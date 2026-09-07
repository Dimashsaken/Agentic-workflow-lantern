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
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
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


def product_root() -> Path:
    """Where the product repo is checked out for this stage.

    In a sandbox the entrypoint clones it to /work/product from the read-only mirror
    mount; in-process the dispatcher sets LANTERN_PRODUCT_DIR to a host checkout.
    Read at call time, not import time, so both executors work in one process.
    """
    return Path(os.environ.get("LANTERN_PRODUCT_DIR", "/work/product"))

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
    "03-coding": "coding",          # only executed when runs.coding_mode = 'auto' (D14)
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

# QA roles must leave video evidence (P0.1). Derived from ROLE_FOR_STAGE so the
# debug lifecycle's 05-regression is covered by the same rule automatically —
# a parallel stage-key set would silently drift when stages are added/renamed.
QA_VIDEO_ROLES = {"qa-dev", "qa-staging"}


def is_qa_video_stage(stage: str) -> bool:
    return ROLE_FOR_STAGE.get(stage) in QA_VIDEO_ROLES

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


# Env keys the MCP child process needs. MCPServerStdio spawns children with the MCP
# SDK's MINIMAL default environment (PATH/HOME and little else), which silently strips
# PLAYWRIGHT_BROWSERS_PATH — the browser install would be invisible to the very server
# that needs it. So the child env is built explicitly: platform basics + PLAYWRIGHT*.
_MCP_CHILD_ENV_BASE = (
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "TERM", "TMPDIR", "DISPLAY",
    # Windows (laptop runs): node/npx need these to start at all
    "SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC", "PATHEXT", "APPDATA", "LOCALAPPDATA",
    "TEMP", "TMP", "USERPROFILE", "PROGRAMFILES",
)


