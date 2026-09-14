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
- 2026-09-07 [feat-20260907-pipeline-smoke · 05-post-coding] 2026-09-07: When a smoke run reuses an already merged feature, compare the current tree against the original approved plan and prior stage-5 resolutions, because reviewing only the smoke run's empty main-to-HEAD diff can miss both the real feature scope and whether earlier fix-now findings stayed resolved.
- 2026-09-11 [feat-20260911-tender-onboarding · 05-post-coding] 2026-09-11: When a feature adds its first runtime dependency to a repository that tracks generated `*.egg-info`, redirecting `egg_base` into a virtualenv only hides stale dependency and source metadata; remove and ignore generated metadata instead, because contradictory package manifests mislead builds, scanners, and maintainers.
- 2026-09-11 [feat-20260911-tender-onboarding · 05-post-coding] 2026-09-11: When a post-coding fix requires paths outside an approved write scope, amend and reapprove the typed plan before rerunning coding; otherwise the quality gate either rejects the correct cleanup or pressures the builder to revert it, because human intent and mechanical authorization must agree.
- 2026-09-11 [feat-20260911-tender-onboarding · 05-post-coding] 2026-09-11: A process-local abuse limiter needs a post-coding cardinality pass even when security approves it for a demo, because full-map expiry scans and non-shared counters can make the control itself costly or bypassable under distributed identity churn; record the bounded distributed replacement before production.
- 2026-09-11 [feat-20260911-tender-onboarding · 05-post-coding] 2026-09-11: A typed readiness exception should be translated separately at each ingress—browser flows can redirect after CSRF, while signed provider webhooks need a retry contract—but any provider-facing 2xx drop also needs explicit operational visibility because the provider will treat the message as delivered.
- 2026-09-12 [feat-20260911-tender-catalog-orders · 05-post-coding] 2026-09-12: Once Alembic owns production schema, an unconditional application-startup `create_all` must be removed or explicitly limited to dev/tests, because it can create unversioned tables and silently undo the physical effect of a downgrade.
- 2026-09-12 [feat-20260911-tender-catalog-orders · 05-post-coding] 2026-09-12: When removing startup `create_all` after Alembic adoption, update and test the documented development boot path in the same change, because an apparently healthy Uvicorn process can otherwise fail on its first database-backed route against an empty schema.
- 2026-09-12 [feat-20260911-tender-catalog-orders · 05-post-coding] 2026-09-12: A migrate-before-run documentation fix is only trustworthy when its regression starts from an absent database and completes a persisted HTTP flow after migration, because process startup or `/healthz` alone does not prove the application schema is usable.
- 2026-09-12 [feat-20260911-tender-catalog-orders · 05-post-coding] 2026-09-12: A durable outbox can close an accepted-send/commit gap while still leaking memory if adapters retain every reconciliation receipt forever; post-coding must separately bound process-local correlation caches because durable database state does not bound helper-process state.
- 2026-09-12 [feat-20260911-tender-escalations · 05-post-coding] 2026-09-12: When a server-rendered inbox enriches an existing conversation list with per-row event and delivery state, an inherited N+1 can silently become a three-query-per-row fan-out; query-count and bounded-preview tests are needed because rendering only three messages does not help if the service first materializes the full transcript.
- 2026-09-14 [feat-20260911-tender-escalations · 05-post-coding] 2026-09-14: When correctness requires every child event to remain visible, adding an unbounded per-parent history query can fix the criterion while worsening an existing N+1; batch the histories for a bounded parent page and keep older events accessible through explicit history pagination because completeness does not require linear SQL fan-out.
