# Memory — researcher

Long-term judgement for this role. Read fully at session start. Append at session end.

Rules: dated entries, concrete, with the *why*; append-only during runs; no secrets or
customer data. Target: under ~200 lines after consolidation.

## Learnings (append-only, newest last)

- 2026-09-08 (seed): A path you did not open is a fabrication, and the harness treats it
  as one — research.json fails validation when a cited file does not exist. Grep, then
  read, then cite; never cite from a directory listing alone.
- 2026-09-08 (seed): The consumer you did not find is the one that breaks. Search for
  callers, cron jobs, event listeners and dashboards of anything the feature will
  change before writing the risks section.

<!-- ENTRIES BELOW ARE RENDERED FROM THE role_memory TABLE — do not edit here; agents use append_memory, humans consolidate upward and re-run `pipeline.py render-memory` -->

- 2026-09-08 [feat-20260908-status-facts · 00-story.scout] 2026-09-08: In Lantern, `product_working_branch = NULL` means “derive the effective branch from the run id,” not “there is no work branch”; research and machine-contract reviews must distinguish stored provenance from resolved runtime behavior because D15 preserves null for older and fresh-branch runs.
- 2026-09-08 [feat-20260908-runboard-stage-timestamps · 00-story.scout] 2026-09-08: In Lantern, a visible stage timestamp cannot be derived uniformly from `stage_executions`: split execution phases share a stage directory, while human coding can open a gate without an execution row; stage-age research must trace execution, approval, event, and run clocks before assigning semantics.
