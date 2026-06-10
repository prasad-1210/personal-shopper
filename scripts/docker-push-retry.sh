#!/usr/bin/env bash
# Push Docker images with retries (GHCR intermittently returns "unknown blob").
# Additional registry tags are created via buildx imagetools — no layer re-upload.
#
# Usage:
#   bash scripts/docker-push-retry.sh push ghcr.io/org/repo:tag
#   bash scripts/docker-push-retry.sh tag-remote ghcr.io/org/repo:sha ghcr.io/org/repo:dev
set -euo pipefail

MAX_ATTEMPTS="${DOCKER_PUSH_RETRIES:-5}"
INITIAL_WAIT="${DOCKER_PUSH_RETRY_WAIT_SEC:-15}"

_retry() {
  local desc=$1
  shift
  local attempt=1
  local wait=$INITIAL_WAIT
  while true; do
    if "$@"; then
      return 0
    fi
    if (( attempt >= MAX_ATTEMPTS )); then
      echo "ERROR: ${desc} failed after ${MAX_ATTEMPTS} attempts" >&2
      return 1
    fi
    echo "WARN: ${desc} failed (attempt ${attempt}/${MAX_ATTEMPTS}), retrying in ${wait}s..." >&2
    sleep "$wait"
    attempt=$((attempt + 1))
    wait=$((wait * 2))
    (( wait > 120 )) && wait=120
  done
}

cmd_push() {
  if [[ $# -ne 1 ]]; then
    echo "Usage: $0 push <image>" >&2
    exit 1
  fi
  _retry "docker push $1" docker push "$1"
}

cmd_tag_remote() {
  if [[ $# -lt 2 ]]; then
    echo "Usage: $0 tag-remote <source> <target>..." >&2
    exit 1
  fi
  local source=$1
  shift
  for target in "$@"; do
    _retry "imagetools create ${target} from ${source}" \
      docker buildx imagetools create -t "$target" "$source"
  done
}

case "${1:-}" in
  push) shift; cmd_push "$@" ;;
  tag-remote) shift; cmd_tag_remote "$@" ;;
  *)
    echo "Usage: $0 push <image> | tag-remote <source> <target>..." >&2
    exit 1
    ;;
esac
