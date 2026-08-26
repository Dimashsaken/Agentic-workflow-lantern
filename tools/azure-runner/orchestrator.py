"""Lantern stage orchestrator — runs ONE pipeline stage with an Azure OpenAI brain.

    python orchestrator.py <run-id> <stage-dir>
    python orchestrator.py feat-20260824-bulk-export 04-qa-dev

Deterministic pipeline control lives here; the model only has autonomy inside a
stage. After the run, the two written AGENTS.md postconditions are enforced
mechanically — a stage that skipped one fails loudly. Requires Postgres
(LANTERN_DATABASE_URL): role memory is a role_memory table and memory.md files are
rendered views of it, so the postcondition is sound under concurrent runs.
"""

import argparse
import asyncio
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import asyncpg
from dotenv import load_dotenv
from openai import AsyncOpenAI
from agents import (Agent, Runner, function_tool, set_default_openai_api,
                    set_default_openai_client, set_tracing_disabled)
from agents.mcp import MCPServerStdio, MCPServerStreamableHttp

REPO = Path(__file__).resolve().parents[2]
PROCESS_START = datetime.now(timezone.utc).timestamp()  # stale-export guard
load_dotenv(Path(__file__).parent / ".env")


def db_urls() -> tuple[str, str]:
    """(sqlalchemy_url, asyncpg_url) for LANTERN_DATABASE_URL."""
    url = os.environ.get(
        "LANTERN_DATABASE_URL",
        "postgresql+asyncpg://lantern:lantern@localhost:5432/lantern",
    )
    sqlalchemy_url = url if "+asyncpg" in url else url.replace("postgresql://", "postgresql+asyncpg://")
    return sqlalchemy_url, sqlalchemy_url.replace("+asyncpg", "")


DB_REQUIRED_HINT = (
    "Postgres is required: role memory lives in the role_memory table (the memory.md "
    "files are rendered views). Set LANTERN_DATABASE_URL, run `python pipeline.py "
    "init-db` once, and see tools/azure-runner/README.md for the local-dev setup.")


async def db_connect() -> asyncpg.Connection:
    try:
        conn = await asyncpg.connect(db_urls()[1])
        await conn.fetchval("SELECT 1 FROM role_memory LIMIT 1")
        return conn
    except asyncpg.UndefinedTableError:
        sys.exit(f"role_memory table missing — {DB_REQUIRED_HINT}")
    except OSError as e:
        sys.exit(f"cannot reach Postgres ({e}) — {DB_REQUIRED_HINT}")


def azure_v1_client() -> AsyncOpenAI:
    """Client for Azure OpenAI's v1 API surface (endpoint ends in /openai/v1)."""
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
    if not endpoint.endswith("/openai/v1"):
        endpoint += "/openai/v1"
    return AsyncOpenAI(base_url=endpoint, api_key=os.environ["AZURE_OPENAI_API_KEY"])

ROLE_FOR_STAGE = {
    "01-ui-ux": "ui-ux",            # manual whole-stage run (Phase-1 workstation sessions)
    "01-ui-ux.diverge": "ui-ux",    # pipeline: divergence phase (EC2, fast model)
    "01-ui-ux.design": "ui-ux",     # pipeline: Paper convergence phase (workstation)
    "02-pre-coding": "pre-coding",
    "04-qa-dev": "qa-dev",
    "05-post-coding": "post-coding",
    "06-security": "security",
    "07-qa-staging": "qa-staging",
    # debug lifecycle stages all map to the debug role:
    "01-triage": "debug", "02-repro": "debug", "03-root-cause": "debug",
    "04-fix": "debug", "05-regression": "qa-dev", "06-postmortem": "debug",
}

# Roles that drive a browser get the Playwright MCP server.
BROWSER_ROLES = {"ui-ux", "qa-dev", "qa-staging", "debug"}

# Stage executions that get the Paper MCP server (desktop-bound — workstation only).
PAPER_STAGES = {"01-ui-ux", "01-ui-ux.design"}

# Deployment routing: strong model for judgement-heavy roles, fast one for execution.
FAST_ROLES = {"qa-dev", "qa-staging"}
FAST_STAGES = {"01-ui-ux.diverge"}  # divergence is volume work, not judgement


def stage_dir(stage: str) -> str:
    """Run-folder directory for a stage key ('01-ui-ux.diverge' → '01-ui-ux')."""
    return stage.split(".", 1)[0]


