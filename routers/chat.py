import json
import os

import google.generativeai as genai
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.graph import build_graph

router = APIRouter()
graph  = build_graph()

genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))
_gemini = genai.GenerativeModel("gemini-3.1-flash-lite")

# Human-readable labels shown in the UI progress indicator
NODE_LABELS = {
    "route_intent":        "Understanding your request…",
    "get_user_profile":    "Loading user profile…",
    "get_match_content":   "Fetching match data…",
    "extract_key_moments": "Extracting key moments…",
    "score_relevance":     "Scoring relevance…",
    "compose_recap":       "Composing recap…",
    "answer_followup":     "Preparing answer…",
    "handle_unclear":      "Processing…",
    "handle_error":        "Processing…",
    "mark_done":           "Wrapping up…",
}


class ChatStreamRequest(BaseModel):
    session_id: str     # client-generated UUID; maps to LangGraph thread_id
    message:    str


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _generate_events(session_id: str, message: str):
    """
    Sync generator that yields SSE events:
      progress  — one per LangGraph node as it completes
      recap     — full structured recap payload
      token     — one LLM token at a time (follow-up streaming)
      text_done — signals end of token stream
      text      — single plain-text response (unclear / error / done session)
      done_session — user ended the conversation
      error     — unrecoverable exception
    """
    config = {"configurable": {"thread_id": session_id}}

    try:
        # Stream node-level progress events
        for chunk in graph.stream({"user_message": message}, config, stream_mode="updates"):
            node_name = list(chunk.keys())[0]
            label = NODE_LABELS.get(node_name, node_name)
            yield _sse({"type": "progress", "node": node_name, "label": label})

        # Read final state from checkpointer
        final         = graph.get_state(config).values
        response_type = final.get("response_type") or "unclear"

        if response_type == "recap":
            data = {
                "user":          final["user_profile"]["name"],
                "interest_type": final["user_profile"]["interest_type"],
                "match":         final["match_content"]["match"]["title"],
                "recap":         final["recap"],
            }
            yield _sse({"type": "recap", "data": data})

        elif response_type == "followup_stream":
            # Token-level streaming for follow-up answers
            prompt = final.get("response_text", "")
            for chunk in _gemini.generate_content(prompt, stream=True):
                if chunk.text:
                    yield _sse({"type": "token", "text": chunk.text})
            yield _sse({"type": "text_done"})

        elif response_type == "done":
            yield _sse({"type": "done_session"})

        else:
            # text | error | unclear
            msg = final.get("response_text") or "I'm not sure how to help with that."
            yield _sse({"type": "text", "message": msg})

    except Exception as exc:
        yield _sse({"type": "error", "message": str(exc)})

    yield "data: [DONE]\n\n"


@router.post(
    "/chat/stream",
    summary="Conversational cricket assistant (SSE streaming)",
    response_description="Server-Sent Events stream",
)
def chat_stream(req: ChatStreamRequest):
    """
    Streaming chat endpoint. Returns a `text/event-stream` response.

    Each turn sends one JSON event per SSE `data:` line:
    - `progress`     — LangGraph node started (with human-readable label)
    - `recap`        — full personalized recap card
    - `token`        — one LLM token (follow-up streaming)
    - `text_done`    — end of token stream
    - `text`         — single plain-text response
    - `done_session` — user ended the conversation
    - `error`        — error message

    **session_id**: generate a UUID client-side on page load; re-use it across
    turns so the MemorySaver checkpointer maintains conversation state.

    Examples:
    - `"Show me Arjun's recap for India vs Pakistan"`
    - `"Why was Bumrah so important in that game?"` (follow-up)
    - `"done"` (ends session)
    """
    return StreamingResponse(
        _generate_events(req.session_id, req.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control":   "no-cache",
            "X-Accel-Buffering": "no",   # disables nginx buffering
        },
    )
