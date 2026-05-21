import json
import os
from typing import TypedDict

import google.generativeai as genai

from db import get_db

genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))
_gemini = genai.GenerativeModel("gemini-3.1-flash-lite")


# ── State ──────────────────────────────────────────────────────────────────────

class AgentState(TypedDict, total=False):
    # Per-turn input
    user_message:   str

    # Routing
    intent:         str     # "recap" | "followup" | "done" | "unclear" | "error"

    # Recap params — resolved in route_intent
    user_name:      str
    match_hint:     str
    user_id:        int
    match_id:       int

    # Recap pipeline
    user_profile:   dict
    match_content:  dict
    key_moments:    list
    scored_moments: list
    recap:          dict    # persists across turns via checkpointer

    # Response signal read by the SSE generator
    response_type:  str     # "recap" | "followup_stream" | "text" | "done" | "error"
    response_text:  str     # followup prompt OR clarification/error message

    # Session lifecycle
    is_done:        bool


# ── LLM + DB helpers ───────────────────────────────────────────────────────────

CAPABILITIES = (
    "I can help you with:\n"
    "  • Personalized match recaps — e.g. \"Show me Arjun's recap for India vs Pakistan\"\n"
    "  • Follow-up questions about the last recap — e.g. \"Why was Bumrah so important?\"\n"
    "  • End the session — just say \"done\" or \"that's all\"\n\n"
    "Please try a more specific query."
)


def _llm_json(prompt: str) -> dict:
    raw = _gemini.generate_content(prompt).text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return json.loads(raw)


def _db_user(name: str) -> dict | None:
    conn = get_db()
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE LOWER(name) = LOWER(%s)", (name,))
            row = cur.fetchone()
    return dict(row) if row else None


def _db_match(hint: str) -> dict | None:
    conn = get_db()
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM matches WHERE LOWER(title) ILIKE %s ORDER BY id LIMIT 1",
                (f"%{hint.lower()}%",),
            )
            row = cur.fetchone()
    return dict(row) if row else None


# ── Nodes ──────────────────────────────────────────────────────────────────────

def route_intent(state: AgentState) -> AgentState:
    """
    Classifies user intent and, for recap requests, resolves user + match from DB.
    This is the single decision gate — all routing logic lives here.
    """

    # Block further actions once session is ended
    if state.get("is_done"):
        return {**state,
                "intent":        "unclear",
                "response_type": "text",
                "response_text": "This session has ended. Refresh the page to start a new conversation."}

    has_recap = bool(state.get("recap"))

    try:
        result = _llm_json(f"""You are a routing agent for a cricket recap assistant.
{"There IS a previous match recap in context." if has_recap else "There is NO prior recap context."}

Classify the user's message into exactly one intent:
- "recap"    — wants a personalized match recap (mentions a person's name AND a match/team)
- "followup" — asking a question about the previously discussed match (only valid if prior context exists)
- "done"     — ending the session (says done, thanks, bye, that's all, exit, quit, etc.)
- "unclear"  — cannot determine intent

Return ONLY valid JSON: {{"intent": "recap"|"followup"|"done"|"unclear"}}

Message: {state["user_message"]}""")
        intent = result.get("intent", "unclear")
    except Exception:
        intent = "unclear"

    # followup requires prior recap
    if intent == "followup" and not has_recap:
        return {**state,
                "intent":        "unclear",
                "response_type": "text",
                "response_text": "I don't have a match recap in context yet. Ask for a recap first — e.g. \"Show me Arjun's recap for India vs Pakistan\"."}

    if intent != "recap":
        return {**state, "intent": intent}

    # ── Recap: extract + validate ──────────────────────────────────────────────
    try:
        params     = _llm_json(f"""Extract the person's name and the match reference from this message.
Return ONLY valid JSON with string fields "user_name" and "match_hint". Use null if not found.
Message: {state["user_message"]}""")
        user_name  = (params.get("user_name")  or "").strip()
        match_hint = (params.get("match_hint") or "").strip()
    except Exception:
        user_name = match_hint = ""

    if not user_name or not match_hint:
        return {**state,
                "intent":        "error",
                "response_type": "error",
                "response_text": "Please mention both a user name and a match — e.g. \"Show me Arjun's recap for India vs Pakistan\"."}

    user = _db_user(user_name)
    if not user:
        return {**state,
                "intent":        "error",
                "response_type": "error",
                "response_text": (f"No user named '{user_name}' found in the database.\n"
                                  "Available users: Arjun, Priya, Dev, Liam, Sophie, Zara, Hassan, Emma, Oliver, Sneha, Raj, Preet.")}

    match = _db_match(match_hint)
    if not match:
        return {**state,
                "intent":        "error",
                "response_type": "error",
                "response_text": (f"No match found matching '{match_hint}'.\n"
                                  "Try: 'India vs Australia T20', 'India vs Pakistan World Cup', "
                                  "'Ashes Test', 'MI vs CSK Final', 'RCB vs PBKS'.")}

    return {**state,
            "intent":     "recap",
            "user_name":  user_name,
            "match_hint": match_hint,
            "user_id":    user["id"],
            "match_id":   match["id"]}


