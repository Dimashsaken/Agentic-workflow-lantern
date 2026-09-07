# Mission Control

The web UI for the fleet — design and rationale in `docs/MISSION-CONTROL.md`.
Five screens: the **Board** (runs as tickets in obligation columns), **Gates**
(pending approvals with inline Approve/Reject), the **Run page** (verification
timeline: reports, artifacts, videos, events), **Chat** (consult any fleet role,
a custom agent, or the Lantern orchestrator — live tool streaming, history, and
a per-turn token ledger; design in `docs/CHAT.md`, engine in
`tools/azure-runner/chat_service.py`), and **Agents** (the roster + two-field
custom-agent creation). **Spend** folds chat turns into the same ledger.

Chat needs the Azure model env vars (`AZURE_OPENAI_*`, `LANTERN_MODEL_*`) on the
box; without them every page still works and the composer explains what is
missing. The SSE bus is in-process — run ONE uvicorn worker (the systemd unit
and the commands below already do).

**Gate latency (feat-20260831-gate-latency):** the Board carries a full-width
ledger between the statusline and the columns — per gate type, the median
`decided_at - requested_at` over the last 30 days of decided (approved or
rejected) approvals, with its sample count. Zero-decision gates show
`— · no decisions · n=0`; a median over 24h renders in the warning color. Every
pending Review card shows its age from `approvals.requested_at`; strictly over
24h it gains a `STALE` chip and warning border (the plan's staffing threshold —
hardcoded, changing it is a code edit in `app.py:STALE_SECONDS`). All of it is
read-only from the `approvals` table in one grouped query; if that query fails
the ledger degrades to a sentence and the board still renders. Behavior tests:
`python -m unittest test_gate_latency` (stdlib only, no DB).

Runs from the azure-runner venv (shared deps, imports `pipeline.py` directly):

```bash
cd tools/mission-control
../azure-runner/.venv/Scripts/python app.py          # Windows dev
# EC2: systemd unit infra/ec2/lantern-mission-control.service (port 8080)
```

Auth: login page + signed session cookie. Users from
`LANTERN_WEB_USERS="justin:pw,dev:pw"` in the azure-runner `.env` (or SSM on EC2);
optional `LANTERN_WEB_SECRET` for the cookie key. **No page is served without
login**, and with no users configured nobody can log in. Every gate decision
records actor + note + timestamp. Never expose the port publicly — Tailscale or an
IP-allowlisted security group.
