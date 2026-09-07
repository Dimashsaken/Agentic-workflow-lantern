# Stage Report: 05-post-coding — feat-20260907-pipeline-smoke

- **Agent/author:** post-coding
- **Date:** 2026-09-07
- **Status:** PASS-WITH-NOTES

## Summary

The reviewed gate-latency implementation on `main` matches the approved plan and QA-passed behavior; prior fix-now findings are present and resolved in the current tree. No schema, package, environment, write-path, API, or analytics change was introduced, and rollback requires only reverting application code. One existing, documented performance debt ticket remains below its trigger; there are no open fix-now findings, so security may proceed.

## Work performed

- Read the brief, gate decisions, stage 1–4 reports, blast radius, schema plan, task plan, coding evidence, QA charter, bugs, and media manifest.
- Reviewed the full feature diff from pre-feature base `904db65` to current `main` for the five product files: `tools/mission-control/app.py`, `tools/mission-control/ui.py`, `tools/mission-control/test_gate_latency.py`, `tools/mission-control/README.md`, and `docs/MISSION-CONTROL.md`.
- Compared intent with implementation: grouped 30-day median query, stable known-gate rendering, zero state, >24h stale treatment, failure isolation, shared `/runs` behavior, docs, and tests are present; the rejected run-detail redesign is absent.
- Traced `snapshot()` consumers and searched for consumers of the removed `decided` key; only `board()` consumes the additive `gate_latency` value, while `/runs` tolerates it.
- Reviewed `tools/azure-runner/schema.sql` and `03-coding/explain-latency.txt` for query boundedness/index evidence.
- Checked the current tree for debug/TODO noise and verified the earlier fixes: query failures log before graceful degradation, and `gate_latency_metrics` no longer collides with the cost-ledger name.
- Confirmed the feature diff passes `git diff --check`; functional execution evidence is QA's live PASS-WITH-NOTES and the coding report's 35 passing behavior tests.

## Findings / results

| ID | area | severity | tag | evidence |
|---|---|---:|---|---|
| F1 | error observability | medium | waived — resolved | `product/tools/mission-control/app.py` catches `asyncpg.PostgresError as e`, logs `gate latency query failed` to stderr, then degrades only the ledger. This resolves the prior swallowed-error fix-now finding. |
| F2 | naming cleanliness | low | waived — resolved | `product/tools/mission-control/app.py` uses `gate_latency_metrics`; product search shows one definition, one app call, and three test calls, with no old `ledger_metrics` symbol. This resolves the prior naming-drift fix-now finding. |
| F3 | query/index debt | low | debt-ticket — existing DT-1 | `product/tools/azure-runner/schema.sql` has only the pending-approval partial index, so the decided-row aggregate scans the approvals table. `03-coding/explain-latency.txt` measured 11.5 ms and 261 shared-hit buffers at 20,000 rolled-back synthetic rows. Existing ticket trigger remains: approvals >100,000 rows, board p95 >100 ms, or a second decided-row aggregate; first remove the unused `/runs` fetch, then seek schema approval for a partial `decided_at` index if EXPLAIN warrants it. No new ticket was created because DT-1 already exists in the prior stage-5 report on `main`. |
| F4 | shared snapshot work | low | waived | `snapshot()` runs the latency aggregate for `/runs`, where it is unused. This intentionally preserves the shared batch boundary and replaces a previously unused aggregate; measured cost is low and DT-1 owns the growth trigger. |
| F5 | hardcoded 24h threshold | info | waived | `STALE_SECONDS = 24 * 3600` in `product/tools/mission-control/app.py` is explicitly required by the brief's “no configurable thresholds” non-goal and documented in `product/tools/mission-control/README.md`. |
| F6 | unknown-gate ordering | info | waived | Known gates are deterministically ordered by `GATE_META`; unknown historical gates append in database result order. The current writer vocabulary is closed to the five known gate names, so this has no current compatibility impact. |

### Plan vs. diff

All six planned tasks are represented in the current tree. No unplanned schema, dependency, route, write, event, feature-flag, or configuration work was found. QA verified the Board, Gates, Runs, run detail, authentication, desktop/mobile layout, stale state, zero-decision state, refresh, and navigation on the deployed dev target without product defects.

### Backward compatibility and rollback

- **Rollback-safe:** no migration or schema mutation exists; reverting the five application/docs/test files leaves no forward database state behind.
- **API/routes:** no endpoint or POST contract changed. Approval forms and `decide()` remain server-side; the feature adds read-only Board presentation.
- **Internal return shape:** `snapshot()` replaced the unused `decided` value with `gate_latency`; all tracked consumers were traced, and no consumer references `decided`.
- **Configuration/deployments:** no new required environment variable or package. Existing deployments boot with old config.
- **Events/analytics:** none added or renamed.
- **Data volume:** query output is bounded by gate types; scan growth is tracked by DT-1.

## Artifacts

- `report.md` — this post-coding review.
- `../03-coding/explain-latency.txt` — recorded query-plan evidence at current and synthetic volume.
- `../04-qa-dev/media-manifest.json` — QA video locations for the live dev verification.

## Handoff notes for the next stage

Security should begin with `product/tools/mission-control/app.py:LATENCY_SQL`, the graceful-degradation catch, and `product/tools/mission-control/ui.py:gate_ledger`. The feature is read-only and parameterless; database gate names are escaped by `H()` before rendering. DT-1 is performance/schema debt, not a security or deploy blocker.

## Open questions (BLOCKED status must have exactly one)

None.

## Memory candidates

- 2026-09-07: When a smoke run reuses an already merged feature, compare the current tree against the original approved plan and prior stage-5 resolutions; otherwise the review may reopen resolved findings or mistake later main-branch work for feature scope.
