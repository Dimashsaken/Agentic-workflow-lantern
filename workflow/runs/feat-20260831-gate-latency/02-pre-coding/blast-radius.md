# Blast radius — feat-20260831-gate-latency

## Scope reconciliation

The approved `run-detail-context` option is authoritative for the decision block, but `01-ui-ux/options.md` explicitly says it cannot alone satisfy the brief's board-glance outcome. Implement the approved run-detail treatment and the smallest required board companion: pending-gate age on Review cards, an explicit stale state after 24h, and a compact per-gate median/count summary. Do not substitute the unapproved full-width `statusline-ledger` composition.

## Flow and consumers

`tools/mission-control/app.py:snapshot()` is the shared data boundary for Board and Runs. Board rendering flows through `board()` → `build_card()`; run-detail and Gates render pending approvals through `gate_card()`. `tools/mission-control/ui.py` owns the existing humane-duration formatter and all CSS. Approval decisions remain the existing authenticated server-side POST path.

| Path | Action | Why | Risk |
|---|---|---|---|
| `tools/mission-control/app.py` | modify | Add grouped 30-day decision-latency query/data shape; classify pending age; render compact Board summary, Review-card stale state, and approved run-detail context. Preserve `/gates` reuse and POST decisions. | high |
| `tools/mission-control/ui.py` | modify | Add small render helpers/CSS for summary, stale card, and decision context using existing tokens; reuse `ago()`. | medium |
| `tools/azure-runner/schema.sql` | read only | Confirms `approvals.requested_at`, `decided_at`, `status`, and `gate`; no migration. Existing pending index does not support the bounded decided-history aggregate. | medium |
| `tools/mission-control/mockups/tokens.css` | read only | Token source for warning/stale treatment; no new colors. | low |
| `tools/mission-control/mockups/README.md` | read only | Existing board rationale and truthful empty-state conventions. | low |
| `tools/mission-control/README.md` | modify | Document the Board latency readout and 24h stale semantics. | low |
| `docs/MISSION-CONTROL.md` | modify | Keep product documentation aligned with Board/run-detail behavior and read-only source. | low |
| `tools/mission-control/test_gate_latency.py` | create | Focused unit/render/query-contract tests because Mission Control currently has no tests. | medium |

## Consumer tracing

- `snapshot()` consumers: `board()` and `runs_index()`. Additive snapshot keys must not alter Runs behavior.
- `build_card()` consumer: `board()` only. Its returned card HTML must retain existing action forms and evidence link.
- `gate_card()` consumers: `/gates` and `/run/{run_id}`. Gate-latency context must be explicitly enabled for run detail (or safely useful in both places); do not accidentally remove Inbox evidence/actions.
- `ago()` has broad Mission Control use. Do not change its output contract globally; add a gate-specific wrapper only if the approved compact copy requires it.
- Approval fields are also written by CLI/web orchestration code, but this feature only reads them. No auth, decision, event, or pipeline-state mutation is planned.

## Coverage and risk notes

- There are no tracked Mission Control tests; tests precede rendering changes.
- Single riskiest element: `gate_card()` is shared by run detail and the gate inbox, so implementing approved context there can unintentionally change both verification surfaces or the decision controls.
- SQL should compute one grouped aggregate, not one query per gate/card. Use UTC database `now()` and include only rows decided within the last 30 days.
- Median definition must be fixed in tests: `percentile_cont(0.5)` over epoch seconds, grouped by `gate`; approved and rejected decisions both count because both are decisions.
- Security pre-review is not required: no auth, payments, deletion, new writes, or authorization boundary changes.
