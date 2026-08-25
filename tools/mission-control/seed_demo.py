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
    if reset:
        await conn.execute(
            "TRUNCATE events, artifacts, approvals, stage_executions, runs, runners CASCADE")

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

    await conn.close()
    print("demo data seeded (runs:", ", ".join([r1, r2, r3, r4]) + ")")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    asyncio.run(main(ap.parse_args().reset))
