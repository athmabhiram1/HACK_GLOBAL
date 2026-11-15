#!/usr/bin/env bash
# BatonGate fresh-VM setup + redeploy. Implements docs/02-architecture.md Section 7 exactly.
# Run ON the Vultr VM as root:  bash deploy/update.sh [repo-url]
# Idempotent: first run clones + installs; later runs take the git-pull update path.
set -euo pipefail

REPO_URL="${1:-https://github.com/athmabhiram1/HACK_GLOBAL.git}"
APP_DIR="${APP_DIR:-/root/batongate}"

echo "==> [1/10] Install Docker (get.docker.com)"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
else
  echo "    docker already installed, skipping"
fi

echo "==> [2/10] Install git + hadolint"
apt-get update -y
apt-get install -y git hadolint curl iptables ufw ca-certificates

echo "==> [3/10] Fetch app source"
if [ -d "$APP_DIR/.git" ]; then
  echo "    existing checkout found -> update path: git pull"
  git -C "$APP_DIR" pull --ff-only
else
  echo "    fresh clone"
  git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

echo "==> [4/10] Env file reminder (never echo secrets)"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "    copied .env.example -> .env -- EDIT .env ON THE SERVER NOW (LLM_*, VULTR_API_KEY, optional EXA_API_KEY/WISPR_API_KEY). Never commit .env, never print keys."
else
  echo "    .env exists, leaving untouched (edit on server if keys changed)"
fi

echo "==> [5/10] Throttle BuildKit for 2GB VM (/etc/buildkitd.toml max-parallelism=1 + gc caps)"
printf '[worker.oci]\n max-parallelism=1\n[worker.oci.gcpolicy]\n reservedSpace="512MB"\n maxUsedSpace="2GB"\n' | tee /etc/buildkitd.toml
docker buildx create --use --driver docker-container --buildkitd-config /etc/buildkitd.toml || docker buildx use default-builder 2>/dev/null || true

echo "==> [6/10] Metadata guard: REJECT 169.254.169.254 in DOCKER-USER"
# REJECT-not-DROP on purpose: probes fail fast instead of hanging until the 300s build timeout.
# UFW alone is bypassed by Docker's iptables chain, so the DOCKER-USER rule is the real guard.
if ! iptables -C DOCKER-USER -d 169.254.169.254 -j REJECT 2>/dev/null; then
  iptables -I DOCKER-USER -d 169.254.169.254 -j REJECT
fi
iptables -L DOCKER-USER -n | head -5 || true

echo "==> [7/10] Build image (docker build -t baton .)"
docker build -t baton .

echo "==> [8/10] (Re)start container (--restart unless-stopped --env-file .env -p 80:8000)"
docker rm -f baton 2>/dev/null || true
docker run -d --name baton --restart unless-stopped --env-file .env -p 80:8000 baton

echo "==> [9/10] Firewall: ufw allow 80/tcp"
ufw allow 80/tcp || true
ufw --force enable || true

echo "==> [10/10] Health check"
sleep 5
curl -fsS http://127.0.0.1/api/healthz
echo ""
echo "DONE. Open http://<vultr-ip>/ in a private window."
echo "Update path next time: re-run this script (git pull + rebuild + restart)."
