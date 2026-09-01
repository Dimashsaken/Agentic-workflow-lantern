# Stage Report: 03-coding — feat-20260831-gate-latency

- **Agent/author:** dimash (developer session — Claude Code on the laptop, branch `claude/gate-latency-statusline-ledger-9189b4`)
- **Date:** 2026-09-01
- **Status:** PASS-WITH-NOTES

## Summary

The approved `statusline-ledger` UX is implemented: the Board renders a full-width
per-gate 30-day median ledger between the statusline and the five columns, every
pending Review card shows its age, and cards strictly older than 24h get an explicit
`STALE` warning treatment. All 34 new behavior tests plus the existing no-DB
repository test pass; the two checks that need a live Postgres (`EXPLAIN` plan
evidence, `test_verification.py`) are deferred to the box because no local database
was reachable — see Findings 1–2.

## Work performed

Six tasks, one commit each, tests first (`a0d9fda` → `717dad6`):

1. **`tools/mission-control/test_gate_latency.py`** (task 1) — 34 stdlib
   `unittest` cases; no DB, no HTTP client, no new packages. Routes are exercised
   by calling the coroutine endpoints directly with a signed session cookie and a
   `FakePool` that answers `snapshot()`'s queries and records every SQL statement.
2. **Data assembly** (task 2) — `snapshot()`'s unused all-time scalar `decided`
   fetchrow is replaced by one grouped query (`LATENCY_SQL`): per-gate
   `percentile_cont(0.5)` of `decided_at - requested_at` seconds plus count, over
   approvals with `status IN ('approved','rejected') AND decided_at IS NOT NULL
   AND decided_at >= now() - interval '30 days'`. `gate_latency_rows()` normalizes
   to `GATE_META` order and keeps unknown historical gates; `ledger_metrics()`
   formats display values; `is_stale()` is strictly `> 24*3600`. A
   `PostgresError` on this one query degrades to `gate_latency=None`.
3. **Ledger render** (task 3) — `ui.gate_ledger()` + `.ledger` CSS (existing
   tokens only), wired into `board()` between statusline and `.kb`. Stage-1
   wording exactly: `GATE LATENCY · LAST 30 DAYS`, `Median time to decision ·
   UTC`, `<gate> · n=<k>`, and `— · no decisions · n=0` for empty cohorts —
   never `0h`. Medians over 24h render in `--warning`.
4. **Stale Review cards** (task 4) — `build_card()` computes waited seconds once
   from `approvals.requested_at`; strictly over 24h adds a `STALE` warn chip and a
   `stale` card class (`--warning` border, warning-colored age). Approve/Reject
   forms, evidence link, stage rail, cost footer, and report-blocked precedence
   are unchanged. `gate_card()` on `/gates` and `/run/{id}` untouched.
5. **Failure isolation + verification** (task 5) — isolation and route
   regressions were specified in task 1 and went green as tasks 2–4 landed.
   Browser verification (real `board()` output rendered through the test fakes at
   1440px and 720px) caught the ledger 36px over at 1440; gap 44→32px fixed it.
   At 720px the strip scrolls internally, the page body never scrolls
   horizontally, and the last metric is reachable. Degraded and zero-decision
   states render their exact copy.
6. **Docs + self-review** (task 6) — `tools/mission-control/README.md` and
   `docs/MISSION-CONTROL.md` updated; whole-diff review done (one PEP8
   blank-line fix).

Definition-of-code-complete checklist from the task plan: all boxes hold except
the query-plan half of "query plan is acceptable", deferred per Finding 1.
Verified explicitly: constant query count regardless of cards/gate types
(asserted by test), no new package/write/alert/client-clock/threshold-config/
chart/analytics code anywhere in the diff.

## Findings / results

