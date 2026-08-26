# Options — feat-20260825-candidate-compare

Three structural options for the "pick who advances" moment, converged in Paper
(file **Agent sandbox — ui-ux runs**, page `feat-20260825-candidate-compare`:
<https://app.paper.design/file/01M0W444P0FVBY0PKRDYAPYDWH/2-0>), grounded in
`design/design-system.md` (tokens contentHash `288d9538`, extracted from the
product design file the same day). Divergence explored six axes
(`divergence/*.html`); judge scores below.

**IA decision common to all three:** no new top-level tab. Compare is a *stage of
CALIBRATE* (kicker "CALIBRATION · DECIDE") — the existing six-tab nav is untouched.

## Judge scores (vs brief: confident decision, weights do the arguing, ≤3 finalists, states)

| Axis | Score | Kept | One-line reason |
|------|-------|------|-----------------|
| verdict | 8.5 | ✔ | Decision-first is exactly Lantern's voice; recommendation never hidden — and never forced |
| overlay | 8 | ✔ | Trait-first puts the weights (the product's promise) in charge of the page |
| duel | 7.5 | ✔ | The most *legible* two-person comparison; bench keeps a third close |
| columns | 6 | ✘ | Candidate-first buries the weights; cross-candidate reading is horizontal-eye-travel per trait |
| matrix | 6.5 | ✘ | Weight-scaled cells are clever but cramp evidence to labels |
| dossier | 4 | ✘ | Sequential viewing recreates the memory burden the brief exists to remove |

## Option A — `verdict` (recommended)

Lantern's read is the hero: weighted totals (76 · 74), a two-sentence argument,
one accent CTA ("Advance Hannah — draft outreach"), and explicit escape hatches
("Rebalance weights", "Advance Wylin instead"). The full four-trait evidence table
sits directly below, so the recommendation is auditable in one glance.
**Pros:** fastest to a confident decision; the "why" line requirement fits
naturally; conversation panel argues, surface proves. **Cons:** if Lantern's read
is wrong often, the anchoring could annoy — mitigated by the always-visible table
and rebalance path.

## Option B — `overlay`

Traits are the rows, heaviest first; both candidates compared *inside* each row;
decision bar with totals pinned at the bottom. **Pros:** the weights physically
structure the page; scales cleanly to 3 finalists; best for a careful re-read.
**Cons:** slowest to a decision; the verdict lives at the bottom.

## Option C — `duel`

Full-width head-to-head: finalists flank a central trait spine, winner-dot per
side, "WHAT FLIPS IT" sensitivity strip (what weight change reverses the result),
bench chip for the third candidate. Drops the conversation panel — the one
structural departure from the shell. **Pros:** most memorable read; the flip strip
is honest about how close it is. **Cons:** two-at-a-time by design; third finalist
is second-class; loses the persistent Lantern panel.

## States (all options — full detail in flow-spec.md)

Fewer than 2 finalists → screen doesn't exist; CALIBRATE shows "1 yes — keep
judging or advance directly". Evidence still sourcing → row shows "still
sourcing — n queued" in place of the thin cell, never fake evidence. Stale weights
(ICP edited after judging) → warning banner + one-click "re-run comparison".

## Recommendation

**verdict** — it is the only option whose *structure* enacts the product's core
promise ("the weights decide, Lantern argues, you stay in charge").
**Strongest argument against it:** it optimizes for agreeing with Lantern; if
early users mostly overrule, `overlay` is the safer default and `verdict` becomes
a summary card on top of it. That hybrid is a cheap later merge.
