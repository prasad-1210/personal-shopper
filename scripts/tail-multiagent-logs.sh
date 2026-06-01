#!/bin/bash
# Tail all multi-agent langgraph dev logs in one console (prefixed by agent name).
# Usage: bash scripts/tail-multiagent-logs.sh [-n LINES]
#   -n 0   only new lines (default)
#   -n 50  include last 50 lines per agent, then follow

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT/logs"
LINES=0

while getopts ":n:h" opt; do
  case "$opt" in
    n) LINES="$OPTARG" ;;
    h)
      echo "Usage: $0 [-n LINES]"
      echo "  Tails logs/agent-{supervisor,nutrition,recipe,shopping,budget}.log"
      exit 0
      ;;
    *)
      echo "Unknown option: -$OPTARG" >&2
      exit 1
      ;;
  esac
done

AGENTS=(supervisor nutrition recipe shopping budget)

mkdir -p "$LOG_DIR"
missing=0
for name in "${AGENTS[@]}"; do
  log="$LOG_DIR/agent-${name}.log"
  if [ ! -f "$log" ]; then
    touch "$log"
    missing=$((missing + 1))
  fi
done

if [ "$missing" -gt 0 ]; then
  echo "Note: some log files were empty/missing (start agents with: bash scripts/dev-multiagent.sh)"
fi

echo "=== Combined agent logs (Ctrl+C to exit) ==="
printf '  '
printf '%s ' "${AGENTS[@]}"
echo ""
echo ""

pids=()
cleanup() {
  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  exit 0
}
trap cleanup INT TERM

for name in "${AGENTS[@]}"; do
  log="$LOG_DIR/agent-${name}.log"
  (
    exec tail -n "$LINES" -F "$log" 2>/dev/null
  ) | while IFS= read -r line || [ -n "$line" ]; do
    printf '[%-10s] %s\n' "$name" "$line"
  done &
  pids+=("$!")
done

wait
