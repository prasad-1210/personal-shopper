"""Spoonacular API recipe and substitute tools.

Drop-in alternative to ``edamam.py`` when ``RECIPE_PROVIDER=spoonacular``.
Requires ``SPOONACULAR_API_KEY``.
"""
import os
from typing import Any

import httpx
from langchain_core.tools import tool

BASE_URL = "https://api.spoonacular.com"


def _get_api_key() -> str:
    api_key = os.environ.get("SPOONACULAR_API_KEY")
    if not api_key:
        raise OSError("SPOONACULAR_API_KEY environment variable is not set")
    return api_key


@tool
def search_recipes(
    query: str,
    diet: str = "",
    max_ready_time: int = 60,
    number: int = 3,
    exclude_ingredients: list[str] | None = None,
    max_calories: int | None = None,
) -> list[dict[str, Any]]:
    """Search Spoonacular for recipes matching a query.

    Args:
        query: Dish search text.
        diet: Spoonacular diet filter string.
        max_ready_time: Maximum ready time in minutes.
        number: Max results.
        exclude_ingredients: Comma-separated ``excludeIngredients`` for Spoonacular.
        max_calories: Maximum calories per serving (``maxCalories``).

    Returns:
        Recipe dicts compatible with Edamam shape (id, title, servings, …).
    """
    params: dict[str, str | int | bool] = {
        "apiKey": _get_api_key(),
        "query": query,
        "number": number,
        "maxReadyTime": max_ready_time,
        "addRecipeInformation": True,
    }
    if diet:
        params["diet"] = diet
    if exclude_ingredients:
        params["excludeIngredients"] = ",".join(exclude_ingredients[:8])
    if max_calories:
        params["maxCalories"] = max_calories
    response = httpx.get(f"{BASE_URL}/recipes/complexSearch", params=params, timeout=30)
    response.raise_for_status()
    results = response.json().get("results", [])
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "ready_in_minutes": r.get("readyInMinutes"),
            "servings": r.get("servings"),
            "source_url": r.get("sourceUrl", ""),
        }
        for r in results
    ]


@tool
def get_recipe_ingredients(recipe_id: int) -> dict[str, Any]:
    """Fetch extended ingredients for a Spoonacular recipe ID.

    Returns same shape as ``edamam.get_recipe_ingredients`` for graph compatibility.
    """
    params = {"apiKey": _get_api_key()}
    response = httpx.get(
        f"{BASE_URL}/recipes/{recipe_id}/information", params=params, timeout=30
    )
    response.raise_for_status()
    data = response.json()
    return {
        "recipe_id": data["id"],
        "title": data["title"],
        "servings": data.get("servings", 4),
        "ingredients": [
            {
                "name": ing["name"],
                "original": ing.get("original", ing["name"]),
                "amount": ing.get("amount"),
                "unit": ing.get("unit", ""),
                "aisle": ing.get("aisle", "Other"),
            }
            for ing in data.get("extendedIngredients", [])
        ],
    }


@tool
def get_ingredient_substitutes(ingredient_name: str) -> dict[str, Any]:
    """Call Spoonacular substitutes API for an unavailable ingredient.

    Returns ``ingredient`` and ``substitutes`` string list.
    """
    params = {"apiKey": _get_api_key(), "ingredientName": ingredient_name}
    response = httpx.get(
        f"{BASE_URL}/food/ingredients/substitutes", params=params, timeout=30
    )
    response.raise_for_status()
    data = response.json()
    return {
        "ingredient": ingredient_name,
        "substitutes": data.get("substitutes", []),
    }
