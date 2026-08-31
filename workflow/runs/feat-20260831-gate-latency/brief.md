# Feature Brief: Gate latency on the board

- **Run ID:** feat-20260831-gate-latency
- **Author:** dimash (drafted via Claude session — dogfood run for P0.3)
- **Assigned developer:** dimash
- **Date:** 2026-08-31
- **Target release:** —
- **Product repo:** https://github.com/Dimashsaken/Agentic-workflow-lantern
- **Base branch:** main

## Problem

The Symphony-alignment plan (§6) names human review latency the #1 failure mode of
ticket-to-PR systems and this plan's own schedule risk: "Track gate-latency in Mission
Control; if a gate median exceeds a day, that's a staffing conversation, not an
automation one." Mission Control today shows *that* a gate is pending but not *how
long* it has waited, and nothing anywhere shows the median time gates take. The two
runs that sat on vacuous `plan_signoff` gates for four days (2026-08-27 → 08-31) are
the live example: nothing on the board made the wait visible.

## Desired outcome

An operator glancing at the board sees at once which gates are stale and whether gate
latency is trending toward the plan's one-day staffing threshold. Success: every
pending gate on the board shows its age; a small summary shows median
time-to-decision per gate type; a gate older than 24h is visually flagged.

## Scope

- Age of every pending gate, shown wherever pending gates render (board strips and
  the run detail view), in humane units ("3h", "4d") — computed from
  `approvals.requested_at`.
- A gate-latency summary on the board: per gate type (`ux_signoff`,
  `plan_signoff`, …), the median `decided_at - requested_at` over the last 30 days of
  decided approvals, and the count it is computed from.
- Pending gates older than 24 hours get a visible stale treatment consistent with the
  existing design tokens (`tools/mission-control/mockups/tokens.css`).
- All data derived from the existing `approvals` table — read-only queries.

## Non-goals

- No schema changes, no new tables, no writes.
- No alerts, notifications, Slack, or email — display only (the Phase 1 Slack app is
  a separate plan item).
- No per-approver breakdowns, no historical charting beyond the single median
  summary, no configurable thresholds (24h is hardcoded; changing it is a code edit).
- No PostHog events (Mission Control is not instrumented; do not add it).
- No new packages (FastAPI + the existing `ui.py` rendering are enough).

## Constraints

- Match Mission Control v2's flight-strips design language (`tools/mission-control/`
  — `app.py`, `ui.py`, `mockups/tokens.css`); dark/light both work today and must
  keep working.
- Timezone: render ages relative to now in UTC (the DB stores UTC); no client-side JS
  clock dependencies beyond what the board already uses.
- The board must render correctly when there are zero decided approvals (division by
  nothing, empty medians).

## Existing context

- `tools/mission-control/app.py` + `ui.py` — the v2 board (reworked 2026-08-28,
  "flight strips" direction; see `tools/mission-control/mockups/README.md`).
- `approvals` table: `tools/azure-runner/schema.sql` (`requested_at`, `decided_at`,
  `status`, `gate`).
- `docs/plans/symphony-alignment.md` §6 — the risk this feature instruments.
- This is the P0.3 dogfood run: the product repo IS the control plane. QA stages
  target the live Mission Control on the box (`LANTERN_QA_DEV_BASE_URL`).

## Human-in-the-loop preferences

- No new packages without developer sign-off (none are expected).
- The 24h stale threshold and the visual treatment are ux_signoff decisions — present
  options at stage 1, don't assume.
