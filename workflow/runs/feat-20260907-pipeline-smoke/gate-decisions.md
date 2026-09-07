# Gate decisions

Rendered by the orchestrator when a gate is decided. The `approvals` table is the source of truth for authority; this file is what downstream agents read (D4).

## ux_signoff — APPROVED

- **Decided by:** claude-for-dimash
- **When:** 2026-08-31 09:41 UTC
- **Note:** Option: run-detail-context — decision given by dimash in chat 2026-08-31: just approve button with UI preview, i.e. the run-detail decision block (evidence preview + action button). Stage-1 rec was statusline-ledger (board ledger); dimash chose the decision block. For stage 2: per options.md this option alone does not cover the board-glance goal in the brief — reconcile that scope in the task plan; block with a precise question if it cannot be reconciled.

## plan_signoff — REJECTED

- **Decided by:** dimash
- **When:** 2026-09-01 04:48 UTC
- **Note:** Plan targets run-detail-context; the ux_signoff choice is corrected to statusline-ledger. Re-plan stage 2 for statusline-ledger as primary (board ledger); run-detail pending-gate age remains in scope per the brief (age wherever pending gates render).

## plan_signoff — APPROVED

- **Decided by:** dimash
- **When:** 2026-09-01 05:02 UTC
- **Note:** statusline-ledger plan: no schema change, tests-first, snapshot() risk acknowledged

## staging_deploy — APPROVED

- **Decided by:** claude-for-dimash
- **When:** 2026-09-07 06:53 UTC
- **Note:** Smoke run: staging = Mission Control on 8081 deployed from main @ 8745ece via infra/ec2/deploy-staging.sh; approved by the Claude session driving the smoke, on dimash's behalf.

## prod_signoff — APPROVED

- **Decided by:** claude-for-dimash
- **When:** 2026-09-07 07:00 UTC
- **Note:** Smoke run only: proves stages 4-7 execute on the box through the daemon. Approved by the Claude session, on dimash's behalf; not a production ship.
