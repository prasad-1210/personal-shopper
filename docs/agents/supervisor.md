# Supervisor Agent — Integration Spec

| Property | Value |
|----------|-------|
| **Graph ID** | `personal_shopper` |
| **Package** | `supervisor/graph.py` |
| **Local URL** | `http://127.0.0.1:22000` |
| **K8s service** | `http://supervisor:8000` |
| **LLM** | Yes (`gpt-4o-mini` — parse only) |
| **Sub-agents** | Nutrition, Recipe, Shopping, Budget via `RemoteGraph` |

## Purpose

Orchestrates the end-to-end meal → shopping-list workflow. **Entry point for the UI and most integrators.**

## Graph topology

```
START → receive_message → parse_request → find_store → supervisor ⟲
         → nutrition_agent | recipe_agent | shopping_agent | budget_agent | finish_node → END
```

## Operations (graph nodes)

| Node | Type | Description |
|------|------|-------------|
| `receive_message` | Reset | Clears per-run state on each new user message |
| `parse_request` | LLM | Extracts `ShoppingRequest` from latest human message |
| `find_store` | Tool | Kroger or RapidAPI store lookup by zip + retailer |
| `supervisor` | Router | Deterministic next-agent decision |
| `nutrition_agent` | Remote | HTTP call to nutrition agent |
| `recipe_agent` | Remote | HTTP call to recipe agent |
| `shopping_agent` | Remote | HTTP call to shopping agent |
| `budget_agent` | Remote | HTTP call to budget agent |
| `finish_node` | Format | Markdown shopping list → `AIMessage` |

## HTTP invoke

### Request

```json
{
  "assistant_id": "personal_shopper",
  "input": {
    "messages": [
      {
        "type": "human",
        "content": "Low-carb chicken dinner under $30 near 75035 at Walmart"
      }
    ]
  },
  "config": {
    "configurable": { "thread_id": "<uuid>" },
    "metadata": { "session_id": "<uuid>" },
    "tags": ["thread:<prefix>"]
  }
}
```

### Response (key fields)

| Field | Type | Description |
|-------|------|-------------|
| `messages` | `Message[]` | Final `AIMessage` with markdown shopping list |
| `request` | `ShoppingRequest` | Parsed structured request |
| `location_id` | `string` | Store / catalog identifier |
| `store_name` | `string` | Display name |
| `selected_recipes` | `Recipe[]` | Matched recipes |
| `ingredients` | `IngredientAvailability[]` | Full ingredient list with prices |
| `shopping_list` | `IngredientAvailability[]` | Same as ingredients when successful |
| `budget_status` | `string` | `ok` \| `over` \| `unchecked` |
| `nutrition_status` | `string` | `ok` \| `unchecked` |
| `constraint_violations` | `string[]` | Budget / constraint messages |
| `agent_steps` | `string[]` | e.g. `parse_request`, `supervisor→recipe_agent` |
| `error` | `string \| null` | Technical error if sub-agent failed |

### Example response snippet

```json
{
  "messages": [
    {
      "type": "ai",
      "content": "## 🛒 Shopping List — Walmart\n\n**Recipes:** Simple Chicken Stir Fry\n..."
    }
  ],
  "agent_steps": [
    "parse_request",
    "find_store",
    "supervisor→nutrition_agent",
    "nutrition_agent",
    "supervisor→recipe_agent",
    "recipe_agent:iter1",
    "supervisor→shopping_agent",
    "shopping_agent",
    "supervisor→budget_agent",
    "budget_agent",
    "supervisor→finish_node",
    "finish_node"
  ],
  "budget_status": "ok"
}
```

## Tools & external APIs

The supervisor calls **one retailer tool** directly. Sub-agents own recipe/shopping/budget tools (see their specs).

### Tool: `find_nearest_store`

| | |
|--|--|
| **Node** | `find_store` |
| **Module** | `personal_shopper.tools.kroger` or `rapidapi_search` (or `mock_tools`) |
| **Invoked via** | `shared.tool_tracing.invoke_tool` |
| **When** | After `parse_request`, before supervisor loop |

**Provider selection:**

| `request.preferred_retailer` | Module | Real API? |
|------------------------------|--------|-----------|
| Kroger family (`kroger`, `ralphs`, `fred meyer`, …) | `kroger.py` | Yes — Kroger Locations API |
| Walmart, Target, Costco, Amazon, Best Buy | `rapidapi_search.py` | Placeholder only (no store locator) |
| `USE_MOCK_TOOLS=true` | `mock_tools.py` | Fixed demo store |

