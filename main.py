from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from models import RecapResponse
from agent.graph import build_graph
from db import get_db

app = FastAPI(
    title="Cricket Recap API",
    description="Personalized match recaps powered by LangGraph + Gemini",
    version="1.0.0",
)

graph = build_graph()


@app.post("/recap/{match_id}", response_model=RecapResponse, summary="Get personalized match recap")
def get_recap(match_id: int, user_id: int):
    """
    Returns a layered, personalized recap of a match tailored to the user's
    interest type and favorite players/teams.

    Try with:
    - user_id=1 (Arjun — drama_fan)
    - user_id=2 (Priya — stats_nerd)
    - user_id=3 (Dev — fantasy_player)
    """
    try:
        result = graph.invoke({"user_id": user_id, "match_id": match_id})
        return {
            "user": result["user_profile"]["name"],
            "interest_type": result["user_profile"]["interest_type"],
            "match": result["match_content"]["match"]["title"],
            "recap": result["recap"],
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/users", summary="List all user personas")
def list_users():
    """Returns all seeded user personas with their interest types."""
    conn = get_db()
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, interest_type, favorite_teams, favorite_players FROM users ORDER BY id")
            rows = cur.fetchall()
    return [dict(r) for r in rows]


@app.get("/matches", summary="List available matches")
def list_matches():
    """Returns all seeded matches."""
    conn = get_db()
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, title, format, winner, match_date FROM matches ORDER BY id")
            rows = cur.fetchall()
    return [dict(r) for r in rows]
