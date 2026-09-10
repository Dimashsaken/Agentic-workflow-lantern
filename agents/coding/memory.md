# Memory — coding

Long-term judgement for this role. Read fully at session start. Append at session end.

Rules: dated entries, concrete, with the *why*; append-only during runs; no secrets or
customer data. Target: under ~200 lines after consolidation.

## Learnings (append-only, newest last)

- 2026-08-24 (seed): The confidence map handed to QA is the highest-leverage artifact
  this stage produces — honest "I'm not sure about X" entries get bugs caught in dev
  instead of staging.

<!-- ENTRIES BELOW ARE RENDERED FROM THE role_memory TABLE — do not edit here; agents use append_memory, humans consolidate upward and re-run `pipeline.py render-memory` -->

- 2026-09-08 [feat-20260908-status-version · 03-coding] 2026-09-08: When extending an exact-shape JSON payload, update both the exact-key assertion and empty-payload expectation in addition to adding focused field tests, because those regression checks intentionally reject otherwise additive schema changes.
- 2026-09-08 [feat-20260908-note-delete · 03-coding.api] 2026-09-09: Adding deletion to an in-memory store exposes collisions when new ids are derived from the current item count; test delete-then-create or preserve a monotonic allocator because gaps make the count differ from the next free id.
- 2026-09-08 [feat-20260908-note-delete · 03-coding.api] 2026-09-09: A missing-record deletion test should keep a sentinel record and assert it remains, because an empty-store assertion cannot detect an implementation that reports failure while destructively clearing unrelated state.
- 2026-09-08 [feat-20260908-note-delete · 03-coding.api] 2026-09-09: When deletion reports whether a record existed, determine success from key membership rather than payload truthiness because valid falsey values must still be deleted and reported as present.
- 2026-09-08 [feat-20260908-note-delete · 03-coding.docs] 2026-09-09: In a parallel docs-only builder, document the exact approved interface and outcomes without depending on the sibling branch, because sibling code is unavailable until integration and contract drift must be caught at the merge seam.
- 2026-09-08 [feat-20260908-note-delete · 03-coding.docs] 2026-09-09: Before a path-scoped Python builder hands off, remove generated `__pycache__` directories and use `PYTHONDONTWRITEBYTECODE=1` for local reruns, because the write-scope gate counts untracked bytecode outside the builder's approved paths.
- 2026-09-08 [feat-20260908-note-delete · 03-coding.docs] 2026-09-09: If a post-test write-scope check repeatedly sees Python bytecode and the scoped builder cannot add a root `.gitignore`, use repository-local `.git/info/exclude` entries; one-time deletion is insufficient because the gate's own plain Python invocation recreates the caches.
- 2026-09-08 [feat-20260908-note-delete · 03-coding.integrate] 2026-09-09: At D18 integration, inspect tracked generated artifacts as well as test results, because an auto-committed builder handoff can merge bytecode that keeps the final branch dirty whenever the gate runs.
- 2026-09-08 [feat-20260908-note-delete · 03-coding.api] nothing durable learned this run: this repeat execution confirmed the previously recorded deletion and test-design lessons without adding a new generalizable convention.
- 2026-09-08 [feat-20260908-note-delete · 03-coding.docs] nothing durable learned this run: this repeat docs-builder execution confirmed the previously recorded contract-documentation and generated-bytecode write-scope practices.
- 2026-09-08 [feat-20260908-note-delete · 03-coding.integrate] nothing durable learned this run: integration confirmed the already-recorded lesson that tracked generated artifacts must be inspected and removed before the final gate.
- 2026-09-09 [manual · -] nothing durable learned this run: the user only asked an ambiguous capability question and no coding convention or repository insight emerged.
- 2026-09-10 [feat-20260910-agentic-infrastructure · manual-engineering-continuation] 2026-09-10: Before/after source hashes cannot prove which mutable code a test executed; use a separate read-only committed snapshot and a modify/test/restore negative control.
- 2026-09-10 [feat-20260910-agentic-infrastructure · manual-engineering-continuation] 2026-09-10: Persist immutable provider identity, base revision, and the observed old remote ref before publication; a confirmed local effect receipt is insufficient after a provider ref or PR moves, so reobserve before reuse and before opening the human gate.
