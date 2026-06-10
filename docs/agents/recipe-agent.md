# Recipe Agent — Integration Spec

| Property | Value |
|----------|-------|
| **Graph ID** | `recipe_agent` |
| **Package** | `agents/recipe_agent/graph.py` |
| **Local URL** | `http://127.0.0.1:22002` |
| **K8s service** | `http://recipe-agent:8000` |
| **LLM** | No |
| **Graph shape** | `START → find_recipes → END` |

## Purpose

Searches for recipes matching **meal keywords** and dietary filters. Uses Edamam or Spoonacular (or mocks).

## When invoked

Supervisor calls when `selected_recipes` is empty, or on budget retry when `budget_status == "over"`.

## Required input

| Field | Required | Description |
|-------|----------|-------------|
| `request.meal_keywords` | Recommended | Dish names from parse step |
| `request.dietary_restrictions` | Optional | Explicit restrictions |
| `request.dietary_profile` | Optional | Merged into diet filter |
| `budget_status` | Optional | `"over"` triggers simpler query |
| `iteration` | Optional | Supervisor turn; logged in `agent_steps` |

## Output

| Field | Type | Description |
|-------|------|-------------|
| `selected_recipes` | `Recipe[]` | Up to 3 recipes |
| `ingredients` | `[]` | Cleared (shopping agent fills) |
| `shopping_list` | `[]` | Cleared |
| `budget_status` | `string` | Reset to `unchecked` |
| `agent_steps` | `string[]` | e.g. `recipe_agent:iter2` |

### `Recipe` object

```json
{
  "id": "abc123def",
  "title": "Chicken Tikka Masala",
  "ready_in_minutes": 45,
  "servings": 4,
  "source_url": "https://..."
}
```

## Query strategy

1. Last two words of first keyword, then last word alone
2. Fallback queries: `curry`, `chicken`, `pasta`
3. If `budget_status == "over"` and `iteration > 1`, prefix query with `simple `
4. Stops at first query returning results

## HTTP invoke

```json
{
  "assistant_id": "recipe_agent",
  "input": {
    "request": {
      "raw_message": "palak paneer",
      "meal_keywords": ["palak paneer"],
      "dietary_profile": "vegetarian",
      "zip_code": "75035",
      "preferred_retailer": "kroger",
      "servings": 4
    },
    "budget_status": "unchecked",
    "iteration": 1,
    "agent_steps": ["parse_request"]
  },
  "config": { "configurable": { "thread_id": "<uuid>" } }
}
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RECIPE_PROVIDER` | `edamam` (code) | `edamam` or `spoonacular` |
| `EDAMAM_APP_ID` / `EDAMAM_APP_KEY` | — | When provider is edamam |
| `SPOONACULAR_API_KEY` | — | When provider is spoonacular |
| `USE_MOCK_TOOLS` | `false` | Use `mock_tools.search_recipes` |

## Tools & external APIs

### Tool: `search_recipes`

| | |
|--|--|
| **Node** | `find_recipes` |
| **Invoked via** | `shared.tool_tracing.invoke_tool` |
| **Calls per run** | 1–N (stops when a query returns results) |

**Provider selection:**

| Condition | Module | Credentials |
|-----------|--------|-------------|
| `USE_MOCK_TOOLS=true` | `mock_tools.py` | None |
| `RECIPE_PROVIDER=edamam` (default in code) | `edamam.py` | `EDAMAM_APP_ID`, `EDAMAM_APP_KEY` |
| `RECIPE_PROVIDER=spoonacular` | `spoonacular.py` | `SPOONACULAR_API_KEY` |

**Input (per invocation):**

| Parameter | Type | Value in agent |
|-----------|------|----------------|
| `query` | `string` | Keyword variant or fallback (`curry`, `chicken`, `pasta`); prefixed `simple ` on budget retry |
| `diet` | `string` | First of `dietary_restrictions` + `dietary_profile` |
| `max_ready_time` | `int` | `90` |
| `number` | `int` | `3` |
| `exclude_ingredients` | `list[string]` | From `nutrition_constraints.avoid_ingredients` (max 8) |
| `max_calories` | `int` | From `nutrition_constraints.max_calories` (per serving) |

**Output:**

```json
[
  {
    "id": "abc123def",
    "title": "Chicken Tikka Masala",
    "ready_in_minutes": 45,
    "servings": 4,
    "source_url": "https://...",
    "calories_per_serving": 520
  }
]
```

Edamam may include `calories_per_serving` when the API returns calorie data.

| Field | Edamam | Spoonacular |
|-------|--------|-------------|
| `id` | String (URI suffix) | Integer |
| `title` | `label` | `title` |
| `ready_in_minutes` | `totalTime` | `readyInMinutes` |

**LangSmith trace name:** `{provider}.search_recipes:{query}`  
Examples: `edamam.search_recipes:palak paneer`, `mock.search_recipes:simple chicken`

**Error behavior:**

| Provider | On failure |
|----------|------------|
| Edamam / Spoonacular | HTTP exception propagates (run fails) |
| Mock | Always returns 2 demo recipes |

**Mock output:** Fixed recipes IDs `1001` (Thai Green Curry), `1002` (Pasta Carbonara).

### Tools NOT used by this agent

| Tool | Used by |
|------|---------|
| `get_recipe_ingredients` | Shopping agent |
| `get_ingredient_substitutes` | Shopping agent |
| `find_nearest_store` | Supervisor |
| `check_product_availability` | Shopping agent |

See also: [TOOLS.md](../TOOLS.md) · [shopping-agent.md](shopping-agent.md)

## Empty results

Returns `selected_recipes: []`. Supervisor proceeds to shopping with no recipes → `finish_node` error message.
