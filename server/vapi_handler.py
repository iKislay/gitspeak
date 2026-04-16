import logging
import json
from typing import Dict, Any, List, Optional
from fastapi import Request, HTTPException

from config import VAPI_SECRET, BACKEND_URL
from server.retriever import search, search_across_repos, list_indexed_repos
from server.synthesizer import synthesize
from server.standup import generate_standup_summary
from ingest.github_fetcher import GithubFetcher
import server.state as state

logger = logging.getLogger(__name__)

# In-memory conversation history: call_id → [{role, content}]
CONVERSATION_HISTORY: Dict[str, List[Dict[str, str]]] = {}

# Single shared fetcher instance (already authenticated)
_fetcher = GithubFetcher()


# ─────────────────────────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────────────────────────

def verify_vapi_secret(request: Request) -> None:
    secret = request.headers.get("x-vapi-secret")
    if VAPI_SECRET and secret != VAPI_SECRET:
        logger.warning("Forbidden: Invalid VAPI Secret header.")
        raise HTTPException(status_code=403, detail="Invalid VAPI Secret")


# ─────────────────────────────────────────────────────────────────────────────
# Assistant config (injected on every call-start)
# ─────────────────────────────────────────────────────────────────────────────

async def get_assistant_config() -> Dict[str, Any]:
    """
    Return assistant config. Injects the active repo and an enriched system
    prompt that describes all available tools and their voice-safety guidelines.
    """
    if state.active_repo:
        first_message = (
            f"Hey! I'm your Codebase Oracle for {state.active_repo}. "
            "You can ask me to search the code, read a file, list a directory, "
            "get a commit diff, give you a standup briefing, or even create a GitHub issue. What do you want?"
        )
        system_prompt = (
            f"You are a voice assistant for the GitHub repository '{state.active_repo}'. "
            f"Always use '{state.active_repo}' as the repo unless the user names a different one. "
            "Answer conversationally — responses will be spoken aloud, so no markdown or bullet points. "
            "You have access to these tools:\n"
            "- search_codebase(query, repo): semantic search over PRs, commits, and source code\n"
            "- search_all_repos(query): search across every indexed repository\n"
            "- read_file(repo, path): read a specific file from the repository\n"
            "- list_directory(repo, path): list files in a directory\n"
            "- get_recent_diff(repo, sha): get the changes introduced by a commit\n"
            "- get_standup_report(repo, hours): summarise recent activity for standup"
        )
    else:
        indexed = list_indexed_repos()
        repo_list = ", ".join(indexed) if indexed else "none yet"
        first_message = (
            f"Hey! I'm your Codebase Oracle. I have these repos indexed: {repo_list}. "
            "Which one do you want to explore?"
        )
        system_prompt = (
            "You are a voice assistant for GitHub codebases. "
            f"Currently indexed repos: {repo_list}. "
            "Ask the user which repo they want to explore, then call the appropriate tool. "
            "You can also cross-search all repos using search_all_repos."
        )

    return {
        "assistant": {
            "firstMessage": first_message,
            "model": {"systemPrompt": system_prompt},
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tool routing
# ─────────────────────────────────────────────────────────────────────────────

async def handle_function_call(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dispatch a VAPI tool call to the correct handler.
    Supports both Vapi 1.0 (functionCall) and 2.0 (tool-calls).
    """
    tool_call_id = payload.get("id")

    function_data = payload.get("functionCall") or payload.get("function", {})
    name = function_data.get("name", "")

    # Parse parameters
    parameters = function_data.get("parameters")
    if not parameters and "arguments" in function_data:
        args = function_data["arguments"]
        if isinstance(args, dict):
            parameters = args
        else:
            try:
                parameters = json.loads(args)
            except Exception as e:
                logger.error(f"Failed to parse tool arguments: {e}")
                parameters = {}
    parameters = parameters or {}

    call_id = payload.get("call", {}).get("id", "unknown_call")

    # ── Route ──────────────────────────────────────────────────────────────

    if name in ("search_codebase", "codebase_search"):
        answer = await _handle_search_codebase(parameters, call_id)

    elif name == "search_all_repos":
        answer = await _handle_search_all_repos(parameters, call_id)

    elif name == "read_file":
        answer = await _handle_read_file(parameters)

    elif name == "list_directory":
        answer = await _handle_list_directory(parameters)

    elif name == "get_recent_diff":
        answer = await _handle_get_recent_diff(parameters)

    elif name == "get_standup_report":
        answer = await _handle_get_standup_report(parameters)

    elif name == "get_latest_commits":
        answer = await _handle_get_latest_commits(parameters)

    else:
        logger.warning(f"Unknown function call: '{name}'")
        answer = "I'm sorry, I don't know how to perform that action yet."

    # Vapi 2.0 response format
    if tool_call_id:
        return {"toolCallId": tool_call_id, "result": answer}
    return {"result": answer}


# ─────────────────────────────────────────────────────────────────────────────
# Individual tool handlers
# ─────────────────────────────────────────────────────────────────────────────

async def _handle_search_codebase(params: Dict, call_id: str) -> str:
    query = params.get("query")
    repo = params.get("repo") or state.active_repo
    if not query or not repo:
        return "I need both a query and a repository name to search."
    logger.info(f"[Tool] search_codebase: repo={repo}, query='{query}'")
    chunks = search(query=query, repo=repo)
    if not chunks:
        return f"I couldn't find any relevant context for that question in {repo}."
    history = CONVERSATION_HISTORY.get(call_id, [])
    answer = synthesize(query=query, chunks=chunks, conversation_history=history)
    history.append({"role": "user", "content": f"Searched {repo}: {query}"})
    history.append({"role": "assistant", "content": answer})
    CONVERSATION_HISTORY[call_id] = history
    return answer


async def _handle_search_all_repos(params: Dict, call_id: str) -> str:
    query = params.get("query")
    if not query:
        return "Please give me something to search for across all repos."
    logger.info(f"[Tool] search_all_repos: query='{query}'")
    repos = list_indexed_repos()
    chunks = search_across_repos(query=query, repos=repos)
    if not chunks:
        return "I couldn't find anything relevant across all indexed repositories."
    history = CONVERSATION_HISTORY.get(call_id, [])
    answer = synthesize(query=query, chunks=chunks, conversation_history=history)
    history.append({"role": "user", "content": f"Cross-repo search: {query}"})
    history.append({"role": "assistant", "content": answer})
    CONVERSATION_HISTORY[call_id] = history
    return answer


async def _handle_read_file(params: Dict) -> str:
    repo = params.get("repo") or state.active_repo
    path = params.get("path", "").strip()
    if not repo or not path:
        return "I need a repository and a file path to read."
    logger.info(f"[Tool] read_file: repo={repo}, path={path}")
    result = _fetcher.read_file(repo, path)
    if "error" in result:
        return result["error"]
    content = result["content"]
    # Trim to ~600 chars for voice output
    if len(content) > 600:
        content = content[:600].rsplit("\n", 1)[0] + "… I've shown the first part of the file."
    return f"Here's what I see in {path}: {content}"


async def _handle_list_directory(params: Dict) -> str:
    repo = params.get("repo") or state.active_repo
    path = params.get("path", "").strip()
    if not repo:
        return "I need a repository to list a directory."
    logger.info(f"[Tool] list_directory: repo={repo}, path='{path}'")
    result = _fetcher.list_directory(repo, path)
    if "error" in result:
        return result["error"]
    entries = result.get("entries", [])
    if not entries:
        return f"The directory '{path or '/'}' is empty."
    dirs = [e["name"] for e in entries if e["type"] == "dir"]
    files = [e["name"] for e in entries if e["type"] == "file"]
    parts = []
    if dirs:
        parts.append(f"{len(dirs)} folder{'s' if len(dirs) > 1 else ''}: {', '.join(dirs[:10])}")
    if files:
        parts.append(f"{len(files)} file{'s' if len(files) > 1 else ''}: {', '.join(files[:10])}")
    suffix = " and more" if (len(dirs) > 10 or len(files) > 10) else ""
    loc = path or "the root"
    return f"The {loc} directory contains {'; and '.join(parts)}{suffix}."


async def _handle_get_recent_diff(params: Dict) -> str:
    repo = params.get("repo") or state.active_repo
    sha = params.get("sha", "").strip()
    if not repo or not sha:
        return "I need a repository and a commit SHA to get a diff."
    logger.info(f"[Tool] get_recent_diff: repo={repo}, sha={sha}")
    result = _fetcher.get_commit_diff(repo, sha)
    if "error" in result:
        return result["error"]
    message = result.get("message", "").split("\n")[0]
    author = result.get("author", "Unknown")
    files = result.get("files", [])
    if not files:
        return f"Commit {sha[:7]} by {author} — '{message}' — had no file changes."
    file_names = ", ".join(f["filename"] for f in files[:5])
    summary = f"Commit {sha[:7]} by {author}: '{message}'. Changed files: {file_names}."
    if len(files) > 5:
        summary += f" Plus {len(files) - 5} more files."
    return summary


async def _handle_get_latest_commits(params: Dict) -> str:
    repo = params.get("repo") or state.active_repo
    count = int(params.get("count", 5))
    if not repo:
        return "I need a repository to get recent commits."
    logger.info(f"[Tool] get_latest_commits: repo={repo}, count={count}")
    result = _fetcher.get_latest_commits(repo, count=count)
    if "error" in result:
        return result["error"]
    commits = result.get("commits", [])
    if not commits:
        return f"No commits found in {repo}."
    latest = commits[0]
    summary = (
        f"The most recent commit in {repo} was {latest['sha']} by {latest['author']} "
        f"on {latest['date'][:10]}: {latest['message']}."
    )
    if len(commits) > 1:
        rest = "; ".join(
            f"{c['sha']} by {c['author']} on {c['date'][:10]}: {c['message']}"
            for c in commits[1:]
        )
        summary += f" Before that: {rest}."
    return summary


async def _handle_get_standup_report(params: Dict) -> str:
    repo = params.get("repo") or state.active_repo
    hours = int(params.get("hours", 24))
    if not repo:
        return "I need a repository to generate a standup report."
    logger.info(f"[Tool] get_standup_report: repo={repo}, hours={hours}")
    activity = _fetcher.fetch_recent_activity(repo, since_hours=hours)
    if "error" in activity:
        return activity["error"]
    return generate_standup_summary(activity)


# ─────────────────────────────────────────────────────────────────────────────
# Lifecycle handlers
# ─────────────────────────────────────────────────────────────────────────────

async def handle_end_of_call_report(payload: Dict[str, Any]) -> None:
    call_id = payload.get("call", {}).get("id")
    if call_id and call_id in CONVERSATION_HISTORY:
        del CONVERSATION_HISTORY[call_id]
        logger.info(f"Cleared conversation history for call {call_id}")


async def handle_status_update(payload: Dict[str, Any]) -> None:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Main webhook dispatcher
# ─────────────────────────────────────────────────────────────────────────────

async def process_webhook(request: Request) -> Dict[str, Any]:
    verify_vapi_secret(request)
    body = await request.json()
    message = body.get("message", {})
    msg_type = message.get("type")

    if msg_type == "assistant-request":
        return await get_assistant_config()

    elif msg_type == "tool-calls":
        # Vapi 2.0: list of toolCalls → list of results
        tool_calls = message.get("toolCalls", [])
        results = []
        for tc in tool_calls:
            res = await handle_function_call(tc)
            results.append(res)
        return {"results": results}

    elif msg_type == "function-call":
        # Vapi 1.0 (legacy)
        return await handle_function_call(message)

    elif msg_type == "end-of-call-report":
        await handle_end_of_call_report(message)
        return {}

    elif msg_type == "status-update":
        await handle_status_update(message)
        return {}

    return {}


# ─────────────────────────────────────────────────────────────────────────────
# Inline Vapi assistant config (served to the web frontend)
# ─────────────────────────────────────────────────────────────────────────────

async def build_vapi_inline_config() -> Dict[str, Any]:
    """
    Build a complete Vapi inline assistant configuration that can be passed
    directly to vapi.start() in the browser SDK. This eliminates the need
    to pre-configure an assistant in the Vapi dashboard.

    The BACKEND_URL env var must point to the publicly accessible backend
    (e.g. the Railway URL) so that Vapi can reach the /webhook endpoint.
    """
    webhook_url = BACKEND_URL.rstrip("/") + "/webhook"

    # ── System prompt & greeting ────────────────────────────────────────────
    if state.active_repo:
        first_message = (
            f"Hey! I'm SonarCode, your AI dev assistant. "
            f"I'm ready to answer questions about {state.active_repo}. "
            "You can ask me to search the codebase, read a file, get a standup briefing, and more. What do you want to know?"
        )
        system_prompt = (
            f"You are SonarCode, a voice assistant for the GitHub repository '{state.active_repo}'. "
            f"ALWAYS use '{state.active_repo}' as the repo argument in every tool call unless the user explicitly names a different one. "
            "Your responses are spoken aloud — NEVER use markdown, bullet points, or code blocks. "
            "Keep responses under 150 words. Sound like a friendly senior developer on a video call. "
            "When the tool returns an answer, relay it conversationally — do not add filler phrases like 'just a sec' or 'hold on'. "
            "ALWAYS call a tool before answering — never say you cannot fetch information without first trying a tool call. "
            "\n\nTool routing guide:"
            "\n- 'what is this project about?' or 'describe the repo' → call read_file with path='README.md'"
            "\n- 'when was the last commit?' or 'show recent commits' → call get_latest_commits"
            "\n- 'what happened recently?' or standup questions → call get_standup_report"
            "\n- questions about code, features, architecture → call search_codebase"
            "\n- 'read file X' or 'show me X' → call read_file"
            "\n- 'list files in X' → call list_directory"
            "\n- 'what changed in commit ABC?' → call get_recent_diff with the sha"
        )
    else:
        indexed = list_indexed_repos()
        repo_list = ", ".join(indexed) if indexed else "none yet"
        first_message = (
            f"Hey! I'm SonarCode. I have these repos indexed: {repo_list}. "
            "Which one do you want to explore?"
        )
        system_prompt = (
            "You are SonarCode, a voice codebase assistant. "
            f"Indexed repos: {repo_list}. "
            "Ask the user which repo to explore, then use the appropriate tool. "
            "ALWAYS call a tool before answering — never say you cannot fetch information without first trying a tool call. "
            "Responses are spoken aloud — no markdown."
        )

    # ── Tool definitions ─────────────────────────────────────────────────────
    def server_tool(name: str, description: str, properties: Dict, required: List[str]) -> Dict:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
            "server": {"url": webhook_url},
        }

    tools = [
        server_tool(
            "search_codebase",
            "Semantic search over PRs, commits, README, and source code files in a repository.",
            {
                "query": {"type": "string", "description": "The question or search query about the codebase"},
                "repo":  {"type": "string", "description": "Repository slug in owner/repo format"},
            },
            ["query"],
        ),
        server_tool(
            "search_all_repos",
            "Search across all indexed repositories when the user does not specify a particular repo.",
            {
                "query": {"type": "string", "description": "The question or search query"},
            },
            ["query"],
        ),
        server_tool(
            "read_file",
            "Read the full content of a specific file in the repository.",
            {
                "repo": {"type": "string", "description": "Repository slug in owner/repo format"},
                "path": {"type": "string", "description": "File path relative to the repo root, e.g. src/main.py"},
            },
            ["path"],
        ),
        server_tool(
            "list_directory",
            "List files and folders inside a directory of the repository.",
            {
                "repo": {"type": "string", "description": "Repository slug in owner/repo format"},
                "path": {"type": "string", "description": "Directory path, or empty string for the root"},
            },
            [],
        ),
        server_tool(
            "get_recent_diff",
            "Get the file changes introduced by a specific commit SHA.",
            {
                "repo": {"type": "string", "description": "Repository slug in owner/repo format"},
                "sha":  {"type": "string", "description": "Full or short commit SHA"},
            },
            ["sha"],
        ),
        server_tool(
            "get_standup_report",
            "Summarise recent merged PRs and commits for a daily standup briefing.",
            {
                "repo":  {"type": "string", "description": "Repository slug in owner/repo format"},
                "hours": {"type": "number", "description": "How many hours back to look (default 24)"},
            },
            [],
        ),
        server_tool(
            "get_latest_commits",
            "Get the most recent commits in the repository. Use this when asked 'when was the last commit?' or 'show me recent commits'.",
            {
                "repo":  {"type": "string", "description": "Repository slug in owner/repo format"},
                "count": {"type": "number", "description": "Number of recent commits to return (default 5)"},
            },
            [],
        ),
    ]

    return {
        "name": "SonarCode",
        "firstMessage": first_message,
        "model": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "systemPrompt": system_prompt,
            "tools": tools,
        },
        "voice": {
            "provider": "openai",
            "voiceId": "shimmer",
        },
        "transcriber": {
            "provider": "deepgram",
            "model": "nova-2",
            "language": "en",
        },
    }
