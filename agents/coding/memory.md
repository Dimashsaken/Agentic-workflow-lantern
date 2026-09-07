# Memory — coding

Long-term judgement for this role. Read fully at session start. Append at session end.

Rules: dated entries, concrete, with the *why*; append-only during runs; no secrets or
customer data. Target: under ~200 lines after consolidation.

## Learnings (append-only, newest last)

- 2026-08-24 (seed): The confidence map handed to QA is the highest-leverage artifact
  this stage produces — honest "I'm not sure about X" entries get bugs caught in dev
  instead of staging.

<!-- ENTRIES BELOW ARE RENDERED FROM THE role_memory TABLE — do not edit here; agents use append_memory, humans consolidate upward and re-run `pipeline.py render-memory` -->

- 2026-09-07 [feat-20260907-status-json · 03-coding] 2026-09-07: For a CLI machine-output mode, execute shared database reads before branching into renderers and freeze legacy stdout with exact-string tests, because this preserves query parity and catches accidental compatibility changes.
