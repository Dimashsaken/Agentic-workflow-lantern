# azure-runner — the fleet runtime (Azure OpenAI only)

Single model provider by decision (D7): **Azure OpenAI** — the org's startup credits.
Two harnesses, both OpenAI-native, both loading the same `agents/<role>/` knowledge
and `AGENTS.md` contract:

| Harness | Runs | Where |
|---------|------|-------|
| **OpenAI Agents SDK** (`orchestrator.py`) | pipeline stages 1–2, 4–7 + debug lifecycle | EC2 (workstation for Paper-dependent ui-ux work) |
| **Codex CLI** (`codex-config.example.toml`) | stage 3 coding | developer laptops; `codex exec` on EC2 for headless repo tasks |

## Env-var contract (never commit values — see `.env.example`)

```
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
AZURE_OPENAI_API_KEY=<from SSM>
AZURE_OPENAI_API_VERSION=<current GA version>

# Deployment routing — set to whichever of the org's deployments fits each slot:
LANTERN_MODEL_REASONING=sol    # pre-coding, post-coding, security, debug, ui-ux design
LANTERN_MODEL_FAST=terra       # QA charter execution, batch checks, ui-ux divergence

# Runner affinity (docs/plans/ui-ux-agent-paper.md):
LANTERN_RUNNER=ec2                               # 'workstation' on the design machine
LANTERN_PAPER_MCP_URL=http://127.0.0.1:29979/mcp # Paper Desktop's local MCP endpoint

# Execution plane (D10/D12 — EC2 dispatcher only; laptops keep the inprocess default):
LANTERN_EXECUTOR=inprocess          # 'docker' = one sandbox container per stage
LANTERN_MAX_CONCURRENCY=            # default 3 under docker, 1 inprocess
LANTERN_STAGE_TIMEOUT_MIN=45
LANTERN_SANDBOX_CPUS=1.5
LANTERN_SANDBOX_MEMORY=2500m
LANTERN_SANDBOX_IMAGE=lantern-sandbox
LANTERN_SANDBOX_DATABASE_URL=       # DB URL as containers see it (default: host.docker.internal)
LANTERN_PLAYWRIGHT_MCP=             # MCP launch cmd; the sandbox image pins its own

# QA stages (P0.1 — dispatcher host env; containers see uniform QA_BASE_URL/QA_USER/QA_PASS):
LANTERN_QA_DEV_BASE_URL=            # + LANTERN_QA_DEV_USER / LANTERN_QA_DEV_PASS   (SSM /lantern/qa/dev/*)
LANTERN_QA_STAGING_BASE_URL=        # + LANTERN_QA_STAGING_USER / LANTERN_QA_STAGING_PASS
LANTERN_ARTIFACT_BUCKET=            # S3 bucket name; unset = media stays local (dev)

# Product repository (P0.3 — the code the run implements; per-run target overrides these):
LANTERN_PRODUCT_REPO=               # fallback default when a brief/run names none
LANTERN_PRODUCT_BRANCH=main         # fallback default base branch
LANTERN_WORKSPACE_ROOTS=            # dirs the repo picker may scan (D15) - a
                                    # boundary: unset offers nothing, not everything
LANTERN_CODING_BRANCH_PREFIXES=feat,fix,proto   # what agents may push to (D6)
LANTERN_PRODUCT_MIRROR_DIR=         # host mirror cache (default ~/.lantern/product-mirrors)
GITHUB_LANTERN_BOT_TOKEN=           # HOST-ONLY: authenticates the mirror fetch. Never
                                    #   allowlisted into a sandbox, never written into
                                    #   the mirror config that gets mounted.

# Token ledger + spend tripwires (P0.4 — `pipeline.py usage` / `usage-check`):
LANTERN_PRICE_IN_PER_M=4            # $/1M input tokens — PROVISIONAL until Azure
LANTERN_PRICE_CACHED_IN_PER_M=1     #   invoice lines confirm the deployment rates
LANTERN_PRICE_OUT_PER_M=20
LANTERN_DAILY_SPEND_ALARM_USD=50    # rate tripwire (plan §5 v3; ~10x a normal day)
LANTERN_CREDIT_POOL_USD=25000       # pool tripwire: alarms at 25/50/75% drawn
LANTERN_POOL_SPENT_OFFSET_USD=0     # est. credits burned before the ledger existed
LANTERN_ALARM_WEBHOOK=              # Slack-compatible webhook; unset = journal only
```

