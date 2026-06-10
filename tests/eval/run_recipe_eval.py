"""
Eval: recipe_agent — recipe relevance.

Usage:
    python tests/eval/run_recipe_eval.py [--threshold 0.60]

Uses LLM-as-judge (gpt-4o-mini). Recipe search uses mock tools.
"""
import argparse
import os
import sys

sys.path.insert(0, ".")
os.environ.setdefault("USE_MOCK_TOOLS", "true")

from langsmith import Client, evaluate

from tests.eval.evaluators import (
    check_recipe_returned,
    judge_recipe_relevance,
    mean_evaluator_score,
)
from tests.eval.preflight import skip_if_no_openai


def run_recipe_search(inputs: dict) -> dict:
    """Run recipe_agent find_recipes node directly."""
    from agents.recipe_agent.graph import find_recipes
    from shared.state import AgentState

    request_str = inputs.get("request", "curry")
    diet = inputs.get("diet", "")
    avoid = inputs.get("avoid_ingredients", [])

    state: AgentState = {  # type: ignore[typeddict-item]
        "request": {
            "meal_keywords": [request_str],
            "dietary_restrictions": [diet] if diet else [],
            "dietary_profile": diet,
            "budget_usd": None,
            "max_calories_per_serving": None,
            "preferred_retailer": "kroger",
            "zip_code": "94103",
            "servings": 4,
            "pantry_items": [],
            "raw_message": request_str,
        },
        "nutrition_constraints": {
            "max_carbs_g": None,
            "max_calories": None,
            "max_sugar_g": None,
            "avoid_ingredients": avoid,
            "notes": "",
        }
        if avoid
        else None,
        "messages": [],
        "budget_status": "unchecked",
        "iteration": 0,
        "agent_steps": [],
        "selected_recipes": [],
        "ingredients": [],
    }

    result = find_recipes(state)
    return {"selected_recipes": result.get("selected_recipes", [])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=0.60)
    parser.add_argument("--ci", action="store_true")
    parser.add_argument("--experiment-prefix", default="recipe-eval")
    args = parser.parse_args()
    skip_if_no_openai(ci=args.ci)

    client = Client()
    datasets = list(client.list_datasets(dataset_name="recipe-relevance-v1"))
    if not datasets:
        print("Dataset 'recipe-relevance-v1' not found.")
        print("Run: python tests/eval/seed_datasets.py")
        sys.exit(0)

    print("Running recipe_agent eval against 'recipe-relevance-v1'...")
    results = evaluate(
        run_recipe_search,
        data="recipe-relevance-v1",
        evaluators=[check_recipe_returned, judge_recipe_relevance],
        experiment_prefix=args.experiment_prefix,
        max_concurrency=2,
        metadata={"eval_type": "recipe_relevance", "mode": "mock"},
    )

    mean_score, n = mean_evaluator_score(results, "recipe_relevance")

    print("\nRecipe eval complete.")
    print(f"  Examples scored: {n}")
    print(f"  Mean relevance: {mean_score:.2f} (threshold: {args.threshold})")

    if mean_score < args.threshold:
        print(f"  FAIL: score {mean_score:.2f} below threshold {args.threshold}")
        if args.ci:
            sys.exit(1)
    else:
        print("  PASS")

    print("\nView results: https://smith.langchain.com")


if __name__ == "__main__":
    main()
