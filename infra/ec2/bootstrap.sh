#!/usr/bin/env bash
# Lantern EC2 bootstrap — Ubuntu 24.04. Idempotent: safe to re-run.
# Use as instance user-data, or on a running box:  sudo bash bootstrap.sh
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive

REPO_URL="https://github.com/Dimashsaken/Agentic-workflow-lantern.git"
APP_USER="ubuntu"
APP_HOME="/home/${APP_USER}"
REPO_DIR="${APP_HOME}/Agentic-workflow-lantern"

# --- system packages -------------------------------------------------------
apt-get update
apt-get install -y git unzip curl python3.12 python3.12-venv postgresql-16
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y nodejs
npm install -g @openai/codex

# --- repo + runtimes (as the app user) -------------------------------------
sudo -u "${APP_USER}" bash <<EOS
set -eux
cd "${APP_HOME}"
[ -d "${REPO_DIR}" ] || git clone "${REPO_URL}"
cd "${REPO_DIR}" && git pull --ff-only || true
cd "${REPO_DIR}/tools/qa-recorder" && npm install
cd "${REPO_DIR}/tools/azure-runner"
[ -d .venv ] || python3.12 -m venv .venv
.venv/bin/pip install --quiet -r requirements.txt
EOS

# Playwright browsers + OS deps (root needed for --with-deps)
cd "${REPO_DIR}/tools/qa-recorder"
npx playwright install --with-deps chromium webkit firefox

# --- Postgres: role + database (password comes later via .env/SSM) ---------
sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='lantern'" | grep -q 1 \
  || sudo -u postgres psql -c "CREATE USER lantern WITH PASSWORD 'CHANGE-ME-VIA-SSM';"
sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='lantern'" | grep -q 1 \
  || sudo -u postgres psql -c "CREATE DATABASE lantern OWNER lantern;"

# --- systemd unit for the pipeline daemon ----------------------------------
cp "${REPO_DIR}/infra/ec2/lantern-orchestrator.service" /etc/systemd/system/
systemctl daemon-reload

set +x
echo "── bootstrap complete ──────────────────────────────────────────────"
echo "Remaining manual steps (secrets never live in this script):"
echo "  1. Set the real lantern DB password + write tools/azure-runner/.env"
echo "     (or wire SSM per infra/ec2/README.md)"
echo "  2. cd ${REPO_DIR}/tools/azure-runner && .venv/bin/python pipeline.py init-db"
echo "  3. systemctl enable --now lantern-orchestrator"
