# Mission Control

The web UI for the software factory — design and rationale in
`docs/MISSION-CONTROL.md`. v3 (D22):

| Page | Module | What it answers |
|------|--------|-----------------|
| **Work** `/`, `/runs` | `worklist.py`, `app.py` | One searchable queue. Reviews and blocked runs first; filters for active work, reviews, completed work, and history. |
| **Reviews** `/gates` | `app.py` | Open one review to see its artifact and decide. Timing and decision history are optional disclosures. |
| **Run** `/run/<id>` | `app.py`, `lanes.py` | Current decision and recent activity. Full execution lanes, reports, and audit history are available on demand. |
| **Drawer** `/run/<id>/exec/<n>` | `drawer.py` | Prompt, tool calls, report, validation, quality gate, memory, ledger, retry and rework. |
| **Traceability** `/run/<id>/trace` | `traceability.py` | Story criteria mapped to plan tasks, commits, QA, and validation. |
| **Chat** `/chat` | `chat.py` | Start with Lantern; choose a specialist only when needed. |
| **Workspace** | `catalog.py`, `cost.py`, `chat.py` | Secondary navigation for Agents, Factory and Cost. |

`ui.py` holds the tokens, CSS, page shell and the small vanilla-JS layer (theme,
keyboard map, the drawer over fetch). No build step. **One style: white**, on every
page and every machine — the OS preference is never consulted, so the same page looks
the same to everyone discussing it; dark is a per-browser opt-in (`d`). Every input,
select and textarea shares one field rule. One column below 820px.
Keyboard: `j`/`k` move, `Enter` opens, `a` approves, `r` rejects with a note, `t` the
matrix, `?` the map — every one of them also a link or a button.

The drawer reads `<run>/<stage-dir>/trace/<execution-key>.json`, written by
`factory.write_trace` from both executors and redacted before it exists (the QA target
section dropped, credential-shaped text masked). Executions from before D22 have no
trace and the drawer says so.

Chat needs the Azure model env vars (`AZURE_OPENAI_*`, `LANTERN_MODEL_*`) on the
box; without them every page still works and the composer explains what is
missing. The SSE bus is in-process — run ONE uvicorn worker (the systemd unit
and the commands below already do).

**Gate latency (feat-20260831-gate-latency):** Reviews includes a folded Review timing
ledger below the queue — per gate type, the median
`decided_at - requested_at` over the last 30 days of decided (approved or
rejected) approvals, with its sample count. Zero-decision gates show
`— · no decisions · n=0`; a median over 24h renders in the warning color. Every
pending review shows its age from `approvals.requested_at`; strictly over
24h it gains a `STALE` chip and warning border (the plan's staffing threshold —
hardcoded, changing it is a code edit in `app.py:STALE_SECONDS`). All of it is
read-only from the `approvals` table in one grouped query; if that query fails
the ledger degrades to a sentence and the reviews still render. Behavior tests:
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
