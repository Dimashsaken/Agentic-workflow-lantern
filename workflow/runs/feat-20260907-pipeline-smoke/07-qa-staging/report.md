# Stage Report: 07-qa-staging — feat-20260907-pipeline-smoke

- **Agent/author:** qa-staging
- **Date:** 2026-09-07
- **Status:** PASS-WITH-NOTES

## Summary

**Recommendation: ready for Justin's production sign-off; top residual risk is unexecuted cross-engine coverage because this session exposed only one recorded browser engine.** Staging authentication, database-backed gate latency, stale treatment, protected routes, shared `/runs`, run detail, and mobile overflow behavior passed with no product bugs. The brief specifies no analytics events or third-party integrations, so those checklists are not applicable.

## Work performed

- Read the brief, gate decisions, stage-4 charter/results, post-coding review, security deploy checklist, current product conventions, and current `main` history at `8745ece`.
- Authenticated at the exact staging target with the provisioned account; verified signed-out direct `/gates` access redirected to login.
- Re-ran the non-destructive stage-4 flow across Board, Gates, Runs, smoke-run detail, and gate-latency run detail.
- Verified the ledger heading/subtitle, known cohorts, counts, humane UTC durations, explicit no-decision states, and a staging-specific `staging deploy · n=1` metric.
- Verified the real 6d 1h code-complete gate is stale on the Board, remains `waiting 6d 1h` on `/gates` and run detail, and retains decision/evidence controls; no decision was submitted.
- At 720px measured viewport/body/document widths all at 720px; the ledger alone scrolls internally (`1308px` content, `720px` client width, `overflow-x:auto`) and reached its 588px maximum scroll.
- Inspected console output; only the unrelated favicon 404 appeared.

## Findings / results

| Scenario | Result | Evidence |
|---|---|---|
| Staging login and auth redirect | PASS | Exact supplied login reached Board; a fresh signed-out `/gates` request redirected to `/login`. |
| Ledger and realistic staging data | PASS | UX `20h 15m · n=3`, plan `19h 05m · n=5`, staging deploy `1m · n=1`; code-complete and prod sign-off showed explicit no-decision states. |
| Stale gate and pending age | PASS | Board showed `STALE` and `6d 1h`; `/gates` and run detail showed `waiting 6d 1h`; controls/evidence remained present. |
| Route regression | PASS | Board, `/gates`, `/runs`, smoke-run detail, and gate-latency run detail rendered authenticated. |
| Mobile viewport | PASS | No body/document horizontal overflow; ledger scrolled internally to the final metric. |
| Console | PASS-WITH-NOTE | Only `/favicon.ico` 404; no functional error. |
| Cross-browser | NOT RUN | Browser harness exposed no engine selector; Chromium-like recorded flow only. |

### Event-verification checklist

| Event | Trigger | Required properties | Result |
|---|---|---|---|
| None | — | — | N/A — `brief.md` explicitly says “no PostHog events.” |

### Integrations and data-volume observations

- No third-party integration is introduced by this feature.
- Staging contained realistic historical data across 13 runs, five open runs, two pending gates, and 11 recent decisions; no obviously slow navigation was observed. This is an observation, not a load test.

### Permanent staging regression recommendation

After sign-off, retain: signed-out protected-route redirect; authenticated Board and `/runs` rendering; ledger known/zero-state cohorts; >24h stale treatment; consistent pending age across Board/Gates/run detail; and 720px body-overflow/internal-ledger-scroll checks.

## Artifacts

- `staging-charter.md` — re-run, staging-only, and excluded coverage.
- `bugs.md` — zero product defects and environment notes.
- session 1 — 0:00 login; ~0:15 Board ledger including staging-deploy cohort and stale card; ~0:30 Gates age/history; ~0:45 Runs and smoke-run detail; ~1:05 mobile Board and internal ledger scroll.
- session 2 — 0:00 signed-out `/gates` redirect; ~0:20 login; ~0:35 Gates; ~0:55 gate-latency run detail showing the matching 6d 1h age.

## Handoff notes for the next stage

HITL required: Justin should review the two short videos and provide written production sign-off. Cross-engine coverage remains the only material coverage gap; no sev-1/sev-2 or other product defect was found.

## Open questions (BLOCKED status must have exactly one)

None.

## Memory candidates

- 2026-09-07: For a staging smoke run of an already-deployed read-only dashboard feature, verify deployment identity indirectly with newly staging-specific data (here the staging-deploy cohort changed from n=0 in dev to n=1 in staging) because identical static copy alone does not prove the staging database and deployment path are live.
