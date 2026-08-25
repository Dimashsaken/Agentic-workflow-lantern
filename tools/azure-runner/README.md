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
LANTERN_MODEL_REASONING=sol    # pre-coding, post-coding, security, debug, ui-ux options
LANTERN_MODEL_FAST=terra       # QA charter execution, batch checks
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
```

## The stage orchestrator

`orchestrator.py` runs **one stage of one run** per invocation (used directly for
manual/debug work; `pipeline.py` reuses its internals) — deterministic pipeline
control stays in code/humans, the model only gets autonomy *inside* a stage:

```bash
python orchestrator.py feat-20260824-bulk-export 04-qa-dev
```

What it does:

1. Builds the system prompt: `AGENTS.md` core rules + the role's `charter.md` +
   `skills.md` + `memory.md` + the run/stage assignment.
2. Creates an Agents SDK `Agent` on the role's routed deployment, with tools:
   file read/write scoped to the repo, the Playwright MCP server for browser roles,
   and shell access only where the role's charter needs it.
3. Runs the loop, then **enforces the three postconditions** (stage report exists,
   memory appended, runboard row updated) — failing loudly if the model skipped one.

Status: **scaffold** — reviewed but not yet exercised on EC2; expect to tune tool
scoping and the api-version pin on first real run. `pip install -r requirements.txt`.

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
