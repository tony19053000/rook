#!/usr/bin/env bash
# EC2 user-data (first boot, as root) for the rook host: Docker + compose, automatic security updates, swap,
# and an empty root-only secrets file. It holds NO secrets: user-data is readable from the instance metadata.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get -y upgrade
apt-get install -y --no-install-recommends docker.io docker-compose-v2 unattended-upgrades rsync curl ca-certificates

# Security updates every day, reboot at 04:00 UTC when a kernel update needs it.
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
cat > /etc/apt/apt.conf.d/52rook-unattended <<'EOF'
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
EOF
systemctl enable --now unattended-upgrades

systemctl enable --now docker
usermod -aG docker ubuntu

# t3.small has 2 GB RAM: 2 GB of swap keeps `docker compose build` from running out of memory.
if [[ ! -f /swapfile ]]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# Secrets live only here (root:root 600), written by deploy/aws/scripts/set-secret.sh.
install -d -m 700 -o root -g root /etc/rook
[[ -f /etc/rook/rook.env ]] || install -m 600 -o root -g root /dev/null /etc/rook/rook.env
