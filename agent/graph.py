from langgraph.graph import StateGraph, END

from agent.nodes import (
    AgentState,
    get_user_profile,
    get_match_content,
    extract_key_moments,
    score_relevance,
    compose_recap,
)


def build_graph():
    g = StateGraph(AgentState)

    g.add_node("get_user_profile",    get_user_profile)
    g.add_node("get_match_content",   get_match_content)
    g.add_node("extract_key_moments", extract_key_moments)
    g.add_node("score_relevance",     score_relevance)
    g.add_node("compose_recap",       compose_recap)

    g.set_entry_point("get_user_profile")
    g.add_edge("get_user_profile",    "get_match_content")
    g.add_edge("get_match_content",   "extract_key_moments")
    g.add_edge("extract_key_moments", "score_relevance")
    g.add_edge("score_relevance",     "compose_recap")
    g.add_edge("compose_recap",       END)

    return g.compile()
