import json
import os
from typing import Optional

import google.generativeai as genai
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.graph import build_graph
from db import get_db

router = APIRouter()
graph  = build_graph()

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
_gemini = genai.GenerativeModel("gemini-3.1-flash-lite")


# ── Pydantic models ────────────────────────────────────────────────────────────

class HistoryMessage(BaseModel):
    role: str       # "user" | "assistant"
    content: str    # plain text summary used as context

class ChatRequest(BaseModel):
    message:     str
    history:     list[HistoryMessage] = []
    last_recap:  Optional[dict]       = None   # full recap payload from last response


class ChatResponse(BaseModel):
    type:    str            # "recap" | "text" | "error"
    message: str            # plain-text answer (always populated)
    data:    Optional[dict] = None  # recap payload when type == "recap"


# ── LLM helpers ───────────────────────────────────────────────────────────────

def _llm(prompt: str) -> str:
    raw = _gemini.generate_content(prompt).text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return raw


def _classify_intent(message: str, has_recap_context: bool) -> str:
    """Returns 'recap' | 'followup' | 'unclear'."""
    ctx_note = (
        "There IS a previously discussed match recap available as context."
        if has_recap_context
        else "There is NO prior recap context in this conversation."
    )
    prompt = f"""You are a routing agent for a cricket recap assistant.
{ctx_note}

Classify the user's message into exactly one intent:
- "recap"    — the user wants a personalized match recap (mentions a person's name and a match/team)
- "followup" — the user is asking a question about a previously discussed match (only valid if prior context exists)
- "unclear"  — cannot determine intent

Return ONLY valid JSON: {{"intent": "recap"}} or {{"intent": "followup"}} or {{"intent": "unclear"}}

Message: {message}"""
    result = json.loads(_llm(prompt))
    return result.get("intent", "unclear")


def _extract_recap_params(message: str) -> tuple[str, str]:
    """Returns (user_name, match_hint). Raises ValueError if either is missing."""
    prompt = f"""Extract the person's name and the match reference from this message.
Return ONLY valid JSON with string fields "user_name" and "match_hint".
Use null if a field cannot be found.

Message: {message}"""
    parsed = json.loads(_llm(prompt))
    user_name  = (parsed.get("user_name")  or "").strip()
    match_hint = (parsed.get("match_hint") or "").strip()
    if not user_name or not match_hint:
        raise ValueError("Please mention both a user name and a match in your query.")
    return user_name, match_hint


def _answer_followup(message: str, last_recap: dict, history: list[HistoryMessage]) -> str:
    history_text = "\n".join(
        f"{m.role.upper()}: {m.content}" for m in history[-6:]  # last 3 turns
    ) or "None"
    prompt = f"""You are a cricket analyst assistant. Answer the user's question using the match recap context below.
Be concise, insightful, and plain text only (no markdown, no bullet points).

RECAP CONTEXT:
{json.dumps(last_recap, indent=2)}

CONVERSATION HISTORY:
{history_text}

USER QUESTION: {message}"""
    return _llm(prompt)


# ── DB lookups ────────────────────────────────────────────────────────────────

def _lookup_user(name: str) -> dict:
    conn = get_db()
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM users WHERE LOWER(name) = LOWER(%s)",
                (name,)
            )
            row = cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"No user named '{name}' found in the database."
        )
    return dict(row)


def _lookup_match(hint: str) -> dict:
    conn = get_db()
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM matches WHERE LOWER(title) ILIKE %s ORDER BY id LIMIT 1",
                (f"%{hint.lower()}%",)
            )
            row = cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"No match found matching '{hint}'. Try being more specific (e.g. 'India vs Pakistan T20 World Cup')."
        )
    return dict(row)


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse,
             summary="Conversational cricket assistant — recap requests and follow-up questions")
def chat(req: ChatRequest):
    """
    Smart chat endpoint. Routes between two behaviours:

    **Recap request** — mention a user name and a match:
    > "Give me Arjun's recap for India vs Pakistan"

    **Follow-up question** — ask anything about the last recap:
    > "Why did Bumrah matter so much in that game?"

    Sends `history` (list of prior messages) and `last_recap` (previous recap payload)
    to maintain conversation context across turns.
    """
    intent = _classify_intent(req.message, has_recap_context=req.last_recap is not None)

    # ── Follow-up ──────────────────────────────────────────────────────────────
    if intent == "followup":
        if not req.last_recap:
            return ChatResponse(
                type="text",
                message="I don't have a match recap in context yet. Ask me for a recap first — e.g. 'Show me Arjun's recap for India vs Pakistan'."
            )
        answer = _answer_followup(req.message, req.last_recap, req.history)
        return ChatResponse(type="text", message=answer)

    # ── Unclear ────────────────────────────────────────────────────────────────
    if intent == "unclear":
        return ChatResponse(
            type="text",
            message="I can generate personalized match recaps and answer follow-up questions. Try: \"Show me Priya's recap for the India vs Australia T20\" or ask something about the last match we discussed."
        )

    # ── Recap ──────────────────────────────────────────────────────────────────
    try:
        user_name, match_hint = _extract_recap_params(req.message)
    except ValueError as e:
        return ChatResponse(type="text", message=str(e))

    # These raise HTTPException (404) if not found
    user  = _lookup_user(user_name)
    match = _lookup_match(match_hint)

    try:
        result = graph.invoke({"user_id": user["id"], "match_id": match["id"]})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    recap_data = {
        "user":          result["user_profile"]["name"],
        "interest_type": result["user_profile"]["interest_type"],
        "match":         result["match_content"]["match"]["title"],
        "recap":         result["recap"],
    }
    return ChatResponse(
        type="recap",
        message=recap_data["recap"]["headline"],
        data=recap_data,
    )
