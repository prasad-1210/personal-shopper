#!/usr/bin/env bash
# Deploy personal-shopper full stack to Docker Desktop Kubernetes (namespace: agents-local).
# Idempotent — safe to re-run.
#
# Usage: bash deploy/scripts/local-k8s-setup.sh
# Teardown: bash deploy/scripts/local-k8s-teardown.sh
set -euo pipefail

NAMESPACE="agents-local"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
CHART_DIR="$ROOT_DIR/deploy/helm/charts/langgraph-primitives"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${BLUE}[setup]${NC} $*"; }
ok()   { echo -e "${GREEN}[ok]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
fail() { echo -e "${RED}[fail]${NC} $*"; exit 1; }

# Helm folder name → local Docker image repository (no tag)
local_image_repo() {
  case "$1" in
    supervisor) echo personal-shopper-supervisor ;;
    nutrition-agent) echo personal-shopper-nutrition ;;
    recipe-agent) echo personal-shopper-recipe ;;
    shopping-agent) echo personal-shopper-shopping ;;
    budget-agent) echo personal-shopper-budget ;;
    ui) echo personal-shopper-ui ;;
    *) fail "Unknown agent: $1" ;;
  esac
}

deploy_agent() {
  local agent=$1
  shift
  local repo
  repo="$(local_image_repo "$agent")"
  log "  Deploying $agent (image: ${repo}:local)..."
  helm upgrade --install "$agent" "$CHART_DIR" \
    --namespace "$NAMESPACE" \
    -f "$ROOT_DIR/deploy/helm/org/values.yaml" \
    -f "$ROOT_DIR/deploy/helm/overlays/local/values.yaml" \
    -f "$ROOT_DIR/deploy/helm/agents/${agent}/values.yaml" \
    -f "$ROOT_DIR/deploy/helm/org/configmap.yaml" \
    -f "$ROOT_DIR/deploy/helm/overlays/local/configmap.yaml" \
    -f "$ROOT_DIR/deploy/helm/agents/${agent}/configmap.yaml" \
    --set "image.repository=${repo}" \
    --set "image.tag=local" \
    --set "image.pullPolicy=Never" \
    --set "secretName=${agent}-secrets" \
    "$@" \
    --wait --timeout 180s
  ok "  $agent deployed"
}

create_postgres_databases() {
  log "Creating per-agent Postgres databases..."
  kubectl delete job pg-init-databases -n "$NAMESPACE" --ignore-not-found >/dev/null 2>&1 || true
  cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: pg-init-databases
  namespace: ${NAMESPACE}
spec:
  ttlSecondsAfterFinished: 120
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: psql
          image: postgres:16
          env:
            - name: PGPASSWORD
              value: langgraph
          command:
            - /bin/bash
            - -ec
            - |
              host="${PG_HOST}"
              for db in langgraph_supervisor langgraph_nutrition langgraph_recipe langgraph_shopping langgraph_budget; do
                exists=\$(psql -h "\$host" -U langgraph -d langgraph -tAc "SELECT 1 FROM pg_database WHERE datname='\${db}'")
                if [[ "\$exists" != "1" ]]; then
                  psql -h "\$host" -U langgraph -d langgraph -c "CREATE DATABASE \${db};"
                  echo "created \${db}"
                else
                  echo "exists \${db}"
                fi
              done
EOF
  if kubectl wait --for=condition=complete "job/pg-init-databases" -n "$NAMESPACE" --timeout=120s; then
    ok "Databases ready"
  else
    warn "pg-init-databases did not complete in time — check: kubectl logs job/pg-init-databases -n $NAMESPACE"
  fi
}

