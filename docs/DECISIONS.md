# Architecture Decisions

Read before changing the design. Append-dated; never rewrite old entries — supersede them.

## D1 — 2026-08-24 — Agent knowledge is harness-agnostic files

Each role is `charter.md` + `skills.md` + `memory.md` under `agents/<role>/`. Claude
Code subagents (`.claude/agents/`) are thin wrappers that load these; the Azure runner
loads the same files into its system prompt. **Why:** the fleet spans two model
providers and three execution surfaces (laptop, EC2 interactive, EC2 headless);
duplicating role knowledge per harness would drift immediately. **Consequence:**
wrappers must stay thin — role content added to a wrapper instead of the role folder
is a bug.

## D2 — 2026-08-24 — Provider matrix: Foundry for Claude Code, Azure OpenAI for the runner *(amended by D7)*

Verified against official docs (claude-code third-party integrations, 2026-08):

| Need | Provider | Why |
|------|----------|-----|
| Claude Code sessions/subagents | Claude via **Microsoft Foundry** (`CLAUDE_CODE_USE_FOUNDRY=1`) | Claude Code runs Claude models only (Anthropic API / Bedrock / Vertex / Foundry). Foundry bills CCUs on the Azure invoice and decrements MACC → uses the org's Azure credits. |
| GPT-driven stages (browser QA execution etc.) | **Azure OpenAI** deployments via `tools/azure-runner` | Uses the same Azure credits; an Azure OpenAI key cannot power Claude Code. |

