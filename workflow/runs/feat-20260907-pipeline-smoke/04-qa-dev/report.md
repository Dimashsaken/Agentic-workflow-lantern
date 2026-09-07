# Stage Report: 04-qa-dev — feat-20260907-pipeline-smoke

- **Agent/author:** qa-dev
- **Date:** 2026-09-07
- **Status:** PASS-WITH-NOTES

## Summary

Attempt 2 resolved the authentication blocker and verified the deployed gate-latency UI through the real dev Mission Control. The Board ledger, zero-decision states, stale treatment, pending ages, protected routes, shared `/runs` path, desktop/mobile layout, refresh, and Back navigation passed with no product bugs. The QA gate is met: zero open sev-1/sev-2 defects.

## Work performed

- Retested attempt 1's blocker using the exact supplied target and credentials; login succeeded and redirected to the Board.
- Verified the live ledger copy and values: UX sign-off `20h 15m · n=3`, plan sign-off `19h 05m · n=5`, and code-complete/staging deploy/prod sign-off each rendered `— · no decisions · n=0`.
- Verified the real 6d 1h gate-latency Review card has `STALE`, warning styling, Approve/Reject controls, and evidence navigation; no gate was decided.
- Verified `/gates` shows the same pending age and `/run/feat-20260831-gate-latency` repeats `waiting 6d 1h`.
- Verified `/runs` and `/run/feat-20260907-pipeline-smoke` render, including the current attempt-2 event; refresh and Back remained usable.
- At 1280px, body width equaled viewport width. At 720px, body width still equaled viewport width while the ledger used internal horizontal scrolling (`1416px` content in `720px`, `overflow-x:auto`); scrolling reached the final prod-signoff metric.
- Closed between charter sections to produce short recorded sessions. The only console error was a non-functional `/favicon.ico` 404.

## Findings / results

1. **[PASS] Authentication:** exact provisioned credentials work; attempt-1 ENV-1 is resolved.
2. **[PASS] Brief conformance:** ledger heading/subtitle, metric counts, humane ages, explicit no-decision copy, and >24h stale treatment are visible in the deployed UI.
3. **[PASS] Regression:** Board, Gates, Runs, and run detail render after login; direct signed-out `/gates` redirects to login.
4. **[PASS] Layout:** no body-level horizontal overflow at 1280px or 720px; the narrow ledger scrolls internally to its last metric.
5. **[NOTE] Coverage:** destructive decision probes and new DB boundary seeds were not run against real data; these are already unit-pinned and covered by the prior full QA run. No product defect was observed.

## Artifacts

- `test-charter.md` — attempt-2 charter written before execution.
- `bugs.md` — zero product bugs and resolved environment blocker.
- session 1 — 0:00 login; ~0:25 Board ledger and stale card; ~0:45 Gates; ~1:00 Runs and smoke-run detail; ~1:15 Back/refresh; ~1:30 mobile Board and ledger internal scroll.
- session 2 — 0:00 signed-out `/gates` redirect; ~0:15 re-login; ~0:30 Gates age; ~0:40 gate-latency run detail age; ~0:50 Back navigation.

## Handoff notes for the next stage

Post-coding may proceed. Review the shared `snapshot()` path and the intentional absence of stale styling on `/runs`; QA observed no compatibility regression. Treat the missing favicon as unrelated cosmetic infrastructure noise, not a gate-latency defect.

## Open questions (BLOCKED status must have exactly one)

None.

## Memory candidates

- 2026-09-07: When a retry exists solely to clear an environment blocker, explicitly retest that blocker first, then execute the highest-value non-destructive charter against live data; this preserves evidence without risking real control-plane gates.
