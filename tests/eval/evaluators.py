"""
Shared LangSmith evaluators for personal-shopper agent.

Heuristic evaluators (no LLM calls):
    check_parse_schema      — validates ShoppingRequest field extraction
    check_recipe_returned   — validates at least one recipe was found

LLM-as-judge evaluators:
    judge_recipe_relevance  — rates recipe quality against criterion
    judge_substitution      — rates substitution quality against criterion
"""
from __future__ import annotations

import re
from typing import Any


def mean_evaluator_score(experiment_results: Any, key: str) -> tuple[float, int]:
    """Aggregate mean score for an evaluator key from LangSmith evaluate output."""
    scores: list[float] = []
    rows = getattr(experiment_results, "results", None)
    if rows is None:
        try:
            rows = list(experiment_results)
        except TypeError:
            rows = []

    for row in rows or []:
        eval_block = getattr(row, "evaluation_results", None)
        if eval_block is None and isinstance(row, dict):
            eval_block = row.get("evaluation_results")
        if eval_block is None:
            continue

        results_list = getattr(eval_block, "results", None)
        if results_list is None and isinstance(eval_block, dict):
            results_list = eval_block.get("results", [])

        for res in results_list or []:
            if isinstance(res, dict):
                res_key = res.get("key")
                res_score = res.get("score")
            else:
                res_key = getattr(res, "key", None)
                res_score = getattr(res, "score", None)
            if res_key == key and res_score is not None:
                scores.append(float(res_score))

    if not scores:
        return 0.0, 0
    return sum(scores) / len(scores), len(scores)


def check_parse_schema(run, example) -> dict:
    """Heuristic: did parse_request extract required fields correctly?"""
    outputs = run.outputs or {}
    request = outputs.get("request") or {}

    def get_field(obj, field, default=None):
        if isinstance(obj, dict):
            return obj.get(field, default)
        return getattr(obj, field, default)

    expected = example.outputs or {}
    errors = []

    if "zip_code" in expected:
        actual = get_field(request, "zip_code", "")
        if str(actual) != str(expected["zip_code"]):
            errors.append(f"zip_code: expected {expected['zip_code']!r}, got {actual!r}")

    if "servings" in expected:
        actual = get_field(request, "servings", 4)
        if int(actual or 4) != int(expected["servings"]):
            errors.append(f"servings: expected {expected['servings']}, got {actual}")

    if "dietary_profile" in expected:
        actual = get_field(request, "dietary_profile", "")
        if str(actual or "") != str(expected["dietary_profile"]):
            errors.append(
                f"dietary_profile: expected {expected['dietary_profile']!r}, got {actual!r}"
            )

    if "budget_usd" in expected:
        actual = get_field(request, "budget_usd")
        exp = expected["budget_usd"]
        if exp is None and actual is not None:
            errors.append(f"budget_usd: expected None, got {actual}")
        elif exp is not None and actual is None:
            errors.append(f"budget_usd: expected {exp}, got None")
        elif exp is not None and actual is not None:
            if abs(float(actual) - float(exp)) > 0.01:
                errors.append(f"budget_usd: expected {exp}, got {actual}")

    if "preferred_retailer" in expected:
        actual = get_field(request, "preferred_retailer", "kroger")
        if str(actual or "kroger") != str(expected["preferred_retailer"]):
            errors.append(
                f"preferred_retailer: expected {expected['preferred_retailer']!r}, "
                f"got {actual!r}"
            )

    if "meal_keywords_contains" in expected:
        keywords = get_field(request, "meal_keywords", []) or []
        keywords_str = " ".join(str(k).lower() for k in keywords)
        expected_kw = expected["meal_keywords_contains"].lower()
        if expected_kw not in keywords_str:
            errors.append(
                f"meal_keywords: expected to contain {expected_kw!r}, got {keywords}"
            )

    if "max_calories_per_serving" in expected:
        actual = get_field(request, "max_calories_per_serving")
        exp = expected["max_calories_per_serving"]
        if exp is not None and actual is None:
            errors.append(f"max_calories_per_serving: expected {exp}, got None")
        elif exp is not None and actual is not None:
            if abs(float(actual) - float(exp)) > 0.01:
                errors.append(f"max_calories_per_serving: expected {exp}, got {actual}")

    score = 1.0 if not errors else 0.0
    comment = "All fields correct" if not errors else "; ".join(errors)
    return {"score": score, "comment": comment, "key": "parse_schema"}


