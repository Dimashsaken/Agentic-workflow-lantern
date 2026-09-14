"""Seed DEMO data so Mission Control has something to show. LOCAL DEV ONLY.

    python seed_demo.py --reset     (--reset wipes all pipeline tables first)
"""

import argparse
import asyncio
import base64
import json
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

AZURE_RUNNER = Path(__file__).resolve().parents[1] / "azure-runner"
sys.path.insert(0, str(AZURE_RUNNER))
load_dotenv(AZURE_RUNNER / ".env")

from pipeline import REPO, db_urls  # noqa: E402
from chat_service import ensure_chat_tables  # noqa: E402

DEMO_REPORT = """# Stage Report: 01-ui-ux — feat-20260825-demo-export

- **Agent/author:** ui-ux
- **Status:** PASS

## Summary
Diverged 7 skeletons on EC2, converged the top 3 in Paper; recommending
**background-job** (queue + email link) — fewest steps for large exports.

## Artifacts
- `options.md` — the three options with judge scores
- `handoff.json` — gate payload source (Paper URL + 2x PNGs)
- video: 0:00 entry · 0:14 column picker · 0:31 export queued · 0:48 error state
"""

# 1x1 gray PNG — placeholder option frames so the gate's image strip renders.
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVR4nGNiAAAABgADNjd8qAAAAABJRU5ErkJggg==")


