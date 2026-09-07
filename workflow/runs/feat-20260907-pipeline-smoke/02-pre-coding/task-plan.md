# Task plan — feat-20260831-gate-latency (attempt 2)

## Structure and package decisions

- Follow `tools/mission-control/app.py:snapshot()` for the grouped read query and `board()`/`build_card()` for Board composition.
- Follow `tools/mission-control/ui.py` atoms and `.statusline`, `.kb`, `.kcard` CSS; implement the approved full-width ledger between statusline and Board columns.
- Reuse `ui.py:ago()` without changing its broad contract.
- No new package: existing `asyncpg`, Python stdlib, and server-rendered HTML suffice.
- No architecture refactor or feature flag: this is the explicitly approved UI and is backward-compatible/read-only.

## Coding principles most at risk

1. **Boring > clever:** one explicit grouped SQL query and small pure format/render helpers, not a generic metrics subsystem.
2. **Errors at the boundary, degrade gracefully:** a latency-query failure must not hide the Board or decision controls.
3. **Tests travel with tasks:** establish Mission Control behavior tests before modifying shared snapshot/render paths.

## Ordered tasks

1. **Specify latency behavior in tests** — ≤0.5 day, no dependency.
   - Create `tools/mission-control/test_gate_latency.py` with stdlib/unit fakes and pure helper assertions.
   - Cover known gate ordering, unknown gate retention, approved+rejected inclusion, pending/expired exclusion, 30-day decision-time boundary, odd/even median intent, zero samples, humane formatting, exact 24h, >24h, and future timestamp clamping.
   - Cover Board ledger labels/counts and Review-card preservation of Approve/Reject/evidence controls.
   - Reviewable state: failing tests define the chosen UI and data contract.

2. **Implement grouped 30-day data assembly** — ≤0.5 day, depends on 1.
   - Modify `snapshot()` to fetch per-gate median seconds/count in one query; replace the currently unused all-time scalar `decided` result or add a clearly named normalized key.
   - Normalize known gates by `GATE_META` order and append unknown gates safely.
   - Add pure formatting/stale helpers; stale is `elapsed_seconds > 24 * 3600`.
   - Run `EXPLAIN (ANALYZE, BUFFERS)` on production-like volume; stop for schema approval if an index is actually required.
   - Reviewable state: data tests pass; no visible UI change.

3. **Implement approved `statusline-ledger`** — ≤0.5 day, depends on 2.
   - Render a persistent full-width section after the existing statusline and before `.kb`.
   - Match stage-1 wording: `GATE LATENCY · LAST 30 DAYS`, `Median time to decision · UTC`, one metric per known gate, median plus `n`/no-decisions copy.
   - Use existing tokens and preserve all five columns; allow horizontal scrolling/wrapping at narrow widths rather than clipping values.
   - Render `—` and `no decisions · n=0`, never `0h`, for empty cohorts.
   - Reviewable state: the selected Board composition is complete.

4. **Add local stale treatment to Review cards** — ≤0.5 day, depends on 2.
   - Continue computing age from `approvals.requested_at` in `build_card()`.
   - For strictly >24h, add explicit `STALE` text/chip and warning treatment using `--warning`, `--warning-soft`, and existing derived borders only.
   - Preserve report-blocked precedence, server-side approval forms, stage rail, cost, and evidence link.
   - Confirm `gate_card()` on `/run/{id}` still displays pending age; do not add rejected run-detail median/context design.
   - Reviewable state: stale and non-stale cards are distinguishable without changing authority.

5. **Failure isolation and route regression** — ≤0.5 day, depends on 3–4.
   - Isolate aggregate-read failure so Board cards remain visible and show `Gate latency unavailable — refresh.` in the ledger region.
   - Test `/`, `/runs`, `/gates`, `/run/{id}`, auth redirects, zero decided approvals, no pending approvals, exactly/just-over 24h, and decision form markup.
   - Confirm query count is constant regardless of cards/gate types.
   - Reviewable state: focused and existing repository tests pass.

6. **Docs and whole-diff self-review** — ≤0.25 day, depends on 5.
   - Update `tools/mission-control/README.md` and `docs/MISSION-CONTROL.md`.
   - Verify desktop and narrow layouts, both current theme modes if supported by the deployed app, and UTC copy.
   - Record deviations immediately in `03-coding/report.md`; provide QA confidence map for median cohort, 24h boundary, and Board layout.
   - Reviewable state: clean code-complete handoff.

## HITL

- **HITL: required — developer plan approval:** approve implementation of the corrected `statusline-ledger` choice and the exact read-only query semantics above.
- No schema approval is required because there is no schema change.
- No package approval is required because there is no new dependency.
- If query-plan evidence shows an index is necessary, stop and request separate schema approval; do not add it under this plan.

## Definition of code-complete

- [ ] Board displays the chosen persistent full-width per-gate 30-day median ledger above all five columns.
- [ ] Every known gate type appears in stable order with median and sample count.
- [ ] Approved and rejected decisions whose `decided_at` is within 30 days count; pending, expired, null-decision, and older rows do not.
- [ ] Zero-sample gates display `— · no decisions · n=0` without errors.
- [ ] Every pending Review card shows age from `approvals.requested_at` in humane UTC units.
- [ ] Cards strictly older than 24h show explicit `STALE` warning treatment; exact boundary behavior is tested.
- [ ] Run detail still shows pending age through existing `gate_card()`; rejected run-detail redesign is absent.
- [ ] `/runs`, `/gates`, auth, evidence links, and server-side Approve/Reject POSTs remain unchanged.
- [ ] Aggregate query count is constant and query plan is acceptable without schema changes.
- [ ] No package, write, alert, client clock, configurable threshold, chart, or analytics event is added.
- [ ] New and existing tests pass; docs and coding report are updated.
