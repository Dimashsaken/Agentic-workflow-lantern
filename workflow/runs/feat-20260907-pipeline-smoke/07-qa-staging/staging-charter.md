# Staging charter — feat-20260907-pipeline-smoke

Target: `http://172.17.0.1:8081`; test login supplied by the stage kickoff. Deployed source: `main` at `8745ece`, per `gate-decisions.md`.

## Re-run from stage 4

1. Authenticate with the provisioned staging account; confirm signed-out protected-route redirect.
2. Verify the Board ledger heading/subtitle, five known gate types, sample counts, humane UTC durations, and explicit zero-decision states.
3. Verify a >24h pending gate has `STALE`, warning treatment, unchanged decision controls/evidence, and the same age on `/gates` and run detail.
4. Verify Board, `/runs`, `/gates`, and run detail render; inspect browser console.
5. At 720px verify no body-level horizontal overflow and that the ledger scrolls internally to the final metric.

## Staging-only

1. Confirm staging authentication and database-backed realistic run/gate data.
2. Confirm the newly decided staging-deploy cohort appears in the aggregate ledger.
3. Confirm staging is serving the reviewed feature behavior after the human deploy.

## Explicitly excluded

- Gate approval/rejection and double-submit: only real gates were available and the brief forbids deciding them.
- Aggregate-query failure injection and new database boundary seeds: no staging fault-injection/seeding interface; unit-pinned upstream.
- Third-party delivery checks: the feature adds no integration.
- PostHog event checks/browser distribution: the brief explicitly specifies no analytics events; no event checklist entries exist. Cross-engine execution was unavailable in this browser harness, so the primary flow was exercised in its available recorded engine and mobile viewport.
