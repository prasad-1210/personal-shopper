# LangGraph agent images (one image per agent)

Agent registry: `deploy/agents.manifest.yaml` (ids, graphIds, build paths).  
Helm deployment: `deploy/helm/agents/<name>/values.yaml` per agent.

Production builds **one image per registry entry** via `scripts/build-agent-images.sh`:

| Image | Config | Graph ID |
|-------|--------|----------|
| `personal-shopper-supervisor` | `supervisor/langgraph.json` | `personal_shopper` |
| `personal-shopper-nutrition` | `agents/nutrition_agent/langgraph.json` | `nutrition_agent` |
| `personal-shopper-recipe` | `agents/recipe_agent/langgraph.json` | `recipe_agent` |
| `personal-shopper-shopping` | `agents/shopping_agent/langgraph.json` | `shopping_agent` |
| `personal-shopper-budget` | `agents/budget_agent/langgraph.json` | `budget_agent` |

## Build (CI or locally)

```bash
bash scripts/build-agent-images.sh              # tag: latest
bash scripts/build-agent-images.sh --tag ci
bash scripts/build-agent-images.sh --only nutrition
```

Or a single image:

```bash
langgraph build -c supervisor/langgraph.json -t personal-shopper-supervisor:latest
```

## Runtime environment

**Infrastructure**

- `REDIS_URI` — Redis for LangGraph queue/checkpointing
- `DATABASE_URI` — Postgres for persistence

**LangSmith** (supervisor + sub-agents for distributed tracing)

- `LANGSMITH_TRACING=true`
- `LANGSMITH_API_KEY`
- `LANGSMITH_ENDPOINT` — default `https://api.smith.langchain.com`
- `LANGSMITH_PROJECT` — e.g. `personal-shopper-dev`

**Supervisor only** (RemoteGraph client URLs)

- `NUTRITION_AGENT_URL` — e.g. `http://<release>-nutrition:8000`
- `RECIPE_AGENT_URL`
- `SHOPPING_AGENT_URL`
- `BUDGET_AGENT_URL`

In Helm **split** mode (default), the ConfigMap sets these to each in-cluster Service. Local dev uses ports `22001`–`22004` via `scripts/dev-multiagent.sh`.

**APIs**

- `OPENAI_API_KEY`
- `KROGER_CLIENT_ID` / `KROGER_CLIENT_SECRET`
- `EDAMAM_APP_ID` / `EDAMAM_APP_KEY` (or `RECIPE_PROVIDER=spoonacular` + `SPOONACULAR_API_KEY`)
- `RAPIDAPI_KEY`

## Ports

- Container: **8000** (LangGraph API)
- Local `langgraph dev`: supervisor **22000**, sub-agents **22001–22004**, UI **22005**

## Health check

`GET /ok`
