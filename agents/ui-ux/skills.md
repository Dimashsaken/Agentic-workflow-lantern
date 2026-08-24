# Skills — ui-ux

## 1. Session start

Read charter → this file → memory → run folder (brief first). Confirm run ID. If the
brief lacks a success metric or target user, mark BLOCKED with that one question.

## 2. Flow mapping

- Walk the brief as the user: entry point → steps → success. Write it as a numbered
  narrative before any visuals.
- For every step list the non-happy states: empty, loading, error, no-permission,
  slow-network, mobile. A flow without these is not done.
- Check memory for patterns that failed before in similar flows.

## 3. Producing options

- 2–3 options that differ in *structure* (e.g. wizard vs. single-page vs. inline edit),
  not in colour. For each: a mermaid flow diagram or ASCII wireframe, step count for
  the primary task, pros/cons, and which existing product patterns it reuses.
- End `options.md` with a recommendation and the single strongest argument against it.

## 4. Prototype + walkthrough video

- Build the chosen option as a minimal static app in `01-ui-ux/prototype/` (plain
  HTML/JS or the product's stack if trivial). Fake all data. Realistic copy, not lorem.
- Record: serve the prototype, then drive the primary flow + one error state with
  `tools/qa-recorder` (video on). Slow, deliberate actions — the video is for humans.
- Upload video, link in report with a shot list ("0:00 entry, 0:20 validation error…").

## 5. Session end

Report per template. Memory: append any pattern decision (chosen or rejected + why) that
future flows should know about.
