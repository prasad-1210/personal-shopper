# Personal Shopper — System Inventory

> **Purpose:** Single reference record of the entire codebase — every significant file,
> every function, how components integrate, and example environment configuration.
> **No source code** — descriptions only.  
> **Last updated:** 2026-05-31

---

## Table of contents

1. [System overview](#1-system-overview)
2. [Integration & data flow](#2-integration--data-flow)
3. [Environment configuration](#3-environment-configuration)
4. [Runtime topology](#4-runtime-topology)
5. [Application code inventory](#5-application-code-inventory)
6. [UI inventory](#6-ui-inventory)
7. [Scripts inventory](#7-scripts-inventory)
8. [Deployment inventory](#8-deployment-inventory)
9. [CI/CD & build pipeline](#9-cicd--build-pipeline)
10. [Tests inventory](#10-tests-inventory)
11. [Documentation inventory](#11-documentation-inventory)
12. [Configuration & manifest files](#12-configuration--manifest-files)
13. [Design asks, decisions & recommendations](#13-design-asks-decisions--recommendations)

---

## 1. System overview

Personal Shopper is a **multi-agent LangGraph** application that turns natural-language meal requests into markdown shopping lists with store availability and prices.

| Layer | Technology | Role |
|-------|------------|------|
| Entry graph | Supervisor (`personal_shopper`) | Parse, store lookup, orchestrate sub-agents |
| Sub-agents | 4 standalone LangGraph servers | Nutrition, recipe, shopping, budget |
| Tools | LangChain `@tool` + HTTP APIs | Kroger, Edamam/Spoonacular, RapidAPI, mock |
| UI | FastAPI + static HTML | Chat, constraints sidebar, LangSmith trace links |
| Persistence | Redis + Postgres (per agent in K8s) | LangGraph checkpoints |
| Observability | LangSmith | Distributed tracing across RemoteGraph calls |
| Packaging | `langgraph build` (Wolfi images) + Helm | One K8s release per agent |

```mermaid
flowchart TB
    User[User / Integrator]
    UI[UI :22005]
    SUP[Supervisor :22000]
    NUT[Nutrition :22001]
    REC[Recipe :22002]
    SHO[Shopping :22003]
    BUD[Budget :22004]

    User --> UI
    UI -->|LangGraph HTTP| SUP
    SUP --> NUT & REC & SHO & BUD
    SUP --> Kroger[Kroger API]
    REC --> Edamam[Edamam / Spoonacular]
    SHO --> Kroger & Edamam & Rapid[RapidAPI]
```

---

## 2. Integration & data flow

### End-to-end path (UI → shopping list)

1. **UI** `POST /session` → creates LangGraph `thread_id`
2. **UI** `POST /chat` → `POST /threads/{id}/runs/wait` on supervisor with `assistant_id: personal_shopper`
3. **Supervisor** `receive_message` → resets per-run state
4. **Supervisor** `parse_request` → OpenAI structured output → `ShoppingRequest`
5. **Supervisor** `find_store` → `find_nearest_store` tool (Kroger or RapidAPI placeholder)
6. **Supervisor loop** (deterministic routing):
   - **Nutrition** (optional) → LLM → `nutrition_constraints`
   - **Recipe** → `search_recipes` tool → `selected_recipes`
   - **Shopping** → ingredient expansion + availability + substitutes → `ingredients`
   - **Budget** (optional) → sum prices vs `budget_usd`; may loop back to recipe
7. **Supervisor** `finish_node` → markdown `AIMessage` shopping list
8. **UI** reads `messages`, `agent_steps`, fetches `run_id` for LangSmith URL

### Cross-process integration (RemoteGraph)

| From | To | Mechanism |
|------|-----|-----------|
| Supervisor | Sub-agents | `RemoteGraph.invoke(state)` over HTTP |
| Supervisor | LangSmith | `distributed_tracing=True` propagates parent trace |
| Sub-agents | LangSmith | `export_traced_graph` context manager nests child runs |
| All tool calls | LangSmith | `invoke_tool()` sets `run_name`, tags, metadata |

### Shared contract

- **State:** `shared/state.py` — `AgentState`, `ShoppingRequest`, `IngredientAvailability`
- **HTTP API:** LangGraph Platform REST (`/threads`, `/threads/{id}/runs/wait`)
- **Spec:** [agents/API-CONTRACT.md](agents/API-CONTRACT.md)

---

## 3. Environment configuration

### Root `.env` (agents + LangSmith)

```bash
# ── Observability ──
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_pt_...
LANGSMITH_PROJECT=personal-shopper-dev
LANGSMITH_ENDPOINT=https://api.smith.langchain.com

# ── LLM (supervisor parse + nutrition agent) ──
OPENAI_API_KEY=sk-...

# ── Kroger (store + inventory for Kroger-family retailers) ──
KROGER_CLIENT_ID=...
KROGER_CLIENT_SECRET=...

# ── RapidAPI (Walmart, Target, Costco, Amazon catalog search) ──
RAPIDAPI_KEY=...

# ── Recipe provider (recipe + shopping ingredient APIs) ──
RECIPE_PROVIDER=edamam          # or spoonacular
EDAMAM_APP_ID=...
EDAMAM_APP_KEY=...
SPOONACULAR_API_KEY=...         # if RECIPE_PROVIDER=spoonacular

# ── Dev without API keys ──
USE_MOCK_TOOLS=false            # true → mock_tools.py for all external APIs

# ── LangGraph server persistence (production / K8s) ──
REDIS_URI=redis://localhost:6379/0
DATABASE_URI=postgres://langgraph:langgraph@localhost:5432/langgraph_supervisor

# ── Sub-agent URLs (supervisor only) ──
NUTRITION_AGENT_URL=http://127.0.0.1:22001
RECIPE_AGENT_URL=http://127.0.0.1:22002
SHOPPING_AGENT_URL=http://127.0.0.1:22003
BUDGET_AGENT_URL=http://127.0.0.1:22004

# ── Optional LangGraph Platform license (prod) ──
# LANGGRAPH_CLOUD_LICENSE_KEY=...
```

### UI `ui/.env`

```bash
LANGGRAPH_URL=http://127.0.0.1:22000
PORT=22005
LANGGRAPH_API_KEY=              # if supervisor requires x-api-key
```

### Environment by component

| Component | Required vars | Optional vars |
|-----------|---------------|---------------|
| Supervisor | `OPENAI_API_KEY`, sub-agent URLs | Kroger/RapidAPI if not mock |
| Nutrition | `OPENAI_API_KEY` | LangSmith |
| Recipe | Edamam **or** Spoonacular **or** `USE_MOCK_TOOLS` | `RECIPE_PROVIDER` |
| Shopping | Recipe provider keys + Kroger **or** RapidAPI **or** mock | |
| Budget | None | |
| UI | `LANGGRAPH_URL` | `LANGGRAPH_API_KEY`, LangSmith (for trace URLs) |
| K8s agents | `REDIS_URI`, `DATABASE_URI` from secrets | Per-agent Redis DB index, Postgres DB name |

---

## 4. Runtime topology

| Mode | How to start | Ports |
|------|--------------|-------|
| Local multi-agent | `bash scripts/dev-multiagent.sh` | Supervisor 22000, agents 22001–22004, UI 22005 |
| Docker Compose | `docker compose up` | Internal 8000, UI 22005 |
| Local K8s | `bash deploy/scripts/local-k8s-setup.sh` | Port-forwards 8000–8080, namespace `agents-local` |
| CI | GitHub Actions | N/A |

| Agent | Graph ID | `langgraph.json` path |
|-------|----------|----------------------|
| Supervisor | `personal_shopper` | `supervisor/langgraph.json` |
| Nutrition | `nutrition_agent` | `agents/nutrition_agent/langgraph.json` |
| Recipe | `recipe_agent` | `agents/recipe_agent/langgraph.json` |
| Shopping | `shopping_agent` | `agents/shopping_agent/langgraph.json` |
| Budget | `budget_agent` | `agents/budget_agent/langgraph.json` |

Build registry: `deploy/agents.manifest.yaml` (CI image builds; Helm uses separate values).

**Container images:** see [§9 Container images & base dependencies](#container-images--base-dependencies) for full image names, Wolfi vs Debian bases, tags per environment, and infra images.

---

## 5. Application code inventory

### `shared/state.py`

Shared Pydantic/TypedDict models for all graphs.

| Symbol | Kind | Description |
|--------|------|-------------|
| `ShoppingRequest` | class | Structured user request: meal keywords, zip, retailer, budget, diet profile, servings, pantry |
| `IngredientAvailability` | class | One shopping line: name, aisle, availability, price, substitute |
| `AgentState` | TypedDict | Full graph state: messages, request, recipes, ingredients, status flags, agent_steps |

---

### `shared/prompt_loader.py`

Loads externalized LLM prompts from `shared/prompts/*.md`.

| Function | Description |
|----------|-------------|
| `load_prompt_text(name, role)` | Read and cache `shared/prompts/{name}.{role}.md` |
| `chat_prompt(name)` | Build `ChatPromptTemplate` from system + human prompt files |

---

### `shared/tool_tracing.py`

| Function | Description |
|----------|-------------|
| `invoke_tool(tool, inputs, ...)` | Wrap `tool.invoke` with LangSmith `run_name`, tags, metadata |

---

### `shared/distributed_tracing.py`

| Function | Description |
|----------|-------------|
| `export_traced_graph(compiled_graph, agent_tag)` | Return context-manager factory for sub-agent `langgraph.json` export; nests traces under supervisor |

---

### `shared/prompts/` (files, not functions)

| File | Used by | Variables |
|------|---------|-----------|
| `parse_request.system.md` | Supervisor `parse_request` | — |
| `parse_request.human.md` | Supervisor `parse_request` | `{message}` |
| `nutrition_constraints.system.md` | Nutrition agent | — |
| `nutrition_constraints.human.md` | Nutrition agent | `{profile}`, `{calories}` |
| `README.md` | Maintainers | Naming conventions |

---

### `supervisor/graph.py`

Orchestrator graph. Module-level: `llm`, sub-agent URL env vars, retailer sets, `graph` export.

| Function | Description |
|----------|-------------|
| `_remote(name, url)` | Cached `RemoteGraph` client with `distributed_tracing=True` |
| `_remote_invoke_config(agent_name)` | Build LangSmith correlation metadata from parent run |
| `_invoke_remote(...)` | HTTP invoke sub-agent with merged config |
| `_get_retailer(state)` | Normalise `preferred_retailer` to Kroger or RapidAPI key |
| `_uses_rapidapi(retailer)` | True for Walmart/Target/Costco/Amazon/Best Buy |
| `receive_message(state)` | Reset per-run state fields on new user message |
| `_parse_ui_constraints(content)` | Parse `[Zip: … \| Retailer: …]` UI prefix |
| `_set_request_field(result, name, value)` | Set field on Pydantic or dict request |
| `_split_ui_prefix_and_body(content)` | Split UI prefix from user message body |
| `_get_request_field(result, name)` | Read field from Pydantic or dict request |
| `_body_mentions_zip(body)` | Regex: user text contains 5-digit zip |
| `_body_mentions_retailer(body)` | User text mentions a retailer name |
| `_body_mentions_diet(body)` | User text mentions diet profile terms |
| `_body_mentions_budget(body)` | User text mentions budget/dollar amount |
| `_body_mentions_calories(body)` | User text mentions calories |
| `_body_mentions_servings(body)` | User text mentions servings |
| `_apply_ui_defaults(result, constraints, body)` | Merge sidebar values when body omits them |
| `parse_request(state)` | LLM structured extract → `ShoppingRequest` |
| `find_store(state)` | Tool: nearest store by zip + retailer |
| `_req_field(state, field, default)` | Read field from `state.request` |
| `_decide_next_agent(state)` | Deterministic routing rules → next node name |
| `_summarise(state)` | Debug string of current state snapshot |
| `supervisor_node(state)` | Increment iteration; set `next_agent` |
| `supervisor_router(state)` | Conditional edge: return `next_agent` |
| `_merge_remote_result(state, result, step_name)` | Merge sub-agent HTTP response into state |
| `call_nutrition_agent(state)` | RemoteGraph → nutrition agent |
| `call_recipe_agent(state)` | RemoteGraph → recipe agent; bump refinement on budget retry |
| `call_shopping_agent(state)` | RemoteGraph → shopping agent |
| `call_budget_agent(state)` | RemoteGraph → budget agent |
| `finish_node(state)` | Format markdown shopping list or error message |
| `build_graph()` | Wire StateGraph; export as `graph` |

---

### `agents/nutrition_agent/graph.py`

| Function | Description |
|----------|-------------|
| `interpret_constraints(state)` | LLM: diet profile → JSON constraints; skip if empty |
| `build_graph()` | Single-node graph; `graph` = `export_traced_graph(...)` |

---

### `agents/recipe_agent/graph.py`

| Function | Description |
|----------|-------------|
| `find_recipes(state)` | Tool: `search_recipes` with diet, nutrition constraints (`exclude_ingredients`, `max_calories`), query fallbacks, budget retry prefix |
| `build_graph()` | Single-node graph; traced export |

---

### `agents/shopping_agent/graph.py`

| Function | Description |
|----------|-------------|
| `_get_retailer(state)` | Normalise retailer for Kroger vs RapidAPI routing |
| `check_availability(state)` | Tools: ingredients → availability → substitutes |
| `build_graph()` | Single-node graph; traced export |

---

### `agents/budget_agent/graph.py`

| Function | Description |
|----------|-------------|
| `validate_budget(state)` | Sum `ingredients[].price` vs `budget_usd`; set status |
| `build_graph()` | Single-node graph; traced export |

---

### `src/personal_shopper/tools/kroger.py`

Kroger Developer API (OAuth2 client credentials).

| Function | Description |
|----------|-------------|
| `_get_kroger_client()` | Build `KrogerAPI` from env credentials |
| `find_nearest_store(zip_code)` | **Tool:** nearest store within 15 miles |
| `check_product_availability(ingredient, location_id)` | **Tool:** search products at store; return price |

---

### `src/personal_shopper/tools/rapidapi_search.py`

RapidAPI real-time-product-search (Google Shopping catalog).

| Function | Description |
|----------|-------------|
| `_headers()` | RapidAPI auth headers from `RAPIDAPI_KEY` |
| `_parse_price(price_str)` | Extract float from price strings |
| `_normalise_retailer(retailer)` | Map retailer name to API store key |
| `_extract_products(data)` | Parse product list from API response shapes |
| `_product_fields(product)` | Extract title, price, store, URL from product dict |
| `_http_error_message(status, body)` | Human-readable 403/429 messages |
| `find_nearest_store(zip_code)` | **Tool:** placeholder (no real store locator) |
| `check_product_availability(ingredient, location_id, store)` | **Tool:** catalog search by retailer |

---

### `src/personal_shopper/tools/edamam.py`

Edamam Recipe Search API.

| Function | Description |
|----------|-------------|
| `_creds()` | Read `EDAMAM_APP_ID` / `EDAMAM_APP_KEY` |
| `_headers(app_id)` | Edamam account user header |
| `_extract_id(uri)` | Parse recipe ID from Edamam URI |
| `_map_aisle(food_category)` | Map food category to store aisle name |
| `search_recipes(query, diet, max_ready_time, number, exclude_ingredients, max_calories)` | **Tool:** recipe search with exclusion and calorie caps |
| `get_recipe_ingredients(recipe_id)` | **Tool:** ingredient list for recipe |
| `get_ingredient_substitutes(ingredient_name)` | **Tool:** always empty (no Edamam API) |

---

### `src/personal_shopper/tools/spoonacular.py`

Spoonacular API (alternate recipe provider).

| Function | Description |
|----------|-------------|
| `_get_api_key()` | Read `SPOONACULAR_API_KEY` |
| `search_recipes(...)` | **Tool:** complex search |
| `get_recipe_ingredients(recipe_id)` | **Tool:** extended ingredients |
| `get_ingredient_substitutes(ingredient_name)` | **Tool:** Spoonacular substitutes API |

---

### `src/personal_shopper/tools/mock_tools.py`

Deterministic fakes when `USE_MOCK_TOOLS=true`. Same tool names/signatures as live providers.

| Function | Description |
|----------|-------------|
| `find_nearest_store(zip_code)` | **Tool:** fixed demo Kroger store |
| `check_product_availability(ingredient, location_id)` | **Tool:** most items available; lemongrass/galangal unavailable |
| `search_recipes(...)` | **Tool:** 2 mock recipes (IDs 1001, 1002) |
| `get_recipe_ingredients(recipe_id)` | **Tool:** mock ingredient lists |
| `get_ingredient_substitutes(ingredient_name)` | **Tool:** hardcoded subs for select items |

---

## 6. UI inventory

### `ui/server.py`

FastAPI proxy between browser and supervisor LangGraph server.

| Symbol | Kind | Description |
|--------|------|-------------|
| `ChatRequest` | model | `message`, optional `thread_id` |
| `SessionResponse` | model | New `thread_id` for chat |
| `ChatResponse` | model | `reply`, `thread_id`, `agent_steps`, `run_id`, `langsmith_url`, budget fields |
| `_langsmith_trace_url(run_id)` | fn | Resolve LangSmith URL via `Client.read_run` |
| `_request_headers()` | fn | JSON + optional `x-api-key` |
| `_run_config(thread_id)` | fn | LangGraph config with thread metadata/tags |
| `_ensure_langgraph_thread(...)` | async fn | `POST /threads` create or 409 |
| `_latest_thread_run_id(...)` | async fn | `GET /threads/{id}/runs` for trace link |
| `index()` | route GET `/` | Serve `index.html` |
| `health()` | route GET `/health` | Liveness `{"status":"ok"}` |
| `create_session()` | route POST `/session` | New thread UUID |
| `chat(req)` | route POST `/chat` | Invoke supervisor `runs/wait`, extract reply + trace |

### `ui/index.html`

Single-page chat UI (no Python functions). Features: constraint sidebar, retailer/diet/budget chips, agent steps bar, markdown rendering (`marked.js`), LangSmith trace link, example prompts, `sessionStorage` thread persistence.

### `ui/requirements.txt`

Python deps: FastAPI, httpx, uvicorn, python-dotenv, langsmith.

---

## 7. Scripts inventory

| File | Description |
|------|-------------|
| `scripts/dev-multiagent.sh` | Start all 5 LangGraph agents locally on ports 22000–22004 |
| `scripts/multiagent-ports.sh` | Export port constants (sourced by other scripts) |
| `scripts/stop-multiagent.sh` | Stop local agent processes |
| `scripts/tail-multiagent-logs.sh` | Tail combined agent logs |
| `scripts/check-agents.sh` | Health-check agent HTTP endpoints |
| `scripts/build-agent-images.sh` | Run `langgraph build` for all manifest agents |
| `scripts/langgraph-agents.py` | Registry CLI — see functions below |
| `deploy/scripts/helm-deploy.sh` | Deploy one agent with layered Helm values |
| `deploy/scripts/helm-deploy-all.sh` | Deploy all agents + UI for an environment |
| `deploy/scripts/local-k8s-setup.sh` | Full stack to Docker Desktop K8s (`agents-local`) |
| `deploy/scripts/local-k8s-teardown.sh` | Remove local K8s deployment |
| `deploy/scripts/local-k8s-status.sh` | Pod/status summary |
| `deploy/scripts/create-agent-secrets.sh` | Create K8s secrets with Redis/Postgres URIs |

### `scripts/langgraph-agents.py` functions

| Function | Description |
|----------|-------------|
| `_load_yaml(path)` | Parse YAML file |
| `load_manifest()` | Load `deploy/agents.manifest.yaml` agents list |
| `helm_agent_values(manifest_id)` | Load matching `deploy/helm/agents/*/values.yaml` |
| `buildable_agents()` | Agents with `build.config` in manifest |
| `image_repository(agent_id, prefix, explicit)` | Resolve Docker image repository name |
| `main()` | CLI: `ids`, `build-specs`, `image-repos` |

---

## 8. Deployment inventory

### Helm three-layer model

| Layer | Path | Contents |
|-------|------|----------|
| K8s primitives | `deploy/helm/charts/k8s-primitives/` | Library templates: Deployment, Service, HPA, PDB, Ingress, ServiceAccount |
| LangGraph primitives | `deploy/helm/charts/langgraph-primitives/` | Agent Deployment, ConfigMap, ExternalName Redis/Postgres, network policy |
| Org | `deploy/helm/org/` | Org-wide `values.yaml`, `configmap.yaml` (security, LangSmith project) |
| Overlays | `deploy/helm/overlays/{local,dev,prod}/` | Per-environment Redis/Postgres external names, replicas |
| Per-agent | `deploy/helm/agents/{supervisor,nutrition-agent,...}/` | Image, ports, Redis DB index, Postgres DB name, inter-agent URLs |

### Key Helm templates (`langgraph-primitives`)

| Template | Description |
|----------|-------------|
| `agent-deployment.yaml` | LangGraph container; secrets for `REDIS_URI`, `DATABASE_URI`, API keys |
| `agent-configmap.yaml` | Env: agent URLs, `USE_MOCK_TOOLS`, LangSmith project |
| `agent-service.yaml` | ClusterIP on port 8000 |
| `redis-external.yaml` | ExternalName service to Azure Redis (dev/prod) |
| `postgres-external.yaml` | ExternalName service to Azure Postgres |
| `agent-network-policy.yaml` | Restrict supervisor ingress to sub-agents |
| `agent-ingress.yaml` | UI ingress (local) |

### Docker files

| File | Description |
|------|-------------|
| `Dockerfile.agent` | Base for `langgraph build` output (reference) |
| `Dockerfile.ui` | UI image (Python + static HTML) |
| `docker-compose.yml` | Local compose: Redis, Postgres, agents, UI |

---

## 9. CI/CD & build pipeline

### Build pipeline overview

```mermaid
flowchart LR
    subgraph PR_CI [ci.yaml — PR / push]
        Lint[Ruff + pytest]
        Eval[LangSmith eval]
        Wolfi[wolfi check]
        LGBuild[langgraph build]
        UIBuild[Dockerfile.ui build]
        HelmCI[helm lint partial]
    end
    subgraph CD [cd-dev.yaml — develop/master]
        LGBuildCD[langgraph build]
        PushGHCR[push GHCR]
        UIpush[UI image push]
        HelmPost[helm validate post-build]
    end
    subgraph HelmPR [helm-validate.yaml — PR helm paths]
        Matrix[6 agents × 2 envs]
        Owner[ownership hint]
    end
    Manifest[agents.manifest.yaml] --> LGBuild & LGBuildCD
    BuildScript[build-agent-images.sh] --> LGBuild & LGBuildCD
    AgentsPy[langgraph-agents.py] --> BuildScript
```

### Build-related files

| File | Role in CI/CD |
|------|----------------|
| `deploy/agents.manifest.yaml` | **Source of truth** for which agents to build; maps id → `langgraph.json` path, graphId, remote env var |
| `scripts/langgraph-agents.py` | CLI: `ids`, `build-specs`, `image-repos`; bridges manifest ↔ Helm image names |
| `scripts/build-agent-images.sh` | Loops manifest agents; runs `langgraph build -c <config> -t <image>` per agent |
| `supervisor/langgraph.json` | Build config: wolfi, python 3.12, graph export path |
| `agents/*/langgraph.json` | Same per sub-agent |
| `Dockerfile.ui` | UI image build (`python:3.12-slim`, port 22005) — **not** used for agents |
| `Dockerfile.agent` | Docker Compose dev base (`python:3.12-slim-bookworm` + `langgraph dev`); not used in CI/CD Wolfi builds |
| `Dockerfile.agent.md` | Human docs: image names, build commands, runtime env |
| `pyproject.toml` | Package install for CI tests (`pip install -e .`) |
| `Makefile` | Local `test`, `lint`, `format` (not invoked by GitHub Actions today) |

### Container images & base dependencies

Three **distinct** image strategies exist — do not confuse them:

| Strategy | When used | Base OS | How built |
|----------|-----------|---------|-----------|
| **A. LangGraph Wolfi** | CI, CD, local K8s prod-like | LangGraph API **Wolfi** (upstream `langchain/langgraph-api`) | `langgraph build` |
| **B. Dockerfile.agent** | Docker Compose dev only | `python:3.12-slim-bookworm` (Debian) | `docker compose build` |
| **C. Dockerfile.ui** | UI everywhere | `python:3.12-slim` (Debian) | `docker build -f Dockerfile.ui` |

#### A. Production agent images (`langgraph build` / Wolfi)

All five agents share the same build settings in their `langgraph.json`:

| Setting | Value | Effect |
|---------|-------|--------|
| `image_distro` | `wolfi` | Base image = LangGraph API Wolfi distro (not `debian` / `ubuntu`) |
| `python_version` | `3.12` | Python runtime inside the LangGraph API container |
| Build platform | `linux/amd64` | Set by `build-agent-images.sh` (`--platform linux/amd64`) |
| Base pull | `--pull` | Fresh upstream Wolfi base on each CI/CD build |

**Upstream base (conceptual):** `langgraph build` produces an image layered on the published **LangGraph API Wolfi** image. Helm org values require `runAsNonRoot: false` and `readOnlyRootFilesystem: false` because this base runs as root and writes runtime cache under `/tmp`.

**Python package dependencies** (baked in at build time via `langgraph.json` → `dependencies`):

| Agent | `langgraph.json` | Path dependencies included |
|-------|------------------|----------------------------|
| Supervisor | `supervisor/langgraph.json` | repo root (`..`), `shared/` |
| Nutrition | `agents/nutrition_agent/langgraph.json` | repo root, `shared/` |
| Recipe | `agents/recipe_agent/langgraph.json` | repo root, `shared/`, `src/` (tools) |
| Shopping | `agents/shopping_agent/langgraph.json` | repo root, `shared/`, `src/` |
| Budget | `agents/budget_agent/langgraph.json` | repo root, `shared/` |

Runtime Python deps come from `pyproject.toml` (installed during `langgraph build`): `langgraph`, `langchain-openai`, `httpx`, `pydantic`, `kroger-api`, etc.

#### Complete agent image matrix

| Manifest id | Graph ID | Image repository (default) | `langgraph.json` | Helm chart folder |
|-------------|----------|----------------------------|------------------|-------------------|
| `supervisor` | `personal_shopper` | `personal-shopper-supervisor` | `supervisor/langgraph.json` | `supervisor` |
| `nutrition` | `nutrition_agent` | `personal-shopper-nutrition` | `agents/nutrition_agent/langgraph.json` | `nutrition-agent` |
| `recipe` | `recipe_agent` | `personal-shopper-recipe` | `agents/recipe_agent/langgraph.json` | `recipe-agent` |
| `shopping` | `shopping_agent` | `personal-shopper-shopping` | `agents/shopping_agent/langgraph.json` | `shopping-agent` |
| `budget` | `budget_agent` | `personal-shopper-budget` | `agents/budget_agent/langgraph.json` | `budget-agent` |
| *(UI — not in manifest)* | — | `personal-shopper-ui` | — | `ui` |

#### Image tags by environment

| Environment | Agent tag | UI tag | pullPolicy | Image source |
|-------------|-----------|--------|------------|--------------|
| Local K8s (`agents-local`) | `local` | `local` | `Never` | Built on host via `build-agent-images.sh` |
| CI | `ci` | `ci` | — | Built in GitHub Actions, not pushed (agents) |
| CD dev (GHCR) | `<git-sha>` + `dev` | `<git-sha>` + `dev` | `Always` | `ghcr.io/<github-repo>/personal-shopper-{id}` |
| Helm dev/prod values | `latest` (placeholder) | `latest` | `Always` | `ghcr.io/<YOUR_ORG>/personal-shopper-{id}` |

Full CD image examples (repo = `myorg/personal-shopper`):

```
ghcr.io/myorg/personal-shopper/personal-shopper-supervisor:abc1234
ghcr.io/myorg/personal-shopper/personal-shopper-supervisor:dev
ghcr.io/myorg/personal-shopper/personal-shopper-ui:abc1234
```

#### B. Docker Compose dev image (`Dockerfile.agent`)

| Layer | Detail |
|-------|--------|
| **Base image** | `python:3.12-slim-bookworm` |
| **OS packages** | `curl` (healthchecks) |
| **Installed at build** | `pip install -e ".[dev]"` + `langgraph-cli[inmem]>=0.4.14` |
| **Runtime command** | `langgraph dev` (not Wolfi API server) |
| **Purpose** | Fast local multi-agent via `docker compose up` without pre-building Wolfi images |

Compose service names vs image: one shared `Dockerfile.agent` image reused by all agent services; each service overrides `command` to `cd` into its agent folder.

#### C. UI image (`Dockerfile.ui`)

| Layer | Detail |
|-------|--------|
| **Base image** | `python:3.12-slim` |
| **App** | `ui/server.py` + `ui/index.html` |
| **pip deps** | `ui/requirements.txt` (FastAPI, httpx, uvicorn, python-dotenv, langsmith) |
| **Expose** | `22005` (local); Helm local K8s uses `8080` via values override |
| **Does not include** | Agent graphs, `shared/`, or LangGraph server |

#### Infrastructure & data-store images (not application)

| Image | Used in | Role |
|-------|---------|------|
| `postgres:16` | `docker-compose.yml` | Single DB for compose dev |
| `redis:7-alpine` | `docker-compose.yml` | Redis for compose dev |
| `bitnami/redis` (chart) | `local-k8s-setup.sh` | In-cluster Redis (`agents-local`) |
| `bitnami/postgresql` (chart) | `local-k8s-setup.sh` | In-cluster Postgres + per-agent DBs |
| `postgres:16` | `local-k8s-setup.sh` (Job) | One-shot `pg-init-databases` job |
| Azure Redis / Postgres hostnames | `overlays/dev`, `overlays/prod` | ExternalName targets (not container images in repo) |

#### Dependency diagram (images)

```mermaid
flowchart TB
    subgraph upstream [Upstream bases]
        Wolfi[LangGraph API Wolfi image]
        PySlim[python:3.12-slim]
        PyBookworm[python:3.12-slim-bookworm]
        PG[postgres:16]
        Redis[redis:7-alpine]
    end
    subgraph app [Application images]
        Agents[personal-shopper-supervisor … budget]
        UIimg[personal-shopper-ui]
        DevAgent[Dockerfile.agent dev image]
    end
    Wolfi -->|langgraph build| Agents
    PySlim -->|Dockerfile.ui| UIimg
    PyBookworm -->|Dockerfile.agent| DevAgent
    PG --> compose[docker-compose]
    Redis --> compose
```

Helm folder names differ (`nutrition-agent` vs manifest id `nutrition`) — mapped in `langgraph-agents.py` `HELM_AGENT_DIRS`.

### `scripts/build-agent-images.sh` behavior

| Flag / env | Effect |
|------------|--------|
| `--tag <name>` | Docker tag (CI uses `ci`; CD uses `github.sha`) |
| `--push` | `docker push` after each build |
| `--only <id>` | Build single manifest agent (e.g. `nutrition`) |
| `IMAGE_PREFIX` | Image repo prefix (default `personal-shopper`; CD sets `ghcr.io/.../personal-shopper`) |

Per agent: `langgraph build -c <path> --platform linux/amd64 --pull -t ${IMAGE_PREFIX}-${id}:${TAG}`

Reads build list from: `python3 scripts/langgraph-agents.py build-specs` → `id:config` lines.

### Workflow: `.github/workflows/ci.yaml`

**Trigger:** push/PR to `main`, `master`, `develop`

| Job | Depends on | Steps (summary) |
|-----|------------|-----------------|
| `lint-and-test` | — | `pip install -e .`; ruff (non-blocking `|| true`); pytest with `USE_MOCK_TOOLS=true`; multi-agent graph import + `distributed_tracing` assert; UI `import server` |
| `build-langgraph-images` | lint-and-test | Verify all `langgraph.json` have `image_distro: wolfi`; `build-agent-images.sh --tag ci`; docker smoke import supervisor + nutrition images |
| `build-ui-image` | lint-and-test | `docker build -f Dockerfile.ui`; smoke `import server` in container |
| `helm-validate` | lint-and-test | `helm lint` supervisor + UI (local overlay); template supervisor; grep inter-agent URLs |
| `eval` | lint-and-test | Seed LangSmith datasets; parse eval gates at 0.70 (`--ci`); recipe/substitution evals informational (`continue-on-error`) |

**Not in CI today:** full 6×3 helm matrix (that's `helm-validate.yaml`); prod CD.

### Workflow: `.github/workflows/cd-dev.yaml`

**Trigger:** push to `master`, `develop`

| Job | Steps (summary) |
|-----|-----------------|
| `build-and-push` | Login GHCR; `build-agent-images.sh --tag $GITHUB_SHA`; tag+push each agent as `:sha` and `:dev`; `docker/build-push-action` for UI |
| `helm-validate` | Post-build helm lint + template supervisor (local overlay) |

**Not in CD today:** Auto-update `deploy/helm/agents/*/values.yaml` image tags; deploy to AKS; prod approval gate.

### Workflow: `.github/workflows/helm-validate.yaml`

**Trigger:** PR when paths under `deploy/helm/**`, `helm-deploy*.sh`, or this workflow change

| Job | Matrix | Steps |
|-----|--------|-------|
| `lint` | 6 agents × (`local`, `dev`) = 12 runs | `helm dependency build`; `helm lint`; `helm template` dry-run |
| `ownership-check` | single | Diff changed paths → flag platform vs app-team layer |

**Note:** `prod` overlay is not in the matrix (lint works locally; not gated in this workflow).

### CI/CD secrets & permissions

| Context | Secrets / tokens |
|---------|------------------|
| CI tests | No real API keys; `OPENAI_API_KEY=sk-test-fake`, `USE_MOCK_TOOLS=true` |
| cd-dev push | `GITHUB_TOKEN` → GHCR (`packages: write`) |
| Runtime deploy | `create-agent-secrets.sh` — Redis/Postgres URIs, API keys (not in GitHub Actions yet) |

### Local equivalents (not CI)

| Task | Command |
|------|---------|
| Run tests | `make test` or `pytest tests/unit/` |
| Build all agent images | `bash scripts/build-agent-images.sh --tag local` |
| Build one agent | `bash scripts/build-agent-images.sh --only supervisor --tag local` |
| Build UI | `docker build -f Dockerfile.ui -t personal-shopper-ui:local .` |
| Deploy local K8s | `bash deploy/scripts/local-k8s-setup.sh` (builds images if missing, Helm install) |

### What is **not** covered (deferred)

- `cd-prod.yaml` / AKS deploy with approval gate
- CI eval threshold tightening (parse 0.70 → 0.85 after baseline; recipe/sub 0.50 → 0.65)
- Auto-commit updated Helm image tags after CD
- `staging` overlay in helm-validate matrix
- `integration-tests.yml` (if present in fork — not in current workflow set)

---

## 10. Tests inventory

| File | Tests |
|------|-------|
| `tests/conftest.py` | `anyio_backend` fixture |
| `tests/unit/test_state.py` | `ShoppingRequest.preferred_retailer` cases |
| `tests/unit/test_distributed_tracing.py` | Sub-agent contextmanager export; trace yield |
| `tests/unit/test_supervisor_tracing.py` | Remote invoke config; UI prefix parsing |
| `tests/unit/test_tool_tracing.py` | `invoke_tool` run_name and metadata |
| `tests/unit/test_prompt_loader.py` | Prompt file load; `chat_prompt` format |
| `tests/unit/test_nutrition_filter.py` | Mock exclusion filter; nutrition_constraints → `find_recipes` |
| `tests/eval/conftest.py` | Mock-mode defaults for LangSmith eval scripts |
| `tests/eval/seed_datasets.py` | Idempotent LangSmith dataset seeding (3 datasets) |
| `tests/eval/evaluators.py` | Heuristic + LLM-as-judge evaluators |
| `tests/eval/run_parse_eval.py` | Parse node eval; CI gate at 0.70 |
| `tests/eval/run_recipe_eval.py` | Recipe relevance eval (LLM judge) |
| `tests/eval/run_substitution_eval.py` | Substitution quality eval (LLM judge) |

---

## 11. Documentation inventory

| File | Audience | Contents |
|------|----------|----------|
| `README.md` | Developers | Quick start paths, prerequisites, CI summary |
| `docs/ARCHITECTURE.md` | Developers | Design decisions, topology, deferred features |
| `docs/SYSTEM-INVENTORY.md` | Record / audit | **This file** |
| `docs/TOOLS.md` | Integrators | External API tool catalog |
| `docs/agents/README.md` | Integrators | Agent spec index |
| `docs/agents/API-CONTRACT.md` | Integrators | HTTP API, AgentState schema |
| `docs/agents/supervisor.md` | Integrators | Supervisor spec + tools |
| `docs/agents/nutrition-agent.md` | Integrators | Nutrition spec |
| `docs/agents/recipe-agent.md` | Integrators | Recipe spec + tools |
| `docs/agents/shopping-agent.md` | Integrators | Shopping spec + tools |
| `docs/agents/budget-agent.md` | Integrators | Budget spec |
| `deploy/README.md` | Ops | Deploy overview |
| `deploy/helm/README.md` | Ops | Helm usage |
| `deploy/helm/LAYERS.md` | Ops | Three-layer ownership model |
| `deploy/scripts/README.md` | Ops | Script reference |
| `ui/README.md` | Developers | UI setup |
| `shared/prompts/README.md` | Developers | Prompt file conventions |

---

## 12. Configuration & manifest files

| File | Description |
|------|-------------|
| `.env.example` | Root env template for all agents |
| `ui/.env.example` | UI LangGraph URL and port |
| `pyproject.toml` | Python package, deps, ruff, pytest, setuptools package-data for prompts |
| `deploy/agents.manifest.yaml` | Agent IDs, graph IDs, `langgraph.json` build paths, remote env var names |
| `supervisor/langgraph.json` | Graph `personal_shopper`, wolfi, deps |
| `agents/*/langgraph.json` | Per sub-agent graph registration |
| `Makefile` | Convenience targets |
| `uv.lock` | uv lockfile (if using uv) |

### Per-agent Helm values (config, not code)

Each `deploy/helm/agents/<name>/values.yaml` sets: `image.repository/tag`, `redis.dbIndex`, `postgres.database`, `langsmith.project`, `interAgent.*Url` (supervisor).  
Each `configmap.yaml` sets agent-specific env data (e.g. UI flags).

---

## 13. Design asks, decisions & recommendations

This section captures **product and engineering intent** from the design conversation (compliance audit, documentation, tracing, prompts, CI/CD). It complements [ARCHITECTURE.md](ARCHITECTURE.md) (runtime design) and the compliance gap analysis performed in-session.

### 13.1 Design asks (what was requested)

| # | Ask | Outcome / where documented |
|---|-----|----------------------------|
| D1 | **Compliance audit** — planned vs implemented vs gaps for requirements A–G (Helm, agents, LangSmith, CI/CD, UI) | Gap analysis in session; partial scorecard; deferred items in §13.4 and [ARCHITECTURE.md §Deferred](ARCHITECTURE.md#not-implemented-intentionally-deferred) |
| D2 | **LangSmith traces easier to follow** — expose tool names in trace tree | `shared/tool_tracing.invoke_tool()`; named runs e.g. `kroger.check_product_availability:basil` |
| D3 | **Live architecture documentation** — current agents, graphs, design patterns | [ARCHITECTURE.md](ARCHITECTURE.md) (maintainer-updated) |
| D4 | **Externalize prompts** — editable without code changes | `shared/prompts/*.md` + `shared/prompt_loader.py` |
| D5 | **Clarify prompt caching** — what is cached today | In-process `.md` string cache only; no OpenAI/LangSmith Hub caching (§13.4) |
| D6 | **Explain deterministic supervisor** — why not LLM router; is it recommended? | Decision D4; recommendation R1 |
| D7 | **In-code developer docs** — docstrings for functions and tools | `shared/`, `supervisor/`, `agents/`, `tools/` |
| D8 | **Per-agent integration specs** — Swagger-level HTTP docs for external teams | [agents/*.md](agents/README.md) + [API-CONTRACT.md](agents/API-CONTRACT.md) |
| D9 | **Tool details in per-agent specs** — I/O, providers, trace names per agent | Tools sections in each [agents/*.md](agents/README.md) |
| D10 | **System inventory** — all files, all functions, integration, example env, no code | **This document** |
| D11 | **CI/CD & build inventory** — workflows, manifest, image build chain | [§9 CI/CD & build pipeline](#9-cicd--build-pipeline) |
| D12 | **Image names & base dependencies** — Wolfi vs Debian, tags, infra images | [§9 Container images](#container-images--base-dependencies) |
| D13 | **Record design asks / decisions / recommendations** in inventory | **This section** |

#### Original platform requirements (compliance reference)

| Area | Original intent | Current state (summary) |
|------|-----------------|-------------------------|
| AKS / self-hosted LangSmith | Target prod on AKS; LangSmith Cloud first | Overlays + ExternalNames; no AKS CD workflow; cloud LangSmith via env |
| Azure Redis / Postgres PaaS | Managed backing services | dev/prod ExternalName placeholders; local uses in-cluster Bitnami |
| 3-layer Helm | k8s-primitives → langgraph-primitives → org/overlays/agents | **Implemented** — custom charts, not LangSmith upstream Helm chart |
| GRC environments | dev / staging / prod separation | `local`, `dev`, `prod` overlays; **no `staging`**; no prod approval gate |
| Novice-friendly | Simple dev path, mock mode, README | **Implemented** — Path 1–3, `USE_MOCK_TOOLS`, docs |
| Engineering CI gates | Tests, helm lint, eval threshold | Tests + wolfi + partial helm + **LangSmith eval** (parse at 0.70; recipe/sub informational) |

---

### 13.2 Decisions (what we chose and why)

| ID | Decision | Rationale | Key artifacts |
|----|----------|-----------|---------------|
| **D1** | **Multi-agent via RemoteGraph** — one LangGraph server per agent | Independent deploy, scale, trace per domain; matches K8s one-pod-per-agent | `supervisor/graph.py`, per-agent `langgraph.json` |
| **D2** | **Deterministic supervisor routing** — rule engine, not LLM router | Predictable traces, testable, no extra LLM cost per turn; fixed pipeline (see R1) | `_decide_next_agent()` |
| **D3** | **Shared `AgentState`** across all agents | Simple merge over HTTP via RemoteGraph; UI reads one shape | `shared/state.py` |
| **D4** | **Imperative `tool.invoke()`** inside nodes, not LLM `bind_tools` | Cheaper, reliable pipelines; trace names via `invoke_tool` | `shared/tool_tracing.py`, agent graphs |
| **D5** | **Custom 3-layer Helm** (not LangSmith published chart) | Org control, Wolfi conventions, per-agent values ownership | `deploy/helm/` |
| **D6** | **Wolfi production images** via `langgraph build` | LangGraph CLI standard; `image_distro: wolfi` in all agent `langgraph.json` | `build-agent-images.sh`, CI wolfi check |
| **D7** | **Wolfi security posture** — `runAsNonRoot: false`, writable root FS | Upstream Wolfi API constraint; documented in org Helm values | `deploy/helm/org/values.yaml` |
| **D8** | **Secrets as full URIs** — `REDIS_URI`, `DATABASE_URI` from K8s secrets | Wolfi/env compatibility; not assembled in templates | `agent-deployment.yaml`, `create-agent-secrets.sh` |
| **D9** | **Omit `LANGGRAPH_CHECKPOINTER` env** from org configmap | Plain string value crashed Wolfi API; URIs from secrets suffice | `org/configmap.yaml` (comment only) |
| **D10** | **Per-agent Redis DB index (0–4) + Postgres database** | Isolation between agent checkpoints | `deploy/helm/agents/*/values.yaml` |
| **D11** | **Distributed tracing** — `RemoteGraph(distributed_tracing=True)` + `export_traced_graph` | Single LangSmith tree across processes | `shared/distributed_tracing.py` |
| **D12** | **One LangGraph thread per UI chat** | Checkpoint + trace grouping | `ui/server.py` `POST /session`, `_run_config` |
| **D13** | **Prompts in git markdown files** — not LangSmith Prompt Hub (yet) | Reviewable in PRs; works offline/CI without Hub credentials | `shared/prompts/` |
| **D14** | **In-process prompt text cache** — no file watch reload | Simplicity; restart agent after `.md` edit | `prompt_loader._cache` |
| **D15** | **Edamam default in code** for `RECIPE_PROVIDER`; Spoonacular optional | Edamam free tier; swap via env | `recipe_agent`, `shopping_agent` |
| **D16** | **Kroger vs RapidAPI retailer split** | Official inventory vs catalog-only multi-retailer | `kroger.py`, `rapidapi_search.py` |
| **D17** | **Budget feedback loop** — re-invoke recipe agent up to 3× when over budget | Cheaper recipe retry without new agent | `MAX_BUDGET_RETRIES`, supervisor routing |
| **D18** | **Compose dev uses Debian + `langgraph dev`** — not Wolfi images | Fast inner loop; production path uses Wolfi | `Dockerfile.agent`, `docker-compose.yml` |
| **D19** | **Build registry in manifest** — Helm values separate | CI reads `agents.manifest.yaml`; deploy reads layered Helm | `deploy/agents.manifest.yaml` |
| **D20** | **Agent integration docs as markdown** — not OpenAPI YAML | LangGraph HTTP is documented contract-style in MD | `docs/agents/` |

---

### 13.3 Recommendations

#### Adopted (aligned with current codebase)

| ID | Recommendation | Status |
|----|----------------|--------|
| **R1** | **Keep deterministic supervisor** for this product — pipeline is known; routing is state-flag driven | **Adopted** — do not switch to LLM router without new requirements |
| **R2** | **Named tool runs in LangSmith** for imperative tools | **Adopted** — `invoke_tool()` |
| **R3** | **Externalize LLM prompts** to versioned files | **Adopted** — `shared/prompts/` |
| **R4** | **Live ARCHITECTURE.md** updated when graphs/env change | **Adopted** — maintainer checklist |
| **R5** | **Per-agent HTTP specs** for external integrators | **Adopted** — `docs/agents/` |
| **R6** | **SYSTEM-INVENTORY.md** as audit record (files, functions, CI, images) | **Adopted** — this file |
| **R7** | **Mock mode** (`USE_MOCK_TOOLS`) for CI and novice dev | **Adopted** — unit tests, `.env.example` |

#### Future (if requirements grow)

| ID | Recommendation | When to revisit |
|----|----------------|-----------------|
| **R8** | **Hybrid supervisor** — rules for happy path; LLM only on ambiguous failures or user mid-flight replanning | Conversational detours, dynamic agent roster |
| **R9** | **LangSmith offline eval + CI threshold gate** | **Adopted** — `tests/eval/`; parse eval at 0.70 |
| **R10** | **Prod CD to AKS** with GitHub Environment approval + secret scoping | GRC path to production |
| **R11** | **HITL** — `interrupt()` before final list; UI resume | `ENABLE_HUMAN_IN_THE_LOOP` flag exists but unused |
| **R12** | **OpenAI prompt caching** or **Prompt Hub** (`hub.pull`) | High LLM volume or non-dev prompt editors |
| **R13** | **Prompt hot-reload** (mtime invalidation) | Faster local prompt iteration without restart |
| **R14** | **CD auto-bump** Helm `image.tag` after GHCR push | Close build→deploy loop |
| **R15** | **Add `staging` overlay** + include `prod` in helm-validate matrix | Full GRC environment parity |
| **R16** | **Wire `nutrition_constraints` into recipe search** | **Adopted** — `exclude_ingredients` + `max_calories` on `search_recipes` |

#### Suggested next build order (from gap analysis)

1. `cd-prod.yaml` + AKS deploy + approval gate (R10)  
2. HITL interrupt + UI resume (R11)  
3. Tighten eval thresholds after baseline (parse 0.85, recipe/sub 0.65)  

#### Quick wins (low effort)

| Item | Fix |
|------|-----|
| helm-validate matrix | Add `prod` overlay |
| CD pipeline | Patch/commit `image.tag` in `deploy/helm/agents/*/values.yaml` after push |
| CI lint | Remove `ruff \|\| true` soft-fail |
| Supervisor turn cap | Document or align `MAX_SUPERVISOR_TURNS` (12) vs original “max 3” spec |
| `.env.example` | Default `RECIPE_PROVIDER=edamam` to match code default |

---

### 13.4 Deferred & known gaps

Consolidated from compliance audit, architecture deferred list, and conversation. Remove rows when built.

| Item | Category | Notes |
|------|----------|-------|
| LangSmith self-hosted on AKS | Platform | Cloud LangSmith first; AKS overlays only |
| LangSmith upstream Helm chart | Platform | Custom 3-layer chart used instead |
| `staging` Helm overlay | GRC | Only local/dev/prod |
| AKS prod CD + approval gate | CI/CD | `cd-dev` only; no `cd-prod` |
| CI LangSmith eval threshold tightening | CI/CD | Parse at 0.70; tighten after baseline |
| CD auto-update Helm image tags | CI/CD | Images pushed; values.yaml not bumped in repo |
| HITL / `interrupt()` / confirm list | Product | Helm flag only |
| Cooking instructions agent | Product | Not built |
| Edamam Nutrition Analysis API | Product | Not built |
| Prompt Hub | Observability | Local files only |
| OpenAI / provider prompt caching | Performance | Full prompt sent every LLM call |
| Prompt hot-reload | DevEx | Restart required after `.md` edit |
| Annotation queues | LangSmith ops | Not configured |
| Online / production evals | LangSmith ops | Not configured |
| `helm-validate` prod matrix | CI/CD | prod lint works locally, not in workflow |
| Monolith `src/personal_shopper/graph.py` | Legacy | Removed; supervisor orchestration is canonical |

---

### 13.5 Documentation map (conversation deliverables)

| Deliverable | Path |
|-------------|------|
| Architecture & patterns | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Full inventory (this file) | [SYSTEM-INVENTORY.md](SYSTEM-INVENTORY.md) |
| Tool catalog | [TOOLS.md](TOOLS.md) |
| Agent HTTP specs | [agents/](agents/README.md) |
| Prompt files | [shared/prompts/](../shared/prompts/) |
| Image build reference | [Dockerfile.agent.md](../Dockerfile.agent.md), [§9](#container-images--base-dependencies) |
| Helm layers | [deploy/helm/LAYERS.md](../deploy/helm/LAYERS.md) |

---

## Quick reference: which file talks to what

| Consumer | Depends on |
|----------|------------|
| UI | `ui/server.py` → supervisor HTTP |
| Supervisor | `shared/*`, `tools/*`, sub-agent URLs |
| Sub-agents | `shared/state`, `shared/distributed_tracing`, `tools/*` |
| Tools | External APIs (Kroger, Edamam, Spoonacular, RapidAPI) |
| Helm | `langgraph-primitives` chart + layered values |
| CI/CD | `agents.manifest.yaml`, `build-agent-images.sh`, `langgraph-agents.py`, `.github/workflows/*`, `Dockerfile.ui` |
| Tests | All `shared/` and agent `graph` exports |

---

*Maintain this file when adding agents, tools, graph nodes, env vars, deployment paths, CI/CD workflows, or when design decisions change (update §13).*
