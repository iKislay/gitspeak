import logging
from typing import Dict, Any

import httpx
from config import OLLAMA_API_KEY, OLLAMA_BASE_URL, OLLAMA_MODEL

logger = logging.getLogger(__name__)


def generate_standup_summary(activity: Dict[str, Any]) -> str:
    """
    Synthesizes a voice-optimized standup briefing from recent repo activity.
    Result is conversational, under 200 words, and suitable to be spoken aloud.
    """
    repo = activity.get("repo", "the repository")
    window = activity.get("window_hours", 24)
    merged_prs = activity.get("merged_prs", [])
    commits = activity.get("commits", [])
    open_prs = activity.get("open_prs_updated", [])

    if not merged_prs and not commits and not open_prs:
        return f"There's been no activity in {repo} in the last {window} hours. Looks like a quiet window."

    # Build structured context for the LLM
    context_lines = [f"Repository: {repo}", f"Time window: Last {window} hours", ""]

    if merged_prs:
        context_lines.append(f"Merged Pull Requests ({len(merged_prs)}):")
        for pr in merged_prs[:10]:
            context_lines.append(
                f"  - PR #{pr['number']} '{pr['title']}' by {pr['author']} at {pr['merged_at'][:10]}"
            )

    if commits:
        context_lines.append(f"\nNew Commits ({len(commits)}):")
        for c in commits[:15]:
            context_lines.append(f"  - {c['sha']} '{c['message']}' by {c['author']} on {c['date'][:10]}")

    if open_prs:
        context_lines.append(f"\nOpen PRs with Recent Activity ({len(open_prs)}):")
        for pr in open_prs[:5]:
            context_lines.append(
                f"  - PR #{pr['number']} '{pr['title']}' by {pr['author']} (updated {pr['updated_at'][:10]})"
            )

    context = "\n".join(context_lines)

    system_prompt = (
        "You are a voice assistant giving a developer their morning standup briefing. "
        "Summarize the recent repository activity in a natural, spoken style. "
        "Do NOT use markdown, bullet points, or code blocks — this will be read aloud. "
        "Mention who did what, group similar changes, and keep it under 200 words. "
        "Speak directly, like you're briefing someone in a meeting."
    )

    user_message = (
        f"Here is the recent activity data:\n\n{context}\n\n"
        f"Give me a spoken standup briefing for this repository."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    url = OLLAMA_BASE_URL.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {OLLAMA_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "temperature": 0.6,
        "max_tokens": 350,
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            answer = data["choices"][0]["message"]["content"]
            logger.info("Standup summary synthesized successfully.")
            return answer
    except Exception as e:
        logger.error(f"Standup synthesis failed: {e}")
        # Fallback: build a basic summary ourselves
        parts = []
        if merged_prs:
            pr_titles = ", ".join(f"PR {p['number']}" for p in merged_prs[:3])
            parts.append(f"{len(merged_prs)} pull request{'s' if len(merged_prs) > 1 else ''} merged: {pr_titles}")
        if commits:
            parts.append(f"{len(commits)} new commit{'s' if len(commits) > 1 else ''} pushed")
        if open_prs:
            parts.append(f"{len(open_prs)} open pull request{'s' if len(open_prs) > 1 else ''} had updates")
        if parts:
            return f"In the last {window} hours for {repo}: " + ", and ".join(parts) + "."
        return f"No significant activity in {repo} in the last {window} hours."
