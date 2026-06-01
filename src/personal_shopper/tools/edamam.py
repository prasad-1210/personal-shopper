"""Edamam Recipe Search API tools — alternative to spoonacular.py
Same function signatures as spoonacular.py so graph.py can swap
between providers using only the RECIPE_PROVIDER env var.
"""
import os
from typing import Any

import httpx
from langchain_core.tools import tool

EDAMAM_BASE = "https://api.edamam.com/api/recipes/v2"

DIET_MAP = {
    "vegetarian": "vegetarian",
    "vegan": "vegan",
    "gluten free": "gluten-free",
    "dairy free": "dairy-free",
    "ketogenic": "keto-friendly",
    "paleo": "paleo",
}

AISLE_MAP = {
    "meat": "Meat",
    "poultry": "Meat",
    "seafood": "Seafood",
    "fish": "Seafood",
    "vegetable": "Produce",
    "produce": "Produce",
    "fruit": "Produce",
    "dairy": "Dairy & Eggs",
    "cheese": "Dairy & Eggs",
    "egg": "Dairy & Eggs",
    "grain": "Pasta & Rice",
    "pasta": "Pasta & Rice",
    "rice": "Pasta & Rice",
    "bread": "Pasta & Rice",
    "spice": "Spices and Seasonings",
    "herb": "Spices and Seasonings",
    "condiment": "Spices and Seasonings",
    "oil": "Oil, Vinegar, Salad Dressing",
    "beverage": "Beverages",
    "juice": "Beverages",
}


def _creds() -> tuple[str, str]:
    app_id = os.environ.get("EDAMAM_APP_ID", "")
    app_key = os.environ.get("EDAMAM_APP_KEY", "")
    if not app_id or not app_key:
        raise OSError(
            "EDAMAM_APP_ID and EDAMAM_APP_KEY must be set in environment"
        )
    return app_id, app_key


def _headers(app_id: str) -> dict[str, str]:
    # Edamam free tier requires Edamam-Account-User header
    return {"Edamam-Account-User": app_id}


def _extract_id(uri: str) -> str:
    # uri format: "http://www.edamam.com/ontologies/edamam.owl#recipe_b79327d..."
    # extract everything after "recipe_" as the usable ID
    if "recipe_" in uri:
        return uri.split("recipe_")[-1]
    return uri.split("#")[-1]


def _map_aisle(food_category: str) -> str:
    cat = (food_category or "").lower()
    for key, aisle in AISLE_MAP.items():
        if key in cat:
            return aisle
    return "General"


@tool
def search_recipes(
    query: str,
    diet: str = "",
    max_ready_time: int = 60,
    number: int = 3,
) -> list[dict[str, Any]]:
    """Search for recipes matching a natural language query using Edamam.
    diet options: vegetarian, vegan, gluten free, dairy free, ketogenic, paleo.
    Returns list of recipes with id, title, ready_in_minutes, servings, source_url.
    Use get_recipe_ingredients to get the full ingredient list for a recipe id.
    """
    app_id, app_key = _creds()

    params: dict[str, str] = {
        "type": "public",
        "app_id": app_id,
        "app_key": app_key,
        "q": query,
    }
    if diet and diet.lower() in DIET_MAP:
        params["health"] = DIET_MAP[diet.lower()]

    r = httpx.get(
        EDAMAM_BASE,
        headers=_headers(app_id),
        params=params,
        timeout=15,
    )
    r.raise_for_status()
    hits = r.json().get("hits", [])

    # First pass: apply time filter
    results = []
    for hit in hits:
        recipe = hit.get("recipe", {})
        ready = int(recipe.get("totalTime") or 0)
        if max_ready_time and ready > 0 and ready > max_ready_time:
            continue
        results.append({
            "id": _extract_id(recipe.get("uri", "")),
            "title": recipe.get("label", ""),
            "ready_in_minutes": ready,
            "servings": int(recipe.get("yield") or 4),
            "source_url": recipe.get("url", ""),
        })
        if len(results) >= number:
            break

    # Second pass: if time filter removed everything, return without filter
    if not results:
        for hit in hits[:number]:
            recipe = hit.get("recipe", {})
            results.append({
                "id": _extract_id(recipe.get("uri", "")),
                "title": recipe.get("label", ""),
                "ready_in_minutes": int(recipe.get("totalTime") or 0),
                "servings": int(recipe.get("yield") or 4),
                "source_url": recipe.get("url", ""),
            })

    return results


@tool
def get_recipe_ingredients(recipe_id: str) -> dict[str, Any]:
    """Get the full ingredient list for an Edamam recipe by its ID.
    Returns recipe title, servings, and structured ingredients with aisle mapping.
    Use the id returned by search_recipes.
    """
    app_id, app_key = _creds()

    r = httpx.get(
        f"{EDAMAM_BASE}/{recipe_id}",
        headers=_headers(app_id),
        params={
            "type": "public",
            "app_id": app_id,
            "app_key": app_key,
        },
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    recipe = data.get("recipe", {})

    ingredients = []
    for ing in recipe.get("ingredients", []):
        ingredients.append({
            "name": ing.get("food", ""),
            "original": ing.get("text", ""),
            "amount": float(ing.get("quantity") or 0),
            "unit": ing.get("measure", ""),
            "aisle": _map_aisle(ing.get("foodCategory", "")),
        })

    return {
        "recipe_id": recipe_id,
        "title": recipe.get("label", ""),
        "servings": int(recipe.get("yield") or 4),
        "ingredients": ingredients,
    }


@tool
def get_ingredient_substitutes(ingredient_name: str) -> dict[str, Any]:
    """Get substitution suggestions for an unavailable ingredient.
    Note: Edamam has no substitutes endpoint.
    Returns empty list — graph handles this with a generic fallback message.
    """
    return {
        "ingredient": ingredient_name,
        "substitutes": [],
    }
