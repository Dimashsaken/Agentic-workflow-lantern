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
- 2026-09-10 [feat-20260910-agentic-infrastructure · manual-engineering-continuation] 2026-09-11: Absence of a per-action intent permits first execution only when every version of that protocol persists intent before its external call; legacy aggregate records and lost intent responses must remain held because absence of a provider result cannot prove the operation never started.
- 2026-09-10 [feat-20260910-agentic-infrastructure · manual-engineering-continuation] 2026-09-11: Test optional safety flags independently of neighboring runtime flags; an operator enabling a protected pilot must reach that protected entry point even when the older dispatcher mode remains configured. Retention inventories must include temporary maintenance clones and permanent descriptor growth, because deleting checkout bytes alone does not bound lifecycle overhead.
- 2026-09-11 [feat-20260910-agentic-infrastructure · manual-engineering-continuation] 2026-09-11: A bounded historical-path index must preserve the write protocol across rollback and mixed-version writers; a permanent completeness marker can silently lose ancestor protection after a legacy writer adds a path. Keep registry locks out of slow clone work, and validate final maintenance changes against the inherited scope rather than a reread plan. Compatibility metadata can reject an old reader yet still change which OS lock newer readers acquire; keep each execution lock identity permanent.
