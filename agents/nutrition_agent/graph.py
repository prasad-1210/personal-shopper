"""
Nutrition Agent — interprets dietary profile into concrete constraints.

LLM-powered JSON constraint extraction. Port 22001 local dev.
Called by supervisor via RemoteGraph.

Integration spec: docs/agents/nutrition-agent.md
"""
import json

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from shared.distributed_tracing import export_traced_graph
from shared.prompt_loader import chat_prompt
from shared.state import AgentState

_LLM: ChatOpenAI | None = None


def _get_llm() -> ChatOpenAI:
    global _LLM
    if _LLM is None:
        _LLM = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    return _LLM


def interpret_constraints(state: AgentState) -> dict:
    """Convert dietary profile and calorie limit into structured JSON rules.

    Skips the LLM when both ``dietary_profile`` and ``max_calories_per_serving``
    are empty.

    Args:
        state: Requires ``request`` with optional ``dietary_profile`` and
            ``max_calories_per_serving``.

    Returns:
        ``nutrition_constraints`` dict, ``nutrition_status`` (``ok``),
        and ``agent_steps`` (``nutrition_agent`` or ``nutrition_agent:skipped``).
    """
    req = state.get("request") or {}
    profile = req.get("dietary_profile", "") if isinstance(req, dict) \
        else getattr(req, "dietary_profile", "")
    max_cal = req.get("max_calories_per_serving") if isinstance(req, dict) \
        else getattr(req, "max_calories_per_serving", None)

    steps = list(state.get("agent_steps", []))

    if not profile and not max_cal:
        steps.append("nutrition_agent:skipped")
        return {
            "nutrition_status": "ok",
            "nutrition_constraints": {},
            "agent_steps": steps,
        }

    result = (chat_prompt("nutrition_constraints") | _get_llm()).invoke({
        "profile": profile or "none",
        "calories": str(max_cal) if max_cal else "not specified",
    })

    try:
        constraints = json.loads(result.content.strip())
    except Exception:
        constraints = {"notes": result.content.strip()}

    if max_cal:
        constraints["max_calories"] = max_cal

    steps.append("nutrition_agent")
    return {
        "nutrition_constraints": constraints,
        "nutrition_status": "ok",
        "agent_steps": steps,
    }


def build_graph():
    """Compile the single-node nutrition interpretation graph."""
    builder = StateGraph(AgentState)
    builder.add_node("interpret_constraints", interpret_constraints)
    builder.add_edge(START, "interpret_constraints")
    builder.add_edge("interpret_constraints", END)
    return builder.compile()


_compiled_graph = build_graph()
graph = export_traced_graph(_compiled_graph, "nutrition_agent")
