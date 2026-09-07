# Blast radius — feat-20260831-gate-latency (attempt 2)

## Approved scope

The corrected authoritative choice is `statusline-ledger`: a persistent full-width 30-day median ledger above the five Board columns, with pending age and stale treatment local to Review cards. The rejected attempt-1 run-detail composition must not be implemented. Run detail remains in scope only for the brief's existing requirement that pending gates show age there; `gate_card()` already does so, so no run-detail redesign is planned.

## Flow and consumers

`tools/mission-control/app.py:snapshot()` is the shared batch data boundary for Board and Runs. Board rendering flows through `board()` → `build_card()`; run detail and Gates use `gate_card()`. `tools/mission-control/ui.py` owns the humane-duration formatter, page shell, and CSS. The feature adds one grouped read query and Board presentation while leaving authenticated approval POSTs unchanged.

| Path | Action | Why | Risk |
|---|---|---|---|
| `tools/mission-control/app.py` | modify | Replace/extend the existing all-time ungrouped `decided` aggregate with per-gate 30-day medians/counts; render the approved Board ledger; classify Review cards stale at >24h. | high |
| `tools/mission-control/ui.py` | modify | Add full-width ledger and stale-card CSS/render atom using existing tokens; reuse `ago()` unchanged. | medium |
| `tools/azure-runner/schema.sql` | read only | Confirms all source fields and current pending-only index; no migration. | medium |
| `tools/mission-control/mockups/tokens.css` | read only | Source of warning/stale and ordered-quantity tokens; no new colors. | low |
| `tools/mission-control/mockups/README.md` | read only | Existing Board density, truthfulness, and token conventions. | low |
| `tools/mission-control/README.md` | modify | Document the ledger, 30-day window, and >24h stale state. | low |
| `docs/MISSION-CONTROL.md` | modify | Align Board behavior documentation with the chosen UI. | low |
| `tools/mission-control/test_gate_latency.py` | create | Add focused behavioral coverage because Mission Control has no tracked tests. | medium |

## Consumer tracing

- `snapshot()` consumers are `board()` and `runs_index()`. The latency result must be additive or replace the currently unused `decided` key without changing Runs rendering.
- `build_card()` is consumed only by `board()`. It already derives Review age from `approvals.requested_at`; this feature adds explicit stale copy/style without changing action forms.
- `gate_card()` is consumed by `/gates` and `/run/{id}` and already renders `waiting {age}` from `requested_at`. Leave it structurally unchanged except optional shared stale helper/class if required; do not implement rejected run-detail median context.
- `ago()` has many Mission Control consumers. Keep its global output contract unchanged.
- Approval creation and decisions are written by orchestration/CLI/web code outside this read path. No writer, auth, event, cron, analytics, or pipeline state consumer changes.

## Coverage and risks

- No Mission Control tests are tracked; write tests first.
- Single riskiest element: the existing `snapshot()` aggregate is shared by Board and Runs, so changing its query/result shape can break `/runs` while the new Board appears correct.
- Use one grouped query, never one query per gate or card. Include statuses `approved` and `rejected`, require non-null `decided_at`, and filter decisions by `decided_at >= now() - interval '30 days'`.
- Render all five known `GATE_META` types in stable order, including zero-sample rows as `—` and `no decisions · n=0`; unknown historical gate types may append after known types rather than disappear.
- Stale means strictly older than 24h. Existing duration formatting clamps future timestamps to zero; test this behavior.
- No security pre-review: auth, writes, payments, deletion, and authorization boundaries are untouched.
