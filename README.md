# Cricket Recap Agent

A personalized cricket match recap system built for the **Personalization & Content Discovery** hackathon track. Users get tailored match recaps based on their fan profile — the same match reads differently for a drama fan versus a stats nerd versus a fantasy player.

---

## What It Does

1. User sends a natural language message: _"Show me Arjun's recap for India vs Pakistan"_
2. The agent classifies intent, looks up the user's profile and the match from Postgres
3. A LangGraph pipeline scores match events by relevance to that user's preferences (favourite players, teams, interest type)
4. Gemini composes a structured recap tailored to the user's persona
5. The recap streams back to the browser as the pipeline progresses
6. Follow-up questions about the same match are answered in a stateful multi-turn session

---

## Architecture

```
Browser (SSE)
    │
    ▼
FastAPI  ──► POST /chat/stream   (routers/chat.py)
             POST /recap/{id}    (routers/recap.py)
             GET  /users|matches (routers/meta.py)
    │
    ▼
LangGraph StateGraph  (agent/graph.py)
    │
    ├── route_intent        → classifies message; resolves user + match from DB
    ├── get_user_profile    → loads user row
    ├── get_match_content   → loads match, events, scorecard
    ├── extract_key_moments → filters events with importance_score ≥ 7
    ├── score_relevance     → boosts by fav players (+3/+2) and fav teams (+1)
    ├── compose_recap       → Gemini call → structured JSON recap
    ├── answer_followup     → builds follow-up prompt; SSE generator streams tokens
    ├── handle_unclear      → returns capability list
    ├── handle_error        → surfaces specific DB lookup errors
    └── mark_done           → sets is_done=True; blocks further turns
    │
    ▼
PostgreSQL (users, matches, match_events, scorecards)
```

**State persistence**: `MemorySaver` checkpointer keyed by `session_id` (UUID generated per page load). Each turn passes only `{"user_message": msg}`; the checkpointer merges it with stored state so `recap`, `user_profile`, etc. survive across turns.

**Streaming**: Node-level progress events (`progress`) are emitted as LangGraph nodes complete. Recap is a single `recap` event after the full pipeline. Follow-up answers stream token-by-token (`token` → `text_done`) directly from Gemini.

---

## Project Structure

```
├── main.py                  # FastAPI app, static file mount, router registration
├── db.py                    # psycopg2 connection with RealDictCursor
├── models.py                # Pydantic response models
├── requirements.txt
├── seed.sql                 # DDL + 3 users + 1 match (India vs Australia T20I)
├── seed_extra.sql           # 9 more users + 4 more matches
├── .env.example
├── agent/
│   ├── graph.py             # StateGraph definition, MemorySaver, conditional edges
│   ├── nodes.py             # AgentState TypedDict + all node functions
│   └── prompts.py           # Persona-aware Gemini prompt builder
├── routers/
│   ├── chat.py              # POST /chat/stream — SSE streaming endpoint
│   ├── recap.py             # POST /recap/{match_id} — Swagger-friendly endpoint
│   └── meta.py              # GET /users, GET /matches
└── static/
    ├── index.html
    ├── css/style.css
    └── js/main.js
```

---

## Database Schema

| Table | Key columns |
|---|---|
| `users` | `id`, `name`, `interest_type` (drama_fan / stats_nerd / fantasy_player / casual), `favorite_players[]`, `favorite_teams[]` |
| `matches` | `id`, `title`, `team_a`, `team_b`, `format`, `result_summary`, `date` |
| `match_events` | `id`, `match_id`, `event_type`, `description`, `player`, `player2`, `importance_score` |
| `scorecards` | `id`, `match_id`, `player_name`, `team`, `runs`, `wickets`, `economy` |

---

## Setup

**Prerequisites**: Python 3.10+, PostgreSQL

```bash
# 1. Clone and create virtualenv
python -m venv hackathon_venv
hackathon_venv\Scripts\activate      # Windows
source hackathon_venv/bin/activate   # Linux/Mac

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create database and seed data
createdb cricket_recap
psql cricket_recap < seed.sql
psql cricket_recap < seed_extra.sql

# 4. Configure environment
cp .env.example .env
# Edit .env — set DATABASE_URL and GEMINI_API_KEY

# 5. Run
uvicorn main:app --reload
```

Open `http://localhost:8000` for the chat UI or `http://localhost:8000/docs` for Swagger.

---

## Example Queries

| Query | What happens |
|---|---|
| `Show me Arjun's recap for India vs Pakistan` | Full personalized recap for drama_fan persona |
| `Why was Bumrah so important in that game?` | Follow-up streamed token-by-token using stored recap context |
| `Show me Priya's recap for the Ashes Test` | Same match, stats_nerd framing — different tone and highlights |
| `done` | Ends session; further messages are blocked |
---

## Planned Improvements

These were not implemented due to time constraints but are high-value additions:

### Edge Case Handling
- LLM JSON parse failures currently fall back silently — should surface a structured error and retry once
- `graph.stream()` can return empty chunks if a node returns `None`; needs a guard
- Concurrent writes to the same `session_id` are not guarded — last write wins
- Gemini rate limit / quota errors are caught generically; should distinguish transient vs. permanent failures

### Structured Logging
- Add Python `logging` with structured JSON output (use `structlog` or `python-json-logger`)
- Log per-node: node name, duration, token counts, user_id, match_id, session_id
- Log intent classification outcomes and DB lookup hits/misses separately
- This enables tracing a full session end-to-end across turns

### Configurable Models
- Currently `gemini-3.1-flash-lite` is hardcoded in `agent/nodes.py` and `routers/chat.py`
- Move to `.env`: `GEMINI_MODEL_ROUTING`, `GEMINI_MODEL_RECAP`, `GEMINI_MODEL_FOLLOWUP`
- Allows swapping models per task (cheap model for routing, capable model for recap composition) without code changes

### Configurable Generation Settings
- `temperature`, `top_p`, `top_k`, `max_output_tokens` are all using Gemini defaults
- Expose via `.env` or a `config.py` dataclass: `RECAP_TEMPERATURE=0.7`, `ROUTING_TEMPERATURE=0.0`
- Low temperature for routing/extraction (deterministic), higher for narrative composition

### Persistent State Management
- Current `MemorySaver` is in-process only — sessions are lost on server restart
- Replace with `langgraph-checkpoint-postgres` (official LangGraph Postgres checkpointer) using the existing `DATABASE_URL`
- Schema migration: `langgraph_checkpoint` table stores serialized state blobs keyed by `thread_id`
- This also enables resuming sessions across browser tabs and inspecting historical sessions

### Database Connection Management
- Current `get_db()` opens a new `psycopg2` connection per node call — fine for demo, inefficient in production
- Replace with a connection pool (`psycopg2.pool.ThreadedConnectionPool` or `asyncpg` pool)
- Add connection health checks and retry on stale connections
- For async FastAPI: migrate to `asyncpg` + `async with pool.acquire()` pattern
