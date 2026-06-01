# Mock tools implement the same interface as:
#   kroger.py              — find_nearest_store, check_product_availability
#   rapidapi_search.py     — find_nearest_store, check_product_availability
# Both tools have identical signatures so mocks work for all retailers.
# Mock tools implement the same interface as both spoonacular.py and edamam.py
from typing import Any

from langchain_core.tools import tool

UNAVAILABLE = {"lemongrass", "galangal", "kaffir lime leaves"}

MOCK_STORE = {
    "location_id": "70300132",
    "name": "Kroger SF (Demo)",
    "address": "1 Market St",
    "chain": "Kroger",
}

MOCK_RECIPES = [
    {
        "id": 1001,
        "title": "Thai Green Curry (Mock)",
        "ready_in_minutes": 40,
        "servings": 4,
        "source_url": "",
    },
    {
        "id": 1002,
        "title": "Pasta Carbonara (Mock)",
        "ready_in_minutes": 30,
        "servings": 4,
        "source_url": "",
    },
]

MOCK_INGREDIENTS = {
    1001: {
        "recipe_id": 1001,
        "title": "Thai Green Curry (Mock)",
        "servings": 4,
        "ingredients": [
            {
                "name": "chicken breast",
                "original": "500g chicken breast",
                "amount": 500,
                "unit": "g",
                "aisle": "Meat",
            },
            {
                "name": "coconut milk",
                "original": "1 can coconut milk",
                "amount": 1,
                "unit": "can",
                "aisle": "Canned Goods",
            },
            {
                "name": "green curry paste",
                "original": "2 tbsp green curry paste",
                "amount": 2,
                "unit": "tbsp",
                "aisle": "International",
            },
            {
                "name": "lemongrass",
                "original": "2 stalks lemongrass",
                "amount": 2,
                "unit": "stalks",
                "aisle": "Produce",
            },
            {
                "name": "galangal",
                "original": "1 inch galangal",
                "amount": 1,
                "unit": "inch",
                "aisle": "Produce",
            },
        ],
    },
    1002: {
        "recipe_id": 1002,
        "title": "Pasta Carbonara (Mock)",
        "servings": 4,
        "ingredients": [
            {
                "name": "spaghetti",
                "original": "400g spaghetti",
                "amount": 400,
                "unit": "g",
                "aisle": "Pasta & Rice",
            },
            {
                "name": "pancetta",
                "original": "150g pancetta",
                "amount": 150,
                "unit": "g",
                "aisle": "Meat",
            },
            {
                "name": "eggs",
                "original": "4 large eggs",
                "amount": 4,
                "unit": "",
                "aisle": "Dairy & Eggs",
            },
            {
                "name": "parmesan",
                "original": "100g parmesan",
                "amount": 100,
                "unit": "g",
                "aisle": "Dairy & Eggs",
            },
        ],
    },
}


@tool
def find_nearest_store(zip_code: str) -> dict[str, Any]:
    """Find the nearest Kroger store for a zip code."""
    return MOCK_STORE


@tool
def check_product_availability(ingredient: str, location_id: str) -> dict[str, Any]:
    """Check if an ingredient is available at a Kroger store."""
    name_lower = ingredient.lower()
    if name_lower in UNAVAILABLE:
        return {
            "ingredient": ingredient,
            "available": False,
            "product_description": None,
            "price": None,
            "size": None,
        }
    return {
        "ingredient": ingredient,
        "available": True,
        "product_description": f"{ingredient.title()} (Mock)",
        "price": 3.49,
        "size": "1 unit",
    }


@tool
def search_recipes(
    query: str, diet: str = "", max_ready_time: int = 60, number: int = 3
) -> list[dict[str, Any]]:
    """Search for recipes matching a query."""
    return MOCK_RECIPES[:number]


@tool
def get_recipe_ingredients(recipe_id: int) -> dict[str, Any]:
    """Get ingredients for a recipe by ID."""
    return MOCK_INGREDIENTS.get(
        recipe_id,
        {"recipe_id": recipe_id, "title": "", "servings": 4, "ingredients": []},
    )


@tool
def get_ingredient_substitutes(ingredient_name: str) -> dict[str, Any]:
    """Get substitute ingredients for an unavailable item."""
    subs = {
        "lemongrass": ["lemon zest + ginger", "lemon juice"],
        "galangal": ["ginger", "galangal paste"],
    }
    name_lower = ingredient_name.lower()
    if name_lower in subs:
        return {"ingredient": ingredient_name, "substitutes": subs[name_lower]}
    return {
        "ingredient": ingredient_name,
        "substitutes": ["similar item in same aisle", "ask store staff"],
    }