Deployment names (`sol`, `terra`, …) are org-internal Azure deployment labels — the
runner treats them as opaque strings. If one is clearly the stronger model, it goes in
`REASONING`; measure and swap freely, it's one env var.

## The pipeline runner (the "one call")

`pipeline.py` is the durable concept→live loop (design: `docs/ORCHESTRATION.md`):
a Postgres state machine drives all stages in order, pauses at human gates
(`approvals` rows) for as long as needed, and survives restarts. Conversations
persist per `{run_id}:{stage}` via the Agents SDK's `SQLAlchemySession` in the same
Postgres (`LANTERN_DATABASE_URL`).

```bash
python pipeline.py init-db                      # once
python pipeline.py run workflow/briefs/x.md     # the one call
python pipeline.py daemon                       # service loop (systemd on EC2)
python pipeline.py status | approve | reject | retry
python pipeline.py runboard | render-memory     # re-render the Postgres-backed views
python pipeline.py import-run <run-id>          # backfill a file-era run into the DB
python pipeline.py set-product | set-coding-mode   # per-run product repo + how stage 3 runs (D14)
python pipeline.py usage [--days 7]             # token ledger: per-day + per-run est. spend
python pipeline.py usage-check                  # spend tripwires (hourly systemd timer on EC2)
```

For scripts, `python pipeline.py status --json` prints one JSON object with `runs`
and `pending_gates` arrays; plain `python pipeline.py status` keeps the human-readable
table.

