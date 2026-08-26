# Lantern agent sandbox — ONE ephemeral container per stage execution (D10/D12).
#
#   docker build -t lantern-sandbox -f infra/sandbox/Dockerfile .   (repo root)
#
# (.dockerignore keeps the context tiny; the repo itself is NOT baked in — the
# dispatcher mounts it read-only at /repo-src and the entrypoint assembles a
# private copy per run, so image rebuilds are only needed for dependency changes.)
#
# The container runs exactly one stage and exits:
#   entrypoint.sh <run-id> <stage>   →  orchestrator.py <run-id> <stage>
#
# Nothing secret is baked in: credentials arrive as -e vars from the dispatcher's
# allowlist, scoped per stage execution.
#
# v1 scope: stages that need Python + a browser (01-ui-ux.diverge, 02-pre-coding,
# 05/06 review stages). qa stages additionally need tools/qa-recorder's node_modules
# baked — add that when a run first reaches stage 4.

FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive PIP_ROOT_USER_ACTION=ignore
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3.12 python3.12-venv git rsync curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Playwright MCP + a matching browser build, resolved ONCE at image build —
# a stage start must never download anything. Installing `playwright` alongside
# `@playwright/mcp` at the same moment keeps the browser revision in step with the
# MCP's bundled playwright-core. Browsers go to a world-readable shared path
# because the container runs as uid 1000 (below), not root.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN npm install -g @playwright/mcp playwright \
    && npx playwright install --with-deps chromium \
    && chmod -R a+rX /ms-playwright \
    && rm -rf /var/lib/apt/lists/*

COPY tools/azure-runner/requirements.txt /opt/lantern/requirements.txt
RUN python3.12 -m venv /opt/lantern/venv \
    && /opt/lantern/venv/bin/pip install --quiet -r /opt/lantern/requirements.txt

# plain COPY + chmod: --chmod needs BuildKit, which docker.io's legacy builder lacks
COPY infra/sandbox/entrypoint.sh /opt/lantern/entrypoint.sh
RUN chmod 755 /opt/lantern/entrypoint.sh

# The container runs as uid 1000 (the dispatcher passes --user), which on the host
# is `ubuntu` — so files written onto the mounted run dir come out host-owned, not
# root-owned. Found the hard way on 2026-08-26: root-owned artifacts inside the git
# working tree break every later git/file operation for the app user.
RUN mkdir -p /work && chown 1000:1000 /work

# The orchestrator honors LANTERN_PLAYWRIGHT_MCP instead of `npx -y @playwright/mcp@latest`
# so the preinstalled, version-locked binary is used. Exports die with the container —
# the stale-export bug class (2026-08-26) is structurally impossible here. HOME=/work:
# anything that writes to $HOME lands in the ephemeral workspace.
ENV LANTERN_PLAYWRIGHT_MCP="playwright-mcp --headless --isolated" \
    LANTERN_EXPORT_DIR=/work/exports \
    HOME=/work
WORKDIR /work
ENTRYPOINT ["/opt/lantern/entrypoint.sh"]
