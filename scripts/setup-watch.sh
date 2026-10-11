#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/api.sh
config=${1:-config/watch.json}
filter=${2:-filters/sessions.jq}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
# A single selector: multiline jq is folded because UI selectors are line based.
jq --rawfile filter "$filter" '. + {include_filters: ["jq:" + ($filter | split("\n") | map(select(startswith("#")|not)) | join(" "))]}' "$config" > "$tmp/watch.json"
title=$(jq -r .title "$config")
api "$API_URL/watch" > "$tmp/watches.json"
ids=$(jq -r --arg title "$title" 'to_entries[] | select(.value.title == $title) | .key' "$tmp/watches.json")
count=$(printf '%s\n' "$ids" | awk 'NF {n++} END {print n+0}')
if [[ $count -gt 1 ]]; then
  echo 'Multiple watches have this title; resolve duplicates in the dashboard first.' >&2; exit 1
elif [[ $count == 1 ]]; then
  if ! api -X PUT --data-binary "@$tmp/watch.json" "$API_URL/watch/$ids" > "$tmp/updated.json"; then
    cat "$tmp/updated.json" >&2; exit 1
  fi
  echo "Updated $title ($ids)"
else
  if ! api -X POST --data-binary "@$tmp/watch.json" "$API_URL/watch" > "$tmp/created.json"; then
    cat "$tmp/created.json" >&2; exit 1
  fi
  echo "Created $title ($(jq -r .uuid "$tmp/created.json"))"
fi
