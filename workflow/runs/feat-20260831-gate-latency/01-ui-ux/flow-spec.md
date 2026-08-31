# Flow spec — gate latency

1. Operator opens Board.
2. Every pending Review card shows humane UTC age.
3. At >24h, the card shows explicit `STALE` copy plus warning treatment.
4. Operator reads the 30-day median and sample count for the gate type.
5. Operator opens the run; run detail repeats local age, threshold, median, count, evidence, and the existing decision action.

## States
- No decided approvals: `—` and `no decisions · n=0`; never `0h`.
- No pending gates: existing `No runs need review.` state.
- Loading: keep existing board/evidence visible; `Loading gate latency…`.
- Error: `Gate latency unavailable — refresh. Pending gates are still shown.`
- No permission: existing authentication redirect; no data leaks.
- Slow network: server-rendered ages remain stable until existing reload.
- Narrow/mobile: columns may horizontally scroll; age and `STALE` stay adjacent to the gate identity.

## Rules
- Age = UTC now − `requested_at`.
- Median = `decided_at - requested_at`, decisions from last 30 days, grouped by gate.
- Stale means older than 24h; warning treatment is display-only.
- No writes, alerts, configurable thresholds, per-approver data, or charts.
