# Stage Report: 01-ui-ux — feat-20260825-candidate-compare

- **Agent/author:** ui-ux (Claude session driving Paper MCP directly — demo of the
  planned loop, `docs/plans/ui-ux-agent-paper.md`)
- **Date:** 2026-08-25
- **Status:** PASS-WITH-NOTES

## Summary

Ran the full stage-1 loop for candidate compare: 6 divergence skeletons → judge
pass kept 3 → converged in Paper (isolated sandbox file, product tokens recreated)
→ 2 critique iterations per option → exported the presentation set. Recommendation:
**verdict** (decision-first). Next: Justin picks at ux_signoff.

## Work performed

- Extracted the real design constraint layer first: 50 tokens (`contentHash
  288d9538`) + shell patterns from the product design file, read-only →
  `design/design-system.md` now POPULATED; reference screenshots in
  `design/references/`.
- Divergence: `divergence/{columns,duel,overlay,verdict,dossier,matrix}.html`,
  scored against the brief (table in options.md).
- Convergence: Paper file **Agent sandbox — ui-ux runs** (new file — zero writes
  to "Lantern Agent V2"), page `feat-20260825-candidate-compare`, one artboard per
  surviving option, all styling via the recreated tokens.
- Critique loop per `design/critique-checklist.md`, layout pass then style pass,
  2 rounds each: r1 → r2 fixed ghost-button wrap (verdict), stacked weight
  numerals + sourcing footer (overlay), row breathing + "WHAT FLIPS IT" strip
  replacing a 335px dead zone (duel).

## Findings / results

1. Paper MCP quirk (operational, high value): **nodes created before the file has
   ever been opened in the renderer never mount** — screenshots/exports return
   empty / "No DOM element". Fix: open the file in the app first (one human click;
   `open_file` alone does not switch the visible tab), then create. Dead nodes must
   be recreated, not styled into life.
2. Paper tool surface is now 35 tools incl. **design tokens (shipped)** — research
   doc said roadmap. `create_file` gives real per-run isolation; `fileId` on every
   write call makes cross-file writes structurally impossible.
3. `move_nodes` is tree-order only; artboard canvas position is set at creation
   (auto-placement works once the file is mounted).
4. Design: all three options keep the six-tab IA (compare = a CALIBRATE stage).

## Artifacts

- `options.md` — 3 options + judge table + recommendation
- `verdict@2x.png` / `overlay@2x.png` / `duel@2x.png` — presentation set (also on
  the Paper canvas: <https://app.paper.design/file/01M0W444P0FVBY0PKRDYAPYDWH/2-0>)
- `jsx/{verdict,overlay,duel}.jsx` — structural source of truth (not production code)
- `flow-spec.md` — screens, transitions, all states, events
- `handoff.json` — machine-readable gate payload (metrics included)
- `design-system.snapshot.md` — the constraint-layer version used
- `divergence/` — all six skeletons (rejected axes documented)

## Handoff notes for the next stage

Pre-coding should read `flow-spec.md` first; the "why" line on every decision is a
hard requirement (it feeds calibration). Evidence cells must never show invented
data — "still sourcing" is a first-class state. Walkthrough video deliberately
deferred until an option is picked (record only the winner).

## Open questions (BLOCKED status must have exactly one)

None — but the brief is demo-authored: Justin should confirm scope at the gate.

## Memory candidates

- Paper: create content only after the file has been opened once in the renderer;
  `open_file` does not switch the visible tab — ask the human for one click.
- Compare-type screens: judge divergence axes on "does the structure enact the
  product's core promise" — it cleanly separated 3 keepers from 3 rejects.
