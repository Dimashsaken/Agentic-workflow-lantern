# Memory — reviewer

Long-term judgement for this role. Read fully at session start. Append at session end.

Rules: dated entries, concrete, with the *why*; append-only during runs; no secrets or
customer data. Target: under ~200 lines after consolidation.

## Learnings (append-only, newest last)

- 2026-09-08 (seed): The verdict is computed from the severities, so the only judgement
  that matters is the severity of each finding — spend the thinking there. A "major"
  that is really a nit costs a fix execution and a round; a "nit" that is really a
  bug reaches a human as approved.
- 2026-09-08 (seed): Review the handoff's exact range (`base_sha..head_sha`), never
  "the branch": a run that continues an existing branch carries commits nobody asked
  this run to review, and a finding on them is noise the fix execution cannot act on.

<!-- ENTRIES BELOW ARE RENDERED FROM THE role_memory TABLE — do not edit here; agents use append_memory, humans consolidate upward and re-run `pipeline.py render-memory` -->

- 2026-09-08 [feat-20260908-status-version · 03-coding.review] 2026-09-08: For an additive top-level constant in a JSON shaper, require tests that both compare the value to the exported constant and exercise the empty payload; an exact top-level key-set assertion plus direct subscription makes missing fields fail loudly, while equality catches stale or hard-coded values.
