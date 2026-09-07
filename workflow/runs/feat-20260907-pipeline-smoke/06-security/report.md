# Stage Report: 06-security — feat-20260907-pipeline-smoke

- **Agent/author:** security
- **Date:** 2026-09-07
- **Status:** PASS-WITH-NOTES

## Summary

Reviewed the merged gate-latency feature from base `904db65` through `b75a4f2`, its current `main` implementation, upstream reports, schema, tests, and query-plan evidence. The feature adds only authenticated, read-only aggregation and escaped server-rendered output; it adds no endpoint, write path, package, migration, secret, upload, outbound request, or analytics event. Recommendation: **GO with conditions** listed in the deploy checklist; there are no critical or high findings.

## Work performed

- Established the review target from the original feature commits and current `main`; inspected `product/tools/mission-control/app.py`, `product/tools/mission-control/ui.py`, `product/tools/mission-control/test_gate_latency.py`, `product/tools/mission-control/README.md`, `product/tools/azure-runner/schema.sql`, and `03-coding/explain-latency.txt`.
- Traced the changed Board route through `current_user()` → `snapshot()` → `LATENCY_SQL` → `gate_latency_rows()` / `gate_latency_metrics()` → `ui.gate_ledger()` and the pending-card stale path.
- Checked authorization, IDOR/input boundaries, SQL injection, XSS, sensitive logging/analytics, rate-limit relevance, dependency/lockfile changes, configuration, migration behavior, failure isolation, and rollback.
- Confirmed the changed Board remains protected by an in-handler `current_user()` check. The new SQL has no user input or dynamic interpolation, and database gate names and values are escaped through `ui.H()` before HTML rendering.
- Confirmed no dependency or lockfile change exists in the reviewed feature commits, so no new package advisory, typo-squatting, maintainer, install-script, or transitive-dependency review is required.

## Findings / results

| ID | Severity | Finding | Evidence | Mitigation / disposition |
|---|---|---|---|---|
| S1 | Low | The 30-day latency aggregate is executed on every authenticated Board and `/runs` snapshot and currently scans decided approvals; this is a bounded availability/performance risk as the table grows, not an injection or confidentiality issue. | `product/tools/mission-control/app.py` defines static, parameterless `LATENCY_SQL`; `product/tools/azure-runner/schema.sql` has only `idx_approvals_pending`; `03-coding/explain-latency.txt` records 11.5 ms at 20,000 synthetic rows. | Accept for this deploy. Retain post-coding DT-1 triggers (approvals >100k, Board p95 >100 ms, or another decided-row aggregate); then remove the unused `/runs` fetch and seek schema approval for an appropriate partial index if EXPLAIN warrants it. |
| S2 | Info | Aggregate query failures disclose only the exception text to server stderr; no request input, credentials, approval payload, or row values are included by this feature. | `product/tools/mission-control/app.py` catches `asyncpg.PostgresError as e`, emits `gate latency query failed: {e}`, and returns `gate_latency=None`; `product/tools/mission-control/ui.py` renders a generic unavailable message. | Accept. Keep logs access-controlled under existing operational policy; do not add SQL parameters or row data to this message later. |

### Vulnerability review

- **Authentication/authorization:** No new or changed endpoint. The changed `board()` handler verifies `current_user()` before database access. Existing gate decision authorization and ownership model are unchanged.
- **IDOR:** No new identifier is accepted. Pending approval IDs appear only in existing decision forms; this feature does not alter the server-side guarded update.
- **Injection:** `LATENCY_SQL` is a fixed literal with no request-derived values. No shell, filesystem path, URL fetch, or dynamic SQL was added.
- **XSS:** Unknown historical gate names originate in the database but pass through `H()` in `ui.gate_ledger()`; latency values are generated server-side and also escaped. No unsafe script or raw user HTML was added.
- **Sensitive data:** Only gate type, aggregate duration, count, and pending age are displayed to authenticated users. No PII, token, credential, payload, or analytics event was added.
- **Rate limits:** No unauthenticated or mutating surface was added. Existing authenticated page polling remains unchanged; the aggregate's growth risk is S1/DT-1.

### Deploy risk and rollback

- **Migration:** None. Deployment is application rollout only; old and new code use the existing approvals schema.
- **Configuration/secrets:** None added. Existing `LANTERN_WEB_USERS`, optional `LANTERN_WEB_SECRET`, and database configuration remain required by Mission Control but are not changed by this feature.
- **Partial-failure behavior:** If the aggregate alone fails, the Board renders a generic unavailable ledger while pending cards and controls remain available. If the overall database is unavailable, Mission Control retains its pre-existing outage behavior.
- **Blast radius:** Board reads and the shared `/runs` snapshot gain one aggregate query. No approval state, pipeline state, route contract, or external system is modified.
- **Rollback:** Revert the gate-latency application/UI/test/docs commits and redeploy. There is no data or schema rollback and no flag to unwind.

### Recommendation

**GO with conditions:** deploy from the reviewed `main` commit, verify existing staging auth/database configuration before rollout, and execute the checks below. Roll back if authentication or gate controls regress, Board or `/runs` fails to render, or the new query causes the stated latency/error trigger.

### Deploy-day checklist

1. Confirm staging deploy source is the reviewed `main` commit (currently `8745ece`) and no unreviewed diff is included.
2. Confirm existing staging `LANTERN_WEB_USERS`, `LANTERN_WEB_SECRET`, and database settings are present; no new secret or config should be introduced.
3. Deploy application code; do **not** run a migration or add an index for this feature.
4. Authenticate with the provisioned staging test user and verify signed-out `/` redirects to login.
5. Open Board and `/runs`; verify both render, the ledger shows values or the documented generic unavailable state, and pending Approve/Reject controls remain present.
6. Inspect service logs for `gate latency query failed` and observe Board latency. **Rollback trigger:** repeated aggregate errors, Board or `/runs` HTTP failure, loss of auth/gate controls, or Board p95 exceeding 100 ms attributable to the aggregate.
7. If rollback triggers, revert/redeploy the feature commits; verify Board, `/runs`, and gate controls on the prior version. No database action is required.

## Artifacts

- `report.md` — security findings, verdict, and deploy-day checklist.
- `../03-coding/explain-latency.txt` — reviewed query-plan and rollback-confirmation evidence.

## Handoff notes for the next stage

After the human staging deploy, QA staging should first verify authentication, Board and `/runs` availability, ledger failure isolation, and unchanged gate controls. No schema, package, or environment delta is expected; treat any such delta as outside the reviewed release and stop for review.

## Open questions (BLOCKED status must have exactly one)

None.

## Memory candidates

- 2026-09-07: For read-only dashboard aggregates, security review must include the shared-route query cost and failure isolation even when there is no input injection surface, because authenticated polling can turn table growth into an availability risk.
