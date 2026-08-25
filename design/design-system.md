# Design system — generation constraints for the ui-ux agent

STATUS: UNPOPULATED TEMPLATE — extract real values from the product repo before
relying on this file (instructions: `design/README.md`). While this line is present,
the ui-ux agent must state in `options.md` that it generated without the constraint
layer and must ground itself in product screenshots instead.

Every value below must be a literal copied from the product repo, with its source
recorded. Agents: treat this file as **hard constraints** — never introduce a color,
font, spacing value, or component variant that is not listed here; propose additions
in your report instead.

## Source of truth

| What | Product repo path | Commit |
|------|-------------------|--------|
| Tailwind / token config | TODO | — |
| CSS custom properties | TODO | — |
| Shared components | TODO | — |
| Extraction date | — | — |

## Color tokens

| Token | Value | Use for | Never for |
|-------|-------|---------|-----------|
| TODO `--color-primary` | `#______` | primary actions | body text |

## Typography

- Font stack: TODO (copy the literal `font-family` value)
- Scale (name → size/line-height/weight): TODO — list every step the product
  actually uses; do not invent intermediate sizes.

## Spacing & layout

- Spacing scale: TODO (e.g. 4/8/12/16/24/32 — the literal scale, nothing off-scale)
- Grid / max content width / breakpoints: TODO
- Radii & elevation: TODO (each radius and shadow the product uses, by name)

## Component inventory

| Component | Use when | Never for | Source file |
|-----------|----------|-----------|-------------|
| TODO Button (primary/secondary/danger) | | | |
| TODO Modal | | | |
| TODO Table | | | |

## Patterns

- Forms: TODO (label position, validation display, button placement)
- Empty states: TODO (illustration? copy tone? primary action?)
- Loading: TODO (skeleton vs spinner, where each is used)
- Errors: TODO (inline vs toast vs page-level, and when)

## Copy voice

- TODO: 3–5 rules with a good/bad example each (e.g. sentence case everywhere;
  verbs on buttons — "Export 12 items", never "OK").

## Reference screens

- TODO: `design/references/<screen>.png` — 2–4 annotated screenshots of
  representative product screens the agent should visually match.
