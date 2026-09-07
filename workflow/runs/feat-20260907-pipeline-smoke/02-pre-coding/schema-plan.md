# Schema plan — feat-20260831-gate-latency (attempt 2)

No schema change is needed; all values are read from existing `approvals.requested_at`, `decided_at`, `status`, and `gate` columns.

## Query/index assessment

- Pending ages reuse approvals already loaded by `snapshot()` and the server's UTC `now`.
- Ledger query: group by `gate`; include `status IN ('approved','rejected')`, non-null `decided_at`, and `decided_at >= now() - interval '30 days'`; return `count(*)` and `percentile_cont(0.5)` over epoch seconds of `decided_at - requested_at`.
- The 30-day cohort is defined by decision time, matching “decided approvals over the last 30 days.” Rows requested earlier but decided within the window count.
- Mid-deploy rows are safe: pending rows do not enter medians; a decision becomes visible on the next existing page refresh.
- No backfill, forward migration, rollback migration, dual-write, locking, or constraint impact.
- Do not add an index in this feature. Current volume is operationally small; validate the aggregate with `EXPLAIN (ANALYZE, BUFFERS)` on production-like data. Any later partial index on decided rows is a separate schema-gated proposal.
- Estimated migration duration: 0 seconds. Rollback: revert application code only.
