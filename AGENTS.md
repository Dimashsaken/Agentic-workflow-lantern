# Lantern — Agentic Feature-Development Pipeline

Lantern is the control plane for a **fixed, multi-agent software-delivery pipeline**.
Justin writes a feature brief, assigns a developer, and the feature flows through the
same sequence of role agents every time: UI/UX → pre-coding → coding → QA (dev) →
post-coding → security → QA (staging). Bugs flow through a parallel debug lifecycle.

**All models come from Azure OpenAI** (the org's startup credits). The fleet runs on
the OpenAI-native stack: the **OpenAI Agents SDK** executes pipeline stages on EC2,
and **Codex CLI** (configured for Azure OpenAI) is the developer's coding session.
This file is the system contract every agent session loads — `AGENTS.md` is the
convention those tools read.

This repo holds three things:

1. **Agent knowledge** — each role's charter, skills, and persistent memory (`agents/`)
2. **The pipeline contract** — stages, gates, handoffs, artifact formats (`workflow/`)
3. **Runtime tooling** — EC2 setup, QA video recording, the stage orchestrator (`infra/`, `tools/`)

## Repo map

```
agents/<role>/          charter.md + skills.md + memory.md per role (harness-agnostic)
workflow/PIPELINE.md    the fixed lifecycle: stages, inputs/outputs, gates
workflow/RUNBOARD.md    live index of runs — orientation step 1, updated every session
workflow/DEBUG-LIFECYCLE.md   bug intake → repro → fix → regression
workflow/briefs/        feature briefs from Justin (start from _TEMPLATE.md)
workflow/runs/          one folder per feature/bug run; all stage artifacts live here
workflow/templates/     stage report + handoff templates
tools/azure-runner/     the fleet runtime: pipeline.py (one-call loop) + orchestrator.py (single stage) + schema.sql
tools/qa-recorder/      Playwright-based QA with built-in video recording
tools/mission-control/  web UI: gate inbox, run board, verification timeline (docs/MISSION-CONTROL.md)
infra/ec2/              EC2 provisioning: bootstrap.sh + systemd units + operations
docs/ORCHESTRATION.md   the one-call concept→live loop: Postgres state machine, gates, failure modes
docs/AGENT-TOOLING.md   runtime stack, per-agent tools/MCP matrix, GitHub identity, orientation protocol
docs/DECISIONS.md       architecture decisions (read before changing the design)
.mcp.json               reference list of shared MCP servers (wired per-harness, see AGENT-TOOLING §2)
.claude/agents/         dormant Claude Code wrappers — not part of the fleet (see DECISIONS D7)
```

## The one rule that matters

Every agent session, **before doing anything else**, reads in this order:

1. `agents/<role>/charter.md` — what the role is (and is not) responsible for
2. `agents/<role>/skills.md` — how this role does its work
3. `agents/<role>/memory.md` — judgement accumulated from past runs
4. `workflow/RUNBOARD.md` — what's in flight, then the active run folder
   `workflow/runs/<run-id>/` — the brief and all upstream stage reports
5. The product repo's git state and its own AGENTS.md — full orientation protocol in
   `docs/AGENT-TOOLING.md` §5 (branches, prior commits for this run, open agent PRs)

And **before ending**, it must:

1. Write its stage report to `workflow/runs/<run-id>/<stage-dir>/report.md`
   (copy `workflow/templates/stage-report.md`)
2. Append durable learnings to its own `agents/<role>/memory.md` (dated, append-only —
   never rewrite history; consolidation happens separately, see Memory protocol)
3. Update the run's row in `workflow/RUNBOARD.md`

An agent that skips any step breaks the pipeline for everyone downstream. The
orchestrator (`tools/azure-runner`) verifies all three after every stage run.

## The pipeline (fixed — do not reorder)

| # | Stage dir        | Agent        | Key output                                   | Gate to advance                    |
|---|------------------|--------------|----------------------------------------------|------------------------------------|
| 1 | `01-ui-ux`       | `ui-ux`      | 2–3 flow options → coded prototype + video   | Justin/developer picks an option   |
| 2 | `02-pre-coding`  | `pre-coding` | Blast-radius report, schema plan, task plan  | Schema + plan approved             |
| 3 | `03-coding`      | developer    | Implementation on a feature branch           | Code complete, self-review done    |
| 4 | `04-qa-dev`      | `qa-dev`     | Test design + executed runs + **videos**     | No open sev-1/sev-2 bugs           |
| 5 | `05-post-coding` | `post-coding`| Cleanliness / tech-debt / backward-compat    | Findings resolved or waived        |
| 6 | `06-security`    | `security`   | Deploy-risk + vulnerability report           | No unmitigated high-risk findings  |
| — | *deploy to staging (human)* |   |                                              |                                    |
| 7 | `07-qa-staging`  | `qa-staging` | Staging QA runs + **videos**                 | Justin signs off for production    |

Stage 3 (coding) is done by the assigned developer in their own **Codex CLI session**
on their laptop (Azure OpenAI provider — config in `tools/azure-runner/`) — it is the
primary session, not a fleet agent. All other stages run through the orchestrator on
EC2 (or a workstation for Paper-dependent ui-ux work). Details, per-stage contracts,
and the list of human-in-the-loop gates: `workflow/PIPELINE.md`.

Bugs (user report or PostHog signal) do **not** enter at stage 1 — they follow
`workflow/DEBUG-LIFECYCLE.md`, owned by the `debug` agent.

## Runs and artifacts

- Run ID: `feat-YYYYMMDD-<slug>` or `bug-YYYYMMDD-<slug>` (e.g. `feat-20260824-bulk-export`).
- Everything a stage produces goes in `workflow/runs/<run-id>/<stage-dir>/`:
  `report.md` (required), plus plans, diffs, screenshots.
- **Videos and large binaries never go in git.** Upload to the artifact bucket
  (see `infra/ec2/README.md`) and link the URL from the report.

## Memory protocol

- `memory.md` is each agent's long-term judgement. Entries are dated, concrete, and
  say *why* — "2026-08-24: Modal flows on mobile Safari need X because Y", not "be careful with modals".
- Append-only during runs. Roughly monthly, a human (or a dedicated session) consolidates:
  merge duplicates, delete entries proven wrong, keep the file under ~200 lines.
- Never store secrets, customer data, or anything derivable from this repo's code in memory files.

## Models and providers

- **Single provider: Azure OpenAI.** Every agent brain is one of the org's GPT
  deployments (`sol`, `terra`, …). Deployment routing per role is configured in the
  orchestrator (`tools/azure-runner`): the stronger deployment for reasoning-heavy
  stages (pre-coding, security, debug, post-coding), the faster one for volume
  execution (QA charter runs).
- Harnesses: **OpenAI Agents SDK** (pipeline stages) and **Codex CLI** (coding stage).
  Both read this file and both are wired to the same MCP tool layer
  (`docs/AGENT-TOOLING.md` §2). Decision record: `docs/DECISIONS.md` D7.
- All credentials come from environment variables (locally via `.env`, on EC2 via SSM
  Parameter Store). **Never commit keys.** Env-var contract: `tools/azure-runner/README.md`.
- Agents act on GitHub as the `lantern-bot` collaborator (never a human identity),
  restricted to `feat/*`/`fix/*`/`proto/*` branches — identity, branch rules, and the
  per-agent tool matrix live in `docs/AGENT-TOOLING.md`.

## Human-in-the-loop gates (never automate past these)

1. Choosing the UX option (stage 1 → 2)
2. Approving schema/migration changes (stage 2 → 3)
3. Deploying to staging (stage 6 → 7) and to production (after stage 7)
4. Anything the pre-coding agent flags as `HITL: required` in its report

## Conventions

- New agent roles: copy `agents/_template/`, fill in the three files, register the
  role in the orchestrator's stage map (`tools/azure-runner`). The pipeline table
  above and `workflow/PIPELINE.md` must be updated in the same commit. Designed to
  scale to ~20 roles.
- Commits from agent sessions reference the run ID: `feat-20260824-bulk-export: <message>`.
- When a stage is blocked, the report says `Status: BLOCKED` with a single unambiguous
  question — downstream agents do not guess.
