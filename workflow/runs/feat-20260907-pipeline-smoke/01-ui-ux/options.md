# Gate latency — converged options

Paper: https://app.paper.design/file/01M0W444P0FVBY0PKRDYAPYDWH/8-0

## statusline-ledger — recommended
- **Screens:** Board.
- **Axis:** persistent full-width median ledger above the five ticket columns; stale age remains local to Review cards.
- **Trade-offs:** zero-click comparison across every gate type and strongest product fit; uses 110px of vertical space even when some samples are empty.
- **Judge score:** 20/20.

## review-lane-summary
- **Screens:** Board.
- **Axis:** place the 30-day median summary inside the Review lane where decisions happen.
- **Trade-offs:** least eye travel and no global board chrome; makes the narrow Review lane denser than its peers.
- **Judge score:** 19/20.

## run-detail-context
- **Screens:** Run detail.
- **Axis:** combine this gate's age, threshold, gate-type median, sample count, evidence, and action into one decision block.
- **Trade-offs:** best decision context and state coverage; requires opening a run and cannot alone satisfy the board-glance goal.
- **Judge score:** 17/20.

## Recommendation
Choose **statusline-ledger**. It exposes age + threshold + median + sample count in zero clicks while preserving Mission Control's five-column board.

Strongest argument against it: a global ledger spends vertical space on gate types with no decisions.

## Divergence record
Eight axes were generated. Cut: gate-type-strips (heavier duplicate), stale-first-review (fragmented summary), compact-table (too tall), threshold-bands (implies unsupported trend/distribution), disclosure-drawer (hides the signal).
