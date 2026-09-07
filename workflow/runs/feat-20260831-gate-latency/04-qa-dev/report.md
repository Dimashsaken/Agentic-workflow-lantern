# Stage Report: 04-qa-dev — feat-20260831-gate-latency

- **Agent/author:** qa-dev (Claude Code session on the laptop, worktree
  `gate-latency-qa-stage4-8db671`; browser sessions via `tools/qa-recorder`
  scripted Playwright, video on for every session)
- **Date:** 2026-09-07
- **Status:** PASS-WITH-NOTES

## Summary

The gate-latency feature passes: all four charter priorities verified against the
live dev Mission Control with 124/126 scripted checks green across 8 recorded
sessions, and the 2 non-passes are QA-harness artifacts (clock jump, deliberate
409 probe), not product behavior. Zero product bugs filed — the gate condition
(no open sev-1/sev-2) is met; the notes are three environment findings (feature
was not actually deployed at stage start; provisioned QA credentials could not
log in; the box clock was 6 days wrong and resynced mid-stage). Next:
post-coding review of branch `claude/gate-latency-statusline-ledger-9189b4`.

## Work performed

Charter in `test-charter.md`, executed as 8 one-context-one-video sessions
(all synthetic data under run ids `qa-20260901-*`, deleted at the end; the real
pending `code_complete` gate was never decided):

1. **Median cohort semantics vs the real DB** (priority 1, dev confidence
   MEDIUM) — seeded cohorts where every wrong inclusion/exclusion changes the
   visible median or n: approved+rejected both counting (n=5 odd cohort),
   decided-at 30-day boundary (a just-inside row counted, a 31-days-ago row
   excluded), pending/expired rows excluded even with plausible `decided_at`,
   even cohort interpolating per `percentile_cont` (1h/2h/3h/5h → `2h 30m`),
   `— · no decisions · n=0` (never `0h`) for the empty cohort, unknown
   historical gate rendered after the known five with warn color for a >24h
   median. Every rendered value was compared against an independent Python
   reimplementation of median interpolation + the humane formatter fed by raw
   DB rows fetched at verification time — exact match on all six metrics
   (session 2, 24/24).
2. **24h staleness boundary** (priority 2) — pendings re-timed to 23h58m and
   24h02m immediately before verification: under shows no STALE and no warning
   treatment; over shows the STALE warn chip, `.stale` warning border
   (rgb(231,147,90) vs the normal rgb(46,42,34)), warning-colored age, with
   Approve/Reject and the evidence link still present and working; a 98h
   pending renders humane `4d 2h`. Run detail repeats `waiting 24h 02m` with no
   STALE chip (stale visuals are scoped to Board Review cards by plan).
   Exact-equality strictness at 24h stays unit-pinned (`test_gate_latency.py`);
   live checks bracket the boundary to ±2 minutes (session 3, 17/17).
3. **Board layout** (priority 3) — with all five known gates carrying long-form
   medians plus the unknown sixth: at 1440×900 the strip fits exactly
   (scrollWidth 1440) with no clipped value; at 720×900 the strip scrolls
   internally (1279px content in a 720px strip, overflow-x auto), the last
   metric is reachable by scrolling the strip, and the page body never scrolls
   sideways at either width. Verified in Chromium (session 5, 10/10) and
   Firefox 153 (session 6, 10/10 — run on the box; the laptop's Playwright
   Firefox build fails to start for lack of a VC++ runtime).
4. **Regressions and round-trips** (priority 4) — signed-out `/`, `/runs`,
   `/gates`, `/run/{id}` all 303 to /login with no data leaked; wrong password
   rejected; `/runs` and `/gates` render with ages (no STALE on `/runs` strips,
   per coding note 5); the real run's Review card shows its gate age (`5d 23h`,
   correctly STALE — the brief's motivating case, live on the board). Full
   Approve round-trip on a seeded run at stage 7/7 → run `done`, `shipped`
   chip, card leaves Review, and the ledger's prod cohort went n=0 → n=1 with
   the decision's true elapsed (517664s → `5d 23h`, verified by DB
   recomputation) — proving the ledger reads live decision data (session 4,
   13/14). Reject round-trip → run `failed`, Blocked column (safe-by-design:
   only the last-stage seeded run was ever approved, so the daemon could never
   claim real work for a synthetic run).
