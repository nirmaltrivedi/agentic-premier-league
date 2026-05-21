import json
import os
from typing import TypedDict

from db import get_db


class AgentState(TypedDict):
    user_id: int
    match_id: int
    user_profile: dict
    match_content: dict
    key_moments: list
    scored_moments: list
    recap: dict


def get_user_profile(state: AgentState) -> AgentState:
    conn = get_db()
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE id = %s", (state["user_id"],))
            row = cur.fetchone()
    if row is None:
        raise ValueError(f"User {state['user_id']} not found")
    state["user_profile"] = dict(row)
    return state


def get_match_content(state: AgentState) -> AgentState:
    conn = get_db()
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM matches WHERE id = %s", (state["match_id"],))
            match = cur.fetchone()
            if match is None:
                raise ValueError(f"Match {state['match_id']} not found")

            cur.execute(
                "SELECT * FROM match_events WHERE match_id = %s ORDER BY importance_score DESC",
                (state["match_id"],),
            )
            events = cur.fetchall()

            cur.execute(
                "SELECT * FROM scorecards WHERE match_id = %s",
                (state["match_id"],),
            )
            scorecard = cur.fetchall()

    state["match_content"] = {
        "match": dict(match),
        "events": [dict(e) for e in events],
        "scorecard": [dict(s) for s in scorecard],
    }
    return state


def extract_key_moments(state: AgentState) -> AgentState:
    state["key_moments"] = [
        e for e in state["match_content"]["events"] if e["importance_score"] >= 7
    ]
    return state


def score_relevance(state: AgentState) -> AgentState:
    profile = state["user_profile"]
    fav_players = {p.lower() for p in (profile.get("favorite_players") or [])}
    fav_teams = {t.lower() for t in (profile.get("favorite_teams") or [])}
    match_teams = {
        state["match_content"]["match"]["team_a"].lower(),
        state["match_content"]["match"]["team_b"].lower(),
    }
    team_boost = 1 if fav_teams & match_teams else 0

    scored = []
    for moment in state["key_moments"]:
        score = moment["importance_score"] + team_boost
        if (moment.get("player") or "").lower() in fav_players:
            score += 3
        if (moment.get("player2") or "").lower() in fav_players:
            score += 2
        scored.append({**moment, "relevance_score": score})

    state["scored_moments"] = sorted(scored, key=lambda x: x["relevance_score"], reverse=True)
    return state


def compose_recap(state: AgentState) -> AgentState:
    import google.generativeai as genai
    from agent.prompts import build_prompt

    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-3.1-flash-lite")

    prompt = build_prompt(state)
    response = model.generate_content(prompt)

    raw = response.text.strip()
    # Strip markdown fences if Gemini wraps the response
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0].strip()

    state["recap"] = json.loads(raw)
    return state
