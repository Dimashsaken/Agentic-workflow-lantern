# Stage Report: 05-post-coding — feat-20260831-gate-latency

- **Agent/author:** post-coding (Claude Code session on the laptop; no orchestrator —
  the control-plane box and its Postgres were decommissioned 2026-09-07, so this stage
  ran without `append_memory`, without any `pipeline.py` write, and without a database)
- **Date:** 2026-09-07
- **Status:** PASS-WITH-NOTES — conditional: the stage-5 gate ("all `fix-now` findings
  resolved and verified in the diff") is **not yet met**. Two `fix-now` items are open
  (F1, F2), both one-line edits; the status becomes PASS once the developer lands them
  and this role verifies them in the updated diff. No blocking question. No
  backward-compatibility break.

## Summary

The reviewed diff (`git diff 904db65 main`; five product files, the rest run artifacts)
matches the approved `statusline-ledger` plan in both directions, adds no schema, env,
package, event, or write, and **is rollback-safe: reverting the application code alone
restores the previous build — there is no migration to keep applied, and both the
forward and the reverse direction are read-only.** Two `fix-now` findings: the latency
query's `PostgresError` is swallowed with no log line, so a persistent failure leaves no
trace beyond a UI sentence that says "refresh" (F1), and the new `ledger_metrics()`
takes the name of the module's pre-existing per-run cost `ledger` (F2); one
`debt-ticket` (an index for the decided-approvals aggregate, schema-gated, with the
trigger stated) and seven `waived` items with reasons. Next: the developer resolves
F1/F2, this role verifies them in the updated diff, then stage 6 (security).

## Work performed

- Read charter, skills, memory; the run folder end to end (brief, stage 1 report,
  flow-spec, options, jsx, handoff.json, blast-radius, schema-plan, task-plan, stage 2
  report, stage 3 report + `explain-latency.txt`, stage 4 report + bugs + charter,
  gate-decisions); `AGENTS.md`; `docs/MISSION-CONTROL.md` and
  `tools/mission-control/README.md` as they stand; `mockups/README.md` and `tokens.css`.
- Generated the full diff once (`git diff 904db65 main`, 31 files) and worked from it,
  not commit-by-commit. Product files: `tools/mission-control/app.py` (+84/-4),
  `tools/mission-control/ui.py` (+38), `tools/mission-control/test_gate_latency.py`
  (new, 421 lines), `tools/mission-control/README.md` (+12), `docs/MISSION-CONTROL.md`
  (+9/-1). `tools/azure-runner/` and `infra/` are untouched (empty diff).
- Read the surrounding code, not just the hunks: `snapshot()`, `build_card()`,
  `build_strip()`, `board()`, `runs_index()`, `gates()`, `gate_card()`, `decide()`,
  `ui.page()`, the reload script, the `:root` tokens, and the board CSS — to judge
  naming against the exemplar patterns and to trace every consumer of `snapshot()`.
- **Merge integrity.** QA validated `b75a4f2` (the coding-branch tip). `main` is
  `57c9549` (merge of main's D13 chat work into the feature) + `0f210bf` (test-only,
  +5 lines). Proved the feature's `app.py`/`ui.py` hunks are byte-identical before and
  after the merge: `git diff 525a6da b75a4f2` vs `git diff 904db65 main` on those two
  files, hunk headers stripped — `diff` reports no difference. Confirmed the ledger's
  CSS selectors (`.ledger .lhead .lm .lerr`) are unique in the merged `ui.py`.
- Consumer tracing for the changed `snapshot()` return shape across `app.py`,
  `chat.py`, `tools/azure-runner/chat_service.py`, `seed_demo.py`.
- Reviewed the query-plan evidence (`03-coding/explain-latency.txt`) against
  `schema.sql`'s index inventory.
- Ran the test suites (results below), `py_compile` on the three Python files,
  `git diff --check` (clean), and — no `pyflakes`/`flake8`/`ruff` in the venv — an
  AST scan for unused imports and assigned-never-read locals.
- Did not: modify product code, commit, run any `pipeline.py` command, touch the
  local demo Postgres, or read `.env`.

## Findings / results

| ID | Area | Severity | Tag | Evidence |
|----|------|----------|-----|----------|
| F1 | tech-debt: swallowed error | medium | **fix-now** | `tools/mission-control/app.py:289-292` — `except asyncpg.PostgresError: gate_latency = None` with **no log line**. The module's own "degrade, don't die" idiom logs: `_chat_startup` at `app.py:157-160` prints `f"chat startup skipped: {e}"` to stderr. The only surviving signal is the UI copy `Gate latency unavailable — refresh.` (`ui.py:710`), which is the wrong advice when the failure is persistent (permissions change, column rename): an operator seeing that sentence for a week finds nothing in `journalctl`. Suggested one-liner: `except asyncpg.PostgresError as e:` + `print(f"gate latency query failed: {e}", file=sys.stderr)` before `gate_latency = None`. (`sys` is already imported.) Note the pre-existing `runners` catch at `app.py:293-297` is silent too, but that one is a documented, self-resolving condition — a pre-v2 database — not an unexpected failure. |
| F2 | cleanliness: naming drift | low | **fix-now** | `app.py:243 def ledger_metrics(rows)` — "ledger" already means the **per-run cost ledger** in this module: `snapshot()` builds `ledger: dict[str, dict]` at `app.py:316`, returns it as the `"ledger"` key at `:332`, and both consumers read it as `led = snap["ledger"]` (`build_strip` `:368`, `build_card` `:626`); `README.md` calls token spend "the same ledger". In `board()` the two now sit two lines apart: `lat = snap["gate_latency"]` / `ledger_metrics(lat)` (`:761-762`). Every sibling helper in the feature is gate-prefixed (`gate_latency_rows`, `ui.gate_ledger`, existing `gate_card`, `GATE_META`, `GATE_SHORT`). Pure rename, no behavior change: `ledger_metrics` → `gate_latency_metrics`; sites: `app.py:243`, `app.py:762`, `test_gate_latency.py:202, 312, 324`. (`ui.gate_ledger` and the `.ledger` CSS class keep the word — that is the UX option's name and it is prefixed/scoped.) |
| F3 | tech-debt: query ordering | low | waived | `LATENCY_SQL` (`app.py:209-215`) has no `ORDER BY`; `gate_latency_rows()` (`:224-240`) re-orders known gates by `GATE_META` but appends **unknown** gates in result order, which SQL leaves unspecified (`GroupAggregate` happens to sort; a `HashAggregate` plan would not). *Waived because* gate names are a closed vocabulary — the only writer is `pipeline.py:704` inserting from `FEATURE_STAGES` (`pipeline.py:226-232`), which is exactly `GATE_META`'s five — so no unknown gate can exist today, and one unknown gate has no ordering problem. If a second vocabulary ever appears, add `ORDER BY gate` (one token). |
| F4 | tech-debt: index / boundedness | low today | **debt-ticket DT-1** | `approvals` has one index, partial on pending rows (`tools/azure-runner/schema.sql:61`); `LATENCY_SQL`'s predicate is `status IN (...) AND decided_at IS NOT NULL AND decided_at >= now() - 30d` → **seq scan of the whole table**. Output is bounded (≤ distinct gates); the scan is not. `explain-latency.txt`: 0.183 ms at 10 rows; 11.5 ms, 261 shared-hit buffers, quicksort 522 kB at 20 000 rows. It runs on every `/` **and** `/runs` load (F5), and the board reloads itself every 30 s per open tab (`ui.py:625-629`). The plan explicitly deferred any index to a separate schema gate; the evidence supports deferring. Ticket below states the trigger. |
| F5 | tech-debt: unused work on `/runs` | low | waived | `snapshot()` (`app.py:274-334`) fetches `LATENCY_SQL` for `/runs` too (`runs_index` `:838`), where `build_strip()` (`:365-447`) never reads `gate_latency`. *Waived because* it is the blast-radius design (one shared batch boundary), it has the same shape as the unused `decided` fetchrow it replaced (`904db65` `app.py:234-239`, `:280` — also computed for both pages, read by neither), and the cost is sub-frame at production-like volume. Revisit under DT-1, where "fetch it only in `board()`" is the no-schema first step. |
| F6 | config: hardcoded threshold | info | waived | `STALE_SECONDS = 24 * 3600` (`app.py:217`). Brief non-goal: "no configurable thresholds (24h is hardcoded; changing it is a code edit)"; documented at `README.md:20-21` (`app.py:STALE_SECONDS`). |
| F7 | cleanliness: duplicated comparison | low | waived | Strict `> STALE_SECONDS` appears twice: `is_stale()` (`app.py:220-221`, a pending approval's age) and inline at `app.py:255` (a cohort **median**). The constant is the single source of truth; folding the second into `is_stale()` would label a median "stale", which it is not. Leave as is. |
| F8 | cleanliness: annotation drift | info | waived | `gate_latency_rows(rows)` (`app.py:224`) is the one new helper without a parameter annotation (siblings: `rows: list[dict]`, `elapsed_seconds: float`). It accepts asyncpg `Record`s or dicts; the docstring says what it takes. Cosmetic. |
| F9 | docs precision | info | waived | `README.md:27` "stdlib only, no DB" — the tests import `app.py`, so they need the azure-runner venv (asyncpg, FastAPI, markdown, dotenv), which `README.md:29-33` states immediately below. The intended meaning is "no test-only packages". Cosmetic. |
| F10 | process: reviewed ≠ QA'd commit | info | waived | QA validated `b75a4f2`; `main` merged D13 (`57c9549`) afterwards. *Verified* the feature hunks are byte-identical across the merge (method under Work performed) and the ledger CSS selectors are unique post-merge; unit tests run against the merged code (35/35). Residual: the ledger and the chat nav were never rendered together in a browser — a stage-7 check, not a stage-5 block. |

Outside the diff (not this run's findings, recorded so the next maintainer has them):
`app.py:26 import html` is unused since 2026-08-25 (`H` comes from `ui`), and the
loop variable `i` at `app.py:1058` (`run_page`) is never read, since 2026-08-27.

### Plan vs. diff

**Planned and present** (task-plan tasks → commits):

1. Tests first → `a0d9fda`, `test_gate_latency.py`. Covers everything task 1 lists:
   known-gate order, unknown-gate retention, approved+rejected inclusion and
   pending/expired exclusion (asserted on `LATENCY_SQL`'s clauses), the 30-day
   boundary on `decided_at` (asserts `requested_at >=` is absent), median intent
   (`percentile_cont`), zero samples, humane formatting, exact 24h, >24h, future
   clamp, ledger labels/counts, Review-card control preservation.
2. Grouped assembly → `49e9c4d`: `LATENCY_SQL`, `gate_latency_rows`, `ledger_metrics`,
   `is_stale`; the unused scalar `decided` replaced by a clearly named `gate_latency`
   key (the plan offered exactly this choice). `EXPLAIN (ANALYZE, BUFFERS)` at
   production-like volume done on the box and recorded; no index required, so no
   schema gate was triggered — consistent with the plan's stop condition.
3. Ledger → `fa693e8`, `622eba3`: `ui.gate_ledger()` + `.ledger` CSS, wired between
   `statusline` and `.kb` (`app.py:780`; ordering asserted by
   `test_board_renders_ledger_between_statusline_and_columns`). Wording matches the
   task plan verbatim. Existing tokens only (`--surface-1 --edge --text-xl --text-caps
   --font-label --font-mono --warning --text-dim --text-muted`, all present in
   `ui.py:24-41`). `overflow-x:auto` for narrow widths.
4. Stale cards → `ab05cf3`: `waited` computed once from `requested_at`; `STALE` warn
   chip + `.kcard.stale` (border `--warning`, warning-colored age); report-blocked
   chip keeps precedence (`app.py:648-651`); forms, evidence link, rail, cost footer
   untouched; `gate_card()` untouched (`app.py:480-565` identical to `904db65`).
5. Failure isolation + route regression: degrade path + `Gate latency unavailable —
   refresh.`; routes `/`, `/runs`, `/gates`, `/run/{id}` with auth redirects; zero
   decided / zero pending; exact / just-over 24h; decision-form markup; **constant
   query count** (`test_board_query_count_is_constant`). The `/gates` redirect
   assertion was the one gap at `b75a4f2` and was added post-QA in `0f210bf`
   (test-only).
6. Docs → `717dad6`: `README.md`, `docs/MISSION-CONTROL.md`. Coding report records
   the one deviation-class note (dark-only app, so "both theme modes" is vacuous).

**Definition of code-complete**, checked item by item against the diff: all eleven
boxes hold. The two that depend on evidence rather than code — "query plan acceptable
without schema changes" and "existing tests pass" — hold on `explain-latency.txt` and
on this stage's test run respectively.

**Planned but missing:** none.

**Present but not in the task plan** (all traced to the approved stage-1 design or to
process, none to invention):

- The degraded copy carries a second sentence, `Pending gates are still shown.` — the
  stage-1 flow-spec's Error state verbatim; the task plan quoted only the first half.
- Medians over 24h render in `--warning` (`app.py:255`, `ui.py:95`) — in the chosen
  jsx (`text-warning` on the 4d plan sign-off metric); the brief's "trending toward
  the one-day threshold" signal.
- Header copy follows the task plan (`GATE LATENCY · LAST 30 DAYS` / `Median time to
  decision · UTC`) rather than the jsx mock (`… · 30 DAYS` / `Median decision time`);
  the approved plan is the authority. Metric labels reuse `GATE_SHORT` (lower-case
  `plan sign-off`) rather than the mock's capitalized labels — consistent with every
  other surface in the app.
- `workflow/RUNBOARD.md` (+1/-1) — rendered by the orchestrator (`76df1ae`), not
  product code; see landmine below.
- `0f210bf` — a test-only commit after QA; product code is unchanged since `b75a4f2`.

**Stage-1 states deliberately not carried into the plan and correctly absent:** the
`Loading gate latency…` state (inapplicable — the page is server-rendered) and flow
step 5's run-detail median/threshold repeat (the rejected attempt-1 composition;
`test_run_detail_still_shows_pending_age_no_median_context` pins its absence).

### Backward compatibility

**Rollback safety — yes.** No schema change (`git diff 904db65 main -- tools/azure-runner
infra` is empty; the columns read — `gate`, `status`, `requested_at`, `decided_at` —
exist since the v1 schema, `schema.sql:47-60`). Deploy = ship the code and restart the
`lantern-mission-control` unit only (the orchestrator daemon has no diff). Rollback =
redeploy the previous commit and restart the same unit; nothing to un-migrate, no
in-flight rows to reason about (pending rows never enter the median; a decision is
visible on the next reload in either build).

- **`snapshot()` return shape** — `decided` removed, `gate_latency` added. Every
  consumer traced: `board()` (`app.py:732, 761`), `runs_index()` → `build_strip()`
  (`:838`, `:365-447`), `build_card()` (`:616-723`) — they read `runs latest_by_dir
  ledger pend online`; only `board()` reads `gate_latency`. Non-web consumers: none.
  `chat.py` imports nothing from `app.py` (`chat.py:9`); `chat_service.pipeline_snapshot`
  is its own DB-direct function (`chat_service.py:335-375`); `seed_demo.py` writes
  fixtures and never calls `snapshot()` (it does not reference `decided` or
  `gate_latency`). At `904db65` the `decided` key was assembled (`:234-239`, `:280`)
  and read by nothing. Removing it breaks no one.
- **Route contracts** — `GET /`, `/runs`, `/gates`, `/run/{id}` are server-rendered
  HTML with no JSON consumer; the only client is a browser. Anonymous → `303 /login`
  on all four (tests). `POST /gate/{id}/{decision}` (`app.py:1148-1171`) and
  `gate_card()` are byte-identical to `904db65`. QA's live approve/reject round trips
  and the 409 double-submit probe confirm the write path is unchanged.
- **Env / config** — no new environment reads in the added lines; no feature flag; no
  new package (`asyncpg` + stdlib). An old `.env` boots the new code (the tests boot
  `app.py` with only `LANTERN_WEB_USERS`). The systemd unit is untouched.
- **Events / analytics** — none emitted (brief non-goal; QA's read-only audit saw only
  `/login`, `/logout`, and the pre-existing gate POSTs).
- **Database features** — `percentile_cont` and `FILTER` were already in use before
  this feature; nothing new is demanded of Postgres.
- **The old browser tab** — CSS ships inline in every page; a tab holding last
  month's page gets the new CSS on its next 30 s reload. Nothing cached to invalidate.
- **Unknown gates at 0 / 1 / many** — 0: the five known rows; 1: appended after the
  known five with its raw name escaped (`ui.py:715`); many: appended in query order
  (F3), the strip scrolls internally (QA measured six metrics fitting exactly at 1440).
  Bounded by the closed gate vocabulary.
- **Merge integrity** — see F10: hunks byte-identical across the D13 merge; selectors
  unique; 35/35 on the merged code.

### Debt tickets

No tracker is wired (Linear chosen, not integrated); this entry is the ticket.

**DT-1 — Partial index for the decided-approvals latency aggregate (schema-gated)**

- **Where:** `tools/azure-runner/schema.sql` (`approvals`; only `idx_approvals_pending`
  at `:61`); `tools/mission-control/app.py:209-215` (`LATENCY_SQL`) and `:289-292`
  (its call site inside `snapshot()`).
- **Why:** the predicate on `decided_at` / `status` has no index, so every `/` and
  `/runs` render seq-scans the whole `approvals` table, multiplied by open tabs every
  30 s. Measured 11.5 ms / 261 buffers at 20 000 rows (`03-coding/explain-latency.txt`).
  Growth is ~5 approvals per run, so 20 000 rows ≈ 4 000 runs — years away at current
  volume — but the cost sits on the board's hottest path and grows linearly.
- **Suggested fix, in order:** (1) no schema: fetch `LATENCY_SQL` only in `board()`
  (or a `with_latency` flag on `snapshot()`), removing it from `/runs` (closes F5);
  (2) schema-gated (HITL gate #2): `CREATE INDEX CONCURRENTLY idx_approvals_decided ON
  approvals (decided_at) WHERE status IN ('approved','rejected');` then re-run
  `EXPLAIN (ANALYZE, BUFFERS)` and confirm an index/bitmap scan replaces the seq scan.
- **Trigger:** `approvals` beyond ~100 000 rows, or board p95 render above 100 ms, or a
  second aggregate over decided rows.
- **Size:** S (half a day including the schema gate).

### Test results

- `cd tools/mission-control && ../azure-runner/.venv/Scripts/python.exe -m unittest
  test_gate_latency -v` → **`Ran 35 tests in 0.015s — OK`**, zero failures, zero
  errors, zero skips. By class: `TestLatencySQL` 1, `TestGateLatencyRows` 4,
  `TestLedgerMetrics` 5, `TestStale` 5, `TestReviewCards` 5, `TestGateCardPreserved`
  1, `TestLedgerRender` 3, `TestRoutes` 11.
- `cd tools/azure-runner && .venv/Scripts/python.exe test_product_access.py` →
  **`all product-access properties hold`**, exit 0; 25 checks `ok` (confinement 5,
  read-only 4, git allowlist 6, no credential leak 5, brief parsing 5).
- `test_chat_service.py` — **not run:** its header says `needs LANTERN_DATABASE_URL +
  init-db` and it writes rows; the authoritative database is gone and the local demo
  Postgres is off-limits for this stage. `test_verification.py` — not run, same
  reason (it passed on the box on 2026-09-01 per the stage-3 report). Neither module
  is touched by this diff.
- `py_compile` on `app.py`, `ui.py`, `test_gate_latency.py`: OK. `git diff --check
  904db65 main -- tools docs`: clean. AST unused-name scan: nothing introduced by the
  diff (the two pre-existing hits are listed under Findings).

## Artifacts

- `report.md` — this report (the stage's only artifact; no videos at this stage).

## Handoff notes for the next stage

- **For the developer (before stage 6):** resolve F1 and F2 (one line each, plus the
  three test references for F2), re-run `python -m unittest test_gate_latency` (expect
  35 OK), then ask this role to verify the updated diff; the report's Status flips to
  PASS on verification.
- **For security (stage 6):** the feature is read-only over `approvals`; the only new
  SQL is the parameterless `LATENCY_SQL` — no user input reaches it. Every rendered
  string, including a gate name straight from the database, passes through `H()`
  (`ui.py:714-715`, chips in `app.py`). No new route, no auth change, no new package.
- **For staging QA (stage 7):** render the board with the chat nav present at 1440
  and 720 — the ledger and D13's surface were merged after QA and have never been
  seen together (F10). The degraded-ledger state has unit coverage only; forcing it
  needs a Postgres fault, which stage 4 declined to inject into a live control plane.
- **Landmines:** the control plane is gone, so `workflow/RUNBOARD.md` (still showing
  `03-coding / code_complete`) and `gate-decisions.md` will not re-render until a new
  box exists; this run's `code_complete` gate was still pending when the box died.
  Nothing in this repo needs the box's `.env` fixes from QA's E-2 — they were box-only.

## Open questions (BLOCKED status must have exactly one)

None.

## Memory candidates

No `append_memory` tool in this harness (no orchestrator); recorded here for the
postmortem trail and for whoever consolidates `agents/post-coding/memory.md`:

- 2026-09-07: When the commit QA validated and the branch under review differ by a
  merge of main (here D13 landed between stages 4 and 5), do not take "clean merge"
  on faith — diff the feature's hunks before and after the merge with hunk headers
  stripped (`git diff <base> <qa-tip>` vs `git diff <main-base> main`, minus `@@` and
  `index` lines). A byte-identical result proves the review target is what QA saw and
  shrinks the residual to "the two features were never rendered together", which is a
  stage-7 note rather than a stage-5 block.
- 2026-09-07: A "degrade gracefully" `except` that renders a UI sentence still needs a
  log line — the UI copy ("refresh") tells the operator the wrong thing when the
  failure is persistent, and the module usually already has the idiom to copy (here
  `print(..., file=sys.stderr)` in the startup hook). Check every new catch for both a
  UI path and a log path, and distinguish it from a documented self-resolving catch
  (a table that only a pre-upgrade database lacks), which may stay silent.
- 2026-09-07: A read-only feature on a shared assembly boundary (`snapshot()`) is
  rollback-safe by construction — spend the compat pass on the return-shape change
  instead: list every consumer of the removed/renamed key including the non-web ones
  (chat tools, seed scripts, CLI), and confirm the removed key had zero readers at the
  base commit, because that is the only way a "read-only" change breaks a sibling.
- 2026-09-07: Check new identifiers against existing dict keys and CSS vocabulary in
  the same module, not only against existing function names — a UX option named
  "ledger" collided with a pre-existing cost `ledger` key and the collision propagated
  into a function name two lines from the other one.