def model_for(role: str, stage: str | None = None) -> str:
    fast = role in FAST_ROLES or stage in FAST_STAGES
    var = "LANTERN_MODEL_FAST" if fast else "LANTERN_MODEL_REASONING"
    deployment = os.environ.get(var)
    if not deployment:
        sys.exit(f"Missing env var {var} (Azure deployment name, e.g. sol/terra)")
    return deployment


def paper_mcp_url() -> str:
    return os.environ.get("LANTERN_PAPER_MCP_URL", "http://127.0.0.1:29979/mcp")


async def paper_reachable(timeout: float = 2.0) -> bool:
    """Preflight: is Paper Desktop's MCP port answering on this machine?"""
    from urllib.parse import urlparse
    u = urlparse(paper_mcp_url())
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(u.hostname, u.port or 80), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except (OSError, asyncio.TimeoutError):
        return False


def paper_mcp_server() -> MCPServerStreamableHttp:
    return MCPServerStreamableHttp(params={"url": paper_mcp_url()}, name="paper")


PAPER_PREFLIGHT_HINT = ("Paper MCP is not reachable — open Paper Desktop on the design "
                        "workstation with the Lantern team file, then retry.")

# Phase-specific assignment notes for the split stage-1 executions.
PHASE_NOTES = {
    "01-ui-ux.diverge": (
        "\n\n# Phase note\nThis execution is ONLY the divergence phase (skills §3A): "
        "generate the low-fi skeletons in the stage directory's divergence/ folder, run "
        "the judge pass, record scores and survivors in report.md. You have NO Paper "
        "access here — do not attempt Paper work; the design workstation picks up next."),
    "01-ui-ux.design": (
        "\n\n# Phase note\nThis execution is the Paper convergence phase (skills §3B–3D): "
        "divergence output and scores already exist in the stage directory — read them, "
        "do not redo them. You have the `paper` MCP server. Finish by writing "
        "handoff.json (skills §3D) — the gate payload is built from it."),
}


def paper_file_note() -> str:
    """Tell the agent which Paper file is agent-owned (mounted; page-per-run works)."""
    fid = os.environ.get("LANTERN_PAPER_FILE_ID")
    if not fid:
        return ("\n\nNo LANTERN_PAPER_FILE_ID is configured. You may not create a Paper file "
                "unattended (a new file cannot mount without a human opening it): write your "
                "report with Status: BLOCKED asking for the agent-owned file to be created and "
                "opened once — and still satisfy all three postconditions.")
    return (f"\n\n# Your Paper workspace\nThe agent-owned Paper file is `{fid}` — already open in "
            "the Desktop app. Work ONLY there: `create_page` named after the run ID, then "
            "`open_file` with that fileId AND pageId (page switches inside the open file mount "
            "correctly), then create your artboards. Pass `fileId` on every single call. Never "
            "create a new file and never write into any other file — human files are read-only "
            "references you may `get_tokens`/`get_screenshot` for grounding.")


def build_instructions(role: str, run_id: str, stage: str) -> str:
    parts = [
        (REPO / "AGENTS.md").read_text(encoding="utf-8"),
        f"\n\n# Your assignment\nYou are the **{role}** agent. Run ID: `{run_id}`. "
        f"Stage directory: `workflow/runs/{run_id}/{stage_dir(stage)}/`.\n"
        "Follow your charter and skills exactly. Before finishing you MUST: "
        "(1) write the stage report, (2) record at least one durable learning with the "
        "`append_memory` tool (an explicit 'nothing durable learned this run' note also "
        "counts). Both are verified mechanically. Do NOT edit memory.md or "
        "workflow/RUNBOARD.md directly — memory.md is rendered from the database "
        "(append_memory is the only write path) and the runboard renders itself. "
        "This applies EVEN IF you end BLOCKED: a blocked stage still writes its report "
        "(Status: BLOCKED, one precise question) and still records memory. "
        "Blocking is not an exit from the contract.\n\n"
        "# How to run your turn\n"
        "You are running headless: there is no human to read a plan and no one to reply to "
        "you mid-stage. Your reply text is a return value, not a message. NEVER end a turn "
        "with an announcement of what you are about to do ('I'm beginning orientation…', "
        "'Next I will…') — a reply with no tool call ENDS THE STAGE IMMEDIATELY and the run "
        "fails with nothing written. Act first: call tools, write files, then reply only "
        "once the three postconditions are already on disk. Work continuously until done.",
    ]
    parts.append(PHASE_NOTES.get(stage, ""))
    if stage in PAPER_STAGES:
        parts.append(paper_file_note())
    for name in ("charter.md", "skills.md", "memory.md"):
        f = REPO / "agents" / role / name
        parts.append(f"\n\n# {role}/{name}\n" + f.read_text(encoding="utf-8"))
    return "".join(parts)


