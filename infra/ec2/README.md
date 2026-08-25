# EC2 — running the agent fleet

One box is enough to start. Scale to per-stage instances only when queueing actually
hurts.

## Instance

- **Ubuntu 24.04 LTS**, `t3.xlarge` (4 vCPU / 16 GB) — browsers are the memory hog;
  `t3.large` works for non-QA stages.
- 50 GB gp3. No GPU needed — Playwright records video headless in software.
- IAM instance profile with: read on the SSM parameters below, read/write on the
  artifact bucket. No long-lived AWS keys on disk.

## Base setup

```bash
sudo apt-get update && sudo apt-get install -y git unzip python3.12 python3.12-venv
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt-get install -y nodejs
git clone <this-repo> && cd Agentic-workflow-lantern
cd tools/qa-recorder && npm install && sudo npx playwright install --with-deps chromium webkit firefox
cd ../azure-runner && python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
npm install -g @openai/codex   # Codex CLI for headless repo tasks (codex exec)
```

## Azure OpenAI — the fleet's only model provider (D7)

Every agent brain is one of the org's Azure OpenAI deployments; the startup credits
cover it. Session env (values from SSM):

```bash
export AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
export AZURE_OPENAI_API_KEY=<from SSM>
export AZURE_OPENAI_API_VERSION=<current GA version>
export LANTERN_MODEL_REASONING=sol    # stronger deployment: pre-coding, security, debug…
export LANTERN_MODEL_FAST=terra       # volume deployment: QA charter execution
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

Upload: `aws s3 cp videos/<name>.webm s3://<bucket>/lantern/<run-id>/<stage>/`.
Reports link the S3 URL (or a presigned/CloudFront URL if reviewers lack AWS access).
Lifecycle rule: expire run artifacts after 90 days; postmortem-linked videos are
copied to `/lantern/permanent/` first.

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
ExecStart=/home/ubuntu/Agentic-workflow-lantern/tools/azure-runner/.venv/bin/python pipeline.py daemon
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

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
