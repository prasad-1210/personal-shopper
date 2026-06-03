#!/usr/bin/env bash
# Tear down local Docker Desktop Kubernetes deployment (namespace: agents-local).
set -euo pipefail

NAMESPACE="agents-local"
BLUE='\033[0;34m'
GREEN='\033[0;32m'
NC='\033[0m'
log() { echo -e "${BLUE}[teardown]${NC} $*"; }
ok()  { echo -e "${GREEN}[ok]${NC} $*"; }

log "Stopping port forwards..."
pkill -f "kubectl port-forward.*${NAMESPACE}" 2>/dev/null || true
for f in /tmp/pf-*.pid; do
  [[ -f "$f" ]] && kill "$(cat "$f")" 2>/dev/null || true
  rm -f "$f"
done
ok "Port forwards stopped"

log "Removing agent Helm releases..."
for release in ui supervisor budget-agent shopping-agent recipe-agent nutrition-agent; do
  if helm uninstall "$release" --namespace "$NAMESPACE" 2>/dev/null; then
    ok "  Removed $release"
  else
    log "  $release not installed — skipping"
  fi
done

log "Removing backing services..."
helm uninstall redis --namespace "$NAMESPACE" 2>/dev/null || true
helm uninstall postgres --namespace "$NAMESPACE" 2>/dev/null || true
kubectl delete job pg-init-databases -n "$NAMESPACE" --ignore-not-found >/dev/null 2>&1 || true
ok "Backing services removed"

log "Deleting namespace $NAMESPACE..."
kubectl delete namespace "$NAMESPACE" --ignore-not-found --wait=false
ok "Namespace deletion initiated"

ok "Teardown complete (ingress-nginx left installed in ingress-nginx namespace)"
