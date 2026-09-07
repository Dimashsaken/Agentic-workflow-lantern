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

## The five screens (and why these visuals)

1. **The Inbox — "what needs a human right now."** Pending gates, oldest first,
   each with its payload (video link, plan, findings) and Approve/Reject inline.
   This is the top of the page because the research's #5 failure mode is the silent
   stall: *waiting must be visible, never assumed*. A developer who opens Mission
   Control sees their blocking decisions before anything else.
2. **The Board — runs as cards in stage columns** (kanban: `01-ui-ux` →
   `07-qa-staging`). Color = status (running/waiting/failed/done). One glance
   answers "where is my feature?" — the mental model matches the fixed pipeline, so
   no legend is needed. Above the columns sits the **gate-latency ledger**
   (feat-20260831-gate-latency): per gate type, the median time-to-decision over
   the last 30 days of decided approvals with its sample count — the
   symphony-alignment §6 staffing signal. Human review latency is the #1 failure
   mode of ticket-to-PR systems, so the wait is on the board, not in a report:
   every pending Review card shows its age, and past 24h it gets an explicit
   `STALE` warning treatment. Read-only over `approvals`; a failed aggregate
   degrades to a sentence without hiding the cards or their decision controls.
3. **The Run page — a verification timeline.** Per stage: status, attempts, the
   stage report rendered as HTML, artifacts (QA videos linked with their shot
   lists, plans, diff/PR links), and the append-only event log underneath. This is
   where Justin watches a video instead of attending a demo, and where a developer
   audits an agent's claim in seconds — small artifacts, visually reviewable, per
   Karpathy's leash rule. Every stage card links to a run-scoped consult of its
   owning role ("consult ui-ux about this run"), and the run header to Lantern.
4. **Chat — talking to the fleet** (`/chat`, design: `docs/CHAT.md`). The web
   face of consult mode (D11): any fleet role, any custom agent, or the Lantern
   orchestrator (which reads the pipeline database and hands questions to
   specialists), with session history, live tool-call streaming over SSE, and
   every turn in the token ledger. Advisory and read-only — the composer footer
   says so on every conversation.
5. **Agents — the roster** (`/agents`). Fleet roles beside user-created custom
   agents, with per-agent usage and memory counts; new agents are a two-field
   form (name + purpose; instructions composed when left empty).

## Gate integrity in the UI

**Nothing is served unauthenticated** — every page redirects to a login screen;
sessions are HMAC-signed cookies (7-day TTL, key from `LANTERN_WEB_SECRET`, falling
back to a hash of `LANTERN_WEB_USERS`). Decisions write the `approvals` row with
actor + timestamp + note (`channel='web'`) — the same fail-closed contract as the
CLI (D8). No users configured → nobody can log in at all. Agents have no route here.

The UI explains itself: stage columns carry human names and one-line descriptions
(`STAGE_META`), each gate states what is being decided and how (`GATE_META`), and a
status legend defines every color — a developer's first visit needs no walkthrough.

## Roadmap

- v1: the first three screens, polling refresh. **Done.**
- v2 (now): Chat + Agents (SSE streaming landed there first); chat spend in the
  ledger views.
- v3: SSE on the run page; inline `<video>` playback via presigned S3 URLs;
  Slack notification links deep-linking to the gate; brief-composer form
  ("start a run" from the browser); PostHog error inbox feeding the debug
  lifecycle; browser-MCP consults for browser roles (docs/CHAT.md roadmap).
