import logging
import json
from typing import Dict, Any, List, Optional
from fastapi import Request, HTTPException

from config import VAPI_SECRET
from server.retriever import search, list_indexed_repos
from server.synthesizer import synthesize
import server.state as state

logger = logging.getLogger(__name__)

# Basic in-memory dict to hold conversation history
# Key: call.id, Value: list of dicts {"role": "...", "content": "..."}
CONVERSATION_HISTORY: Dict[str, List[Dict[str, str]]] = {}

def verify_vapi_secret(request: Request) -> None:
    """
    Verifies that the incoming request has the correct x-vapi-secret header.
    """
    secret = request.headers.get("x-vapi-secret")
    if VAPI_SECRET and secret != VAPI_SECRET:
        logger.warning("Forbidden: Invalid VAPI Secret header.")
        raise HTTPException(status_code=403, detail="Invalid VAPI Secret")

async def get_assistant_config() -> Dict[str, Any]:
    """
    Return assistant config. Injects the active repo into the system prompt
    so the voice call never needs to ask the user which repo to use.
    """
    if state.active_repo:
        first_message = f"Hey! I'm ready to answer questions about {state.active_repo}. What do you want to know?"
        system_prompt = (
            f"You are a voice assistant for the GitHub repository '{state.active_repo}'. "
            f"Always use '{state.active_repo}' as the repo when calling search_codebase unless the user explicitly names a different one. "
            "Answer conversationally — responses will be spoken aloud, so keep them concise."
        )
    else:
        indexed = list_indexed_repos()
        repo_list = ", ".join(indexed) if indexed else "none yet"
        first_message = f"Hey! I can answer questions about these repos: {repo_list}. Which one do you want to explore?"
        system_prompt = (
            "You are a voice assistant for codebases. "
            f"Currently indexed repos: {repo_list}. "
            "Ask the user which repo they want to explore, then use search_codebase to answer their questions."
        )

    return {
        "assistant": {
            "firstMessage": first_message,
            "model": {
                "systemPrompt": system_prompt
            }
        }
    }

async def handle_function_call(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle custom tool/function execution from VAPI.
    Supports both Vapi 1.0 (functionCall) and 2.0 (tool-calls).
    """
    # Extract ID for Vapi 2.0 result mapping
    tool_call_id = payload.get("id")
    
    # Extract common data
    function_data = payload.get("functionCall") or payload.get("function", {})
    name = function_data.get("name")
    
    # Parse parameters (Vapi 2.0 sends them as stringified 'arguments' or a dict)
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
    
    # Check for either name to be safe
    if name in ["search_codebase", "codebase_search"]:
        query = parameters.get("query")
        repo = parameters.get("repo") or state.active_repo

        if not query or not repo:
            answer = "I need both a query and a repository name to search."
        else:
            logger.info(f"VAPI invoked search_codebase: repo={repo}, query='{query}'")
            chunks = search(query=query, repo=repo)
            
            if not chunks:
                answer = f"I couldn't find any context for {repo} in the database."
            else:
                call_id = payload.get("call", {}).get("id", "unknown_call")
                history = CONVERSATION_HISTORY.get(call_id, [])
                answer = synthesize(query=query, chunks=chunks, conversation_history=history)
                
                # Cache turn
                history.append({"role": "user", "content": f"Searched {repo}: {query}"})
                history.append({"role": "assistant", "content": answer})
                CONVERSATION_HISTORY[call_id] = history
        
        # Format response based on Vapi version
        if tool_call_id:
            return {
                "toolCallId": tool_call_id,
                "result": answer
            }
        return {"result": answer}

    logger.warning(f"Unknown function call received: {name}")
    return {"result": "I'm sorry, I don't know how to perform that action yet."}

async def handle_end_of_call_report(payload: Dict[str, Any]) -> None:
    call_id = payload.get("call", {}).get("id")
    if call_id and call_id in CONVERSATION_HISTORY:
        del CONVERSATION_HISTORY[call_id]

async def handle_status_update(payload: Dict[str, Any]) -> None:
    pass

async def process_webhook(request: Request) -> Dict[str, Any]:
    verify_vapi_secret(request)
    body = await request.json()
    message = body.get("message", {})
    msg_type = message.get("type")
    
    if msg_type == "assistant-request":
        return await get_assistant_config()
        
    elif msg_type == "tool-calls":
        # Vapi 2.0 sends a list of toolCalls and expects a 'results' list back
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
        
    return {}
