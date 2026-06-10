"""
Budget Agent — validates total shopping cost against user budget.

Pure Python, no LLM calls. Deployed as standalone LangGraph server on port 22004.
Called by supervisor via RemoteGraph.

Integration spec: docs/agents/budget-agent.md
"""
from langgraph.graph import END, START, StateGraph

from shared.distributed_tracing import export_traced_graph
from shared.state import AgentState


def validate_budget(state: AgentState) -> dict:
    """Sum ingredient prices and compare to ``request.budget_usd``.

    Args:
        state: Must contain ``ingredients`` (from shopping agent) and
            ``request.budget_usd`` for validation to run.

    Returns:
        Partial state update with ``budget_status`` (``ok`` | ``over``),
        ``constraint_violations`` when over budget, and updated ``agent_steps``.
        Skips validation (``budget_agent:skipped``) when no budget is set.
    """
    req = state.get("request") or {}
    budget = req.get("budget_usd") if isinstance(req, dict) \
        else getattr(req, "budget_usd", None)

    steps = list(state.get("agent_steps", []))

    if not budget:
        steps.append("budget_agent:skipped")
        return {"budget_status": "ok", "agent_steps": steps}

    total = sum(
        (i.get("price") or 0) if isinstance(i, dict) else (i.price or 0)
        for i in state.get("ingredients", [])
    )

    violations = list(state.get("constraint_violations", []))
    steps.append("budget_agent")

    if total > budget:
        msg = (
            f"Over budget by ${total - budget:.2f} "
            f"(estimated ${total:.2f}, limit ${budget:.2f})"
        )
        if msg not in violations:
            violations.append(msg)
        return {
            "budget_status": "over",
            "constraint_violations": violations,
            "agent_steps": steps,
        }

    return {
        "budget_status": "ok",
        "constraint_violations": violations,
        "agent_steps": steps,
    }


def build_graph():
    """Compile the single-node budget validation graph."""
    builder = StateGraph(AgentState)
    builder.add_node("validate_budget", validate_budget)
    builder.add_edge(START, "validate_budget")
    builder.add_edge("validate_budget", END)
    return builder.compile()


_compiled_graph = build_graph()
graph = export_traced_graph(_compiled_graph, "budget_agent")
