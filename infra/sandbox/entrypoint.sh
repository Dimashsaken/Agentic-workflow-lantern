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
#   LANTERN_PRODUCT_REPO    the mounted mirror path (/product-src.git) — NOT a URL
#                           and NOT credentialed: the host owns the PAT and the fetch
#   LANTERN_PRODUCT_BRANCH  base branch to check out (default main)
#   LANTERN_PRODUCT_ORIGIN  the real origin URL, for messages and the system prompt
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

# qa-recorder deps are baked at image build (rsync excluded node_modules above);
# link them into the fresh copy so `node record-session.mjs` works in QA stages.
if [ -d /opt/lantern/qa-recorder/node_modules ]; then
  ln -sfn /opt/lantern/qa-recorder/node_modules /work/lantern/tools/qa-recorder/node_modules
fi

# Product code, read-only and credential-free: the dispatcher bind-mounts a HOST-side
# bare mirror at /product-src.git (the PAT authenticated the host fetch and is never
# in that mirror's config), and we clone a throwaway working tree from it. Nothing
# here can push, and nothing written here outlives the container.
if [ -n "${LANTERN_PRODUCT_REPO:-}" ]; then
  # The mount is root-owned and we are uid 1000 — without this git refuses it as
  # "dubious ownership" and the stage dies with an unreadable product tree.
  git config --global --add safe.directory "${LANTERN_PRODUCT_REPO}"
  # A bare mirror IS the repo dir; a local-path target (sync_product_mirror uses an
  # on-box checkout as-is) keeps its repo in .git/ — mark both, or the local-path
  # case dies with "dubious ownership in .../.git" and a useless clone error.
  git config --global --add safe.directory "${LANTERN_PRODUCT_REPO}/.git"
  git config --global --add safe.directory /work/product
  # --no-hardlinks: the mount is read-only and on another filesystem; be explicit
  # rather than relying on git's fallback.
  if ! git clone --quiet --no-hardlinks --branch "${LANTERN_PRODUCT_BRANCH:-main}" \
       "${LANTERN_PRODUCT_REPO}" /work/product; then
    echo "FATAL: could not check out ${LANTERN_PRODUCT_ORIGIN:-$LANTERN_PRODUCT_REPO}" \
         "branch ${LANTERN_PRODUCT_BRANCH:-main} — the stage would have planned" \
         "against no product code at all." >&2
    exit 1
  fi
  # Auto-coding (D14): the dispatcher names the run's branch. Put the checkout on it
  # (continuing an existing branch on retry), give commits the bot identity + trailer
  # convention, and mark the checkout writable for orchestrator.py. Still no
  # credentials: the bundle the stage writes into the run folder is the only way
  # code leaves this container, and the HOST pushes it.
  if [ -n "${LANTERN_CODING_BRANCH:-}" ]; then
    git -C /work/product config user.name  "${LANTERN_GIT_AUTHOR_NAME:-lantern-bot}"
    git -C /work/product config user.email "${LANTERN_GIT_AUTHOR_EMAIL:-lantern-bot@users.noreply.github.com}"
    git -C /work/product config commit.gpgsign false
    if git -C /work/product show-ref --verify --quiet "refs/remotes/origin/${LANTERN_CODING_BRANCH}"; then
      git -C /work/product checkout --quiet -b "${LANTERN_CODING_BRANCH}" "origin/${LANTERN_CODING_BRANCH}"
    else
      git -C /work/product checkout --quiet -b "${LANTERN_CODING_BRANCH}"
    fi
    export LANTERN_PRODUCT_WRITABLE=1
  fi
fi

exec /opt/lantern/venv/bin/python /work/lantern/tools/azure-runner/orchestrator.py \
     "${RUN_ID}" "${STAGE}" --execution-key "${LANTERN_EXECUTION_KEY:?dispatcher must set LANTERN_EXECUTION_KEY}" \
     --persist-session
