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
import urllib.error
import urllib.request
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

from agents import Agent, Runner, set_default_openai_api, set_default_openai_client, set_tracing_disabled
from agents.extensions.memory import SQLAlchemySession

from orchestrator import (
    BROWSER_ROLES, CODING_BRANCH_PREFIXES, check_coding_handoff, finalize_coding, max_turns_for, stage_tools, PAPER_PREFLIGHT_HINT, PAPER_STAGES, REPO, ROLE_FOR_STAGE,
    USAGE_MARKER, append_file, azure_v1_client, build_consult_instructions,
    build_instructions, check_postconditions, check_stage_inputs, collect_export,
    consult_roles, db_urls,
    list_dir, list_exports, make_append_memory, make_collect_jsx, model_for,
    model_settings_for, paper_mcp_server,
    product_git,
    paper_reachable, playwright_mcp_server, read_file, render_role_memory, usage_dict,
    write_file,
)

load_dotenv(Path(__file__).parent / ".env")

import factory  # noqa: E402  D17: quality gate + fix loop for the in-process coding path
import review   # noqa: E402  D19: review loop after publish + merge babysitter

PIPELINE_VERSION = "3"  # v3 (D17): story stage + validation execution; v2: stage 1 diverge/design split
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
    "LANTERN_MODEL_REASONING", "LANTERN_MODEL_CODING", "LANTERN_MODEL_FAST",
    "LANTERN_EFFORT_REASONING", "LANTERN_EFFORT_CODING", "LANTERN_EFFORT_FAST",
    "LANTERN_OPENAI_API",
)

# ── QA stages (P0.1): target credentials + video ─────────────────────────────
# Which stages are QA is derived from ROLE_FOR_STAGE (orchestrator.is_qa_video_stage)
# — one source of truth, so the debug lifecycle's regression stage is covered the day
# it gets a dispatch path, with no parallel stage-key set to drift. Video recording
# itself is configured by the orchestrator (playwright_mcp_server appends --config/
# --output-dir), so it works identically in-process, in sandboxes, and manually;
# the video postcondition lives in check_postconditions for the same reason.
QA_TARGET_PREFIX = {"qa-dev": "LANTERN_QA_DEV", "qa-staging": "LANTERN_QA_STAGING"}
# Media uploads happen HOST-side after the container exits — AWS credentials never
# enter a sandbox (D10's scoped-credentials rule; the instance role stays host-only).
ARTIFACT_BUCKET = os.environ.get("LANTERN_ARTIFACT_BUCKET", "")


def qa_stage_env(stage: str) -> dict[str, str]:
    """Container env additions for QA stages: target creds + the bucket NAME.

    Host vars come from SSM (/lantern/qa/{dev,staging}/*); in-container names are
    uniform (QA_BASE_URL/QA_USER/QA_PASS) so role skills don't fork by stage. The
    bucket name is not a credential — it lets the agent pre-link the deterministic
    S3 URLs (PIPELINE.md naming) in its report before the host uploads.
    """
    prefix = QA_TARGET_PREFIX.get(ROLE_FOR_STAGE.get(stage, ""))
    if not prefix:
        return {}
    env = {}
    for inner, suffix in (("QA_BASE_URL", "_BASE_URL"), ("QA_USER", "_USER"), ("QA_PASS", "_PASS")):
        if os.environ.get(prefix + suffix):
            env[inner] = os.environ[prefix + suffix]
    if ARTIFACT_BUCKET:
        env["LANTERN_ARTIFACT_BUCKET"] = ARTIFACT_BUCKET
    return env


def sandbox_db_url() -> str:
    """The DB URL as seen from inside a container (host Postgres via the gateway)."""
    return os.environ.get(
        "LANTERN_SANDBOX_DATABASE_URL",
        db_urls()[0].replace("@localhost", "@host.docker.internal"))

# ── the product repository (per-run target + host-side mirror) ───────────────
# Two rules shape this design:
#   1. The PAT NEVER enters a sandbox (D10 scoped-credentials, plan §4 C2.3). So the
#      HOST authenticates and keeps a bare mirror; the container gets that mirror
#      bind-mounted READ-ONLY at /product-src.git and clones from a plain local path.
#      The token is passed per-fetch on the command line and is never written into
#      the mirror's config, so mounting the mirror leaks nothing.
#   2. The target is PER RUN, not per daemon: `runs.product_repo`/`product_branch`.
#      A brief names its own target (the brief field is the authoring surface),
#      LANTERN_PRODUCT_REPO/_BRANCH are only the fallback default for a box that
#      works on one product.
PRODUCT_MIRROR_DIR = Path(os.environ.get(
    "LANTERN_PRODUCT_MIRROR_DIR", Path.home() / ".lantern" / "product-mirrors"))
PRODUCT_REPO_DEFAULT = os.environ.get("LANTERN_PRODUCT_REPO", "")
PRODUCT_BRANCH_DEFAULT = os.environ.get("LANTERN_PRODUCT_BRANCH", "main")
GIT_TOKEN = os.environ.get("GITHUB_LANTERN_BOT_TOKEN", "")
# Auto-coding (D14): identity for the commits the coding agent makes in its sandbox
# and for the PR the host opens. Defaults are the bot identity D6 specifies.
CODING_MODES = ("human", "auto")
CODING_TIMEOUT_MIN = int(os.environ.get("LANTERN_CODING_TIMEOUT_MIN", "120"))
GIT_AUTHOR_NAME = os.environ.get("LANTERN_GIT_AUTHOR_NAME", "lantern-bot")
GIT_AUTHOR_EMAIL = os.environ.get("LANTERN_GIT_AUTHOR_EMAIL", "lantern-bot@users.noreply.github.com")
PUBLIC_URL = os.environ.get("LANTERN_PUBLIC_URL", "").rstrip("/")   # Mission Control, for PR links


def coding_branch(run_id: str) -> str:
    """The run's own branch: feat/<date>-<slug> for feature runs, fix/… for bug runs —
    unique per run (the run id is) and inside the feat/*|fix/* namespace D6 lets
    agents push to."""
    if run_id.startswith("bug-"):
        return "fix/" + run_id[len("bug-"):]
    if run_id.startswith("feat-"):
        return "feat/" + run_id[len("feat-"):]
    return "feat/" + run_id


def work_branch(run_id: str, working_branch: str = "") -> str:
    """The branch this run's code lands on (D15).

    A run may name an EXISTING branch to continue on; when it does not, the branch is
    derived from the run id exactly as it always was. coding_branch() stays the pure
    default so the derivation has one definition and one set of assertions.
    """
    return (working_branch or "").strip() or coding_branch(run_id)


def parse_brief_coding_mode(text: str) -> str:
    """`- **Coding mode:** auto|human` in a brief; anything else reads as unset ('')."""
    # [ \t]* not \s*: an empty field must not swallow the next line (found 2026-09-08).
    m = re.search(r"^\s*-\s*\*\*Coding mode:\*\*[ \t]*(.*?)[ \t]*$", text, re.M | re.I)
    if not m:
        return ""
    v = m.group(1).strip().strip("`").lower()
    return v if v in CODING_MODES else ""


def parse_brief_product(text: str) -> tuple[str, str, str]:
    """Pull `- **Product repo:**` / `- **Base branch:**` / `- **Working branch:**` out
    of a brief. Returns (repo, base, working); working is '' when the run should get a
    fresh branch derived from its id (D15).

    Placeholder values (em-dash, TBD, or an unfilled <angle-bracket> template slot)
    read as 'not set' — an unfilled template must not look like a configured target.
    """
    def field(label: str) -> str:
        # [ \t]* not \s*: `- **Working branch:**` left blank (the template says "leave
        # blank for a fresh one") must read as '', not as the following line.
        m = re.search(rf"^\s*-\s*\*\*{label}:\*\*[ \t]*(.*?)[ \t]*$", text, re.M | re.I)
        if not m:
            return ""
        v = m.group(1).strip().strip("`")
        if v in ("—", "-", "") or v.upper() in ("TBD", "N/A", "NONE"):
            return ""
        if v.startswith("<") and v.endswith(">"):
            return ""
        return v
    return field("Product repo"), field("Base branch"), field("Working branch")


def _mirror_path(repo: str) -> Path:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", repo.rstrip("/").removesuffix(".git")).strip("-").lower()
    return PRODUCT_MIRROR_DIR / f"{slug[-60:]}-{hashlib.sha256(repo.encode()).hexdigest()[:8]}.git"


def _authed(repo: str) -> str:
    """The fetch URL WITH credentials — host-process only, never persisted or mounted."""
    if GIT_TOKEN and repo.startswith("https://") and "@" not in repo.split("//", 1)[1].split("/", 1)[0]:
        return "https://x-access-token:" + GIT_TOKEN + "@" + repo.split("//", 1)[1]
    return repo


def _git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          timeout=600, errors="replace")


def sync_product_mirror(repo: str) -> Path:
    """Fetch/refresh the host-side bare mirror of `repo` and return its path.

    A local path (an on-box mirror or checkout) is used as-is — no network, no token.
    """
    local = Path(repo)
    if repo.startswith(("/", ".")) or (len(repo) > 2 and repo[1] == ":"):
        if not local.exists():
            raise RuntimeError(f"product repo path does not exist on the host: {repo}")
        return local.resolve()

    mirror = _mirror_path(repo)
    mirror.parent.mkdir(parents=True, exist_ok=True)
    if not (mirror / "HEAD").exists():
        r = _git("clone", "--mirror", _authed(repo), str(mirror))
        if r.returncode != 0:
            raise RuntimeError(f"product mirror clone failed: {_scrub(r.stderr)[-600:]}")
        # Drop the credentialed URL from the mirror's config immediately — this
        # directory gets mounted into sandboxes and must never carry the token.
        _git("remote", "set-url", "origin", repo, cwd=mirror)
    else:
        r = _git("fetch", "--prune", _authed(repo),
                 "+refs/heads/*:refs/heads/*", "+refs/tags/*:refs/tags/*", cwd=mirror)
        if r.returncode != 0:
            raise RuntimeError(f"product mirror fetch failed: {_scrub(r.stderr)[-600:]}")
    leak = _git("config", "--get", "remote.origin.url", cwd=mirror).stdout
    if "@" in leak and GIT_TOKEN and GIT_TOKEN[:12] in leak:
        raise RuntimeError("refusing to mount a mirror whose config holds the PAT")
    return mirror


def _scrub(text: str) -> str:
    """Never let the PAT reach a log line, an error, or a stage_executions row."""
    return text.replace(GIT_TOKEN, "***") if GIT_TOKEN else text


async def product_target(conn, run_id: str) -> tuple[str, str]:
    """(repo, branch) for a run — DB first, env default second, ('', '') if unset."""
    row = await conn.fetchrow(
        "SELECT product_repo, product_branch FROM runs WHERE id = $1", run_id)
    repo = (row and row["product_repo"]) or PRODUCT_REPO_DEFAULT
    branch = (row and row["product_branch"]) or PRODUCT_BRANCH_DEFAULT
    return repo, (branch if repo else "")


