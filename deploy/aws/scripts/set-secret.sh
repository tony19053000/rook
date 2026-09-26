#!/usr/bin/env bash
# shellcheck disable=SC2029  # the remote command holds only the allowlisted NAME
# Set one server secret in /etc/rook/rook.env on the rook host (root-only, 600) and restart the server.
#   deploy/aws/scripts/set-secret.sh BOB_API_KEY                         # prompts, input hidden
#   deploy/aws/scripts/set-secret.sh GITHUB_APP_PRIVATE_KEY < app.pem    # piped: newlines are kept
# The value travels only over ssh stdin: never in argv, shell history, logs or this script's output.
# Needs deploy/aws/deploy.sh to have run once (it installs the helper and deploy/.env on the host).
set -euo pipefail
# shellcheck source=deploy/aws/lib.sh
source "$(dirname "$0")/../lib.sh"

ALLOWED=(BOB_API_KEY ROOK_GUEST_SECRET SUPABASE_JWT_SECRET SUPABASE_URL GITHUB_APP_ID GITHUB_APP_PRIVATE_KEY
    GITHUB_WEBHOOK_SECRET)

[[ $# -eq 1 ]] || die "usage: $0 NAME   (NAME is one of: ${ALLOWED[*]})"
name=$1
allowed=false
for n in "${ALLOWED[@]}"; do [[ "$name" == "$n" ]] && allowed=true; done
$allowed || die "'$name' is not a settable secret (one of: ${ALLOWED[*]})"

ip=$(public_ip)
ssh_opts
# $name is checked against the allowlist, so it is safe inside the remote command line.
store="sudo python3 $REMOTE_DIR/deploy/aws/remote/set_env.py $name"

if [[ -t 0 ]]; then
    [[ "$name" != GITHUB_APP_PRIVATE_KEY ]] || die "pipe the key file in: $0 $name < path/to/app.pem"
    read -r -s -p "Value for $name (hidden): " value
    echo
    [[ -n "$value" ]] || die "empty value"
    printf '%s' "$value" | ssh "${SSH_OPTS[@]}" "$SSH_USER@$ip" "$store"
    unset value
else
    ssh "${SSH_OPTS[@]}" "$SSH_USER@$ip" "$store"
fi

echo "Restarting rook with the new secret..."
ssh "${SSH_OPTS[@]}" -n "$SSH_USER@$ip" "cd $REMOTE_DIR/deploy && sudo docker compose up -d --force-recreate rook"
