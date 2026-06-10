# Nutrition Agent — Integration Spec

| Property | Value |
|----------|-------|
| **Graph ID** | `nutrition_agent` |
| **Package** | `agents/nutrition_agent/graph.py` |
| **Local URL** | `http://127.0.0.1:22001` |
| **K8s service** | `http://nutrition-agent:8000` |
| **LLM** | Yes (`gpt-4o-mini`) |
| **Graph shape** | `START → interpret_constraints → END` |

## Purpose

Converts a user's **dietary profile** and optional **calorie limit** into structured JSON constraints for downstream recipe/shopping logic.

## When invoked

Supervisor calls this agent when `request.dietary_profile` or `request.max_calories_per_serving` is set and `nutrition_status == "unchecked"`.

Direct integrators call when they need constraint JSON without the full supervisor flow.

## Required input

| Field | Required | Description |
|-------|----------|-------------|
| `request.dietary_profile` | One of profile or calories | e.g. `vegan`, `diabetic`, `keto` |
| `request.max_calories_per_serving` | One of profile or calories | Numeric cap |
| `agent_steps` | Optional | Appended on output |

If **both** profile and calories are empty, agent skips LLM and returns `nutrition_agent:skipped`.

## Output

| Field | Type | Description |
|-------|------|-------------|
| `nutrition_constraints` | `object` | Parsed JSON constraints |
| `nutrition_status` | `string` | Always `ok` on success |
| `agent_steps` | `string[]` | Includes `nutrition_agent` or `nutrition_agent:skipped` |

### `nutrition_constraints` schema

```json
{
  "max_carbs_g": 45,
  "max_calories": 500,
  "max_sugar_g": 25,
  "avoid_ingredients": ["sugar", "honey"],
  "notes": "optional string"
}
```

Supported profiles (prompt-defined): `diabetic`, `low-carb`, `keto`, `vegan`, `vegetarian`, `gluten-free`, `dairy-free`.

## HTTP invoke

```json
{
  "assistant_id": "nutrition_agent",
  "input": {
    "request": {
      "raw_message": "keto dinner",
      "meal_keywords": ["dinner"],
      "dietary_profile": "keto",
      "max_calories_per_serving": 600,
      "zip_code": "94103",
      "preferred_retailer": "kroger",
      "servings": 4
    },
    "agent_steps": []
  },
  "config": { "configurable": { "thread_id": "<uuid>" } }
}
```

## Environment variables

| Variable | Required |
|----------|----------|
| `OPENAI_API_KEY` | Yes |
| `LANGSMITH_*` | Recommended |

## Tools & external APIs

This agent does **not** call LangChain `@tool` functions or third-party HTTP APIs.

| Capability | Mechanism | External dependency |
|------------|-----------|---------------------|
| Constraint extraction | OpenAI chat completion | OpenAI API |
| Prompt templates | `shared/prompt_loader.chat_prompt` | Local files only |

### No `@tool` invocations

Unlike recipe and shopping agents, nutrition does not use `personal_shopper.tools.*` or `invoke_tool()`. Integrators embedding only this agent need **OpenAI credentials**, not Kroger/Edamam/RapidAPI keys.

### LLM call detail

| | |
|--|--|
| **Node** | `interpret_constraints` |
| **Model** | `gpt-4o-mini` (temperature 0) |
| **Prompt** | `shared/prompts/nutrition_constraints.{system,human}.md` |
| **Template variables** | `{profile}`, `{calories}` |
| **Expected output** | JSON object (parsed in code) |

**Skip path (no LLM call):** when `dietary_profile` and `max_calories_per_serving` are both empty → `nutrition_agent:skipped`, `nutrition_constraints: {}`.

### Downstream use of output

`nutrition_constraints` is written to state and consumed by the recipe agent: `avoid_ingredients` maps to `exclude_ingredients` on `search_recipes`, and `max_calories` constrains calories per serving at search time (Edamam `calories=`, Spoonacular `maxCalories=`).

## Prompts

Externalized in `shared/prompts/nutrition_constraints.{system,human}.md`.

## Errors

- LLM returns non-JSON → wrapped in `{"notes": "<raw text>"}`
- `max_calories` from request always applied after parse

## Idempotency

Safe to call multiple times; supervisor only calls while `nutrition_status == unchecked`.
