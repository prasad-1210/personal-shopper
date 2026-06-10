# External tools reference

LangChain `@tool` functions in `src/personal_shopper/tools/`. Invoked imperatively from graph nodes via `shared.tool_tracing.invoke_tool`.

**Mock mode:** Set `USE_MOCK_TOOLS=true` — all tools use `mock_tools.py` with identical signatures.

---

## Kroger (`kroger.py`)

**Env:** `KROGER_CLIENT_ID`, `KROGER_CLIENT_SECRET`  
**Auth:** OAuth2 client credentials (`product.compact` scope)

### `find_nearest_store`

| | |
|--|--|
| **Purpose** | Locate nearest Kroger-family store for a US zip |
| **Used by** | Supervisor `find_store` (Kroger retailers) |

**Input:**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `zip_code` | `string` | Yes | 5-digit US zip |

**Output:**

```json
{
  "location_id": "70300132",
  "name": "Kroger Marketplace",
  "address": "123 Main St, City, ST, 75035",
  "chain": "KROGER",
  "error": "optional — on failure"
}
```

### `check_product_availability`

| | |
|--|--|
| **Purpose** | Search Kroger inventory at a specific store |
| **Used by** | Shopping agent (Kroger retailers) |

**Input:**

| Param | Type | Required |
|-------|------|----------|
| `ingredient` | `string` | Yes — search term |
| `location_id` | `string` | Yes — from `find_nearest_store` |

**Output:**

```json
{
  "ingredient": "basil",
  "available": true,
  "product_description": "Organic Basil",
  "price": 2.99,
  "size": "0.75 oz",
  "error": "optional"
}
```

---

## RapidAPI (`rapidapi_search.py`)

**Env:** `RAPIDAPI_KEY`  
**API:** [real-time-product-search](https://rapidapi.com/letscrape-6bRBa3QguO5/api/real-time-product-search) (Google Shopping catalog)

### `find_nearest_store`

Placeholder — no real store locator. Returns synthetic `location_id` for pipeline continuity.

**Output:** `{ "location_id": "rapidapi-{zip}", "name": "...", "note": "catalog only" }`

### `check_product_availability`

| | |
|--|--|
| **Purpose** | Catalog search for Walmart, Target, Costco, Amazon, Best Buy |
| **Used by** | Shopping agent (non-Kroger retailers) |

**Input:**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `ingredient` | `string` | Yes | Search query |
| `location_id` | `string` | No | Ignored by API (interface compat) |
| `store` | `string` | No | `walmart`, `target`, `costco`, `amazon`, `bestbuy` |

**Output:**

```json
{
  "ingredient": "pasta",
  "available": true,
  "product_description": "Barilla Spaghetti",
  "price": 1.98,
  "store": "Walmart",
  "link": "https://...",
  "source": "rapidapi_google_shopping",
  "note": "Catalog price — in-store availability not confirmed"
}
```

---

## Edamam (`edamam.py`)

**Env:** `EDAMAM_APP_ID`, `EDAMAM_APP_KEY`  
**Select:** `RECIPE_PROVIDER=edamam`

### `search_recipes`

**Input:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `query` | `string` | — | Natural language search |
| `diet` | `string` | `""` | vegetarian, vegan, gluten-free, keto, diabetic (→ low-sugar), … |
| `max_ready_time` | `int` | `60` | Max cook time minutes |
| `number` | `int` | `3` | Max results |
| `exclude_ingredients` | `list[string]` | `None` | Edamam: repeated `excluded` params; Spoonacular: `excludeIngredients` |
| `max_calories` | `int` | `None` | Max calories per serving (Edamam `calories=`, Spoonacular `maxCalories`) |

**Output:** `Recipe[]` — see [API-CONTRACT](agents/API-CONTRACT.md).

### `get_recipe_ingredients`

**Input:** `recipe_id` (string from Edamam URI suffix)

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

### `get_ingredient_substitutes`

Always returns `{ "ingredient": "...", "substitutes": [] }` — Edamam has no substitutes API. Shopping agent falls back to `"Ask store staff"`.

---

## Spoonacular (`spoonacular.py`)

**Env:** `SPOONACULAR_API_KEY`  
**Select:** `RECIPE_PROVIDER=spoonacular`

Same three tools as Edamam with compatible signatures. `get_ingredient_substitutes` calls Spoonacular substitutes API.

---

## Mock (`mock_tools.py`)

**Env:** `USE_MOCK_TOOLS=true`

Deterministic demo data. `lemongrass` and `galangal` always unavailable (tests substitution path).

| Tool | Behavior |
|------|----------|
| `find_nearest_store` | Returns fixed Kroger SF demo store |
| `check_product_availability` | Most items available at $3.49 |
| `search_recipes` | Returns 2 mock recipes; filters by `exclude_ingredients` when set |
| `get_recipe_ingredients` | Mock ingredient lists for IDs 1001, 1002 |
| `get_ingredient_substitutes` | Hardcoded subs for lemongrass, galangal |
