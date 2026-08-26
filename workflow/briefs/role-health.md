# Feature Brief: Role health — is this pipeline alive?

- **Run ID:** feat-20260825-role-health
- **Author:** ui-ux demo session (acting brief — needs Justin's confirmation)
- **Assigned developer:** —
- **Date:** 2026-08-25
- **Target release:** —

## Problem

After launch ("11 · Live"), a role's pipeline runs across several channels
(distribution boards, outreach, inbound) but the hirer has no single answer to
"is this role healthy, and if not, what do I do?" They notice stalls late — a
board quota quietly exhausted, outreach replies drying up, calibration queue
starving — and each discovery today requires spelunking through separate surfaces.

## Desired outcome

A hirer glances at one screen and knows: volume trend, where candidates come from,
quality against the weighted traits, and the single most useful next action when
something stalls. Lantern narrates the "why" and proposes the fix. PostHog:
`role_health_opened`, `health_action_taken` (which suggested fix), time-to-detect
stalls (should drop).

## Scope

- One per-role screen: pipeline volume over time, per-source performance
  (boards / outreach / inbound), trait-match quality distribution, stall detection
  with a concrete suggested action.
- Lantern's narration in the left panel — diagnosis first, numbers second.
- States: healthy, stalling (one channel degraded), stalled (no flow), just-launched
  (not enough data yet — must not look like failure).

## Non-goals

- No cross-role dashboard (single role only in v1).
- No new data collection — composes what launch/distribution/calibration already
  track. No configurable charts or date pickers in v1.

## Constraints

Product shell + dark theme tokens as with every screen; desktop-first at 1440;
numbers must be legible at a glance (this screen is checked between meetings).

## Existing context

Paper file "Lantern Agent V2": artboards 10 (Launch refused — stale preview),
11 (Live — after launch), 12/12a/12b (Distribution). This screen is where "Live"
grows a memory and an opinion.

## Human-in-the-loop preferences

Standard gates. Justin picks the option at ux_signoff.
