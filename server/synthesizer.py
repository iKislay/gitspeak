import logging
from typing import List, Dict, Any
from openai import OpenAI

from config import OLLAMA_API_KEY, OLLAMA_BASE_URL, OLLAMA_MODEL

logger = logging.getLogger(__name__)

# Single instance using the Ollama Cloud endpoint
client = OpenAI(
    api_key=OLLAMA_API_KEY,
    base_url=OLLAMA_BASE_URL
)

def synthesize(query: str, chunks: List[Dict[str, Any]], conversation_history: List[Dict[str, Any]]) -> str:
    """
    Builds the prompt and calls Ollama Cloud (OpenAI-compatible) for a dictation-optimized answer.
    """
    logger.info(f"Synthesizing answer using {OLLAMA_MODEL}...")
    
    system_prompt = """You are a voice assistant that answers questions about a software repository.
You have access to context pulled from PRs, commits, issues, and the README.
Answer conversationally and concisely — this will be spoken aloud, so no markdown, no bullet points, no code blocks.
Always mention the source (PR number, commit SHA, or README) naturally in the sentence.
If you don't know, say so clearly. Do not hallucinate.
Keep your response under 120 words."""

    # Format chunks
    context_str = "Context:\n"
    for chunk in chunks:
        item_type = chunk.get("type", "unknown")
        item_id = chunk.get("id", "unknown")
        author = chunk.get("author", "unknown")
        date = chunk.get("date", "unknown")[:10]  # Grab just YYYY-MM-DD
        text = chunk.get("text", "")
        
        source_label = ""
        if item_type == "pr":
            source_label = f"PR #{item_id} by {author} on {date}"
        elif item_type == "commit":
            source_label = f"Commit {item_id[:7]} by {author} on {date}"
        elif item_type == "readme":
            source_label = "README"
        elif item_type == "file_tree":
            source_label = "File Tree"
        else:
            source_label = f"{item_type} {item_id}"
            
        context_str += f"[{source_label}]: {text}\n"

    user_content = f"{context_str}\nQuestion: {query}"

    # Build messages array keeping only last 4 turns
    messages = [{"role": "system", "content": system_prompt}]
    
    # Take last 4 interactions (if available) for brief context
    recent_history = conversation_history[-4:] if len(conversation_history) > 4 else conversation_history
    messages.extend(recent_history)
    
    # Append the current augmented request
    messages.append({"role": "user", "content": user_content})

    try:
        response = client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=256
        )
        answer = response.choices[0].message.content
        logger.info("Answer synthesized successfully.")
        return answer
    except Exception as e:
        logger.error(f"Synthesis failed: {e}")
        return "I'm sorry, I encountered an error while trying to generate my answer with Ollama. Please ask me again."
