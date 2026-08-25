# Mission Control

The web UI for the fleet — design and rationale in `docs/MISSION-CONTROL.md`.
Three screens: the **Inbox** (pending gates with inline Approve/Reject), the
**Board** (runs as cards in stage columns), and the **Run page** (verification
timeline: reports, artifacts, videos, events).

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
