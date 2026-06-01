"""
Shopping Agent — checks store availability and resolves substitutions.
Deployed as a standalone LangGraph server on port 22003 (local dev).
Called by supervisor via RemoteGraph.
"""
import os

from langgraph.graph import END, START, StateGraph

from shared.distributed_tracing import export_traced_graph
from shared.state import AgentState, IngredientAvailability

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
    """Extract ingredients, check availability, resolve substitutions."""
    req = state.get("request") or {}
    pantry_items = (
        req.get("pantry_items", []) if isinstance(req, dict)
        else getattr(req, "pantry_items", [])
    )
    pantry = {p.lower().strip() for p in pantry_items}

    seen: set[str] = set()
    all_ingredients: list[IngredientAvailability] = []

    for recipe in state.get("selected_recipes", []):
        data = get_recipe_ingredients.invoke({"recipe_id": recipe["id"]})
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

    for ing in all_ingredients:
        if uses_rapid:
            result = rapidapi_check.invoke({
                "ingredient": ing.name,
                "location_id": location_id,
                "store": retailer,
            })
        else:
            result = kroger_check.invoke({
                "ingredient": ing.name,
                "location_id": location_id,
            })
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
        subs = get_ingredient_substitutes.invoke({"ingredient_name": ing.name})
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
    builder = StateGraph(AgentState)
    builder.add_node("check_availability", check_availability)
    builder.add_edge(START, "check_availability")
    builder.add_edge("check_availability", END)
    return builder.compile()


_compiled_graph = build_graph()
graph = export_traced_graph(_compiled_graph, "shopping_agent")