5. **Exploratory** (session 7, 10/11) — ages advance across refreshes
   (server-rendered, `24h 10m` → `24h 11m`); rapid navigation stable; two-tab
   double-submit of the same gate decision returns 409 with exactly one
   decision recorded; narrow-width stale card keeps STALE adjacent to the gate
   identity with usable controls; logout → protected routes again → re-login.
6. **Read-only audit** — across all sessions the only non-GET requests were
   `/login`, `/logout`, and the pre-existing `/gate/{id}/{decision}` POSTs this
   charter itself issued; no write/alert/chart/analytics/config surface
   observed. Console clean except the deliberate 409 probe's fetch log.
7. **Cleanup** (session 8, 9/9) — every seeded row deleted (approvals/events/
   runs back to the pre-stage baseline of 10/11), then the board re-verified
   against freshly recomputed real-only expectations: no synthetic residue, and
   the live ledger honestly shows `plan sign-off · n=4 · 2d 10h` in warn — the
   4-day plan_signoff pathology the brief was written about, now visible.

Not executed live, deliberately: forcing the ledger's degraded state
(`Gate latency unavailable — refresh.`) needs a Postgres failure injected into
the live control plane; it stays covered by the unit contract, as does exact
24h equality.

## Findings / results

1. **[env, fixed in-stage] Feature was not deployed at stage start.** Kickoff
   said `feat/gate-latency` was live in dev; the box was at pre-coding
   `525a6da` and the coding commits existed only on
   `claude/gate-latency-statusline-ledger-9189b4` (locally — never pushed, and
   not merged into `feat/gate-latency`). This session deployed that branch
   (clean fast-forward, bundle-over-scp), moved the box's `feat/gate-latency`
   ref to `b75a4f2`, and restarted only `lantern-mission-control`. Landmine
   for post-coding: the local/remote `feat/gate-latency` refs still lack the
   coding commits — review the coding branch, and reconcile refs before stage 6.
2. **[env, fixed in-stage] Provisioned QA dev credentials could not log in**
   (`LANTERN_QA_DEV_USER=none`, matching no `LANTERN_WEB_USERS` entry).
   `qa-preflight` validates reachability but not login, so every sandboxed
   stage-4 run would have stalled at the login form. Fixed on the box `.env`
   (backup `/tmp/env.backup.qa-stage4`): `qa-dev` user added with the already
   provisioned password, `LANTERN_QA_DEV_USER=qa-dev`. Known side effect: the
   derived cookie secret changed (no explicit `LANTERN_WEB_SECRET`), logging
   out pre-existing sessions once. SSM `/lantern/qa/dev/*` was not readable
   from the box role at check time (ParameterNotFound) — worth aligning when
   SSM is touched next.
3. **[env] The box clock was ~6 days behind and resynced mid-stage** (box
   `now()` jumped Sep 1 → Sep 7 during a ~25-minute unreachability window;
   laptop egress IP change was ruled out — same IP after recovery). All
   time-relative seeds shifted at once; affected seeds were re-timed and
   sessions re-run. Until the resync, every age and median on the live board
   was computed against a wrong "now".
4. **[product, none]** Zero product bugs — see `bugs.md` for the full
   accounting of the 2 harness-artifact non-passes.

## Artifacts

All local to this stage dir; the orchestrator upload pass was not run (this
session ran outside the orchestrator, so no S3 URLs are claimed). Videos are in
recording order; durations are short because headless scripted runs are fast.

