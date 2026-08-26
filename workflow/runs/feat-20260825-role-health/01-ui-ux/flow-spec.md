# Flow spec — role health (recommended option: diagnosis-brief)

## Entry points

1. LAUNCH tab once a role is live (this screen replaces the static "Live" panel).
2. Lantern-initiated: a health check that changes state posts a line into the
   conversation column of whatever screen the user is on ("Board flow just dropped 70%
   — want to look?").
3. Weekly digest link (Monday), deep-linking to this screen for the named role.

## Screens and transitions

### 1. Role health (kicker `LIVE · ROLE HEALTH`)

- **Left column** — Lantern states the condition in plain language, answers follow-ups,
  and keeps two standing blocks: `IF YOU DO NOTHING` (a concrete projection, not a
  warning) and `WHAT I'M WATCHING` (the signals that would change the verdict).
- **Right column** — verdict headline; warning card (cause, one primary action with
  price and expected effect, one dismissal, and the "nothing is billed until you press
  it" reassurance); vitals row; source ledger; what-changed timeline; trait-match
  distribution.
- Copy rules: the headline states a condition, never a metric. Actions name their price
  and their effect ("Renew LinkedIn slot — $99/mo", "resumes ~12 candidates/week").
  Never say "error" for a business condition — a quota is exhausted, not broken.

### 2. Taking the action

Primary action → confirmation inline in the conversation column ("Slot renewed —
I'll tell you when the first candidates land"), the warning card collapses to a resolved
state with a timestamp, and the what-changed timeline gains an entry. No modal.

### 3. Dismissal

"Ignore this week" → card collapses to a single muted line ("boards quota — ignored
until Monday"), and the projection in `IF YOU DO NOTHING` stays visible so the choice
remains legible.

## Non-happy states

| State | Behaviour |
|-------|-----------|
| Healthy | Headline states it plainly ("Healthy — nothing needs you"); no warning card at all; vitals + ledger + trait match remain. The screen must be worth opening when nothing is wrong. |
| Stalling (shown) | One warning card, one action. |
| Stalled (no flow at all) | Headline states it; card explains which channels stopped and in what order; action is the highest-leverage restart, not a list. |
| Just launched (<20 candidates) | No verdict. Lantern says it is still learning and shows what it has, with the date it expects to have an opinion. Must never render as "unhealthy". |
| Stale data | Amber inline note with the last successful check time; numbers shown but marked provisional; retry action. |
| One source fails to load | That ledger row shows a retry; every other row and the verdict still render. |
| No permission | The role is listed but its numbers are withheld with a request-access action; Lantern does not summarise data the viewer cannot see. |

## Events (PostHog)

`role_health_opened` {role_id, state} · `health_action_taken` {action, suggested_by_lantern, seconds_from_open} · `health_action_dismissed` {action} · `health_stall_detected` {channel, days_to_detect}.
