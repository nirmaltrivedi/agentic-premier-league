import json
import os

import google.generativeai as genai
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.graph import build_graph

router = APIRouter()
graph = build_graph()

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
_gemini = genai.GenerativeModel("gemini-3.1-flash-lite")


class ChatRequest(BaseModel):
    message: str


def _parse_ids(message: str) -> tuple[int, int]:
    prompt = (
        "Extract the user_id and match_id from this message. "
        "Return ONLY a JSON object with integer fields \"user_id\" and \"match_id\". No explanation.\n\n"
        f"Message: {message}"
    )
    raw = _gemini.generate_content(prompt).text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    parsed = json.loads(raw)
    return int(parsed["user_id"]), int(parsed["match_id"])


@router.post("/chat", summary="Natural language query — parses user_id and match_id, then returns recap")
def chat(req: ChatRequest):
    """
    Accepts a plain-English message, extracts user_id and match_id via Gemini,
    then runs the full recap pipeline.

    Example: "Show me the recap for user 2 on match 1"
    """
    try:
        user_id, match_id = _parse_ids(req.message)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not parse user_id and match_id from your message.")

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
