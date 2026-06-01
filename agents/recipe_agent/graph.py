"""
Recipe Agent — finds recipes matching user request and constraints.
Deployed as a standalone LangGraph server on port 22002 (local dev).
Called by supervisor via RemoteGraph.
"""
import os

from langgraph.graph import END, START, StateGraph

from shared.distributed_tracing import export_traced_graph
from shared.state import AgentState

USE_MOCK = os.environ.get("USE_MOCK_TOOLS", "false").lower() == "true"
RECIPE_PROVIDER = os.environ.get("RECIPE_PROVIDER", "edamam")

if USE_MOCK:
    from personal_shopper.tools.mock_tools import search_recipes
elif RECIPE_PROVIDER == "edamam":
    from personal_shopper.tools.edamam import search_recipes
else:
    from personal_shopper.tools.spoonacular import search_recipes


def find_recipes(state: AgentState) -> dict:
    """Find recipes matching user constraints."""
    req = state.get("request") or {}
    keywords = req.get("meal_keywords", []) if isinstance(req, dict) \
        else getattr(req, "meal_keywords", [])
    restrictions = req.get("dietary_restrictions", []) if isinstance(req, dict) \
        else getattr(req, "dietary_restrictions", [])
    profile = req.get("dietary_profile", "") if isinstance(req, dict) \
        else getattr(req, "dietary_profile", "")

    diet_parts = list(restrictions)
    if profile and profile not in diet_parts:
        diet_parts.append(profile)
    diet = diet_parts[0] if diet_parts else ""

    budget_status = state.get("budget_status", "unchecked")
    iteration = state.get("iteration", 0)

    queries = []
    if keywords:
        words = keywords[0].strip().split()
        if len(words) >= 2:
            queries.append(" ".join(words[-2:]))
        queries.append(words[-1])
    queries.extend(["curry", "chicken", "pasta"])

    recipes = []
    for query in queries:
        if budget_status == "over" and iteration > 1:
            query = f"simple {query}"
        recipes = search_recipes.invoke({
            "query": query,
            "diet": diet,
            "max_ready_time": 90,
            "number": 3,
        })
        if recipes:
            break

    steps = list(state.get("agent_steps", []))
    steps.append(f"recipe_agent:iter{iteration}")
    return {
        "selected_recipes": recipes,
        "ingredients": [],
        "shopping_list": [],
        "budget_status": "unchecked",
        "agent_steps": steps,
    }


def build_graph():
    builder = StateGraph(AgentState)
    builder.add_node("find_recipes", find_recipes)
    builder.add_edge(START, "find_recipes")
    builder.add_edge("find_recipes", END)
    return builder.compile()


_compiled_graph = build_graph()
graph = export_traced_graph(_compiled_graph, "recipe_agent")
