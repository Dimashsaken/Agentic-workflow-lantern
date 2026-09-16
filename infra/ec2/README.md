# EC2 — running the agent fleet

One box is enough to start. Scale to per-stage instances only when queueing actually
hurts.

## Instance

- **Ubuntu 24.04 LTS**, `t3.xlarge` (4 vCPU / 16 GB) — browsers are the memory hog;
  `t3.large` works for non-QA stages.
- **Sizing for concurrency (D10).** One container per stage execution, and browser
  stages want ~2 GB each. `t3.xlarge` realistically supports ~4 concurrent sandboxes
  with Postgres and Mission Control on the same box; for ~5 developers in parallel plan
  on `m5.2xlarge` (8 vCPU / 32 GB) or cap dispatcher concurrency explicitly. Cap it
  deliberately either way — an unbounded dispatcher will thrash the box long before
  Postgres notices.
- 50 GB gp3. No GPU needed — Playwright records video headless in software.
- IAM instance profile with: read on the SSM parameters below, read/write on the
  artifact bucket (write for the dispatcher's uploads, read for the video links
  Mission Control signs). No long-lived AWS keys on disk.

## Base setup — one script

Everything the box needs is `bootstrap.sh` (idempotent — node, Codex CLI, Python
venv, Playwright browsers, Postgres 16, systemd units). Paste it as instance
**user-data** at launch, or on a running box:

```bash
sudo bash infra/ec2/bootstrap.sh
```

Then the three manual steps it prints: real DB password + `.env` (from SSM),
`pipeline.py init-db`, `systemctl enable --now lantern-orchestrator
lantern-mission-control`.

## Azure OpenAI — the fleet's only model provider (D7)

Every agent brain is one of the org's Azure OpenAI deployments; the startup credits
cover it. Session env (values from SSM):

```bash
export AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
export AZURE_OPENAI_API_KEY=<from SSM>
export AZURE_OPENAI_API_VERSION=<current GA version>
export LANTERN_MODEL_REASONING=gpt-5.6-sol    # frontier size: planning, review, security, debug… (D26)
export LANTERN_MODEL_CODING=gpt-5.6-terra     # mid size: the auto-mode builders
export LANTERN_MODEL_FAST=gpt-5.6-luna        # cheap size: QA charter execution, ui-ux divergence
# All three are deployed on lantern-agentic-foundry (2026-09-14); the endpoint above must name it.
```

Codex CLI on EC2 uses the same key via `tools/azure-runner/codex-config.example.toml`
copied to `~/.codex/config.toml`.

## Secrets — SSM Parameter Store, nothing on disk

```
/lantern/azure-openai/api-key
/lantern/github/bot-token          → GITHUB_LANTERN_BOT_TOKEN (gh + github MCP)
/lantern/posthog/personal-api-key  → POSTHOG_PERSONAL_API_KEY (posthog MCP)
/lantern/qa/dev/{base-url,user,pass}
/lantern/qa/staging/{base-url,user,pass}
```

A small profile script fetches these into the session environment at start
(`aws ssm get-parameter --with-decryption`). `.env` files are a local-dev convenience
only.

## Artifact bucket

```
s3://<bucket>/lantern/<run-id>/<stage>/<file>.webm
```

**Uploads are host-side (P0.1):** after a sandbox exits and postconditions pass, the
dispatcher uploads THIS attempt's `.webm` files (`aws` CLI via the instance role —
AWS credentials never cross into a sandbox) to
`s3://<bucket>/lantern/<run-id>/<stage>/attempt-<k>/<run-id>--<stage>--session-<n>.webm`
— attempt-prefixed so a retry never overwrites earlier evidence, session-numbered in
recording order (the MCP names files itself). It records an `artifacts` row per file,
regenerates `media-manifest.json` next to the report FROM those rows (never merged
from the agent-writable run dir), and deletes the local copies. Set `LANTERN_ARTIFACT_BUCKET` in the daemon env. A report may name the S3
URL; Mission Control links every video through `/media`, which signs a 15-minute URL with
the instance role when it is clicked, so reviewers need no AWS access and the bucket stays
private (docs/MISSION-CONTROL.md, "QA videos: signed links"). Lifecycle rule:
expire run artifacts after 90 days; postmortem-linked videos are copied to
`/lantern/permanent/` first.

