# Design system — generation constraints for the ui-ux agent

STATUS: POPULATED — extracted 2026-08-25 from the Paper design file (not yet from
product code; re-extract from the product repo once it is linked in a brief).

Every value below is a literal copied from the source of truth. Agents: treat this
file as **hard constraints** — never introduce a color, font, spacing value, or
component variant that is not listed here; propose additions in your report instead.

## Source of truth

| What | Source | Version |
|------|--------|---------|
| Design tokens (50) | Paper file "Lantern Agent V2" (`01KZVT6JVAN2XTZWRADNVCQYCE`), `get_tokens` | contentHash `288d9538` |
| Patterns & shell | Artboards 01–12b of the same file (reference PNGs below) | 2026-08-25 |
| Extraction date | 2026-08-25 (ui-ux demo session) | — |

## Color tokens

Surface ladder (elevation — canvas up):

| Token | Value | Note (from the file) |
|-------|-------|----------------------|
| `--surface-0` | `#0A0A0C` | Page canvas. Not pure black — pure black kills the elevation ladder. |
| `--surface-1` | `#121216` | Resting cards and panels, ~4% lighter than canvas. |
| `--surface-2` | `#191920` | Raised / focused cards. |
| `--surface-3` | `#22222A` | Overlays, active controls, hover. |
| `--edge` | `#24242C` | Hairline between surfaces. |
| `--edge-top` | `rgb(255 255 255 / 5.5%)` | Top highlight on raised surfaces — light catching an edge. |

Legacy/base set: `--color-bg #050506`, `--color-panel #0E0E12`, `--color-card
#14141A`, `--color-card-hi #1D1D24`, `--color-line #232329`.

Text: `--color-text #E8E8EC` · `--color-text-muted #8E8E98` · `--color-text-dim #6C6C76`.

Accent & semantics (accent is *scarce* — one primary action per screen):

| Token | Value | Use for | Never for |
|-------|-------|---------|-----------|
| `--color-accent` | `#F2C57F` | THE primary action, active tab underline | decoration, body text |
| `--color-accent-soft` | `#2C2113` | accent-tinted fills behind accent text | large areas |
| `--color-on-accent` | `#08080A` | text on accent | — |
| `--color-success` / `-soft` | `#43C67E` / `#12301F` | confirmations, "Yes" chips, saved-state lines | anything non-semantic |
| `--color-warning` / `-soft` | `#E7935A` / `#2E1E16` | degradation, caution | — |
| `--color-danger` | `#E5705F` | destructive/refused states | — |
| `--color-gold-deep` / `--color-gold-light` | `#8C6A2F` / `#C9B183` | brand gold ramp | — |

Data spectrum (ordered quantities ONLY — "never categories, never verdicts"):
`--night-1 #46565F` → `--night-2 #5C6E77` → `--night-3 #7B8A90` → (ash hinge =
`--color-text-muted`) → `--dawn-1 #C77A4E` → `--dawn-2 #D89A5E` → `--dawn-3 #E8B570`
→ `--dawn-4 #F2C77E` → `--dawn-5 #F8D68D` → `--dawn-6 #FCE3A6`.

## Typography

| Token | Value | Role |
|-------|-------|------|
| `--font-display`, `--font-ui` | `Figtree` | headings and all body/UI text |
| `--font-mono` | `JetBrains Mono` | meta ("JOB v7", counters, money, `search.begin` tags) |
| `--font-label` | `ADAM.CG PRO` | caps-only: wordmark, nav tabs, section labels, state words. **Never body text.** |

Scale (use only these steps): `--text-caps 11px` · `--text-xs 13px` · `--text-sm
14px` · `--text-base 15px` · `--text-md 16px` · `--text-lg 20px` · `--text-xl 28px`
· `--text-2xl 40px` · `--text-3xl 56px`. Caps labels get generous letter-spacing
(~0.1em+); numbers that matter are large + right-aligned with a tiny muted caption
under/beside them (e.g. **34** / `weight`).

## Spacing & layout

- Radii: `--radius-sm 6px` · `--radius-md 12px` · `--radius-lg 16px` ·
  `--radius-pill 999px`.
- Desktop frame: 1440×900. **The product shell** (every screen):
  1. Left icon rail ~64px, canvas-black, logo circle top, avatar bottom.
  2. Top nav: caps tabs with full-width underline rails; active tab = accent
     underline + brighter label (IDEAL CANDIDATE · CALIBRATE · STRATEGY · PIPELINE
     · OUTREACH · LAUNCH).
  3. Split body: **left column (~440px) = the conversation** — `LANTERN` speaks,
     `YOU` replies, a saved-state line in success green, free-text input pinned at
     bottom ("Keep teaching it — type, or drop a file…"), caps status footer
     ("— SOURCING IDLE · NOTHING BILLED YET").
  4. **Right column = the working surface** — the artifact being shaped.
- Prefer information on surfaces over boxing everything into cards (file rule);
  cards only where elevation means something (summary, money, candidate rows).

## Component inventory (observed in artboards 04/05)

| Component | Use when | Never for |
|-----------|----------|-----------|
| Numbered row (index, bold title, muted desc, right-aligned weight) | ranked/weighted lists | plain unordered content |
| Summary card (key–value rows, mono values right) | totals, open questions ("not sure yet — left open, not guessed") | general text |
| Money callout (caps title, mono tag right, body, one accent CTA) | first-spend / irreversible moments | routine actions |
| Chips `Yes` / `Maybe` / `No · reason` | judgments | navigation |
| Section header `A · COMPETITOR POACH` (caps + counter right) | grouped queues | — |
| Candidate row (avatar initials, name + meta, one-line evidence, chip right) | people lists | — |

## Copy voice

- Lantern speaks first-person, concrete, calm: "Four traits, weighted. The weights
  decide who gets ranked first — … tell me and I'll move them."
- Buttons are verbs with the consequence attached: "Start calibration — up to $40".
- States admit uncertainty instead of faking data: "not sure yet — left open, not
  guessed"; "3 queued · still sourcing".
- Sentence case everywhere except caps labels. No lorem, ever.

## Reference screens

- `design/references/ideal-candidate.png` — artboard 04: weighted traits, summary
  card, money callout.
- `design/references/calibration.png` — artboard 05: judging queue, chips, lanes.
