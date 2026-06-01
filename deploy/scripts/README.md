# Deploy scripts

Bash helpers for local Kubernetes setup and layered Helm installs. Run from the **repository root** (scripts `cd` to root automatically).

## Scripts

### `local-setup.sh`

**One-time** Docker Desktop Kubernetes bootstrap.

1. Verifies `kubectl` context is `docker-desktop`
2. Creates namespace `agents-dev` (default)
3. Installs nginx ingress controller
4. Installs Bitnami Redis and PostgreSQL in the namespace
5. Builds all agent images via `scripts/build-agent-images.sh`
6. Builds UI via `Dockerfile.ui`
7. Creates per-agent secrets via `create-agent-secrets.sh`
8. Runs `helm-deploy-all.sh local`

```bash
bash deploy/scripts/local-setup.sh
```

### `create-agent-secrets.sh`

Creates or updates Kubernetes secrets with API keys from `.env` and **per-agent** `REDIS_URI` / `DATABASE_URI` strings required by the Wolfi langgraph-api image.

| Secret name | Redis DB | Postgres database |
|-------------|----------|-------------------|
| `supervisor-secrets` | 0 | `langgraph_supervisor` |
| `nutrition-agent-secrets` | 1 | `langgraph_nutrition` |
| `recipe-agent-secrets` | 2 | `langgraph_recipe` |
| `shopping-agent-secrets` | 3 | `langgraph_shopping` |
| `budget-agent-secrets` | 4 | `langgraph_budget` |
| `ui-secrets` | — | — (API keys only) |

```bash
bash deploy/scripts/create-agent-secrets.sh [namespace]
# default namespace: agents-dev
```

Override hosts if needed:

```bash
REDIS_HOST=redis-master.agents-dev.svc.cluster.local \
PG_HOST=postgres-postgresql.agents-dev.svc.cluster.local \
  bash deploy/scripts/create-agent-secrets.sh agents-dev
```

### `helm-deploy.sh`

Deploy **one** agent release.

```bash
bash deploy/scripts/helm-deploy.sh <agent-folder> [environment] [namespace]
```

| Argument | Default | Description |
|----------|---------|-------------|
| `agent-folder` | (required) | Name under `deploy/helm/agents/` (e.g. `recipe-agent`) |
| `environment` | `local` | Overlay: `local`, `dev`, or `prod` |
| `namespace` | `agents-dev` | Kubernetes namespace |

**Environment variables**

| Variable | Effect |
|----------|--------|
| `IMAGE_REPOSITORY` | `--set image.repository=...` |
| `IMAGE_TAG` | `--set image.tag=...` |

For `environment=local`, if `IMAGE_REPOSITORY` is unset, the script maps to `personal-shopper-*` local image names.

```bash
bash deploy/scripts/helm-deploy.sh recipe-agent local
IMAGE_TAG=abc123 IMAGE_REPOSITORY=ghcr.io/myorg/personal-shopper-recipe \
  bash deploy/scripts/helm-deploy.sh recipe-agent dev agents-dev
```

### `helm-deploy-all.sh`

Deploy all agents in order: sub-agents → supervisor → UI (supervisor should start after sub-agents are routable).

```bash
bash deploy/scripts/helm-deploy-all.sh [environment] [namespace]
```

Uses the same local `IMAGE_REPOSITORY` mapping as `helm-deploy.sh` when `environment` is `local`.

## Related repo scripts

| Script | Role |
|--------|------|
| `scripts/build-agent-images.sh` | `langgraph build` for every agent in `deploy/agents.manifest.yaml` |
| `scripts/langgraph-agents.py` | Manifest helpers: `ids`, `build-specs`, `image-repos` |
| `scripts/dev-multiagent.sh` | Local dev without Kubernetes (processes on ports 22000–22005) |

## Troubleshooting

| Symptom | Check |
|---------|--------|
| `ImagePullBackOff` (local) | Images built? `docker images \| grep personal-shopper`. Overlay `local` uses `pullPolicy: Never`. |
| `CreateContainerConfigError` | Secret missing? Run `create-agent-secrets.sh`. Keys `REDIS_URI`, `DATABASE_URI` required for agents. |
| Agent crash loop, permission errors | Wolfi requires `runAsNonRoot: false` — see `deploy/helm/org/values.yaml`. |
| Supervisor cannot reach sub-agents | Inter-agent URLs in `helm/agents/supervisor/values.yaml`; sub-agent pods ready in same namespace. |
| Helm chart not found / empty templates | Run `helm dependency build deploy/helm/charts/langgraph-primitives`. |
