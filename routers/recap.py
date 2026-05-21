from fastapi import APIRouter, HTTPException
from models import RecapResponse
from agent.graph import build_graph

router = APIRouter()
graph = build_graph()


@router.post("/recap/{match_id}", response_model=RecapResponse, summary="Get personalized match recap")
def get_recap(match_id: int, user_id: int):
    """
    Returns a personalized recap tailored to the user's interest type and favourite players/teams.

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
