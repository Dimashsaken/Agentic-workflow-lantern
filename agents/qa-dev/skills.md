# Skills — qa-dev

## 1. Session start

Standard reads. From the coding report extract: deviations, deferred tasks, confidence
map. These are your primary targets. Check memory for bug patterns in adjacent features.

## 2. Writing the test charter

Sections, in priority order:
1. **Confidence-map probes** — one scenario per "least confident" area.
2. **Brief conformance** — every promise in the brief becomes a checkable scenario.
3. **Edge cases** — empty/max inputs, unicode + emoji, double-click/double-submit,
   back button, refresh mid-flow, expired session, slow network (throttle), mobile
   viewport, concurrent edits.
4. **Regression suspects** — from the blast-radius table: features sharing touched code.
5. **Exploratory time-box** — at least one free session; follow what feels fragile.

## 3. Executing with video

- Everything runs through `tools/qa-recorder` (see its README): Playwright with
  `recordVideo` on, trace on. One browser context per charter section keeps videos short
  and named per scenario.
- Exploratory sessions: drive interactively (headed or via the harness), keep video on,
  narrate in the session log file as you go.
- Video naming: `<run-id>--04-qa-dev--<scenario>.webm`; upload; link with timestamps.

## 4. Filing bugs

Per bug in `bugs.md`: ID (`QA-1…`), severity, one-line title, exact repro steps,
expected vs. actual, video + timestamp, first-seen commit if determinable. A bug
without deterministic repro gets logged as `flaky` with occurrence notes — never
silently dropped.

## 5. Re-testing and regression seeds

- After a fix: re-run the exact repro + the surrounding charter section. Record round 2
  in the same files under `## Round 2`.
- Promote sev-1/2 repros into committed Playwright specs so they run forever.

## 6. Session end

Report per template: pass/fail per charter section, open-bug table, videos. Memory:
append every bug *class* that the charter design missed (the goal is a charter that
would have caught it next time).
