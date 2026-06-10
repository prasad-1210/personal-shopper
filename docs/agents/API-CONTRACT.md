# LangGraph Agent API Contract

> **Audience:** External integrators calling Personal Shopper agents over HTTP.  
> **Protocol:** [LangGraph Platform HTTP API](https://langchain-ai.github.io/langgraph/cloud/reference/api/) (LangGraph server / `langgraph dev` / `langgraph up`).

Each agent is a **standalone LangGraph server** exposing the same REST surface. The supervisor orchestrates sub-agents internally; integrators may call any agent directly.

---

## Base URLs

| Agent | Graph ID (`assistant_id`) | Local dev | K8s (in-cluster) |
|-------|---------------------------|-----------|------------------|
| Supervisor | `personal_shopper` | `http://127.0.0.1:22000` | `http://supervisor:8000` |
| Nutrition | `nutrition_agent` | `http://127.0.0.1:22001` | `http://nutrition-agent:8000` |
| Recipe | `recipe_agent` | `http://127.0.0.1:22002` | `http://recipe-agent:8000` |
| Shopping | `shopping_agent` | `http://127.0.0.1:22003` | `http://shopping-agent:8000` |
| Budget | `budget_agent` | `http://127.0.0.1:22004` | `http://budget-agent:8000` |

---

## Authentication

| Header | When required |
|--------|---------------|
| `x-api-key` | When `LANGGRAPH_API_KEY` is set on the server |
| `Content-Type: application/json` | All POST bodies |

---

## Endpoints

### `GET /ok` / `GET /health`

Liveness probe. Returns `200` when the server is up.

### `POST /threads`

Create a conversation thread (checkpoint scope).

**Request body (optional):**

```json
{ "thread_id": "550e8400-e29b-41d4-a716-446655440000" }
```

**Responses:** `200`, `201`, or `409` (thread already exists).

### `POST /threads/{thread_id}/runs/wait`

Run the graph synchronously and return final state.

**Request body:**

```json
{
  "assistant_id": "<graph_id>",
  "input": { },
  "config": {
    "configurable": { "thread_id": "<same-as-path>" },
    "metadata": { "session_id": "optional" },
    "tags": ["optional"]
  }
}
```

**Response:** Graph output object (merged `AgentState` fields). Shape varies by agent; see per-agent specs.

**Timeouts:** Supervisor full flow may take 30–120s. Sub-agents typically &lt; 30s.

### `GET /threads/{thread_id}/runs?limit=1`

List runs on a thread. Use to obtain `run_id` for LangSmith trace URLs after `/runs/wait`.

---

## Shared state schema (`AgentState`)

All agents read/write subsets of this schema. Full definition: `shared/state.py`.

### Input (common)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `messages` | `Message[]` | Supervisor only | Chat history; latest human message drives parse |
| `request` | `ShoppingRequest` | Sub-agents | Structured user request (see below) |
| `location_id` | `string \| null` | Shopping | Kroger store ID or RapidAPI placeholder |
| `store_name` | `string \| null` | Shopping | Display name |
| `selected_recipes` | `Recipe[]` | Shopping | Output of recipe agent |
| `ingredients` | `IngredientAvailability[]` | Budget | Output of shopping agent |
| `budget_status` | `string` | Recipe, Budget | `unchecked` \| `ok` \| `over` |
| `nutrition_status` | `string` | Supervisor | `unchecked` \| `ok` \| `fail` |
| `iteration` | `int` | Recipe | Supervisor turn counter |
| `refinement_count` | `int` | Recipe | Budget retry counter |
| `agent_steps` | `string[]` | All | Progress trail |

### `ShoppingRequest`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `raw_message` | `string` | — | Original user text |
| `meal_keywords` | `string[]` | `[]` | 1–3 dish names |
| `dietary_restrictions` | `string[]` | `[]` | Explicit restrictions |
| `servings` | `int` | `4` | Portion count |
| `zip_code` | `string` | `94103` | US 5-digit zip |
| `pantry_items` | `string[]` | `[]` | Items to exclude from list |
| `preferred_retailer` | `string` | `kroger` | `kroger`, `walmart`, `target`, `costco`, `amazon`, … |
| `budget_usd` | `float \| null` | `null` | Max spend |
| `max_calories_per_serving` | `float \| null` | `null` | Calorie cap |
| `dietary_profile` | `string` | `""` | `diabetic`, `vegan`, `keto`, … |

### `Recipe` (dict)

```json
{
  "id": "string-or-int",
  "title": "string",
  "ready_in_minutes": 40,
  "servings": 4,
  "source_url": "https://..."
}
```

### `IngredientAvailability`

```json
{
  "name": "chicken breast",
  "original": "500g chicken breast",
  "aisle": "Meat",
  "available": true,
  "product_description": "Organic chicken",
  "price": 8.99,
  "substitute": null
}
```

### Message format (supervisor input)

```json
{
  "type": "human",
  "content": "Palak paneer for 4 near 75035"
}
```

Optional UI constraint prefix (parsed by supervisor):

```
[Zip: 75035 | Retailer: walmart | Diet: vegan | Budget: $30 | Max Calories: 500 | Servings: 4]

Palak paneer for dinner
```

---

## Distributed tracing headers

When the supervisor calls a sub-agent via `RemoteGraph(distributed_tracing=True)`, LangGraph propagates:

- `langsmith-trace` — parent run ID
- `langsmith-project` — project name
- `langsmith-metadata` / `langsmith-tags`

Sub-agents export `graph` as a context manager (`export_traced_graph`) to nest traces under the supervisor run.

Direct integrators may pass the same `config` fields for trace correlation.

---

## Error behavior

| Situation | Behavior |
|-----------|----------|
| Sub-agent unreachable | Supervisor sets `error`, appends `agent_name:error` to `agent_steps`, may still finish with user message |
| Tool API failure | Tool returns `available: false` or `error` field; graph continues |
| Missing API keys | Tool raises `OSError` or returns error dict (provider-dependent) |
| `USE_MOCK_TOOLS=true` | All external APIs replaced with `mock_tools` |

---

## Environment variables (all agents)

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Supervisor, Nutrition | LLM calls |
| `LANGSMITH_API_KEY` | Recommended | Tracing |
| `LANGSMITH_TRACING` | Optional | `true` / `false` |
| `LANGSMITH_PROJECT` | Optional | Trace project name |
| `USE_MOCK_TOOLS` | Optional | `true` skips live APIs |
| `REDIS_URI` | Production | Checkpoint backend |
| `DATABASE_URI` | Production | Checkpoint backend |

See per-agent specs for provider-specific keys.

---

## Example: invoke nutrition agent

```bash
THREAD_ID=$(uuidgen)

curl -s -X POST "http://127.0.0.1:22001/threads" \
  -H "Content-Type: application/json" \
  -d "{\"thread_id\": \"$THREAD_ID\"}"

curl -s -X POST "http://127.0.0.1:22001/threads/$THREAD_ID/runs/wait" \
  -H "Content-Type: application/json" \
  -d '{
    "assistant_id": "nutrition_agent",
    "input": {
      "request": {
        "raw_message": "vegan pasta",
        "meal_keywords": ["pasta"],
        "dietary_profile": "vegan",
        "zip_code": "94103",
        "preferred_retailer": "kroger",
        "servings": 4
      },
      "agent_steps": []
    },
    "config": {
      "configurable": { "thread_id": "'"$THREAD_ID"'" }
    }
  }'
```

---

## Per-agent specifications

| Agent | Spec |
|-------|------|
| Supervisor (orchestrator) | [supervisor.md](supervisor.md) |
| Nutrition | [nutrition-agent.md](nutrition-agent.md) |
| Recipe | [recipe-agent.md](recipe-agent.md) |
| Shopping | [shopping-agent.md](shopping-agent.md) |
| Budget | [budget-agent.md](budget-agent.md) |

Tool reference (Kroger, Edamam, RapidAPI): [../TOOLS.md](../TOOLS.md)
