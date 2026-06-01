# Deploy

Kubernetes deployment for the personal-shopper multi-agent system: one Helm release per agent (supervisor, four sub-agents, UI), backed by Redis and PostgreSQL.

## Layout

```
deploy/
├── README.md                 ← you are here
├── agents.manifest.yaml      # Build registry (langgraph.json paths, graph IDs)
├── helm/                     # Layered Helm charts and values — see helm/README.md
│   ├── LAYERS.md             # Deep reference: layers, wolfi, secrets, ownership
│   ├── charts/
│   │   ├── k8s-primitives/       # Layer 1 — generic K8s library chart
│   │   └── langgraph-primitives/ # Layer 2 — LangGraph agent application chart
│   ├── org/                  # Org-wide values + configmap data (platform)
│   ├── overlays/             # local | dev | prod environment overrides
│   └── agents/               # Per-agent values + configmap (app teams)
└── scripts/                  # Local setup and Helm deploy helpers — see scripts/README.md
```

## Prerequisites

| Tool | Purpose |
|------|---------|
| [kubectl](https://kubernetes.io/docs/tasks/tools/) | Cluster access |
| [Helm 3](https://helm.sh/docs/intro/install/) | Chart install |
| [Docker](https://docs.docker.com/get-docker/) | Image build / local cluster |
| [langgraph-cli](https://pypi.org/project/langgraph-cli/) | `langgraph build` for agent images |
| `.env` in repo root | API keys and local dev config |

For **Docker Desktop Kubernetes** (Path 3 in the root README), enable Kubernetes in Docker Desktop and confirm `kubectl config current-context` is `docker-desktop`.

## Quick start (local cluster)

One command installs ingress, Redis, PostgreSQL, builds images, creates secrets, and deploys all agents:

```bash
bash deploy/scripts/local-setup.sh
```

Then open **http://localhost** (ingress) or port-forward the UI:

```bash
kubectl port-forward svc/ui 22005:22005 -n agents-dev
```

### Manual steps

If you prefer to run pieces yourself:

```bash
# 1. Build agent images (wolfi via langgraph build)
pip install "langgraph-cli>=0.2.11"
bash scripts/build-agent-images.sh --tag latest

# 2. Build UI (standard Docker — not langgraph)
docker build -t personal-shopper-ui:latest -f Dockerfile.ui .

# 3. Per-agent secrets (REDIS_URI, DATABASE_URI, API keys)
bash deploy/scripts/create-agent-secrets.sh agents-dev

# 4. Deploy all agents
bash deploy/scripts/helm-deploy-all.sh local agents-dev
```

Deploy a single agent:

```bash
bash deploy/scripts/helm-deploy.sh recipe-agent local
```

## Agent registry

`agents.manifest.yaml` is the canonical list of LangGraph agents for **CI image builds** and tooling (`scripts/langgraph-agents.py`). Helm deployment uses folders under `helm/agents/<name>/` (names may differ from manifest `id` — see `HELM_AGENT_DIRS` in `langgraph-agents.py`).

| Manifest `id` | Helm folder | LangGraph config |
|---------------|-------------|------------------|
| supervisor | `supervisor` | `supervisor/langgraph.json` |
| nutrition | `nutrition-agent` | `agents/nutrition_agent/langgraph.json` |
| recipe | `recipe-agent` | `agents/recipe_agent/langgraph.json` |
| shopping | `shopping-agent` | `agents/shopping_agent/langgraph.json` |
| budget | `budget-agent` | `agents/budget_agent/langgraph.json` |
| — | `ui` | `Dockerfile.ui` (not in manifest) |

## Images

**Agents** are built with `langgraph build` (Wolfi base: `langchain/langgraph-api:3.12-wolfi`). Each `langgraph.json` sets `image_distro: wolfi` and `python_version: 3.12`.

```bash
langgraph build \
  --config agents/recipe_agent/langgraph.json \
  --platform linux/amd64 \
  --pull \
  -t personal-shopper-recipe:latest
```

**UI** uses `Dockerfile.ui` and listens on port **22005**.

| Environment | Image repository in values | Local override |
|-------------|---------------------------|----------------|
| AKS / GHCR | `ghcr.io/<YOUR_ORG>/personal-shopper-*` in `helm/agents/*/values.yaml` | — |
| Local K8s | Same in values file | `helm-deploy.sh` sets `personal-shopper-*` when overlay is `local` |

Override explicitly:

```bash
IMAGE_REPOSITORY=personal-shopper-recipe IMAGE_TAG=ci \
  bash deploy/scripts/helm-deploy.sh recipe-agent local
```

## Secrets

Wolfi agent images require **full connection strings** in Kubernetes secrets (not assembled by Helm):

- `REDIS_URI` — unique Redis DB index per agent (0–4)
- `DATABASE_URI` — unique Postgres database per agent
- `LANGSMITH_API_KEY`, `OPENAI_API_KEY`, plus retailer keys as needed

Each release uses `secretName: <agent-name>-secrets` (e.g. `recipe-agent-secrets`). See [helm/LAYERS.md](helm/LAYERS.md#langgraph-wolfi-image-constraints) for the full key list.

```bash
bash deploy/scripts/create-agent-secrets.sh agents-dev
```

## Who changes what

| Area | Owner | Examples |
|------|-------|----------|
| `helm/charts/*` | Platform | Templates, probes, ExternalName services |
| `helm/org/`, `helm/overlays/` | Platform | Resources, security context, backing service hosts |
| `helm/agents/<name>/` | App team | Image tag, LangSmith project, agent configmap |
| `agents.manifest.yaml` | Platform + app | New agent registration |
| `deploy/scripts/` | Platform | Setup and deploy automation |

App teams should only edit `helm/agents/<their-agent>/values.yaml` and `configmap.yaml`.

## CI/CD

| Workflow | Trigger | Role |
|----------|---------|------|
| `.github/workflows/ci.yaml` | PR / push | Lint, tests, `langgraph build`, Helm template |
| `.github/workflows/cd-dev.yaml` | push to `develop` / `master` | Build and push images to GHCR |
| `.github/workflows/helm-validate.yaml` | PR touching `deploy/helm/**` | Matrix lint/template all agents × local/dev |

Before Helm in CI:

```bash
helm dependency build deploy/helm/charts/langgraph-primitives
```

## Further reading

- [helm/README.md](helm/README.md) — chart structure and value merge order
- [helm/LAYERS.md](helm/LAYERS.md) — layer model, wolfi constraints, adding agents
- [scripts/README.md](scripts/README.md) — script reference
- [../Dockerfile.agent.md](../Dockerfile.agent.md) — notes on agent image layout (if present)
