#!/usr/bin/env bash
# Container entry point (runs as the non-root `rook` user under tini): checks the Bob setup, then runs uvicorn.
# Never prints a secret value, only whether it is set.
set -euo pipefail

mode=${ROOK_BOB_MODE:-replay}
bob=${ROOK_BOB_BIN:-/usr/local/bin/bob}

if [[ -x "$bob" ]]; then
    echo "rook: Bob Shell found at $bob"
else
    echo "rook: NO Bob Shell in this image: replay mode only (see deploy/vendor/README.md)"
fi
if [[ "$mode" != "replay" ]]; then
    if [[ ! -x "$bob" ]]; then
        echo "rook: ROOK_BOB_MODE=$mode needs Bob Shell; set ROOK_BOB_MODE=replay or rebuild with deploy/vendor/" >&2
        exit 1
    fi
    if [[ -z "${BOB_API_KEY:-}" ]]; then
        echo "rook: ROOK_BOB_MODE=$mode needs the BOB_API_KEY secret (deploy/aws/scripts/set-secret.sh BOB_API_KEY)" >&2
        exit 1
    fi
fi
if docker version --format '{{.Server.Version}}' >/dev/null 2>&1; then
    echo "rook: Docker reachable: user GitHub runs possible (with the GitHub App and BOB_API_KEY)"
else
    echo "rook: Docker NOT reachable: user GitHub runs are off (demos are unaffected)"
fi
[[ -n "${ROOK_GUEST_SECRET:-}" ]] || echo "rook: WARNING ROOK_GUEST_SECRET is unset: guest cookies reset on restart"
echo "rook: bob_mode=$mode, trusted proxy hops=${ROOK_TRUSTED_PROXY_HOPS:-0}, web origins=${ROOK_WEB_ORIGINS:-<default>}"

mkdir -p "$(dirname "${ROOK_DB_PATH:-/data/rook.db}")" "${ROOK_WORKSPACES:-/data/workspaces}"

# --no-proxy-headers: the server reads X-Forwarded-For itself, counting ROOK_TRUSTED_PROXY_HOPS (03 §8).
exec uvicorn rook.server.app:app --host 0.0.0.0 --port "${PORT:-8000}" --no-proxy-headers --no-server-header \
    --timeout-graceful-shutdown 10
