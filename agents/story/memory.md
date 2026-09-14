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

- 2026-09-11 [feat-20260911-tender-onboarding · 00-story.write] 2026-09-11: When a brief names a future vendor-backed metric, make the event name, firing point, and minimum counting properties an acceptance criterion while keeping vendor delivery and dashboards as non-goals; this preserves a testable telemetry contract without silently expanding the current run into an analytics integration.
- 2026-09-11 [feat-20260911-tender-catalog-orders · 00-story.write] 2026-09-11: For multi-turn commerce chat, give collection, pre-creation summary, idempotent confirmation, and cancellation/reset separate observable criteria, because a single “assistant takes an order” criterion can pass while creating premature or duplicate orders and leaking stale draft state across retries.
- 2026-09-12 [feat-20260911-tender-escalations · 00-story.write] 2026-09-12: Escalation stories must state whether each trigger suppresses its triggering response or takes effect after that response, because explicit-human requests, consecutive fallback replies, and high-value order confirmations otherwise produce contradictory silence tests.
