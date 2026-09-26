#!/usr/bin/env bash
# Shared helpers for deploy/aws/*.sh (sourced, never run). Every AWS call goes through `aws` below:
# the AWS CLI via uvx, profile `rook`, region us-west-2. Resources are found by their tags (Project=rook).
# shellcheck disable=SC2034  # the variables are used by the scripts that source this file
set -euo pipefail

AWS_PROFILE_NAME=rook
AWS_REGION_NAME=us-west-2
PROJECT_TAG=rook
NAME_TAG=rook
KEY_NAME=rook-ec2
KEY_FILE="$HOME/.ssh/rook-ec2.pem"
SG_NAME=rook-sg
SSH_USER=ubuntu
REMOTE_DIR=rook
REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)

aws() {
    uvx --from awscli aws --profile "$AWS_PROFILE_NAME" --region "$AWS_REGION_NAME" "$@"
}

die() {
    echo "error: $*" >&2
    exit 1
}

confirm() {
    local reply
    read -r -p "$1 [y/N] " reply
    [[ "$reply" == [yY] || "$reply" == [yY][eE][sS] ]]
}

# The id of the live (pending/running/stopping/stopped) rook instance, or "".
instance_id() {
    local id
    id=$(aws ec2 describe-instances \
        --filters "Name=tag:Project,Values=$PROJECT_TAG" "Name=tag:Name,Values=$NAME_TAG" \
        "Name=instance-state-name,Values=pending,running,stopping,stopped" \
        --query 'Reservations[].Instances[].InstanceId' --output text)
    [[ "$id" == "None" ]] && id=""
    [[ "$id" != *[[:space:]]* ]] || die "more than one rook instance: $id"
    echo "$id"
}

# The allocation id and public IP of the rook Elastic IP ("" when there is none).
eip_allocation() {
    local out
    out=$(aws ec2 describe-addresses --filters "Name=tag:Project,Values=$PROJECT_TAG" \
        --query 'Addresses[0].AllocationId' --output text)
    [[ "$out" == "None" ]] && out=""
    echo "$out"
}

public_ip() {
    local ip
    ip=$(aws ec2 describe-addresses --filters "Name=tag:Project,Values=$PROJECT_TAG" \
        --query 'Addresses[0].PublicIp' --output text)
    [[ "$ip" == "None" || -z "$ip" ]] && die "no rook Elastic IP: run deploy/aws/create.sh first"
    echo "$ip"
}

# 203.0.113.7 -> 203-0-113-7.sslip.io (sslip.io resolves it back to the IP; Caddy gets a real certificate).
host_for_ip() {
    echo "${1//./-}.sslip.io"
}

ssh_opts() {
    [[ -f "$KEY_FILE" ]] || die "no SSH key at $KEY_FILE (created by deploy/aws/create.sh)"
    SSH_OPTS=(-i "$KEY_FILE" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10)
}
