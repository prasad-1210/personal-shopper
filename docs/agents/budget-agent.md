# Budget Agent — Integration Spec

| Property | Value |
|----------|-------|
| **Graph ID** | `budget_agent` |
| **Package** | `agents/budget_agent/graph.py` |
| **Local URL** | `http://127.0.0.1:22004` |
| **K8s service** | `http://budget-agent:8000` |
| **LLM** | No |
| **Graph shape** | `START → validate_budget → END` |

## Purpose

Sums ingredient prices and compares total to `request.budget_usd`. Pure Python — no external APIs.

## When invoked

Supervisor calls when `budget_usd` is set and `budget_status == "unchecked"`, after shopping list is built.

## Required input

| Field | Required | Description |
|-------|----------|-------------|
| `request.budget_usd` | For validation | If null/missing, agent skips |
| `ingredients` | Yes | From shopping agent (with `price` fields) |

## Output

| Field | Type | Description |
|-------|------|-------------|
| `budget_status` | `string` | `ok` \| `over` \| skipped → `ok` |
| `constraint_violations` | `string[]` | Human-readable message when over |
| `agent_steps` | `string[]` | `budget_agent` or `budget_agent:skipped` |

### Over-budget example

```json
{
  "budget_status": "over",
  "constraint_violations": [
    "Over budget by $12.50 (estimated $42.50, limit $30.00)"
  ],
  "agent_steps": ["budget_agent"]
}
```

## Supervisor feedback loop

When `budget_status == "over"`, supervisor re-invokes **recipe agent** (up to 3 times) with `budget_status` still `over`, causing simpler recipe queries.

## HTTP invoke

```json
{
  "assistant_id": "budget_agent",
  "input": {
    "request": {
      "raw_message": "dinner under $30",
      "meal_keywords": ["dinner"],
      "budget_usd": 30.0,
      "zip_code": "94103",
      "preferred_retailer": "kroger",
      "servings": 4
    },
    "ingredients": [
      {
        "name": "chicken",
        "original": "1 lb chicken",
        "aisle": "Meat",
        "available": true,
        "price": 8.99
      },
      {
        "name": "cream",
        "original": "1 cup cream",
        "aisle": "Dairy",
        "available": true,
        "price": 4.50
      }
    ],
    "agent_steps": ["shopping_agent"]
  },
  "config": { "configurable": { "thread_id": "<uuid>" } }
}
```

## Tools & external APIs

This agent has **no LangChain tools** and makes **no HTTP calls**. It is pure Python arithmetic on state.

### Implicit dependency on upstream tool prices

`budget_status` is only as accurate as prices returned by the shopping agent's `check_product_availability` tool:

| Upstream provider | Price source | Budget reliability |
|-------------------|--------------|-------------------|
| Kroger API | Store shelf price when found | Higher |
| RapidAPI / Google Shopping | Catalog estimate | Approximate |
| Mock tools | Fixed `$3.49` | Demo only |
| Missing price | Treated as `$0` | May falsely pass budget |

### Calculation (equivalent logic)

```
total = sum(ingredient.price or 0 for ingredient in ingredients)
if total > request.budget_usd:
    budget_status = "over"
else:
    budget_status = "ok"
```

No `invoke_tool()` — nothing appears under `run_type: tool` in LangSmith for this agent.

### Tools NOT used

| Tool | Agent that uses it |
|------|-------------------|
| `search_recipes` | Recipe agent |
| `get_recipe_ingredients` | Shopping agent |
| `check_product_availability` | Shopping agent |
| `find_nearest_store` | Supervisor |

## Environment variables

None required beyond standard LangGraph server config. No tool API keys.

## Pricing accuracy

- **Kroger:** store API prices when available  
- **RapidAPI:** catalog estimates — budget check is approximate  
- Missing `price` treated as `0`
