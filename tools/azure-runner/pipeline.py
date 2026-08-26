"""Lantern pipeline runner — one call takes a brief from concept to live.

    python pipeline.py init-db
    python pipeline.py run workflow/briefs/<slug>.md [--run-id feat-YYYYMMDD-<slug>] [--by justin] [--follow]
    python pipeline.py daemon [--runner ec2|workstation]   # claim-execute-advance loop
    python pipeline.py status
    python pipeline.py approve <run-id> <gate> --by <name> [--note "..."]
    python pipeline.py reject  <run-id> <gate> --by <name> [--note "..."]
    python pipeline.py retry   <run-id>
    python pipeline.py agents                      # list consultable agents
    python pipeline.py ask <role> "<prompt>" [-i] [--session name] [--new]  # consult one agent directly
    python pipeline.py runboard                    # re-render workflow/RUNBOARD.md from the DB
    python pipeline.py render-memory [--role X]    # re-render agents/<role>/memory.md from role_memory
    python pipeline.py import-run <run-id> [--stage S --status waiting_gate --gate G]  # backfill a file-era run

Design: docs/ORCHESTRATION.md. Schema: schema.sql.
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

from orchestrator import (
    BROWSER_ROLES, PAPER_PREFLIGHT_HINT, PAPER_STAGES, REPO, ROLE_FOR_STAGE,
    append_file, azure_v1_client, build_consult_instructions, build_instructions,
    check_postconditions, collect_export, consult_roles, db_urls, list_dir,
    list_exports, make_append_memory, model_for, paper_mcp_server, paper_reachable,
    playwright_mcp_server, read_file, render_role_memory, write_file,
)

load_dotenv(Path(__file__).parent / ".env")

PIPELINE_VERSION = "2"  # v2: stage 1 split into diverge/design executions (runner affinity)
POLL_SECONDS = 5

# ── execution plane (D10/D12) ────────────────────────────────────────────────
# LANTERN_EXECUTOR=docker turns the daemon into a dispatcher: it claims work and
# schedules one ephemeral sandbox container per stage execution instead of running
# the agent in-process. 'inprocess' (default) is the laptop/workstation mode.
EXECUTOR = os.environ.get("LANTERN_EXECUTOR", "inprocess")
SANDBOX_IMAGE = os.environ.get("LANTERN_SANDBOX_IMAGE", "lantern-sandbox")
SANDBOX_CPUS = os.environ.get("LANTERN_SANDBOX_CPUS", "1.5")
SANDBOX_MEMORY = os.environ.get("LANTERN_SANDBOX_MEMORY", "2500m")
STAGE_TIMEOUT_MIN = int(os.environ.get("LANTERN_STAGE_TIMEOUT_MIN", "45"))
MAX_CONCURRENCY = int(os.environ.get(
    "LANTERN_MAX_CONCURRENCY", "3" if EXECUTOR == "docker" else "1"))
# Only these env vars cross into a sandbox — never a whole .env. Secrets a stage
# doesn't need (GitHub PAT, PostHog key) are added per-stage when a stage that
# needs them first exists.
SANDBOX_ENV_ALLOWLIST = (
    "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_API_VERSION",
    "LANTERN_MODEL_REASONING", "LANTERN_MODEL_FAST", "LANTERN_OPENAI_API",
)


def sandbox_db_url() -> str:
    """The DB URL as seen from inside a container (host Postgres via the gateway)."""
    return os.environ.get(
        "LANTERN_SANDBOX_DATABASE_URL",
        db_urls()[0].replace("@localhost", "@host.docker.internal"))

# (stage key, run-folder dir, type, gate-after, runner). Human stages produce an
# approval immediately and wait. Stage 1 is split by runner affinity: cheap divergence
# on EC2, Paper convergence on the design workstation (docs/plans/ui-ux-agent-paper.md).
FEATURE_STAGES = [
    ("01-ui-ux.diverge", "01-ui-ux",       "agent", None,             "ec2"),
    ("01-ui-ux.design",  "01-ui-ux",       "agent", "ux_signoff",     "workstation"),
    ("02-pre-coding",    "02-pre-coding",  "agent", "plan_signoff",   "ec2"),
    ("03-coding",        "03-coding",      "human", "code_complete",  "ec2"),
    ("04-qa-dev",        "04-qa-dev",      "agent", None,             "ec2"),
    ("05-post-coding",   "05-post-coding", "agent", None,             "ec2"),
    ("06-security",      "06-security",    "agent", "staging_deploy", "ec2"),
    ("07-qa-staging",    "07-qa-staging",  "agent", "prod_signoff",   "ec2"),
]
STAGE_INDEX = {s[0]: i for i, s in enumerate(FEATURE_STAGES)}
STAGE_DIR = {s[0]: s[1] for s in FEATURE_STAGES}
STAGE_RUNNER = {s[0]: s[4] for s in FEATURE_STAGES}


async def connect() -> asyncpg.Connection:
    return await asyncpg.connect(db_urls()[1])


async def log_event(conn, run_id: str | None, actor: str, type_: str, data: dict | None = None) -> None:
    await conn.execute(
        "INSERT INTO events (run_id, actor, type, data) VALUES ($1, $2, $3, $4)",
        run_id, actor, type_, json.dumps(data or {}),
    )


# ── stage execution ──────────────────────────────────────────────────────────

async def run_agent_stage(conn, run_id: str, stage: str, runner: str) -> None:
    role = ROLE_FOR_STAGE[stage]
    sdir = STAGE_DIR[stage]
    attempt = await conn.fetchval(
        "SELECT coalesce(max(attempt), 0) + 1 FROM stage_executions WHERE run_id = $1 AND stage = $2",
        run_id, stage,
    )
    execution_key = f"{run_id}:{stage}:{attempt}"
    exec_id = await conn.fetchval(
        """INSERT INTO stage_executions (run_id, stage, runner, attempt, status, idempotency_key, heartbeat_at)
           VALUES ($1, $2, $3, $4, 'running', $5, now()) RETURNING id""",
        run_id, stage, runner, attempt, execution_key,
    )
    await log_event(conn, run_id, "orchestrator", "stage_started",
                    {"stage": stage, "attempt": attempt, "runner": runner})

    await render_role_memory(conn, role)   # instructions must read a fresh view
    session = SQLAlchemySession.from_url(f"{run_id}:{stage}", url=db_urls()[0], create_tables=True)

    mcp_servers = []
    if role in BROWSER_ROLES:
        mcp_servers.append(playwright_mcp_server())
    if stage in PAPER_STAGES:
        if not await paper_reachable():
            raise RuntimeError(PAPER_PREFLIGHT_HINT)
        mcp_servers.append(paper_mcp_server())
    for s in mcp_servers:
        await s.connect()
    try:
        agent = Agent(
            name=role,
            model=model_for(role, stage),
            instructions=build_instructions(role, run_id, stage),
            tools=[read_file, write_file, append_file, list_dir, list_exports, collect_export,
                   make_append_memory(role, run_id, stage, execution_key)],
            mcp_servers=mcp_servers,
        )
        result = await Runner.run(
            agent,
            input=f"Begin your {stage} session for run {run_id} (attempt {attempt}). Do not "
                  "reply with a plan — start calling tools now and keep working until the "
                  "report is on disk and append_memory has been called.",
            session=session,
            max_turns=120,
        )
        final = str(result.final_output)
    finally:
        for s in mcp_servers:
            await s.cleanup()

    missing = await check_postconditions(conn, role, run_id, stage, execution_key)
    if missing:
        raise RuntimeError("postconditions failed: " + "; ".join(missing))

    report = f"workflow/runs/{run_id}/{sdir}/report.md"
    await conn.execute(
        "INSERT INTO artifacts (run_id, stage, kind, uri) VALUES ($1, $2, 'report', $3)",
        run_id, sdir, report,
    )
    if stage == "01-ui-ux.design":
        await register_design_artifacts(conn, run_id, sdir)
    await conn.execute(
        "UPDATE stage_executions SET status = 'succeeded', output = $1, finished_at = now() WHERE id = $2",
        json.dumps({"final_output": final[-4000:], "report": report}), exec_id,
    )
    await log_event(conn, run_id, f"agent:{role}", "stage_succeeded", {"stage": stage})


async def run_agent_stage_docker(conn, run_id: str, stage: str, runner: str) -> None:
    """One stage in one ephemeral sandbox container (D10/D12).

    The host side owns the DB row lifecycle and the postcondition verdict; the
    container runs orchestrator.py with this execution's key and checks its own
    postconditions too (defense in depth — a compromised container exiting 0 still
    cannot pass without the report on the mounted run dir and its memory row).
    """
    role = ROLE_FOR_STAGE[stage]
    sdir = STAGE_DIR[stage]
    attempt = await conn.fetchval(
        "SELECT coalesce(max(attempt), 0) + 1 FROM stage_executions WHERE run_id = $1 AND stage = $2",
        run_id, stage,
    )
    execution_key = f"{run_id}:{stage}:{attempt}"
    exec_id = await conn.fetchval(
        """INSERT INTO stage_executions (run_id, stage, runner, attempt, status, idempotency_key, heartbeat_at)
           VALUES ($1, $2, $3, $4, 'running', $5, now()) RETURNING id""",
        run_id, stage, runner, attempt, execution_key,
    )
    await log_event(conn, run_id, "orchestrator", "stage_started",
                    {"stage": stage, "attempt": attempt, "runner": runner, "executor": "docker"})

    run_dir = REPO / "workflow" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    name = f"lantern-{run_id}-{stage}-{attempt}".replace(".", "-")
    cmd = ["docker", "run", "--rm", "--name", name,
           # uid 1000 == the host app user: artifacts on the mounted run dir come out
           # host-owned; root-owned files in the git tree broke cleanup on 2026-08-26
           "--user", os.environ.get("LANTERN_SANDBOX_UID", "1000:1000"),
           "--cpus", SANDBOX_CPUS, "--memory", SANDBOX_MEMORY,
           "--add-host=host.docker.internal:host-gateway",
           "-v", f"{REPO}:/repo-src:ro",
           "-v", f"{run_dir}:/work/lantern/workflow/runs/{run_id}:rw",
           "-e", f"LANTERN_EXECUTION_KEY={execution_key}",
           "-e", f"LANTERN_DATABASE_URL={sandbox_db_url()}"]
    for var in SANDBOX_ENV_ALLOWLIST:
        if os.environ.get(var):
            cmd += ["-e", f"{var}={os.environ[var]}"]
    cmd += [SANDBOX_IMAGE, run_id, stage]

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=STAGE_TIMEOUT_MIN * 60)
    except asyncio.TimeoutError:
        kill = await asyncio.create_subprocess_exec("docker", "kill", name)
        await kill.wait()
        await proc.communicate()
        raise RuntimeError(f"sandbox hit the {STAGE_TIMEOUT_MIN}-minute wall clock and was killed")
    tail = out.decode(errors="replace")[-4000:]
    if proc.returncode != 0:
        raise RuntimeError(f"sandbox exited {proc.returncode}: {tail[-1500:]}")

    missing = await check_postconditions(conn, role, run_id, stage, execution_key)
    if missing:
        raise RuntimeError("postconditions failed (host re-check): " + "; ".join(missing))
    await render_role_memory(conn, role)   # keep the host's rendered view fresh

    report = f"workflow/runs/{run_id}/{sdir}/report.md"
    await conn.execute(
        "INSERT INTO artifacts (run_id, stage, kind, uri) VALUES ($1, $2, 'report', $3)",
        run_id, sdir, report,
    )
    if stage == "01-ui-ux.design":
        await register_design_artifacts(conn, run_id, sdir)
    await conn.execute(
        "UPDATE stage_executions SET status = 'succeeded', output = $1, finished_at = now() WHERE id = $2",
        json.dumps({"final_output": tail, "report": report}), exec_id,
    )
    await log_event(conn, run_id, f"agent:{role}", "stage_succeeded", {"stage": stage})


def _read_handoff(run_id: str, sdir: str) -> dict | None:
    handoff = REPO / "workflow" / "runs" / run_id / sdir / "handoff.json"
    if not handoff.exists():
        return None
    try:
        return json.loads(handoff.read_text(encoding="utf-8"))
    except ValueError:
        return None


async def register_design_artifacts(conn, run_id: str, sdir: str) -> None:
    """Auto-register the ui-ux handoff set (PNGs, Paper URL, flow-spec) as artifacts."""
    data = _read_handoff(run_id, sdir)
    if data is None:
        return
    rel = f"workflow/runs/{run_id}/{sdir}"
    rows: list[tuple[str, str, dict | None]] = [(f"{rel}/handoff.json", "design_handoff", None)]
    if data.get("paper_url"):
        rows.append((data["paper_url"], "paper_file", None))
    if (REPO / rel / "flow-spec.md").exists():
        rows.append((f"{rel}/flow-spec.md", "flow_spec", None))
    for opt in data.get("options", []):
        for png in opt.get("pngs", []):
            rows.append((png, "design_png", {"option": opt.get("name"), "status": opt.get("status")}))
    for uri, kind, meta in rows:
        await conn.execute(
            "INSERT INTO artifacts (run_id, stage, kind, uri, metadata) VALUES ($1, $2, $3, $4, $5)",
            run_id, sdir, kind, uri, json.dumps(meta) if meta else None)


def _run_title(run_id: str) -> str:
    brief = REPO / "workflow" / "runs" / run_id / "brief.md"
    if brief.exists():
        for line in brief.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("#"):
                return line.lstrip("# ").strip()
    return ""


async def render_runboard(conn) -> None:
    """Regenerate workflow/RUNBOARD.md from Postgres.

    The runboard is derived data; agents never write it (their write tools reject it).
    Every pipeline state change re-renders it, so the file stays a faithful view for
    humans reading the repo and for agent orientation.
    """
    active = await conn.fetch(
        """SELECT id, status, current_stage, updated_at FROM runs
           WHERE status NOT IN ('done', 'cancelled') ORDER BY updated_at DESC""")
    done = await conn.fetch(
        """SELECT id, completed_at FROM runs
           WHERE status = 'done' AND completed_at > now() - interval '30 days'
           ORDER BY completed_at DESC""")
    pending = {r["run_id"]: r for r in await conn.fetch(
        "SELECT run_id, gate, payload FROM approvals WHERE status = 'pending'")}
    lines = [
        "# Runboard — the live index of runs",
        "",
        "RENDERED from the pipeline database — do not hand-edit. `python pipeline.py runboard`",
        "regenerates it, and every pipeline state change re-renders it automatically. First",
        "thing every agent reads after its role files (orientation step 1 —",
        "`docs/AGENT-TOOLING.md` §5); detail lives in the run folders.",
        "",
        "## Active",
        "",
        "| Run ID | What | Stage | Status | Waiting on | Updated |",
        "|--------|------|-------|--------|------------|---------|",
    ]
    for r in active:
        waiting = ""
        p = pending.get(r["id"])
        if p:
            waiting = f"gate `{p['gate']}`"
            try:
                rec = json.loads(p["payload"] or "{}").get("handoff", {}).get("recommended")
                if rec:
                    waiting += f" (rec: {rec})"
            except ValueError:
                pass
        elif r["status"] == "failed":
            waiting = "rework, then `pipeline.py retry`"
        elif r["status"] == "executing":
            waiting = "stage in progress"
        elif r["status"] == "running":
            waiting = f"runner `{STAGE_RUNNER.get(r['current_stage'], '?')}`"
        lines.append(
            f"| {r['id']} | {_run_title(r['id'])} | {r['current_stage']} | {r['status']} "
            f"| {waiting} | {r['updated_at']:%Y-%m-%d} |")
    if not active:
        lines.append("| — | no active runs | | | | |")
    lines += ["", "## Recently completed (last 30 days)", "",
              "| Run ID | What | Completed |", "|--------|------|-----------|"]
    for r in done:
        lines.append(f"| {r['id']} | {_run_title(r['id'])} | {r['completed_at']:%Y-%m-%d} |")
    if not done:
        lines.append("| — | | |")
    (REPO / "workflow" / "RUNBOARD.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


async def open_gate(conn, run_id: str, stage: str, gate: str) -> None:
    payload: dict = {"stage": stage, "run_folder": f"workflow/runs/{run_id}/"}
    handoff = _read_handoff(run_id, STAGE_DIR[stage])
    if handoff is not None:
        payload["handoff"] = handoff   # Mission Control renders paper_url + PNGs from this
    await conn.execute(
        """INSERT INTO approvals (run_id, gate, channel, payload) VALUES ($1, $2, 'cli', $3)""",
        run_id, gate, json.dumps(payload),
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


async def step_run(conn, run_id: str, runner: str = "ec2") -> None:
    """Execute the current stage of one claimed run, then gate or advance."""
    row = await conn.fetchrow("SELECT current_stage FROM runs WHERE id = $1", run_id)
    stage = row["current_stage"]
    _, _, stype, gate, _ = FEATURE_STAGES[STAGE_INDEX[stage]]
    try:
        if stype == "agent":
            execute = run_agent_stage_docker if EXECUTOR == "docker" else run_agent_stage
            await execute(conn, run_id, stage, runner)
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
    await render_runboard(conn)


async def heartbeat(conn, runner: str) -> None:
    await conn.execute(
        """INSERT INTO runners (name, last_seen) VALUES ($1, now())
           ON CONFLICT (name) DO UPDATE SET last_seen = now()""", runner)


async def claim_run(conn, runner: str) -> str | None:
    """Claim one runnable run whose current stage belongs to this runner.

    The claim marks the run 'executing' — without that, a daemon running N>1 slots
    (or a second tick during a long stage) would claim the same run twice; the old
    single-slot loop was only safe because it executed synchronously. The status
    is overwritten by every completion path (gate/advance/fail); a daemon crash is
    recovered by the startup requeue in cmd_daemon.
    """
    stages = [s for s, r in STAGE_RUNNER.items() if r == runner]
    async with conn.transaction():
        row = await conn.fetchrow(
            """SELECT id FROM runs WHERE status = 'running' AND current_stage = ANY($1::text[])
               ORDER BY updated_at FOR UPDATE SKIP LOCKED LIMIT 1""", stages)
        if not row:
            return None
        await conn.execute(
            "UPDATE runs SET status = 'executing', updated_at = now() WHERE id = $1", row["id"])
        return row["id"]


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
    await render_runboard(conn)
    print(f"run {run_id} created — the pipeline takes it from here.")
    if follow:
        local = os.environ.get("LANTERN_RUNNER", "ec2")
        waiting_on = None
        while True:
            row = await conn.fetchrow("SELECT status, current_stage FROM runs WHERE id = $1", run_id)
            if row["status"] not in ("running", "executing"):
                print(f"[{run_id}] status: {row['status']}")
                break
            if row["status"] == "executing":   # a daemon slot has it — just watch
                await asyncio.sleep(POLL_SECONDS)
                continue
            needed = STAGE_RUNNER[row["current_stage"]]
            if needed != local:
                if waiting_on != row["current_stage"]:
                    print(f"[{run_id}] {row['current_stage']} needs the '{needed}' runner — waiting for its daemon.")
                    waiting_on = row["current_stage"]
                await asyncio.sleep(POLL_SECONDS)
                continue
            claimed = await conn.execute(
                "UPDATE runs SET status = 'executing', updated_at = now() WHERE id = $1 AND status = 'running'",
                run_id)
            if claimed.endswith(" 0"):         # a daemon won the race — watch instead
                continue
            await step_run(conn, run_id, local)
    await conn.close()


async def cmd_daemon(runner: str) -> None:
    conn = await connect()
    if runner == "workstation" and not await paper_reachable():
        sys.exit(PAPER_PREFLIGHT_HINT)  # fail fast at startup, never mid-run
    # Crashed-daemon recovery: with one daemon per runner, any of OUR stages still
    # marked 'executing' at startup is an orphan from a dead process — requeue it.
    my_stages = [s for s, r in STAGE_RUNNER.items() if r == runner]
    await conn.execute(
        """UPDATE runs SET status = 'running', updated_at = now()
           WHERE status = 'executing' AND current_stage = ANY($1::text[])""", my_stages)
    print(f"lantern orchestrator daemon [{runner}] executor={EXECUTOR} "
          f"concurrency={MAX_CONCURRENCY} — polling every {POLL_SECONDS}s")

    async def heartbeat_loop() -> None:
        # Own connection: keeps beating while stages run, so Mission Control never
        # shows a busy runner as offline.
        hb_conn = await connect()
        while True:
            await heartbeat(hb_conn, runner)
            await asyncio.sleep(POLL_SECONDS)

    async def execute(run_id: str) -> None:
        # Own connection per slot — one asyncpg connection cannot serve concurrent
        # executions.
        c = await connect()
        try:
            await step_run(c, run_id, runner)
        except Exception as e:  # noqa: BLE001 — a dead slot must not kill the daemon
            print(f"[{run_id}] executor slot crashed: {e}", file=sys.stderr)
        finally:
            await c.close()

    hb_task = asyncio.create_task(heartbeat_loop())
    slots: set[asyncio.Task] = set()
    paper_ok = True
    try:
        while True:
            slots = {t for t in slots if not t.done()}
            if runner == "workstation":
                ok = await paper_reachable()
                if not ok and paper_ok:
                    print(PAPER_PREFLIGHT_HINT, file=sys.stderr)
                paper_ok = ok
                if not ok:           # hold claims until Paper is back — no mid-run failures
                    await asyncio.sleep(POLL_SECONDS)
                    continue
            if len(slots) < MAX_CONCURRENCY:
                run_id = await claim_run(conn, runner)
                if run_id:
                    slots.add(asyncio.create_task(execute(run_id)))
                    continue         # fill remaining slots before sleeping
            await asyncio.sleep(POLL_SECONDS)
    finally:
        hb_task.cancel()


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
    await render_runboard(conn)
    await conn.close()


async def cmd_retry(run_id: str) -> None:
    conn = await connect()
    await conn.execute("UPDATE runs SET status = 'running', updated_at = now() WHERE id = $1", run_id)
    await log_event(conn, run_id, "human:cli", "run_retried", {})
    await render_runboard(conn)
    print(f"[{run_id}] re-queued at its current stage (fresh attempt, same session memory).")
    await conn.close()


async def cmd_agents() -> None:
    print("Consultable agents (python pipeline.py ask <role> \"<prompt>\"):\n")
    for name, desc in consult_roles().items():
        print(f"  {name:<14} {desc}")


async def cmd_ask(role: str, prompt: str, session_name: str, by: str,
                  new: bool, interactive: bool, no_browser: bool) -> None:
    """Direct consult of one agent, outside any pipeline run.

    Advisory and read-only by design: the agent gets the role's knowledge, repo read
    tools, and append_memory — no write tools. Conversation persists per
    {developer}:{role}:{session}, so follow-up prompts continue where you left off
    (or use -i for a live back-and-forth in one command).
    """
    roles = consult_roles()
    if role not in roles:
        sys.exit(f"unknown role: {role}\navailable: {', '.join(roles)}")
    conn = await connect()
    await render_role_memory(conn, role)   # the prompt embeds memory — render it fresh

    session_id = f"consult:{by}:{role}:{session_name}"
    session = SQLAlchemySession.from_url(session_id, url=db_urls()[0], create_tables=True)
    if new:
        await session.clear_session()

    mcp_servers = []
    if role in BROWSER_ROLES and not no_browser:
        mcp_servers.append(playwright_mcp_server())
    for s in mcp_servers:
        await s.connect()
    try:
        agent = Agent(
            name=role,
            model=model_for(role),
            instructions=build_consult_instructions(role),
            tools=[read_file, list_dir,
                   make_append_memory(role, None, None, session_id)],
            mcp_servers=mcp_servers,
        )

        async def turn(text: str) -> None:
            result = await Runner.run(agent, input=text, session=session, max_turns=40)
            print(f"\n[{role} · {model_for(role)}]\n{result.final_output}\n")
            await log_event(conn, None, f"human:{by}", "consult",
                            {"role": role, "session": session_name, "prompt": text[:300]})

        await turn(prompt)
        while interactive:
            text = (await asyncio.to_thread(input, f"you -> {role} (empty line ends) > ")).strip()
            if not text or text.lower() in ("exit", "quit"):
                break
            await turn(text)
    finally:
        for s in mcp_servers:
            await s.cleanup()
    await conn.close()


async def cmd_runboard() -> None:
    conn = await connect()
    await render_runboard(conn)
    await conn.close()
    print("rendered workflow/RUNBOARD.md from the database")


async def cmd_render_memory(role: str | None) -> None:
    conn = await connect()
    roles = [role] if role else sorted(
        d.name for d in (REPO / "agents").iterdir()
        if d.is_dir() and not d.name.startswith("_") and (d / "memory.md").exists())
    for r in roles:
        await render_role_memory(conn, r)
        print(f"rendered agents/{r}/memory.md")
    await conn.close()


async def cmd_import_run(run_id: str, by: str, stage: str, status: str, gate: str | None) -> None:
    """Bring a file-era run folder under database management (one-time backfill).

    Once RUNBOARD.md is rendered from Postgres, any run that exists only as files
    would vanish from the board — importing gives it a runs row (and optionally its
    pending gate, with the payload built from handoff.json like a live run's).
    """
    run_dir = REPO / "workflow" / "runs" / run_id
    if not run_dir.is_dir():
        sys.exit(f"no run folder: workflow/runs/{run_id}")
    if stage not in STAGE_INDEX:
        sys.exit(f"unknown stage: {stage} (expected one of {', '.join(STAGE_INDEX)})")
    conn = await connect()
    inserted = await conn.fetchval(
        """INSERT INTO runs (id, brief, pipeline_version, status, current_stage, created_by)
           VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (id) DO NOTHING RETURNING id""",
        run_id, f"workflow/runs/{run_id}/brief.md", PIPELINE_VERSION, status, stage, by)
    if not inserted:
        sys.exit(f"{run_id} already exists in the database — nothing imported")
    await log_event(conn, run_id, f"human:{by}", "run_imported", {"stage": stage, "status": status})
    if gate:
        await open_gate(conn, run_id, stage, gate)  # sets waiting_gate + payload from handoff.json
    await render_runboard(conn)
    await conn.close()
    print(f"imported {run_id} at {stage} ({status}{', gate ' + gate if gate else ''})")


async def cmd_status() -> None:
    conn = await connect()
    runs = await conn.fetch(
        """SELECT id, status, current_stage, updated_at FROM runs
           WHERE status NOT IN ('done', 'cancelled') ORDER BY updated_at DESC""")
    if not runs:
        print("no active runs")
    for r in runs:
        print(f"{r['id']:<40} {r['status']:<13} {r['current_stage']:<18} updated {r['updated_at']:%Y-%m-%d %H:%M}")
    pend = await conn.fetch("SELECT run_id, gate, requested_at FROM approvals WHERE status = 'pending'")
    for p in pend:
        # plain ASCII: Windows consoles default to cp1252 and choke on emoji/arrows
        print(f"  pending gate: {p['run_id']} -> {p['gate']} (since {p['requested_at']:%Y-%m-%d %H:%M})")
    await conn.close()


def main() -> None:
    set_default_openai_client(azure_v1_client())
    # Responses API — chat_completions drops image tool outputs, blinding vision
    # critique loops (see orchestrator.py for the full note).
    set_default_openai_api(os.environ.get("LANTERN_OPENAI_API", "responses"))
    set_tracing_disabled(True)  # no OpenAI-platform key on the Azure credential set

    ap = argparse.ArgumentParser(prog="lantern")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db")
    p = sub.add_parser("run"); p.add_argument("brief"); p.add_argument("--run-id")
    p.add_argument("--by", default=os.environ.get("USERNAME") or os.environ.get("USER", "unknown"))
    p.add_argument("--follow", action="store_true")
    p = sub.add_parser("daemon")
    p.add_argument("--runner", choices=["ec2", "workstation"],
                   default=os.environ.get("LANTERN_RUNNER", "ec2"))
    for name in ("approve", "reject"):
        p = sub.add_parser(name); p.add_argument("run_id"); p.add_argument("gate")
        p.add_argument("--by", required=True); p.add_argument("--note", default="")
    p = sub.add_parser("retry"); p.add_argument("run_id")
    sub.add_parser("status")
    sub.add_parser("agents")
    p = sub.add_parser("ask"); p.add_argument("role"); p.add_argument("prompt")
    p.add_argument("--session", default="default",
                   help="named conversation; follow-up asks with the same name continue it")
    p.add_argument("--by", default=os.environ.get("USERNAME") or os.environ.get("USER", "unknown"))
    p.add_argument("--new", action="store_true", help="clear this session and start fresh")
    p.add_argument("-i", "--interactive", action="store_true", help="keep prompting in a loop")
    p.add_argument("--no-browser", action="store_true", help="skip the Playwright MCP for browser roles")
    sub.add_parser("runboard")
    p = sub.add_parser("render-memory"); p.add_argument("--role")
    p = sub.add_parser("import-run"); p.add_argument("run_id")
    p.add_argument("--by", default="justin"); p.add_argument("--stage", default="01-ui-ux.design")
    p.add_argument("--status", default="waiting_gate"); p.add_argument("--gate")
    a = ap.parse_args()

    match a.cmd:
        case "init-db": asyncio.run(cmd_init_db())
        case "run":     asyncio.run(cmd_run(a.brief, a.run_id, a.by, a.follow))
        case "daemon":  asyncio.run(cmd_daemon(a.runner))
        case "approve": asyncio.run(cmd_decide(a.run_id, a.gate, a.by, a.note, True))
        case "reject":  asyncio.run(cmd_decide(a.run_id, a.gate, a.by, a.note, False))
        case "retry":   asyncio.run(cmd_retry(a.run_id))
        case "status":  asyncio.run(cmd_status())
        case "agents":  asyncio.run(cmd_agents())
        case "ask":     asyncio.run(cmd_ask(a.role, a.prompt, a.session, a.by,
                                            a.new, a.interactive, a.no_browser))
        case "runboard":      asyncio.run(cmd_runboard())
        case "render-memory": asyncio.run(cmd_render_memory(a.role))
        case "import-run":    asyncio.run(cmd_import_run(a.run_id, a.by, a.stage, a.status, a.gate))


if __name__ == "__main__":
    main()
