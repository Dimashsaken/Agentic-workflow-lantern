# Task plan — feat-20260831-gate-latency

## Structure and package decisions

- Keep data/query and route composition in `tools/mission-control/app.py`, following existing `snapshot()` aggregation and server-rendered route patterns.
- Keep visual atoms and duration formatting in `tools/mission-control/ui.py`, following `chip()`, `ago()`, and the existing `.kcard`/`.gcard` CSS.
- Preserve server-side UTC rendering and the existing 30-second whole-page refresh; no client clock.
- No new package. `asyncpg`, Python stdlib, and current HTML helpers are sufficient.
- No refactor prerequisite beyond extracting small pure helpers needed for tests.

## Coding principles most at risk

1. **Boring > clever:** keep one explicit aggregate query and plain render helpers; avoid a generic analytics abstraction.
2. **Errors at the boundary, graceful user behavior:** latency summary failure must not hide pending gates or decision controls.
3. **Tests with each task:** Mission Control has no existing test suite, so establish behavioral tests before changing shared renderers.

## Ordered tasks

1. **Add gate-latency behavior tests** — ≤0.5 day, no dependency.
   - Create `tools/mission-control/test_gate_latency.py` using stdlib fakes/records and pure helper assertions.
   - Cover 30-day filtering/query shape, odd/even median intent, approved+rejected inclusion, pending exclusion, empty gate types, exact 24h boundary, >24h stale, humane age, and HTML escaping.
   - Cover Board review card, run-detail decision block, and preservation of Approve/Reject forms.
   - Reviewable result: failing tests specify the contract without product behavior changes.

2. **Add one read-only latency data path** — ≤0.5 day, depends on 1.
   - Extend `snapshot()` with one grouped last-30-days query and normalize results by `GATE_META` order.
   - Add pure helpers for stale classification (`age > 24h`, not `>=`) and safe median/count display.
   - Keep known gate types with `n=0`; tolerate an unknown gate by its raw name.
   - Verify the query plan on production-like data; no index/schema change in this run.
   - Reviewable result: tests pass for data semantics; existing board output unchanged.

3. **Implement the minimal Board companion** — ≤0.5 day, depends on 2.
   - Render a compact per-gate 30-day median/count summary without adopting the unapproved full-width ledger layout.
   - In `build_card()`, use approval `requested_at` for Review age and apply explicit `STALE` warning treatment only when age is greater than 24h.
   - Preserve all existing card controls, stage rail, cost, and evidence link.
   - Add only existing-token CSS in `ui.py`; verify narrow overflow behavior.
   - Reviewable result: the brief's board-glance requirement is met with the approved option still governing detailed composition.

4. **Implement approved run-detail context** — ≤0.5 day, depends on 2.
   - On `/run/{id}`, enrich the pending gate decision block with local age, `24h threshold`, that gate type's 30-day median, sample count, evidence/report, and existing action buttons.
   - Keep `/gates` behavior stable; pass context explicitly rather than coupling to globals.
   - Render no-data as `—`, `no decisions`, `n=0`; never `0h`.
   - Reviewable result: approved `run-detail-context` is represented without changing decision authority.

5. **Failure isolation and regression pass** — ≤0.5 day, depends on 3–4.
   - If aggregate retrieval fails, render existing pending cards/decision block and a non-blocking `Gate latency unavailable — refresh.` message.
   - Exercise zero approvals, only pending approvals, rejected decisions, a future/skewed timestamp clamped for display, and a gate exactly/just beyond 24h.
   - Verify `/`, `/gates`, `/run/{id}`, `/runs`, auth redirect, and POST action markup.
   - Reviewable result: focused tests green and no regression to gate integrity.

6. **Document and self-review** — ≤0.25 day, depends on 5.
   - Update `tools/mission-control/README.md` and `docs/MISSION-CONTROL.md`.
   - Run repository tests plus the new Mission Control tests; inspect the full diff in one sitting.
   - Capture QA handoff risks: timezone/boundary, median semantics, shared gate-card rendering.
   - Reviewable result: code-complete report and clean branch.

## HITL

- **HITL: required — developer plan approval:** approve this reconciliation: implement the selected `run-detail-context` plus only the minimal Board age/stale/median companion required by the brief, not the unselected full-width ledger.
- No schema approval is required because there is no schema change.
- No package approval is required because there is no new dependency.
- If implementation reveals that acceptable query performance requires an index, stop and return with a separate schema proposal; do not add it under this approval.

## Definition of code-complete

- [ ] Every pending Board Review card uses `approvals.requested_at` and shows humane UTC age.
- [ ] Ages strictly greater than 24h have explicit `STALE` text and existing warning-token treatment; exactly 24h is covered by test.
- [ ] Board shows median decision duration and count per known gate type for the last 30 days.
- [ ] Approved and rejected decisions count; pending and older decisions do not.
- [ ] Zero-sample gate types render `— · no decisions · n=0` without errors.
- [ ] Run detail combines age, threshold, same-gate median/count, evidence, and unchanged decision controls.
- [ ] `/gates` and `/runs` regressions are tested; auth and server-side POST authority are unchanged.
- [ ] Query count is constant with respect to number of runs/gates; no N+1.
- [ ] No schema migration, package, client-side clock, write, alert, or analytics event is added.
- [ ] Existing and new tests pass; docs and stage-3 report identify any deviations.