Model pinning on Foundry is mandatory for fleet machines (alias defaults can lag the
resource's enabled models). Config: `infra/ec2/README.md`.

## D3 — 2026-08-24 — QA video = Playwright `recordVideo`, not screen capture

Videos come from Playwright's context-level `recordVideo` (+ tracing), which works
headless on EC2 with no display, GPU, or ffmpeg. **Why:** zero-infra, per-scenario
files, works identically under every harness because recording is a property of the
browser context, not the model driving it. Full-desktop xvfb+ffmpeg capture is the
documented exception, not the default. **Consequence:** videos are per-context — the
"one context per scenario" convention in `tools/qa-recorder` is load-bearing for
reviewable, short videos.

## D4 — 2026-08-24 — The run folder is the only handoff channel

Stages communicate exclusively through `workflow/runs/<run-id>/` reports. No chat
handoffs, no side channels. **Why:** durable, auditable, resumable by any harness, and
it forces each stage to write for a reader — which is also what makes the pipeline
debuggable when a stage goes wrong. Large binaries (videos) live in S3 and are linked,
keeping git fast.

## D5 — 2026-08-24 — Brain/harness split: Claude Code (Foundry) is the default harness; GPT runs in its own harness *(superseded by D7)*

An agent = brain (LLM) + harness (tool loop). Claude Code is a harness that accepts
only Claude brains; "GPT brain inside Claude Code" does not exist. Therefore:
**default all pipeline stages to Claude brain + Claude Code harness via Foundry**
(zero harness code, native subagents/MCP/CLAUDE.md, same Azure credit pool), and run
GPT deployments (`sol`/`terra`) through the OpenAI Agents SDK in `tools/azure-runner`
only where a high-volume second brain earns its keep (bulk QA execution, batch
checks). Both harnesses consume the same MCP tool layer (`.mcp.json`), so tools are
written once. **Consequence:** build order is Foundry fleet first; azure-runner is
deferred until a GPT-driven stage is actually scheduled. Full explanation:
`docs/AGENT-TOOLING.md` §1.

## D6 — 2026-08-24 — Agents act on GitHub as `lantern-bot`, never as humans

One machine identity (machine user now, GitHub App if audit needs grow) with Write on
product repos; fine-grained PAT in SSM. Branch protection enforces the contract:
`main`/`staging` are PR-only with human review; agents push only `feat/*`, `fix/*`,
`proto/*`. Commits carry the run-ID prefix plus a `Lantern-Agent: <role>` trailer;
agent PRs are labeled `agent:<role>`. **Why:** clean audit trail (git shows which
agent did what), instant revocability, and no agent ever inherits a human's broader
permissions. Details: `docs/AGENT-TOOLING.md` §3.

## D7 — 2026-08-24 — Azure OpenAI is the only model provider; OpenAI-native harnesses

Justin's call: the org's ~$25k Azure OpenAI startup credits make GPT deployments
(`sol`, `terra`) effectively free, so **every agent brain is an Azure OpenAI
deployment** — no Claude models, no Foundry. This supersedes D5's Claude-Code-default
and amends D2 (whose factual matrix still holds: an Azure OpenAI key cannot power
Claude Code — which is exactly why the harness changes too). The runtime becomes:

- **OpenAI Agents SDK** (`tools/azure-runner/orchestrator.py`) runs pipeline stages
  on EC2 — one stage per invocation, postconditions enforced in code.
- **Codex CLI** (Azure provider config) is the developer's stage-3 session and the
  headless repo-task tool; it reads `AGENTS.md` natively.
- **`AGENTS.md` is the canonical contract file** (OpenAI-ecosystem convention);
  `CLAUDE.md` is a pointer. `.claude/agents/` wrappers stay in-tree but dormant —
  free insurance if the provider decision ever reverses.
- Deployment routing: `LANTERN_MODEL_REASONING` / `LANTERN_MODEL_FAST` env vars map
  roles to deployments; swapping is a one-var change.

**Consequence:** D1 (harness-agnostic knowledge) is what made this pivot a one-day
change — that invariant is now load-bearing and must be preserved as roles scale.

## D8 — 2026-08-25 — One-call durable loop: Postgres state machine + Agents SDK sessions

Justin's ask: "idea from concept to live with one call," Karpathy-style agentic
loop, Postgres managing all sessions. Design (full doc: `docs/ORCHESTRATION.md`;
research: `docs/research/`): **two-layer durability with no workflow engine** —
an explicit Postgres state machine (runs / stage_executions / approvals /
artifacts / events, claimed by one systemd daemon with `FOR UPDATE SKIP LOCKED`)
around Agents SDK `SQLAlchemySession` per `{run_id}:{stage}` for conversation
persistence in the same Postgres. Human gates are `approvals` rows (fail-closed;
agents have no write path to them); CLI front-end first, Slack buttons + GitHub
PR webhooks later. Temporal and LangGraph rejected for one-box scale; upgrade
path is DBOS Transact, then Temporal's official Agents SDK plugin. Karpathy
grounding: gates are the autonomy slider's detents — one call *starts*
concept→live but never skips the human at choose/approve/ship
("LLMs automate what you can verify"). Tracing to the OpenAI dashboard is
disabled (Azure-only credentials); self-hosted Langfuse is the future option.

## D9 — 2026-08-25 — Stage 1 splits by runner affinity: divergence on EC2, Paper convergence on a design workstation

Paper's MCP is desktop-bound (no headless mode — `docs/research/design-agents.md`),
and divergence is cheap volume work that shouldn't spend Paper's call budget. So the
pipeline's stage 1 becomes two executions sharing one run-folder dir: `01-ui-ux.diverge`
(EC2, `LANTERN_MODEL_FAST`, 5–10 low-fi skeletons + judge pass) and `01-ui-ux.design`
(design workstation, Paper MCP, convergence + critique loop). Mechanism: stage tuples
carry a `runner`; one daemon per runner (`pipeline.py daemon --runner workstation`)
claims only its stages; the workstation daemon preflights Paper's port at startup and
every tick, and daemons heartbeat into a `runners` table so Mission Control shows
"needs the design workstation" instead of a silent stall. The ui-ux agent writes
`01-ui-ux/handoff.json`; the orchestrator builds the `ux_signoff` payload from it and
Mission Control renders Paper URL + option PNGs side by side. Quality is constrained
by the checked-in design layer (`design/design-system.md` + `design/critique-checklist.md`)
because Paper ships no token/component system yet and unconstrained agents produce
generic output. Full plan + phases: `docs/plans/ui-ux-agent-paper.md`. **Consequence:**
stage keys in the DB are no longer always run-folder dirs — anything joining stages to
folders must go through `STAGE_DIR`/`stage_dir()`.
