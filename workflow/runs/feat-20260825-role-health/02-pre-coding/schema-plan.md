# Schema plan — feat-20260825-role-health

**Status: UNDETERMINED — human approval required before any schema work.**

The brief says “no new data collection,” but that does not prove “no schema change”: the chosen implementation may calculate health on read, add a materialized snapshot/cache, or persist action/dismissal state. The target product schema, data volume, retention model, and current indexes are not present in this checkout, so forward migration, rollback, mid-deploy behavior, backfill, index/constraint impact, and production duration cannot be specified safely.

## Preferred decision order after repository orientation

1. Prove existing source, candidate-history, weighted-trait, and calibration data can serve the screen with bounded queries. Prefer **no schema change** and compute a read model from existing records.
2. If query cost is unsafe, propose an additive health snapshot/materialization table with versioned computation inputs; use expand → backfill → dual-read/feature flag → contract.
3. If “Ignore this week” is not already represented, prefer an additive per-role/per-signal suppression record with expiry and actor rather than overloading business-source records.
4. Never persist a paid action as complete before the external provider/payment boundary confirms success; require idempotency and an audit record.

## Mandatory migration worksheet if any change is proposed

For every table/index/constraint: exact forward SQL, exact rollback SQL, online-lock behavior, rows created during deploy, idempotent backfill and resume strategy, production row-count estimate, measured duration on representative data, and old/new application compatibility.

`HITL: required` — the developer/Justin must approve the completed schema plan. No migration may be inferred from this placeholder.
