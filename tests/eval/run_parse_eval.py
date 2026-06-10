"""
Eval: parse_request node — schema correctness.

Usage:
    python tests/eval/run_parse_eval.py [--threshold 0.85]

CI usage:
    python tests/eval/run_parse_eval.py --threshold 0.70 --ci
"""
import argparse
import os
import sys

sys.path.insert(0, ".")
os.environ.setdefault("USE_MOCK_TOOLS", "true")

from langchain_core.messages import HumanMessage
from langsmith import Client, evaluate

from tests.eval.evaluators import check_parse_schema, mean_evaluator_score


def run_agent(inputs: dict) -> dict:
    """Run parse_request node only (no sub-agents required)."""
    os.environ.setdefault("OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY", ""))

    from shared.state import AgentState
    from supervisor.graph import parse_request

    utterance = inputs.get("utterance", "")

    state: AgentState = {  # type: ignore[typeddict-item]
        "messages": [HumanMessage(content=utterance)],
        "request": None,
        "location_id": None,
        "store_name": None,
        "selected_recipes": [],
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
    result = parse_request(state)
    return {"request": result.get("request")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=0.85)
    parser.add_argument("--ci", action="store_true", help="Exit 1 if score below threshold")
    parser.add_argument("--experiment-prefix", default="parse-eval")
    args = parser.parse_args()

    client = Client()
    datasets = list(client.list_datasets(dataset_name="request-parsing-v1"))
    if not datasets:
        print("Dataset 'request-parsing-v1' not found.")
        print("Run: python tests/eval/seed_datasets.py")
        sys.exit(0)

    print("Running parse_request eval against 'request-parsing-v1'...")
    results = evaluate(
        run_agent,
        data="request-parsing-v1",
        evaluators=[check_parse_schema],
        experiment_prefix=args.experiment_prefix,
        max_concurrency=2,
        metadata={"eval_type": "parse_schema", "mode": "mock"},
    )

    mean_score, n = mean_evaluator_score(results, "parse_schema")

    print("\nParse eval complete.")
    print(f"  Examples: {n}")
    print(f"  Mean score: {mean_score:.2f} (threshold: {args.threshold})")

    if mean_score < args.threshold:
        print(f"  FAIL: score {mean_score:.2f} below threshold {args.threshold}")
        if args.ci:
            sys.exit(1)
    else:
        print(f"  PASS: score {mean_score:.2f} >= threshold {args.threshold}")

    print("\nView results: https://smith.langchain.com")


if __name__ == "__main__":
    main()
