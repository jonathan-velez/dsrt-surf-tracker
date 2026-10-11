#!/usr/bin/env bash
# Source from scripts/tests after changing to the repository root.
set -euo pipefail
API_URL=${API_URL:-http://localhost:5050/api/v1}
if [[ -z ${CHANGEDETECTION_API_KEY:-} ]]; then
  CHANGEDETECTION_API_KEY=$(docker compose exec -T changedetection python -c 'import json; print(json.load(open("/datastore/changedetection.json"))["settings"]["application"]["api_access_token"])')
fi
# Keep the key out of process arguments and logs.
api() {
  printf 'header = "x-api-key: %s"\n' "$CHANGEDETECTION_API_KEY" |
    curl --config - --fail-with-body --silent --show-error --max-time 60 \
      -H 'Content-Type: application/json' "$@"
}
