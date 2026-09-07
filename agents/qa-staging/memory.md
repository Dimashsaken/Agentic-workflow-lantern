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
