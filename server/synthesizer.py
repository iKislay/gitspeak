import logging
import httpx
from typing import List, Dict, Any

from config import OLLAMA_API_KEY, OLLAMA_BASE_URL, OLLAMA_MODEL

logger = logging.getLogger(__name__)

def synthesize(query: str, chunks: List[Dict[str, Any]], conversation_history: List[Dict[str, Any]]) -> str:
    """
    Builds the prompt and calls Ollama Cloud (OpenAI-compatible) for a voice-optimized answer.
    """
    logger.info(f"Synthesizing answer using {OLLAMA_MODEL} at {OLLAMA_BASE_URL}...")

    system_prompt = """You are a voice assistant that answers questions about a software repository.
You have access to context pulled from PRs, commits, issues, and the README.
Answer conversationally and concisely — this will be spoken aloud, so no markdown, no bullet points, no code blocks.
Always mention the source (PR number, commit SHA, or README) naturally in the sentence.
If you don't know, say so clearly. Do not hallucinate.
Keep your response under 120 words."""

    # Format chunks into context string
    context_str = "Context:\n"
    for chunk in chunks:
        item_type = chunk.get("type", "unknown")
        item_id = chunk.get("id", "unknown")
        author = chunk.get("author", "unknown")
        date = chunk.get("date", "unknown")[:10]
        text = chunk.get("text", "")

        if item_type == "pr":
            source_label = f"PR #{item_id} by {author} on {date}"
        elif item_type == "commit":
            source_label = f"Commit {item_id[:7]} by {author} on {date}"
        elif item_type == "readme":
            source_label = "README"
        elif item_type == "file_tree":
            source_label = "File Tree"
        elif item_type == "source_file":
            file_path = chunk.get("path", item_id)
            language = chunk.get("language", "")
            source_label = f"File {file_path}" + (f" ({language})" if language else "")
        else:
            source_label = f"{item_type} {item_id}"

        context_str += f"[{source_label}]: {text}\n"

    user_content = f"{context_str}\nQuestion: {query}"

    messages = [{"role": "system", "content": system_prompt}]
    recent_history = conversation_history[-4:] if len(conversation_history) > 4 else conversation_history
    messages.extend(recent_history)
    messages.append({"role": "user", "content": user_content})

    url = OLLAMA_BASE_URL.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {OLLAMA_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 256
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            answer = data["choices"][0]["message"]["content"]
            logger.info("Answer synthesized successfully.")
            return answer
    except Exception as e:
        logger.error(f"Synthesis failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response {e.response.status_code}: {e.response.text}")
        return "I'm sorry, I encountered an error while generating my answer. Please check the server logs."
