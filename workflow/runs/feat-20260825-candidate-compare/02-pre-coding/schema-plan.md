# Schema plan — feat-20260825-candidate-compare

**Status: BLOCKED — schema impact cannot be determined because the product repository and current schema are not identified in the brief or run artifacts.**

Potential persistence needing verification includes the required advance/hold rationale, decision timestamp/actor, source ICP-weight version, recommendation match, and whether existing calibration/status records already model these values. Existing fields must be preferred; analytics-only data must not be treated as the durable source of truth.

If inspection shows no persistence change is needed, replace this document with the required one-line declaration: **No schema change is needed.**

If a change is needed, the completed plan must include an additive forward migration, explicit rollback, constraints/indexes, mid-deploy behavior, backfill strategy, production-size duration estimate, and compatibility across old/new application versions. **HITL: required** for every schema change before coding.
