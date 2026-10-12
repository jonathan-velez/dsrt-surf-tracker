#!/usr/bin/env bash
# Change the existing feed once, muted, preserving watch identity and all history.
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/api.sh
mkdir -p .local
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
api "$API_URL/watch" > "$tmp/watches.json"
ids=$(jq -r 'to_entries[] | select(.value.title == "DSRT Surf — Published Session Pricing") | .key' "$tmp/watches.json")
[[ $(printf '%s\n' "$ids" | awk 'NF {n++} END {print n+0}') == 1 ]] || { echo 'Expected exactly one pricing watch.' >&2; exit 1; }
api "$API_URL/watch/$ids" > "$tmp/before.json"
cp "$tmp/before.json" .local/pricing-before-migration.json
chmod 600 .local/pricing-before-migration.json
jq '{notification_muted, paused}' "$tmp/before.json" > "$tmp/restore.json"
# Mute before switching formats so the migration cannot produce a pricing alert.
printf '%s\n' '{"notification_muted":true,"paused":true}' > "$tmp/pause.json"
api -X PUT --data-binary "@$tmp/pause.json" "$API_URL/watch/$ids" > /dev/null
restore() {
  api -X PUT --data-binary "@$tmp/restore.json" "$API_URL/watch/$ids" > /dev/null
  rm -rf "$tmp"
}
trap restore EXIT
jq '{url, notification_title, notification_body, notification_format} + {include_filters: [], notification_muted: true, paused: false}' config/watch.json > "$tmp/feed.json"
api -X PUT --data-binary "@$tmp/feed.json" "$API_URL/watch/$ids" > /dev/null
api "$API_URL/watch/$ids" > "$tmp/current.json"
before=$(jq -r .check_count "$tmp/current.json")
api "$API_URL/watch/$ids?recheck=true" > /dev/null
success=false
for ((i=0;i<120;i++)); do
  api "$API_URL/watch/$ids" > "$tmp/current.json"
  if [[ $(jq -r .check_count "$tmp/current.json") -gt $before ]]; then
    if jq -e '(.last_error | not) and .history_n > 0' "$tmp/current.json" > /dev/null; then success=true; fi
    break
  fi
  sleep 1
done
if [[ $success != true ]]; then
  # Restore the old feed if the new baseline could not be verified.
  jq '{url, include_filters, notification_title, notification_body, notification_format}' "$tmp/before.json" > "$tmp/rollback.json"
  api -X PUT --data-binary "@$tmp/rollback.json" "$API_URL/watch/$ids" > /dev/null
  echo 'Pricing migration failed; previous watch settings restored.' >&2
  exit 1
fi
if [[ -f .local/watch.json ]]; then
  jq --slurpfile feed config/watch.json '. + ($feed[0] | {url, notification_title, notification_body, notification_format}) + {include_filters: []}' .local/watch.json > "$tmp/local.json"
  cp "$tmp/local.json" .local/watch.json
  chmod 600 .local/watch.json
fi
echo "Pricing baseline verified for $ids; original notification and pause settings restored."
