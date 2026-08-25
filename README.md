# Agentic Workflow — Lantern

A fixed, repeatable feature-development pipeline run by a fleet of role agents, each
with a persistent charter, skill set, and memory. Humans (Justin + the assigned
developer) stay in the loop at a small number of explicit gates.

All agent brains run on **Azure OpenAI** (the org's startup credits); the fleet uses
the OpenAI Agents SDK on EC2 plus Codex CLI for developers (decision D7).

**Start here:**

- [AGENTS.md](AGENTS.md) — how the whole system works (agents read this automatically)
- [workflow/PIPELINE.md](workflow/PIPELINE.md) — the feature lifecycle, stage by stage
- [workflow/DEBUG-LIFECYCLE.md](workflow/DEBUG-LIFECYCLE.md) — the bug lifecycle
- [agents/README.md](agents/README.md) — how agent roles are defined and how to add one
- [docs/ORCHESTRATION.md](docs/ORCHESTRATION.md) — the one-call concept→live loop
- [docs/MISSION-CONTROL.md](docs/MISSION-CONTROL.md) — the web UI for gates, runs, and verification
- [docs/AGENT-TOOLING.md](docs/AGENT-TOOLING.md) — runtime stack, tools, GitHub identity
- [infra/ec2/README.md](infra/ec2/README.md) — running the fleet on EC2
- [tools/azure-runner/README.md](tools/azure-runner/README.md) — the orchestrator + Codex setup
- [tools/qa-recorder/README.md](tools/qa-recorder/README.md) — QA with video recording

## Kicking off a feature

1. Copy `workflow/briefs/_TEMPLATE.md` → `workflow/briefs/<slug>.md`, fill it in.
2. Create the run folder: `workflow/runs/feat-YYYYMMDD-<slug>/`.
3. Run the first stage:
   `python tools/azure-runner/orchestrator.py feat-YYYYMMDD-<slug> 01-ui-ux`
   (or the equivalent in an interactive Codex session at the repo root).
4. Review at each gate; the run folder accumulates every stage's report and artifacts.

## Reporting a bug

Copy `workflow/briefs/_BUG-TEMPLATE.md` → create a `bug-YYYYMMDD-<slug>` run → hand it
to the `debug` agent. PostHog-detected issues enter the same way.
