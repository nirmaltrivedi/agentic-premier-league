PERSONA_INSTRUCTIONS = {
    "drama_fan":      "Focus on tension, momentum shifts, and emotional moments. Use vivid language.",
    "stats_nerd":     "Lead with numbers, records, and statistical context. Be precise.",
    "fantasy_player": "Highlight individual player performances and point-scoring moments.",
    "casual":         "Keep it brief and jargon-free. Just the key story in plain language.",
}


def build_prompt(state: dict) -> str:
    profile = state["user_profile"]
    match = state["match_content"]["match"]
    moments = state["scored_moments"][:5]
    scorecard = state["match_content"]["scorecard"]
    interest = profile.get("interest_type", "casual")
    persona_instruction = PERSONA_INSTRUCTIONS.get(interest, PERSONA_INSTRUCTIONS["casual"])

    moments_text = "\n".join(
        f"- [{m['over_ball']}] {m['description']} (relevance: {m['relevance_score']})"
        for m in moments
    )
    scorecard_text = "\n".join(
        f"- {s['player']} ({s['team']}): {s['runs']} runs / {s['wickets']} wkts"
        for s in scorecard
        if s.get("runs") is not None or s.get("wickets") is not None
    )

    return f"""You are a cricket content assistant. Generate a personalized match recap as strict JSON.

USER PROFILE:
- Name: {profile['name']}
- Favorite teams: {profile['favorite_teams']}
- Favorite players: {profile['favorite_players']}
- Interest type: {interest}
- Persona instruction: {persona_instruction}

MATCH: {match['title']} — Winner: {match['winner']}

TOP MOMENTS (ranked by relevance to this user):
{moments_text}

SCORECARD HIGHLIGHTS:
{scorecard_text}

Return ONLY this JSON, no markdown fences:
{{
  "headline": "one punchy sentence",
  "summary": "2-3 sentence recap tailored to this persona",
  "highlights": [
    {{"moment": "description", "why_relevant": "reason for this user", "relevance_score": 0}}
  ],
  "narrative_thread": "one storyline this user would care about most",
  "dropped_content_note": "what you deliberately excluded and why"
}}"""
