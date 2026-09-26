#!/usr/bin/env bash
# Copy the repo to the rook host and (re)start the server:  deploy/aws/deploy.sh
# Optional settings (non-secret, written to deploy/.env on the host):
#   ROOK_WEB_ORIGINS=https://rook-xyz.vercel.app  (CORS; the Vercel origin once you have it)
#   ROOK_BOB_MODE=replay|live|record              (default replay; live needs the vendored Bob + BOB_API_KEY)
#   ROOK_DAILY_COIN_CAP=2                         (Bobcoins per day for the whole server)
# The optional vendored Bob Shell (deploy/vendor/, see deploy/pack-bob.sh) is copied with the repo.
set -euo pipefail
# shellcheck source=deploy/aws/lib.sh
source "$(dirname "$0")/lib.sh"

web_origins=${ROOK_WEB_ORIGINS:-http://localhost:3000}
bob_mode=${ROOK_BOB_MODE:-replay}
coin_cap=${ROOK_DAILY_COIN_CAP:-2}
origin_re='^https?://[A-Za-z0-9.-]+(:[0-9]{1,5})?$'
IFS=, read -r -a origins <<< "$web_origins"
for origin in "${origins[@]}"; do
    [[ "$origin" =~ $origin_re ]] || die "ROOK_WEB_ORIGINS: '$origin' is not scheme://host[:port]"
done
[[ "$bob_mode" =~ ^(replay|live|record)$ ]] || die "ROOK_BOB_MODE must be replay, live or record"
[[ "$coin_cap" =~ ^[0-9]+(\.[0-9]+)?$ ]] || die "ROOK_DAILY_COIN_CAP must be a number"

ip=$(public_ip)
host=$(host_for_ip "$ip")
ssh_opts
target="$SSH_USER@$ip"
# shellcheck disable=SC2029  # remote commands are built from validated values on purpose
remote() { ssh "${SSH_OPTS[@]}" "$target" "$@"; }

echo "Waiting for $target (first boot installs Docker)..."
for _ in $(seq 1 30); do
    remote true 2>/dev/null && break
    sleep 10
done
remote 'cloud-init status --wait >/dev/null || true; command -v docker >/dev/null' \
    || die "Docker is not installed on the host yet (check: deploy/aws/ssh.sh 'cloud-init status --long')"

if [[ -f "$REPO_ROOT/deploy/vendor/bobshell-2.0.5.tgz" ]]; then
    echo "Vendored Bob Shell found: the image will support live mode."
else
    echo "No vendored Bob Shell (deploy/pack-bob.sh): the image will be REPLAY-ONLY."
    [[ "$bob_mode" == "replay" ]] || die "ROOK_BOB_MODE=$bob_mode needs Bob: run deploy/pack-bob.sh first"
fi

echo "Copying the repo to $target:~/$REMOTE_DIR ..."
rsync -az --delete \
    --exclude '.git/' --exclude 'node_modules/' --exclude '.venv/' --exclude '/web/' \
    --exclude '.env*' --exclude '*.pem' --exclude '.rook/' --exclude '__pycache__/' \
    --exclude '.pytest_cache/' --exclude '.ruff_cache/' --exclude '.next/' \
    -e "ssh ${SSH_OPTS[*]}" "$REPO_ROOT/" "$target:$REMOTE_DIR/"

echo "Writing the non-secret settings (deploy/.env on the host)..."
printf 'ROOK_HOST=%s\nROOK_WEB_ORIGINS=%s\nROOK_BOB_MODE=%s\nROOK_DAILY_COIN_CAP=%s\n' \
    "$host" "$web_origins" "$bob_mode" "$coin_cap" | remote "cat > $REMOTE_DIR/deploy/.env"

# A guest-cookie key made ON the host (it never leaves it), unless one was set with set-secret.sh.
remote "sudo install -d -m 700 /etc/rook && sudo touch /etc/rook/rook.env && sudo chmod 600 /etc/rook/rook.env \
    && { sudo grep -q '^ROOK_GUEST_SECRET=' /etc/rook/rook.env \
         || openssl rand -hex 32 | sudo python3 $REMOTE_DIR/deploy/aws/remote/set_env.py ROOK_GUEST_SECRET; }"

echo "Building and starting (the first build takes a few minutes)..."
remote "cd $REMOTE_DIR/deploy && sudo docker compose up -d --build --remove-orphans && sudo docker image prune -f >/dev/null"

url="https://$host/api/v1/health"
echo "Waiting for $url (Caddy gets the Let's Encrypt certificate on the first request)..."
for _ in $(seq 1 40); do
    if health=$(curl -fsS --max-time 10 "$url" 2>/dev/null); then
        echo "UP: $health"
        echo "Server origin (ROOK_API_PROXY_TARGET for Vercel): https://$host"
        exit 0
    fi
    sleep 5
done
die "no answer from $url; see: deploy/aws/ssh.sh 'cd $REMOTE_DIR/deploy && sudo docker compose logs --tail 50'"
