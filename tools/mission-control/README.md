# Mission Control

The web UI for the fleet — design and rationale in `docs/MISSION-CONTROL.md`.
Three screens: the **Inbox** (pending gates with inline Approve/Reject), the
**Board** (runs as cards in stage columns), and the **Run page** (verification
timeline: reports, artifacts, videos, events).

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