def _safe(rel: str) -> Path:
    p = (REPO / rel).resolve()
    if not p.is_relative_to(REPO):
        raise ValueError(f"path escapes repo: {rel}")
    return p


def _writable(rel: str) -> Path:
    """Like _safe, but rejects files that are rendered views of Postgres.

    Under concurrency these files are shared between runs; a direct write both races
    other runs and is silently discarded on the next render — so it is an error, not
    a convenience.
    """
    p = _safe(rel)
    rp = p.relative_to(REPO).as_posix()
    if rp == "workflow/RUNBOARD.md":
        raise ValueError(
            "RUNBOARD.md is rendered from the pipeline database — agents never write it; "
            "it updates automatically when your stage finishes")
    if rp.startswith("agents/") and rp.endswith("/memory.md"):
        raise ValueError(
            "memory.md is rendered from the role_memory table — record learnings with "
            "the append_memory tool instead")
    return p


@function_tool
def read_file(path: str) -> str:
    """Read a file. Path is relative to the Lantern repo root."""
    return _safe(path).read_text(encoding="utf-8")


@function_tool
def write_file(path: str, content: str) -> str:
    """Create or overwrite a file. Path is relative to the Lantern repo root."""
    p = _writable(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"wrote {path}"


@function_tool
def append_file(path: str, content: str) -> str:
    """Append to a file (reports, logs). Path relative to repo root."""
    with _writable(path).open("a", encoding="utf-8") as f:
        f.write(content)
    return f"appended to {path}"


# ── role memory: Postgres is the source of truth, memory.md is a rendered view ──

MEMORY_MARKER = ("<!-- ENTRIES BELOW ARE RENDERED FROM THE role_memory TABLE — do not "
                 "edit here; agents use append_memory, humans consolidate upward and "
                 "re-run `pipeline.py render-memory` -->")


async def render_role_memory(conn: asyncpg.Connection, role: str) -> None:
    """Regenerate agents/<role>/memory.md: human-consolidated base + unconsolidated rows."""
    f = REPO / "agents" / role / "memory.md"
    base = f.read_text(encoding="utf-8").split(MEMORY_MARKER)[0].rstrip() if f.exists() else f"# {role} — memory\n"
    rows = await conn.fetch(
        """SELECT run_id, stage, entry, created_at FROM role_memory
           WHERE role = $1 AND NOT consolidated ORDER BY created_at""", role)
    lines = [base, "", MEMORY_MARKER, ""]
    for r in rows:
        origin = r["run_id"] or "manual"
        entry = "\n  ".join(r["entry"].strip().splitlines())
        lines.append(f"- {r['created_at']:%Y-%m-%d} [{origin} · {r['stage'] or '-'}] {entry}")
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_append_memory(role: str, run_id: str, stage: str, execution_key: str):
    """Build the append_memory tool bound to this stage execution's identity.

    The binding is what makes the memory postcondition sound under concurrency: the
    check asks for a row with THIS execution_key, which no other run can insert.
    """
    @function_tool
    async def append_memory(entry: str) -> str:
        """Record ONE durable learning in your role memory — the only write path to it.

        Make it dated-quality judgement: concrete, with the why ("Modal flows on mobile
        Safari need X because Y"), never a session log. If the run taught you nothing
        durable, record exactly that ("nothing durable learned this run: <one line why>")
        — required before finishing either way. Call once per distinct learning.
        """
        conn = await asyncpg.connect(db_urls()[1])
        try:
            await conn.execute(
                """INSERT INTO role_memory (role, run_id, stage, execution_key, entry)
                   VALUES ($1, $2, $3, $4, $5)""",
                role, run_id, stage, execution_key, entry.strip())
            await render_role_memory(conn, role)
        finally:
            await conn.close()
        return "memory entry recorded"
    return append_memory


@function_tool
def list_dir(path: str) -> str:
    """List a directory. Path is relative to the Lantern repo root."""
    return "\n".join(sorted(x.name + ("/" if x.is_dir() else "") for x in _safe(path).iterdir()))


def export_dir() -> Path:
    """Where design/QA tools drop exported files (Paper writes PNG/MP4 here)."""
    return Path(os.environ.get("LANTERN_EXPORT_DIR", Path.home() / "Downloads"))


@function_tool
def list_exports() -> str:
    """List files waiting in the export folder (where Paper's `export` writes PNGs/MP4s).

    Newest first, with size and age. Use this after exporting to find the real filenames.
    """
    d = export_dir()
    if not d.is_dir():
        return f"export folder {d} does not exist"
    files = sorted((f for f in d.iterdir() if f.is_file()),
                   key=lambda f: f.stat().st_mtime, reverse=True)[:40]
    now = datetime.now(timezone.utc).timestamp()
    return "\n".join(
        f"{f.name}\t{f.stat().st_size // 1024} KB\t{int((now - f.stat().st_mtime) // 60)} min ago"
        for f in files) or "export folder is empty"


@function_tool
def collect_export(filename: str, dest_path: str) -> str:
    """Move an exported binary (PNG/MP4/PDF) from the export folder into the run folder.

    Text tools cannot carry binaries, so this is the ONLY way to turn a Paper `export`
    into a run artifact. `filename` is the name as it appears in the export folder
    (see list_exports); `dest_path` is repo-relative, e.g.
    'workflow/runs/<run-id>/01-ui-ux/verdict@2x.png'. Returns the size actually written.
    """
    src = export_dir() / Path(filename).name          # no traversal out of the export dir
    if not src.is_file():
        raise FileNotFoundError(f"{src.name} not in the export folder — check list_exports()")
    if src.stat().st_mtime < PROCESS_START:
        raise ValueError(
            f"{src.name} predates this stage run — it is a leftover from an earlier run, not "
            "something you exported. Export it again from the artboard you built, then collect it.")
    dst = _safe(dest_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))                   # move, so re-runs never see stale exports
    return f"collected {dst.relative_to(REPO).as_posix()} ({dst.stat().st_size // 1024} KB)"


