# Test charter — feat-20260907-pipeline-smoke (04-qa-dev, attempt 2)

Target: `http://172.17.0.1:8080`, credentials supplied in the stage kickoff (`qa-dev` / `none`). Product: Mission Control gate-latency feature on `main` at `2df71ec`.

Hard rule: do not decide any real run gate. This attempt has no database seeding interface, so decision round-trips are excluded rather than performed on live data.

## 1. Confidence-map probes

1. **Authentication preflight / attempt-1 blocker retest** — sign in with the exact provisioned credentials and prove the Board is reachable.
2. **Median presentation** — verify `GATE LATENCY · LAST 30 DAYS`, UTC subtitle, known gate metrics, sample counts, humane durations, and explicit no-decision rendering where present.
3. **24h staleness** — verify real pending cards older than 24h show age, `STALE`, warning treatment, and unchanged evidence/decision controls.
4. **Layout** — at 1440px verify no page overflow; at 720px verify the ledger remains reachable through internal scrolling and cards/controls remain usable.

## 2. Brief conformance

- Pending gates show humane UTC age on Board, `/gates`, and run detail.
- Board ledger shows median decision latency and sample count per known gate type.
- A gate older than 24h has visible stale treatment.
- Approve/Reject controls and evidence links remain present.
- Board remains usable when a gate cohort has no decisions.

## 3. Edge cases

- Signed-out direct access redirects to login.
- Wrong-password error does not disclose protected content.
- Refresh and Back retain a usable authenticated flow.
- Mobile viewport has no body-level horizontal overflow.
- Double-submit is not executed because only real gates are available and must not be changed.

## 4. Regression suspects

- `/`, `/runs`, `/gates`, and `/run/feat-20260907-pipeline-smoke` render after login.
- Shared `snapshot()` change does not break `/runs`.
- Browser console remains free of unexpected errors.

## 5. Exploratory time-box

Navigate Board → Gates → Runs → smoke-run detail; refresh, Back, and inspect mobile navigation/card controls. Record every session and stop on any environment blocker.
