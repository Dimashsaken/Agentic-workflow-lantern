#!/usr/bin/env bash
# Lantern EC2 bootstrap — Ubuntu 24.04. Idempotent: safe to re-run.
# Use as instance user-data, or on a running box:  sudo bash bootstrap.sh
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive

REPO_URL="https://github.com/Dimashsaken/Agentic-workflow-lantern.git"
APP_USER="ubuntu"
APP_HOME="/home/${APP_USER}"
REPO_DIR="${APP_HOME}/Agentic-workflow-lantern"
AWS_REGION="${AWS_REGION:-us-east-1}"

# --- system packages -------------------------------------------------------
apt-get update
apt-get install -y git unzip curl python3.12 python3.12-venv postgresql-16 awscli
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y nodejs
npm install -g @openai/codex

# --- secrets from SSM (instance role must allow ssm:GetParameter /lantern/*) ---
ssm() { aws ssm get-parameter --region "${AWS_REGION}" --name "$1" \
          --with-decryption --query Parameter.Value --output text 2>/dev/null || true; }
GH_TOKEN="$(ssm /lantern/github/bot-token)"
DOTENV="$(ssm /lantern/dotenv)"
if [ -n "${GH_TOKEN}" ] && [ "${GH_TOKEN}" != "None" ]; then
  sudo -u "${APP_USER}" git config --global credential.helper store
  printf 'https://x-access-token:%s@github.com\n' "${GH_TOKEN}" > "${APP_HOME}/.git-credentials"
  chown "${APP_USER}:${APP_USER}" "${APP_HOME}/.git-credentials" && chmod 600 "${APP_HOME}/.git-credentials"
else
  echo "WARN: /lantern/github/bot-token not in SSM — clone of the private repo will fail; add it and re-run."
fi

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

# --- Postgres: role + database (listens on localhost only) -----------------
sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='lantern'" | grep -q 1 \
  || sudo -u postgres psql -c "CREATE USER lantern WITH PASSWORD 'lantern';"
sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='lantern'" | grep -q 1 \
  || sudo -u postgres psql -c "CREATE DATABASE lantern OWNER lantern;"

# --- .env from SSM, schema, services ----------------------------------------
if [ -n "${DOTENV}" ] && [ "${DOTENV}" != "None" ]; then
  printf '%s\n' "${DOTENV}" > "${REPO_DIR}/tools/azure-runner/.env"
  chown "${APP_USER}:${APP_USER}" "${REPO_DIR}/tools/azure-runner/.env"
  chmod 600 "${REPO_DIR}/tools/azure-runner/.env"
  sudo -u "${APP_USER}" bash -c "cd '${REPO_DIR}/tools/azure-runner' && .venv/bin/python pipeline.py init-db"
else
  echo "WARN: /lantern/dotenv not in SSM — write tools/azure-runner/.env by hand, then run pipeline.py init-db."
fi

cp "${REPO_DIR}/infra/ec2/lantern-orchestrator.service" /etc/systemd/system/
cp "${REPO_DIR}/infra/ec2/lantern-mission-control.service" /etc/systemd/system/
systemctl daemon-reload
if [ -f "${REPO_DIR}/tools/azure-runner/.env" ]; then
  systemctl enable --now lantern-orchestrator lantern-mission-control
fi

set +x
echo "── bootstrap complete ──────────────────────────────────────────────"
systemctl --no-pager status lantern-orchestrator lantern-mission-control || true
