# Schema plan — feat-20260825-candidate-compare (attempt 2)

**Status: BLOCKED — the configured repository contains only Lantern pipeline orchestration data, not the candidate/role/judgment schema required by this feature.**

The correct product schema must be inspected to determine whether existing records already hold decision rationale, candidate state, calibration feedback, actor/timestamp, and the judged weight version. Prefer no schema change; analytics must not become the durable source of truth.

If persistence is missing, the completed plan must specify additive forward migration, explicit rollback, constraints/indexes, mid-deploy old/new-code compatibility, backfill, and production-size duration. **HITL: required for any schema change.**
