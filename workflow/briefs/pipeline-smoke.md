# Feature Brief: Gate latency on the board (pipeline smoke run, stages 4–7 on the box)

- **Run ID:** feat-20260907-pipeline-smoke
- **Author:** dimash (drafted via Claude session — smoke run to prove stages 4–7 execute on the rebuilt box)
- **Assigned developer:** dimash
- **Date:** 2026-09-07
- **Target release:** —
- **Product repo:** https://github.com/Dimashsaken/Agentic-workflow-lantern
- **Base branch:** main
- **Coding mode:** human

## Why this run exists

This run re-enters the pipeline at stage 4 for a feature that is already implemented,
merged and deployed: the **gate-latency ledger** on Mission Control's board
(`feat-20260831-gate-latency`, commits `a0d9fda`…`b75a4f2`, on `main` since 2026-09-07).
Stages 1–3 of that run are copied into this folder verbatim as context. The purpose is
to prove, on the rebuilt box, that stages 4 (QA in dev, video), 5 (post-coding), 6
(security), the human staging deploy, and 7 (QA in staging, video) execute through the
daemon in sandboxes and leave the evidence the contract requires. The feature is live on
the QA dev target (the box's own Mission Control) and will be deployed to the staging
instance at the `staging_deploy` gate.

## Problem

Mission Control showed *that* a gate is pending but not *how long* it has waited, and
nothing showed the median time gates take. Human review latency is the #1 failure mode
of ticket-to-PR systems; the wait must be visible on the board.

## Desired outcome

An operator glancing at the board sees which gates are stale and whether gate latency
trends toward the one-day staffing threshold: every pending gate shows its age; a
ledger above the columns shows median time-to-decision per gate type over the last 30
days with its sample count; a gate older than 24h is visually flagged (`STALE`).

## Scope (as implemented)

- Age of every pending gate wherever pending gates render (board cards, `/gates`, run
  detail), in humane UTC units, from `approvals.requested_at`.
- A full-width gate-latency ledger on the board between the statusline and the five
  columns: `GATE LATENCY · LAST 30 DAYS` / `Median time to decision · UTC`, one metric
  per known gate type, `— · no decisions · n=0` for empty cohorts, warning color for a
  median over 24h.
- Review cards strictly older than 24h get a `STALE` chip and warning border; Approve /
  Reject controls and the evidence link are unchanged.
- If the aggregate query fails, the ledger shows `Gate latency unavailable — refresh.`
  and the board still renders with all decision controls.

## Non-goals

- No schema changes, no writes, no alerts, no configurable thresholds, no PostHog
  events, no new packages, no per-approver breakdown, no charts.

## Constraints

- Dark-only Mission Control flight-strips design; UTC everywhere.
- The board must render with zero decided approvals.

## Existing context

- Implementation: `tools/mission-control/app.py` (`LATENCY_SQL`, `gate_latency_rows`,
  `gate_latency_metrics`, `is_stale`, `STALE_SECONDS`) and `ui.py` (`gate_ledger`).
- Behavior tests: `tools/mission-control/test_gate_latency.py` (35 cases).
- Prior stage reports for this feature are in this folder (01–03) and, for the earlier
  laptop-driven QA and review, in `workflow/runs/feat-20260831-gate-latency/`.
- QA dev target: the box's Mission Control on the docker bridge; the QA user can log in
  and approve/reject synthetic gates. Do not decide any real run's gate (the real runs are
  `feat-20260831-gate-latency` and `feat-20260907-status-json`); seed synthetic runs with
  ids prefixed `qa-` and remove them when done.

## Human-in-the-loop preferences

- Standard gates. The staging deploy is performed by a human with
  `bash infra/ec2/deploy-staging.sh main` on the box.
