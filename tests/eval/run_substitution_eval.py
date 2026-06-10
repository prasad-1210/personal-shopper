"""
Eval: shopping_agent substitutions — substitution quality.

Usage:
    python tests/eval/run_substitution_eval.py [--threshold 0.60]

Uses LLM-as-judge. Shopping agent uses mock tools.
"""
import argparse
import os
import sys

sys.path.insert(0, ".")
os.environ.setdefault("USE_MOCK_TOOLS", "true")

from langsmith import Client, evaluate

from tests.eval.evaluators import judge_substitution, mean_evaluator_score


def run_substitution(inputs: dict) -> dict:
    """Run shopping_agent check_availability and return substitutions."""
    from agents.shopping_agent.graph import check_availability
    from shared.state import AgentState

    unavailable = inputs.get("unavailable_ingredient", "lemongrass")
    recipe_context = inputs.get("recipe_context", "Thai curry")
    diet = inputs.get("dietary_profile", "")

    state: AgentState = {  # type: ignore[typeddict-item]
        "request": {
            "meal_keywords": [recipe_context],
            "dietary_restrictions": [diet] if diet else [],
            "dietary_profile": diet,
            "budget_usd": None,
            "max_calories_per_serving": None,
            "preferred_retailer": "kroger",
            "zip_code": "94103",
            "servings": 4,
            "pantry_items": [],
            "raw_message": recipe_context,
        },
        "selected_recipes": [{"id": 1001, "title": recipe_context}],
        "location_id": "70300132",
        "store_name": "Kroger Demo",
        "messages": [],
        "ingredients": [],
        "shopping_list": [],
        "confirmed": False,
        "error": None,
        "nutrition_constraints": None,
        "budget_status": "unchecked",
        "nutrition_status": "unchecked",
        "constraint_violations": [],
        "iteration": 0,
        "next_agent": "",
        "agent_steps": [],
    }

    result = check_availability(state)
    return {"ingredients": result.get("ingredients", [])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=0.60)
    parser.add_argument("--ci", action="store_true")
    parser.add_argument("--experiment-prefix", default="sub-eval")
    args = parser.parse_args()

    client = Client()
    datasets = list(client.list_datasets(dataset_name="substitution-quality-v1"))
    if not datasets:
        print("Dataset 'substitution-quality-v1' not found.")
        print("Run: python tests/eval/seed_datasets.py")
        sys.exit(0)

    print("Running substitution eval against 'substitution-quality-v1'...")
    results = evaluate(
        run_substitution,
        data="substitution-quality-v1",
        evaluators=[judge_substitution],
        experiment_prefix=args.experiment_prefix,
        max_concurrency=2,
        metadata={"eval_type": "substitution_quality", "mode": "mock"},
    )

    mean_score, n = mean_evaluator_score(results, "substitution_quality")

    print("\nSubstitution eval complete.")
    print(f"  Examples scored: {n}")
    print(f"  Mean quality: {mean_score:.2f} (threshold: {args.threshold})")

    if mean_score < args.threshold:
        print(f"  FAIL: score {mean_score:.2f} below threshold {args.threshold}")
        if args.ci:
            sys.exit(1)
    else:
        print("  PASS")

    print("\nView results: https://smith.langchain.com")


if __name__ == "__main__":
    main()
