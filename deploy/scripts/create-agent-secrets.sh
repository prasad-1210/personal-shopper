#!/bin/bash
# Create per-agent K8s secrets with wolfi-required REDIS_URI and DATABASE_URI.
# Usage: bash deploy/scripts/create-agent-secrets.sh [namespace]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
NAMESPACE="${1:-agents-dev}"

if [[ ! -f .env ]]; then
  echo "Missing .env in repo root" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

REDIS_HOST="${REDIS_HOST:-redis-master.${NAMESPACE}.svc.cluster.local}"
PG_HOST="${PG_HOST:-postgres-postgresql.${NAMESPACE}.svc.cluster.local}"
PG_USER="${POSTGRES_USER:-langgraph}"
PG_PASS="${POSTGRES_PASSWORD:-langgraph}"

apply_secret() {
  local agent_name=$1
  local redis_db=$2
  local pg_db=$3

  kubectl create secret generic "${agent_name}-secrets" \
    --namespace "$NAMESPACE" \
    --from-literal=OPENAI_API_KEY="${OPENAI_API_KEY:-}" \
    --from-literal=LANGSMITH_API_KEY="${LANGSMITH_API_KEY:-}" \
    --from-literal=KROGER_CLIENT_ID="${KROGER_CLIENT_ID:-}" \
    --from-literal=KROGER_CLIENT_SECRET="${KROGER_CLIENT_SECRET:-}" \
    --from-literal=EDAMAM_APP_ID="${EDAMAM_APP_ID:-}" \
    --from-literal=EDAMAM_APP_KEY="${EDAMAM_APP_KEY:-}" \
    --from-literal=SPOONACULAR_API_KEY="${SPOONACULAR_API_KEY:-}" \
    --from-literal=RAPIDAPI_KEY="${RAPIDAPI_KEY:-}" \
    --from-literal=REDIS_URI="redis://${REDIS_HOST}:6379/${redis_db}" \
    --from-literal=DATABASE_URI="postgres://${PG_USER}:${PG_PASS}@${PG_HOST}:5432/${pg_db}" \
    --from-literal=LANGGRAPH_CLOUD_LICENSE_KEY="${LANGGRAPH_CLOUD_LICENSE_KEY:-}" \
    --dry-run=client -o yaml | kubectl apply -f -
  echo "    ${agent_name}-secrets"
}

echo "==> Applying per-agent secrets in ${NAMESPACE}..."
apply_secret supervisor 0 langgraph_supervisor
apply_secret nutrition-agent 1 langgraph_nutrition
apply_secret recipe-agent 2 langgraph_recipe
apply_secret shopping-agent 3 langgraph_shopping
apply_secret budget-agent 4 langgraph_budget

kubectl create secret generic ui-secrets \
  --namespace "$NAMESPACE" \
  --from-literal=OPENAI_API_KEY="${OPENAI_API_KEY:-}" \
  --from-literal=LANGSMITH_API_KEY="${LANGSMITH_API_KEY:-}" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "    ui-secrets"

echo "    Done."