Every stage execution records its token usage on its `stage_executions` row (P0.4):
the Agents SDK usage object in-process, or the container's `LANTERN_USAGE` stdout
line (validated — it shares stdout with agent text) parsed by the dispatcher — a
host-side write either way, so the ledger keeps working when sandboxes lose direct
table access. Executions that crash before reporting stay unmetered; `usage` prints
the count. QA stages (04/07, debug regression) must leave a fresh, non-empty `.webm`
from the current attempt (the orchestrator launches the browser MCP with the
checked-in `saveVideo` config — recording is automatic in every executor); the check
lives in `check_postconditions`, so container, host re-check, and in-process runs
all enforce it. After postconditions pass, the **host** uploads the attempt's videos
to `s3://$LANTERN_ARTIFACT_BUCKET/lantern/<run-id>/<stage>/attempt-<k>/` under the
PIPELINE.md `session-<n>` naming (AWS creds never enter a sandbox; retries never
overwrite earlier attempts' footage), regenerates `media-manifest.json` from the
artifacts table, and deletes the local files.

## Connecting a codebase — and letting the pipeline code in it (D14)

A run works on ONE product repository, the way a developer's coding agent works in one
checkout. Point the run at it and the fleet does the rest:

There are three ways to point a run at a codebase, and they resolve in this order:
**CLI flag → the brief's own field → the box default**.

```markdown
# in the brief (workflow/briefs/<slug>.md)
- **Product repo:** https://github.com/org/repo     # or an on-box path: /home/ubuntu/work/repo
- **Base branch:** main                             # what work branches FROM, what the PR targets
- **Working branch:**                               # blank = a fresh feat/<date>-<slug> for this run
- **Coding mode:** auto                             # human (default) | auto
```

```bash
# or on the command line
python pipeline.py repos                             # git repos THIS host can offer
python pipeline.py run workflow/briefs/x.md --product-repo https://github.com/org/repo --coding-mode auto
python pipeline.py set-product <run-id> --repo <url-or-path> --branch main   # an existing run
python pipeline.py set-product <run-id> --repo <url-or-path> --branch main \
                   --working-branch feat/20260901-thing                      # continue a branch
python pipeline.py set-coding-mode <run-id> auto
```

**Or from the browser (D15):** Mission Control's run page links to `/run/<run-id>/repo`,
which lists the git repositories on **the host serving that page** — the box, a
workstation, a laptop — with their current branch, plus a field for a remote URL. Pick
a repo, load its branches, choose the base and (optionally) an existing working branch,
and save. The picker only looks inside `LANTERN_WORKSPACE_ROOTS`; unset means it offers
nothing, falling back to `~/work` when that exists. That is deliberate — whatever path
is admitted becomes a run's product tree, so an unconfined picker would be a
filesystem-read primitive behind a login form.

**Base vs working branch.** `product_branch` is the base. `product_working_branch` is
where commits land; leave it unset and the branch is derived from the run id, exactly as
before D15. A chosen branch must sit inside the `feat/*|fix/*|proto/*` namespace D6 lets
agents push to (`LANTERN_CODING_BRANCH_PREFIXES`) and is refused at selection time
otherwise. When a run continues a branch that already has commits, only the commits
**that execution** adds count as its work — the stage is failed if it adds none, even
though the branch differs from the base.

What "connected" means, stage by stage:

- The host keeps a bare mirror of the repo (`GITHUB_LANTERN_BOT_TOKEN` authenticates
  the fetch for private GitHub repos; a local path needs no token). Every sandbox gets a
  throwaway clone of that mirror — read-only for stages 1–2 and 4–7
  (`read_file('product/…')`, `product_git`).
- Every stage's system prompt ends with the codebase itself (D15): an `<env>` block
  (repo, origin, base, the branch this run works on, working-tree state, recent
  commits), the repo's own `AGENTS.md`/`CLAUDE.md`/`README.md` auto-loaded and capped at
  ~6k chars, and what that stage is there to do. Those docs are fenced as **reference
  material, not instructions** — they are authoritative for the codebase's conventions
  and powerless over the Lantern contract, because they come from a repository a user
  chose and land above the role's own charter.
- **Stage 3 in `auto` mode gets the same clone writable**, on the run's branch
  (`feat/<date>-<slug>`, `fix/…` for bug runs, or an existing branch chosen for the
  run), plus `product_shell` — one shell command
  at a time inside the checkout (run the tests, build, `git commit`). Those conventions
  win over Lantern's. There is
  still no credential in the sandbox: when the agent finishes, the harness bundles the
  committed branch into `03-coding/handoff.json` + `branch.bundle`, and the HOST verifies
  the bundle carries exactly that branch, pushes it as the bot identity, and opens the
  pull request (GitHub) — `03-coding/pr.md` records it and the `code_complete` gate
  shows it in Mission Control. Non-GitHub https remotes get the branch pushed without a
  PR; local-path repos get the branch landed in place.
- `human` mode is unchanged: the developer codes in their own session and approves
  `code_complete` themselves.

For a product repo to work in auto mode it must be reachable from the box (an https
URL the token can read, or a local path), its base branch must exist, and its build and
test commands must be discoverable from `AGENTS.md`/`README` (the sandbox image has
Python 3.12, Node 22 and git; other toolchains need an image change). Knobs:
`LANTERN_CODING_TIMEOUT_MIN` (120), `LANTERN_CODING_MAX_TURNS` (400),
`LANTERN_PRODUCT_SHELL_TIMEOUT` (900 s per command), `LANTERN_GIT_AUTHOR_NAME/EMAIL`
(`lantern-bot`), `LANTERN_PUBLIC_URL` (Mission Control URL, linked from PRs). Proof:
`test_coding_stage.py` (no database). Still open, stated plainly: sandbox egress is not
yet allowlisted (plan item C2.5) and the sandbox DB role is not yet restricted (C2.0) —
run auto mode on repos you trust until they land.

## Direct consult — use one agent, no run (D11)

```bash
python pipeline.py agents                                  # what can I ask?
python pipeline.py ask security "Is storing the QA creds in SSM enough for staging?"
python pipeline.py ask security "what about rotation?"     # continues the same conversation
python pipeline.py ask ui-ux "critique this flow idea" -i  # live loop; empty line ends
python pipeline.py ask qa-dev "..." --session bulk-export  # named parallel thread
python pipeline.py ask qa-dev "..." --new                  # forget the thread, start over
```

The role's charter/skills/memory load into the system prompt, the agent can read the
whole repo (and browser roles get the Playwright MCP — `--no-browser` to skip), and
conversation state persists in Postgres per `{you}:{role}:{session}`. Consults are
advisory and read-only by design; producing or changing artifacts is pipeline-run work.

The same consults run in the browser: **`chat_service.py`** powers Mission
Control's Chat tab (docs/CHAT.md, D13) — same session store (a CLI thread whose
`{you}:{role}:{session}` matches continues on the web), plus the `lantern`
orchestrator chat (read-only DB tools + `ask_specialist`), user-created custom
agents (`custom_agents` table), a per-turn token ledger (`chat_turns`), and live
SSE streaming. `test_chat_service.py` covers the turn lifecycle with a faked
model loop — no Azure credentials needed.

Role memory consolidation (roughly monthly): merge the rendered rows below the marker
in `agents/<role>/memory.md` up into the hand-written base, then mark them done and
re-render:

