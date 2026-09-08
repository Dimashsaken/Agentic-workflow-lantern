# Validation — <run-id>

- **Author:** validator agent
- **Date:**
- **Verdict:** PASS | FAIL (computed: pass only when every criterion is covered and fix-now is empty)
- **Branch:** <working branch> @ <head sha> (from `03-coding/handoff.json`)

## Traceability

| ID | Criterion | Status | Code | Test | QA evidence (session · time) | Notes |
|----|-----------|--------|------|------|------------------------------|-------|
| AC-1 | | covered / missing / skipped / off-spec / insecure | `path::symbol` | `path::test` | session n · m:ss | |

## Fix now

| ID | Criterion | Smallest change that covers it |
|----|-----------|--------------------------------|
| F-1 | AC-n | |

## Findings (not verdict-changing)

- Pattern drift vs `research.json`, scope drift vs `plan.json` write_scope, unrequested work.

---
The typed twin is `validation.json`. A FAIL verdict stops the run here; the fix happens
in stage 3 (`pipeline.py rework <run-id> --to 03-coding` in auto mode).
