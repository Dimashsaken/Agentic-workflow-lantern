# Memory — qa-dev

Long-term judgement for this role. Read fully at session start. Append at session end.

Rules: dated entries, concrete, with the *why*; append-only during runs; no secrets or
customer data. Target: under ~200 lines after consolidation.

## Learnings (append-only, newest last)

- 2026-08-24 (seed): Double-submit and back-button-mid-flow find more real bugs per
  minute than any other generic probe — they're in every charter until data proves
  otherwise.
- 2026-08-24 (seed): A video nobody can navigate is write-only. Always pair the link
  with timestamps per scenario; reviewers watch 30 seconds, not 10 minutes.

<!-- ENTRIES BELOW ARE RENDERED FROM THE role_memory TABLE — do not edit here; agents use append_memory, humans consolidate upward and re-run `pipeline.py render-memory` -->

- 2026-08-26 [manual · -] 2026-08-25: When the requested run folder is absent, stop before browser execution and explicitly leave the QA gate unevaluated, because inventing expected behavior or a target environment can produce a false pass.
- 2026-09-07 [feat-20260831-gate-latency · 04-qa-dev] 2026-09-07: Before seeding time-relative QA data, compare the target DB's now() against a trusted clock — this box was 6 days behind and resynced mid-stage, silently moving every seeded 30-day-window row out of window and aging every pending by 6 days at once. Re-time boundary-sensitive seeds immediately before the session that verifies them, and treat any mid-stage reachability blip as a "clock may have jumped" signal.
- 2026-09-07 [feat-20260831-gate-latency · 04-qa-dev] 2026-09-07: On a live control plane, only Approve a seeded gate whose run sits at the FINAL pipeline stage (advance() then marks it done); an Approve at any earlier stage flips the synthetic run to 'running' and the daemon will claim it and spend real agent tokens. Reject is safe at any stage (run → failed). Design decision round-trips around this before seeding.
- 2026-09-07 [feat-20260831-gate-latency · 04-qa-dev] 2026-09-07: Reachability preflights don't prove a QA stage can run — this dev environment's provisioned QA credentials had never been able to log in (placeholder LANTERN_QA_DEV_USER=none absent from LANTERN_WEB_USERS). Preflight should attempt a real login before a stage is dispatched.
- 2026-09-07 [feat-20260907-pipeline-smoke · 04-qa-dev] 2026-09-07: QA preflight must validate a real authenticated request, because this smoke attempt reached the login page but still had no usable credentials, making reachability alone a false readiness signal.
- 2026-09-07 [feat-20260907-pipeline-smoke · 04-qa-dev] 2026-09-07: When a retry exists solely to clear an environment blocker, explicitly retest that blocker first, then execute the highest-value non-destructive charter against live data; this preserves evidence without risking real control-plane gates.