def check_claimed_artifacts(run_id: str, sdir: str) -> list[str]:
    """Every file a handoff.json claims must actually exist.

    Without this, a stage can pass by *describing* deliverables it never produced —
    observed 2026-08-26: handoff.json listed three option PNGs, none of which were on
    disk, and the stage still passed. Claims are not evidence.
    """
    import json
    handoff = REPO / "workflow/runs" / run_id / sdir / "handoff.json"
    if not handoff.exists():
        return []
    try:
        data = json.loads(handoff.read_text(encoding="utf-8"))
    except ValueError as e:
        return [f"{sdir}/handoff.json is not valid JSON: {e}"]
    problems = []
    for opt in data.get("options", []):
        pngs = opt.get("pngs") or []
        if not pngs:
            problems.append(f"handoff.json option '{opt.get('name')}' claims no PNG")
        for rel in pngs:
            p = REPO / rel
            if not p.is_file():
                problems.append(f"handoff.json claims '{rel}' but no such file exists")
            elif p.stat().st_size == 0:
                problems.append(f"handoff.json claims '{rel}' but the file is empty")
    vid = data.get("video")
    if vid and not str(vid).startswith(("http://", "https://", "s3://")):
        if not (REPO / vid).is_file():
            problems.append(f"handoff.json claims video '{vid}' but no such file exists")
    # Presence AND validity. A validity-only check passes vacuously when the agent
    # simply omits the deliverable — observed 2026-08-26: no jsx/ directory at all.
    jsx_dir = REPO / "workflow/runs" / run_id / sdir / "jsx"
    jsx_files = sorted(jsx_dir.glob("*.jsx")) if jsx_dir.is_dir() else []
    names = [o.get("name", "?") for o in data.get("options", [])]
    if names and not jsx_files:
        problems.append(
            f"no jsx/ output for {len(names)} presented options — the handoff promises "
            "get_jsx structural source per frame; omitting it is not an option")
    elif len(jsx_files) < len(names):
        problems.append(
            f"jsx/ has {len(jsx_files)} files for {len(names)} presented options — one per frame")
    for f in jsx_files:
        body = f.read_text(encoding="utf-8", errors="replace")
        if "<" not in body or len(body) < 400:
            problems.append(
                f"jsx/{f.name} is a pointer stub, not get_jsx output — the handoff promises "
                "structural source the coding agent can read, not a node id")
    # The critique loop must leave evidence, not just a self-reported number.
    if names and not (REPO / "workflow/runs" / run_id / sdir / "critique-log.md").is_file():
        problems.append(
            "critique-log.md missing — per-option layout/style pass findings are the only "
            "evidence the critique loop actually ran (metrics.critique_iterations is a claim)")
    return problems


