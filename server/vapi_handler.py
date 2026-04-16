import logging
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
    
    Args:
        request: The incoming FastAPI Request object.
        
    Raises:
        HTTPException: If the secret is missing or invalid.
    """
    secret = request.headers.get("x-vapi-secret")
    if VAPI_SECRET and secret != VAPI_SECRET:
        logger.warning("Forbidden: Invalid VAPI Secret header.")
        raise HTTPException(status_code=403, detail="Invalid VAPI Secret")

async def get_assistant_config() -> Dict[str, Any]:
    """
    Return the assistant config when VAPI asks.
    Matches the schema expected by VAPI for dynamic assistant configuration.
    
    Returns:
        A dictionary containing the assistant configuration.
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
    
    Args:
        payload: The function-call message payload from VAPI.
        
    Returns:
        A dictionary containing the 'result' for VAPI to speak.
    """
    call_id = payload.get("call", {}).get("id", "unknown_call")
    function_call = payload.get("functionCall", {})
    name = function_call.get("name")
    parameters = function_call.get("parameters", {})
    
    if name == "search_codebase":
        query = parameters.get("query")
        repo = parameters.get("repo")
        
        if not query or not repo:
            return {"result": "I need both a query and a repository name to search. Could you provide those?"}
            
        logger.info(f"VAPI invoked search_codebase: repo={repo}, query='{query}'")
        
        # 1. Retrieve relevant chunks from Qdrant
        chunks = search(query=query, repo=repo)
        
        if not chunks:
            return {"result": f"I couldn't find any context for that in the {repo} repository. Is it possible it hasn't been indexed yet?"}
            
        # 2. Get conversation history for context
        history = CONVERSATION_HISTORY.get(call_id, [])
        
        # 3. Synthesize the final spoken answer
        answer = synthesize(query=query, chunks=chunks, conversation_history=history)
        
        # Cache this turn in history
        history.append({"role": "user", "content": f"Searched {repo} for: {query}"})
        history.append({"role": "assistant", "content": answer})
        CONVERSATION_HISTORY[call_id] = history
        
        return {"result": answer}

    logger.warning(f"Unknown function call received: {name}")
    return {"result": "I'm sorry, I don't know how to perform that action yet."}

async def handle_end_of_call_report(payload: Dict[str, Any]) -> None:
    """
    Log the call report and clean up in-memory history.
    
    Args:
        payload: The end-of-call-report message payload from VAPI.
    """
    call_id = payload.get("call", {}).get("id")
    summary = payload.get("summary", "No summary provided.")
    ended_reason = payload.get("endedReason", "Unknown")
    
    logger.info(f"Call {call_id} ended. Reason: {ended_reason}. Summary: {summary}")
    
    if call_id and call_id in CONVERSATION_HISTORY:
        del CONVERSATION_HISTORY[call_id]

async def handle_status_update(payload: Dict[str, Any]) -> None:
    """
    Log status updates during the call.
    
    Args:
        payload: The status-update message payload from VAPI.
    """
    call_id = payload.get("call", {}).get("id")
    status = payload.get("status")
    logger.info(f"Call {call_id} status updated to: {status}")

async def process_webhook(request: Request) -> Dict[str, Any]:
    """
    Main webhook entry point for processing VAPI events.
    
    Args:
        request: The incoming FastAPI Request.
        
    Returns:
        The JSON response for VAPI.
    """
    verify_vapi_secret(request)
    body = await request.json()
    
    message = body.get("message", {})
    msg_type = message.get("type")
    
    if msg_type == "assistant-request":
        return await get_assistant_config()
        
    elif msg_type == "function-call":
        return await handle_function_call(message)
        
    elif msg_type == "end-of-call-report":
        await handle_end_of_call_report(message)
        return {}
        
    elif msg_type == "status-update":
        await handle_status_update(message)
        return {}
        
    logger.debug(f"Received unhandled VAPI message type: {msg_type}")
    return {}

