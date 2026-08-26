#!/usr/bin/env bash
# Sandbox entrypoint — assemble a private /work, run exactly one stage, exit.
#
#   (dispatched)  entrypoint.sh <run-id> <stage>
#
# Mounts provided by the dispatcher (pipeline.py, LANTERN_EXECUTOR=docker):
#   /repo-src                               Lantern repo checkout, READ-ONLY
#   /work/lantern/workflow/runs/<run-id>    this run's folder only, READ-WRITE
#
# The copy below EXCLUDES workflow/runs, so no other run's artifacts exist inside
# this container at all — cross-run visibility is structurally impossible, not
# just discouraged. Everything else in /work dies with the container (--rm).
#
# Optional product-repo checkout (stages that need the product code):
#   LANTERN_PRODUCT_REPO    clone URL or a mounted mirror path (e.g. /product-src.git)
#   LANTERN_PRODUCT_BRANCH  run branch (default main)
set -euo pipefail
RUN_ID="$1"; STAGE="$2"

# Start as root ONLY to repair mountpoint ownership, then drop to the app uid.
# Docker pre-creates missing mountpoint parents (/work/lantern/workflow/runs/...)
# as root before any process runs, so a container started directly as uid 1000
# cannot write beside them. The chown also descends into the run-dir bind mount,
# which doubles as repair for any root-owned files older images left on the host.
APP_UID="${LANTERN_SANDBOX_UID:-1000}"
if [ "$(id -u)" = "0" ]; then
  mkdir -p /work/lantern/workflow/runs
  chown -R "${APP_UID}:${APP_UID}" /work
  exec setpriv --reuid "${APP_UID}" --regid "${APP_UID}" --init-groups "$0" "$@"
fi

mkdir -p /work/exports
rsync -a --exclude '.venv' --exclude '.git' --exclude 'node_modules' \
      --exclude 'workflow/runs' /repo-src/ /work/lantern/
mkdir -p /work/lantern/workflow/runs   # the run-dir mount already sits below this

if [ -n "${LANTERN_PRODUCT_REPO:-}" ]; then
  git clone --quiet --branch "${LANTERN_PRODUCT_BRANCH:-main}" \
      "${LANTERN_PRODUCT_REPO}" /work/product
fi

exec /opt/lantern/venv/bin/python /work/lantern/tools/azure-runner/orchestrator.py \
     "${RUN_ID}" "${STAGE}" --execution-key "${LANTERN_EXECUTION_KEY:?dispatcher must set LANTERN_EXECUTION_KEY}" \
     --persist-session
