#!/bin/sh
# Significant host change. Run only after the owner reviews/approves this script.
# Official repositories, no convenience-script execution and no foreign service restart.
set -eu
test "${1:-}" = --approved-host-change || { echo 'Review this script and obtain explicit owner approval first.' >&2; exit 2; }
test "$(id -u)" = 0
. /etc/os-release
test "$ID" = debian && test "$VERSION_ID" = 13
test "$(uname -m)" = x86_64
if command -v docker >/dev/null 2>&1 || test -e /etc/docker/daemon.json; then
 echo 'Docker/config already exists. Stop and repeat read-only audit; no automatic overwrite/restart.' >&2
 exit 2
fi
umask 077
SNAPSHOT=/root/debugych-preflight-$(date -u +%Y%m%dT%H%M%SZ)
mkdir "$SNAPSHOT"
nft list ruleset > "$SNAPSHOT/nftables.rules"
iptables-save > "$SNAPSHOT/iptables.rules"
ip6tables-save > "$SNAPSHOT/ip6tables.rules"
ip route show table all > "$SNAPSHOT/routes.txt"
systemctl list-units --type=service --state=running --no-pager > "$SNAPSHOT/services.txt"
ss -lntup > "$SNAPSHOT/ports.txt"
dpkg-query -W > "$SNAPSHOT/packages.txt"
tar -C /etc -czf "$SNAPSHOT/nginx.tar.gz" nginx
# Preserve VPN forwarding. Do not flush/restore nftables, change SSH, or change VPN ports.
install -d -m 755 /etc/docker /etc/apt/keyrings
cat > /etc/docker/daemon.json <<'EOF'
{
  "ip-forward-no-drop": true,
  "runtimes": {"runsc": {"path": "/usr/bin/runsc", "runtimeArgs": ["--platform=systrap"]}},
  "log-driver": "json-file",
  "log-opts": {"max-size": "10m", "max-file": "3"}
}
EOF
chmod 644 /etc/docker/daemon.json
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/debugych-docker.asc
chmod 644 /etc/apt/keyrings/debugych-docker.asc
cat > /etc/apt/sources.list.d/debugych-docker.sources <<'EOF'
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: trixie
Components: stable
Architectures: amd64
Signed-By: /etc/apt/keyrings/debugych-docker.asc
EOF
curl -fsSL https://gvisor.dev/archive.key -o "$SNAPSHOT/gvisor-archive.key"
gpg --batch --dearmor -o /etc/apt/keyrings/debugych-gvisor.gpg "$SNAPSHOT/gvisor-archive.key"
chmod 644 /etc/apt/keyrings/debugych-gvisor.gpg
echo 'deb [arch=amd64 signed-by=/etc/apt/keyrings/debugych-gvisor.gpg] https://storage.googleapis.com/gvisor/releases release main' > /etc/apt/sources.list.d/debugych-gvisor.list
apt-get update
apt-get --simulate install --no-install-recommends docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin runsc > "$SNAPSHOT/apt-plan.txt"
if grep -q '^Remv ' "$SNAPSHOT/apt-plan.txt"; then echo 'APT proposes removal; refusing.' >&2; exit 2; fi
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin runsc
systemctl enable --now docker
runsc --version
docker version --format '{{.Server.Version}}'
docker compose version
docker info --format '{{json .Runtimes}}'
iptables -S FORWARD | head -1
docker run --rm --runtime=runsc --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true --memory 64m --pids-limit 32 --cpus 0.5 hello-world
systemctl is-active ssh nginx xray warp-svc
echo "Host preparation finished. Private baseline: $SNAPSHOT. No Debugych public listener enabled."
