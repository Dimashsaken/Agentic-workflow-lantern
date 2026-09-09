# Mission Control

The web UI for the software factory — design and rationale in
`docs/MISSION-CONTROL.md`. v3 (D22):

| Page | Module | What it answers |
|------|--------|-----------------|
| **Home** `/` | `app.py` | The **Inbox** (every pending gate, each card opening with the artifact being decided, Approve/Reject on the card) above the gate-latency ledger and the **Board** (runs as tickets in five workflow columns). |
| **Run** `/run/<id>` | `lanes.py` | **Swim lanes**: one lane per stage execution key in start order, attempts as bars, gate diamonds between lanes, per-lane tier / tokens / est. cost. |
| **Drawer** `/run/<id>/exec/<n>` | `drawer.py` | One execution end to end: compiled prompt, kickoff, tool-call timeline, report, envelope + validation, quality gate, memory rows, ledger, and the retry / rework-to actions. |
| **Traceability** `/run/<id>/trace` | `traceability.py` | Story criteria × plan tasks × commits × QA charter × validation verdicts. |
| **Factory** `/factory` | `catalog.py` | Roles, stages and gates, the model stack, each product's quality commands, evals, builders. |
| **Cost** `/cost` | `cost.py` | Per run, per day, per model, and both spend tripwires. (`/spend` redirects here.) |
| **Gates** · **Runs** · **Chat** · **Agents** | `app.py`, `chat.py` | Gate history, the flight-strip run list, and consult mode (`docs/CHAT.md`). |

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
