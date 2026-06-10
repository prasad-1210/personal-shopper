# Personal Shopper Agent

LangGraph agent + FastAPI UI. Recipes via Edamam. 
Live store inventory via Kroger API. Traces to LangSmith Cloud.

**Architecture (agents, graphs, design decisions):** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — keep this updated when you change the system.

**Agent integration specs (external HTTP API):** [docs/agents/README.md](docs/agents/README.md) · [API contract](docs/agents/API-CONTRACT.md) · [Tools](docs/TOOLS.md)

**Full system inventory (files, functions, integration, env):** [docs/SYSTEM-INVENTORY.md](docs/SYSTEM-INVENTORY.md)

---

## Prerequisites

| Tool | Purpose | Install |
|---|---|---|
| Docker Desktop | Container runtime + Kubernetes | docker.com/products/docker-desktop |
| Helm | Kubernetes package manager | `brew install helm` |
| Python 3.12 | Local dev | `brew install python@3.12` |
| langgraph-cli | Build + dev server | `pip install "langgraph-cli[inmem]"` |

Enable Kubernetes in Docker Desktop:
**Settings → Kubernetes → Enable Kubernetes → Apply & Restart**

---

## Path 1 — Local dev (fastest, no Docker)

```bash
cp .env.example .env   # fill in API keys
pip install -e ".[dev]"

# Terminal 1 — all agents (supervisor :22000, sub-agents :22001–:22004)
bash scripts/dev-multiagent.sh
# Studio: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:22000

# Terminal 2 — UI
cd ui && cp .env.example .env
# set LANGGRAPH_URL=http://127.0.0.1:22000
pip install -r requirements.txt
python server.py        # runs on port 22005
```

Open http://localhost:22005

---

## Path 2 — Docker Compose (production image, local)

```bash
# Build per-agent images (optional — compose uses langgraph dev by default)
bash scripts/build-agent-images.sh

# Start everything
docker compose up

# Open http://localhost:22005
```

Spins up Redis + PostgreSQL automatically alongside the agent and UI.

---

## Path 3 — Docker Desktop Kubernetes (mirrors AKS)

```bash
# One-time setup (namespace agents-local)
bash deploy/scripts/local-k8s-setup.sh
bash deploy/scripts/local-k8s-status.sh

# Open http://localhost:8080 (UI port-forward from setup script)
```

---

## Helm layer model

Deployment docs: **[deploy/README.md](deploy/README.md)** (overview, secrets, CI). Helm details: [deploy/helm/README.md](deploy/helm/README.md) and [deploy/helm/LAYERS.md](deploy/helm/LAYERS.md):

| Layer | Path | Owner |
|---|---|---|
| Chart | `deploy/helm/charts/langgraph-primitives/` | Platform |
| Org + env | `deploy/helm/org/`, `overlays/<env>/` | Platform |
| Per agent | `deploy/helm/agents/<name>/` | App team |

```bash
bash deploy/scripts/helm-deploy.sh recipe-agent local
bash deploy/scripts/helm-deploy-all.sh local
```

Upgrade workflow: change image tag → `helm upgrade` → done.

---

## Required API keys

| Key | Free tier | Register at |
|---|---|---|
| `LANGSMITH_API_KEY` | Yes | smith.langchain.com |
| `OPENAI_API_KEY` | Pay-as-you-go | platform.openai.com |
| `KROGER_CLIENT_ID/SECRET` | Yes | developer.kroger.com |
| `EDAMAM_APP_ID/KEY` | 10k req/month | developer.edamam.com |

---

## CI/CD

| Workflow | Trigger | Does |
|---|---|---|
| `ci.yaml` | Every PR | Lint, unit tests, graph import, docker build, helm lint |
| `cd-dev.yaml` | Push to develop | Builds images, pushes to GHCR |

---

## Deployment progression

```
dev-multiagent.sh      → local inner loop (supervisor :22000)
docker compose         → local production image test (UI port 22005)
Docker Desktop K8s     → local AKS simulation (agents-local)
AKS dev namespace      → shared dev environment (same Helm chart)
AKS prod namespace     → production (same Helm chart, different values)
```

Only env vars and values files change between environments.
Code and Helm templates are identical across all stages.
