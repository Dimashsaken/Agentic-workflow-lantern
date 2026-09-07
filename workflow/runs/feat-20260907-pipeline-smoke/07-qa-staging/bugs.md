# Bugs — feat-20260907-pipeline-smoke (07-qa-staging)

No product bugs found.

## Environment/noise notes

- `/favicon.ico` returned 404 in both recorded sessions. This is pre-existing, cosmetic, and unrelated to the gate-latency feature.
- Cross-engine launch controls and PostHog project access were not exposed by this session. The brief specifies no analytics events, so there were no event arrivals to verify.
