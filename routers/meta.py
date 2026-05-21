from fastapi import APIRouter
from db import get_db

router = APIRouter()


@router.get("/users", summary="List all user personas")
def list_users():
    """Returns all seeded user personas with their interest types."""
    conn = get_db()
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, interest_type, favorite_teams, favorite_players FROM users ORDER BY id"
            )
            rows = cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/matches", summary="List available matches")
def list_matches():
    """Returns all seeded matches."""
    conn = get_db()
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, title, format, winner, match_date FROM matches ORDER BY id")
            rows = cur.fetchall()
    return [dict(r) for r in rows]