def playwright_mcp_server(run_id: str | None = None, stage: str | None = None) -> MCPServerStdio:
    """The Playwright MCP server process for browser roles.

    LANTERN_PLAYWRIGHT_MCP overrides the launch command — the sandbox image sets it
    to its preinstalled, version-locked binary so containers never download at stage
    start; the npx default is for laptops/EC2-direct where a fetch is acceptable.

    For QA stages (when run_id+stage are given) the MCP is launched with a config
    that records video into the run's media dir, so every browser session leaves
    evidence the video postcondition can verify. Done here, not in the dispatcher,
    so the SAME behavior holds in-process, in sandboxes, and in manual runs.

    Recording is configured through `browser.contextOptions.recordVideo` — the raw
    Playwright context option. The MCP's own top-level `saveVideo` key is accepted
    but INERT (verified 2026-08-26 against @playwright/mcp 0.0.79); this passthrough
    is what actually produces .webm files. `infra/sandbox/prove_video.sh` is the
    regression check for that behavior after any MCP bump.
    """
    import shlex
    cmd = shlex.split(os.environ.get(
        "LANTERN_PLAYWRIGHT_MCP", "npx -y @playwright/mcp@latest"))
    if run_id and stage and is_qa_video_stage(stage):
        media_dir = REPO / "workflow" / "runs" / run_id / stage_dir(stage) / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        cfg = json.loads((REPO / "infra" / "sandbox" / "qa-mcp-config.json")
                         .read_text(encoding="utf-8"))
        cfg.pop("_comment", None)
        ctx = cfg.setdefault("browser", {}).setdefault("contextOptions", {})
        ctx.setdefault("recordVideo", {})["dir"] = str(media_dir)
        fd, cfg_path = tempfile.mkstemp(prefix="lantern-mcp-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        cmd += ["--config", cfg_path, "--output-dir", str(media_dir)]
    env = {k: os.environ[k] for k in _MCP_CHILD_ENV_BASE if k in os.environ}
    env.update({k: v for k, v in os.environ.items() if k.startswith("PLAYWRIGHT")})
    return MCPServerStdio(params={"command": cmd[0], "args": cmd[1:], "env": env},
                          name="playwright")


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
        "do not redo them. You have the `paper` MCP server. Collect each presented "
        "option's JSX with the `collect_jsx` tool — the host writes get_jsx output "
        "verbatim; JSX copied through your own context is rejected. Finish by writing "
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
    parts.append(product_note())
    parts.append(PHASE_NOTES.get(stage, ""))
    if stage in PAPER_STAGES:
        parts.append(paper_file_note())
    for name in ("charter.md", "skills.md", "memory.md"):
        f = REPO / "agents" / role / name
        parts.append(f"\n\n# {role}/{name}\n" + f.read_text(encoding="utf-8"))
    return "".join(parts)


def consult_roles() -> dict[str, str]:
    """Every consultable role (agents/<role>/ with a charter) -> one-line description."""
    out: dict[str, str] = {}
    for d in sorted((REPO / "agents").iterdir()):
        charter = d / "charter.md"
        if d.is_dir() and not d.name.startswith("_") and charter.exists():
            desc = ""
            for line in charter.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if s and not s.startswith("#"):
                    desc = s
                    break
            out[d.name] = desc
    return out


def build_consult_instructions(role: str) -> str:
    """System prompt for consult mode: the role's knowledge, none of the stage contract."""
    parts = [
        f"# Consult mode\nYou are the **{role}** agent of the Lantern fleet, consulted "
        "directly by a developer OUTSIDE any pipeline run. There is no run folder, no "
        "stage report, and no postconditions — your final message IS the deliverable, "
        "so answer directly and concretely, sized to the question.\n\n"
        "- Ground yourself in the repo before answering anything you are not sure of: "
        "read_file/list_dir any file (workflow/RUNBOARD.md and workflow/runs/ hold the "
        "live pipeline state; the product work lives in the run folders).\n"
        "- Consult mode is advisory and read-only: you have no file-write tools. Work "
        "that changes the product or a run goes through a pipeline run instead — say so "
        "if the developer asks for it, and describe exactly what the run should do.\n"
        "- If the conversation surfaces a durable, role-level learning, record it with "
        "append_memory — optional here, never required.\n"
        "- The developer may follow up; earlier turns of this consult persist.",
    ]
    for name in ("charter.md", "skills.md", "memory.md"):
        f = REPO / "agents" / role / name
        if f.exists():
            parts.append(f"\n\n# {role}/{name}\n" + f.read_text(encoding="utf-8"))
    return "".join(parts)


def _safe(rel: str) -> Path:
    p = (REPO / rel).resolve()
    if not p.is_relative_to(REPO):
        raise ValueError(f"path escapes repo: {rel}")
    return p


def product_wired() -> bool:
    """True when this stage has a product checkout to read."""
    return product_root().is_dir()


def product_writable() -> bool:
    """True only in an auto-coding execution (D14): the dispatcher/entrypoint set
    LANTERN_PRODUCT_WRITABLE=1 for stage 03-coding and nothing else. Every other
    stage keeps the read-only contract test_product_access.py proves."""
    return os.environ.get("LANTERN_PRODUCT_WRITABLE") == "1" and product_wired()


def coding_branch_name() -> str:
    return os.environ.get("LANTERN_CODING_BRANCH", "")


PRODUCT_HINT = (
    "No product repository is wired into this run. Report Status: BLOCKED asking for "
    "the product repo + base branch to be set (`pipeline.py set-product <run-id> "
    "--repo <url> --branch <branch>`), and still satisfy every postcondition.")


def _resolve_read(rel: str) -> Path:
    """Resolve a read path across BOTH roots: the Lantern repo and `product/`.

    `product/...` addresses the read-only product checkout; everything else stays
    relative to the Lantern repo root, so existing skills and paths are unchanged.
    Both branches confine the result to their own root — a `..` escape is an error,
    not a traversal, and the product root can never be reached from the repo one.
    """
    norm = rel.replace("\\", "/").lstrip("/")
    if norm == "product" or norm.startswith("product/"):
        if not product_wired():
            raise FileNotFoundError(PRODUCT_HINT)
        sub = norm[len("product"):].lstrip("/")
        p = (product_root() / sub).resolve() if sub else product_root().resolve()
        if not p.is_relative_to(product_root().resolve()):
            raise ValueError(f"path escapes the product checkout: {rel}")
        return p
    return _safe(rel)


def _writable(rel: str) -> Path:
    """Like _safe, but rejects files that are rendered views of Postgres.

    Under concurrency these files are shared between runs; a direct write both races
    other runs and is silently discarded on the next render — so it is an error, not
    a convenience.
    """
    norm = rel.replace("\\", "/").lstrip("/")
    if norm == "product" or norm.startswith("product/"):
        if product_writable():
            # Auto-coding (D14): the checkout is this execution's working tree on the
            # run's branch. Confined exactly like reads; the harness bundles the
            # committed result into the run folder at the end of the stage.
            sub = norm[len("product"):].lstrip("/")
            if not sub:
                raise ValueError("write a file inside the product tree, not the root")
            p = (product_root() / sub).resolve()
            if not p.is_relative_to(product_root().resolve()):
                raise ValueError(f"path escapes the product checkout: {rel}")
            if ".git/" in (p.relative_to(product_root().resolve()).as_posix() + "/"):
                raise ValueError("never write inside the product's .git directory")
            return p
        raise ValueError(
            "the product checkout is READ-ONLY for fleet stages — it is a throwaway clone "
            "of a mirror and nothing written there survives the container. Product code is "
            "written in stage 3 (coding); your output goes in your run folder.")
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
    if p.name == COLLECTED_MANIFEST:
        raise ValueError(
            f"{COLLECTED_MANIFEST} is written only by collect_jsx — it is the proof that "
            "a jsx file came through the host verbatim, so agents never write it")
    return p


@function_tool
def read_file(path: str) -> str:
    """Read a file. Relative to the Lantern repo root, or `product/...` for product code."""
    return _resolve_read(path).read_text(encoding="utf-8")


@function_tool
def write_file(path: str, content: str) -> str:
    """Create or overwrite a file. Path is relative to the Lantern repo root, or
    `product/...` for product code — accepted ONLY in an auto-coding execution."""
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


# ── product repository: read-only git, no shell ──────────────────────────────
# Orientation (AGENT-TOOLING §5) tells every agent to read the product repo's git
# state, and pre-coding's blast-radius work is `grep broadly` by definition — both
# need git, neither needs a shell. This is git with an allowlist: read-only
# subcommands, no flags that can write a file or execute anything, fixed cwd.
PRODUCT_GIT_ALLOWED = {
    "log", "show", "branch", "diff", "ls-files", "ls-tree", "grep",
    "shortlog", "blame", "tag", "rev-parse", "describe", "status",
}
# `-c`/`--exec-path` inject config and binaries; the rest write files or open
# network paths. Matched exactly and as `--flag=value`.
PRODUCT_GIT_DENY = ("-c", "--exec-path", "--upload-pack", "--receive-pack",
                    "--output", "--git-dir", "--work-tree", "-o", "--ext-diff")
PRODUCT_GIT_MAX = 24000


@function_tool
def product_git(subcommand: str, args: list[str] | None = None) -> str:
    """Run one READ-ONLY git command in the product checkout (no shell).

    This is how you orient in the product repo and how you trace blast radius:

      product_git("log", ["--oneline", "-20"])             recent history on this branch
      product_git("branch", ["-a"])                        branches (yours may exist already)
      product_git("log", ["--all", "--grep", "<run-id>"])  commits already made for this run
      product_git("grep", ["-n", "createCandidate"])       find every consumer
      product_git("ls-files", ["src/"])                    enumerate files

    `git grep` searches tracked files only, which is what you want. Allowed
    subcommands: log, show, branch, diff, ls-files, ls-tree, grep, shortlog, blame,
    tag, rev-parse, describe, status. Output is truncated at ~24k characters — narrow
    the query rather than asking for everything.
    """
    return _product_git(subcommand, args)


def _product_git(subcommand: str, args: list[str] | None = None) -> str:
    """The tool body, callable as a plain function (see test_product_access.py)."""
    if not product_wired():
        raise FileNotFoundError(PRODUCT_HINT)
    if subcommand not in PRODUCT_GIT_ALLOWED:
        raise ValueError(f"'{subcommand}' is not a read-only git subcommand. "
                         f"Allowed: {', '.join(sorted(PRODUCT_GIT_ALLOWED))}")
    argv = [str(a) for a in (args or [])]
    for a in argv:
        if any(a == d or a.startswith(d + "=") for d in PRODUCT_GIT_DENY):
            raise ValueError(f"flag not allowed in the sandboxed product repo: {a}")
    try:
        r = subprocess.run(["git", subcommand, *argv], cwd=product_root(), timeout=120,
                           capture_output=True, text=True, errors="replace")
    except subprocess.TimeoutExpired:
        raise TimeoutError("git command took over 120s — narrow it (add a path or -n limit)")
    out = (r.stdout or "") + (("\n[stderr] " + r.stderr) if r.stderr.strip() else "")
    # A non-zero exit is information (git grep exits 1 on no match), not a failure.
    if len(out) > PRODUCT_GIT_MAX:
        out = out[:PRODUCT_GIT_MAX] + f"\n… truncated at {PRODUCT_GIT_MAX} chars — narrow the query"
    return out.strip() or f"(no output, git exit {r.returncode})"


# ── auto-coding (D14): a writable checkout, a shell, and a bundle handoff ─────
# Stage 03-coding with runs.coding_mode = 'auto' runs the `coding` role like any other
# fleet stage, with two additions: the product checkout is WRITABLE (on the run's
# feat/* branch, created by the entrypoint/dispatcher) and the agent gets a shell in
# it — the same "cd into the repo and work" access a developer's Claude Code or Codex
# session has. The checkout still dies with the container: what survives is the git
# bundle finalize_coding() writes into the run folder, which the HOST verifies, pushes
# as the bot identity and turns into the PR that becomes the code_complete payload.
# The PAT never enters the sandbox; the sandbox never pushes.

PRODUCT_SHELL_MAX = 24000
PRODUCT_SHELL_TIMEOUT = int(os.environ.get("LANTERN_PRODUCT_SHELL_TIMEOUT", "900"))


def _product_shell(command: str, timeout_s: int | None = None) -> str:
    """The tool body, callable as a plain function (test_coding_stage.py)."""
    if not product_writable():
        raise PermissionError(
            "product_shell is available only in an auto-coding execution — this stage's "
            "product checkout is read-only (use product_git and read_file)")
    if not command or not command.strip():
        raise ValueError("empty command")
    timeout = max(5, min(int(timeout_s or PRODUCT_SHELL_TIMEOUT), PRODUCT_SHELL_TIMEOUT))
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("AZURE_", "LANTERN_DATABASE", "GITHUB_", "POSTHOG_"))}
    env.setdefault("HOME", str(Path.home()))
    env["GIT_TERMINAL_PROMPT"] = "0"   # never hang on a credential prompt
    env["CI"] = "1"
    shell = ["bash", "-lc", command]
    if os.name == "nt":
        shell = ["bash", "-c", command]  # Git Bash on a laptop; -l would source profiles
    try:
        r = subprocess.run(shell, cwd=product_root(), timeout=timeout, env=env,
                           capture_output=True, text=True, errors="replace",
                           stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise TimeoutError(
            f"command ran over {timeout}s and was killed — run long tasks in smaller "
            "pieces (a single test file, one package) or raise timeout_s up to "
            f"{PRODUCT_SHELL_TIMEOUT}")
    out = (r.stdout or "")
    if r.stderr.strip():
        out += ("\n[stderr]\n" if out else "[stderr]\n") + r.stderr
    if len(out) > PRODUCT_SHELL_MAX:
        out = out[:PRODUCT_SHELL_MAX // 2] + "\n… [truncated] …\n" + out[-PRODUCT_SHELL_MAX // 2:]
    return f"exit {r.returncode}\n{out}".strip()


@function_tool
def product_shell(command: str, timeout_s: int = 600) -> str:
    """Run ONE shell command inside the product checkout (auto-coding only).

    This is how you work in the codebase the way a developer does at a terminal:

      product_shell("cat AGENTS.md README.md | head -120")     conventions first
      product_shell("ls; git status --short; git log --oneline -5")
      product_shell("npm test -- --runInBand")                  or pytest, go test, …
      product_shell("git add -A && git commit -m '<run-id>: task 2 — add the endpoint'")

    cwd is the product root on your feature branch. Output (stdout+stderr) is
    truncated at ~24k characters — pipe through head/tail/grep rather than dumping
    everything. Commands are killed at timeout_s (default 600s). There is no
    network credential here: `git push` and package publishing will not work and
    are not your job — the harness bundles your COMMITTED branch into the run
    folder when you finish, and the host pushes it and opens the pull request.
    Install dependencies with scripts disabled where the stack allows
    (`npm ci --ignore-scripts`, `pip install -r requirements.txt`).
    """
    return _product_shell(command, timeout_s)


def _git_out(args: list[str], cwd: Path, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, timeout=timeout, capture_output=True,
                          text=True, errors="replace", env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})


CODING_BUNDLE = "branch.bundle"


def finalize_coding(run_id: str, stage: str) -> list[str]:
    """Turn the agent's committed branch into the stage's handoff: a git bundle plus
    handoff.json in the stage dir. Returns problems (empty = the handoff is valid).

    Runs INSIDE the execution (container or in-process) right after the agent's turn,
    because the checkout is gone the moment the container exits — the bundle is the
    only thing that crosses to the host. Uncommitted work is committed by the harness
    rather than lost (flagged in handoff.json); an empty branch is a failed stage.
    """
    problems: list[str] = []
    if not product_writable():
        return ["finalize_coding called without a writable product checkout"]
    root = product_root()
    branch = coding_branch_name()
    base = os.environ.get("LANTERN_PRODUCT_BRANCH", "main")
    if not branch:
        return ["LANTERN_CODING_BRANCH is not set — the dispatcher must name the run's branch"]
    head_name = _git_out(["rev-parse", "--abbrev-ref", "HEAD"], root).stdout.strip()
    if head_name != branch:
        co = _git_out(["checkout", branch], root)
        if co.returncode != 0:
            return [f"checkout is on '{head_name}', not the run's branch '{branch}': "
                    f"{co.stderr.strip()[-300:]}"]
    auto_committed = False
    if _git_out(["status", "--porcelain"], root).stdout.strip():
        _git_out(["add", "-A"], root)
        c = _git_out(["commit", "-q", "-m",
                      f"{run_id}: uncommitted changes at handoff (auto-committed by the harness)\n\n"
                      f"Lantern-Agent: coding"], root)
        auto_committed = c.returncode == 0
        if not auto_committed:
            problems.append(f"could not commit leftover changes: {c.stderr.strip()[-300:]}")
    base_ref = f"refs/remotes/origin/{base}"
    if _git_out(["rev-parse", "--verify", "-q", base_ref], root).returncode != 0:
        base_ref = base   # in-process checkouts may carry the base as a local branch
        if _git_out(["rev-parse", "--verify", "-q", base_ref], root).returncode != 0:
            return [f"base branch '{base}' is not present in the checkout — cannot compute the diff"]
    base_sha = _git_out(["merge-base", base_ref, "HEAD"], root).stdout.strip()
    head_sha = _git_out(["rev-parse", "HEAD"], root).stdout.strip()
    log = _git_out(["log", "--format=%H%x09%s", f"{base_sha}..HEAD"], root).stdout
    commits = [{"sha": ln.split("\t", 1)[0], "subject": ln.split("\t", 1)[1] if "\t" in ln else ""}
               for ln in log.splitlines() if ln.strip()]
    if not commits:
        problems.append(
            "the coding branch has no commits beyond the base — nothing to hand off. "
            "Implement the task plan and commit (one task, one commit).")
        return problems
    sdir = REPO / "workflow" / "runs" / run_id / stage_dir(stage)
    sdir.mkdir(parents=True, exist_ok=True)
    bundle = sdir / CODING_BUNDLE
    if bundle.exists():
        bundle.unlink()
    b = _git_out(["bundle", "create", str(bundle), f"refs/heads/{branch}", f"^{base_sha}"], root)
    if b.returncode != 0 or not bundle.is_file() or bundle.stat().st_size == 0:
        problems.append(f"git bundle create failed: {b.stderr.strip()[-400:]}")
        return problems
    v = _git_out(["bundle", "verify", str(bundle)], root)
    if v.returncode != 0:
        problems.append(f"the bundle does not verify: {v.stderr.strip()[-400:]}")
    diffstat = _git_out(["diff", "--stat", f"{base_sha}..HEAD"], root).stdout.strip()
    handoff = {
        "kind": "coding_branch",
        "run_id": run_id,
        "branch": branch,
        "base": base,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "commits": list(reversed(commits)),      # oldest first, how a reviewer reads them
        "bundle": f"workflow/runs/{run_id}/{stage_dir(stage)}/{CODING_BUNDLE}",
        "auto_committed": auto_committed,
        "diffstat": diffstat[-4000:],
        "files_changed": [ln for ln in _git_out(
            ["diff", "--name-only", f"{base_sha}..HEAD"], root).stdout.splitlines() if ln.strip()],
    }
    (sdir / "handoff.json").write_text(json.dumps(handoff, indent=2), encoding="utf-8")
    return problems


def check_coding_handoff(run_id: str, sdir: str, verify_in: Path | None = None) -> list[str]:
    """Presence AND validity of the coding handoff (the fabrication lesson, applied to
    code): handoff.json must name a feat/* or fix/* branch with ≥1 commit, the bundle
    must exist, be non-empty, verify against a repo that has the base (when one is
    given), and carry exactly that one branch ref — nothing else can ride along."""
    d = REPO / "workflow" / "runs" / run_id / sdir
    hf = d / "handoff.json"
    if not hf.is_file():
        return [f"{sdir}/handoff.json missing — the coding branch was never bundled "
                "(finalize_coding did not run or found no commits)"]
    try:
        h = json.loads(hf.read_text(encoding="utf-8"))
    except ValueError as e:
        return [f"{sdir}/handoff.json is not valid JSON: {e}"]
    problems = []
    branch = str(h.get("branch") or "")
    if not branch.startswith(("feat/", "fix/", "proto/")):
        problems.append(f"handoff branch '{branch}' is not a feat/*, fix/* or proto/* branch")
    if not h.get("commits"):
        problems.append("handoff.json lists no commits")
    bundle = REPO / str(h.get("bundle") or f"workflow/runs/{run_id}/{sdir}/{CODING_BUNDLE}")
    if not bundle.is_file() or bundle.stat().st_size == 0:
        problems.append(f"bundle {bundle.name} missing or empty")
        return problems
    heads = _git_out(["bundle", "list-heads", str(bundle)], REPO).stdout.split()
    refs = [x for x in heads if x.startswith("refs/")]
    if refs != [f"refs/heads/{branch}"]:
        problems.append(f"bundle carries refs {refs} — expected exactly refs/heads/{branch}")
    if verify_in is not None:
        v = _git_out(["bundle", "verify", str(bundle)], verify_in)
        if v.returncode != 0:
            problems.append(f"bundle does not verify against the base: {v.stderr.strip()[-300:]}")
    return problems


def coding_product_note() -> str:
    """System-prompt section for an auto-coding execution — the 'connect to this
    codebase' contract (docs: tools/azure-runner/README.md, Connecting a codebase)."""
    origin = os.environ.get("LANTERN_PRODUCT_ORIGIN", "") or "unknown"
    base = os.environ.get("LANTERN_PRODUCT_BRANCH", "") or "main"
    branch = coding_branch_name() or "(unset)"
    head = ""
    try:
        head = subprocess.run(["git", "log", "-1", "--format=%h %s"], cwd=product_root(),
                              timeout=30, capture_output=True, text=True).stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return (
        "\n\n# The product repository — you are CODING in it\n"
        "This execution is stage 3 in AUTO mode (D14): you implement the approved task "
        "plan yourself. The product checkout under the `product/` prefix is WRITABLE and "
        "already on your feature branch.\n\n"
        f"- **Origin:** `{origin}`\n- **Base branch:** `{base}`\n"
        f"- **Your branch:** `{branch}` (checked out; HEAD at {head or 'unknown'})\n\n"
        "How to work in this codebase — the same way a developer's coding agent would:\n"
        "1. Orient: `product_shell('cat AGENTS.md CLAUDE.md README.md 2>/dev/null | head -200')`, "
        "`product_shell('ls')`, `product_git('log', ['--oneline','-20'])`. The product's own "
        "AGENTS.md/README are authoritative for its conventions, build and test commands; "
        "Lantern's coding skills yield to them.\n"
        "2. Read the approved plan: `workflow/runs/<run-id>/02-pre-coding/task-plan.md` "
        "(and blast-radius.md). Work the tasks IN ORDER. Do not re-decide architecture or "
        "schema; if the plan is wrong, stop and report Status: BLOCKED with the question.\n"
        "3. Edit with `write_file('product/<path>', …)` / `read_file('product/<path>')`; run "
        "builds and tests with `product_shell(...)`. Tests accompany each task.\n"
        "4. Commit per task with `product_shell(\"git add -A && git commit -m '<run-id>: "
        "<task> — <message>'\")`. Author identity and the `Lantern-Agent: coding` trailer "
        "are configured for you. Never push, never touch other branches, never rewrite "
        "history someone else may have read.\n"
        "5. Finish with `03-coding/report.md` (commit list, deviations, the QA confidence "
        "map) and `append_memory`. When you stop, the harness bundles your committed "
        "branch into the run folder; the host pushes it and opens the pull request that a "
        "human approves at the `code_complete` gate. Uncommitted work is auto-committed but "
        "flagged — commit deliberately instead.\n\n"
        "Limits: no network credentials in this sandbox (pushes/publishes fail by design), "
        "no package installs that run arbitrary scripts unless the plan requires them "
        "(prefer `--ignore-scripts`), wall clock is bounded — keep commands short and "
        "output filtered. Every path you cite in the report must be one you opened here.\n"
        "Sandbox facts: Python 3.12 (`python3`), Node 22, git; a Python venv with Lantern's "
        "own dependencies already exists at `/opt/lantern/venv` (use it when the product "
        "IS Lantern; otherwise create one under `/work`). `/work` is scratch; only commits "
        "on your branch and files in your run folder survive.")


def product_note() -> str:
    """The product-repo section of a stage's system prompt (orientation §3/§4)."""
    origin = os.environ.get("LANTERN_PRODUCT_ORIGIN", "")
    branch = os.environ.get("LANTERN_PRODUCT_BRANCH", "")
    if product_writable():
        return coding_product_note()
    if not product_wired():
        return ("\n\n# The product repository\nNOT WIRED INTO THIS RUN. " + PRODUCT_HINT +
                " Do not invent product paths, consumers, or schema — a plan built on "
                "guessed paths is worse than a blocked one.")
    head = ""
    try:
        head = subprocess.run(["git", "log", "-1", "--format=%h %s"], cwd=product_root(),
                              timeout=30, capture_output=True, text=True).stdout.strip()
    except Exception:  # noqa: BLE001 — orientation text must never fail a stage
        pass
    return (
        "\n\n# The product repository\n"
        "The product code for this run is checked out READ-ONLY under the `product/` path "
        "prefix — `read_file('product/src/app.ts')`, `list_dir('product/src')`.\n\n"
        f"- **Origin:** `{origin or 'unknown'}`\n"
        f"- **Base branch:** `{branch or 'unknown'}` (checked out)\n"
        f"- **HEAD:** {head or 'unknown'}\n\n"
        "Use the `product_git` tool for history and search (`log`, `branch`, `grep`, "
        "`ls-files`) — it is real git, read-only, no shell. Start orientation there: read "
        "the product's own `AGENTS.md`/`README` for its conventions and commands, "
        "`product_git('log', ['--oneline','-20'])` for recent history, and "
        "`product_git('log', ['--all','--grep','<run-id>'])` for work already done for this "
        "run. This checkout is a throwaway clone of a host-side mirror: it has no "
        "credentials, no push path, and nothing written there survives the container. "
        "Every path you put in a report must be one you actually opened here.")


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


# Sidecar written only by collect_jsx (agent write tools refuse the name): maps each
# collected file to the sha256 of what the host wrote, so the postcondition can prove
# a jsx artifact never transited — and was never rewritten from — agent context.
COLLECTED_MANIFEST = ".collected.json"


def _record_collected(dst: Path, node_id: str) -> None:
    manifest = dst.parent / COLLECTED_MANIFEST
    data = {}
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except ValueError:
            data = {}
    data[dst.name] = {"sha256": hashlib.sha256(dst.read_bytes()).hexdigest(),
                      "bytes": dst.stat().st_size, "node_id": node_id}
    manifest.write_text(json.dumps(data, indent=2), encoding="utf-8")


def make_collect_jsx(paper: MCPServerStreamableHttp):
    """Build the collect_jsx tool bound to this stage's Paper MCP connection.

    Host-side for a reason: get_jsx returns 7–9 KB per artboard, and routing that
    through the agent's own context invites truncation — observed 2026-08-31
    (feat-20260831-gate-latency attempt 5): jsx/ files arrived as ~1.5 KB
    hand-compressed summaries and still cleared the size floor. The host calls
    get_jsx itself and writes the tool result verbatim; the agent only ever sees a
    size confirmation, so context limits can never touch the artifact.
    """
    @function_tool
    async def collect_jsx(node_id: str, dest_path: str) -> str:
        """Write Paper's full get_jsx output for one artboard/frame into the run folder.

        This is the ONLY way to produce a jsx/ handoff file: the host calls get_jsx
        and writes the result verbatim to `dest_path` — never copy JSX through your
        own context (it gets truncated) and never rewrite the file afterwards (the
        orchestrator hash-checks it against what was collected). `node_id` is the id
        you recorded from create_artboard; `dest_path` is repo-relative, e.g.
        'workflow/runs/<run-id>/01-ui-ux/jsx/<axis>.jsx'. Call once per presented
        option. Returns the size written, not the JSX.
        """
        call_args = {"nodeId": node_id}
        fid = os.environ.get("LANTERN_PAPER_FILE_ID")
        if fid:
            call_args["fileId"] = fid     # scoped to the agent-owned file by construction
        res = await paper.call_tool("get_jsx", call_args)
        text = "\n".join(c.text for c in res.content if getattr(c, "text", None))
        if getattr(res, "isError", False):
            raise RuntimeError(f"get_jsx failed for node {node_id}: {text[:500]}")
        if "<" not in text:
            raise RuntimeError(
                f"get_jsx returned no markup for node {node_id} — check the id against "
                "what create_artboard returned, and that the node still exists")
        dst = _safe(dest_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(text, encoding="utf-8")
        _record_collected(dst, node_id)
        return (f"collected {dst.relative_to(REPO).as_posix()} "
                f"({len(text.encode('utf-8')) // 1024} KB of get_jsx output, verbatim)")
    return collect_jsx


def stage_tools(role: str, run_id: str, stage: str, execution_key: str, paper=None) -> list:
    """The tool set for one stage execution — one definition for the container path
    (main below) and the in-process path (pipeline.run_agent_stage), so a tool added
    for a role cannot silently exist in one executor and not the other."""
    tools = [read_file, write_file, append_file, list_dir, list_exports, collect_export,
             product_git, make_append_memory(role, run_id, stage, execution_key)]
    if paper:
        tools.append(make_collect_jsx(paper))
    if product_writable():
        tools.append(product_shell)
    return tools


def max_turns_for(role: str) -> int:
    """Coding is a long loop of edit/test/commit; the other roles are review-shaped."""
    if role == "coding":
        return int(os.environ.get("LANTERN_CODING_MAX_TURNS", "400"))
    return 120


def check_claimed_artifacts(run_id: str, sdir: str) -> list[str]:
    """Every file a handoff.json claims must actually exist.

    Without this, a stage can pass by *describing* deliverables it never produced —
    observed 2026-08-26: handoff.json listed three option PNGs, none of which were on
    disk, and the stage still passed. Claims are not evidence.
    """
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
    if vid and str(vid).startswith("s3://"):
        # Under host-side uploads (P0.1) an agent can never legitimately know an S3
        # URL at report time — the host uploads only after postconditions pass. An
        # s3:// claim is therefore unverifiable-by-construction, i.e. fabricated.
        problems.append(
            f"handoff.json claims video '{vid}' — s3:// URLs cannot exist yet at report "
            "time; reference the local file, the orchestrator uploads and manifests it")
    elif vid and not str(vid).startswith(("http://", "https://")):
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
    # Provenance, not plausibility. A size/markup floor passed a ~1.5 KB hand-compressed
    # summary of 7–9 KB get_jsx output (observed 2026-08-31, attempt 5) — anything that
    # transits agent context can be silently truncated, so the only acceptable evidence
    # is the collect_jsx manifest hash proving the host wrote the file verbatim.
    collected = {}
    mf = jsx_dir / COLLECTED_MANIFEST
    if mf.is_file():
        try:
            collected = json.loads(mf.read_text(encoding="utf-8"))
        except ValueError:
            problems.append(f"jsx/{COLLECTED_MANIFEST} is not valid JSON")
    for f in jsx_files:
        entry = collected.get(f.name)
        if not entry or entry.get("sha256") != hashlib.sha256(f.read_bytes()).hexdigest():
            problems.append(
                f"jsx/{f.name} was not written by collect_jsx (or was rewritten after) — "
                "get_jsx output copied through agent context gets truncated; call "
                "collect_jsx(node_id, dest_path) so the host writes it verbatim, and "
                "leave the file alone")
    # The critique loop must leave evidence, not just a self-reported number.
    if names and not (REPO / "workflow/runs" / run_id / sdir / "critique-log.md").is_file():
        problems.append(
            "critique-log.md missing — per-option layout/style pass findings are the only "
            "evidence the critique loop actually ran (metrics.critique_iterations is a claim)")
    return problems


def check_stage_inputs(run_id: str, stage: str) -> str | None:
    """Refuse to start a stage whose upstream inputs are absent from this checkout.

    Run folders move between runners only through git (D9 assumed "one shared
    run-folder dir"; with EC2 + workstation that sharing is a git commit/pull, and
    nothing automates it yet). Without this check the agent starts against a
    checkout that never saw the upstream phase and invents the missing context —
    observed 2026-08-31 on feat-20260831-gate-latency: 01-ui-ux.design fabricated
    a divergence (claimed 6 skeletons, there were 8) and converged an option the
    judge had explicitly cut.
    """
    if stage == "01-ui-ux.design":
        sdir = REPO / "workflow/runs" / run_id / "01-ui-ux"
        skeletons = (sorted((sdir / "divergence").glob("*.html"))
                     if (sdir / "divergence").is_dir() else [])
        if not (sdir / "report.md").is_file() or not skeletons:
            return ("01-ui-ux.design inputs missing from this checkout: the diverge "
                    "report and divergence/*.html skeletons must exist before Paper "
                    "convergence — pull the diverge commit into this runner's checkout "
                    "(run folders sync between runners through git), then retry")
    if stage == "03-coding":
        # Auto-coding implements the APPROVED plan — without it the agent would code
        # from the brief alone, which is exactly the vague-ticket failure the plan
        # (symphony-alignment C2.4) names. The gate record is the approval evidence.
        plan = REPO / "workflow/runs" / run_id / "02-pre-coding" / "task-plan.md"
        if not plan.is_file():
            return ("03-coding (auto) needs 02-pre-coding/task-plan.md in this checkout — "
                    "stage 2 has not produced an approved plan for this run")
    return None


def usage_dict(result) -> dict:
    """Token usage of one Runner.run, as plain ints (P0.4 token ledger).

    Defensive getattr throughout: the Agents SDK usage shape has shifted between
    releases, and a missing field must degrade to an absent key, never a crash —
    the ledger is observability, not a postcondition.
    """
    u = getattr(getattr(result, "context_wrapper", None), "usage", None)
    if u is None:
        return {}
    d = {
        "requests": getattr(u, "requests", None),
        "input_tokens": getattr(u, "input_tokens", None),
        "output_tokens": getattr(u, "output_tokens", None),
        "total_tokens": getattr(u, "total_tokens", None),
    }
    details = getattr(u, "input_tokens_details", None)
    if details is not None:
        d["cached_input_tokens"] = getattr(details, "cached_tokens", None)
    return {k: int(v) for k, v in d.items() if isinstance(v, (int, float))}


# The dispatcher greps container stdout for this prefix to fill the token ledger —
# host-side write, so it keeps working when sandboxes lose stage_executions access
# (the planned restricted DB role, plan item C2.0).
USAGE_MARKER = "LANTERN_USAGE "


def report_blocker(report: Path) -> str | None:
    """The open question of a `Status: BLOCKED` stage report, or None if not blocked.

    Returns "" for a blocked report that states no question — still a failure, and a
    louder one: the contract is BLOCKED + exactly one unambiguous question.
    """
    try:
        text = report.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = re.search(r"^\s*[-*]?\s*\**Status:?\**:?\s*\**\s*([A-Za-z_]+)", text, re.M)
    if not m or m.group(1).upper() != "BLOCKED":
        return None
    q = re.search(r"^#+\s*Open questions.*?$(.*?)(?=^#|\Z)", text, re.M | re.S)
    if not q:
        return ""
    lines = [ln.strip().lstrip("-*").strip()
             for ln in q.group(1).splitlines() if ln.strip()]
    return lines[0][:400] if lines else ""


async def check_postconditions(conn: asyncpg.Connection, role: str, run_id: str,
                               stage: str, execution_key: str) -> list[str]:
    """The two written postconditions: stage report on disk, memory row from THIS execution.

    The memory check queries by execution_key, not by diffing memory.md — the file diff
    was unsound under concurrency (another run's append to the same role's file satisfied
    it, so a stage that wrote nothing passed). Proven by test_verification.py.
    """
    missing = []
    sdir = stage_dir(stage)
    report_path = REPO / "workflow/runs" / run_id / sdir / "report.md"
    if not report_path.exists():
        missing.append(f"stage report workflow/runs/{run_id}/{sdir}/report.md not written")
    else:
        # A BLOCKED report is a legitimate outcome, but it is NOT a completed stage.
        # Until this check existed, blocked and succeeded were indistinguishable to the
        # dispatcher: both wrote a report + a memory row, so both opened the stage's
        # approval gate, and a human could sign off a plan whose own summary said no
        # plan exists. (Both 02-pre-coding executions of 2026-08-27 did exactly that.)
        # Fail the stage instead: the report and memory still stand on disk, no gate is
        # created, and `retry` is the resume path once the question is answered.
        blocked_q = report_blocker(report_path)
        if blocked_q is not None:
            missing.append(
                "stage reported Status: BLOCKED, so it did not complete — no gate is "
                "opened for a blocked stage. Answer its open question, then `retry`. "
                f"Question: {blocked_q or '(none stated — the report must state exactly one)'}")
    missing.extend(check_claimed_artifacts(run_id, sdir))
    if role == "coding":
        # The branch bundle is the deliverable; a report without one is a claim.
        # Verified against the checkout when this process has one (container /
        # in-process); the host re-check verifies again against its mirror before
        # anything is pushed (pipeline.publish_coding_branch).
        verify_in = product_root() if (product_root() / ".git").exists() else None
        missing.extend(check_coding_handoff(run_id, sdir, verify_in))
    if is_qa_video_stage(stage):
        # Presence AND validity AND recency (the fabrication lesson, applied to video):
        # a real, non-empty .webm recorded by THIS attempt — a stale file from a failed
        # earlier attempt must not stand in as evidence, exactly like the memory check
        # is scoped by execution_key rather than "any row exists".
        started = await conn.fetchval(
            "SELECT started_at FROM stage_executions WHERE idempotency_key = $1", execution_key)
        floor_ts = (started.timestamp() if started else PROCESS_START) - 60  # clock-skew slack
        videos = [p for p in (REPO / "workflow/runs" / run_id / sdir).rglob("*.webm")
                  if p.is_file() and p.stat().st_size > 0 and p.stat().st_mtime >= floor_ts]
        if not videos:
            missing.append(
                f"no video from this attempt under workflow/runs/{run_id}/{sdir}/ — QA "
                "browser sessions record automatically (the MCP is launched with "
                "saveVideo); a QA pass without fresh video evidence is a claim, not "
                "evidence, and does not advance")
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
    ap.add_argument("--execution-key", default=None,
                    help="ties this execution to its stage_executions row (the dispatcher "
                         "sets it in sandboxes); default: a fresh manual key")
    ap.add_argument("--persist-session", action="store_true",
                    help="persist the conversation as the Agents SDK session "
                         "{run_id}:{stage} in Postgres, like pipeline.py does")
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
    execution_key = args.execution_key or f"manual:{args.run_id}:{args.stage}:{uuid4().hex[:8]}"
    await render_role_memory(conn, role)   # instructions must read a fresh view

    session = None
    if args.persist_session:
        from agents.extensions.memory import SQLAlchemySession
        session = SQLAlchemySession.from_url(
            f"{args.run_id}:{args.stage}", url=db_urls()[0], create_tables=True)

    mcp_servers = []
    if role in BROWSER_ROLES:
        mcp_servers.append(playwright_mcp_server(args.run_id, args.stage))
    paper = None
    if args.stage in PAPER_STAGES:
        if not await paper_reachable():
            sys.exit(PAPER_PREFLIGHT_HINT)
        paper = paper_mcp_server()
        mcp_servers.append(paper)

    for s in mcp_servers:
        await s.connect()
    try:
        agent = Agent(
            name=role,
            model=model_for(role, args.stage),
            instructions=build_instructions(role, args.run_id, args.stage),
            tools=stage_tools(role, args.run_id, args.stage, execution_key, paper),
            mcp_servers=mcp_servers,
        )
        # Attempt number from the execution key ('run:stage:attempt') — the agent
        # needs it to pre-link the attempt-scoped media URLs in its report.
        _tail = execution_key.rsplit(":", 1)[-1]
        attempt_note = f" (attempt {_tail})" if _tail.isdigit() else ""
        result = await Runner.run(
            agent,
            input=f"Begin your {args.stage} session for run {args.run_id}{attempt_note}. "
                  "Do not reply with a plan — start calling tools now and keep working "
                  "until the report is on disk and append_memory has been called.",
            session=session,
            max_turns=max_turns_for(role),
        )
        print(result.final_output)
        if role == "coding":
            # The checkout dies with this process; bundle the committed branch into
            # the run folder NOW so the host can verify, push and open the PR (D14).
            for p in finalize_coding(args.run_id, args.stage):
                print(f"FINALIZE: {p}", file=sys.stderr)
        print(USAGE_MARKER + json.dumps(
            {**usage_dict(result), "model": model_for(role, args.stage)}))
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
