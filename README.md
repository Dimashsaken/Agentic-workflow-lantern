# Agentic Workflow — Lantern

A fixed, repeatable feature-development pipeline run by a fleet of role agents, each
with a persistent charter, skill set, and memory. Humans (Justin + the assigned
developer) stay in the loop at a small number of explicit gates.

**Start here:**

- [CLAUDE.md](CLAUDE.md) — how the whole system works (agents read this automatically)
- [workflow/PIPELINE.md](workflow/PIPELINE.md) — the feature lifecycle, stage by stage
- [workflow/DEBUG-LIFECYCLE.md](workflow/DEBUG-LIFECYCLE.md) — the bug lifecycle
- [agents/README.md](agents/README.md) — how agent roles are defined and how to add one
- [infra/ec2/README.md](infra/ec2/README.md) — running the fleet on EC2
- [tools/qa-recorder/README.md](tools/qa-recorder/README.md) — QA with video recording

## Kicking off a feature

1. Copy `workflow/briefs/_TEMPLATE.md` → `workflow/briefs/<slug>.md`, fill it in.
2. Create the run folder: `workflow/runs/feat-YYYYMMDD-<slug>/`.
3. In a Claude Code session at the repo root, say:
   *"Run the pipeline for `workflow/briefs/<slug>.md`, run ID `feat-YYYYMMDD-<slug>`. Start with the ui-ux stage."*
4. Review at each gate; the run folder accumulates every stage's report and artifacts.

## Reporting a bug

Copy `workflow/briefs/_BUG-TEMPLATE.md` → create a `bug-YYYYMMDD-<slug>` run → hand it
to the `debug` agent. PostHog-detected issues enter the same way.