def check_recipe_returned(run, example) -> dict:
    """Heuristic: did the agent return at least one recipe?"""
    _ = example
    outputs = run.outputs or {}
    recipes = outputs.get("selected_recipes", [])
    score = 1.0 if recipes else 0.0
    comment = (
        f"{len(recipes)} recipe(s) found"
        if recipes
        else "No recipes returned"
    )
    return {"score": score, "comment": comment, "key": "recipe_returned"}


def _llm_judge(prompt: str) -> float:
    """Call gpt-4o-mini with a scoring prompt. Returns float 0-1."""
    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, max_tokens=5)
        response = llm.invoke(prompt)
        text = response.content.strip()
        match = re.search(r"[1-5]", text)
        if match:
            raw_score = int(match.group())
            return (raw_score - 1) / 4
    except Exception:
        pass
    return 0.5


def judge_recipe_relevance(run, example) -> dict:
    """LLM-as-judge: are the returned recipes relevant to the request + criterion?"""
    outputs = run.outputs or {}
    recipes = outputs.get("selected_recipes", [])
    criterion = (example.outputs or {}).get("criterion", "")

    if not recipes:
        return {
            "score": 0.0,
            "comment": "No recipes to evaluate",
            "key": "recipe_relevance",
        }

    recipe_titles = ", ".join(r.get("title", "") for r in recipes[:3])
    request_info = example.inputs or {}

    prompt = f"""Rate these recipe results 1-5 for relevance.

User request: {request_info.get('request', '')}
Diet: {request_info.get('diet', 'none')}
Avoid: {request_info.get('avoid_ingredients', [])}

Recipes returned: {recipe_titles}

Criterion: {criterion}

Score:
5 = recipes perfectly match request and satisfy all constraints
3 = recipes loosely relevant, minor constraint violations
1 = recipes irrelevant or clearly violate constraints

Respond with a single digit 1-5."""

    score = _llm_judge(prompt)
    comment = f"Recipes: {recipe_titles}"
    return {"score": score, "comment": comment, "key": "recipe_relevance"}


def judge_substitution(run, example) -> dict:
    """LLM-as-judge: is the substitution appropriate given context and diet?"""
    outputs = run.outputs or {}
    ingredients = outputs.get("ingredients", [])
    criterion = (example.outputs or {}).get("criterion", "")
    unavailable = (example.inputs or {}).get("unavailable_ingredient", "")

    substitute = None
    for ing in ingredients:
        name = ing.get("name", "") if isinstance(ing, dict) else getattr(ing, "name", "")
        sub = ing.get("substitute", "") if isinstance(ing, dict) else getattr(ing, "substitute", "")
        if unavailable.lower() in name.lower() and sub:
            substitute = sub
            break

    if not substitute:
        return {
            "score": 0.5,
            "comment": f"No substitute found for {unavailable} in output",
            "key": "substitution_quality",
        }

    prompt = f"""Rate this ingredient substitution 1-5.

Unavailable ingredient: {unavailable}
Recipe context: {(example.inputs or {}).get('recipe_context', '')}
Dietary profile: {(example.inputs or {}).get('dietary_profile', 'none')}
Proposed substitute: {substitute}

Criterion: {criterion}

Score:
5 = excellent substitute, culinarily appropriate, respects dietary constraints
3 = acceptable but not ideal
1 = inappropriate, wrong flavour profile, or violates dietary constraint

Respond with a single digit 1-5."""

    score = _llm_judge(prompt)
    comment = f"Substitute for {unavailable}: {substitute}"
    return {"score": score, "comment": comment, "key": "substitution_quality"}
