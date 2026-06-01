#!/bin/bash
# Stop all multi-agent langgraph dev servers (ports 22000-22004).
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck source=multiagent-ports.sh
source "$ROOT/scripts/multiagent-ports.sh"

PORTS=(
  "$MULTIAGENT_SUPERVISOR_PORT"
  "$MULTIAGENT_NUTRITION_PORT"
  "$MULTIAGENT_RECIPE_PORT"
  "$MULTIAGENT_SHOPPING_PORT"
  "$MULTIAGENT_BUDGET_PORT"
)
NAMES=(supervisor nutrition recipe shopping budget)

echo "Stopping all agents (ports ${PORTS[*]})..."

# 1. Kill PIDs recorded by dev-multiagent.sh
if [ -d logs ]; then
  for pidfile in logs/*.pid; do
    [ -f "$pidfile" ] || continue
    pid=$(cat "$pidfile")
    if kill -0 "$pid" 2>/dev/null; then
      echo "  kill PID $pid ($(basename "$pidfile" .pid))"
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "$pidfile"
  done
fi

sleep 1

# 2. Free ports (catches orphaned langgraph/uvicorn children)
kill_port() {
  local port=$1
  local name=$2
  local pids
  pids=$(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)
  if [ -z "$pids" ]; then
    return 0
  fi
  echo "  freeing :${port} (${name}) — PID(s): ${pids//$'\n'/ }"
  echo "$pids" | xargs kill 2>/dev/null || true
  sleep 0.5
  pids=$(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "$pids" | xargs kill -9 2>/dev/null || true
  fi
}

for i in "${!PORTS[@]}"; do
  kill_port "${PORTS[$i]}" "${NAMES[$i]}"
done

sleep 0.5
echo "Done."
