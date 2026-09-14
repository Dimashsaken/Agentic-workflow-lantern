# Memory — validator

Long-term judgement for this role. Read fully at session start. Append at session end.

Rules: dated entries, concrete, with the *why*; append-only during runs; no secrets or
customer data. Target: under ~200 lines after consolidation.

## Learnings (append-only, newest last)

- 2026-09-08 (seed): "Covered" needs code AND behaviour evidence (a test or a QA video
  timestamp). The fabrication saga of 2026-08-26 was a stage passing on claims alone;
  this role exists so that cannot happen to a feature's requirements.
- 2026-09-08 (seed): Write the verdict the statuses imply. Choosing "pass" with an
  off-spec criterion is caught mechanically and fails the stage anyway — the honest
  fail with a fix_now list is the faster path to done.

<!-- ENTRIES BELOW ARE RENDERED FROM THE role_memory TABLE — do not edit here; agents use append_memory, humans consolidate upward and re-run `pipeline.py render-memory` -->

- 2026-09-11 [feat-20260911-tender-onboarding · 05-post-coding.validate] 2026-09-11: When live external delivery is unsafe in dev, acceptance validation can combine the real HTTP boundary with an injected recording transport to prove handoff, persistence, deduplication, and event counts; retain a controlled staging interoperability check because mocked transport evidence does not prove provider compatibility.
- 2026-09-11 [feat-20260911-tender-onboarding · 05-post-coding.validate] 2026-09-11: When post-story abuse controls add 429 responses ahead of authentication work, validation must prove both the ordinary acceptance response and the exact N/N+1/reset behavior; the guard is compatible only when normal requests still satisfy the criterion and denied requests have no protected side effect.
- 2026-09-11 [feat-20260911-tender-onboarding · 05-post-coding.validate] 2026-09-11: A readiness fix is acceptance-safe only when evidence proves both sides of the boundary: precondition failures have zero protected side effects and completing setup restores the promised exactly-once behavior; a provider-facing 2xx drop still needs separate visibility because safe HTTP does not mean retained customer work.
- 2026-09-12 [feat-20260911-tender-catalog-orders · 05-post-coding.validate] 2026-09-12: A feature-flag acceptance criterion can be validated compositionally when selection code, a no-network fallback test, and the shared downstream state-machine tests are all present; still name live provider interoperability as staging-only because deterministic injected evidence does not prove deployed provider configuration.
- 2026-09-12 [feat-20260911-tender-catalog-orders · 05-post-coding.validate] 2026-09-12: After a security rework moves status persistence before external delivery, acceptance validation must split the projections: prove one durable status/history edge, truthful rejected-versus-uncertain seller copy, and exactly one accepted customer transcript; checking only the final order status can hide duplicate sends or false success.
- 2026-09-12 [feat-20260911-tender-escalations · 05-post-coding.validate] 2026-09-12: When a conversation can be escalated more than once, proving a median and the latest event is insufficient for a requirement to show each answered escalation; validation needs a same-conversation, two-cycle scenario because a latest-only read model silently hides historical first-reply durations.
- 2026-09-14 [feat-20260911-tender-escalations · 05-post-coding.validate] 2026-09-14: A repeated-lifecycle history fix is acceptance-safe only when one scenario proves both projections simultaneously: all immutable past event metrics remain visible, while unread state and actions still target only the latest active event.