## The execution plane — sandbox per stage (D10/D12)

The EC2 daemon runs as a **dispatcher** (`LANTERN_EXECUTOR=docker`, set in the systemd
unit): it claims work and runs each stage in an ephemeral `lantern-sandbox` container
with CPU/memory caps, a wall-clock timeout, a per-stage env allowlist (never a `.env`
in the image), and exactly one run folder mounted read-write.

```bash
sudo apt-get install -y docker.io && sudo usermod -aG docker ubuntu
# Postgres must also listen on the docker bridge for sandboxes:
#   postgresql.conf: listen_addresses = 'localhost,172.17.0.1'
#   pg_hba.conf:     host lantern lantern 172.17.0.0/16 scram-sha-256
cd ~/Agentic-workflow-lantern
sudo docker build -t lantern-sandbox -f infra/sandbox/Dockerfile .
bash infra/sandbox/prove_isolation.sh     # the D12 proof battery — run after every image change
bash infra/sandbox/prove_video.sh         # P0.1: proves an MCP session really records a .webm
```

**After ANY code deploy, restart the daemon** — it is a long-lived Python process
that loaded `pipeline.py` at startup, so a `git pull` alone changes nothing it
executes (sandboxes rsync the checkout fresh, so *they* get new code immediately —
which makes the mismatch silent and confusing: new agent behavior, old dispatcher).
Bit us 2026-08-27, when two stages ran with a ledger-less dispatcher:

```bash
sudo systemctl restart lantern-orchestrator
```

Dispatcher knobs (environment of the daemon):

```
LANTERN_EXECUTOR=docker            # 'inprocess' = laptop/workstation mode
LANTERN_MAX_CONCURRENCY=2          # sandboxes in flight; see sizing below
LANTERN_STAGE_TIMEOUT_MIN=45       # wall clock per stage, then docker kill
LANTERN_SANDBOX_CPUS=1.5  LANTERN_SANDBOX_MEMORY=2500m
LANTERN_SANDBOX_IMAGE=lantern-sandbox
LANTERN_SANDBOX_DATABASE_URL=      # default: LANTERN_DATABASE_URL with host.docker.internal
LANTERN_ARTIFACT_BUCKET=           # media uploads after each stage (see Artifact bucket)
LANTERN_QA_DEV_BASE_URL=           # + _USER/_PASS from SSM /lantern/qa/dev/* — QA stages
LANTERN_QA_STAGING_BASE_URL=       # + _USER/_PASS from /lantern/qa/staging/*
LANTERN_PRODUCT_REPO=              # default product target (a run's own target wins)
LANTERN_PRODUCT_BRANCH=main        # default base branch
LANTERN_PRODUCT_MIRROR_DIR=        # host mirror cache (default ~/.lantern/product-mirrors)
GITHUB_LANTERN_BOT_TOKEN=          # HOST-ONLY — authenticates the mirror fetch and the
                                   #   branch push / PR of auto-coding (D14); never
                                   #   allowlisted into a sandbox, never in the mirror config
LANTERN_CODING_TIMEOUT_MIN=120     # wall clock for an auto-coding stage (D14)
LANTERN_CODING_MAX_TURNS=400       # agent turns for the coding loop
LANTERN_PUBLIC_URL=                # Mission Control URL, linked from agent-opened PRs
```

**Before stage 4's first run, preflight the target:**

```bash
cd ~/Agentic-workflow-lantern/tools/azure-runner && .venv/bin/python pipeline.py qa-preflight
```

To point a QA stage at an app you just started (say Tender on the docker bridge), write the
target with the command instead of editing `.env` by hand — it replaces the URL in place,
sets the QA login, regenerates the password when the user changes, and never prints a value.
`.env` wins over SSM for these names (the daemon fills only unset ones from SSM), so what the
file says IS the target; restart the daemon afterwards, when no stage is executing:

```bash
.venv/bin/python pipeline.py qa-target qa-dev --base-url http://172.17.0.1:8000 --user qa@tender.test
```