- `test-charter.md` — the charter, written before execution
- `bugs.md` — zero product bugs + environment findings E-1..E-3
- `media/session-1--auth-regressions.webm` (0:11) — 0:00 signed-out redirects
  ×4, ~0:04 wrong-password rejection, ~0:06 login + board (ledger + real STALE
  card), ~0:08 /runs, /gates, /run/{id}
- `media/session-2--ledger-semantics.webm` (0:13) — board ledger with all six
  cohorts; ~0:05 ledger scrolled into view and held for reading
- `media/session-3--staleness-boundary.webm` (0:07) — 0:00 board with 23h58m
  (no STALE) beside 24h02m (STALE) and 4d 2h cards, ~0:04 evidence link →
  /gates, ~0:06 run detail `waiting 24h 02m`
- `media/session-4--decision-roundtrips.webm` (0:12) — 0:00 board with prod
  n=0, ~0:03 Approve → run page `Shipped`, ~0:06 board Done column + prod n=1
  in ledger, ~0:09 Reject → failed card
- `media/session-5--layout-chromium.webm` (0:08) — 1440px board then 720px with
  the strip's internal scroll to the last metric
- `media/session-6--layout-firefox.webm` (0:06) — same two widths in Firefox
- `media/session-7--exploratory.webm` (1:30) — 0:00–1:06 age-advance wait
  across refresh (24h 10m → 24h 11m), ~1:08 rapid navigation, ~1:12 two-tab
  double-submit → 409, ~1:20 narrow-width stale card, ~1:25 logout/re-login
- `media/session-7b--exploratory-tab-b.webm` (0:04) — tab B of the
  double-submit probe (the tab whose decision won)
- `media/session-8--post-cleanup.webm` (0:06) — board back to real-only data,
  no synthetic residue
- `media/shots/*.png` — 19 keyframe screenshots referenced above

## Handoff notes for the next stage

- **post-coding reviews branch `claude/gate-latency-statusline-ledger-9189b4`
  (`b75a4f2`)** — that is what is deployed and what QA validated. The
  `feat/gate-latency` name on the box now points at it; laptop/origin refs do
  not yet.
- The real `code_complete` gate for this run is still pending (untouched by
  QA, per charter hard rule) and is now visibly STALE on the board at 5d+ —
  deciding it is the human's move.
- Environment fixes E-1/E-2 live only on the box (`.env` + checkout); nothing
  in this repo changed for them. E-3 (clock) deserves an ops follow-up: chrony
  health on the box, and a preflight `now()` sanity check for QA stages.
- QA harness for reuse: session scripts + independent median calculator are in
  this attempt's scratchpad pattern (`compute-expected.py`, `qa-lib.mjs`,
  `s1…s8`); the committed regression seeds remain `test_gate_latency.py` (34
  unit cases) — no new permanent Playwright spec was promoted because no bug
  repro exists to pin.

## Open questions (BLOCKED status must have exactly one)

None.

## Memory candidates

Recorded via `role_memory` insert (the orchestrator's `append_memory` path)
this session:

- 2026-09-07: Before seeding time-relative QA data, compare the target DB's
  `now()` against a trusted clock — this box was 6 days behind and resynced
  mid-stage, which silently moved every seeded 30-day-window row out of window
  and aged every pending by 6 days at once. Re-time boundary-sensitive seeds
  immediately before the session that verifies them, and treat any mid-stage
  reachability blip as a "clock may have jumped" signal.
- 2026-09-07: On a live control plane, only ever Approve a seeded gate whose
  run sits at the final pipeline stage (advance() then marks it done); an
  Approve at any earlier stage flips the synthetic run to 'running' and the
  daemon will claim it and spend real agent tokens. Reject is safe at any
  stage (run → failed). Design decision round-trips around this before
  seeding.
- 2026-09-07: qa-preflight-style reachability checks don't prove a QA stage
  can run — this environment's provisioned QA credentials had never been able
  to log in (placeholder user not present in LANTERN_WEB_USERS). A preflight
  should attempt a real login (or a signed-cookie probe) before a stage is
  dispatched.
