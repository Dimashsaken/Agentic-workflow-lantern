# Memory — post-coding

Long-term judgement for this role. Read fully at session start. Append at session end.

Rules: dated entries, concrete, with the *why*; append-only during runs; no secrets or
customer data. Target: under ~200 lines after consolidation.

## Learnings (append-only, newest last)

- 2026-08-24 (seed): Rollback safety is the compat check teams skip most: "can we roll
  back the code while the forward migration stays applied?" — if no, the report must
  say so in the summary line, because the deploy plan depends on it.

<!-- ENTRIES BELOW ARE RENDERED FROM THE role_memory TABLE — do not edit here; agents use append_memory, humans consolidate upward and re-run `pipeline.py render-memory` -->

- 2026-08-26 [manual · -] 2026-08-25: A post-coding pass requires both a QA-passed branch and the full intent artifacts; without either, report the compatibility/debt gate as unevaluated rather than inferring cleanliness from an absent diff.
- 2026-09-10 [feat-20260910-agentic-infrastructure · manual-engineering-continuation] 2026-09-10: Review optional lifecycle protections at every public entry point, including manual commands, and place durable success after resource cleanup and authoritative completion; disabling a scheduler path or finishing model turns alone does not establish the execution boundary.
- 2026-09-10 [feat-20260910-agentic-infrastructure · manual-engineering-continuation] 2026-09-10: Publication receipts, artifacts and success events must share the final target-and-fence acceptance transaction; provider success followed by a changed destination must leave a held intent rather than independently accepted local success evidence.
