# Test charter — feat-20260831-gate-latency (04-qa-dev, attempt 1)

Target: live Mission Control on the box (dev == control plane, P0.3 dogfood).
Deployed: branch `feat/gate-latency` @ `b75a4f2` (coding branch fast-forwarded onto
the previously-deployed `525a6da`; deployed by this QA session — see report, env
finding E-1). All seeded data uses run ids `qa-20260901-*`, `created_by='qa-dev-stage4'`,
decided_by `qa-dev` — deleted at session end.

Hard rule: the REAL pending gate (`feat-20260831-gate-latency` / `code_complete`)
is never decided. Decisions happen only on seeded synthetic runs.

## 1. Confidence-map probes (highest value first)

### 1.1 Median cohort semantics against the real DB (dev confidence: MEDIUM)

Seeded cohorts are designed so that every wrong-inclusion/exclusion produces a
*visibly different* median or n. Expected values are computed independently
(Python percentile-interpolation over rows fetched from the DB at verification
time) and compared against the rendered board.

| Gate | Cohort after seeding | What it proves |
|---|---|---|
| ux_signoff | 3 existing approved + seeded 1 approved (2h) + 1 **rejected** (1h) → n=5, odd | rejected counts; if rejected were excluded → n=4 and different median |
| plan_signoff | 4 existing + seeded decided `now-30d+10min` (just inside) + decided `now-31d` (outside, dur 999999s) → n=5 | 30-day boundary is on `decided_at`; wrong inclusion of the 31d row shifts median hugely |
| code_complete | seeded 4 decided (1h/2h/3h/5h) + seeded **expired** row with `decided_at` set + the real **pending** row → n=4, even | even cohort must interpolate → 2h 30m (percentile_cont); expired and pending rows excluded even with plausible timestamps |
| staging_deploy | seeded 1 decided, dur 86340s → n=1 | long-form `23h 59m` display; 86340 < 86400 → NOT warn-colored; existing expired row excluded |
| prod_signoff | nothing | `— · no decisions · n=0`, never `0h` (until §4 round-trip adds one — checked BEFORE §4) |
| qa_legacy_gate (unknown) | seeded 1 decided, dur 90000s | unknown historical gate appears AFTER the known five, not dropped; >24h median renders warn |

Also: stable GATE_META order (ux, plan, code-complete, staging, prod, then unknown),
`GATE LATENCY · LAST 30 DAYS` + `Median time to decision · UTC` copy.

### 1.2 24h staleness boundary (dev confidence: HIGH — verify anyway)

Strictness (`>`, not `>=`) at exactly 24h is pinned by unit tests; live check
brackets the boundary as tightly as a live clock allows:
- pending seeded at `now - 24h + 180s` → renders `23h 5xm`, NO stale treatment.
- pending seeded at `now - 24h - 120s` → renders `24h 0xm`, STALE warn chip,
  warning border (`.kcard.stale`), warning-colored age.
- STALE card still carries working Approve/Reject forms and the evidence link.
- pending seeded at `now - 4d2h` → humane `4d 2h`, stale.
- run detail (`/run/{id}`) still shows `waiting <age>` via gate_card (no stale
  chip there by design — plan scopes stale visuals to Board Review cards).

### 1.3 Board layout (dev confidence: MEDIUM-HIGH; Chromium was covered in dev)

Board state: five populated long-form medians (`4h 48m`, `19h 05m`, `2h 30m`,
`23h 59m`, `23h 59m`) plus unknown sixth gate (`25h`, warn).
- 1440×900: ledger fits or scrolls inside its strip; `document.body.scrollWidth
  <= 1440`; no clipped metric values.
- 720×900: ledger scrolls horizontally INSIDE the strip; page body never
  scrolls sideways; last metric reachable by scrolling the strip.
- Repeat both widths in **Firefox** (new coverage).

## 2. Brief conformance

- Every pending Review card shows humane UTC age computed from
  `approvals.requested_at` (cross-check one card against DB elapsed).
- Ledger shows median + count per gate type, last 30 days.
- >24h pending gets visible stale treatment using existing tokens.
- Read-only: the feature adds no write/alert/chart/config/analytics surface —
  network log during board loads shows GETs only (except the pre-existing
  gate-decision POSTs); diff audit confirms no new POST routes.

## 3. Edge cases

- Zero-decided-cohort rendering (prod_signoff before round-trips).
- Unknown gate type from history (qa_legacy_gate).
- Double-click Approve (double-submit) on a seeded gate → exactly one decision;
  second submit hits 409 path, no crash, no duplicate advance.
- Back button after decision → no resubmit corruption (form POST + 303 redirect).
- Refresh mid-flow: board re-renders stably; ages monotonically increase.
- Session expiry / signed-out: all routes redirect to /login (see §4).

## 4. Regressions (from blast-radius: snapshot() and board composition shared)

- Signed out: `/`, `/runs`, `/gates`, `/run/feat-20260831-gate-latency` → 303
  to /login, no data leaked.
- Signed in: all four routes render; `/runs` strips show elapsed (no stale
  treatment there — intentional, coding report note 5); `/gates` shows the real
  pending gate card with `waiting <age>`; evidence link works.
- Full Approve round-trip on `qa-20260901-approve` (current_stage=07-qa-staging
  → advance marks run done; daemon never claims it) — board Done column.
- Full Reject round-trip on `qa-20260901-reject` → run failed, Blocked column.
- After round-trips: prod_signoff ledger becomes n=1 (decision written by the
  existing server-side POST — also proves ledger reads live data).
- Real run's card: still in Review with its `code_complete` gate, ~hours age,
  NOT decided by anything in this charter.

## 5. Exploratory time-box (~15 min)

Follow whatever feels fragile; candidates: rapid navigation between routes,
narrow-width card interactions, ledger under many review cards, login error path,
logout. Recorded like everything else.

## Out of scope / not executed live

- Forcing the ledger's degraded state (`Gate latency unavailable — refresh.`)
  requires injecting a Postgres failure into the LIVE control plane — unit-pinned
  instead (test_gate_latency.py); not worth breaking the shared dev DB.
- Exact-equality 24h check (unit-pinned; live clock can't hold `now == 24h`).

## Sessions & evidence

One browser context per section → one short video each, landing in
`04-qa-dev/media/` via tools/qa-recorder scripted sessions (the MCP here is not
launched by the orchestrator, so scripted recordVideo is the evidence path).

Execution order (round-trips run BEFORE the layout phase so S2 can verify the
empty prod_signoff cohort and S6 can verify it becoming n=1; the layout phase
then adds two `23h 59m` prod rows so all five known gates carry long-form
medians): S1 regressions+auth → S2 ledger semantics → S3 staleness (boundary
rows re-timed just before) → S6 round-trips → prod layout seeds → S4 layout
Chromium → S5 layout Firefox → S7 exploratory.
