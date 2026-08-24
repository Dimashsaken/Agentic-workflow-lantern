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
sudo apt-get update && sudo apt-get install -y git unzip
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt-get install -y nodejs
git clone <this-repo> && cd Agentic-workflow-lantern/tools/qa-recorder
npm install && sudo npx playwright install --with-deps chromium webkit firefox
npm install -g @anthropic-ai/claude-code
```

## Claude Code on Azure credits (Microsoft Foundry)

Claude models on Microsoft Foundry are GA and bill as Claude Consumption Units on the
Azure invoice, decrementing MACC like other Azure Marketplace consumption — this is how
the fleet's Claude Code sessions burn the org's Azure credits. Docs:
<https://code.claude.com/docs/en/microsoft-foundry>

```bash
export CLAUDE_CODE_USE_FOUNDRY=1
export ANTHROPIC_FOUNDRY_RESOURCE=<resource-name>     # or ANTHROPIC_FOUNDRY_BASE_URL
export ANTHROPIC_FOUNDRY_API_KEY=<from SSM>           # or Entra ID via az login

# Pin models explicitly — alias defaults can lag what's enabled on the resource,
# and an unpinned fleet fails unpredictably:
export ANTHROPIC_DEFAULT_OPUS_MODEL='<exact model id enabled in Foundry>'
export ANTHROPIC_DEFAULT_SONNET_MODEL='<exact model id>'
export ANTHROPIC_DEFAULT_HAIKU_MODEL='<exact model id>'
```

Azure OpenAI (GPT) deployments are configured separately for `tools/azure-runner` —
they cannot power Claude Code (see `docs/DECISIONS.md` D2).

## Secrets — SSM Parameter Store, nothing on disk

```
/lantern/foundry/api-key
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

## Running a stage headless

Interactive (SSH + tmux) is fine early. For unattended runs:

```bash
cd ~/Agentic-workflow-lantern
claude -p "Use the qa-dev agent for run feat-20260824-bulk-export. Dev URL is in QA_BASE_URL." \
  --permission-mode acceptEdits
```

Wrap in a systemd oneshot or a small queue script per stage as volume grows. Logs to
CloudWatch; a failed stage run should page nobody — it writes BLOCKED and waits.