async def check_postconditions(conn: asyncpg.Connection, role: str, run_id: str,
                               stage: str, execution_key: str) -> list[str]:
    """The two written postconditions: stage report on disk, memory row from THIS execution.

    The memory check queries by execution_key, not by diffing memory.md — the file diff
    was unsound under concurrency (another run's append to the same role's file satisfied
    it, so a stage that wrote nothing passed). Proven by test_verification.py.
    """
    missing = []
    sdir = stage_dir(stage)
    if not (REPO / "workflow/runs" / run_id / sdir / "report.md").exists():
        missing.append(f"stage report workflow/runs/{run_id}/{sdir}/report.md not written")
    missing.extend(check_claimed_artifacts(run_id, sdir))
    n = await conn.fetchval("SELECT count(*) FROM role_memory WHERE execution_key = $1", execution_key)
    if not n:
        missing.append(
            f"no role_memory row from this execution — the agent never called append_memory "
            "(an explicit 'nothing durable learned' entry also counts)")
    return missing


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("stage")
    args = ap.parse_args()

    role = ROLE_FOR_STAGE.get(args.stage) or sys.exit(f"unknown stage: {args.stage}")

    set_default_openai_client(azure_v1_client())
    # The v1 surface supports the Responses API; flip here if a deployment lacks it.
    # Responses API, not chat_completions: the chat surface silently DROPS image tool
    # outputs ("tool outputs cannot be empty or contain only non-text content" →
    # replaced with a placeholder), which makes get_screenshot return nothing and the
    # vision critique loop a no-op. Verified 2026-08-26 that the deployments support it.
    set_default_openai_api(os.environ.get("LANTERN_OPENAI_API", "responses"))
    set_tracing_disabled(True)  # no OpenAI-platform key on the Azure credential set

    conn = await db_connect()
    execution_key = f"manual:{args.run_id}:{args.stage}:{uuid4().hex[:8]}"
    await render_role_memory(conn, role)   # instructions must read a fresh view

    mcp_servers = []
    if role in BROWSER_ROLES:
        mcp_servers.append(MCPServerStdio(
            params={"command": "npx", "args": ["-y", "@playwright/mcp@latest"]},
            name="playwright",
        ))
    if args.stage in PAPER_STAGES:
        if not await paper_reachable():
            sys.exit(PAPER_PREFLIGHT_HINT)
        mcp_servers.append(paper_mcp_server())

    for s in mcp_servers:
        await s.connect()
    try:
        agent = Agent(
            name=role,
            model=model_for(role, args.stage),
            instructions=build_instructions(role, args.run_id, args.stage),
            tools=[read_file, write_file, append_file, list_dir, list_exports, collect_export,
                   make_append_memory(role, args.run_id, args.stage, execution_key)],
            mcp_servers=mcp_servers,
        )
        result = await Runner.run(
            agent,
            input=f"Begin your {args.stage} session for run {args.run_id}. Do not reply with a "
                  "plan — start calling tools now and keep working until the report is on "
                  "disk and append_memory has been called.",
            max_turns=120,
        )
        print(result.final_output)
        calls = sum(1 for i in result.new_items if type(i).__name__ == "ToolCallItem")
        if calls == 0:
            print("\nDIAGNOSIS: the agent ended its turn without calling a single tool — the "
                  "stage stopped before doing any work. Re-run it (see 'How to run your turn' "
                  "in the system prompt).", file=sys.stderr)
    finally:
        for s in mcp_servers:
            await s.cleanup()

    missing = await check_postconditions(conn, role, args.run_id, args.stage, execution_key)
    await conn.close()
    if missing:
        print("POSTCONDITIONS FAILED:\n- " + "\n- ".join(missing), file=sys.stderr)
        sys.exit(1)
    print("postconditions ok")


if __name__ == "__main__":
    asyncio.run(main())
