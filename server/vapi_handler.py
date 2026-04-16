import logging
import json
from typing import Dict, Any, List, Optional
from fastapi import Request, HTTPException

from config import VAPI_SECRET
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
