#!/usr/bin/env bash
# Delete everything create.sh made: the instance (and its disk), the Elastic IP, the security group and the
# key pair (+ ~/.ssh/rook-ec2.pem). The server database and secrets on the host are lost. Asks first.
#   deploy/aws/destroy.sh
set -euo pipefail
# shellcheck source=deploy/aws/lib.sh
source "$(dirname "$0")/lib.sh"

inst_id=$(instance_id)
alloc_id=$(eip_allocation)
sg_id=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$SG_NAME" \
    "Name=tag:Project,Values=$PROJECT_TAG" --query 'SecurityGroups[0].GroupId' --output text)
[[ "$sg_id" == "None" ]] && sg_id=""
key_id=$(aws ec2 describe-key-pairs --filters "Name=key-name,Values=$KEY_NAME" --query 'KeyPairs[0].KeyPairId' \
    --output text)
[[ "$key_id" == "None" ]] && key_id=""

echo "Will DELETE (profile $AWS_PROFILE_NAME, region $AWS_REGION_NAME):"
echo "  instance:       ${inst_id:-<none>} (with its disk: the run database and /etc/rook/rook.env)"
echo "  Elastic IP:     ${alloc_id:-<none>}"
echo "  security group: ${sg_id:-<none>}"
echo "  key pair:       ${key_id:-<none>} and $KEY_FILE"
[[ -n "$inst_id$alloc_id$sg_id$key_id" ]] || { echo "Nothing to delete."; exit 0; }
confirm "Delete all of these?" || { echo "Nothing was deleted."; exit 1; }

if [[ -n "$inst_id" ]]; then
    aws ec2 terminate-instances --instance-ids "$inst_id" >/dev/null
    echo "terminating $inst_id ..."
    aws ec2 wait instance-terminated --instance-ids "$inst_id"
fi
if [[ -n "$alloc_id" ]]; then
    aws ec2 release-address --allocation-id "$alloc_id"
    echo "released $alloc_id"
fi
if [[ -n "$sg_id" ]]; then
    aws ec2 delete-security-group --group-id "$sg_id"
    echo "deleted $sg_id"
fi
if [[ -n "$key_id" ]]; then
    aws ec2 delete-key-pair --key-pair-id "$key_id"
    rm -f "$KEY_FILE"
    echo "deleted key pair $KEY_NAME"
fi
echo "Done."
