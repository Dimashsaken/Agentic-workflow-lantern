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
```

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