```sql
UPDATE role_memory SET consolidated = true WHERE role = '<role>' AND created_at < '<date>';
```

### Runner affinity — the design workstation daemon

Paper's MCP server is desktop-bound, so stage 1 is split (D9): `01-ui-ux.diverge`
runs on EC2 with `LANTERN_MODEL_FAST`; `01-ui-ux.design` (Paper convergence) is
claimed only by a daemon started with `--runner workstation`. Setup on the design
machine (once):

1. Install Paper Desktop, sign in, open the team file `Lantern` (its MCP server
   listens on `http://127.0.0.1:29979/mcp` while the file is open).
2. `pip install -r requirements.txt`; copy `.env.example` → `.env` with
   `LANTERN_RUNNER=workstation` and a `LANTERN_DATABASE_URL` that reaches the EC2
   Postgres (Tailscale recommended) plus the Azure OpenAI vars.
3. Run `python pipeline.py daemon --runner workstation`.

The daemon preflights Paper at startup (exits with instructions if the Desktop app
isn't up) and re-checks every tick — it never claims a stage it would fail mid-run.
Daemons heartbeat into the `runners` table; Mission Control uses that to show
"needs the design workstation" instead of a silent stall when the daemon is offline.

## The stage orchestrator

`orchestrator.py` runs **one stage of one run** per invocation (used directly for
manual/debug work; `pipeline.py` reuses its internals) — deterministic pipeline
control stays in code/humans, the model only gets autonomy *inside* a stage:

```bash
python orchestrator.py feat-20260824-bulk-export 04-qa-dev
```

What it does:

1. Renders the role's `memory.md` fresh from the `role_memory` table, then builds the
   system prompt: `AGENTS.md` core rules + the role's `charter.md` + `skills.md` +
   `memory.md` + the run/stage assignment.
2. Creates an Agents SDK `Agent` on the role's routed deployment, with tools:
   file read/write scoped to the repo (rejects the rendered views RUNBOARD.md and
   memory.md), `append_memory` bound to this execution, the Playwright MCP server for
   browser roles, and shell access only where the role's charter needs it.
3. Runs the loop, then **enforces the two written postconditions** (stage report
   exists + claimed artifacts are real, memory row inserted by THIS execution) —
   failing loudly if the model skipped one. Sound under concurrent runs:
   `test_verification.py` is the proof.

**Requires Postgres** (`LANTERN_DATABASE_URL` + `pipeline.py init-db` once) even for
one-off stage runs — role memory lives in the database. `pip install -r requirements.txt`.

### Local dev Postgres on Windows (no admin, no service)

Portable binaries from EDB, kept outside the OneDrive-synced repo:

```powershell
# once: download + extract https://get.enterprisedb.com/postgresql/postgresql-16.9-1-windows-x64-binaries.zip
#       to %USERPROFILE%\.lantern\pgsql, then:
& "$env:USERPROFILE\.lantern\pgsql\bin\initdb" -U lantern -A trust -E UTF8 -D "$env:USERPROFILE\.lantern\pgdata"
& "$env:USERPROFILE\.lantern\pgsql\bin\pg_ctl" -D "$env:USERPROFILE\.lantern\pgdata" -l "$env:USERPROFILE\.lantern\pg.log" start
& "$env:USERPROFILE\.lantern\pgsql\bin\createdb" -U lantern -h localhost lantern
# every reboot: just the pg_ctl ... start line
```

The default `LANTERN_DATABASE_URL` (`postgresql+asyncpg://lantern:lantern@localhost:5432/lantern`)
matches this setup as-is.

## Codex CLI for developers (stage 3)

Copy `codex-config.example.toml` into `~/.codex/config.toml`, fill in the resource
name, and export `AZURE_OPENAI_API_KEY`. Codex reads the product repo's `AGENTS.md`
natively; Lantern's coding conventions (`agents/coding/skills.md`) apply as before.
Check Codex's docs for the current `api-version` value when setting up.

## MCP wiring

The shared server list lives in `.mcp.json` (repo root) as the single reference.
- Agents SDK: servers are attached in `orchestrator.py` (stdio/HTTP per server).
- Codex CLI: mirror the needed servers into `~/.codex/config.toml` (`[mcp_servers]`).

Video recording stays harness-independent: it's a property of the Playwright browser
context (`tools/qa-recorder`), so QA videos work identically under every option above.
