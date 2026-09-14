# Memory — qa-staging

Long-term judgement for this role. Read fully at session start. Append at session end.

Rules: dated entries, concrete, with the *why*; append-only during runs; no secrets or
customer data. Target: under ~200 lines after consolidation.

## Learnings (append-only, newest last)

- 2026-08-24 (seed): Verify integrations at the receiving end (the inbox, the webhook
  consumer's log, the bucket) — a 200 response is a claim, not a delivery.
- 2026-08-24 (seed): Analytics verification belongs in PostHog itself; events visible
  in the browser's network tab can still be dropped by ingestion filters.

<!-- ENTRIES BELOW ARE RENDERED FROM THE role_memory TABLE — do not edit here; agents use append_memory, humans consolidate upward and re-run `pipeline.py render-memory` -->

- 2026-09-07 [feat-20260907-pipeline-smoke · 07-qa-staging] 2026-09-07: For a staging smoke run of an already-deployed read-only dashboard feature, verify deployment identity indirectly with newly staging-specific data (here the staging-deploy cohort changed from n=0 in dev to n=1 in staging) because identical static copy alone does not prove the staging database and deployment path are live.
- 2026-09-11 [feat-20260911-tender-onboarding · 07-qa-staging] 2026-09-11: Staging onboarding QA must exercise persistent/global navigation before setup completion, because a fresh provisioned account exposed Sandbox before a business profile existed and a valid send reached an unhandled missing-profile path (HTTP 500) even though the configured happy path passed.
- 2026-09-11 [feat-20260911-tender-onboarding · 07-qa-staging] 2026-09-11: A staging fix for a setup-dependent flow should be verified with a genuinely fresh account and both direct GET and valid-CSRF POST, then followed by an empty-state side-effect check and a configured happy-path control, because a persisted shared account cannot reproduce missing-profile behavior honestly.
- 2026-09-12 [feat-20260911-tender-catalog-orders · 07-qa-staging] 2026-09-12: A staging order-flow pass on an explicitly Sandbox-only account cannot clear a production notification gate, because it never proves receiving-side Meta acceptance, callback reconciliation after worker loss, or target-database contention even when status/history/transcript replay is correct.
- 2026-09-12 [feat-20260911-tender-catalog-orders · 07-qa-staging] 2026-09-12: When a human waives production-like staging integrations for an internal demo, rerun the complete supported channel and preserve each waiver beside the pass recommendation, because a green Sandbox result should authorize only the demonstrated scope rather than silently broadening into Cloud or cross-browser assurance.
- 2026-09-14 [feat-20260911-tender-escalations · 07-qa-staging] 2026-09-14: For repeated escalation metrics on staging, create two answered cycles in the same conversation and leave the newest active, because that single state proves historical first-reply retention and median inclusion while also showing that hand-back and paused-state actions still target only the latest event.
