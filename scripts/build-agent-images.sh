#!/usr/bin/env bash
# Build one LangGraph image per agent from deploy/agents.manifest.yaml + Helm values.
#
# Usage:
#   bash scripts/build-agent-images.sh
#   bash scripts/build-agent-images.sh --tag ci
#   IMAGE_PREFIX=ghcr.io/org/repo/personal-shopper bash scripts/build-agent-images.sh --tag dev --push
#   bash scripts/build-agent-images.sh --only nutrition
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TAG="latest"
PUSH=false
ONLY=""
IMAGE_PREFIX="${IMAGE_PREFIX:-personal-shopper}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag) TAG="$2"; shift 2 ;;
    --push) PUSH=true; shift ;;
    --only) ONLY="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,14p' "$0"
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if ! command -v langgraph >/dev/null 2>&1; then
  echo "langgraph CLI not found. Install: pip install 'langgraph-cli[inmem]'" >&2
  exit 1
fi

pip install -q pyyaml 2>/dev/null || true

mapfile -t SPECS < <(python3 scripts/langgraph-agents.py build-specs)
if [[ ${#SPECS[@]} -eq 0 ]]; then
  echo "No buildable agents (check deploy/agents.manifest.yaml)" >&2
  exit 1
fi

build_one() {
  local name=$1
  local config=$2
  local image="${IMAGE_PREFIX}-${name}:${TAG}"
  echo "==> langgraph build -c ${config} -t ${image}"
  langgraph build \
    -c "${ROOT}/${config}" \
    --platform linux/amd64 \
    --pull \
    -t "${image}"
  if [[ "$PUSH" == "true" ]]; then
    docker push "${image}"
  fi
  echo "${image}"
}

built=()
for spec in "${SPECS[@]}"; do
  name="${spec%%:*}"
  config="${spec#*:}"
  if [[ -n "$ONLY" && "$name" != "$ONLY" ]]; then
    continue
  fi
  built+=("$(build_one "$name" "$config")")
done

echo ""
echo "Built ${#built[@]} image(s) with tag ${TAG}:"
printf '  %s\n' "${built[@]}"
