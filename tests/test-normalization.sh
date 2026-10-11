#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
fixture=tests/fixtures/sessions.json
jq -f filters/sessions.jq "$fixture" > "$tmp/base"
check() {
  local expected=$1 name=$2 expression=$3
  jq "$expression" "$fixture" > "$tmp/input"
  if jq -f filters/sessions.jq "$tmp/input" > "$tmp/result" 2> "$tmp/error"; then
    if cmp -s "$tmp/base" "$tmp/result"; then actual=same; else actual=change; fi
  else actual=error; fi
  [[ $actual == "$expected" ]] || { echo "FAIL $name: $actual instead of $expected"; exit 1; }
  echo "PASS $name"
}
check same availability 'map(.available=0 | .effectiveAvailable=0 | .incart=9)'
check same capacity 'map(.sessionlimit=999 | .effectiveMax=999)'
check same direction-availability '.[1].available=0'
check same order 'reverse'
check same duplicate-expiry 'del(.[3])'
check same blocked 'map(.blocked=true | .bookingMode="request-only")'
check same fallback 'map(del(.currentPrice))'
check same private-exclusion '. + [.[0] | .privateSession=true | .currentPrice=12500]'
check same bay-exclusion '. + [.[0] | .waveClass="bay" | .currentPrice=60]'
check change weekday-decrease '.[2].currentPrice-=10'
check change weekend-decrease '.[0].currentPrice-=10'
check change increase '.[0].currentPrice+=10'
check change discounted-tier '. + [.[0] | .currentPrice-=20]'
check change rename 'map(.sessiontype="New name")'
check change new-type '. + [.[0] | .sessiontype="New type"]'
check change direction-price '.[1].currentPrice+=15'
check change last-tier-expiry 'del(.[2:4])'
check error empty '[]'
check error wrong-shape '{}'
check error missing-price 'map(del(.currentPrice,.price))'
check error bad-price '.[0].currentPrice="220"'
check error invalid-date '.[0].dateid="not-a-date"'
check error no-reef 'map(.waveClass="bay")'
if printf '{broken' | jq -f filters/sessions.jq > /dev/null 2>&1; then exit 1; fi
echo 'PASS invalid-json'
