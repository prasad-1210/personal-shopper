# Helm

Layered Helm deployment: one **release per agent** in namespace `agents-dev` (local) or environment-specific namespaces on AKS.

## Charts

| Chart | Type | Purpose |
|-------|------|---------|
| [charts/k8s-primitives/](charts/k8s-primitives/) | `library` | Generic Deployment, Service, HPA, PDB, Ingress, ServiceAccount (template `define`s only) |
| [charts/langgraph-primitives/](charts/langgraph-primitives/) | `application` | LangGraph agent Deployment, ConfigMap, Redis/Postgres ExternalName, network policy |

`langgraph-primitives` depends on `k8s-primitives` and includes it for Service, HPA, PDB, ServiceAccount, and Ingress.

Build dependencies after cloning or changing chart versions:

```bash
helm dependency build deploy/helm/charts/langgraph-primitives
```

## Value layers (merge order)

Later files override earlier ones:

1. `charts/langgraph-primitives/values.yaml` — schema defaults
2. `org/values.yaml` + `org/configmap.yaml` — org-wide policy and config
3. `overlays/<env>/values.yaml` + `configmap.yaml` — `local`, `dev`, or `prod`
4. `agents/<name>/values.yaml` + `configmap.yaml` — per-agent overrides

Example install (recipe agent, local):

```bash
helm upgrade --install recipe-agent deploy/helm/charts/langgraph-primitives \
  --namespace agents-dev \
  --create-namespace \
  -f deploy/helm/org/values.yaml \
  -f deploy/helm/overlays/local/values.yaml \
  -f deploy/helm/agents/recipe-agent/values.yaml \
  -f deploy/helm/org/configmap.yaml \
  -f deploy/helm/overlays/local/configmap.yaml \
  -f deploy/helm/agents/recipe-agent/configmap.yaml
```

Prefer the wrapper: `bash deploy/scripts/helm-deploy.sh recipe-agent local`.

## Directory guide

```
helm/
├── charts/           # Platform-owned templates
├── org/              # Platform: security, resources, Redis/Postgres hostnames
├── overlays/
│   ├── local/        # Docker Desktop: pullPolicy Never, in-cluster Redis/Postgres DNS
│   ├── dev/          # AKS dev: GHCR pull, Azure Redis/Postgres FQDNs
│   └── prod/         # AKS prod: HPA, stricter availability
└── agents/
    ├── supervisor/
    ├── nutrition-agent/
    ├── recipe-agent/
    ├── shopping-agent/
    ├── budget-agent/
    └── ui/
```

Each agent folder contains:

- **`values.yaml`** — `agent.name`, `image`, `langsmith.project`, `redis.dbIndex`, `postgres.database`, `secretName`, resources
- **`configmap.yaml`** — non-secret `configMap.data` merged into the agent ConfigMap

Do not put secrets in `configmap.yaml`.

## App team checklist

1. Edit only `agents/<your-agent>/values.yaml` and `configmap.yaml`.
2. Set a unique `redis.dbIndex` and `postgres.database` (documented in values; actual URIs live in the agent secret).
3. Set `langsmith.project` per environment if needed.
4. For GHCR, set `image.repository` to `ghcr.io/<YOUR_ORG>/personal-shopper-<id>` and `image.tag` to the CI SHA or `latest`.
5. Deploy: `bash deploy/scripts/helm-deploy.sh <helm-folder-name> local`

Helm folder names use kebab-case (`nutrition-agent`); manifest ids use short names (`nutrition`).

## Validation

```bash
helm dependency build deploy/helm/charts/langgraph-primitives

helm lint deploy/helm/charts/langgraph-primitives \
  -f deploy/helm/org/values.yaml \
  -f deploy/helm/overlays/local/values.yaml \
  -f deploy/helm/agents/supervisor/values.yaml \
  -f deploy/helm/org/configmap.yaml \
  -f deploy/helm/overlays/local/configmap.yaml \
  -f deploy/helm/agents/supervisor/configmap.yaml

helm template supervisor deploy/helm/charts/langgraph-primitives \
  --namespace agents-dev \
  -f deploy/helm/org/values.yaml \
  -f deploy/helm/overlays/local/values.yaml \
  -f deploy/helm/agents/supervisor/values.yaml \
  -f deploy/helm/org/configmap.yaml \
  -f deploy/helm/overlays/local/configmap.yaml \
  -f deploy/helm/agents/supervisor/configmap.yaml
```

Full matrix runs in `.github/workflows/helm-validate.yaml`.

## Deep reference

Wolfi image constraints, secret key lists, platform vs app ownership, and adding a new agent are documented in **[LAYERS.md](LAYERS.md)**.
