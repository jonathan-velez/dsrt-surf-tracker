#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
compose=(docker compose -p dsrt-monitor-test -f tests/compose.yaml)
cleanup() {
  result=$?
  if [[ $result != 0 ]]; then "${compose[@]}" logs --tail=25; fi
  "${compose[@]}" down >/dev/null
  exit "$result"
}
trap cleanup EXIT
"${compose[@]}" up -d
"${compose[@]}" exec -T integration python /work/tests/integration.py
