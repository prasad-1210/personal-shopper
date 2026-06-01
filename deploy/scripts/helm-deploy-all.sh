#!/usr/bin/env bash
# Deploy all agents in dependency order (sub-agents → supervisor → UI).
# Usage: bash deploy/scripts/helm-deploy-all.sh [environment] [namespace]

set -euo pipefail

ENV=${1:-local}
NAMESPACE=${2:-agents-dev}

AGENTS=(
  nutrition-agent
  recipe-agent
  shopping-agent
  budget-agent
  supervisor
  ui
)

local_image_repo() {
  case "$1" in
    supervisor) echo personal-shopper-supervisor ;;
    nutrition-agent) echo personal-shopper-nutrition ;;
    recipe-agent) echo personal-shopper-recipe ;;
    shopping-agent) echo personal-shopper-shopping ;;
    budget-agent) echo personal-shopper-budget ;;
    ui) echo personal-shopper-ui ;;
    *) echo "" ;;
  esac
}

for agent in "${AGENTS[@]}"; do
  echo "──────────────────────────────"
  if [[ "$ENV" == "local" ]]; then
    IMAGE_REPOSITORY="$(local_image_repo "$agent")" \
      bash deploy/scripts/helm-deploy.sh "$agent" "$ENV" "$NAMESPACE"
  else
    bash deploy/scripts/helm-deploy.sh "$agent" "$ENV" "$NAMESPACE"
  fi
  echo ""
done

echo "══════════════════════════════"
echo "All agents deployed to ${NAMESPACE}"
kubectl get pods -n "${NAMESPACE}"
