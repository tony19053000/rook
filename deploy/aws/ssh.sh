#!/usr/bin/env bash
# SSH into the rook host (or run one command there):  deploy/aws/ssh.sh ['command']
set -euo pipefail
# shellcheck source=deploy/aws/lib.sh
source "$(dirname "$0")/lib.sh"

ip=$(public_ip)
ssh_opts
exec ssh "${SSH_OPTS[@]}" "$SSH_USER@$ip" "$@"