async def product_work_branch(conn, run_id: str) -> str:
    """The branch this run works ON, resolved (D15) — the chosen one, else derived.

    A sibling of product_target() rather than a third tuple element on purpose: every
    existing caller unpacks that 2-tuple, and an additive function is something a
    long-lived daemon picks up on restart with no coordinated deploy.
    """
    wb = await conn.fetchval(
        "SELECT product_working_branch FROM runs WHERE id = $1", run_id)
    return work_branch(run_id, wb or "")


def product_mount_args(repo: str, branch: str, work: str = "") -> list[str]:
    """Docker args that give a sandbox a read-only, credential-free product checkout.

    `work` (D15) is advisory for read stages: the entrypoint checks that branch out
    when the origin already has it, so a stage sees the code the run is working on
    rather than the base. Keyword-with-default keeps every pre-D15 caller valid.
    """
    if not repo:
        return []
    mirror = sync_product_mirror(repo)
    args = ["-v", f"{mirror}:/product-src.git:ro",
            "-e", "LANTERN_PRODUCT_REPO=/product-src.git",
            "-e", f"LANTERN_PRODUCT_BRANCH={branch}",
            "-e", f"LANTERN_PRODUCT_ORIGIN={repo}"]
    if work:
        args += ["-e", f"LANTERN_PRODUCT_WORK_BRANCH={work}"]
    return args


# (stage key, run-folder dir, type, gate-after, runner). Human stages produce an
# approval immediately and wait. Stage 1 is split by runner affinity: cheap divergence
# on EC2, Paper convergence on the design workstation (docs/plans/ui-ux-agent-paper.md).
FEATURE_STAGES = [
    ("00-story.scout",   "00-story",       "agent", None,             "ec2"),   # D17: researcher
    ("00-story.write",   "00-story",       "agent", "story_signoff",  "ec2"),   # D17: story + criteria
    ("01-ui-ux.diverge", "01-ui-ux",       "agent", None,             "ec2"),
    ("01-ui-ux.design",  "01-ui-ux",       "agent", "ux_signoff",     "workstation"),
    ("02-pre-coding",    "02-pre-coding",  "agent", "plan_signoff",   "ec2"),
    ("03-coding",        "03-coding",      "human", "code_complete",  "ec2"),
    ("04-qa-dev",        "04-qa-dev",      "agent", None,             "ec2"),
    ("05-post-coding",   "05-post-coding", "agent", None,             "ec2"),
    ("05-post-coding.validate", "05-post-coding", "agent", None,      "ec2"),   # D17: validator
    ("06-security",      "06-security",    "agent", "staging_deploy", "ec2"),
    ("07-qa-staging",    "07-qa-staging",  "agent", "prod_signoff",   "ec2"),
]
STAGE_INDEX = {s[0]: i for i, s in enumerate(FEATURE_STAGES)}
STAGE_DIR = {s[0]: s[1] for s in FEATURE_STAGES}
STAGE_RUNNER = {s[0]: s[4] for s in FEATURE_STAGES}
STAGE_DIR.update(review.SUB_STAGE_DIRS)   # D19: review/fix/regate executions live in 03-coding/


async def connect() -> asyncpg.Connection:
    return await asyncpg.connect(db_urls()[1])


async def log_event(conn, run_id: str | None, actor: str, type_: str, data: dict | None = None) -> None:
    await conn.execute(
        "INSERT INTO events (run_id, actor, type, data) VALUES ($1, $2, $3, $4)",
        run_id, actor, type_, json.dumps(data or {}),
    )


# ── token ledger (P0.4) ──────────────────────────────────────────────────────

async def record_usage(conn, exec_id: int, usage: dict, model: str | None = None) -> None:
    """Write one execution's token counts onto its stage_executions row (host-side)."""
    if not usage:
        return
    await conn.execute(
        """UPDATE stage_executions
           SET model = coalesce($1, model), requests = $2, input_tokens = $3,
               cached_input_tokens = $4, output_tokens = $5, total_tokens = $6
           WHERE id = $7""",
        usage.get("model", model), usage.get("requests"), usage.get("input_tokens"),
        usage.get("cached_input_tokens"), usage.get("output_tokens"),
        usage.get("total_tokens"), exec_id)


# Per-key upper bounds match the column types: requests is int4, tokens are bigint.
_USAGE_INT_BOUNDS = {"requests": 2**31 - 1, "input_tokens": 10**12,
                     "cached_input_tokens": 10**12, "output_tokens": 10**12,
                     "total_tokens": 10**12}


def parse_usage_line(container_output: str) -> dict:
    """Extract and VALIDATE the orchestrator's LANTERN_USAGE line from container output.

    The line shares stdout with agent-controlled text, so nothing here is trusted:
    ints only (bools rejected), sane bounds, model as a short string — a fabricated
    or malformed line degrades to an empty dict, never to a DataError mid-bookkeeping.
    """
    for line in reversed(container_output.splitlines()):
        if not line.startswith(USAGE_MARKER):
            continue
        try:
            raw = json.loads(line[len(USAGE_MARKER):])
        except ValueError:
            return {}
        if not isinstance(raw, dict):
            return {}
        clean: dict = {}
        for k, bound in _USAGE_INT_BOUNDS.items():
            v = raw.get(k)
            if type(v) is int and 0 <= v <= bound:
                clean[k] = v
        if isinstance(raw.get("model"), str):
            clean["model"] = raw["model"][:100]
        return clean
    return {}


def _price_rates(model: str | None) -> tuple[float, float, float]:
    """($/1M input, $/1M cached input, $/1M output) for a deployment.

    LANTERN_PRICE_JSON ('{"sol": {"in": 4, "cached": 1, "out": 20}, ...}') gives
    per-deployment rates — the fleet deliberately routes across two price classes,
    so one flat rate misprices the alarms by the models' ratio. The flat
    LANTERN_PRICE_*_PER_M vars are the fallback. All PROVISIONAL until real Azure
    invoice lines confirm them; token counts are exact, only dollars are estimates.
    """
    flat = (float(os.environ.get("LANTERN_PRICE_IN_PER_M", "4")),
            float(os.environ.get("LANTERN_PRICE_CACHED_IN_PER_M", "1")),
            float(os.environ.get("LANTERN_PRICE_OUT_PER_M", "20")))
    try:
        table = json.loads(os.environ.get("LANTERN_PRICE_JSON", "") or "{}")
        r = table.get(model or "") if isinstance(table, dict) else None
        if isinstance(r, dict):
            return (float(r.get("in", flat[0])), float(r.get("cached", flat[1])),
                    float(r.get("out", flat[2])))
    except (ValueError, TypeError):
        pass
    return flat


def est_cost_usd(input_tokens, cached_input_tokens, output_tokens, model: str | None = None) -> float:
    """Estimated spend for one bucket of tokens (int-coerced: SQL sums arrive as Decimal)."""
    p_in, p_cached, p_out = _price_rates(model)
    cached = int(cached_input_tokens or 0)
    uncached = max(0, int(input_tokens or 0) - cached)
    return (uncached * p_in + cached * p_cached + int(output_tokens or 0) * p_out) / 1_000_000


def est_cost_rows(rows) -> float:
    """Total est. cost of per-model aggregate rows (model, inp, cached, outp)."""
    return sum(est_cost_usd(r["inp"], r["cached"], r["outp"], r["model"]) for r in rows)


# ── media uploads (P0.1): host-side, after the container exits ───────────────

async def insert_artifact(conn, run_id: str, stage: str, kind: str, uri: str,
                          metadata: dict | None = None) -> None:
    await conn.execute(
        "INSERT INTO artifacts (run_id, stage, kind, uri, metadata) VALUES ($1, $2, $3, $4, $5)",
        run_id, stage, kind, uri, json.dumps(metadata) if metadata else None)


