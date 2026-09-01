# Schema plan — feat-20260831-gate-latency

No schema change is needed; all values are read from existing `approvals.requested_at`, `decided_at`, `status`, and `gate` columns.

## Query/index assessment

- Pending ages reuse the already-fetched pending approvals and application `now` in UTC.
- Summary query: decided approvals only, `decided_at >= now() - interval '30 days'`, grouped by `gate`, with `count(*)` and `percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM decided_at-requested_at))`.
- Zero decided rows return an empty mapping; rendering supplies every known gate type as `— · no decisions · n=0`.
- No backfill, forward migration, rollback migration, dual-write, locking, or mid-deploy row compatibility work exists.
- Do not add an index in this feature. The table is operationally small and the query is bounded; capture `EXPLAIN (ANALYZE, BUFFERS)` against production-like volume before proposing a partial index. If later justified, that is a separate schema-gated change.
- Estimated migration duration: 0 seconds. Rollback: revert application changes only.