**Input:**

| Parameter | Type | Source |
|-----------|------|--------|
| `zip_code` | `string` | `request.zip_code` (default `94103`) |

**Output (written to state):**

| Field | From tool key |
|-------|---------------|
| `location_id` | `location_id` — Kroger store ID or `rapidapi-{zip}` |
| `store_name` | `name` (fallback: retailer title case) |

**Kroger success response:**

```json
{
  "location_id": "70300132",
  "name": "Kroger Marketplace",
  "address": "123 Main St, Dallas, TX, 75035",
  "chain": "KROGER"
}
```

**RapidAPI placeholder response:**

```json
{
  "location_id": "rapidapi-75035",
  "name": "Nearby store (near 75035)",
  "address": "Near zip code 75035",
  "chain": "Multi-retailer",
  "note": "Catalog price via Google Shopping — in-store availability not confirmed."
}
```

**LangSmith trace name examples:**

- `kroger.find_nearest_store:75035`
- `rapidapi.find_nearest_store:75035@walmart`
- `mock.find_nearest_store:94103`

**Env vars:**

| Variable | Required when |
|----------|---------------|
| `KROGER_CLIENT_ID`, `KROGER_CLIENT_SECRET` | Kroger retailers, mock off |
| `RAPIDAPI_KEY` | Not required for `find_nearest_store` (placeholder); required downstream in shopping agent |
| `USE_MOCK_TOOLS` | `true` → no keys needed |

### LLM (not a tool): `parse_request`

| | |
|--|--|
| **Model** | `gpt-4o-mini` (temperature 0) |
| **Output schema** | `ShoppingRequest` (structured output) |
| **Prompt** | `shared/prompts/parse_request.{system,human}.md` |
| **Env** | `OPENAI_API_KEY` |

### Sub-agent tools (delegated)

| Agent | Tools | Spec |
|-------|-------|------|
| Nutrition | LLM only | [nutrition-agent.md](nutrition-agent.md) |
| Recipe | `search_recipes` | [recipe-agent.md](recipe-agent.md) |
| Shopping | `get_recipe_ingredients`, `check_product_availability`, `get_ingredient_substitutes` | [shopping-agent.md](shopping-agent.md) |
| Budget | None (sums `ingredients[].price`) | [budget-agent.md](budget-agent.md) |

Full tool catalog: [TOOLS.md](../TOOLS.md)

---

## Routing rules (deterministic)

1. Nutrition if diet profile or max calories set and not yet checked
2. Recipe if no recipes selected
3. Shopping if no shopping list
4. Budget if `budget_usd` set and not yet checked
5. Recipe retry if over budget (max 3 refinements)
6. Finish otherwise

Safety cap: **12 supervisor turns** per message.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NUTRITION_AGENT_URL` | `http://127.0.0.1:22001` | Sub-agent base URL |
| `RECIPE_AGENT_URL` | `http://127.0.0.1:22002` | |
| `SHOPPING_AGENT_URL` | `http://127.0.0.1:22003` | |
| `BUDGET_AGENT_URL` | `http://127.0.0.1:22004` | |
| `OPENAI_API_KEY` | — | Required for `parse_request` |
| `KROGER_CLIENT_ID` / `SECRET` | — | Kroger store lookup |
| `RAPIDAPI_KEY` | — | Non-Kroger retailers |
| `USE_MOCK_TOOLS` | `false` | Mock all external APIs |

## Sub-agent failure

If a sub-agent is down, supervisor catches the exception, sets `error`, appends `agent_name:error` to `agent_steps`, and `finish_node` returns a user-facing message with troubleshooting hints.

## curl example

```bash
THREAD=$(uuidgen)
curl -s -X POST "http://127.0.0.1:22000/threads" \
  -H "Content-Type: application/json" -d "{\"thread_id\":\"$THREAD\"}"

curl -s -X POST "http://127.0.0.1:22000/threads/$THREAD/runs/wait" \
  -H "Content-Type: application/json" \
  -d "{
    \"assistant_id\": \"personal_shopper\",
    \"input\": {\"messages\": [{\"type\": \"human\", \"content\": \"Vegan pasta for 2 near 94103\"}]},
    \"config\": {\"configurable\": {\"thread_id\": \"$THREAD\"}}
  }"
```