async def upload_stage_media(conn, run_id: str, sdir: str, execution_key: str) -> None:
    """Ship THIS attempt's videos to the artifact bucket, then delete them locally.

    Runs on the HOST after postconditions pass — sandboxes have no AWS credentials.
    Contract: NOTHING here may fail a stage that already passed — every failure
    path degrades to a media_upload_failed event (the files stay on disk).

    Scoped to the current attempt (same mtime floor as the video postcondition):
    a failed earlier attempt's leftover .webm must not be renumbered into this
    attempt's evidence. Keys are prefixed `attempt-<k>/` so a retry after a gate
    rejection never overwrites approved-or-rejected footage, and each artifacts
    row stays unique. Only .webm (browser recordings) is handled — Paper MP4
    walkthroughs are referenced by handoff.json/the gate payload as local files
    and get their own flow later; deleting them here would break the ux_signoff
    payload (found in review).

    media-manifest.json is REGENERATED from the artifacts table — never merged
    from the on-disk file, which every sandbox in the run can write: an
    agent-seeded manifest must not survive as host evidence.
    """
    try:
        started = await conn.fetchval(
            "SELECT started_at FROM stage_executions WHERE idempotency_key = $1", execution_key)
        floor_ts = (started.timestamp() - 60) if started else 0
        tail = execution_key.rsplit(":", 1)[-1]
        attempt = int(tail) if tail.isdigit() else 1
        stage_path = REPO / "workflow" / "runs" / run_id / sdir
        media = sorted((p for p in stage_path.rglob("*.webm") if p.is_file()
                        and p.stat().st_size > 0 and p.stat().st_mtime >= floor_ts),
                       key=lambda p: p.stat().st_mtime)
        if not media:
            return
        if not ARTIFACT_BUCKET:
            await log_event(conn, run_id, "orchestrator", "media_upload_skipped",
                            {"stage": sdir, "files": [p.name for p in media],
                             "reason": "LANTERN_ARTIFACT_BUCKET not set"})
            return
        uploaded = 0
        for session, f in enumerate(media, start=1):
            name = f"{run_id}--{sdir}--session-{session}.webm"
            uri = f"s3://{ARTIFACT_BUCKET}/lantern/{run_id}/{sdir}/attempt-{attempt}/{name}"
            try:
                proc = await asyncio.create_subprocess_exec(
                    "aws", "s3", "cp", str(f), uri,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
                out, _ = await proc.communicate()
                err = None if proc.returncode == 0 else out.decode(errors="replace")[-300:]
            except OSError as e:          # aws CLI missing / not on the unit's PATH
                err = str(e)
            if err is not None:
                await log_event(conn, run_id, "orchestrator", "media_upload_failed",
                                {"stage": sdir, "file": f.name, "error": err})
                continue
            await insert_artifact(conn, run_id, sdir, "qa_video", uri,
                                  {"local_name": f.name, "bytes": f.stat().st_size,
                                   "attempt": attempt, "session": session})
            f.unlink()   # .gitignore also excludes *.webm — belt and braces
            uploaded += 1
        rows = await conn.fetch(
            """SELECT uri, metadata, created_at FROM artifacts
               WHERE run_id = $1 AND stage = $2 AND kind = 'qa_video' ORDER BY created_at""",
            run_id, sdir)
        (stage_path / "media-manifest.json").write_text(json.dumps({"uploaded": [
            {"uri": r["uri"], **json.loads(r["metadata"] or "{}"),
             "at": r["created_at"].isoformat(timespec="seconds")} for r in rows
        ]}, indent=2) + "\n", encoding="utf-8")
        if uploaded:
            await log_event(conn, run_id, "orchestrator", "media_uploaded",
                            {"stage": sdir, "count": uploaded})
    except Exception as e:  # noqa: BLE001 — uploads must never fail a passed stage
        try:
            await log_event(conn, run_id, "orchestrator", "media_upload_failed",
                            {"stage": sdir, "error": str(e)[:300]})
        except Exception:  # noqa: BLE001
            print(f"[{run_id}] media upload bookkeeping failed: {e}", file=sys.stderr)


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
    # Same product access as a sandbox, via a host checkout instead of a mount, so
    # laptop/workstation runs see exactly what the box does (orchestrator reads
    # LANTERN_PRODUCT_DIR at call time).
    repo, branch = await product_target(conn, run_id)
    work = await product_work_branch(conn, run_id) if repo else ""
    for var in ("LANTERN_PRODUCT_DIR", "LANTERN_PRODUCT_WRITABLE", "LANTERN_CODING_BRANCH",
                "LANTERN_PRODUCT_WORK_BRANCH", "LANTERN_CODING_START_SHA"):
        os.environ.pop(var, None)
    if stage == "03-coding" and not repo:
        raise RuntimeError("auto-coding needs a product repo — set one with "
                           f"`pipeline.py set-product {run_id} --repo … --branch …"
                           " [--working-branch …]` or in Mission Control at "
                           f"/run/{run_id}/repo")
    if repo:
        checkout = await asyncio.to_thread(product_checkout, repo, branch, run_id, work)
        os.environ["LANTERN_PRODUCT_DIR"] = str(checkout)
        os.environ["LANTERN_PRODUCT_ORIGIN"], os.environ["LANTERN_PRODUCT_BRANCH"] = repo, branch
        # D15: EVERY stage learns the working branch, not just coding — that is what
        # lets stages 1-2 and 4-7 orient on the code the run is actually working on.
        os.environ["LANTERN_PRODUCT_WORK_BRANCH"] = work
        if stage == "03-coding" or stage in review.WRITABLE_STAGES:   # D14 (+ D19 fix executions): writable, on the run's branch, bot identity
            start = await asyncio.to_thread(prepare_coding_checkout, checkout, work)
            os.environ["LANTERN_CODING_BRANCH"] = work
            os.environ["LANTERN_CODING_START_SHA"] = start
            os.environ["LANTERN_PRODUCT_WRITABLE"] = "1"
    session = SQLAlchemySession.from_url(f"{run_id}:{stage}", url=db_urls()[0], create_tables=True)

    problem = check_stage_inputs(run_id, stage)
    if problem:
        raise RuntimeError(problem)
    mcp_servers = []
    if role in BROWSER_ROLES:
        mcp_servers.append(playwright_mcp_server(run_id, stage))
    paper = None
    if stage in PAPER_STAGES:
        if not await paper_reachable():
            raise RuntimeError(PAPER_PREFLIGHT_HINT)
        paper = paper_mcp_server()
        mcp_servers.append(paper)
    for s in mcp_servers:
        await s.connect()
    try:
        agent = Agent(
            name=role,
            model=model_for(role, stage),
            model_settings=model_settings_for(role, stage),
            instructions=build_instructions(role, run_id, stage),
            tools=stage_tools(role, run_id, stage, execution_key, paper),
            mcp_servers=mcp_servers,
        )
        kickoff = (f"Begin your {stage} session for run {run_id} (attempt {attempt}). Do not "
                   "reply with a plan — start calling tools now and keep working until the "
                   "report is on disk and append_memory has been called.")

        async def run_turn(text: str):
            return await Runner.run(agent, input=text, session=session,
                                    max_turns=max_turns_for(role))

        if role == "coding":
            # D17: quality gate as code + bounded fix loop — the same helper the
            # container path uses, so laptop and box runs cannot disagree.
            results, gate = await factory.coding_turns(
                run_turn, kickoff, run_id=run_id, stage=stage,
                root=Path(os.environ["LANTERN_PRODUCT_DIR"]), execution_key=execution_key,
                since_sha=os.environ.get("LANTERN_CODING_START_SHA") or None)
            print(f"[{run_id}] quality gate {'green' if gate['passed'] else 'RED'} after "
                  f"{gate['round']} fix round(s)")
        else:
            results = [await run_turn(kickoff)]
        result = results[-1]
        final = str(result.final_output)
        # D14: bundle the committed branch into the run folder while the checkout exists.
        finalize_problems = finalize_coding(run_id, stage) if role == "coding" else []
    finally:
        for s in mcp_servers:
            await s.cleanup()
        for var in ("LANTERN_PRODUCT_WRITABLE", "LANTERN_CODING_BRANCH",
                    "LANTERN_CODING_START_SHA"):
            os.environ.pop(var, None)   # never leak writability into the next stage

    # Ledger before the postcondition verdict: tokens are spent either way (P0.4).
    # Known gap, both paths: a Runner.run exception (max_turns, API error) yields no
    # result/usage line, so that spend goes unmetered — `usage` reports the count.
    await record_usage(conn, exec_id, factory.merge_usage([usage_dict(r) for r in results]),
                       model_for(role, stage))

    if finalize_problems:
        raise RuntimeError("coding handoff failed: " + "; ".join(finalize_problems))
    missing = await check_postconditions(conn, role, run_id, stage, execution_key)
    if missing:
        raise RuntimeError("postconditions failed: " + "; ".join(missing))
    await upload_stage_media(conn, run_id, sdir, execution_key)

    report = f"workflow/runs/{run_id}/{sdir}/report.md"
    await insert_artifact(conn, run_id, sdir, "report", report)
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

    problem = check_stage_inputs(run_id, stage)
    if problem:
        raise RuntimeError(problem)
    run_dir = REPO / "workflow" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    name = f"lantern-{run_id}-{stage}-{attempt}".replace(".", "-")
    # No --user here: the entrypoint starts as root solely to repair docker-created
    # root-owned mountpoint parents, then drops itself to uid 1000 (the host app
    # user) — so artifacts on the mounted run dir come out host-owned. Root-owned
    # files in the git tree broke cleanup on 2026-08-26.
    cmd = ["docker", "run", "--rm", "--name", name,
           "--cpus", SANDBOX_CPUS, "--memory", SANDBOX_MEMORY,
           "--add-host=host.docker.internal:host-gateway",
           "-v", f"{REPO}:/repo-src:ro",
           "-v", f"{run_dir}:/work/lantern/workflow/runs/{run_id}:rw",
           "-e", f"LANTERN_EXECUTION_KEY={execution_key}",
           "-e", f"LANTERN_DATABASE_URL={sandbox_db_url()}"]
    for var in SANDBOX_ENV_ALLOWLIST:
        if os.environ.get(var):
            cmd += ["-e", f"{var}={os.environ[var]}"]
    # Per-stage additions (D12: secrets cross only when the stage needs them).
    # Video recording needs no env here — orchestrator.py configures the MCP itself.
    for inner, value in qa_stage_env(stage).items():
        cmd += ["-e", f"{inner}={value}"]
    # Product code (read-only, credential-free): the host refreshes its mirror and
    # bind-mounts it; the entrypoint clones /product-src.git into /work/product.
    repo, branch = await product_target(conn, run_id)
    work = await product_work_branch(conn, run_id) if repo else ""
    if stage == "03-coding" and not repo:
        raise RuntimeError("auto-coding needs a product repo — set one with "
                           f"`pipeline.py set-product {run_id} --repo … --branch …"
                           " [--working-branch …]` or in Mission Control at "
                           f"/run/{run_id}/repo")
    cmd += await asyncio.to_thread(product_mount_args, repo, branch, work)
    timeout_min = STAGE_TIMEOUT_MIN
    if stage == "03-coding" or stage in review.WRITABLE_STAGES:   # D19: fix executions too
        # D14: the entrypoint puts the checkout on the run's branch and marks it
        # writable; commits carry the bot identity. Still no PAT in the container —
        # the bundle it writes into the run folder is the only way code leaves.
        timeout_min = CODING_TIMEOUT_MIN
        cmd += ["-e", f"LANTERN_CODING_BRANCH={work}",
                "-e", f"LANTERN_GIT_AUTHOR_NAME={GIT_AUTHOR_NAME}",
                "-e", f"LANTERN_GIT_AUTHOR_EMAIL={GIT_AUTHOR_EMAIL}"]
        for var in ("LANTERN_CODING_MAX_TURNS", "LANTERN_PRODUCT_SHELL_TIMEOUT",
                    "LANTERN_FIX_ROUNDS"):
            if os.environ.get(var):
                cmd += ["-e", f"{var}={os.environ[var]}"]
    cmd += [SANDBOX_IMAGE, run_id, stage]

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_min * 60)
    except asyncio.TimeoutError:
        kill = await asyncio.create_subprocess_exec("docker", "kill", name)
        await kill.wait()
        await proc.communicate()
        raise RuntimeError(f"sandbox hit the {timeout_min}-minute wall clock and was killed")
    full = out.decode(errors="replace")
    tail = full[-4000:]
    # Ledger first — tokens are spent whether or not the stage passed (P0.4). The
    # usage line comes from container stdout, so this write stays host-side even
    # after sandboxes lose stage_executions access (plan item C2.0).
    await record_usage(conn, exec_id, parse_usage_line(full))
    if proc.returncode != 0:
        raise RuntimeError(f"sandbox exited {proc.returncode}: {tail[-1500:]}")

    # The video-evidence gate for QA stages lives inside check_postconditions
    # (mtime-scoped to this attempt), so it holds at all three verdict sites:
    # container self-check, this host re-check, and the in-process path.
    missing = await check_postconditions(conn, role, run_id, stage, execution_key)
    if missing:
        raise RuntimeError("postconditions failed (host re-check): " + "; ".join(missing))
    await render_role_memory(conn, role)   # keep the host's rendered view fresh
    await upload_stage_media(conn, run_id, sdir, execution_key)

    report = f"workflow/runs/{run_id}/{sdir}/report.md"
    await insert_artifact(conn, run_id, sdir, "report", report)
    if stage == "01-ui-ux.design":
        await register_design_artifacts(conn, run_id, sdir)
    await conn.execute(
        "UPDATE stage_executions SET status = 'succeeded', output = $1, finished_at = now() WHERE id = $2",
        json.dumps({"final_output": tail, "report": report}), exec_id,
    )
    await log_event(conn, run_id, f"agent:{role}", "stage_succeeded", {"stage": stage})