def get_user_profile(state: AgentState) -> AgentState:
    conn = get_db()
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE id = %s", (state["user_id"],))
            row = cur.fetchone()
    return {**state, "user_profile": dict(row)}


def get_match_content(state: AgentState) -> AgentState:
    conn = get_db()
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM matches WHERE id = %s", (state["match_id"],))
            match = cur.fetchone()
            cur.execute(
                "SELECT * FROM match_events WHERE match_id = %s ORDER BY importance_score DESC",
                (state["match_id"],),
            )
            events = cur.fetchall()
            cur.execute("SELECT * FROM scorecards WHERE match_id = %s", (state["match_id"],))
            scorecard = cur.fetchall()

    return {**state, "match_content": {
        "match":     dict(match),
        "events":    [dict(e) for e in events],
        "scorecard": [dict(s) for s in scorecard],
    }}


def extract_key_moments(state: AgentState) -> AgentState:
    moments = [e for e in state["match_content"]["events"] if e["importance_score"] >= 7]
    return {**state, "key_moments": moments}


def score_relevance(state: AgentState) -> AgentState:
    profile     = state["user_profile"]
    fav_players = {p.lower() for p in (profile.get("favorite_players") or [])}
    fav_teams   = {t.lower() for t in (profile.get("favorite_teams")   or [])}
    match_teams = {
        state["match_content"]["match"]["team_a"].lower(),
        state["match_content"]["match"]["team_b"].lower(),
    }
    team_boost = 1 if fav_teams & match_teams else 0

    scored = []
    for m in state["key_moments"]:
        score = m["importance_score"] + team_boost
        if (m.get("player")  or "").lower() in fav_players: score += 3
        if (m.get("player2") or "").lower() in fav_players: score += 2
        scored.append({**m, "relevance_score": score})

    return {**state,
            "scored_moments": sorted(scored, key=lambda x: x["relevance_score"], reverse=True)}


def compose_recap(state: AgentState) -> AgentState:
    from agent.prompts import build_prompt

    model    = genai.GenerativeModel("gemini-3.1-flash-lite")
    prompt   = build_prompt(state)
    response = model.generate_content(prompt)

    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    return {**state, "recap": json.loads(raw), "response_type": "recap"}


def answer_followup(state: AgentState) -> AgentState:
    """Builds the Gemini prompt; the SSE generator streams the actual LLM response."""
    prompt = (
        "You are a cricket analyst. Answer the user's question based on the match recap below.\n"
        "Be concise and insightful. Plain text only — no markdown, no bullet points.\n\n"
        f"RECAP CONTEXT:\n{json.dumps(state.get('recap', {}), indent=2)}\n\n"
        f"QUESTION: {state['user_message']}"
    )
    return {**state, "response_type": "followup_stream", "response_text": prompt}


def handle_unclear(state: AgentState) -> AgentState:
    msg = state.get("response_text") or CAPABILITIES
    return {**state, "response_type": "text", "response_text": msg}


def handle_error(state: AgentState) -> AgentState:
    # response_text already set by route_intent; just ensure type is correct
    return {**state, "response_type": "error"}


def mark_done(state: AgentState) -> AgentState:
    return {**state, "response_type": "done", "is_done": True}