It fills `LANTERN_QA_DEV_*` from SSM (`/lantern/qa/dev/{base_url,user,pass}` — the
daemon does the same at startup, so the documented SSM path no longer needs a
hand-copied `.env`), then checks reachability **from a sandbox container**, not just
from the host. That last check is the one that decides whether stage 4 works: a dev
environment on localhost, behind Tailscale only, or inside a VPC the container network
cannot see will pass a host curl and still fail the stage.

**QA stages (image v2, P0.1):** the sandbox image bakes `tools/qa-recorder`'s deps;
video recording is configured by the ORCHESTRATOR itself — for QA stages it reads the
`infra/sandbox/qa-mcp-config.json` template, injects the run's mounted `media/` dir as
`browser.contextOptions.recordVideo.dir`, and launches the MCP with that config, so
every browser session leaves a `.webm` on the host in every executor (sandbox,
in-process, manual). **The MCP's own top-level `saveVideo` key is inert** — accepted
and silently records nothing (verified on 0.0.79); the `recordVideo` passthrough is
what works, which is why `@playwright/mcp` and `playwright` are version-pinned in the
Dockerfile and the MCP's `chrome-for-testing` browser is installed at build time.
The video postcondition (a fresh, non-empty `.webm` from the current attempt) is
enforced in `check_postconditions` at all three verdict sites; uploads happen after it
passes (above). The QA target must be reachable from the docker bridge network. After
any image change or MCP bump, re-run `prove_isolation.sh` AND `prove_video.sh` — the
MCP's config keys are upstream's, not ours, and a config that looks right is not
evidence.

**Sizing (2026-08-26, this t3.large — 2 vCPU / 8 GB, sharing Postgres + Mission
Control):** the cap is **2**, not the 3 the plan hoped for. What was actually
measured: two dispatcher-driven diverge sandboxes ran concurrently at ~200 MiB each
(browser idle). The cap is set by the 2.5 GB per-container memory limit that
browser-active stages (design/QA) need headroom for: 2 × 2.5 GB + system + Postgres +
Mission Control fits in 8 GB; 3 × 2.5 GB does not. `t3.xlarge` supports 3–4;
`m5.2xlarge` for five developers in parallel. Raise the cap only together with the
instance size.

**Deferred, deliberately:** per-container egress allowlisting (needs a container
network + nftables or a proxy; must land before any stage touches untrusted
third-party input) — see D12.

## The first product run — `infra/ec2/tender-playbook.sh`

One command per human step for carrying `feat-20260911-tender-onboarding` (the Tender
WhatsApp assistant, product branch `product/tender-whatsapp`) through the pipeline:
`deploy` (fetch the branch, migrate, lint, restart the services), `start` (create the
run), `status`, `serve dev|staging <branch>` (run Tender for stages 4 and 7 on the
docker bridge and register it with the daemon), `approve <gate>`. Gates stay human.

## Postgres + the pipeline daemon (docs/ORCHESTRATION.md)

```bash
sudo apt-get install -y postgresql-16
sudo -u postgres psql -c "CREATE USER lantern WITH PASSWORD '<from SSM>';"
sudo -u postgres psql -c "CREATE DATABASE lantern OWNER lantern;"
export LANTERN_DATABASE_URL=postgresql+asyncpg://lantern:<pw>@localhost:5432/lantern
cd ~/Agentic-workflow-lantern/tools/azure-runner && .venv/bin/python pipeline.py init-db
```

systemd unit (`/etc/systemd/system/lantern-orchestrator.service`):

```ini
[Unit]
Description=Lantern pipeline orchestrator
After=network.target postgresql.service

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/Agentic-workflow-lantern/tools/azure-runner
ExecStart=/home/ubuntu/Agentic-workflow-lantern/tools/azure-runner/.venv/bin/python pipeline.py daemon --runner ec2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

The EC2 daemon claims only `ec2`-affinity stages. The Paper-bound `01-ui-ux.design`
execution needs a second daemon on the design workstation — setup in
`tools/azure-runner/README.md` ("Runner affinity"); it is a plain terminal process
there, not a systemd unit.

## Staging instance — the stage-7 target (dogfood runs)

When the product IS Lantern, "deploy to staging" means running the candidate build of
Mission Control on a second port. `lantern-mission-control-staging.service` serves
`~/lantern-staging` (a second checkout) on **8081** against the same database with the
main checkout's `.env`; the human at the `staging_deploy` gate deploys with:

```bash
bash infra/ec2/deploy-staging.sh <branch-or-sha>     # e.g. main, or feat/20260907-status-json
```

The script fetches the ref from the main checkout, restarts the unit, and proves the
port answers. QA stage 7 reaches it on the docker bridge —
`LANTERN_QA_STAGING_BASE_URL=http://172.17.0.1:8081` with the QA user — exactly like
stage 4 reaches the main instance on `http://172.17.0.1:8080`.

