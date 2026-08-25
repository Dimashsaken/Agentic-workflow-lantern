"""Lantern pipeline runner — one call takes a brief from concept to live.

    python pipeline.py init-db
    python pipeline.py run workflow/briefs/<slug>.md [--run-id feat-YYYYMMDD-<slug>] [--by justin] [--follow]
    python pipeline.py daemon                      # claim-execute-advance loop (systemd on EC2)
    python pipeline.py status
    python pipeline.py approve <run-id> <gate> --by <name> [--note "..."]
    python pipeline.py reject  <run-id> <gate> --by <name> [--note "..."]
    python pipeline.py retry   <run-id>

Design: docs/ORCHESTRATION.md. Schema: schema.sql. SCAFFOLD (D8): compiles and
imports verified; first exercised end-to-end on EC2 with a real Postgres.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

from agents import Agent, Runner, set_default_openai_api, set_default_openai_client, set_tracing_disabled
from agents.extensions.memory import SQLAlchemySession
from agents.mcp import MCPServerStdio

from orchestrator import (
    BROWSER_ROLES, REPO, ROLE_FOR_STAGE, append_file, azure_v1_client,
    build_instructions, check_postconditions, list_dir, model_for, read_file,
    write_file,
)

load_dotenv(Path(__file__).parent / ".env")

PIPELINE_VERSION = "1"
POLL_SECONDS = 5

# (stage, type, gate-after). Human stages produce an approval immediately and wait.
FEATURE_STAGES = [
    ("01-ui-ux",       "agent", "ux_signoff"),
    ("02-pre-coding",  "agent", "plan_signoff"),
    ("03-coding",      "human", "code_complete"),
    ("04-qa-dev",      "agent", None),
    ("05-post-coding", "agent", None),
    ("06-security",    "agent", "staging_deploy"),
    ("07-qa-staging",  "agent", "prod_signoff"),
]
STAGE_INDEX = {s: i for i, (s, _, _) in enumerate(FEATURE_STAGES)}


def db_urls() -> tuple[str, str]:
    url = os.environ.get(
        "LANTERN_DATABASE_URL",
        "postgresql+asyncpg://lantern:lantern@localhost:5432/lantern",
    )
    sqlalchemy_url = url if "+asyncpg" in url else url.replace("postgresql://", "postgresql+asyncpg://")
    return sqlalchemy_url, sqlalchemy_url.replace("+asyncpg", "")


async def connect() -> asyncpg.Connection:
    return await asyncpg.connect(db_urls()[1])


async def log_event(conn, run_id: str | None, actor: str, type_: str, data: dict | None = None) -> None:
    await conn.execute(
        "INSERT INTO events (run_id, actor, type, data) VALUES ($1, $2, $3, $4)",
        run_id, actor, type_, json.dumps(data or {}),
    )


# ── stage execution ──────────────────────────────────────────────────────────

async def run_agent_stage(conn, run_id: str, stage: str) -> None:
    role = ROLE_FOR_STAGE[stage]
    attempt = await conn.fetchval(
        "SELECT coalesce(max(attempt), 0) + 1 FROM stage_executions WHERE run_id = $1 AND stage = $2",
        run_id, stage,
    )
    exec_id = await conn.fetchval(
        """INSERT INTO stage_executions (run_id, stage, attempt, status, idempotency_key, heartbeat_at)
           VALUES ($1, $2, $3, 'running', $4, now()) RETURNING id""",
        run_id, stage, attempt, f"{run_id}:{stage}:{attempt}",
    )
    await log_event(conn, run_id, "orchestrator", "stage_started", {"stage": stage, "attempt": attempt})

    memory_before = (REPO / "agents" / role / "memory.md").read_text(encoding="utf-8")
    session = SQLAlchemySession.from_url(f"{run_id}:{stage}", url=db_urls()[0], create_tables=True)

    mcp_servers = []
    if role in BROWSER_ROLES:
        mcp_servers.append(MCPServerStdio(
            params={"command": "npx", "args": ["-y", "@playwright/mcp@latest"]}, name="playwright"))
    for s in mcp_servers:
        await s.connect()
    try:
        agent = Agent(
            name=role,
            model=model_for(role),
            instructions=build_instructions(role, run_id, stage),
            tools=[read_file, write_file, append_file, list_dir],
            mcp_servers=mcp_servers,
        )
        result = await Runner.run(
            agent,
            input=f"Begin your {stage} session for run {run_id} (attempt {attempt}). "
                  "Orient per AGENTS.md, do the work, satisfy all three postconditions.",
            session=session,
            max_turns=120,
        )
        final = str(result.final_output)
    finally:
        for s in mcp_servers:
            await s.cleanup()

    missing = check_postconditions(role, run_id, stage, memory_before)
    if missing:
        raise RuntimeError("postconditions failed: " + "; ".join(missing))

    report = f"workflow/runs/{run_id}/{stage}/report.md"
    await conn.execute(
        "INSERT INTO artifacts (run_id, stage, kind, uri) VALUES ($1, $2, 'report', $3)",
        run_id, stage, report,
    )
    await conn.execute(
        "UPDATE stage_executions SET status = 'succeeded', output = $1, finished_at = now() WHERE id = $2",
        json.dumps({"final_output": final[-4000:], "report": report}), exec_id,
    )
    await log_event(conn, run_id, f"agent:{role}", "stage_succeeded", {"stage": stage})


async def open_gate(conn, run_id: str, stage: str, gate: str) -> None:
    await conn.execute(
        """INSERT INTO approvals (run_id, gate, channel, payload) VALUES ($1, $2, 'cli', $3)""",
        run_id, gate, json.dumps({"stage": stage, "run_folder": f"workflow/runs/{run_id}/"}),
    )
    await conn.execute(
        "UPDATE runs SET status = 'waiting_gate', updated_at = now() WHERE id = $1", run_id)
    await log_event(conn, run_id, "orchestrator", "gate_opened", {"gate": gate, "after_stage": stage})
    print(f"[{run_id}] gate '{gate}' opened — approve with: python pipeline.py approve {run_id} {gate} --by <you>")


async def advance(conn, run_id: str, stage: str) -> None:
    nxt = STAGE_INDEX[stage] + 1
    if nxt >= len(FEATURE_STAGES):
        await conn.execute(
            "UPDATE runs SET status = 'done', completed_at = now(), updated_at = now() WHERE id = $1", run_id)
        await log_event(conn, run_id, "orchestrator", "run_done", {})
        print(f"[{run_id}] DONE — concept to live complete.")
        return
    await conn.execute(
        "UPDATE runs SET current_stage = $1, status = 'running', updated_at = now() WHERE id = $2",
        FEATURE_STAGES[nxt][0], run_id)


async def step_run(conn, run_id: str) -> None:
    """Execute the current stage of one claimed run, then gate or advance."""
    row = await conn.fetchrow("SELECT current_stage FROM runs WHERE id = $1", run_id)
    stage = row["current_stage"]
    _, stype, gate = FEATURE_STAGES[STAGE_INDEX[stage]]
    try:
        if stype == "agent":
            await run_agent_stage(conn, run_id, stage)
        else:  # human stage: nothing to execute — the gate IS the stage
            print(f"[{run_id}] {stage} is a human stage (developer + Codex CLI).")
        if gate:
            await open_gate(conn, run_id, stage, gate)
        else:
            await advance(conn, run_id, stage)
    except Exception as e:  # noqa: BLE001 — orchestrator must not die with a claim held
        await conn.execute(
            """UPDATE stage_executions SET status = 'failed', error = $1, finished_at = now()
               WHERE run_id = $2 AND stage = $3 AND status = 'running'""",
            str(e)[:4000], run_id, stage)
        await conn.execute(
            "UPDATE runs SET status = 'failed', updated_at = now() WHERE id = $1", run_id)
        await log_event(conn, run_id, "orchestrator", "stage_failed", {"stage": stage, "error": str(e)[:500]})
        print(f"[{run_id}] {stage} FAILED: {e}\n  rework, then: python pipeline.py retry {run_id}", file=sys.stderr)


async def claim_and_step(conn) -> bool:
    """One tick: claim a runnable run (skip-locked) and execute its current stage."""
    async with conn.transaction():
        row = await conn.fetchrow(
            "SELECT id FROM runs WHERE status = 'running' ORDER BY updated_at FOR UPDATE SKIP LOCKED LIMIT 1")
        if not row:
            return False
        run_id = row["id"]
        await conn.execute("UPDATE runs SET updated_at = now() WHERE id = $1", run_id)
    await step_run(conn, run_id)
    return True


# ── commands ─────────────────────────────────────────────────────────────────

async def cmd_init_db() -> None:
    conn = await connect()
    await conn.execute((Path(__file__).parent / "schema.sql").read_text(encoding="utf-8"))
    await conn.close()
    print("schema applied")


async def cmd_run(brief_path: str, run_id: str | None, by: str, follow: bool) -> None:
    brief = Path(brief_path)
    if not brief.exists():
        sys.exit(f"brief not found: {brief_path}")
    if not run_id:
        run_id = f"feat-{datetime.now(timezone.utc):%Y%m%d}-{brief.stem.lstrip('_').lower()}"
    run_dir = REPO / "workflow" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "brief.md").write_text(brief.read_text(encoding="utf-8"), encoding="utf-8")

    conn = await connect()
    await conn.execute(
        """INSERT INTO runs (id, brief, pipeline_version, current_stage, created_by)
           VALUES ($1, $2, $3, $4, $5)""",
        run_id, str(brief), PIPELINE_VERSION, FEATURE_STAGES[0][0], by)
    await log_event(conn, run_id, f"human:{by}", "run_created", {"brief": str(brief)})
    print(f"run {run_id} created — the pipeline takes it from here.")
    if follow:
        while True:
            status = await conn.fetchval("SELECT status FROM runs WHERE id = $1", run_id)
            if status != "running":
                print(f"[{run_id}] status: {status}")
                break
            await step_run(conn, run_id)
    await conn.close()


async def cmd_daemon() -> None:
    conn = await connect()
    print(f"lantern orchestrator daemon — polling every {POLL_SECONDS}s")
    while True:
        worked = await claim_and_step(conn)
        if not worked:
            await asyncio.sleep(POLL_SECONDS)


async def cmd_decide(run_id: str, gate: str, by: str, note: str, approved: bool) -> None:
    # NOTE (fail-closed): CLI access to this box == approval authority for now.
    # The Slack/GitHub front-ends MUST verify actor allowlists + webhook signatures.
    conn = await connect()
    status = "approved" if approved else "rejected"
    updated = await conn.fetchval(
        """UPDATE approvals SET status = $1, decided_at = now(), decided_by = $2, decision_note = $3
           WHERE run_id = $4 AND gate = $5 AND status = 'pending' RETURNING id""",
        status, by, note, run_id, gate)
    if not updated:
        sys.exit(f"no pending approval for run {run_id} gate {gate}")
    await log_event(conn, run_id, f"human:{by}", f"gate_{status}", {"gate": gate, "note": note})
    if approved:
        stage = await conn.fetchval("SELECT current_stage FROM runs WHERE id = $1", run_id)
        await advance(conn, run_id, stage)
        print(f"[{run_id}] {gate} approved by {by} — advancing.")
    else:
        await conn.execute("UPDATE runs SET status = 'failed', updated_at = now() WHERE id = $1", run_id)
        print(f"[{run_id}] {gate} rejected by {by} — run marked failed; rework then `retry`.")
    await conn.close()


async def cmd_retry(run_id: str) -> None:
    conn = await connect()
    await conn.execute("UPDATE runs SET status = 'running', updated_at = now() WHERE id = $1", run_id)
    await log_event(conn, run_id, "human:cli", "run_retried", {})
    print(f"[{run_id}] re-queued at its current stage (fresh attempt, same session memory).")
    await conn.close()


async def cmd_status() -> None:
    conn = await connect()
    runs = await conn.fetch(
        "SELECT id, status, current_stage, updated_at FROM runs WHERE status != 'done' ORDER BY updated_at DESC")
    if not runs:
        print("no active runs")
    for r in runs:
        print(f"{r['id']:<40} {r['status']:<13} {r['current_stage']:<16} updated {r['updated_at']:%Y-%m-%d %H:%M}")
    pend = await conn.fetch("SELECT run_id, gate, requested_at FROM approvals WHERE status = 'pending'")
    for p in pend:
        print(f"  ⏳ pending gate: {p['run_id']} → {p['gate']} (since {p['requested_at']:%Y-%m-%d %H:%M})")
    await conn.close()


def main() -> None:
    set_default_openai_client(azure_v1_client())
    set_default_openai_api("chat_completions")
    set_tracing_disabled(True)  # no OpenAI-platform key on the Azure credential set

    ap = argparse.ArgumentParser(prog="lantern")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db")
    p = sub.add_parser("run"); p.add_argument("brief"); p.add_argument("--run-id")
    p.add_argument("--by", default=os.environ.get("USERNAME") or os.environ.get("USER", "unknown"))
    p.add_argument("--follow", action="store_true")
    sub.add_parser("daemon")
    for name in ("approve", "reject"):
        p = sub.add_parser(name); p.add_argument("run_id"); p.add_argument("gate")
        p.add_argument("--by", required=True); p.add_argument("--note", default="")
    p = sub.add_parser("retry"); p.add_argument("run_id")
    sub.add_parser("status")
    a = ap.parse_args()

    match a.cmd:
        case "init-db": asyncio.run(cmd_init_db())
        case "run":     asyncio.run(cmd_run(a.brief, a.run_id, a.by, a.follow))
        case "daemon":  asyncio.run(cmd_daemon())
        case "approve": asyncio.run(cmd_decide(a.run_id, a.gate, a.by, a.note, True))
        case "reject":  asyncio.run(cmd_decide(a.run_id, a.gate, a.by, a.note, False))
        case "retry":   asyncio.run(cmd_retry(a.run_id))
        case "status":  asyncio.run(cmd_status())


if __name__ == "__main__":
    main()
