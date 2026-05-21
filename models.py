from typing import List, Optional
from pydantic import BaseModel


class Highlight(BaseModel):
    moment: str
    why_relevant: str
    relevance_score: int


class RecapPayload(BaseModel):
    headline: str
    summary: str
    highlights: List[Highlight]
    narrative_thread: str
    dropped_content_note: str


class RecapResponse(BaseModel):
    user: str
    interest_type: str
    match: str
    recap: RecapPayload