## Outside access

The security group allows **8080 and 8081 from anywhere** (opened 2026-09-07 so the
CTO can test) and 22 from named IPs only. Mission Control is behind its login
(`LANTERN_WEB_USERS`), but it is plain HTTP: put CloudFront/ALB with TLS (or Tailscale)
in front before anyone types a password on a network they do not own, and narrow the
rules back to named IPs when the demo is over:

```bash
aws ec2 revoke-security-group-ingress --group-id sg-0b3dd42bc8b77c474 \
  --ip-permissions 'IpProtocol=tcp,FromPort=8080,ToPort=8080,IpRanges=[{CidrIp=0.0.0.0/0}]'
```

## Spend tripwires (P0.4)

The token ledger lives on `stage_executions`; `pipeline.py usage` reports it. The
hourly timer runs the two alarms from the plan (§5): daily-rate
(`LANTERN_DAILY_SPEND_ALARM_USD`, default 500) and credit-pool drawdown
(25/50/75% of `LANTERN_CREDIT_POOL_USD`), deduped through the `events` table and
delivered to `LANTERN_ALARM_WEBHOOK` (Slack-compatible) or the journal:

```bash
sudo cp infra/ec2/lantern-usage-check.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now lantern-usage-check.timer
```

Dollar figures are estimates from `LANTERN_PRICE_*_PER_M` env rates until real Azure
invoice lines confirm them; token counts are exact.

## Running a stage headless

Interactive (SSH + tmux) is fine early. For unattended runs, the orchestrator runs
exactly one stage per invocation and verifies the AGENTS.md postconditions itself:

```bash
cd ~/Agentic-workflow-lantern/tools/azure-runner
.venv/bin/python orchestrator.py feat-20260824-bulk-export 04-qa-dev
```

For repo-editing tasks outside the pipeline (maintenance, one-offs), Codex headless:

```bash
codex exec "Consolidate agents/qa-dev/memory.md per the memory protocol in AGENTS.md"
```

Wrap in a systemd oneshot or a small queue script per stage as volume grows. Logs to
CloudWatch; a failed stage run should page nobody — it writes BLOCKED and waits.

## Deploying D16/D17 (model stack, story stage, quality gate)

No sandbox image rebuild: `factory.py` and the new roles are plain repo files, and the
entrypoint rsyncs the repo copy into every container. What changes on the box:

1. Ship the commit (bundle over scp or `git pull --ff-only`), then `pipeline.py init-db`
   (idempotent; only a comment changed in `schema.sql`).
2. Put the model stack in SSM `/lantern/dotenv` and the box `.env`:
   `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY` of `lantern-agentic-foundry` (the
   resource with all three GPT-5.6 sizes since 2026-09-14; the box's previous resource,
   `lantern-prod-agent`, was retired on 2026-09-15), `LANTERN_MODEL_REASONING=gpt-5.6-sol`,
   `_CODING=gpt-5.6-terra`, `_FAST=gpt-5.6-luna` (D26; a var naming a deployment the
   endpoint lacks fails its stages), `LANTERN_EFFORT_*`, `LANTERN_PRICE_JSON` (the three
   rates, `tools/azure-runner/.env.example`), `LANTERN_FIX_ROUNDS=3`.
3. **Restart the daemon** — it loads `pipeline.py` at start, and the stage table now
   begins at `00-story.scout` (`PIPELINE_VERSION=3`). Runs already past stage 0 keep
   their `current_stage` keys unchanged; new runs start with the researcher.
4. Product repos need a `lantern.toml` (`workflow/templates/lantern.toml`) for the
   coding gate to run anything; without one the gate is green with nothing configured
   and the coding agent is told so in its prompt.
