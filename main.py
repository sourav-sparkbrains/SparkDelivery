import os
import uuid
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

from common.log import logger
from utils.utility_functions import (
    get_user_id,
    cleanup_static_folder,
    check_valid_query,
    processing_map_path,
    display_map_link,
    format_response
)
from core.deep_agent import get_agent

app = FastAPI()

os.makedirs("static", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://localhost:8001", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    query: str
    user_session_id: Optional[str] = None


class QueryResponse(BaseModel):
    html_response: str
    map_url: Optional[str] = None
    user_session_id: str
    message: str
    is_new_session: bool


@app.post("/query", response_model=QueryResponse)
async def process_delivery_query(
        request_data: QueryRequest,
        request: Request
):
    """
    Process delivery queries with multi-user support.

    Session Management:
    - If user_session_id is None: Create new session
    - If user_session_id is provided: Use existing session for context

    Returns:
    - html_response: Formatted route information
    - map_url: URL to the static map file (e.g., "/static/route_123.html")
    """
    user_session_id = request_data.user_session_id
    is_new_session = False

    try:
        query = request_data.query
        logger.info(f"Received query: {query} | Session ID: {user_session_id}")

        try:
            cleaned_query = check_valid_query(query, user_session_id or "new")
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))

        user_id = get_user_id(request)

        if not user_session_id or user_session_id.strip() == "":
            user_session_id = str(uuid.uuid4())
            is_new_session = True
            logger.info(f"NEW SESSION CREATED: User={user_id} | Thread={user_session_id}")
        else:
            is_new_session = False
            logger.info(f"CONTINUING SESSION: User={user_id} | Thread={user_session_id}")

        config = {
            "configurable": {
                "user_id": user_id,
                "thread_id": user_session_id
            }
        }

        agent = get_agent()

        result = agent.invoke(
            {"messages": [{"role": "user", "content": cleaned_query}]},
            config=config
        )

        response_text = ""
        if isinstance(result, dict) and "messages" in result:
            for message in reversed(result["messages"]):
                if getattr(message, "type", None) == "ai" and getattr(message, "content", None):
                    response_text = message.content
                    break
        else:
            response_text = str(result)

        logger.info("=" * 60)
        logger.info(f"USER: {user_id} | THREAD: {user_session_id}")
        logger.info("AGENT RESPONSE:")
        logger.info(response_text)
        logger.info("=" * 60)

        map_file_path, response_text = processing_map_path(response_text)
        html_response = format_response(response_text)
        map_url = display_map_link(map_file_path) if map_file_path else None


        if is_new_session:
            message = f"New session started! Response generated for: {cleaned_query}"
        else:
            message = f"Response generated for: {cleaned_query}"

        return QueryResponse(
            html_response=html_response,
            map_url=map_url,
            user_session_id=user_session_id,
            message=message,
            is_new_session=is_new_session
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error processing query: {str(e)}")
        import traceback
        traceback.print_exc()

        error_html = f"""
        <div style='padding:25px; background:#ffebee; border-left:5px solid #ef5350; 
                    border-radius:10px; box-shadow:0 2px 8px rgba(0,0,0,0.1);'>
            <h3 style='color:#c62828; margin:0 0 15px 0; font-weight:600;'>Error Occurred</h3>
            <p style='margin:0; color:#b71c1c; line-height:1.6;'><strong>Details:</strong> {str(e)}</p>
        </div>
        """

        if not user_session_id:
            user_session_id = str(uuid.uuid4())

        raise HTTPException(
            status_code=500,
            detail={
                "html_response": error_html,
                "map_url": None,
                "user_session_id": user_session_id,
                "message": f"Error: {str(e)}\n\nPlease try again or rephrase your query.",
                "is_new_session": is_new_session
            }
        )


@app.post("/clear_session")
async def clear_all(user_session_id: Optional[str] = None):
    """Clear all outputs but preserve session for memory continuity"""
    try:
        logger.info(f"Clearing outputs for session: {user_session_id}")
        cleanup_static_folder()

        return {
            "query_input": "",
            "output": "<div style='padding:40px; text-align:center; color:#757575; background:#fafafa; border-radius:10px; min-height:300px; display:flex; align-items:center; justify-content:center;'><div><p style='font-size:1.1em;'>Your route details will appear here</p><p style='font-size:0.9em; margin-top:10px; color:#9e9e9e;'>Enter a query and click Send to get started</p></div></div>",
            "map_output": "<div style='padding:40px; text-align:center; color:#757575; background:#fafafa; border-radius:10px; min-height:600px; display:flex; align-items:center; justify-content:center;'><div><p style='font-size:1.1em;'>Interactive map will appear here</p><p style='font-size:0.9em; margin-top:10px; color:#9e9e9e;'>Plan a route to see the map</p></div></div>",
            "user_session_id": user_session_id
        }
    except Exception as e:
        logger.error(f"Error clearing session {user_session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