async def main(reset: bool) -> None:
    conn = await asyncpg.connect(db_urls()[1])
    await ensure_chat_tables(conn)
    if reset:
        await conn.execute(
            "TRUNCATE events, artifacts, approvals, stage_executions, runs, runners, "
            "chat_turns, chat_sessions, custom_agents CASCADE")

    # Runner heartbeats: EC2 alive, the design workstation offline for 10 minutes.
    await conn.execute("""INSERT INTO runners (name, last_seen) VALUES
                          ('ec2', now()), ('workstation', now() - interval '10 minutes')
                          ON CONFLICT (name) DO UPDATE SET last_seen = excluded.last_seen""")

    # Run 1: waiting at the ux_signoff gate (Inbox + Paper URL + PNGs side by side)
    r1 = "feat-20260825-demo-export"
    run_dir = REPO / "workflow" / "runs" / r1 / "01-ui-ux"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.md").write_text(DEMO_REPORT, encoding="utf-8")
    options = ["background-job", "wizard", "inline-progress"]
    for name in options:
        (run_dir / f"{name}@2x.png").write_bytes(TINY_PNG)
    handoff = {
        "paper_url": "https://app.paper.design/file/demo-lantern",
        "recommended": "background-job",
        "options": [{"name": n, "status": "presented",
                     "pngs": [f"workflow/runs/{r1}/01-ui-ux/{n}@2x.png"]} for n in options],
        "video": "https://example-bucket.s3.amazonaws.com/demo/ux-walkthrough.webm",
        "metrics": {"divergence_generated": 7,
                    "critique_iterations": {"background-job": 2, "wizard": 3, "inline-progress": 1}},
    }
    (run_dir / "handoff.json").write_text(json.dumps(handoff, indent=2), encoding="utf-8")

    await conn.execute(
        """INSERT INTO runs (id, brief, pipeline_version, status, current_stage, created_by)
           VALUES ($1, 'workflow/briefs/demo.md', '2', 'waiting_gate', '01-ui-ux.design', 'justin')""", r1)
    await conn.execute(
        """INSERT INTO stage_executions (run_id, stage, runner, status, finished_at, idempotency_key)
           VALUES ($1, '01-ui-ux.diverge', 'ec2', 'succeeded', now(), $1 || ':01-ui-ux.diverge:1')""", r1)
    e1 = await conn.fetchval(
        """INSERT INTO stage_executions (run_id, stage, runner, status, finished_at, idempotency_key)
           VALUES ($1, '01-ui-ux.design', 'workstation', 'succeeded', now(), $1 || ':01-ui-ux.design:1')
           RETURNING id""", r1)
    await conn.execute(
        """INSERT INTO approvals (run_id, stage_execution_id, gate, channel, payload)
           VALUES ($1, $2, 'ux_signoff', 'cli', $3)""",
        r1, e1, json.dumps({"stage": "01-ui-ux.design", "run_folder": f"workflow/runs/{r1}/",
                            "handoff": handoff}))
    await conn.execute(
        """INSERT INTO artifacts (run_id, stage, kind, uri) VALUES
           ($1, '01-ui-ux', 'report', 'workflow/runs/' || $1 || '/01-ui-ux/report.md'),
           ($1, '01-ui-ux', 'design_handoff', 'workflow/runs/' || $1 || '/01-ui-ux/handoff.json'),
           ($1, '01-ui-ux', 'paper_file', 'https://app.paper.design/file/demo-lantern'),
           ($1, '01-ui-ux', 'qa_video', 'https://example-bucket.s3.amazonaws.com/demo/ux-walkthrough.webm')""", r1)
    for actor, typ in [("human:justin", "run_created"), ("orchestrator", "stage_started"),
                       ("agent:ui-ux", "stage_succeeded"), ("orchestrator", "gate_opened")]:
        await conn.execute("INSERT INTO events (run_id, actor, type, data) VALUES ($1,$2,$3,'{}')",
                           r1, actor, typ)

    # Run 2: mid-pipeline at qa-dev (shows the Board in motion)
    r2 = "feat-20260820-demo-sso"
    await conn.execute(
        """INSERT INTO runs (id, brief, pipeline_version, status, current_stage, created_by)
           VALUES ($1, 'workflow/briefs/sso.md', '2', 'running', '04-qa-dev', 'dev-anna')""", r2)
    for st in ("01-ui-ux.diverge", "01-ui-ux.design", "02-pre-coding", "03-coding"):
        await conn.execute(
            """INSERT INTO stage_executions (run_id, stage, status, finished_at, idempotency_key)
               VALUES ($1, $2, 'succeeded', now(), $1 || ':' || $2 || ':1')""", r2, st)

    # Run 3: stalled — needs the design workstation (its daemon is offline above)
    r3 = "feat-20260825-demo-billing"
    await conn.execute(
        """INSERT INTO runs (id, brief, pipeline_version, status, current_stage, created_by)
           VALUES ($1, 'workflow/briefs/billing.md', '2', 'running', '01-ui-ux.design', 'justin')""", r3)
    await conn.execute(
        """INSERT INTO stage_executions (run_id, stage, runner, status, finished_at, idempotency_key)
           VALUES ($1, '01-ui-ux.diverge', 'ec2', 'succeeded', now(), $1 || ':01-ui-ux.diverge:1')""", r3)

    # Run 4: shipped (shows Recently shipped)
    r4 = "feat-20260810-demo-onboarding"
    await conn.execute(
        """INSERT INTO runs (id, brief, pipeline_version, status, current_stage, created_by, completed_at)
           VALUES ($1, 'workflow/briefs/onboarding.md', '2', 'done', '07-qa-staging', 'justin', now())""", r4)

    # Chat surface (docs/CHAT.md): a Lantern thread with a specialist handoff, a
    # ui-ux consult, and one custom agent — enough for the hub, a transcript, and
    # the roster to render with real-looking rows.
    await conn.execute("""INSERT INTO custom_agents (slug, name, purpose, model_pref, created_by)
        VALUES ('release-notes', 'Release Notes',
                'Turns a run''s stage reports into customer-facing release notes.',
                'fast', 'justin') ON CONFLICT (slug) DO NOTHING""")

    cs1 = "consult:justin:lantern:web-demo01"
    await conn.execute(
        """INSERT INTO chat_sessions (id, agent, title, created_by, last_at)
           VALUES ($1, 'lantern', 'What is blocked right now, and what would it cost to unblock?',
                   'justin', now() - interval '2 hours')
           ON CONFLICT (id) DO NOTHING""", cs1)
    trace1 = [
        {"t": 0.8, "kind": "tool", "name": "pipeline_snapshot", "args": "{}"},
        {"t": 2.1, "kind": "tool_done",
         "output": '{"runs": [{"id": "feat-20260825-demo-export", "status": "waiting_gate", '
                   '"pending_gate": "ux_signoff", "gate_age_h": 11.2}, '
                   '{"id": "feat-20260825-demo-billing", "status": "running", '
                   '"stage": "01-ui-ux.design"}], "runners": [{"name": "ec2", "online": true}, '
                   '{"name": "workstation", "online": false}], "today_est_usd": 0.94}'},
        {"t": 3.0, "kind": "specialist", "role": "ui-ux",
         "question": "What is left before the demo-export ux_signoff gate can be decided?"},
        {"t": 21.4, "kind": "specialist_done", "role": "ui-ux", "tokens": 9840,
         "answer": "The handoff is complete — three options with PNGs and a recommendation "
                   "(background-job). The gate has been waiting on a human for 11 hours; "
                   "nothing is missing from the stage side."},
    ]
    await conn.execute(
        """INSERT INTO chat_turns (session_id, asked_by, user_text, final_text, status, trace,
                                   model, requests, input_tokens, cached_input_tokens,
                                   output_tokens, total_tokens, started_at, finished_at)
           VALUES ($1, 'justin',
                   'What is blocked right now, and what would it cost to unblock?',
                   $2, 'done', $3, 'sol', 6, 41200, 33800, 1450, 42650,
                   now() - interval '2 hours', now() - interval '2 hours' + interval '38 seconds')
           ON CONFLICT DO NOTHING""",
        cs1,
        "Two things are waiting, neither on an agent:\n\n"
        "1. **feat-20260825-demo-export** — parked at the `ux_signoff` gate for 11 hours. "
        "The ui-ux agent confirms the handoff is complete (three options, recommendation: "
        "background-job). Deciding the gate costs nothing but a look at the walkthrough.\n"
        "2. **feat-20260825-demo-billing** — queued for the design workstation, which is "
        "offline. Starting `pipeline.py daemon --runner workstation` on the design machine "
        "unblocks it.\n\nToday's spend so far is ~$0.94 of the $500 tripwire.",
        json.dumps(trace1))

    cs2 = "consult:dev-anna:ui-ux:web-demo02"
    await conn.execute(
        """INSERT INTO chat_sessions (id, agent, title, created_by, run_id, last_at)
           VALUES ($1, 'ui-ux', 'Why background-job over the wizard for large exports?',
                   'dev-anna', 'feat-20260825-demo-export', now() - interval '26 hours')
           ON CONFLICT (id) DO NOTHING""", cs2)
    trace2 = [
        {"t": 1.2, "kind": "tool", "name": "read_file",
         "args": '{"path": "workflow/runs/feat-20260825-demo-export/01-ui-ux/report.md"}'},
        {"t": 2.9, "kind": "tool_done",
         "output": "# Stage Report: 01-ui-ux — feat-20260825-demo-export …"},
    ]
    await conn.execute(
        """INSERT INTO chat_turns (session_id, asked_by, user_text, final_text, status, trace,
                                   model, requests, input_tokens, cached_input_tokens,
                                   output_tokens, total_tokens, started_at, finished_at)
           VALUES ($1, 'dev-anna', 'Why background-job over the wizard for large exports?',
                   $2, 'done', $3, 'sol', 3, 18400, 12100, 620, 19020,
                   now() - interval '26 hours', now() - interval '26 hours' + interval '21 seconds')
           ON CONFLICT DO NOTHING""",
        cs2,
        "Two reasons from the judge pass (report.md, options table):\n\n"
        "- **Fewest steps for the large-file case** — the wizard front-loads choices the "
        "user can't answer for a 2GB export; background-job asks nothing and emails the link.\n"
        "- **Failure isolation** — a queued job can retry server-side; the wizard's inline "
        "progress dies with the tab.\n\nThe wizard scored higher only on discoverability.",
        json.dumps(trace2))

    await conn.close()
    print("demo data seeded (runs:", ", ".join([r1, r2, r3, r4]),
          "+ 2 chat sessions, 1 custom agent)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    asyncio.run(main(ap.parse_args().reset))
