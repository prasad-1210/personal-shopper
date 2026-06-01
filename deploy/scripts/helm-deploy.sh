#!/usr/bin/env bash
# Deploy one agent with layered Helm values.
# Usage: bash deploy/scripts/helm-deploy.sh <agent-name> [environment] [namespace]
# Example: bash deploy/scripts/helm-deploy.sh recipe-agent local

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

AGENT=${1:?"Usage: $0 <agent-name> [environment] [namespace]"}
ENV=${2:-local}
NAMESPACE=${3:-agents-dev}
CHART_DIR="deploy/helm/charts/langgraph-primitives"

AGENT_DIR="deploy/helm/agents/${AGENT}"
if [[ ! -d "$AGENT_DIR" ]]; then
  echo "Unknown agent: $AGENT (no $AGENT_DIR)" >&2
  exit 1
fi

if [[ "$ENV" == "local" && -z "${IMAGE_REPOSITORY:-}" ]]; then
  case "$AGENT" in
    supervisor) IMAGE_REPOSITORY=personal-shopper-supervisor ;;
    nutrition-agent) IMAGE_REPOSITORY=personal-shopper-nutrition ;;
    recipe-agent) IMAGE_REPOSITORY=personal-shopper-recipe ;;
    shopping-agent) IMAGE_REPOSITORY=personal-shopper-shopping ;;
    budget-agent) IMAGE_REPOSITORY=personal-shopper-budget ;;
    ui) IMAGE_REPOSITORY=personal-shopper-ui ;;
  esac
  export IMAGE_REPOSITORY
fi

EXTRA_SET=()
if [[ -n "${IMAGE_TAG:-}" ]]; then
  EXTRA_SET+=(--set "image.tag=${IMAGE_TAG}")
fi
if [[ -n "${IMAGE_REPOSITORY:-}" ]]; then
  EXTRA_SET+=(--set "image.repository=${IMAGE_REPOSITORY}")
fi

echo "Deploying ${AGENT} → namespace ${NAMESPACE} (env overlay: ${ENV})"
helm upgrade --install "${AGENT}" "${CHART_DIR}" \
  --namespace "${NAMESPACE}" \
  --create-namespace \
  -f deploy/helm/org/values.yaml \
  -f "deploy/helm/overlays/${ENV}/values.yaml" \
  -f "${AGENT_DIR}/values.yaml" \
  -f deploy/helm/org/configmap.yaml \
  -f "deploy/helm/overlays/${ENV}/configmap.yaml" \
  -f "${AGENT_DIR}/configmap.yaml" \
  "${EXTRA_SET[@]}" \
  --wait --timeout 120s

echo "✅ ${AGENT} deployed"
kubectl get pods -n "${NAMESPACE}" -l "app.kubernetes.io/name=${AGENT}" 2>/dev/null || true
