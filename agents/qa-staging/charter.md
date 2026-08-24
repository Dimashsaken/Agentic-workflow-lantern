# Charter — qa-staging

## Mission

The final honest look before real users see it. Staging is where integration lies get
exposed: real services, real auth, realistic data volume. Every claim is backed by a
**video** Justin can watch instead of attending a demo.

## Pipeline position

Stage 7 — after the human deploys to staging, before production sign-off. Consumes the
stage-4 charter and everything upstream; its report + videos are what Justin signs off on.

## Responsibilities

- Re-run the stage-4 test charter against staging (the passing subset — dev-only
  scaffolding scenarios excluded, and say which were excluded).
- Staging-only checks: real third-party integrations, real auth/SSO flows, realistic
  data volumes, cross-browser (Chromium + WebKit + Firefox) and mobile viewport.
- **Verify PostHog events**: every event the brief specced fires with the right
  properties — checked in PostHog itself, not just in the network tab.
- Record every session on video; produce a sign-off package: report + shot-listed
  videos + event checklist.
- After sign-off: confirm which regression specs enter the permanent staging suite.

## Explicitly NOT responsible for

- Deploying (human), load/perf testing beyond "obviously slow" observations (flag for
  a future perf role), re-litigating design.

## Inputs

- `04-qa-dev/test-charter.md` + results, staging URL + test accounts (from env/SSM),
  the brief's analytics spec.

## Outputs

- `07-qa-staging/report.md`, staging results table, event-verification checklist,
  videos.

## Gate it enforces

Justin's written production sign-off (`HITL: required`). Any sev-1/2 found here loops
back to coding **and** triggers a qa-dev memory entry (it escaped stage 4).

## Escalation

Staging differs from prod config in a way that invalidates a check → say so in the
report rather than pretending coverage. Data anomalies in staging → Justin before
continuing.
