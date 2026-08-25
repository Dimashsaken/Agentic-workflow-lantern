# The design constraint layer

Paper has no shipped component/token system yet (roadmap — see
`docs/research/design-agents.md`), and agents have no taste by default: without hard
constraints the ui-ux agent produces generic output, the #1 reported failure mode of
design agents. This directory is the constraint layer the pipeline supplies itself.

Two files, both loaded by the ui-ux agent **before any generation**
(`agents/ui-ux/skills.md` §1):

| File | What it is | Who maintains it |
|------|-----------|------------------|
| `design-system.md` | The product's actual tokens, type scale, components, and patterns — extracted from the product repo, not invented | Regenerated when the product's tokens change; hand-curated notes survive regeneration |
| `critique-checklist.md` | The two-pass (layout, then style) checklist the agent runs against every rendered screenshot | Curated by hand; grows from `agents/ui-ux/memory.md` findings |

## Populating `design-system.md` (the code-to-design flow)

Until it is populated, the file is a marked template and the agent must say so in
`options.md` and ground itself in product screenshots instead. To populate:

1. In the product repo, locate the real sources: `tailwind.config.*`, CSS custom
   properties, the theme/token module, and the shared component directory.
2. Extract literal values (hex, px/rem, font stacks) — never paraphrase. Every value
   in `design-system.md` must be traceable to a file in the product repo; record the
   source path + commit next to each section.
3. Inventory the shared components with a one-line "use when / never for" per
   component.
4. Add 2–4 annotated screenshots of representative product screens under
   `design/references/` (small PNGs are fine in git; they are documentation, not run
   artifacts).
5. Flip the `STATUS` line at the top of `design-system.md` and record the extraction
   date + product-repo commit.

Acceptance (plan Phase 2): two options generated with and without this file must be
visibly distinguishable in fidelity to the product's look.
