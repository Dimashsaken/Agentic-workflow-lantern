# Feature Brief: Candidate compare — pick who advances

- **Run ID:** feat-20260825-candidate-compare
- **Author:** ui-ux demo session (acting brief — needs Justin's confirmation)
- **Assigned developer:** —
- **Date:** 2026-08-25
- **Target release:** —

## Problem

Calibration ends with several "Yes" candidates per role, but Lantern V2 has no
moment where the hirer *decides between them*. Today the comparison happens in the
user's head (or a spreadsheet): they re-open profiles one by one and try to remember
how each maps to the four weighted traits they defined. The weights — the product's
core promise — go unused at the exact moment they matter most.

## Desired outcome

A hirer with 2–3 finalists reaches a confident advance/hold decision in one sitting,
inside Lantern, with the weighted traits doing the arguing. Business: decisions per
role speed up and outreach starts sooner. PostHog: `compare_opened`,
`compare_decision` (with time-from-open), share of decisions matching Lantern's
recommendation.

## Scope

- Compare 2–3 calibrated candidates against the role's weighted traits, with the
  evidence snippets calibration already collected.
- Lantern's own recommendation, argued in its voice (left panel), never hidden.
- One decision action per candidate: advance (→ outreach draft) or hold, with a
  required one-line "why" that feeds calibration.
- Empty/loading/error states: fewer than 2 finalists, evidence still sourcing,
  stale weights (ICP changed since judging).

## Non-goals

- No new scoring model — uses the existing per-trait judgments and weights as-is.
- No bulk compare (>3), no PDF export, no sharing/collaboration in v1.
- Rejection outreach flows stay in OUTREACH.

## Constraints

Must live in the product shell (left rail + conversation panel + working surface,
top tab rails); dark theme tokens from the design file; desktop-first at 1440.

## Existing context

Paper file "Lantern Agent V2": artboards 04 (Ideal candidate — weighted traits),
05 (Calibration — judging live candidates), 08 (Outreach draft). This feature sits
between 05 and 08 in the flow.

## Human-in-the-loop preferences

Standard gates. Justin picks the option at ux_signoff.
