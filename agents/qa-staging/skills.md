# Skills — qa-staging

## 1. Session start

Standard reads. Diff the stage-4 charter against what's meaningful on staging; write
the staging charter as: re-run list + staging-only list + explicitly-excluded list.

## 2. Re-run and staging-only execution

- All browser work through `tools/qa-recorder`, video on, one context per scenario
  group. Staging base URL and credentials from environment only.
- Cross-browser: primary flow on all three engines; full charter on the product's
  majority browser (check PostHog for the real distribution).
- Integrations: exercise the real path (emails actually delivered? webhooks actually
  received? files actually stored?) — check the receiving side, not just the 200.

## 3. PostHog event verification

- From the brief, table every specced event: name, trigger, required properties.
- Trigger each on staging, then confirm in PostHog (staging project) the event arrived
  with correct properties and person association. Screenshot each confirmation.
- Also check for *unexpected* events (noise from debug code) in the staging stream
  during your sessions — those are findings for post-coding's memory too.

## 4. Sign-off package

- Report per template with per-scenario pass/fail on staging, the event checklist, and
  videos with shot lists. Lead the summary with the recommendation: ready / not ready,
  and the top residual risk.
- Keep the package self-sufficient: Justin should need nothing but this report and
  30 minutes.

## 5. Session end

Any bug found here that stage 4 could have caught → coordinate the qa-dev memory entry
(that's the pipeline learning, not blame). Append own memory: staging-specific traps
(config drift, data-volume effects, integration quirks).
