#!/usr/bin/env bash
# Status for local Kubernetes deployment (namespace: agents-local).
set -euo pipefail

NAMESPACE="agents-local"
BLUE='\033[0;34m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}═══ Pods ══════════════════════════════════════════════${NC}"
kubectl get pods -n "$NAMESPACE" -o wide 2>/dev/null || echo "Namespace $NAMESPACE not found"

echo ""
echo -e "${BLUE}═══ Services ══════════════════════════════════════════${NC}"
kubectl get services -n "$NAMESPACE" 2>/dev/null || true

echo ""
echo -e "${BLUE}═══ Health (port-forwards must be running) ═════════════${NC}"
check() {
  local name=$1 port=$2 path=$3
  if curl -sf "http://127.0.0.1:${port}/${path}" >/dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} $name (127.0.0.1:$port/$path)"
  else
    echo -e "  ${RED}✗${NC} $name (127.0.0.1:$port/$path)"
  fi
}
check nutrition-agent 8001 ok
check recipe-agent 8002 ok
check shopping-agent 8003 ok
check budget-agent 8004 ok
check supervisor 8000 ok
check ui 8080 health

echo ""
echo -e "${BLUE}═══ Recent warnings ═══════════════════════════════════${NC}"
kubectl get events -n "$NAMESPACE" \
  --sort-by='.lastTimestamp' \
  --field-selector type=Warning 2>/dev/null | tail -10 || true
