# Memory — story

Long-term judgement for this role. Read fully at session start. Append at session end.

Rules: dated entries, concrete, with the *why*; append-only during runs; no secrets or
customer data. Target: under ~200 lines after consolidation.

## Learnings (append-only, newest last)

- 2026-09-08 (seed): A criterion that names a mechanism ("store in a saved_items
  table") cannot be validated from the outside and quietly pre-decides architecture.
  Write the observable outcome; the planner chooses the mechanism.
- 2026-09-08 (seed): The empty state and the "same action twice" case are where most
  stage-4 bugs live — put them in edge_cases explicitly, or QA will not probe them and
  the validator will mark the criterion covered on the happy path alone.

<!-- ENTRIES BELOW ARE RENDERED FROM THE role_memory TABLE — do not edit here; agents use append_memory, humans consolidate upward and re-run `pipeline.py render-memory` -->

- 2026-09-08 [feat-20260908-status-facts · 00-story.write] 2026-09-08: When a machine-readable status field is meant to distinguish pipeline generations, verify that run creation stamps distinct version values; exposing a stored field alone cannot satisfy the user outcome if every new run still receives the old version.
- 2026-09-08 [feat-20260908-status-facts · 00-story.write] 2026-09-08: When a brief explicitly separates version stamping from exposing stored version provenance, keep stamping as a non-goal and assess the projection contract against stored values; otherwise a valid consumer-facing increment is incorrectly blocked by an independent producer change.
- 2026-09-08 [feat-20260908-runboard-stage-timestamps · 00-story.write] 2026-09-08: Stage-age criteria must exclude unrelated run metadata updates and cover gate-only stages, because a generic run timestamp can make stalled work appear recent while some legitimate stage transitions have no execution row.