# ── auto-coding: the HOST publishes the sandbox's branch (D14 / plan item C2.3) ──
# The sandbox commits on the run's branch and bundles it into the run folder; nothing
# in it can push. Here, with the token, the host verifies that bundle carries exactly
# the run's branch, lands it in the mirror, pushes it as the bot identity and opens
# (or reuses) the pull request — which becomes the code_complete gate's payload.

def _github_repo(url: str) -> tuple[str, str] | None:
    m = re.match(r"^https://github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", url.strip())
    return (m.group(1), m.group(2)) if m else None


def _gh_api(method: str, path: str, data: dict | None = None) -> tuple[int, object]:
    """One GitHub REST call with the host token; the token never reaches a log line."""
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        "https://api.github.com" + path, method=method, data=body,
        headers={"Authorization": f"Bearer {GIT_TOKEN}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "lantern-pipeline",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, (json.loads(raw) if raw else {})
        except ValueError:
            return e.code, {"message": _scrub(raw.decode(errors="replace"))[:300]}


def pr_body(run_id: str, handoff: dict, base: str) -> str:
    """The evidence pack a reviewer reads before approving code_complete."""
    d = REPO / "workflow" / "runs" / run_id
    title = _run_title(run_id) or run_id
    commits = handoff.get("commits", [])
    lines = [f"Lantern run `{run_id}` — **{title}**", "",
             f"Branch `{handoff['branch']}` → `{base}` · {len(commits)} commit(s)"
             + (" · leftovers auto-committed by the harness" if handoff.get("auto_committed") else ""),
             ""]
    if PUBLIC_URL:
        lines += [f"Mission Control: {PUBLIC_URL}/run/{run_id}", ""]
    lines += ["### Commits", ""]
    lines += [f"- `{str(c.get('sha', ''))[:8]}` {c.get('subject', '')}" for c in commits]
    lines += ["", "### Files", "", "```", (handoff.get("diffstat") or "")[-3000:], "```", ""]
    rep = d / "03-coding" / "report.md"
    if rep.is_file():
        text = rep.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^## Summary\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
        if m and m.group(1).strip():
            lines += ["### Coding report — summary", "", m.group(1).strip()[:2500], ""]
    lines += [f"Approved plan: `workflow/runs/{run_id}/02-pre-coding/task-plan.md` · "
              f"brief: `workflow/runs/{run_id}/brief.md`", "", "---",
              "Opened by the Lantern pipeline (stage 03-coding, auto mode). A human approves "
              "the `code_complete` gate in Mission Control to advance; QA, code review and "
              "security (stages 4–6) run on this branch before it is merged — "
              "**do not merge from here.**"]
    return "\n".join(lines)


def _open_or_find_pr(owner: str, name: str, branch: str, base: str, title: str, body: str) -> dict:
    status, found = _gh_api("GET", f"/repos/{owner}/{name}/pulls?state=open&head={owner}:{branch}")
    if status == 200 and isinstance(found, list) and found:
        pr = found[0]                     # a retry attempt updates the same PR
        _gh_api("POST", f"/repos/{owner}/{name}/issues/{pr['number']}/comments",
                {"body": "New attempt pushed by the Lantern pipeline.\n\n" + body})
        return {"pr_url": pr["html_url"], "pr_number": pr["number"], "pr_reused": True}
    status, pr = _gh_api("POST", f"/repos/{owner}/{name}/pulls",
                         {"title": title, "head": branch, "base": base, "body": body})
    if status not in (200, 201) or not isinstance(pr, dict) or "html_url" not in pr:
        raise RuntimeError(f"GitHub refused to open the PR ({status}): "
                           f"{_scrub(json.dumps(pr))[:400]}")
    # Labels are best-effort: a repo without the label set still gets its PR.
    _gh_api("POST", f"/repos/{owner}/{name}/labels",
            {"name": "agent:coding", "color": "5319e7",
             "description": "opened by Lantern's coding agent"})
    _gh_api("POST", f"/repos/{owner}/{name}/issues/{pr['number']}/labels",
            {"labels": ["agent:coding"]})
    return {"pr_url": pr["html_url"], "pr_number": pr["number"], "pr_reused": False}


def _publish_branch(run_id: str, repo: str, base: str, work: str = "") -> dict:
    """Verify the coding handoff against the host mirror, land the branch in it, push it
    to the origin (https remotes; a local-path product repo is updated in place) and
    open or reuse the pull request. Returns the code_complete payload. Sync, testable."""
    sdir = REPO / "workflow" / "runs" / run_id / "03-coding"
    hf = sdir / "handoff.json"
    if not hf.is_file():
        raise RuntimeError("no 03-coding/handoff.json — the coding stage produced no branch")
    handoff = json.loads(hf.read_text(encoding="utf-8"))
    branch = str(handoff.get("branch") or "")
    expected = work_branch(run_id, work)
    if branch != expected:
        raise RuntimeError(f"handoff names branch '{branch}', expected '{expected}'")
    mirror = sync_product_mirror(repo)
    problems = check_coding_handoff(run_id, "03-coding", verify_in=mirror)
    if problems:
        raise RuntimeError("coding handoff rejected: " + "; ".join(problems))
    bundle = REPO / handoff["bundle"]
    r = _git("fetch", "--quiet", str(bundle), f"+refs/heads/{branch}:refs/heads/{branch}", cwd=mirror)
    if r.returncode != 0:
        raise RuntimeError(f"could not land the bundle in the mirror: {_scrub(r.stderr)[-400:]}")
    head = _git("rev-parse", f"refs/heads/{branch}", cwd=mirror).stdout.strip()
    if head != handoff.get("head_sha"):
        raise RuntimeError("mirror head does not match the handoff — refusing to push")
    payload: dict = {
        "branch": branch, "base": base, "base_sha": handoff.get("base_sha"), "head_sha": head,
        "commit_count": len(handoff.get("commits", [])),
        "commits": handoff.get("commits", [])[:40],
        "files_changed": len(handoff.get("files_changed", [])),
        "auto_committed": bool(handoff.get("auto_committed")),
        "bundle": handoff["bundle"], "pushed": False, "pr_url": None, "pr_number": None,
    }
    if repo.startswith("https://"):
        r = _git("push", "--quiet", _authed(repo), f"refs/heads/{branch}:refs/heads/{branch}", cwd=mirror)
        if r.returncode != 0 and ("non-fast-forward" in r.stderr or "rejected" in r.stderr):
            # The branch belongs to this run: attempt N supersedes attempt N-1.
            r = _git("push", "--quiet", "--force", _authed(repo),
                     f"refs/heads/{branch}:refs/heads/{branch}", cwd=mirror)
        if r.returncode != 0:
            raise RuntimeError(f"push of {branch} failed: {_scrub(r.stderr)[-500:]}")
        payload["pushed"] = True
        gh = _github_repo(repo)
        if gh:
            payload["compare_url"] = f"https://github.com/{gh[0]}/{gh[1]}/compare/{base}...{branch}"
            if GIT_TOKEN:
                title = f"{run_id}: {_run_title(run_id) or 'feature'}"[:250]
                try:
                    payload.update(_open_or_find_pr(gh[0], gh[1], branch, base, title,
                                                    pr_body(run_id, handoff, base)))
                except (RuntimeError, urllib.error.URLError, OSError, KeyError, TypeError) as e:
                    # The code is done and pushed; a PR-API refusal (a token without
                    # pull-request permission, an outage) must not fail the stage.
                    # The gate opens on the branch + compare link, the reason is on
                    # record, and `pipeline.py publish <run-id>` retries the PR later.
                    payload["pr_error"] = _scrub(str(e))[:500]
            else:
                payload["pr_error"] = "no GITHUB_LANTERN_BOT_TOKEN on the host — branch pushed, PR not opened"
    # D4: the branch/PR facts reach the run folder, not only the approvals row.
    handoff.update({k: payload[k] for k in ("pushed", "pr_url", "pr_number", "pr_error") if k in payload})
    hf.write_text(json.dumps(handoff, indent=2), encoding="utf-8")
    (sdir / "pr.md").write_text(
        f"# Branch published — {run_id}\n\n- **Branch:** `{branch}` → `{base}`\n"
        f"- **Head:** `{head}`\n- **Pushed:** {payload['pushed']}\n"
        f"- **Pull request:** {payload.get('pr_url') or '(none)'}\n"
        + (f"- **Compare:** {payload['compare_url']}\n" if payload.get("compare_url") else "")
        + (f"- **PR not opened:** {payload['pr_error']} — fix the cause, then "
           f"`pipeline.py publish {run_id}`\n" if payload.get("pr_error") else "")
        + f"- **Commits:** {payload['commit_count']}\n", encoding="utf-8")
    return payload


async def publish_coding_branch(conn, run_id: str) -> dict:
    repo, base = await product_target(conn, run_id)
    if not repo:
        raise RuntimeError("auto-coding produced a branch but the run has no product repo to push to")
    work = await product_work_branch(conn, run_id)
    payload = await asyncio.to_thread(_publish_branch, run_id, repo, base, work)
    await insert_artifact(conn, run_id, "03-coding", "coding_branch", payload["bundle"],
                          {"branch": payload["branch"], "head_sha": payload["head_sha"],
                           "commits": payload["commit_count"]})
    if payload.get("pr_url"):
        await insert_artifact(conn, run_id, "03-coding", "pull_request", payload["pr_url"],
                              {"number": payload.get("pr_number")})
    await log_event(conn, run_id, "orchestrator", "branch_published",
                    {"branch": payload["branch"], "head_sha": payload["head_sha"],
                     "pushed": payload["pushed"], "pr_url": payload.get("pr_url")})
    if payload.get("pr_error"):
        await log_event(conn, run_id, "orchestrator", "pr_not_opened",
                        {"branch": payload["branch"], "error": payload["pr_error"]})
        print(f"[{run_id}] branch pushed but the PR was not opened: {payload['pr_error']}",
              file=sys.stderr)
    print(f"[{run_id}] branch {payload['branch']} published"
          + (f" — PR {payload['pr_url']}" if payload.get("pr_url") else ""))
    return payload


def prepare_coding_checkout(checkout: Path, branch: str) -> str:
    """In-process executor: put a fresh product checkout on the run's branch with the
    bot identity — the same thing the sandbox entrypoint does for containers.

    Returns the sha the branch is at BEFORE the agent runs (D15).
    """
    _git("config", "user.name", GIT_AUTHOR_NAME, cwd=checkout)
    _git("config", "user.email", GIT_AUTHOR_EMAIL, cwd=checkout)
    _git("config", "commit.gpgsign", "false", cwd=checkout)
    # D6 audit trail: the agent trailer on every commit, hook-enforced (same as the
    # sandbox entrypoint) rather than left to the model's memory.
    hook = checkout / ".git" / "hooks" / "prepare-commit-msg"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text('#!/bin/sh\ngrep -q "^Lantern-Agent:" "$1" || '
                    'printf "\\nLantern-Agent: coding\\n" >> "$1"\n', encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    # Three-armed since D15: product_checkout may ALREADY have landed us on the
    # working branch, and `checkout -b` on the current branch is a hard error.
    if _git("rev-parse", "--abbrev-ref", "HEAD", cwd=checkout).stdout.strip() == branch:
        r = _git("rev-parse", "HEAD", cwd=checkout)
    elif _git("rev-parse", "--verify", "-q", f"refs/remotes/origin/{branch}", cwd=checkout).returncode == 0:
        r = _git("checkout", "-q", "-b", branch, f"origin/{branch}", cwd=checkout)
    else:
        r = _git("checkout", "-q", "-b", branch, cwd=checkout)
    if r.returncode != 0:
        raise RuntimeError(f"could not create branch {branch}: {r.stderr.strip()[-300:]}")
    # D15: where THIS execution starts. The branch may already carry commits (a
    # continued branch, or a retry), so "did this stage do work" cannot be answered
    # against the base — see finalize_coding.
    return _git("rev-parse", "HEAD", cwd=checkout).stdout.strip()


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
        await insert_artifact(conn, run_id, sdir, kind, uri, meta)


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


async def open_gate(conn, run_id: str, stage: str, gate: str,
                    extra: dict | None = None, external_ref: str | None = None) -> None:
    payload: dict = {"stage": stage, "run_folder": f"workflow/runs/{run_id}/"}
    handoff = _read_handoff(run_id, STAGE_DIR[stage])
    if handoff is not None and handoff.get("kind") != "coding_branch":
        payload["handoff"] = handoff   # Mission Control renders paper_url + PNGs from this
    if extra:
        payload.update(extra)          # code_complete after auto-coding: branch + PR (D14)
    await conn.execute(
        """INSERT INTO approvals (run_id, gate, channel, payload, external_ref)
           VALUES ($1, $2, 'cli', $3, $4)""",
        run_id, gate, json.dumps(payload), external_ref,
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
    row = await conn.fetchrow("SELECT current_stage, coding_mode FROM runs WHERE id = $1", run_id)
    stage = row["current_stage"]
    mode = row["coding_mode"] or "human"
    _, _, stype, gate, _ = FEATURE_STAGES[STAGE_INDEX[stage]]
    extra: dict | None = None
    external_ref: str | None = None
    try:
        execute = run_agent_stage_docker if EXECUTOR == "docker" else run_agent_stage
        if stype == "agent":
            await execute(conn, run_id, stage, runner)
        elif stage == "03-coding" and mode == "auto":
            # D14: the coding agent implements the plan in a sandbox; the host then
            # verifies + pushes its branch and opens the PR — the gate's payload.
            await execute(conn, run_id, stage, runner)
            extra = await publish_coding_branch(conn, run_id)
            extra = await review.after_publish(conn, run_id, extra, runner,   # D19: review rounds
                                               review.default_deps(execute=execute))
            external_ref = extra.get("pr_url")
        else:  # human stage: nothing to execute — the gate IS the stage
            print(f"[{run_id}] {stage} is a human stage (the developer's own session).")
        if gate:
            await open_gate(conn, run_id, stage, gate, extra, external_ref)
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


async def cmd_run(brief_path: str, run_id: str | None, by: str, follow: bool,
                  product_repo: str = "", product_branch: str = "",
                  coding_mode: str = "", working_branch: str = "") -> None:
    brief = Path(brief_path)
    if not brief.exists():
        sys.exit(f"brief not found: {brief_path}")
    # Product target: --flag wins, then the brief's own field, then the box default.
    # Resolved at creation so the run records what it was pointed at, not what the
    # daemon's env happened to say three stages later.
    brief_text = brief.read_text(encoding="utf-8")
    brief_repo, brief_branch, brief_work = parse_brief_product(brief_text)
    product_repo = product_repo or brief_repo or PRODUCT_REPO_DEFAULT
    product_branch = product_branch or brief_branch or PRODUCT_BRANCH_DEFAULT
    # D15: no env default for the working branch on purpose — a box-wide one would
    # silently land every run on the same branch, the opposite of what it is for.
    working_branch = (working_branch or brief_work or "").strip()
    # Coding mode (D14): same precedence; 'human' unless someone asked for 'auto'.
    coding_mode = (coding_mode or parse_brief_coding_mode(brief_text) or "human").lower()
    if coding_mode not in CODING_MODES:
        sys.exit(f"coding mode must be one of {', '.join(CODING_MODES)} — got '{coding_mode}'")
    if coding_mode == "auto" and not product_repo:
        sys.exit("auto coding mode needs a product repo: add `- **Product repo:**` to the "
                 "brief or pass --product-repo")
    if product_repo:
        # Fail here, not inside a container three stages later.
        try:
            await asyncio.to_thread(verify_product_target, product_repo,
                                    product_branch, working_branch)
        except ProductTargetError as e:
            sys.exit(f"{e}\nbranches: {', '.join(e.branches) or '(none)'}")
    else:
        print("WARNING: no product repo for this run — stages 2+ will block asking for "
              "one. Set it with `pipeline.py set-product <run-id> --repo … --branch … "
              "[--working-branch …]`, add a `- **Product repo:**` line to the brief, or "
              "pick one in Mission Control at /run/<run-id>/repo.", file=sys.stderr)
    if not run_id:
        run_id = f"feat-{datetime.now(timezone.utc):%Y%m%d}-{brief.stem.lstrip('_').lower()}"
    run_dir = REPO / "workflow" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "brief.md").write_text(brief.read_text(encoding="utf-8"), encoding="utf-8")

    conn = await connect()
    await conn.execute(
        """INSERT INTO runs (id, brief, pipeline_version, current_stage, created_by,
                             product_repo, product_branch, product_working_branch,
                             coding_mode)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
        run_id, str(brief), PIPELINE_VERSION, FEATURE_STAGES[0][0], by,
        product_repo or None, product_branch or None, working_branch or None, coding_mode)
    await log_event(conn, run_id, f"human:{by}", "run_created",
                    {"brief": str(brief), "product_repo": product_repo,
                     "product_branch": product_branch,
                     "product_working_branch": working_branch, "coding_mode": coding_mode})
    await render_runboard(conn)
    print(f"run {run_id} created (coding mode: {coding_mode}) — the pipeline takes it from here.")
    if product_repo:
        print(f"  work lands on: {work_branch(run_id, working_branch)}")
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
    if runner == "ec2":
        loaded, missing = await asyncio.to_thread(load_ssm_qa_env)
        if loaded:
            print(f"QA targets loaded from SSM: {', '.join(loaded)}")
        if missing:
            print(f"QA targets not configured: {', '.join(missing)} — QA stages will run "
                  f"against no target until these exist (see `pipeline.py qa-preflight`)")
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
            if runner == "ec2" and review.babysit_due():   # D19: merge babysitter, own slot + connection
                slots.add(asyncio.create_task(review.babysit_slot(connect, runner)))
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


def record_gate_decision(run_id: str, gate: str, status: str, by: str, note: str) -> None:
    """Write a gate decision into the RUN FOLDER, not just the approvals table.

    D4 makes the run folder the only handoff channel, and agents have no read path
    to Postgres — so a decision that lives only in `approvals` is invisible to every
    downstream stage. Found by a real run 2026-08-27: pre-coding reported that "a
    recommendation is not approval" and had to treat the chosen UX option as unknown
    while the approval sat in the database. Append-only; the table remains the source
    of truth for authority, this file is the readable trail agents orient on.
    """
    f = REPO / "workflow" / "runs" / run_id / "gate-decisions.md"
    stamp = f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC"
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        new = not f.exists()
        with f.open("a", encoding="utf-8") as fh:
            if new:
                fh.write("# Gate decisions\n\nRendered by the orchestrator when a gate is "
                         "decided. The `approvals` table is the source of truth for "
                         "authority; this file is what downstream agents read (D4).\n")
            fh.write(f"\n## {gate} — {status.upper()}\n\n"
                     f"- **Decided by:** {by}\n"
                     f"- **When:** {stamp}\n"
                     f"- **Note:** {note or '(none)'}\n")
    except OSError as e:   # never fail a gate decision over a file write
        print(f"[{run_id}] warning: could not write gate-decisions.md: {e}", file=sys.stderr)


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
    record_gate_decision(run_id, gate, status, by, note)
    if approved:
        stage = await conn.fetchval("SELECT current_stage FROM runs WHERE id = $1", run_id)
        await advance(conn, run_id, stage)
        print(f"[{run_id}] {gate} approved by {by} — advancing.")
    else:
        await conn.execute("UPDATE runs SET status = 'failed', updated_at = now() WHERE id = $1", run_id)
        print(f"[{run_id}] {gate} rejected by {by} — run marked failed; rework then `retry`.")
    await render_runboard(conn)
    await conn.close()


def product_checkout(repo: str, branch: str, run_id: str, work: str = "") -> Path:
    """Host-side working checkout of the product for the in-process executor.

    Cloned fresh from the mirror every stage, so a stage can never read a tree some
    earlier stage left dirty. The docker executor does not use this — its container
    clones from the read-only mount instead.

    `work` (D15) is the run's working branch: when the mirror already has it, land on
    it so the stage reads the code the run is actually working on. When it does not
    exist yet we stay on the base — creating it belongs to prepare_coding_checkout,
    and a read-only stage has no business creating branches at all.
    """
    mirror = sync_product_mirror(repo)
    dest = PRODUCT_MIRROR_DIR / "checkouts" / run_id
    if dest.exists():
        # D19: force_rmtree, not ignore_errors — git's objects are read-only, so on
        # Windows the old call silently left the tree and the clone below failed with
        # "already exists and is not an empty directory" for EVERY stage after the
        # coding stage of the same run (found by the first live review round).
        review.force_rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = _git("clone", "--no-hardlinks", "--branch", branch, str(mirror), str(dest))
    if r.returncode != 0:
        raise RuntimeError(
            f"product checkout of branch '{branch}' failed: {_scrub(r.stderr)[-600:]}")
    if work and work != branch and _git(
            "rev-parse", "--verify", "-q", f"refs/remotes/origin/{work}",
            cwd=dest).returncode == 0:
        c = _git("checkout", "-q", work, cwd=dest)
        if c.returncode != 0:
            raise RuntimeError(
                f"product checkout of working branch '{work}' failed: "
                f"{_scrub(c.stderr)[-600:]}")
    return dest


def cmd_repos() -> None:
    """Git repos this host can offer as a product target (D15).

    The same view Mission Control's picker shows, with no browser — and the quickest
    way to find out why the picker is empty on a given box. `workspace` is imported
    lazily and from mission-control on purpose: the daemon imports this module, and
    the filesystem-walk surface has no business living in the daemon.
    """
    sys.path.insert(0, str(REPO / "tools" / "mission-control"))
    import workspace   # noqa: PLC0415 — deliberately lazy, see above

    roots = workspace.workspace_roots()
    if not roots:
        print("no workspace roots configured — the picker offers nothing.\n"
              "Set LANTERN_WORKSPACE_ROOTS (os.pathsep-separated) to the directories "
              "holding your repos,\nor create ~/work. This is a security boundary: "
              "unset fails closed on purpose.")
        return
    print("roots: " + ", ".join(str(r) for r in roots))
    repos = workspace.discover_repos(use_cache=False)
    if not repos:
        print("(no git repos found under those roots)")
        return
    width = max(len(r["name"]) for r in repos)
    for r in repos:
        print(f"  {r['name']:<{width}}  {r['head_branch'] or '?':<24}  {r['path']}")
    print(f"\n{len(repos)} repo(s). Point a run at one with:\n"
          f"  pipeline.py set-product <run-id> --repo <path> --branch <base> "
          f"[--working-branch feat/…]")


class ProductTargetError(RuntimeError):
    """A product target that cannot be honoured. Carries the repo's branch list so a
    caller (CLI or web) can show what WAS available instead of a bare refusal."""

    def __init__(self, message: str, branches: list[str] | None = None):
        super().__init__(message)
        self.branches = branches or []


def _branch_heads(mirror: Path) -> list[str]:
    r = _git("for-each-ref", "--format=%(refname:short)", "refs/heads", cwd=mirror)
    return sorted(b for b in r.stdout.split() if b)


def verify_product_target(repo: str, base: str, working: str = "") -> dict:
    """Sync the host mirror and prove the branches exist. Sync, no DB, testable.

    Verification is the point: a run recorded against a repo the box cannot clone
    would fail one stage later, inside a container, as an opaque sandbox error.

    A MISSING working branch is not an error — it means "create it from the base when
    coding starts", so working_sha comes back None. A working branch outside the
    pushable namespace IS an error: D6 bounds what an agent may push to, and refusing
    at selection time beats refusing three stages later at handoff.

    Returns {'mirror', 'base_sha', 'working', 'working_sha', 'branches', 'local'}.
    """
    if not repo:
        raise ProductTargetError("no product repo given")
    mirror = sync_product_mirror(repo)
    heads = _branch_heads(mirror)
    r = _git("rev-parse", "--verify", f"refs/heads/{base}", cwd=mirror)
    if r.returncode != 0:
        raise ProductTargetError(f"branch '{base}' not found in {repo}", heads)
    working = (working or "").strip()
    working_sha = None
    if working:
        if _git("check-ref-format", f"refs/heads/{working}").returncode != 0:
            raise ProductTargetError(f"'{working}' is not a valid git branch name", heads)
        if not working.startswith(CODING_BRANCH_PREFIXES):
            ns = ", ".join(pre + "*" for pre in CODING_BRANCH_PREFIXES)
            raise ProductTargetError(
                f"working branch '{working}' is outside the namespace agents may push "
                f"to ({ns}) — D6. Pick a branch in that namespace, or leave it unset to "
                "get a fresh one derived from the run id.", heads)
        w = _git("rev-parse", "--verify", f"refs/heads/{working}", cwd=mirror)
        working_sha = w.stdout.strip() if w.returncode == 0 else None
    return {"mirror": mirror, "base_sha": r.stdout.strip(), "working": working,
            "working_sha": working_sha, "branches": heads,
            "local": not repo.startswith(("http://", "https://", "git@", "ssh://"))}


async def cmd_set_product(run_id: str, repo: str, branch: str, working: str = "") -> None:
    """Point an existing run at a product repo/branch (and optionally an existing
    working branch to continue on) and verify the host can reach it."""
    conn = await connect()
    if not await conn.fetchval("SELECT 1 FROM runs WHERE id = $1", run_id):
        await conn.close()
        sys.exit(f"unknown run: {run_id}")
    print(f"syncing host mirror for {repo} …")
    try:
        info = await asyncio.to_thread(verify_product_target, repo, branch, working)
    except ProductTargetError as e:
        await conn.close()
        sys.exit(f"{e}\nbranches: {', '.join(e.branches) or '(none)'}")
    await conn.execute(
        """UPDATE runs SET product_repo = $1, product_branch = $2,
                           product_working_branch = $3, updated_at = now()
           WHERE id = $4""",
        repo, branch, info["working"] or None, run_id)
    await log_event(conn, run_id, "human:cli", "product_target_set",
                    {"repo": repo, "branch": branch, "working": info["working"],
                     "head": info["base_sha"][:12], "channel": "cli"})
    await conn.close()
    landed = work_branch(run_id, info["working"])
    fate = ("continues an existing branch" if info["working_sha"]
            else "will be created at the first commit")
    print(f"[{run_id}] product target set: {repo} @ {branch} ({info['base_sha'][:12]})\n"
          f"  mirror: {info['mirror']}\n"
          f"  work lands on: {landed} — {fate}\n"
          f"  stages from here on get it read-only at the `product/` prefix.")
    if info["local"]:
        print("  NOTE: a local-path target is never fetched — the pipeline sees COMMITTED\n"
              "  state only. Uncommitted work in that checkout is invisible to agents.")


async def cmd_publish(run_id: str) -> None:
    """(Re)publish an auto-coding run's branch and PR from its 03-coding handoff (D14).

    For the two ways the last step can fall behind the code: the stage failed AFTER the
    agent's work was bundled (a push or API refusal), or the gate opened without a PR
    (`pr_error` in its payload — e.g. a token that cannot open pull requests). Pushes
    are idempotent; an existing open PR is reused; a pending code_complete gate gets
    its payload refreshed instead of a duplicate row."""
    conn = await connect()
    row = await conn.fetchrow(
        "SELECT status, current_stage, coding_mode FROM runs WHERE id = $1", run_id)
    if not row:
        await conn.close()
        sys.exit(f"unknown run: {run_id}")
    if row["current_stage"] != "03-coding" or row["coding_mode"] != "auto":
        await conn.close()
        sys.exit(f"{run_id} is not an auto-coding run at 03-coding "
                 f"(stage {row['current_stage']}, mode {row['coding_mode']})")
    payload = await publish_coding_branch(conn, run_id)
    pending = await conn.fetchrow(
        "SELECT id, payload FROM approvals WHERE run_id = $1 AND gate = 'code_complete' "
        "AND status = 'pending'", run_id)
    if pending:
        merged = _payload_dict(pending["payload"])
        merged.pop("pr_error", None)
        merged.update(payload)
        await conn.execute(
            "UPDATE approvals SET payload = $1, external_ref = $2 WHERE id = $3",
            json.dumps(merged), payload.get("pr_url"), pending["id"])
        await log_event(conn, run_id, "human:cli", "gate_payload_refreshed",
                        {"gate": "code_complete", "pr_url": payload.get("pr_url")})
        print(f"[{run_id}] code_complete gate refreshed"
              + (f" — PR {payload['pr_url']}" if payload.get("pr_url") else ""))
    else:
        await open_gate(conn, run_id, "03-coding", "code_complete", payload, payload.get("pr_url"))
    await render_runboard(conn)
    await conn.close()
    if payload.get("pr_error"):
        print(f"[{run_id}] PR still not opened: {payload['pr_error']}", file=sys.stderr)


def _payload_dict(raw) -> dict:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return {}
    return dict(raw or {})


async def cmd_set_coding_mode(run_id: str, mode: str) -> None:
    """Switch stage 3 of an existing run between the developer's own session and the
    fleet's coding agent (D14). Allowed until the run has passed stage 3."""
    if mode not in CODING_MODES:
        sys.exit(f"mode must be one of {', '.join(CODING_MODES)}")
    conn = await connect()
    row = await conn.fetchrow("SELECT current_stage, product_repo FROM runs WHERE id = $1", run_id)
    if not row:
        await conn.close()
        sys.exit(f"unknown run: {run_id}")
    if STAGE_INDEX.get(row["current_stage"], 0) > STAGE_INDEX["03-coding"]:
        await conn.close()
        sys.exit(f"{run_id} is already past stage 3 ({row['current_stage']})")
    if mode == "auto" and not (row["product_repo"] or PRODUCT_REPO_DEFAULT):
        await conn.close()
        sys.exit("auto coding needs a product repo — run `pipeline.py set-product` first")
    await conn.execute("UPDATE runs SET coding_mode = $1, updated_at = now() WHERE id = $2", mode, run_id)
    await log_event(conn, run_id, "human:cli", "coding_mode_set", {"mode": mode})
    await conn.close()
    print(f"[{run_id}] coding mode: {mode}")


# ── QA target credentials from SSM (P0.1's documented path, made real) ───────
# infra/ec2/README.md has always said these come from /lantern/qa/{dev,staging}/*,
# but nothing read them at runtime: the daemon loads a hand-written .env, so the
# documented mechanism only worked if a human copied the values by hand. Fill the
# gap here — env/.env still wins, so laptops and the workstation are unaffected.
QA_SSM_PARAMS = {
    "LANTERN_QA_DEV_BASE_URL": "/lantern/qa/dev/base_url",
    "LANTERN_QA_DEV_USER": "/lantern/qa/dev/user",
    "LANTERN_QA_DEV_PASS": "/lantern/qa/dev/pass",
    "LANTERN_QA_STAGING_BASE_URL": "/lantern/qa/staging/base_url",
    "LANTERN_QA_STAGING_USER": "/lantern/qa/staging/user",
    "LANTERN_QA_STAGING_PASS": "/lantern/qa/staging/pass",
}


def load_ssm_qa_env() -> tuple[list[str], list[str]]:
    """Fill unset LANTERN_QA_* from SSM. Returns (loaded_names, missing_names).

    Values are never printed or logged — only names. A missing parameter is normal
    (no staging target yet) and is not an error; an unusable aws CLI is reported once.
    """
    loaded, missing = [], []
    for var, path in QA_SSM_PARAMS.items():
        if os.environ.get(var):
            continue
        try:
            r = subprocess.run(
                ["aws", "ssm", "get-parameter", "--name", path, "--with-decryption",
                 "--query", "Parameter.Value", "--output", "text"],
                capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            return loaded, list(QA_SSM_PARAMS)      # no aws CLI / no route: all missing
        value = r.stdout.strip()
        if r.returncode == 0 and value and value != "None":
            os.environ[var] = value
            loaded.append(var)
        else:
            missing.append(var)
    return loaded, missing


async def cmd_qa_preflight(role: str) -> None:
    """Can a QA stage actually reach its target? Answer before burning a stage run.

    Checks the three things that each fail differently: the credentials are
    configured, the HOST can reach the target, and — the one that actually decides
    whether stage 4 works — a SANDBOX CONTAINER can reach it. A dev environment on
    localhost, behind Tailscale, or inside a VPC the container's network namespace
    cannot see passes the first two checks and fails the third.
    """
    prefix = QA_TARGET_PREFIX[role]
    # qa_stage_env keys off the STAGE ('04-qa-dev'), not the role — resolve it from the
    # feature pipeline so this cannot drift from what the dispatcher actually maps.
    # (ROLE_FOR_STAGE also maps the debug lifecycle's '05-regression' to qa-dev; both
    # resolve to the same env prefix, but the feature stage is the one being previewed.)
    stage = next(k for k, *_ in FEATURE_STAGES if ROLE_FOR_STAGE.get(k) == role)
    loaded, _ = load_ssm_qa_env()
    if loaded:
        print(f"loaded from SSM: {', '.join(loaded)}")
    base = os.environ.get(prefix + "_BASE_URL", "")
    user = os.environ.get(prefix + "_USER", "")
    pw = os.environ.get(prefix + "_PASS", "")

    print(f"\n{stage} target")
    print(f"  {prefix}_BASE_URL  {base or '(unset)'}")
    print(f"  {prefix}_USER      {'set' if user else '(unset)'}")
    print(f"  {prefix}_PASS      {'set' if pw else '(unset)'}")
    if not base:
        sys.exit(f"\nNOT CONFIGURED. Put the values in SSM ({QA_SSM_PARAMS[prefix + '_BASE_URL']} "
                 f"and _user/_pass as SecureString), or set them in .env, then re-run this.")

    def curl(argv: list[str]) -> tuple[str, str]:
        try:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=45)
            return r.stdout.strip(), r.stderr.strip()[-200:]
        except (OSError, subprocess.TimeoutExpired) as e:
            return "", str(e)[-200:]

    print("\nreachability")
    code, err = curl(["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}",
                      "--max-time", "30", base])
    print(f"  host      HTTP {code or 'FAILED'}{'  ' + err if err else ''}")

    # The sandbox check uses the real image and the real per-stage env mapping, so a
    # pass here means stage 4's container sees exactly this.
    if EXECUTOR == "docker":
        cmd = ["docker", "run", "--rm", "--add-host=host.docker.internal:host-gateway",
               "--entrypoint", "curl"]
        for inner, value in qa_stage_env(stage).items():
            if inner != "QA_PASS":
                cmd += ["-e", f"{inner}={value}"]
        cmd += [SANDBOX_IMAGE, "-sS", "-o", "/dev/null", "-w", "%{http_code}",
                "--max-time", "30", base]
        code2, err2 = curl(cmd)
        print(f"  sandbox   HTTP {code2 or 'FAILED'}{'  ' + err2 if err2 else ''}")
        ok = code2.startswith(("2", "3", "401", "403"))
        # Reachability is not readiness: the first daemon-driven stage 4 (2026-09-07)
        # reached the login page and still could not get in. Try the provisioned
        # login from inside a sandbox, credentials passed as env (never on argv).
        # Mission-Control-shaped form: POST /login with username/password answers
        # 303 on success and re-renders (200) on a rejected login.
        if ok and user and pw:
            probe = ["docker", "run", "--rm", "--add-host=host.docker.internal:host-gateway",
                     "-e", f"QA_BASE_URL={base}", "-e", f"QA_USER={user}", "-e", f"QA_PASS={pw}",
                     "--entrypoint", "sh", SANDBOX_IMAGE, "-c",
                     'curl -sS -o /dev/null -w "%{http_code}" --max-time 30 -X POST '
                     '--data-urlencode "username=$QA_USER" --data-urlencode "password=$QA_PASS" '
                     '"$QA_BASE_URL/login"']
            code3, err3 = curl(probe)
            accepted = code3.startswith("3")
            print(f"  login     HTTP {code3 or 'FAILED'}  "
                  f"({'accepted' if accepted else 'REJECTED — the QA user/password do not log in (or the form is not Mission-Control-shaped)'})"
                  f"{'  ' + err3 if err3 else ''}")
            ok = ok and accepted
        print("\n" + ("READY — a QA stage can reach this target." if ok else
                      "NOT REACHABLE FROM A SANDBOX. The host result above does not matter: "
                      "stage 4 runs in a container. A localhost-only, Tailscale-only, or "
                      "VPC-internal dev environment needs a route into the container network "
                      "(host.docker.internal, a published port, or a reachable hostname)."))
    else:
        print("  sandbox   (skipped — LANTERN_EXECUTOR is not 'docker' here)")


REWORK_TARGETS = ("02-pre-coding", "03-coding", "04-qa-dev")


async def cmd_rework(run_id: str, to_stage: str, by: str, note: str) -> None:
    """Send a run BACK to an earlier stage — the loop the software-factory designs run
    as code (D17): a failed validation or a QA round returns to the builder without a
    new run. Only backwards, only to a REWORK_TARGETS stage, only from failed or
    waiting_gate; pending approvals expire; the decision lands in gate-decisions.md."""
    if to_stage not in REWORK_TARGETS:
        sys.exit(f"rework target must be one of {', '.join(REWORK_TARGETS)}")
    conn = await connect()
    row = await conn.fetchrow("SELECT status, current_stage FROM runs WHERE id = $1", run_id)
    if not row:
        sys.exit(f"unknown run {run_id}")
    if row["status"] not in ("failed", "waiting_gate"):
        sys.exit(f"{run_id} is {row['status']} — rework applies to failed or waiting_gate runs")
    if STAGE_INDEX.get(to_stage, 99) >= STAGE_INDEX.get(row["current_stage"], -1):
        sys.exit(f"{to_stage} is not earlier than the run's current stage {row['current_stage']}")
    await conn.execute(
        """UPDATE approvals SET status = 'expired', decided_at = now(), decided_by = $2,
           decision_note = $3 WHERE run_id = $1 AND status = 'pending'""",
        run_id, by, f"expired by rework to {to_stage}")
    await conn.execute(
        "UPDATE runs SET current_stage = $1, status = 'running', updated_at = now() WHERE id = $2",
        to_stage, run_id)
    await log_event(conn, run_id, f"human:{by}", "run_reworked",
                    {"from": row["current_stage"], "to": to_stage, "note": note})
    record_gate_decision(run_id, f"rework -> {to_stage}", "reworked", by,
                         note or f"sent back from {row['current_stage']}")
    await render_runboard(conn)
    print(f"[{run_id}] sent back to {to_stage} (from {row['current_stage']}) — the daemon "
          "picks it up: same branch, same session memory, fresh attempt.")
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
            model_settings=model_settings_for(role, purpose="chat"),
            instructions=build_consult_instructions(role),
            tools=[read_file, list_dir,
                   make_append_memory(role, None, None, session_id)],
            mcp_servers=mcp_servers,
        )

        async def turn(text: str) -> None:
            result = await Runner.run(agent, input=text, session=session, max_turns=40)
            print(f"\n[{role} · {model_for(role)}]\n{result.final_output}\n")
            await log_event(conn, None, f"human:{by}", "consult",
                            {"role": role, "session": session_name, "prompt": text[:300],
                             "usage": usage_dict(result)})   # consults burn credits too

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


def status_payload(runs, pending_gates) -> dict:
    """Shape status query rows for machine-readable output."""
    return {
        "runs": [
            {
                "id": r["id"],
                "status": r["status"],
                "current_stage": r["current_stage"],
                "updated_at": r["updated_at"].isoformat(),
                "coding_mode": r["coding_mode"],
                "product_repo": r["product_repo"],
            }
            for r in runs
        ],
        "pending_gates": [
            {
                "run_id": p["run_id"],
                "gate": p["gate"],
                "requested_at": p["requested_at"].isoformat(),
            }
            for p in pending_gates
        ],
    }


async def cmd_status(json_mode: bool = False) -> None:
    conn = await connect()
    runs = await conn.fetch(
        """SELECT id, status, current_stage, updated_at, coding_mode, product_repo FROM runs
           WHERE status NOT IN ('done', 'cancelled') ORDER BY updated_at DESC""")
    pend = await conn.fetch("SELECT run_id, gate, requested_at FROM approvals WHERE status = 'pending'")
    if json_mode:
        print(json.dumps(status_payload(runs, pend)))
    else:
        if not runs:
            print("no active runs")
        for r in runs:
            tag = "  [auto-coding]" if r["coding_mode"] == "auto" else ""
            print(f"{r['id']:<40} {r['status']:<13} {r['current_stage']:<18} updated {r['updated_at']:%Y-%m-%d %H:%M}{tag}")
        for p in pend:
            # plain ASCII: Windows consoles default to cp1252 and choke on emoji/arrows
            print(f"  pending gate: {p['run_id']} -> {p['gate']} (since {p['requested_at']:%Y-%m-%d %H:%M})")
    await conn.close()


def _post_alarm(text: str) -> None:
    """Deliver an alarm line: webhook if configured (Slack-compatible payload),
    stdout either way (systemd journal keeps it)."""
    print(text)
    hook = os.environ.get("LANTERN_ALARM_WEBHOOK")
    if not hook:
        return
    import urllib.request
    req = urllib.request.Request(
        hook, data=json.dumps({"text": text}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except OSError as e:
        print(f"alarm webhook failed: {e}", file=sys.stderr)


# Aggregate fragment shared by every ledger query. ::bigint matters: Postgres
# sum(bigint) is numeric, which asyncpg decodes as Decimal — and Decimal * float
# rates would TypeError the moment real data exists. Grouped by model because the
# fleet routes across two price classes (see _price_rates).
USAGE_COLS = """model,
           coalesce(sum(input_tokens), 0)::bigint        AS inp,
           coalesce(sum(cached_input_tokens), 0)::bigint AS cached,
           coalesce(sum(output_tokens), 0)::bigint       AS outp,
           count(*)::bigint                              AS n,
           count(*) FILTER (WHERE total_tokens IS NULL)::bigint AS unmetered"""


async def cmd_usage(days: int) -> None:
    """Token + estimated-spend report from the ledger (P0.4)."""
    conn = await connect()
    daily = await conn.fetch(
        f"""SELECT date_trunc('day', started_at)::date AS day, {USAGE_COLS}
            FROM stage_executions
            WHERE started_at >= now() - make_interval(days => $1)
            GROUP BY 1, model ORDER BY 1 DESC""", days)
    print(f"last {days} days (rates are estimates until Azure invoice lines confirm them):")
    print(f"{'day':<12}{'model':<12}{'stages':>7}{'input':>14}{'cached':>12}{'output':>12}{'est $':>10}")
    unmetered = 0
    for r in daily:
        cost = est_cost_usd(r["inp"], r["cached"], r["outp"], r["model"])
        unmetered += r["unmetered"]
        print(f"{r['day']:%Y-%m-%d}  {(r['model'] or '?'):<12}{r['n']:>7}"
              f"{r['inp']:>14,}{r['cached']:>12,}{r['outp']:>12,}{cost:>10.2f}")
    if not daily:
        print("  (no executions yet)")
    if unmetered:
        print(f"  NOTE: {unmetered} execution(s) have no token counts (crashed/killed "
              "before reporting) — real spend is higher than shown")
    top = await conn.fetch(
        f"""SELECT run_id, {USAGE_COLS}
            FROM stage_executions
            WHERE started_at >= now() - make_interval(days => $1)
            GROUP BY run_id, model ORDER BY coalesce(sum(total_tokens), 0) DESC LIMIT 20""", days)
    if top:
        print("\ntop runs:")
        for r in top:
            cost = est_cost_usd(r["inp"], r["cached"], r["outp"], r["model"])
            print(f"  {r['run_id']:<40}{(r['model'] or '?'):<12}{r['inp']:>14,}{r['outp']:>12,}{cost:>10.2f}")
    await conn.close()


async def cmd_usage_check() -> None:
    """The spend tripwires (plan §5): run hourly from lantern-usage-check.timer.

    Two ceilings, two alarms — both dedupe through the events table so a crossed
    threshold alerts once (daily for the rate alarm, once ever per pool threshold):
      1. rate:  today's est spend > LANTERN_DAILY_SPEND_ALARM_USD (default 50 — the
                plan §5 v3 recalibration: at ~$0.50/stage-execution, the old $1,200
                was ~2,400 executions of headroom, i.e. decoration, not an alarm)
      2. pool:  cumulative est spend (+ LANTERN_POOL_SPENT_OFFSET_USD for pre-ledger
                burn) crosses 25/50/75% of LANTERN_CREDIT_POOL_USD (default 25000)

    Known undercount, on the record: executions that crash or get docker-killed
    before the usage line prints leave NULL token columns — `usage` surfaces the
    count, and the alarms fire on what IS metered.
    """
    conn = await connect()
    today_rows = await conn.fetch(
        f"""SELECT {USAGE_COLS} FROM stage_executions
            WHERE started_at >= date_trunc('day', now()) GROUP BY model""")
    today_cost = est_cost_rows(today_rows)
    daily_limit = float(os.environ.get("LANTERN_DAILY_SPEND_ALARM_USD", "50"))
    if today_cost > daily_limit:
        already = await conn.fetchval(
            """SELECT 1 FROM events WHERE actor = 'usage-check' AND type = 'spend_alarm'
               AND at >= date_trunc('day', now())""")
        if not already:
            # plain ASCII (see cmd_status note): cp1252 consoles choke on fancy glyphs
            _post_alarm(f":rotating_light: Lantern model spend today ~${today_cost:,.0f} "
                        f"(> ${daily_limit:,.0f}/day tripwire). Check `pipeline.py usage` "
                        "for the run responsible — unattended retries are the known blow-up mode.")
            await log_event(conn, None, "usage-check", "spend_alarm",
                            {"est_usd": round(today_cost, 2), "limit": daily_limit})

    alltime_rows = await conn.fetch(
        f"SELECT {USAGE_COLS} FROM stage_executions GROUP BY model")
    pool = float(os.environ.get("LANTERN_CREDIT_POOL_USD", "25000"))
    offset = float(os.environ.get("LANTERN_POOL_SPENT_OFFSET_USD", "0"))
    drawn = est_cost_rows(alltime_rows) + offset
    for pct in (75, 50, 25):
        if drawn >= pool * pct / 100:
            already = await conn.fetchval(
                """SELECT 1 FROM events WHERE actor = 'usage-check' AND type = 'pool_alarm'
                   AND (data->>'threshold')::int = $1""", pct)
            if not already:
                _post_alarm(f":warning: Lantern has drawn ~${drawn:,.0f} of the "
                            f"${pool:,.0f} Azure credit pool ({pct}% threshold). "
                            "Per the plan: decide post-credit budget vs throttle "
                            "before the 75% mark — auto-coding is the spend to cut first.")
                await log_event(conn, None, "usage-check", "pool_alarm",
                                {"threshold": pct, "est_drawn_usd": round(drawn, 2)})
            break   # highest crossed threshold only; lower ones are implied
    print(f"usage-check: today ~${today_cost:,.2f}, pool drawn ~${drawn:,.0f}/{pool:,.0f}")
    await conn.close()


# Commands that touch neither a model nor the database, and so must not require Azure
# credentials to be configured. `repos` answers "what can this host offer as a product
# target" — often the first thing an operator runs on a box, before the fleet is wired.
LOCAL_ONLY_CMDS = {"repos"}


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in LOCAL_ONLY_CMDS:
        {"repos": cmd_repos}[sys.argv[1]]()
        return
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
    p.add_argument("--product-repo", default="",
                   help="product repo URL or on-box path (default: the brief's field, then "
                        "LANTERN_PRODUCT_REPO)")
    p.add_argument("--product-branch", default="", help="base branch (default: the brief's field, then main)")
    p.add_argument("--coding-mode", choices=CODING_MODES, default="",
                   help="human = the developer's own session (default); auto = the coding "
                        "agent implements the plan and the host opens a PR (D14)")
    p.add_argument("--working-branch", default="",
                   help="existing branch to continue on (feat/*|fix/*|proto/*); default: "
                        "a fresh branch derived from the run id")
    p = sub.add_parser("set-product", help="point an existing run at a product repo/branch")
    p.add_argument("run_id"); p.add_argument("--repo", required=True)
    p.add_argument("--branch", default=PRODUCT_BRANCH_DEFAULT, help="base branch")
    p.add_argument("--working-branch", default="",
                   help="existing branch to continue on (feat/*|fix/*|proto/*); default: "
                        "a fresh branch derived from the run id")
    p = sub.add_parser("repos", help="git repos this host can offer as a product target "
                                     "(LANTERN_WORKSPACE_ROOTS)")
    p = sub.add_parser("set-coding-mode", help="human (developer's own session) or auto "
                                               "(the coding agent implements the plan → PR)")
    p.add_argument("run_id"); p.add_argument("mode", choices=CODING_MODES)
    p = sub.add_parser("publish", help="(re)push an auto-coding run's branch and open/refresh "
                                       "its PR from the 03-coding handoff")
    p.add_argument("run_id")
    p = sub.add_parser("daemon")
    p.add_argument("--runner", choices=["ec2", "workstation"],
                   default=os.environ.get("LANTERN_RUNNER", "ec2"))
    for name in ("approve", "reject"):
        p = sub.add_parser(name); p.add_argument("run_id"); p.add_argument("gate")
        p.add_argument("--by", required=True); p.add_argument("--note", default="")
    p = sub.add_parser("retry"); p.add_argument("run_id")
    p = sub.add_parser("rework", help="send a failed/waiting run back to an earlier stage "
                                      "(D17 loop: validation or QA findings → the builder)")
    p.add_argument("run_id"); p.add_argument("--to", required=True, choices=REWORK_TARGETS)
    p.add_argument("--by", default=os.environ.get("USERNAME") or os.environ.get("USER", "unknown"))
    p.add_argument("--note", default="")
    p = sub.add_parser("qa-preflight", help="can a QA stage reach its target, from the sandbox?")
    p.add_argument("--stage", choices=sorted(QA_TARGET_PREFIX), default="qa-dev")
    p = sub.add_parser("status"); p.add_argument("--json", action="store_true")
    sub.add_parser("agents")
    p = sub.add_parser("ask"); p.add_argument("role"); p.add_argument("prompt")
    p.add_argument("--session", default="default",
                   help="named conversation; follow-up asks with the same name continue it")
    p.add_argument("--by", default=os.environ.get("USERNAME") or os.environ.get("USER", "unknown"))
    p.add_argument("--new", action="store_true", help="clear this session and start fresh")
    p.add_argument("-i", "--interactive", action="store_true", help="keep prompting in a loop")
    p.add_argument("--no-browser", action="store_true", help="skip the Playwright MCP for browser roles")
    sub.add_parser("runboard")
    p = sub.add_parser("usage"); p.add_argument("--days", type=int, default=7)
    sub.add_parser("usage-check")
    p = sub.add_parser("render-memory"); p.add_argument("--role")
    p = sub.add_parser("import-run"); p.add_argument("run_id")
    p.add_argument("--by", default="justin"); p.add_argument("--stage", default="01-ui-ux.design")
    p.add_argument("--status", default="waiting_gate"); p.add_argument("--gate")
    # D19
    p = sub.add_parser("babysit", help="keep an approved run's branch mergeable: merge the base in, "
                                       "re-run the quality gate, push — never merges into the base")
    p.add_argument("run_id", nargs="?", help="one run; omit for every eligible run")
    p.add_argument("--force", action="store_true",
                   help="retry even if the last attempt failed at this same base commit")
    a = ap.parse_args()

    match a.cmd:
        case "init-db": asyncio.run(cmd_init_db())
        case "run":     asyncio.run(cmd_run(a.brief, a.run_id, a.by, a.follow,
                                            a.product_repo, a.product_branch, a.coding_mode,
                                            a.working_branch))
        case "set-product":   asyncio.run(cmd_set_product(a.run_id, a.repo, a.branch,
                                                          a.working_branch))
        case "repos":   cmd_repos()
        case "set-coding-mode": asyncio.run(cmd_set_coding_mode(a.run_id, a.mode))
        case "publish":       asyncio.run(cmd_publish(a.run_id))
        case "daemon":  asyncio.run(cmd_daemon(a.runner))
        case "approve": asyncio.run(cmd_decide(a.run_id, a.gate, a.by, a.note, True))
        case "reject":  asyncio.run(cmd_decide(a.run_id, a.gate, a.by, a.note, False))
        case "retry":   asyncio.run(cmd_retry(a.run_id))
        case "rework":  asyncio.run(cmd_rework(a.run_id, a.to, a.by, a.note))
        case "status":  asyncio.run(cmd_status(a.json))
        case "qa-preflight":  asyncio.run(cmd_qa_preflight(a.stage))
        case "agents":  asyncio.run(cmd_agents())
        case "ask":     asyncio.run(cmd_ask(a.role, a.prompt, a.session, a.by,
                                            a.new, a.interactive, a.no_browser))
        case "runboard":      asyncio.run(cmd_runboard())
        case "usage":         asyncio.run(cmd_usage(a.days))
        case "usage-check":   asyncio.run(cmd_usage_check())
        case "render-memory": asyncio.run(cmd_render_memory(a.role))
        case "import-run":    asyncio.run(cmd_import_run(a.run_id, a.by, a.stage, a.status, a.gate))
        case "babysit":       asyncio.run(review.cmd_babysit(a.run_id, a.force))   # D19


if __name__ == "__main__":
    main()
