#!/usr/bin/env bash
# Live smoke check: every public page answers 200 and the API health route (same origin, via the Vercel proxy)
# answers JSON with ok: true. Usage: live-smoke.sh <base-url>
set -euo pipefail

base="${1:?usage: live-smoke.sh <base-url>}"
base="${base%/}"
pages=(/ /app /docs /pricing /security /privacy /terms /login)
# --fail makes HTTP errors (e.g. a 503 during a deploy) count as transient, so --retry-all-errors retries them.
curl_opts=(--silent --show-error --fail --location --max-time 30 --retry 4 --retry-delay 5 --retry-all-errors)
failed=0

for page in "${pages[@]}"; do
  code="$(curl "${curl_opts[@]}" --output /dev/null --write-out '%{http_code}' "$base$page")" || true
  if [[ "$code" == "200" ]]; then
    echo "ok   $code $page"
  else
    echo "FAIL $code $page"
    failed=1
  fi
done

health="$(curl "${curl_opts[@]}" "$base/api/v1/health")" || true
if jq -e '.ok == true' <<<"$health" >/dev/null 2>&1; then
  echo "ok   /api/v1/health ok: true"
else
  echo "FAIL /api/v1/health: ${health:0:200}"
  failed=1
fi

exit "$failed"
