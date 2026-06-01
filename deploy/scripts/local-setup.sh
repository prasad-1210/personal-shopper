#!/bin/bash
# Sets up personal-shopper on Docker Desktop Kubernetes
# Prerequisites: Docker Desktop with Kubernetes enabled
# Run once: bash deploy/scripts/local-setup.sh

set -e

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
NAMESPACE="agents-dev"

echo "==> Checking prerequisites..."
command -v kubectl >/dev/null 2>&1 || { echo "kubectl not found. Install Docker Desktop."; exit 1; }
command -v helm >/dev/null 2>&1 || { echo "helm not found: brew install helm"; exit 1; }

# Verify Docker Desktop Kubernetes is running
CONTEXT=$(kubectl config current-context 2>/dev/null || echo "none")
if [[ "$CONTEXT" != "docker-desktop" ]]; then
  echo "ERROR: kubectl context is '$CONTEXT', expected 'docker-desktop'"
  echo "Enable Kubernetes in Docker Desktop: Settings → Kubernetes → Enable"
  exit 1
fi
echo "    Context: $CONTEXT ✓"

echo ""
echo "==> Creating namespace..."
kubectl create namespace $NAMESPACE 2>/dev/null || echo "    Namespace exists"

echo ""
echo "==> Installing nginx ingress controller..."
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.9.5/deploy/static/provider/cloud/deploy.yaml
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s
echo "    Ingress controller ready ✓"

echo ""
echo "==> Installing in-cluster Redis (simulates Azure Cache for Redis)..."
helm repo add bitnami https://charts.bitnami.com/bitnami 2>/dev/null || true
helm repo update --fail-on-repo-update-fail 2>/dev/null || helm repo update
helm upgrade --install redis bitnami/redis \
  --namespace $NAMESPACE \
  --set auth.enabled=false \
  --set master.persistence.enabled=false \
  --wait

echo ""
echo "==> Installing in-cluster PostgreSQL (simulates Azure PostgreSQL)..."
helm upgrade --install postgres bitnami/postgresql \
  --namespace $NAMESPACE \
  --set auth.postgresPassword=langgraph \
  --set auth.database=langgraph \
  --set auth.username=langgraph \
  --set primary.persistence.enabled=false \
  --wait

echo ""
echo "==> Building images..."
echo "    Building agent images (supervisor + 4 sub-agents)..."
pip install "langgraph-cli[inmem]" -q
bash scripts/build-agent-images.sh --tag latest

echo "    Building UI image..."
docker build -t personal-shopper-ui:latest -f Dockerfile.ui .
echo "    Images built ✓ (Docker Desktop shares daemon — no load step needed)"

echo ""
echo "==> Creating per-agent Kubernetes secrets (wolfi REDIS_URI / DATABASE_URI)..."
bash deploy/scripts/create-agent-secrets.sh "$NAMESPACE"
echo "    Secrets applied ✓"

echo ""
echo "==> Deploying all agents via layered Helm..."
bash deploy/scripts/helm-deploy-all.sh local "$NAMESPACE"

echo ""
echo "==> Checking pods..."
kubectl get pods -n $NAMESPACE

echo ""
echo "✅ Done!"
echo ""
echo "   UI:    http://localhost  (via ingress)"
echo "   Agent: http://localhost/agent  (via ingress)"
echo ""
echo "   Or use port-forward:"
echo "   kubectl port-forward svc/ui 22005:22005 -n $NAMESPACE"
echo "   kubectl port-forward svc/supervisor 8000:8000 -n $NAMESPACE"
echo ""
echo "   Per-agent deploy: bash deploy/scripts/helm-deploy.sh <agent> local"
echo "   See deploy/helm/LAYERS.md"
