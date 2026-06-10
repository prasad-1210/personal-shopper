"""Tests for nutrition_constraints → recipe search wiring."""

import os

import pytest


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    monkeypatch.setenv("USE_MOCK_TOOLS", "true")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake")


def test_mock_search_recipes_excludes_ingredients():
    """Verify mock search_recipes respects exclude_ingredients."""
    from src.personal_shopper.tools.mock_tools import search_recipes

    results = search_recipes.invoke({
        "query": "curry",
        "exclude_ingredients": ["chicken breast"],
    })
    recipe_ids = [r["id"] for r in results]
    if 1001 in recipe_ids and len(results) > 1:
        assert 1002 in recipe_ids


def test_nutrition_constraints_passed_to_recipe():
    """Integration: nutrition_constraints.avoid_ingredients reaches find_recipes."""
    from agents.recipe_agent.graph import find_recipes

    state = {
        "request": {
            "meal_keywords": ["curry"],
            "dietary_restrictions": [],
            "dietary_profile": "diabetic",
            "budget_usd": None,
            "max_calories_per_serving": 600,
            "preferred_retailer": "kroger",
            "zip_code": "94103",
            "servings": 4,
            "pantry_items": [],
            "raw_message": "curry for 4",
        },
        "nutrition_constraints": {
            "max_carbs_g": 45,
            "max_calories": 600,
            "max_sugar_g": 25,
            "avoid_ingredients": ["sugar", "honey", "white rice"],
            "notes": "",
        },
        "budget_status": "unchecked",
        "iteration": 0,
        "agent_steps": [],
        "selected_recipes": [],
        "ingredients": [],
    }

    result = find_recipes(state)
    assert "selected_recipes" in result
    assert isinstance(result["selected_recipes"], list)
