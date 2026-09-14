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

- 2026-09-11 [feat-20260911-tender-onboarding · 03-coding.review] 2026-09-11: Once signed cookies authorize tenant data, a committed development fallback signing key is an auth-bypass defect rather than a convenience, because anyone who knows the fallback can mint a valid session for a known tenant identifier; require deployment-supplied entropy or an explicitly isolated local-only mode.
- 2026-09-11 [feat-20260911-tender-onboarding · 03-coding.review] 2026-09-11: A duplicate-delivery concurrency regression must begin with no pre-existing aggregate when production uses get-or-create, because pre-seeding the conversation bypasses the earlier uniqueness race and can make a guarded message claim look complete while first-contact requests still fail.
- 2026-09-11 [feat-20260911-tender-onboarding · 03-coding.review] nothing durable learned this run: the round-2 fixes applied the already-recorded lessons about guarding the earliest uniqueness race and validating security boundaries in protocol order.
- 2026-09-11 [feat-20260911-tender-onboarding · 03-coding.review] nothing durable learned this run: attempt 4 revalidated the unchanged approved head after a fresh green gate, so it introduced no new product-specific review lesson.
- 2026-09-11 [feat-20260911-tender-onboarding · 03-coding.review] 2026-09-11: Generated editable-install metadata should be ignored rather than tracked or redirected into a virtual environment, because tracked manifests become stale as dependencies and sources change while a conventional ignored output keeps both packaging tools and clean-tree gates truthful.
- 2026-09-11 [feat-20260911-tender-onboarding · 03-coding.review] 2026-09-11: Secret-failure observability must include key parsing and codec construction, not only decrypt calls, because malformed deployment key material can throw before instrumented error handling and turn a generic denial into an unlogged 500.
- 2026-09-11 [feat-20260911-tender-onboarding · 03-coding.review] nothing durable learned this run: round 6 confirmed the fixes for the already-recorded lessons on key-construction failures and security tests that isolate each limiter dimension.
- 2026-09-11 [feat-20260911-tender-onboarding · 03-coding.review] 2026-09-11: Persistent navigation can expose later onboarding steps before prerequisites exist, so readiness must be enforced on both GET and POST and again at the shared service boundary; otherwise a valid authenticated shortcut turns missing setup data into a 500.
- 2026-09-12 [feat-20260911-tender-catalog-orders · 03-coding.review] 2026-09-12: Multi-item correction handlers must patch the uniquely identified draft line rather than reset the collection, because rebuilding from only the correction utterance silently drops valid items that the customer did not repeat.
- 2026-09-12 [feat-20260911-tender-catalog-orders · 03-coding.review] 2026-09-12: Returning an explicit rejected delivery receipt is safe only when every transactional caller checks it before commit; exception-only rollback silently persists inbound order state when an adapter reports `accepted=False` without raising.
- 2026-09-12 [feat-20260911-tender-catalog-orders · 03-coding.review] 2026-09-12: A conversational clarification must persist enough pending intent to consume the next answer, because emitting “which item?” while discarding the requested replacement makes the flow look safe but leaves the customer unable to complete the correction.
- 2026-09-12 [feat-20260911-tender-catalog-orders · 03-coding.review] 2026-09-12: Multi-error conversational repair must checkpoint each accepted repair before prompting for the next invalid item, because an early clarification return can otherwise discard progress and trap the user on the first stale line forever.
- 2026-09-12 [feat-20260911-tender-catalog-orders · 03-coding.review] nothing durable learned this run: round 5 confirmed the fix for the already-recorded lesson that each accepted conversational repair must be persisted before advancing to the next invalid item.
- 2026-09-12 [feat-20260911-tender-catalog-orders · 03-coding.review] 2026-09-12: When consolidating exact money formatting, search every seller template for inline minor-unit arithmetic, because a shared helper fixes only its registered consumers and one remaining `value / 100` expression can still misrender accepted high-value amounts.
- 2026-09-12 [feat-20260911-tender-catalog-orders · 03-coding.review] nothing durable learned this run: round 7 confirmed the already-recorded lesson that exact money formatting must be centralized across every seller template and chat consumer.
- 2026-09-12 [feat-20260911-tender-catalog-orders · 03-coding.review] nothing durable learned this run: round 8 verified the already-established migration-ownership lesson through aligned developer docs and a fresh-database migrate-then-signup smoke.
- 2026-09-12 [feat-20260911-tender-escalations · 03-coding.review] 2026-09-12: Browser-level retry flows must preserve the original durable delivery idempotency key across rejection/error renders and suppress new submissions while delivery is uncertain, because rotating the key turns a retry into a second outbound send and can leave the older unresolved row permanently blocking later state transitions.
- 2026-09-12 [feat-20260911-tender-escalations · 03-coding.review] nothing durable learned this run: round 2 confirmed the already-recorded browser idempotency-key lesson and verified the request-phrase and response-metric fixes without exposing a new defect class.
- 2026-09-12 [feat-20260911-tender-escalations · 03-coding.review] 2026-09-12: A plain-HTTP public-origin exception for an internal demo is reviewable only when the bypass is false by default, leaves all structural origin validation intact, and emits a startup warning whenever enabled, because the same setting controls takeover links that otherwise carry authentication over an unsafe transport.
- 2026-09-14 [feat-20260911-tender-escalations · 03-coding.review] 2026-09-12: Repeated lifecycle events need two explicit read-model projections—latest event for actions/unread and complete answered-event history for per-event metrics—because reusing one latest-only projection silently hides earlier valid durations after the aggregate cycles again.
