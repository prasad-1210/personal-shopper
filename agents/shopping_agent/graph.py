"""
Shopping Agent — checks store availability and resolves substitutions.

No LLM; calls recipe + retailer APIs per ingredient. Port 22003 local dev.
Called by supervisor via RemoteGraph.

Integration spec: docs/agents/shopping-agent.md
"""
import os

from langgraph.graph import END, START, StateGraph

from shared.distributed_tracing import export_traced_graph
from shared.state import AgentState, IngredientAvailability
from shared.tool_tracing import invoke_tool

USE_MOCK = os.environ.get("USE_MOCK_TOOLS", "false").lower() == "true"
RECIPE_PROVIDER = os.environ.get("RECIPE_PROVIDER", "edamam")

KROGER_FAMILY = {
    "kroger", "ralphs", "king soopers", "fred meyer",
    "fry's", "harris teeter", "smith's", "foodsco",
}
RAPIDAPI_RETAILERS = {
    "walmart", "target", "costco", "amazon", "bestbuy", "best buy",
}

if USE_MOCK:
    from personal_shopper.tools.mock_tools import (
        check_product_availability as kroger_check,
    )
    from personal_shopper.tools.mock_tools import (
        check_product_availability as rapidapi_check,
    )
    from personal_shopper.tools.mock_tools import (
        get_ingredient_substitutes,
        get_recipe_ingredients,
    )
else:
    from personal_shopper.tools.kroger import (
        check_product_availability as kroger_check,
    )
    from personal_shopper.tools.rapidapi_search import (
        check_product_availability as rapidapi_check,
    )
    if RECIPE_PROVIDER == "edamam":
        from personal_shopper.tools.edamam import (
            get_ingredient_substitutes,
            get_recipe_ingredients,
        )
    else:
        from personal_shopper.tools.spoonacular import (
            get_ingredient_substitutes,
            get_recipe_ingredients,
        )


def _get_retailer(state: AgentState) -> str:
    """Normalise ``request.preferred_retailer`` to Kroger or a RapidAPI store key."""
    req = state.get("request") or {}
    retailer = req.get("preferred_retailer", "kroger") if isinstance(req, dict) \
        else getattr(req, "preferred_retailer", "kroger")
    retailer = str(retailer).lower().strip()
    if retailer in KROGER_FAMILY:
        return "kroger"
    if retailer in RAPIDAPI_RETAILERS:
        return retailer
    return "kroger"


def check_availability(state: AgentState) -> dict:
    """Expand recipes to ingredients, check store stock, resolve substitutes.

    Args:
        state: Requires ``selected_recipes``, ``request``, and ``location_id``.
            Excludes ``request.pantry_items`` from the list.

    Returns:
        ``ingredients`` and ``shopping_list`` (identical lists of
        ``IngredientAvailability``), plus ``agent_steps``.
    """
    req = state.get("request") or {}
    pantry_items = (
        req.get("pantry_items", []) if isinstance(req, dict)
        else getattr(req, "pantry_items", [])
    )
    pantry = {p.lower().strip() for p in pantry_items}

    provider = "mock" if USE_MOCK else RECIPE_PROVIDER
    seen: set[str] = set()
    all_ingredients: list[IngredientAvailability] = []

    for recipe in state.get("selected_recipes", []):
        recipe_id = recipe["id"]
        data = invoke_tool(
            get_recipe_ingredients,
            {"recipe_id": recipe_id},
            provider=provider,
            label=f"{provider}.get_recipe_ingredients:{recipe_id}",
            tags=["shopping_agent"],
            metadata={"recipe_id": recipe_id, "recipe_title": recipe.get("title", "")},
        )
        for ing in data.get("ingredients", []):
            key = ing["name"].lower().strip()
            if key in seen or key in pantry:
                continue
            seen.add(key)
            all_ingredients.append(IngredientAvailability(
                name=ing["name"],
                original=ing["original"],
                aisle=ing.get("aisle", "General"),
                available=True,
            ))

    retailer = _get_retailer(state)
    location_id = state.get("location_id") or "00000000"
    uses_rapid = retailer in RAPIDAPI_RETAILERS
    updated: list[IngredientAvailability] = []

    check_provider = "mock" if USE_MOCK else ("rapidapi" if uses_rapid else "kroger")
    for ing in all_ingredients:
        if uses_rapid:
            result = invoke_tool(
                rapidapi_check,
                {
                    "ingredient": ing.name,
                    "location_id": location_id,
                    "store": retailer,
                },
                provider=check_provider,
                label=f"{check_provider}.check_product_availability:{ing.name}@{retailer}",
                tags=["shopping_agent", retailer],
                metadata={
                    "ingredient": ing.name,
                    "retailer": retailer,
                    "location_id": location_id,
                },
            )
        else:
            result = invoke_tool(
                kroger_check,
                {
                    "ingredient": ing.name,
                    "location_id": location_id,
                },
                provider=check_provider,
                label=f"{check_provider}.check_product_availability:{ing.name}",
                tags=["shopping_agent", "kroger"],
                metadata={"ingredient": ing.name, "location_id": location_id},
            )
        updated.append(ing.model_copy(update={
            "available": result.get("available", False),
            "product_description": result.get("product_description"),
            "price": result.get("price"),
        }))

    final: list[IngredientAvailability] = []
    for ing in updated:
        if ing.available:
            final.append(ing)
            continue
        subs = invoke_tool(
            get_ingredient_substitutes,
            {"ingredient_name": ing.name},
            provider=provider,
            label=f"{provider}.get_ingredient_substitutes:{ing.name}",
            tags=["shopping_agent"],
            metadata={"ingredient": ing.name},
        )
        chosen = (subs.get("substitutes") or ["Ask store staff"])[0]
        final.append(ing.model_copy(update={"substitute": chosen}))

    steps = list(state.get("agent_steps", []))
    steps.append("shopping_agent")
    return {
        "ingredients": final,
        "shopping_list": final,
        "agent_steps": steps,
    }


def build_graph():
    """Compile the single-node shopping availability graph."""
    builder = StateGraph(AgentState)
    builder.add_node("check_availability", check_availability)
    builder.add_edge(START, "check_availability")
    builder.add_edge("check_availability", END)
    return builder.compile()


_compiled_graph = build_graph()
graph = export_traced_graph(_compiled_graph, "shopping_agent")
