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
    query: str, diet: str = "", max_ready_time: int = 60, number: int = 3
) -> list[dict[str, Any]]:
    """Search for recipes matching a query."""
    params: dict[str, str | int | bool] = {
        "apiKey": _get_api_key(),
        "query": query,
        "number": number,
        "maxReadyTime": max_ready_time,
        "addRecipeInformation": True,
    }
    if diet:
        params["diet"] = diet
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
    """Get ingredients for a recipe by ID."""
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
    """Get substitute ingredients for an unavailable item."""
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