start_port_forwards() {
  log "Setting up port forwards..."
  pkill -f "kubectl port-forward.*${NAMESPACE}" 2>/dev/null || true
  for f in /tmp/pf-*.pid; do
    [[ -f "$f" ]] && kill "$(cat "$f")" 2>/dev/null || true
    rm -f "$f"
  done
  sleep 1

  kubectl port-forward -n "$NAMESPACE" svc/supervisor 8000:8000 >/tmp/pf-supervisor.log 2>&1 &
  echo $! >/tmp/pf-supervisor.pid

  kubectl port-forward -n "$NAMESPACE" svc/ui 8080:8080 >/tmp/pf-ui.log 2>&1 &
  echo $! >/tmp/pf-ui.pid

  kubectl port-forward -n "$NAMESPACE" svc/nutrition-agent 8001:8000 >/tmp/pf-nutrition-agent.log 2>&1 &
  echo $! >/tmp/pf-nutrition-agent.pid
  kubectl port-forward -n "$NAMESPACE" svc/recipe-agent 8002:8000 >/tmp/pf-recipe-agent.log 2>&1 &
  echo $! >/tmp/pf-recipe-agent.pid
  kubectl port-forward -n "$NAMESPACE" svc/shopping-agent 8003:8000 >/tmp/pf-shopping-agent.log 2>&1 &
  echo $! >/tmp/pf-shopping-agent.pid
  kubectl port-forward -n "$NAMESPACE" svc/budget-agent 8004:8000 >/tmp/pf-budget-agent.log 2>&1 &
  echo $! >/tmp/pf-budget-agent.pid

  sleep 3
  ok "Port forwards started"
}

health_check() {
  local name=$1
  local url=$2
  local max_attempts=${3:-12}
  local attempt=0
  while (( attempt < max_attempts )); do
    if curl -sf "$url" >/dev/null 2>&1; then
      ok "  $name — healthy"
      return 0
    fi
    attempt=$((attempt + 1))
    sleep 3
  done
  warn "  $name — not responding at $url"
  return 1
}

# ── 0. Prerequisites ───────────────────────────────────────────────────────
log "Checking prerequisites..."
command -v kubectl >/dev/null 2>&1 || fail "kubectl not found"
command -v helm >/dev/null 2>&1 || fail "helm not found"
command -v docker >/dev/null 2>&1 || fail "docker not found"
command -v langgraph >/dev/null 2>&1 || fail "langgraph CLI not found — pip install 'langgraph-cli>=0.2.11'"

CONTEXT="$(kubectl config current-context)"
if [[ "$CONTEXT" != "docker-desktop" ]]; then
  warn "kubectl context is '$CONTEXT' (expected docker-desktop)"
  if [[ -t 0 ]]; then
    read -rp "Continue anyway? [y/N] " yn
    [[ "$yn" =~ ^[Yy]$ ]] || exit 1
  else
    warn "Non-interactive — continuing"
  fi
fi
kubectl cluster-info >/dev/null 2>&1 || fail "Cannot reach Kubernetes cluster"
ok "Prerequisites OK (context: $CONTEXT)"

# ── 1. Namespace ───────────────────────────────────────────────────────────
log "Creating namespace $NAMESPACE..."
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
kubectl label namespace "$NAMESPACE" \
  kubernetes.io/metadata.name="$NAMESPACE" \
  app.kubernetes.io/managed-by=local-k8s-setup \
  --overwrite
ok "Namespace ready"

# ── 2. .env ─────────────────────────────────────────────────────────────────
ENV_FILE="$ROOT_DIR/.env"
[[ -f "$ENV_FILE" ]] || fail ".env not found — copy .env.example and fill in values"
log "Loading $ENV_FILE..."
set -a
# shellcheck disable=SC1091
source "$ENV_FILE"
set +a
ok ".env loaded"

# ── 3. Helm repos ───────────────────────────────────────────────────────────
log "Adding Helm repos..."
helm repo add bitnami https://charts.bitnami.com/bitnami 2>/dev/null || true
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx 2>/dev/null || true
helm repo update
ok "Helm repos ready"

