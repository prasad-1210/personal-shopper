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
    "gluten-free": "gluten-free",
    "dairy free": "dairy-free",
    "dairy-free": "dairy-free",
    "ketogenic": "keto-friendly",
    "keto": "keto-friendly",
    "keto-friendly": "keto-friendly",
    "low-carb": "low-carb",
    "low carb": "low-carb",
    "diabetic": "low-sugar",
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


def _recipe_hit_to_dict(recipe: dict[str, Any]) -> dict[str, Any]:
    cal_per_serving = None
    if recipe.get("calories") and recipe.get("yield"):
        try:
            cal_per_serving = round(recipe["calories"] / recipe["yield"], 1)
        except (ZeroDivisionError, TypeError):
            pass
    return {
        "id": _extract_id(recipe.get("uri", "")),
        "title": recipe.get("label", ""),
        "ready_in_minutes": int(recipe.get("totalTime") or 0),
        "servings": int(recipe.get("yield") or 4),
        "source_url": recipe.get("url", ""),
        "calories_per_serving": cal_per_serving,
    }


@tool
def search_recipes(
    query: str,
    diet: str = "",
    max_ready_time: int = 60,
    number: int = 3,
    exclude_ingredients: list[str] | None = None,
    max_calories: int | None = None,
) -> list[dict[str, Any]]:
    """Search Edamam Recipe API for meals matching a natural language query.

    Args:
        query: Dish or ingredient search text.
        diet: Optional health label (vegetarian, vegan, gluten-free, keto, …).
        max_ready_time: Max cook time in minutes; relaxed if no results match.
        number: Maximum recipes to return.
        exclude_ingredients: Ingredients to exclude (repeated ``excluded`` params).
        max_calories: Maximum calories per serving (Edamam ``calories`` param).

    Returns:
        List of recipe dicts including optional ``calories_per_serving``.
    """
    app_id, app_key = _creds()

    search_query = query
    params: dict[str, Any] = {
        "type": "public",
        "app_id": app_id,
        "app_key": app_key,
        "q": search_query,
    }
    if diet:
        health_label = DIET_MAP.get(diet.lower(), "")
        if health_label:
            params["health"] = health_label
        else:
            search_query = f"{diet} {query}"
            params["q"] = search_query

    if exclude_ingredients:
        params["excluded"] = list(exclude_ingredients)[:8]

    if max_calories:
        params["calories"] = str(max_calories)

    r = httpx.get(
        EDAMAM_BASE,
        headers=_headers(app_id),
        params=params,
        timeout=15,
    )
    r.raise_for_status()
    hits = r.json().get("hits", [])

    results = []
    for hit in hits:
        recipe = hit.get("recipe", {})
        ready = int(recipe.get("totalTime") or 0)
        if max_ready_time and ready > 0 and ready > max_ready_time:
            continue
        results.append(_recipe_hit_to_dict(recipe))
        if len(results) >= number:
            break

    if not results:
        for hit in hits[:number]:
            results.append(_recipe_hit_to_dict(hit.get("recipe", {})))

    return results


@tool
def get_recipe_ingredients(recipe_id: str) -> dict[str, Any]:
    """Fetch structured ingredients for one Edamam recipe.

    Args:
        recipe_id: ID suffix from ``search_recipes`` (after ``recipe_`` in URI).

    Returns:
        Dict with ``recipe_id``, ``title``, ``servings``, and ``ingredients``
        list (``name``, ``original``, ``amount``, ``unit``, ``aisle``).
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
    """Placeholder substitutes — Edamam has no substitutes API.

    Args:
        ingredient_name: Ingredient that was unavailable at the store.

    Returns:
        ``{"ingredient": name, "substitutes": []}`` — shopping agent uses
        ``"Ask store staff"`` when the list is empty.
    """
    return {
        "ingredient": ingredient_name,
        "substitutes": [],
    }
