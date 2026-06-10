# Shopping Agent — Integration Spec

| Property | Value |
|----------|-------|
| **Graph ID** | `shopping_agent` |
| **Package** | `agents/shopping_agent/graph.py` |
| **Local URL** | `http://127.0.0.1:22003` |
| **K8s service** | `http://shopping-agent:8000` |
| **LLM** | No |
| **Graph shape** | `START → check_availability → END` |

## Purpose

1. Expand `selected_recipes` into ingredient lists  
2. Check store availability and price per ingredient  
3. Suggest substitutes for unavailable items  

## When invoked

Supervisor calls when `shopping_list` is empty and recipes exist.

## Required input

| Field | Required | Description |
|-------|----------|-------------|
| `selected_recipes` | Yes | From recipe agent |
| `request.preferred_retailer` | Yes | Routes Kroger vs RapidAPI |
| `location_id` | Recommended | From `find_store` (Kroger ID or RapidAPI placeholder) |
| `request.pantry_items` | Optional | Excluded from shopping list |

## Output

| Field | Type | Description |
|-------|------|-------------|
| `ingredients` | `IngredientAvailability[]` | Full list with availability |
| `shopping_list` | `IngredientAvailability[]` | Same as `ingredients` |
| `agent_steps` | `string[]` | Appends `shopping_agent` |

## Retailer routing

| Retailer family | Availability API | Notes |
|-----------------|------------------|-------|
| Kroger, Ralphs, Fred Meyer, … | Kroger Product API | Real store inventory |
| Walmart, Target, Costco, Amazon, Best Buy | RapidAPI Google Shopping | Catalog only; prices approximate |

## HTTP invoke

```json
{
  "assistant_id": "shopping_agent",
  "input": {
    "request": {
      "raw_message": "palak paneer",
      "meal_keywords": ["palak paneer"],
      "preferred_retailer": "kroger",
      "zip_code": "75035",
      "servings": 4,
      "pantry_items": ["rice"]
    },
    "selected_recipes": [
      {
        "id": "abc123",
        "title": "Palak Paneer",
        "ready_in_minutes": 40,
        "servings": 4,
        "source_url": ""
      }
    ],
    "location_id": "70300132",
    "store_name": "Kroger Marketplace",
    "agent_steps": ["recipe_agent:iter1"]
  },
  "config": { "configurable": { "thread_id": "<uuid>" } }
}
```

## Tools & external APIs

Execution order per run: **expand recipes → check each ingredient → substitutes for misses**.

```
selected_recipes[]
  └─► get_recipe_ingredients (× recipes)
        └─► check_product_availability (× unique ingredients)
              └─► get_ingredient_substitutes (× unavailable only)
```

### Tool 1: `get_recipe_ingredients`

| | |
|--|--|
| **When** | Once per item in `selected_recipes` |
| **Module** | `edamam.py`, `spoonacular.py`, or `mock_tools.py` |

**Input:**

| Parameter | Type | Source |
|-----------|------|--------|
| `recipe_id` | `string` or `int` | `selected_recipes[].id` |

**Output:**

```json
{
  "recipe_id": "abc123",
  "title": "Palak Paneer",
  "servings": 4,
  "ingredients": [
    {
      "name": "spinach",
      "original": "500g spinach",
      "amount": 500,
      "unit": "g",
      "aisle": "Produce"
    }
  ]
}
```

**LangSmith trace:** `{provider}.get_recipe_ingredients:{recipe_id}`

**Provider:** `RECIPE_PROVIDER` env (`edamam` \| `spoonacular`) or mock.

---

### Tool 2: `check_product_availability`

| | |
|--|--|
| **When** | Once per unique ingredient (after pantry dedup) |
| **Module** | `kroger.py` or `rapidapi_search.py` or `mock_tools.py` |

**Retailer routing** (`request.preferred_retailer`):

| Retailer | Module | `store` param |
|----------|--------|---------------|
| Kroger family | `kroger.py` | — |
| `walmart`, `target`, `costco`, `amazon`, `bestbuy` | `rapidapi_search.py` | retailer name |
| Mock | `mock_tools.py` | — |

**Input (Kroger):**

| Parameter | Type | Source |
|-----------|------|--------|
| `ingredient` | `string` | `IngredientAvailability.name` |
| `location_id` | `string` | `state.location_id` from supervisor |

**Input (RapidAPI):**

| Parameter | Type | Source |
|-----------|------|--------|
| `ingredient` | `string` | ingredient name |
| `location_id` | `string` | ignored by API (interface compat) |
| `store` | `string` | normalised retailer (`walmart`, …) |

**Output (success):**

```json
{
  "ingredient": "basil",
  "available": true,
  "product_description": "Organic Basil",
  "price": 2.99,
  "size": "0.75 oz"
}
```

RapidAPI adds: `store`, `link`, `source`, `note` (catalog disclaimer).

**LangSmith trace:**

- `kroger.check_product_availability:basil`
- `rapidapi.check_product_availability:pasta@walmart`

**Mapped to state:** `available`, `product_description`, `price` on each `IngredientAvailability`.

---

### Tool 3: `get_ingredient_substitutes`

| | |
|--|--|
| **When** | Only when `check_product_availability` returned `available: false` |
| **Module** | Edamam (empty list), Spoonacular (API), or mock |

**Input:**

| Parameter | Type |
|-----------|------|
| `ingredient_name` | `string` |

**Output:**

```json
{
  "ingredient": "lemongrass",
  "substitutes": ["lemon zest + ginger", "lemon juice"]
}
```

**Fallback when `substitutes` is empty:** agent uses `"Ask store staff"`.

| Provider | Substitutes |
|----------|-------------|
| Edamam | Always `[]` |
| Spoonacular | API-driven list |
| Mock | Hardcoded for `lemongrass`, `galangal` |

**LangSmith trace:** `{provider}.get_ingredient_substitutes:{name}`

---

### Tool call volume estimate

| Recipes | Unique ingredients | Typical API calls |
|---------|-------------------|-------------------|
| 1 | 10 | 1 + 10 + (0–10 subs) |
| 3 | 25 | 3 + 25 + subs |

Large recipes: **10–30s** latency, watch RapidAPI rate limits (429).

### Environment variables (tools)

| Variable | Required when |
|----------|---------------|
| `RECIPE_PROVIDER` | `edamam` → `EDAMAM_*`; `spoonacular` → `SPOONACULAR_API_KEY` |
| `EDAMAM_APP_ID`, `EDAMAM_APP_KEY` | Recipe provider = edamam |
| `SPOONACULAR_API_KEY` | Recipe provider = spoonacular |
| `KROGER_CLIENT_ID`, `KROGER_CLIENT_SECRET` | Kroger-family retailer |
| `RAPIDAPI_KEY` | Walmart, Target, Costco, Amazon, Best Buy |
| `USE_MOCK_TOOLS` | `true` → no keys; all tools use `mock_tools` |

See [TOOLS.md](../TOOLS.md) for full request/response schemas and error codes.
