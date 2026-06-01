#!/bin/bash
# Quick health check for all multi-agent servers
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=multiagent-ports.sh
source "$ROOT/scripts/multiagent-ports.sh"
for port in \
  "$MULTIAGENT_NUTRITION_PORT" \
  "$MULTIAGENT_RECIPE_PORT" \
  "$MULTIAGENT_SHOPPING_PORT" \
  "$MULTIAGENT_BUDGET_PORT" \
  "$MULTIAGENT_SUPERVISOR_PORT"
do
  if curl -sf "http://127.0.0.1:${port}/ok" >/dev/null; then
    echo "OK   :$port"
  else
    echo "FAIL :$port"
  fi
done
