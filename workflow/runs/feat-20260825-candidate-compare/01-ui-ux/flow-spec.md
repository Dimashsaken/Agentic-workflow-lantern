# Flow spec — candidate compare (recommended option: verdict)

## Entry points

1. CALIBRATE, when ≥2 candidates are marked **Yes** → a "Compare n finalists"
   action appears beside the judging queue.
2. Lantern proactive line in the conversation panel ("Two look final — want me to
   put them side by side?") → same screen.

## Screens & transitions

### 1. Compare (kicker `CALIBRATION · DECIDE`)

- Left panel: Lantern's argued recommendation (2–4 sentences, names the deciding
  trait + where it would change its mind); user replies refocus the evidence
  (e.g. "show velocity" → that row highlights/expands, green "Noted" state line).
- Right surface: weighted totals (mono, accent on leader) + argument + CTA row +
  four-trait evidence table (winner cell: green ● + full text; other: dim ◐).
- Copy rules: totals always "n / 100"; CTA always names the person and the
  consequence ("Advance Hannah — draft outreach").

### 2. Decision moment (any advance/hold action)

- Inline one-line "why" input (required, placeholder "One line on why — it
  teaches the next round"). Submit → success state line in panel
  ("Saved — Hannah advances; your why feeds calibration") → OUTREACH opens with
  the draft pre-addressed to the advanced candidate.
- Hold → candidate stays; row gets a "held — <why>" chip back in CALIBRATE.

### 3. Rebalance path

"Rebalance weights" → IDEAL CANDIDATE with a return breadcrumb; on return the
comparison re-runs, totals animate to new values, Lantern comments on the flip
("That rebalance flips it — Wylin 79 · 71").

## Non-happy states

| State | Behaviour |
|-------|-----------|
| <2 finalists | No compare screen. CALIBRATE offers "advance directly" instead. |
| 3 finalists | Verdict card shows all three totals; table gains a third column; CTA names the leader only. |
| Evidence still sourcing | Cell shows "still sourcing — n queued", never invented evidence; totals show "provisional" mono tag. |
| Weights changed after judging | Amber banner: "Weights changed since judging — re-run comparison" (one click). Totals hidden until re-run. |
| Tie | No accent CTA. Lantern names the tiebreak question instead ("Same total — the difference is all in trait 2. Read that row."). Both advance buttons ghost-styled. |
| Error loading evidence | Row-level retry, rest of the table intact. |

## Events (PostHog)

`compare_opened` {finalists, role_id} · `compare_decision` {advanced_id, matched_recommendation, seconds_from_open, why_length} · `compare_rebalanced` {flipped}.
