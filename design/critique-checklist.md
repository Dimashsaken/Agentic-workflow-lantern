# Critique checklist — two separated passes over every rendered screenshot

Run against each option's `get_screenshot` output during the convergence loop
(`agents/ui-ux/skills.md` §3). The passes are **separate on purpose** (METAL finding,
`docs/research/design-agents.md`): critiquing layout and style together makes the
model fix neither well. Do the layout pass, apply its fixes, re-screenshot, then do
the style pass. ≤3 iterations per option; if an item still fails after 3, note it in
`options.md` rather than looping.

## Pass 1 — layout (structure, before any styling talk)

- **One focal point.** What should the user see first — is it actually the largest /
  highest-contrast element? If two things compete, demote one.
- **Hierarchy matches the flow.** Primary action visually dominant, exactly one per
  screen; secondary actions visibly subordinate; destructive actions separated.
- **Spacing rhythm.** All gaps on the product's spacing scale; related elements
  closer than unrelated ones (proximity = grouping); no accidental near-alignments.
- **Alignment.** Everything sits on a shared edge or grid line; ragged edges only by
  deliberate choice.
- **Scan path.** Reading order (top-left → bottom-right in LTR) matches task order;
  labels precede their controls; nothing important below the fold on a 1366×768 view.
- **States exist.** Empty, loading, error, and no-permission are designed on the
  canvas, not implied. A flow showing only the happy path fails this pass.
- **Density.** Nothing crammed (touch targets ≥ 40px, text blocks ≤ ~70ch); nothing
  wastefully sparse that forces scrolling past emptiness.

## Pass 2 — style (only after layout passes)

- **Tokens only.** Every color, font size, radius, and shadow appears in
  `design/design-system.md`. Anything off-token is a defect, even if it looks good.
- **Contrast.** Body text ≥ 4.5:1 against its background, large text ≥ 3:1; disabled
  states visibly disabled but still legible.
- **Type discipline.** ≤ 2 families, ≤ 4 sizes per screen, weights from the scale;
  no faux hierarchy via ad-hoc bolding.
- **Color meaning.** Semantic colors (success/warn/danger) used only for their
  meaning; the primary color is not decorating non-interactive elements.
- **Consistency with the product.** Side-by-side with a reference screen
  (`design/references/`), a teammate would say "same product". Component variants
  match the inventory — no invented button styles.
- **Copy.** Realistic data and product-voice copy, never lorem; button labels are
  verbs; error messages say what happened *and* what to do next.

## Recording the result

Per iteration, note in the working log (ends up in `report.md`): pass run, items
failed, fix applied. The iteration counts per option go in `handoff.json` metrics —
they are a Phase 4 quality signal, not bureaucracy.
