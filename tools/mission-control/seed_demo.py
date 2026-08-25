"""Seed DEMO data so Mission Control has something to show. LOCAL DEV ONLY.

    python seed_demo.py --reset     (--reset wipes all pipeline tables first)
"""

import argparse
import asyncio
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
Produced three flow options for bulk export; recommending Option B (background job
+ email link) — fewest steps for large exports. Prototype recorded on video.

## Artifacts
- `options.md` — the three options with wireframes
- video: 0:00 entry · 0:14 column picker · 0:31 export queued · 0:48 error state
"""


async def main(reset: bool) -> None:
    conn = await asyncpg.connect(db_urls()[1])
    if reset:
        await conn.execute(
            "TRUNCATE events, artifacts, approvals, stage_executions, runs CASCADE")

    # Run 1: waiting at the ux_signoff gate (shows the Inbox + gate buttons)
    r1 = "feat-20260825-demo-export"
    await conn.execute(
        """INSERT INTO runs (id, brief, pipeline_version, status, current_stage, created_by)
           VALUES ($1, 'workflow/briefs/demo.md', '1', 'waiting_gate', '01-ui-ux', 'justin')""", r1)
    e1 = await conn.fetchval(
        """INSERT INTO stage_executions (run_id, stage, status, finished_at, idempotency_key)
           VALUES ($1, '01-ui-ux', 'succeeded', now(), $1 || ':01-ui-ux:1') RETURNING id""", r1)
    await conn.execute(
        """INSERT INTO approvals (run_id, stage_execution_id, gate, channel, payload)
           VALUES ($1, $2, 'ux_signoff', 'cli', $3)""",
        r1, e1, json.dumps({"video": "s3://demo/ux-walkthrough.webm"}))
    await conn.execute(
        """INSERT INTO artifacts (run_id, stage, kind, uri) VALUES
           ($1, '01-ui-ux', 'report', 'workflow/runs/' || $1 || '/01-ui-ux/report.md'),
           ($1, '01-ui-ux', 'qa_video', 'https://example-bucket.s3.amazonaws.com/demo/ux-walkthrough.webm')""", r1)
    for actor, typ in [("human:justin", "run_created"), ("orchestrator", "stage_started"),
                       ("agent:ui-ux", "stage_succeeded"), ("orchestrator", "gate_opened")]:
        await conn.execute("INSERT INTO events (run_id, actor, type, data) VALUES ($1,$2,$3,'{}')",
                           r1, actor, typ)
    report = REPO / "workflow" / "runs" / r1 / "01-ui-ux" / "report.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(DEMO_REPORT, encoding="utf-8")

    # Run 2: mid-pipeline at qa-dev (shows the Board in motion)
    r2 = "feat-20260820-demo-sso"
    await conn.execute(
        """INSERT INTO runs (id, brief, pipeline_version, status, current_stage, created_by)
           VALUES ($1, 'workflow/briefs/sso.md', '1', 'running', '04-qa-dev', 'dev-anna')""", r2)
    for st in ("01-ui-ux", "02-pre-coding", "03-coding"):
        await conn.execute(
            """INSERT INTO stage_executions (run_id, stage, status, finished_at, idempotency_key)
               VALUES ($1, $2, 'succeeded', now(), $1 || ':' || $2 || ':1')""", r2, st)

    # Run 3: shipped (shows Recently shipped)
    r3 = "feat-20260810-demo-onboarding"
    await conn.execute(
        """INSERT INTO runs (id, brief, pipeline_version, status, current_stage, created_by, completed_at)
           VALUES ($1, 'workflow/briefs/onboarding.md', '1', 'done', '07-qa-staging', 'justin', now())""", r3)

    await conn.close()
    print("demo data seeded (runs:", ", ".join([r1, r2, r3]) + ")")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    asyncio.run(main(ap.parse_args().reset))
