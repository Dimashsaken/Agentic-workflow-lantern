# Options — feat-20260825-role-health

Three structural options for the post-launch "is this role alive?" screen, converged in
Paper (**Agent sandbox — ui-ux runs**, page `feat-20260825-role-health`:
<https://app.paper.design/file/01M0W444P0FVBY0PKRDYAPYDWH/6-0>), grounded in
`design/design-system.md` (tokens contentHash `288d9538`). Divergence explored eight
axes and kept three — scores and the five cuts are in the divergence section of
`report.md`. Critique evidence: `critique-log.md`.

**IA decision common to all three:** this lives under LAUNCH, not a new tab. It is what
"11 · Live" grows into once a role has history — so the six-tab nav is untouched.

## Option A — `diagnosis-brief` (recommended)

Lantern's verdict is the hero: a headline that states the condition ("Stalling — and
it's one fix"), a warning card naming the cause and the single next action with its
price and consequence, then supporting vitals, a source ledger, a what-changed timeline
and the trait-match distribution.

**Pros:** answers the brief's actual question — *is it healthy, and what do I do?* — in
one glance and one click; the "if you do nothing" projection makes the cost of ignoring
it concrete; degradation is localised to a channel, so the user never has to diagnose.
**Cons:** it leads with one recommended action, so a week with two independent problems
compresses awkwardly into a single hero card.

## Option B — `progressive-drilldown`

Six health signals as collapsed rows (volume, boards, outreach, quality, calibration
queue, referrals), each with a status dot and a headline number; the degraded one is
expanded in place with its day-by-day chart, explanation and action.

**Pros:** fastest scan of *everything* at once, and the row model scales to new signals
without redesign; hides evidence until asked, which suits a between-meetings check.
**Cons:** the diagnosis is implied by a dot rather than stated — a hurried reader can
miss the "why"; two simultaneous problems mean two expansions and more scrolling.

## Option C — `channel-lanes`

One card per source (boards, outreach, inbound, referrals), each carrying its own
sparkline, volume, quality, status and action, with the degraded lane tinted and the
never-started lane dashed.

**Pros:** the best answer to "where do my good candidates come from" — quality per lane
sits directly beside volume per lane, which is where the real decision lives; makes an
unused channel visible as an absence rather than hiding it in a table row.
**Cons:** no single verdict — the user assembles the diagnosis themselves; and it is the
weakest at showing the role's overall trend over time.

## States (all options — detail in flow-spec.md)

Healthy, stalling (one channel degraded — shown), stalled (no flow), just-launched (not
enough data, must not read as failure), stale data, and per-source load errors.

## Recommendation

**diagnosis-brief** — it is the only option that enacts the product's promise on this
screen: Lantern forms an opinion, names the cause, and proposes one action, with the
numbers as evidence rather than as the answer.

**Strongest argument against it:** it optimises for the common case of one problem at a
time. If real pipelines routinely degrade on two axes at once, `progressive-drilldown`
degrades more gracefully and `diagnosis-brief` becomes a summary card that sits on top
of it — a cheap merge later, but a rebuild if we discover it after shipping.
