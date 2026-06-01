# Helm layer model

> **Docs:** [Deploy overview](../README.md) · [Helm README](README.md) · [Scripts](../scripts/README.md)

## Three layers

| Layer | Path | Owner | Change frequency |
|-------|------|-------|------------------|
| K8s primitives | `charts/k8s-primitives/` | Platform | Rarely — K8s API / generic workload patterns |
| LangGraph primitives | `charts/langgraph-primitives/` | Platform | When LangGraph deployment patterns change |
| Org values | `org/` | Platform | Security, resource policy, backing services |
| Environment overlay | `overlays/<env>/` | Platform | Per-environment (local, dev, prod) |
| Agent values | `agents/<name>/` | App team | Every sprint |

```
deploy/helm/
├── charts/
│   ├── k8s-primitives/          # Layer 1 — library (Deployment, Service, HPA, …)
│   └── langgraph-primitives/    # Layer 2 — application chart (agents, Redis/Postgres, /ok)
├── org/                         # Layer 3a — org-wide values + configmap data
├── overlays/<env>/              # Layer 3a — environment overrides
└── agents/<name>/               # Layer 3b — per-agent values + configmap data
```

LangGraph templates **include** k8s-primitives for Service, HPA, PDB, ServiceAccount, Ingress, and optional secret reminder ConfigMap. Agent Deployment, ConfigMap, ExternalName services, and supervisor network policy stay LangGraph-specific.

## Merge order (later wins)

1. `charts/langgraph-primitives/values.yaml` (includes k8s schema via layered `-f` files)
2. `org/values.yaml`
3. `overlays/<env>/values.yaml`
4. `agents/<name>/values.yaml`
5. `org/configmap.yaml` → `configMap.data`
6. `overlays/<env>/configmap.yaml`
7. `agents/<name>/configmap.yaml`

## App team workflow

Edit only `deploy/helm/agents/<your-agent>/values.yaml` and `configmap.yaml`.

```bash
bash deploy/scripts/helm-deploy.sh recipe-agent local
bash deploy/scripts/helm-deploy-all.sh local
```

Value keys are documented in `charts/langgraph-primitives/values.yaml` and `charts/k8s-primitives/values.yaml`. Do not put secrets in configmap files — use per-agent secrets (`deploy/scripts/create-agent-secrets.sh` or `local-setup.sh`).

## Platform workflow

- Bump `k8s-primitives` when generic K8s templates change.
- Bump `langgraph-primitives` when agent wiring changes (probes, Redis DB index, inter-agent URLs).
- Keep values schema **backwards-compatible** for app teams.

```bash
helm dependency build deploy/helm/charts/langgraph-primitives
```

## Add a new agent

1. `deploy/agents.manifest.yaml` — `id`, `graphId`, `build.config`
2. `deploy/helm/agents/<helm-folder>/` — `values.yaml` + `configmap.yaml`  
   Required: `agent.name`, `agent.graphId`, `image.repository`, `langsmith.project`, unique `redis.dbIndex`, unique `postgres.database`
3. Add folder to `HELM_AGENT_DIRS` in `scripts/langgraph-agents.py` if manifest `id` ≠ folder name
4. Add to `deploy/scripts/helm-deploy-all.sh` and `.github/workflows/helm-validate.yaml`

## Image names

| Manifest `id` | Helm folder | Image repository (local tag / GHCR) |
|---------------|-------------|-------------------------------------|
| supervisor | supervisor | `personal-shopper-supervisor` or `ghcr.io/<YOUR_ORG>/personal-shopper-supervisor` |
| nutrition | nutrition-agent | `personal-shopper-nutrition` |
| recipe | recipe-agent | `personal-shopper-recipe` |
| shopping | shopping-agent | `personal-shopper-shopping` |
| budget | budget-agent | `personal-shopper-budget` |
| — | ui | `personal-shopper-ui` (Dockerfile.ui — not langgraph build) |

## LangGraph wolfi image constraints

All agent images are built with `langgraph build`, which uses
`langchain/langgraph-api:<python-version>-wolfi` as the base image (`image_distro` + `python_version` in each `langgraph.json`).

| Constraint | Value | Reason |
|---|---|---|
| `runAsNonRoot` | `false` | wolfi image runs as root |
| `runAsUser` | `0` | wolfi requirement |
| `readOnlyRootFilesystem` | `false` | wolfi writes runtime files |
| Health probe | `httpGet /ok` | wolfi has no shell for exec probes |
| Port | `8000` | langgraph-api production port |
| `REDIS_URI` | full URI in secret | not assembled in Helm templates |
| `DATABASE_URI` | full URI in secret | not assembled in Helm templates |

Do not override `command` or `args` on the Deployment — the wolfi image provides its own entrypoint.

### Required secret keys per agent

Each agent uses `<agent.name>-secrets` (see `secretName` in `agents/<name>/values.yaml`):

```
OPENAI_API_KEY
LANGSMITH_API_KEY
REDIS_URI                   (unique db index per agent)
DATABASE_URI                (unique database per agent)
LANGGRAPH_CLOUD_LICENSE_KEY (optional in dev; required for production)
KROGER_CLIENT_ID            (shopping-agent, supervisor)
KROGER_CLIENT_SECRET        (shopping-agent, supervisor)
EDAMAM_APP_ID               (recipe-agent)
EDAMAM_APP_KEY              (recipe-agent)
RAPIDAPI_KEY                (shopping-agent)
```

Local setup: `bash deploy/scripts/create-agent-secrets.sh agents-dev`

### Building images locally

```bash
langgraph build \
  --config agents/recipe_agent/langgraph.json \
  --platform linux/amd64 \
  --pull \
  -t personal-shopper-recipe:local

docker run --rm -p 8000:8000 \
  -e REDIS_URI="redis://localhost:6379/2" \
  -e DATABASE_URI="postgres://langgraph:langgraph@localhost:5432/langgraph_recipe" \
  -e LANGSMITH_API_KEY="<key>" \
  -e OPENAI_API_KEY="<key>" \
  personal-shopper-recipe:local

curl http://localhost:8000/ok
```