# ── 4. Redis ────────────────────────────────────────────────────────────────
log "Deploying Redis..."
helm upgrade --install redis bitnami/redis \
  --namespace "$NAMESPACE" \
  --set auth.enabled=false \
  --set architecture=standalone \
  --set master.persistence.enabled=false \
  --wait --timeout 120s
REDIS_HOST="redis-master.${NAMESPACE}.svc.cluster.local"
ok "Redis ready ($REDIS_HOST)"

# ── 5. PostgreSQL ───────────────────────────────────────────────────────────
log "Deploying PostgreSQL..."
helm upgrade --install postgres bitnami/postgresql \
  --namespace "$NAMESPACE" \
  --set auth.username=langgraph \
  --set auth.password=langgraph \
  --set auth.database=langgraph \
  --set primary.persistence.enabled=false \
  --wait --timeout 120s
PG_HOST="postgres-postgresql.${NAMESPACE}.svc.cluster.local"
ok "PostgreSQL ready ($PG_HOST)"

export PG_HOST REDIS_HOST
create_postgres_databases

# ── 6. Build images ─────────────────────────────────────────────────────────
log "Building agent images (langgraph build / wolfi)..."
cd "$ROOT_DIR"

BUILD_SPECS=(
  "supervisor|supervisor/langgraph.json"
  "nutrition-agent|agents/nutrition_agent/langgraph.json"
  "recipe-agent|agents/recipe_agent/langgraph.json"
  "shopping-agent|agents/shopping_agent/langgraph.json"
  "budget-agent|agents/budget_agent/langgraph.json"
)

for spec in "${BUILD_SPECS[@]}"; do
  agent="${spec%%|*}"
  config="${spec#*|}"
  repo="$(local_image_repo "$agent")"
  image="${repo}:local"
  log "  langgraph build → $image ($config)"
  langgraph build \
    -c "$config" \
    --platform linux/amd64 \
    --pull \
    -t "$image"
  ok "  Built $image"
done

log "Building UI image..."
docker build -f Dockerfile.ui -t personal-shopper-ui:local "$ROOT_DIR"
ok "Built personal-shopper-ui:local"

log "Verifying local images..."
for agent in supervisor nutrition-agent recipe-agent shopping-agent budget-agent ui; do
  repo="$(local_image_repo "$agent")"
  docker image inspect "${repo}:local" >/dev/null 2>&1 \
    || fail "Missing image ${repo}:local"
  ok "  ${repo}:local"
done

# ── 7. Ingress controller ───────────────────────────────────────────────────
log "Installing nginx ingress..."
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx \
  --create-namespace \
  --set controller.service.type=NodePort \
  --set controller.hostPort.enabled=true \
  --wait --timeout 180s
ok "Ingress ready"

# ── 8. Secrets ──────────────────────────────────────────────────────────────
log "Creating secrets..."
for var in OPENAI_API_KEY LANGSMITH_API_KEY KROGER_CLIENT_ID KROGER_CLIENT_SECRET EDAMAM_APP_ID EDAMAM_APP_KEY RAPIDAPI_KEY; do
  if [[ -z "${!var:-}" ]]; then
    warn "$var is not set in .env"
  fi
done
bash "$SCRIPT_DIR/create-agent-secrets.sh" "$NAMESPACE"
ok "Secrets ready"

# ── 9. Helm dependencies ────────────────────────────────────────────────────
log "Building chart dependencies..."
helm dependency build "$ROOT_DIR/deploy/helm/charts/langgraph-primitives"
ok "Chart dependencies ready"

# ── 10. Deploy agents ───────────────────────────────────────────────────────
log "Deploying sub-agents..."
deploy_agent nutrition-agent
deploy_agent recipe-agent
deploy_agent shopping-agent
deploy_agent budget-agent

