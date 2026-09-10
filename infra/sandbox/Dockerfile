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
# v2 scope (P0.1): v1 (Python + browser stages) PLUS the QA stages — tools/qa-recorder
# deps and the video-recording MCP config are baked so stage 4/7 runs record video with
# zero downloads at stage start. AWS credentials are deliberately NOT here and never
# cross the env allowlist: the dispatcher uploads media to S3 after the container exits.

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
# VERSIONS ARE PINNED. Unpinned `npm install -g` drifted the MCP to a build that
# demands a different browser distribution than the one baked here, breaking every
# browser stage at runtime (found 2026-08-26). Bump deliberately, then re-run
# infra/sandbox/prove_video.sh — MCP video behavior is not covered by semver.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN npm install -g @playwright/mcp@0.0.79 playwright@1.62.1 \
    && npx playwright install --with-deps chromium \
    && playwright-mcp install-browser chrome-for-testing \
    && chmod -R a+rX /ms-playwright \
    && rm -rf /var/lib/apt/lists/*

COPY tools/azure-runner/requirements.txt /opt/lantern/requirements.txt
RUN python3.12 -m venv /opt/lantern/venv \
    && /opt/lantern/venv/bin/pip install --quiet -r /opt/lantern/requirements.txt

# QA stages (04-qa-dev, 07-qa-staging, debug regression): qa-recorder deps resolved at
# build time; the entrypoint links them into the per-run repo copy (rsync excludes
# node_modules). Placed AFTER the pip layer so a package.json bump never invalidates
# the venv cache. `npx playwright install chromium` fetches the browser revision
# qa-recorder's OWN playwright version wants into the shared /ms-playwright — it may
# coexist with the MCP's revision; disk is the only cost. The chmod is targeted: a
# blanket `chmod -R /ms-playwright` here would overlayfs-copy-up the entire earlier
# browser layer (~hundreds of MB duplicated); only revision dirs this step ADDED
# (newer than the marker file) need their bits fixed.
# (Video recording config is NOT baked: the orchestrator points the MCP at the
# checked-in infra/sandbox/qa-mcp-config.json inside the repo copy.)
# The marker is touched INSIDE this RUN — a COPYed file keeps its host mtime, which
# predates the earlier browser layer's dirs on cache-cold builds and would sweep
# (and overlayfs-duplicate) the whole tree.
COPY tools/qa-recorder/package.json /opt/lantern/qa-recorder/package.json
RUN touch /tmp/.qa-build-marker \
    && cd /opt/lantern/qa-recorder && npm install \
    && npx playwright install chromium \
    && chmod -R a+rX /opt/lantern/qa-recorder \
    && find /ms-playwright -mindepth 1 -maxdepth 1 -newer /tmp/.qa-build-marker \
         -exec chmod -R a+rX {} + \
    && rm /tmp/.qa-build-marker

# plain COPY + chmod: --chmod needs BuildKit, which docker.io's legacy builder lacks
COPY infra/sandbox/entrypoint.sh /opt/lantern/entrypoint.sh
# Windows checkouts may supply CRLF; normalize the executable shebang in the
# image so a build from Git for Windows starts identically to a Linux build.
RUN sed -i 's/\r$//' /opt/lantern/entrypoint.sh \
    && chmod 755 /opt/lantern/entrypoint.sh

# The container runs as uid 1000 (the dispatcher passes --user), which on the host
# is `ubuntu` — so files written onto the mounted run dir come out host-owned, not
# root-owned. Found the hard way on 2026-08-26: root-owned artifacts inside the git
# working tree break every later git/file operation for the app user.
RUN mkdir -p /work && chown 1000:1000 /work

# The orchestrator honors LANTERN_PLAYWRIGHT_MCP instead of `npx -y @playwright/mcp@latest`
# so the preinstalled, version-locked binary is used. Exports die with the container —
# the stale-export bug class (2026-08-26) is structurally impossible here. HOME=/work:
# anything that writes to $HOME lands in the ephemeral workspace.
# --browser chromium: without it the MCP hunts for a system Google Chrome at
# /opt/google/chrome and dies; with it, it uses the chrome-for-testing build above.
ENV LANTERN_PLAYWRIGHT_MCP="playwright-mcp --headless --isolated --browser chromium" \
    LANTERN_EXPORT_DIR=/work/exports \
    HOME=/work
WORKDIR /work
ENTRYPOINT ["/opt/lantern/entrypoint.sh"]
