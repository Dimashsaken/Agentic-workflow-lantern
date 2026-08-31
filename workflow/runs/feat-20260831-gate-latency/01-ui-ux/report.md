# Stage Report: 01-ui-ux.diverge — feat-20260831-gate-latency

- **Agent/author:** ui-ux
- **Date:** 2026-08-31
- **Status:** PASS

## Summary

Generated eight grayscale low-fi skeletons against the current Mission Control v2 ticket board and judged them on task success, primary-task steps, state coverage, and product-pattern fit. Three structurally distinct survivors advance to Paper convergence: **statusline-ledger**, **review-lane-summary**, and **run-detail-context**. The design workstation should preserve the current one-topbar/five-column Mission Control shell rather than the unrelated hiring-product shell described in the generic design constraint file.

## Work performed

- Read the brief, populated design constraint layer, critique checklist, runboard, product conventions, and current run history.
- Opened product sources `tools/mission-control/app.py`, `tools/mission-control/ui.py`, `tools/mission-control/mockups/tokens.css`, `tools/mission-control/mockups/README.md`, `tools/mission-control/README.md`, `tools/mission-control/seed_demo.py`, `tools/azure-runner/schema.sql`, `docs/MISSION-CONTROL.md`, and `docs/plans/symphony-alignment.md`.
- Traced the existing board card, pending-gate card, run-detail gate card, humane `ago()` formatter, and approvals queries.
- Mapped the flow and non-happy states before sketching.
- Built eight standalone low-fi HTML skeletons under `divergence/` using realistic gate copy and the current Mission Control information architecture.

### Flow narrative

1. An operator opens **Board** and sees pending-gate ages on every Review card without opening anything.
2. The same glance reveals which pending gate crossed 24h through a visible, text-backed stale treatment.
3. The operator reads the 30-day median and sample count for each gate type, including explicit no-data states.
4. The operator opens a run and sees the pending gate's age and stale state again beside its evidence and decision controls.
5. The operator decides through the existing server-side gate action; latency presentation remains read-only.

### Required states

- **Empty:** zero decided approvals renders each gate type as `— · no decisions`; zero pending gates leaves the board's existing honest Review empty state.
- **Loading:** server-rendered page retains the existing document-load behavior; no optimistic placeholder or client clock is introduced.
- **Error:** if latency aggregation is unavailable, preserve pending gate age/card actions and show `Gate latency unavailable — refresh`; never hide a gate.
- **No permission:** existing authentication redirects to login; no latency data is served unauthenticated.
- **Slow network:** ages are computed at render time in UTC and remain stable until the existing 30-second reload; no client clock dependency.
- **Mobile/narrow:** summary becomes a horizontal/stacked list and the existing board scrolls; ages and `STALE` text remain adjacent to the gate name.

## Findings / results

### Judge rubric

Each dimension is scored 1–5; total is /20. `Primary steps` counts actions needed to identify a stale gate and understand its gate-type median from the Board.

| Rank | Axis | Task success | Primary steps | State coverage | Product fit | Total | Verdict |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | **statusline-ledger** | 5 | 5 (0 clicks) | 5 | 5 | **20** | KEEP |
| 2 | **review-lane-summary** | 5 | 5 (0 clicks) | 4 | 5 | **19** | KEEP |
| 3 | **run-detail-context** | 4 | 3 (1 click for context) | 5 | 5 | **17** | KEEP — distinct detail-first axis |
| 4 | gate-type-strips | 5 | 5 (0 clicks) | 4 | 3 | 17 | CUT — structurally duplicates statusline-ledger with heavier tiles |
| 5 | stale-first-review | 5 | 5 (0 clicks) | 3 | 4 | 17 | CUT — urgent count is strong, but per-type summary becomes fragmented across cards |
| 6 | compact-table | 4 | 4 (0 clicks) | 5 | 3 | 16 | CUT — complete but too tall and table-heavy for an at-a-glance board summary |
| 7 | threshold-bands | 4 | 5 (0 clicks) | 3 | 3 | 15 | CUT — visually implies historical distribution/trend beyond the brief's single median |
| 8 | disclosure-drawer | 3 | 3 (1 disclosure action when collapsed) | 4 | 4 | 14 | CUT — hides the staffing signal and adds interaction to the primary glance task |

### Survivor rationale

1. **statusline-ledger (recommended for convergence):** a persistent board-wide readout makes all gate types comparable in zero clicks while stale cards retain local age and threshold meaning. Strongest argument against it: on a five-column board, a full-width ledger consumes vertical space even when samples are empty.
2. **review-lane-summary:** puts the metric exactly where the operator acts, minimizing eye travel and preserving the existing board header. Strongest argument against it: the already narrow Review lane may become disproportionately tall and dense.
3. **run-detail-context:** makes age, threshold, median, and evidence one coherent decision block and best satisfies “wherever pending gates render” on run detail. Strongest argument against it: it cannot alone satisfy the board-glance success metric, so convergence must pair it with a minimal board summary treatment.

### Design constraint note

`design/design-system.md` is populated, but its mandatory 64px icon rail/conversation-column shell describes the hiring product and conflicts with the product actually opened for this run. Mission Control v2 deliberately uses one slim top bar and a five-column ticket board (`tools/mission-control/ui.py`; commit `9601065`). Convergence should use the Mission Control tokens and current shell as the run-specific source of truth, while introducing no new colors, packages, or schema.

### Critique iterations

Not applicable in this divergence-only execution. Screenshot-based layout/style critique belongs to the Paper convergence phase; no critique iterations are claimed here.

## Artifacts

- `divergence/statusline-ledger.html` — full-width per-gate-type median readout plus local stale cards.
- `divergence/review-lane-summary.html` — compact median summary embedded in the Review lane.
- `divergence/run-detail-context.html` — detail-first pending gate context with age, median, sample, and threshold.
- `divergence/gate-type-strips.html` — full-width gate-type tiles; cut as a heavier duplicate.
- `divergence/stale-first-review.html` — stale count and per-card context; cut for fragmented summary.
- `divergence/compact-table.html` — tabular summary; cut for excess height and dashboard weight.
- `divergence/threshold-bands.html` — threshold visualization; cut for implying unsupported trend/distribution.
- `divergence/disclosure-drawer.html` — collapsible summary; cut because it hides the primary signal.

## Handoff notes for the next stage

- Build the three survivors side by side in Paper, grounded in the current Mission Control top bar, statusline, five ticket columns, `.kcard`, `.gcard`, and `.scard` patterns from `tools/mission-control/ui.py`.
- Treat stale as semantic warning with explicit `STALE` copy; never rely on color alone. The 24h decision is a gate choice, so the converged options should visibly compare card treatment and summary placement.
- Preserve sample count next to every median and render `— / no decisions` when count is zero.
- Show both Board and run-detail pending-gate frames for the recommended package; the brief explicitly requires age wherever pending gates render.
- Keep approval controls and server-side behavior unchanged; this feature is display-only.

## Open questions (BLOCKED status must have exactly one)

None.

## Memory candidates

- 2026-08-31 (feat-20260831-gate-latency): For operational latency, judge whether a structure exposes **age + threshold + cohort median + sample count in one glance**; threshold-only treatments create urgency without revealing whether the bottleneck is systemic, while medians without local age hide which gate needs action.
