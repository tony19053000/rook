#!/usr/bin/env bash
# Create the rook EC2 host (idempotent: existing pieces are reused, found by their Project=rook tag / name).
#   deploy/aws/create.sh
# Creates: key pair rook-ec2 (-> ~/.ssh/rook-ec2.pem, 600), security group rook-sg (22 from YOUR public IP /32
# only, 80/443 open), one Ubuntu 24.04 t3.small (30 GB gp3, encrypted, IMDSv2 required, standard CPU credits),
# and an Elastic IP. Prints what it will create and asks before creating anything.
set -euo pipefail
# shellcheck source=deploy/aws/lib.sh
source "$(dirname "$0")/lib.sh"

INSTANCE_TYPE=t3.small
CANONICAL_OWNER=099720109477  # Canonical; looked up via EC2 so the IAM user needs no SSM access
AMI_NAME='ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*'

tags() { # tags <resource-type>
    echo "ResourceType=$1,Tags=[{Key=Project,Value=$PROJECT_TAG},{Key=Name,Value=$NAME_TAG}]"
}

# authorize <group-id> <protocol> <port> <cidr>: add an ingress rule unless it is already there.
authorize() {
    local range=IpRanges key=CidrIp err
    if [[ "$4" == *:* ]]; then range=Ipv6Ranges key=CidrIpv6; fi
    if ! err=$(aws ec2 authorize-security-group-ingress --group-id "$1" --ip-permissions \
        "IpProtocol=$2,FromPort=$3,ToPort=$3,$range=[{$key=$4,Description=rook}]" 2>&1 >/dev/null); then
        [[ "$err" == *InvalidPermission.Duplicate* ]] || die "$err"
    fi
}

echo "Checking AWS (profile $AWS_PROFILE_NAME, region $AWS_REGION_NAME)..."
account=$(aws sts get-caller-identity --query Account --output text)
my_ip=$(curl -fsS --max-time 10 https://checkip.amazonaws.com | tr -d '[:space:]')
[[ "$my_ip" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || die "could not read your public IPv4 (got '$my_ip')"

vpc_id=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
[[ "$vpc_id" != "None" && -n "$vpc_id" ]] || die "no default VPC in $AWS_REGION_NAME"

key_id=$(aws ec2 describe-key-pairs --filters "Name=key-name,Values=$KEY_NAME" --query 'KeyPairs[0].KeyPairId' \
    --output text)
[[ "$key_id" == "None" ]] && key_id=""
if [[ -n "$key_id" && ! -f "$KEY_FILE" ]]; then
    die "key pair $KEY_NAME exists in AWS but $KEY_FILE is missing; delete the key pair (destroy.sh) and rerun"
fi

sg_id=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$SG_NAME" "Name=vpc-id,Values=$vpc_id" \
    --query 'SecurityGroups[0].GroupId' --output text)
[[ "$sg_id" == "None" ]] && sg_id=""
inst_id=$(instance_id)
alloc_id=$(eip_allocation)
ami_id=""
[[ -n "$inst_id" ]] || ami_id=$(aws ec2 describe-images --owners "$CANONICAL_OWNER" \
  --filters "Name=name,Values=$AMI_NAME" Name=state,Values=available \
  --query 'sort_by(Images,&CreationDate)[-1].ImageId' --output text)
[[ -n "$inst_id" || "$ami_id" == ami-* ]] || die "no Ubuntu 24.04 AMI found"

say() { if [[ -n "$2" ]]; then echo "  exists:      $1 ($2)"; else echo "  WILL CREATE: $1"; fi; }
echo
echo "AWS account $account, region $AWS_REGION_NAME, default VPC $vpc_id, your IP $my_ip"
say "key pair $KEY_NAME -> $KEY_FILE" "$key_id"
say "security group $SG_NAME: SSH 22 from $my_ip/32 only, HTTP 80 + HTTPS 443 from anywhere" "$sg_id"
say "EC2 $INSTANCE_TYPE Ubuntu 24.04 ($ami_id), 30 GB gp3, IMDSv2, tags Project=$PROJECT_TAG" "$inst_id"
say "Elastic IP (tag Project=$PROJECT_TAG)" "$alloc_id"
[[ -z "$sg_id" ]] || echo "  ENSURE:      SSH 22 from $my_ip/32 in $SG_NAME (other SSH rules are kept; see destroy.sh)"
echo "Costs: about 0.02 USD/hour for the instance + 0.005 USD/hour for the IPv4 address, plus the disk."
echo
confirm "Create / update these resources?" || { echo "Nothing was created."; exit 1; }

if [[ -z "$key_id" ]]; then
    mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
    (umask 077 && aws ec2 create-key-pair --key-name "$KEY_NAME" --key-type ed25519 \
        --tag-specifications "$(tags key-pair)" --query KeyMaterial --output text > "$KEY_FILE")
    chmod 600 "$KEY_FILE"
    echo "created key pair $KEY_NAME -> $KEY_FILE"
fi

if [[ -z "$sg_id" ]]; then
    sg_id=$(aws ec2 create-security-group --group-name "$SG_NAME" --description "rook server: ssh from admin, web" \
        --vpc-id "$vpc_id" --tag-specifications "$(tags security-group)" --query GroupId --output text)
    echo "created security group $sg_id"
fi
authorize "$sg_id" tcp 22 "$my_ip/32"
for port in 80 443; do
    authorize "$sg_id" tcp "$port" 0.0.0.0/0
    authorize "$sg_id" tcp "$port" ::/0
done

if [[ -z "$inst_id" ]]; then
    inst_id=$(aws ec2 run-instances --image-id "$ami_id" --instance-type "$INSTANCE_TYPE" --count 1 \
        --key-name "$KEY_NAME" --security-group-ids "$sg_id" \
        --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=30,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}' \
        --metadata-options 'HttpTokens=required,HttpEndpoint=enabled,HttpPutResponseHopLimit=1' \
        --credit-specification CpuCredits=standard \
        --user-data "file://$REPO_ROOT/deploy/aws/user-data.sh" \
        --tag-specifications "$(tags instance)" "$(tags volume)" \
        --query 'Instances[0].InstanceId' --output text)
    echo "created instance $inst_id, waiting until it runs..."
fi
aws ec2 wait instance-running --instance-ids "$inst_id"

if [[ -z "$alloc_id" ]]; then
    alloc_id=$(aws ec2 allocate-address --domain vpc --tag-specifications "$(tags elastic-ip)" \
        --query AllocationId --output text)
    echo "allocated Elastic IP $alloc_id"
fi
aws ec2 associate-address --instance-id "$inst_id" --allocation-id "$alloc_id" --allow-reassociation >/dev/null

ip=$(public_ip)
host=$(host_for_ip "$ip")
echo
echo "Ready: instance $inst_id at $ip"
echo "  server URL (after deploy.sh): https://$host  (health: https://$host/api/v1/health)"
echo "  ssh:                          deploy/aws/ssh.sh"
echo "Next: deploy/aws/deploy.sh (first boot installs Docker, give it 2-3 minutes)."
