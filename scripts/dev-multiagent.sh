#!/bin/bash
# Run all agents locally for multi-agent development.
# Always stops existing agents on :22000-:22004 before starting fresh.
# Usage: bash scripts/dev-multiagent.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck source=multiagent-ports.sh
source "$ROOT/scripts/multiagent-ports.sh"
source venv/bin/activate 2>/dev/null || true
# LangSmith distributed tracing: all agent processes need the same env
if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

LG="${ROOT}/venv/bin/langgraph"
if [ ! -x "$LG" ]; then
  LG="langgraph"
fi

PORTS=(
  "$MULTIAGENT_SUPERVISOR_PORT"
  "$MULTIAGENT_NUTRITION_PORT"
  "$MULTIAGENT_RECIPE_PORT"
  "$MULTIAGENT_SHOPPING_PORT"
  "$MULTIAGENT_BUDGET_PORT"
)

echo "=== Stopping any running agents ==="
bash "$ROOT/scripts/stop-multiagent.sh"
echo ""

# Each agent watches the whole repo (langgraph.json dependencies: ../..).
# Hot reload on one save restarts all agents and races in-memory .langgraph_api writes.
clear_langgraph_api_state() {
  local dir
  for dir in \
    supervisor \
    agents/nutrition_agent \
    agents/recipe_agent \
    agents/shopping_agent \
    agents/budget_agent
  do
    if [ -d "$ROOT/$dir/.langgraph_api" ]; then
      rm -rf "$ROOT/$dir/.langgraph_api"
    fi
  done
}
echo "=== Clearing per-agent .langgraph_api state ==="
clear_langgraph_api_state
echo ""

# Confirm ports are free before starting
for port in "${PORTS[@]}"; do
  if lsof -tiTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "ERROR: port ${port} still in use. Run: bash scripts/stop-multiagent.sh"
    exit 1
  fi
done

echo "=== Starting all agents ==="
echo "Supervisor: :${MULTIAGENT_SUPERVISOR_PORT} | nutrition: :${MULTIAGENT_NUTRITION_PORT} | recipe: :${MULTIAGENT_RECIPE_PORT} | shopping: :${MULTIAGENT_SHOPPING_PORT} | budget: :${MULTIAGENT_BUDGET_PORT}"
mkdir -p logs

# Default off: set LANGGRAPH_DEV_RELOAD=true to enable hot reload for a single agent workflow.
LG_DEV_RELOAD_FLAGS=(--no-reload)
if [ "${LANGGRAPH_DEV_RELOAD:-false}" = "true" ]; then
  LG_DEV_RELOAD_FLAGS=()
  echo "Note: hot reload enabled — editing shared/ may reload all agents and cause .langgraph_api races"
fi

wait_for_ok() {
  local port=$1
  local name=$2
  local tries=0
  while [ "$tries" -lt 90 ]; do
    if curl -sf "http://127.0.0.1:${port}/ok" >/dev/null 2>&1; then
      echo "  $name ready on :$port"
      return 0
    fi
    sleep 1
    tries=$((tries + 1))
  done
  echo "  ERROR: $name did not become ready on :$port (see logs/agent-${name}.log)"
  tail -15 "$ROOT/logs/agent-${name}.log" 2>/dev/null | strings || true
  return 1
}

start_agent() {
  local name=$1
  local port=$2
  local dir=$3
  echo "Starting $name on port $port..."
  (
    cd "$ROOT/$dir"
    exec "$LG" dev \
      --host 127.0.0.1 \
      --port "$port" \
      --no-browser \
      "${LG_DEV_RELOAD_FLAGS[@]}" \
      --config langgraph.json
  ) > "$ROOT/logs/agent-${name}.log" 2>&1 &
  echo $! > "$ROOT/logs/${name}.pid"
  echo "  $name PID: $!"
}

start_agent "nutrition" "$MULTIAGENT_NUTRITION_PORT" "agents/nutrition_agent"
start_agent "recipe"    "$MULTIAGENT_RECIPE_PORT"    "agents/recipe_agent"
start_agent "shopping"  "$MULTIAGENT_SHOPPING_PORT"  "agents/shopping_agent"
start_agent "budget"    "$MULTIAGENT_BUDGET_PORT"    "agents/budget_agent"

wait_for_ok "$MULTIAGENT_NUTRITION_PORT" "nutrition" || true
wait_for_ok "$MULTIAGENT_RECIPE_PORT"    "recipe"    || true
wait_for_ok "$MULTIAGENT_SHOPPING_PORT"  "shopping"  || true
wait_for_ok "$MULTIAGENT_BUDGET_PORT"    "budget"    || true

start_agent "supervisor" "$MULTIAGENT_SUPERVISOR_PORT" "supervisor"
wait_for_ok "$MULTIAGENT_SUPERVISOR_PORT" "supervisor" || true

echo ""
echo "=== Health check ==="
failed=0
curl -sf "http://127.0.0.1:${MULTIAGENT_NUTRITION_PORT}/ok" && echo " nutrition OK" || { echo " nutrition FAIL"; failed=1; }
curl -sf "http://127.0.0.1:${MULTIAGENT_RECIPE_PORT}/ok"    && echo " recipe OK"    || { echo " recipe FAIL"; failed=1; }
curl -sf "http://127.0.0.1:${MULTIAGENT_SHOPPING_PORT}/ok"  && echo " shopping OK"  || { echo " shopping FAIL"; failed=1; }
curl -sf "http://127.0.0.1:${MULTIAGENT_BUDGET_PORT}/ok"    && echo " budget OK"    || { echo " budget FAIL"; failed=1; }
curl -sf "http://127.0.0.1:${MULTIAGENT_SUPERVISOR_PORT}/ok" && echo " supervisor OK" || { echo " supervisor FAIL"; failed=1; }
echo ""
if [ "$failed" -eq 0 ]; then
  echo "All agents running."
  echo "Studio: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:${MULTIAGENT_SUPERVISOR_PORT}"
  echo "UI:     cd ui && python server.py  →  http://127.0.0.1:${MULTIAGENT_UI_PORT}"
  echo "Logs:   bash scripts/tail-multiagent-logs.sh"
  echo "Reload: restart with this script after code changes (hot reload off by default)"
else
  echo "Some agents failed — check logs/agent-*.log"
  exit 1
fi
