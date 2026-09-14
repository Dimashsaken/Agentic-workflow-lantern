# Memory — security

Long-term judgement for this role. Read fully at session start. Append at session end.

Rules: dated entries, concrete, with the *why*; append-only during runs; no secrets or
customer data (and no unpatched-vuln details — those live outside the repo until fixed).
Target: under ~200 lines after consolidation.

## Learnings (append-only, newest last)

- 2026-08-24 (seed): Read the authz check in the handler itself. "The middleware
  covers it" is the assumption behind most IDOR findings.
- 2026-08-24 (seed): The lockfile diff is part of the diff. New transitive dependencies
  arrive silently and are nobody's explicit decision unless this role makes them one.

<!-- ENTRIES BELOW ARE RENDERED FROM THE role_memory TABLE — do not edit here; agents use append_memory, humans consolidate upward and re-run `pipeline.py render-memory` -->

- 2026-08-26 [manual · -] 2026-08-25: For authentication features, an unidentified release branch is itself a no-go condition because endpoint authorization, dependency provenance, staging secrets, and rollback behavior cannot be inferred from feature intent.
- 2026-09-07 [feat-20260907-pipeline-smoke · 06-security] 2026-09-07: For read-only dashboard aggregates, security review must include the shared-route query cost and failure isolation even when there is no input injection surface, because authenticated polling can turn table growth into an availability risk.
- 2026-09-11 [feat-20260911-tender-onboarding · 06-security] 2026-09-11: Public sign-up that performs a 600,000-iteration password hash before uniqueness resolution needs shared throttling, because CSRF is not bot protection and arbitrary unique-email submissions can exhaust CPU while growing tenant data.
- 2026-09-11 [feat-20260911-tender-onboarding · 06-security] 2026-09-11: A pre-authentication business-key webhook throttle can itself become a tenant denial primitive, so pair early source-IP load shedding with trusted ingress and apply shared or authenticated business quotas before scaling beyond one internal worker.
- 2026-09-11 [feat-20260911-tender-onboarding · 06-security] 2026-09-11: Setup-dependent message flows need readiness enforcement in the shared message service as well as route-level UX guards, because a router-only redirect does not protect webhook or future adapter entry points from partial writes and outbound side effects.
- 2026-09-12 [feat-20260911-tender-catalog-orders · 06-security] 2026-09-12: An external notification accepted before the matching database commit needs a durable outbox, persisted provider receipt, and reconciliation path, because process or commit failure can otherwise leave an irreversible customer message invisible locally and make retries duplicate it.
- 2026-09-12 [feat-20260911-tender-catalog-orders · 06-security] 2026-09-12: A durable outbox closes the duplicate-send gap only when ambiguous `sending` attempts are never retried blindly; provider callbacks or other authoritative evidence must reconcile them, and stale ambiguous rows need explicit monitoring because safety otherwise becomes an indefinite availability block.
- 2026-09-14 [feat-20260911-tender-escalations · 06-security] 2026-09-14: When customer transcript text is embedded in a branded owner notification, bound and visibly quote the excerpt and neutralize line/control-character injection, because otherwise an external customer can make their text look like trusted takeover instructions or force the provider to reject an oversized alert.