log "Deploying supervisor..."
helm upgrade --install supervisor "$CHART_DIR" \
  --namespace "$NAMESPACE" \
  -f "$ROOT_DIR/deploy/helm/org/values.yaml" \
  -f "$ROOT_DIR/deploy/helm/overlays/local/values.yaml" \
  -f "$ROOT_DIR/deploy/helm/agents/supervisor/values.yaml" \
  -f "$ROOT_DIR/deploy/helm/org/configmap.yaml" \
  -f "$ROOT_DIR/deploy/helm/overlays/local/configmap.yaml" \
  -f "$ROOT_DIR/deploy/helm/agents/supervisor/configmap.yaml" \
  --set "image.repository=personal-shopper-supervisor" \
  --set "image.tag=local" \
  --set "image.pullPolicy=Never" \
  --set "secretName=supervisor-secrets" \
  --set "interAgent.nutritionAgentUrl=http://nutrition-agent.${NAMESPACE}.svc.cluster.local:8000" \
  --set "interAgent.recipeAgentUrl=http://recipe-agent.${NAMESPACE}.svc.cluster.local:8000" \
  --set "interAgent.shoppingAgentUrl=http://shopping-agent.${NAMESPACE}.svc.cluster.local:8000" \
  --set "interAgent.budgetAgentUrl=http://budget-agent.${NAMESPACE}.svc.cluster.local:8000" \
  --wait --timeout 180s
ok "Supervisor deployed"

log "Deploying UI..."
helm upgrade --install ui "$CHART_DIR" \
  --namespace "$NAMESPACE" \
  -f "$ROOT_DIR/deploy/helm/org/values.yaml" \
  -f "$ROOT_DIR/deploy/helm/overlays/local/values.yaml" \
  -f "$ROOT_DIR/deploy/helm/agents/ui/values.yaml" \
  -f "$ROOT_DIR/deploy/helm/org/configmap.yaml" \
  -f "$ROOT_DIR/deploy/helm/overlays/local/configmap.yaml" \
  -f "$ROOT_DIR/deploy/helm/agents/ui/configmap.yaml" \
  --set "image.repository=personal-shopper-ui" \
  --set "image.tag=local" \
  --set "image.pullPolicy=Never" \
  --set "secretName=ui-secrets" \
  --set "agent.port=8080" \
  --set "interAgent.supervisorUrl=http://supervisor.${NAMESPACE}.svc.cluster.local:8000" \
  --set "ingress.enabled=true" \
  --set "ingress.hosts[0].host=personal-shopper.local" \
  --set "ingress.hosts[0].paths[0].path=/" \
  --set "ingress.hosts[0].paths[0].pathType=Prefix" \
  --wait --timeout 180s
ok "UI deployed"

# ── 11. Port forwards & health ──────────────────────────────────────────────
start_port_forwards

log "Running health checks..."
ALL_OK=true
health_check "nutrition-agent" "http://127.0.0.1:8001/ok" || ALL_OK=false
health_check "recipe-agent" "http://127.0.0.1:8002/ok" || ALL_OK=false
health_check "shopping-agent" "http://127.0.0.1:8003/ok" || ALL_OK=false
health_check "budget-agent" "http://127.0.0.1:8004/ok" || ALL_OK=false
health_check "supervisor" "http://127.0.0.1:8000/ok" || ALL_OK=false
health_check "ui" "http://127.0.0.1:8080/health" || ALL_OK=false

echo ""
echo "═══════════════════════════════════════════════════════════"
if $ALL_OK; then
  ok "DEPLOYMENT COMPLETE — all services healthy"
else
  warn "DEPLOYMENT COMPLETE — some services still starting (run: bash deploy/scripts/local-k8s-status.sh)"
fi
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "  UI:                  http://127.0.0.1:8080"
echo "  Supervisor (Studio): http://127.0.0.1:8000"
echo "  Sub-agents:          :8001 – :8004"
echo ""
echo "  LangGraph Studio:"
echo "    https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:8000"
echo ""
echo "  Namespace: $NAMESPACE"
echo ""
echo "  kubectl get pods -n $NAMESPACE"
echo "  bash deploy/scripts/local-k8s-status.sh"
echo "  bash deploy/scripts/local-k8s-teardown.sh"
echo ""
