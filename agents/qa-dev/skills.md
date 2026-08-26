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

- **Video records itself.** Your browser (the Playwright MCP) is launched with
  recording on; every session's video lands in `04-qa-dev/media/` on the run folder.
  Close the browser between charter sections — each browser session is one video, and
  short per-section videos are what reviewers actually watch.
- **You never upload.** After your stage passes, the orchestrator uploads this
  attempt's videos to the artifact bucket as `<run-id>--04-qa-dev--session-<n>.webm`
  (n = recording order) under an `attempt-<k>/` prefix, and writes
  `media-manifest.json` beside your report. The stage FAILS if no video from your
  attempt exists — a QA pass without video evidence is a claim.
- Link videos in the report by recording order **with timestamps** ("session 2, 0:25 —
  the failing submit"). When `LANTERN_ARTIFACT_BUCKET` is set in your environment, the
  final URL is deterministic (your attempt number is in the kickoff message):
  `s3://$LANTERN_ARTIFACT_BUCKET/lantern/<run-id>/04-qa-dev/attempt-<k>/<run-id>--04-qa-dev--session-<n>.webm`.
  Never write an S3 URL for a session you did not record — claims are checked.
- Exploratory sessions: same mechanism — drive, narrate in the session log as you go.
- `tools/qa-recorder` scripted specs are for promoting repros into committed
  regression tests (§5), not for in-stage evidence.

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
