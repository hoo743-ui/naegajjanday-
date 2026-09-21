#!/usr/bin/env bash
# Post-deploy smoke test.
#   smoke.sh <base-url>            e.g. smoke.sh https://staging.naegajjanday.com
# Environment:
#   SMOKE_REGION   region slug that must have data (default seoul-hongdae)
#   SMOKE_RETRIES  /readyz attempts, 10 s apart (default 30)
#
# 1. GET  /readyz               -> 200 (DB, Redis, search reachable)
# 2. POST /v1/courses/generate  -> 200 with at least one course that has stops
#    (the real optimiser path from docs/03-api-spec.md, not a mock).
set -euo pipefail

BASE_URL=${1:?usage: smoke.sh <base-url>}
BASE_URL=${BASE_URL%/}
REGION=${SMOKE_REGION:-seoul-hongdae}
RETRIES=${SMOKE_RETRIES:-30}

echo "== readyz: $BASE_URL/readyz"
ok=0
for i in $(seq 1 "$RETRIES"); do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE_URL/readyz" || true)
  if [[ "$code" == "200" ]]; then
    ok=1
    break
  fi
  echo "   attempt $i/$RETRIES -> HTTP $code"
  sleep 10
done
if [[ "$ok" != "1" ]]; then
  echo "::error::/readyz never returned 200"
  exit 1
fi
echo "   ready"

echo "== POST $BASE_URL/v1/courses/generate (region=$REGION)"
payload=$(jq -cn --arg region "$REGION" '{
  region: $region,
  purpose: "date",
  party_size: 2,
  budget_total: 40000,
  transport: "walk",
  alternatives: 1
}')

body_file=$(mktemp)
code=$(curl -s -o "$body_file" -w '%{http_code}' --max-time 30 \
  -X POST "$BASE_URL/v1/courses/generate" \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: smoke-${GITHUB_SHA:-local}-${GITHUB_RUN_ATTEMPT:-0}" \
  -H 'User-Agent: naegajjanday-smoke/1.0' \
  --data "$payload" || true)

if [[ "$code" != "200" ]]; then
  echo "::error::courses/generate returned HTTP $code"
  head -c 2000 "$body_file" || true
  echo
  exit 1
fi

if ! jq -e '(.courses | length) >= 1 and (.courses[0].stops | length) >= 1' "$body_file" >/dev/null; then
  echo "::error::courses/generate returned 200 but no usable course"
  head -c 2000 "$body_file" || true
  echo
  exit 1
fi

jq -r '"   ok: \(.courses | length) course(s), first has \(.courses[0].stops | length) stops, total \(.courses[0].totals.price) KRW, latency \(.meta.latency_ms // "n/a") ms"' "$body_file"
