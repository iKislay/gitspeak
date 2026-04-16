import logging
import json
from typing import Dict, Any, List, Optional
from fastapi import Request, HTTPException

from config import VAPI_SECRET
from server.retriever import search
from server.synthesizer import synthesize

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
    Return the assistant config when VAPI asks.
    """
    return {
        "assistant": {
            "firstMessage": "Hey, which repo do you want to explore? Give me the owner slash repo name.",
            "model": {
                "provider": "openai",
                "model": "gpt-4o",
                "systemPrompt": "You are a voice assistant for codebases. Keep responses crisp and spoken format.",
                "functions": [
                    {
                        "name": "search_codebase",
                        "description": "Search the indexed codebase to answer developer questions.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The exact question the developer is asking about the codebase."
                                },
                                "repo": {
                                    "type": "string",
                                    "description": "The repository slug, formatted as owner/repo, extracted from user context."
                                }
                            },
                            "required": ["query", "repo"]
                        }
                    }
                ]
            },
            "voice": {
                "provider": "playht",
                "voiceId": "jennifer"
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
    
    # Parse parameters (Vapi 2.0 sends them as stringified 'arguments')
    parameters = function_data.get("parameters")
    if not parameters and "arguments" in function_data:
        try:
            parameters = json.loads(function_data["arguments"])
        except Exception as e:
            logger.error(f"Failed to parse tool arguments: {e}")
            parameters = {}
    
    if name == "search_codebase":
        query = parameters.get("query")
        repo = parameters.get("repo")
        
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
