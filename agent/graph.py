from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from agent.nodes import (
    AgentState,
    route_intent,
    get_user_profile,
    get_match_content,
    extract_key_moments,
    score_relevance,
    compose_recap,
    answer_followup,
    handle_unclear,
    handle_error,
    mark_done,
)

# Single in-process checkpointer — lives for the lifetime of the server
_checkpointer = MemorySaver()


def _get_route(state: AgentState) -> str:
    """Reads the intent set by route_intent and dispatches to the correct subgraph."""
    return state.get("intent", "unclear")


def build_graph():
    g = StateGraph(AgentState)

    # ── Nodes ──────────────────────────────────────────────────────────────────
    g.add_node("route_intent",        route_intent)
    g.add_node("get_user_profile",    get_user_profile)
    g.add_node("get_match_content",   get_match_content)
    g.add_node("extract_key_moments", extract_key_moments)
    g.add_node("score_relevance",     score_relevance)
    g.add_node("compose_recap",       compose_recap)
    g.add_node("answer_followup",     answer_followup)
    g.add_node("handle_unclear",      handle_unclear)
    g.add_node("handle_error",        handle_error)
    g.add_node("mark_done",           mark_done)

    # ── Entry ──────────────────────────────────────────────────────────────────
    g.set_entry_point("route_intent")

    # ── Conditional edge from route_intent ─────────────────────────────────────
    g.add_conditional_edges(
        "route_intent",
        _get_route,
        {
            "recap":    "get_user_profile",
            "followup": "answer_followup",
            "done":     "mark_done",
            "unclear":  "handle_unclear",
            "error":    "handle_error",
        },
    )

    # ── Recap pipeline ─────────────────────────────────────────────────────────
    g.add_edge("get_user_profile",    "get_match_content")
    g.add_edge("get_match_content",   "extract_key_moments")
    g.add_edge("extract_key_moments", "score_relevance")
    g.add_edge("score_relevance",     "compose_recap")

    # ── Terminal edges → END ───────────────────────────────────────────────────
    for terminal in ["compose_recap", "answer_followup",
                     "handle_unclear", "handle_error", "mark_done"]:
        g.add_edge(terminal, END)

    return g.compile(checkpointer=_checkpointer)