1. **[deferred — for qa-dev] `EXPLAIN (ANALYZE, BUFFERS)` not run.** No reachable
   Postgres from this laptop (no local service; Docker Desktop daemon down; the
   `.env` DSN is `localhost:5432/lantern`). Analysis: the query is one grouped
   aggregate over `approvals`, whose volume is one row per gate per run — even
   hundreds of runs is a few thousand rows, where a seq scan is optimal and the
   existing partial index (`pending` only) is irrelevant. I judge no index
   required, so no schema approval is triggered; QA on the box should run the
   EXPLAIN to confirm and attach it to the 04-qa-dev report.
2. **[deferred — for qa-dev] `tools/azure-runner/test_verification.py` needs the
   DB** and was not run for the same reason. `test_product_access.py` (no DB)
   passes. The mission-control change touches neither file's subject matter.
3. **[note] SQL semantics are unit-tested as a query contract** (assertions on
   `LATENCY_SQL`'s clauses), not against a live database — the honest limit of
   the no-DB test design the plan prescribed. The DB-level behaviors (30-day
   boundary row inclusion, interpolated medians) are exactly what the QA charter
   should exercise with seeded approvals.
4. **[note] Theme modes:** the deployed app is dark-only (single `:root` palette
   in `ui.py`); there is no light mode to verify, so "both theme modes if
   supported" is vacuously satisfied.
5. **[note] `/runs` strips intentionally carry no stale treatment** — the plan
   scopes stale visuals to Board Review cards; strips already show elapsed time.

## Artifacts

- Branch `claude/gate-latency-statusline-ledger-9189b4`, commits `a0d9fda`,
  `49e9c4d`, `fa693e8`, `ab05cf3`, `622eba3`, `717dad6` (one per task).
- `tools/mission-control/test_gate_latency.py` — the executable behavior contract;
  `python -m unittest test_gate_latency` from `tools/mission-control` using the
  azure-runner venv. Result this session: **34/34 OK** (plus
  `test_product_access.py` all-pass).
- No videos this stage (developer stage; QA records video in 04).

## Handoff notes for the next stage

- **QA entry point:** seed decided approvals across ≥2 gate types with known
  timestamps, including one exactly 24h pending, one just over, one decided 31
  days ago (must be excluded), one expired and one pending decision (both must be
  excluded from medians), and an even-sized cohort (median should interpolate).
  The live board is `LANTERN_QA_DEV_BASE_URL`.
- **QA confidence map** (where I am least/most confident):
  - *Median cohort semantics against a real DB* — **medium**: clause-level unit
    coverage only (Finding 3); highest-value QA target.
  - *24h boundary* — **high**: strictness is pinned at helper, card, and route
    levels; exact-24h and future-timestamp cases are tested.
  - *Board layout* — **medium-high**: verified in a real browser at 1440/720 with
    overflow measurements, but only on Chromium and only with 2 populated + 3
    empty metrics; a board with five long medians (`"23h 59m"`-shaped values) and
    an unknown sixth gate is worth one look, as is Firefox.
  - *Failure isolation* — **high** at the unit/route level, but the injected
    failure is a `PostgresError` on one query; a real outage takes the whole
    snapshot down (pre-existing behavior, unchanged by design).
- The `EXPLAIN` from Finding 1 is a five-minute box task — please close it.
- `snapshot()` also runs the latency query for `/runs` (shared batch, per the
  blast-radius design); its result is simply unused there.

## Open questions (BLOCKED status must have exactly one)

None.

## Memory candidates

Recorded here for the postmortem trail — this developer session runs outside the
orchestrator, so the `append_memory` tool is not wired in this harness; the
learnings below should ride along when the stage is recorded (same convention as
prior stage-3 sessions):

- 2026-09-01: Mission Control behavior tests need neither Postgres nor httpx —
  the route coroutines take a stub `Request` (cookies only) and `app.pool` can be
  swapped for a query-dispatching fake; asserting on a module-level SQL constant
  pins query semantics without a DB. Pattern lives in `test_gate_latency.py`.
- 2026-09-01: ui.py's flight-strip caps labels are wide — a flex strip of five
  caps-labeled metrics at 44px gaps overflows a 1440px viewport by ~36px.
  Measure `scrollWidth` in a real browser before calling a full-width strip done.
