#!/usr/bin/env bash
# Deploy a git ref to the STAGING Mission Control instance (port 8081) — the human
# act behind the `staging_deploy` gate for dogfood runs, where the product is Lantern
# itself. Run on the box:
#
#     bash infra/ec2/deploy-staging.sh <branch-or-sha>      # e.g. feat/20260907-status-json
#
# What it does: keeps a second checkout at ~/lantern-staging fetched from the main
# checkout (so a branch that only exists locally on the box still deploys), moves it to
# the ref, links the main .env (same database — Mission Control is the control plane),
# installs the systemd unit on first use, and restarts the staging service. Then it
# proves the port answers. The main instance on 8080 is untouched.
set -euo pipefail
REF="${1:?usage: deploy-staging.sh <branch-or-sha>}"
MAIN=/home/ubuntu/Agentic-workflow-lantern
STAGING=/home/ubuntu/lantern-staging
UNIT=lantern-mission-control-staging

if [ ! -d "$STAGING/.git" ]; then
  git clone -q "$MAIN" "$STAGING"
fi
cd "$STAGING"
git remote set-url origin "$MAIN"
git fetch -q --prune origin "+refs/heads/*:refs/remotes/origin/*"
# Accept a branch name (resolved against the main checkout's branches) or a sha.
if git rev-parse -q --verify "refs/remotes/origin/$REF" >/dev/null; then
  git checkout -q -B "staging" "refs/remotes/origin/$REF"
else
  git checkout -q -B "staging" "$REF"
fi
HEAD_SHA=$(git rev-parse --short HEAD)
ln -sfn "$MAIN/tools/azure-runner/.env" "$STAGING/tools/azure-runner/.env"

if [ ! -f "/etc/systemd/system/$UNIT.service" ] || ! cmp -s "$MAIN/infra/ec2/$UNIT.service" "/etc/systemd/system/$UNIT.service"; then
  sudo cp "$MAIN/infra/ec2/$UNIT.service" "/etc/systemd/system/$UNIT.service"
  sudo systemctl daemon-reload
fi
sudo systemctl enable -q "$UNIT"
sudo systemctl restart "$UNIT"
# uvicorn takes a few seconds to bind; poll rather than guess.
CODE=000
for _ in $(seq 1 15); do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:8081/login || true)
  [ "$CODE" = "200" ] && break
  sleep 1
done
echo "staging: $REF @ $HEAD_SHA — http://127.0.0.1:8081/login -> HTTP $CODE ($(systemctl is-active "$UNIT"))"
[ "$CODE" = "200" ] || { sudo journalctl -u "$UNIT" -n 20 --no-pager; exit 1; }
