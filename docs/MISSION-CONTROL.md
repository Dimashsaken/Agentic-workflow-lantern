# Mission Control — the frontend for the agent fleet

Where developers *see* the pipeline. Design principle (from
`docs/research/karpathy-agentic-loops.md`): the human's job in an agentic loop is
**verification**, so the UI is a verification surface first and a dashboard second —
"make the generation-verification loop go as fast as possible."

## Where it runs

`tools/mission-control/app.py` — FastAPI + server-rendered HTML (no build step, no
JS framework), served from the **same EC2 box** as the orchestrator (port 8080,
its own systemd unit `lantern-mission-control.service`). It reads the same Postgres
the pipeline writes, so there is no second source of truth. Expose it to the team
via Tailscale (recommended) or a security-group-allowlisted IP + the built-in HTTP
Basic auth — never open to the internet. Upgrade path if it ever needs public
access or SSO: put CloudFront/ALB + OIDC in front; the app doesn't change.

## The three screens (and why these visuals)

1. **The Inbox — "what needs a human right now."** Pending gates, oldest first,
   each with its payload (video link, plan, findings) and Approve/Reject inline.
   This is the top of the page because the research's #5 failure mode is the silent
   stall: *waiting must be visible, never assumed*. A developer who opens Mission
   Control sees their blocking decisions before anything else.
2. **The Board — runs as cards in stage columns** (kanban: `01-ui-ux` →
   `07-qa-staging`). Color = status (running/waiting/failed/done). One glance
   answers "where is my feature?" — the mental model matches the fixed pipeline, so
   no legend is needed.
3. **The Run page — a verification timeline.** Per stage: status, attempts, the
   stage report rendered as HTML, artifacts (QA videos linked with their shot
   lists, plans, diff/PR links), and the append-only event log underneath. This is
   where Justin watches a video instead of attending a demo, and where a developer
   audits an agent's claim in seconds — small artifacts, visually reviewable, per
   Karpathy's leash rule.

## Gate integrity in the UI

Approve/Reject buttons only render for authenticated users in the approver list
(`LANTERN_WEB_USERS`); the decision writes the `approvals` row with actor +
timestamp + note (`channel='web'`) — the same fail-closed contract as the CLI
(D8). No users configured → the app is read-only. Agents have no route here.

## Roadmap

- v1 (now): the three screens above, polling refresh.
- v2: SSE live event stream on the run page; inline `<video>` playback via
  presigned S3 URLs; Slack notification links deep-linking to the gate.
- v3: brief-composer form ("start a run" from the browser), PostHog error inbox
  feeding the debug lifecycle.
