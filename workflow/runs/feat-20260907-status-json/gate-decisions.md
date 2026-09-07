# Gate decisions

Rendered by the orchestrator when a gate is decided. The `approvals` table is the source of truth for authority; this file is what downstream agents read (D4).

## ux_signoff — WAIVED

- **Decided by:** dimash (via claude-for-dimash)
- **When:** 2026-09-07 06:05 UTC
- **Note:** No user-facing surface — the feature is a CLI flag plus a test. Stage 1 (UI/UX) was skipped by decision and the run was imported directly at `02-pre-coding` (`pipeline.py import-run`). Pre-coding: plan straight from the brief; there is no UX option to reconcile.

## plan_signoff — APPROVED

- **Decided by:** claude-for-dimash
- **When:** 2026-09-07 05:57 UTC
- **Note:** D14 proof run: plan matches the brief (3 tasks, tests first, no schema, no packages). Approved by the Claude session driving the proof, on dimash's behalf.
