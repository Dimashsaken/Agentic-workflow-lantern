# Flow spec — role health

1. From Live, the hirer opens Role health (`role_health_opened`).
2. Lantern leads with one state: healthy, stalling, stalled, or just launched.
3. The right surface shows volume trend, source performance, and weighted-trait match quality.
4. For stalling/stalled, Lantern explains why and offers exactly one suggested action.
5. Taking it records `health_action_taken` with the suggested-fix identifier and confirms the action inline.

## Exact state copy
- Healthy: “The role is healthy. Candidate flow and match quality are holding.”
- Stalling: “The role is healthy overall. Outreach is slowing first.” Action: “Refresh outreach audience”.
- Stalled: “No new candidates arrived this week.” Action: “Restart distribution”.
- Just launched: “Not enough signal yet — this does not mean the role is failing.”
- Loading: “Checking the role’s latest signals…”
- Error: “I couldn’t refresh role health. Your last complete check is still shown.” Action: “Try again”.
- No permission: “You can view the role, but only role owners can change distribution.”

Desktop-first 1440×900. Mobile collapses narration above evidence and preserves the action before charts.