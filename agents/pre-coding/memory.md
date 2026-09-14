# Memory — pre-coding

Long-term judgement for this role. Read fully at session start. Append at session end.

Rules: dated entries, concrete, with the *why*; append-only during runs; no secrets or
customer data. Target: under ~200 lines after consolidation.

## Learnings (append-only, newest last)

- 2026-08-24 (seed): The blast radius that bites is almost never the code you change —
  it's the untracked consumer of the thing you changed. Always grep for callers,
  cron jobs, and webhook/event listeners before sizing.
- 2026-08-24 (seed): Every schema plan ships with a rollback migration written at the
  same time as the forward one; "we'll write it if needed" means it doesn't exist
  during the incident.

<!-- ENTRIES BELOW ARE RENDERED FROM THE role_memory TABLE — do not edit here; agents use append_memory, humans consolidate upward and re-run `pipeline.py render-memory` -->

- 2026-08-27 [feat-20260825-candidate-compare · 02-pre-coding] 2026-08-27: A feature brief must identify the product repository and base branch before pre-coding, because otherwise exact blast radius, consumer tracing, schema impact, and executable task paths cannot be established without guessing.
- 2026-08-27 [feat-20260825-role-health · 02-pre-coding] 2026-08-27: A brief saying “no new data collection” does not prove “no schema change”; derived-health materialization and dismissal/action state can still require storage, so inspect the actual schema and query cost before declaring a schema-free plan.
- 2026-08-31 [feat-20260825-candidate-compare · 02-pre-coding] 2026-08-31: Product-target validation must check domain symbols and schema after cloning, not merely checkout success, because a valid but wrong repository produces the same fabricated blast-radius risk as no repository.
- 2026-08-31 [feat-20260831-gate-latency · 02-pre-coding] 2026-08-31: When an approved UX option is knowingly narrower than the brief, pre-coding must preserve the chosen composition while explicitly planning the smallest companion needed for acceptance, because silently choosing a different option overrides human authority while implementing only the selected screen misses the product outcome.
- 2026-09-01 [feat-20260831-gate-latency · 02-pre-coding] 2026-09-01: A rejected downstream plan followed by a corrected UX decision must trigger a clean re-plan from the authoritative gate record, not an incremental patch to the old plan, because stale scope can otherwise survive in tasks and become accidental implementation.
- 2026-09-07 [feat-20260907-status-json · 02-pre-coding] 2026-09-07: When adding machine output to a mature CLI, freeze the human stdout before branching because spacing and empty-state text can be an undocumented scripting interface even when no code caller exists.
- 2026-09-11 [feat-20260911-tender-onboarding · 02-pre-coding] 2026-09-11: When a feature must recover per-tenant API secrets, UI redaction is not an at-rest protection plan; choose and approve encryption plus key lifecycle before fixing the schema, because plaintext columns or an improvised reversible codec turn an onboarding feature into a durable credential-exposure risk.
- 2026-09-11 [feat-20260911-tender-onboarding · 02-pre-coding] 2026-09-11: When downstream rework authorizes new product paths, amend the typed plan's write_scope before rerunning coding, because a human-approved cleanup still fails the mechanical gate when the executable scope envelope remains stale.
- 2026-09-12 [feat-20260911-tender-catalog-orders · 02-pre-coding] 2026-09-11: Owner-triggered WhatsApp transitions need a standalone encrypted-credential loader and a conditional database state claim before the send, because webhook-only credential loading and naive send-then-update logic create duplicate notifications or false status/history under retries.
- 2026-09-12 [feat-20260911-tender-catalog-orders · 02-pre-coding] 2026-09-12: Removing startup create_all requires the same approved change to update developer commands and exercise a fresh migrated database through HTTP, because a live health endpoint does not prove database-backed routes can serve.
- 2026-09-12 [feat-20260911-tender-escalations · 02-pre-coding] 2026-09-12: Adding a durable “automation paused” state is not rolling-deploy compatible merely because its schema is additive; old workers must be drained before new state is created because they cannot honor the silence invariant and may reply to an escalated conversation.
- 2026-09-12 [feat-20260911-tender-escalations · 02-pre-coding] 2026-09-12: Unread state for webhook-driven conversations should compare owner reads with server processing activity, not provider event timestamps, because delayed delivery can carry an older source time yet still need to restore unread after the owner viewed the thread.
