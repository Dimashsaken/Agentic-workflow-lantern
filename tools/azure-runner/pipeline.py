"""Lantern pipeline runner — one call takes a brief from concept to live.

    python pipeline.py init-db
    python pipeline.py run workflow/briefs/<slug>.md [--run-id feat-YYYYMMDD-<slug>] [--by justin] [--follow]
    python pipeline.py daemon [--runner ec2|workstation]   # claim-execute-advance loop
    python pipeline.py step <run-id> [--runner …]          # one stage of one run, foreground, then exit
    python pipeline.py status
    python pipeline.py approve <run-id> <gate> --by <name> [--note "..."]
    python pipeline.py reject  <run-id> <gate> --by <name> [--note "..."]
    python pipeline.py retry   <run-id>
    python pipeline.py agents                      # list consultable agents
    python pipeline.py ask <role> "<prompt>" [-i] [--session name] [--new]  # consult one agent directly
    python pipeline.py runboard                    # re-render workflow/RUNBOARD.md from the DB
    python pipeline.py render-memory [--role X]    # re-render agents/<role>/memory.md from role_memory
    python pipeline.py import-run <run-id> [--stage S --status waiting_gate --gate G]  # backfill a file-era run
    python pipeline.py init-product <path>         # install the factory's gate into a product repo (D21)

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
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

from agents import Agent, Runner, set_default_openai_api, set_default_openai_client, set_tracing_disabled
from agents.extensions.memory import SQLAlchemySession

from orchestrator import (
    BROWSER_ROLES, CODING_BRANCH_PREFIXES, ModelStackError, check_coding_handoff, finalize_coding, max_turns_for, stage_tools, PAPER_PREFLIGHT_HINT, PAPER_STAGES, REPO, ROLE_FOR_STAGE,
    USAGE_MARKER, append_file, azure_v1_client, build_consult_instructions,
    build_instructions, check_postconditions, check_stage_inputs, collect_export,
    consult_roles, db_urls,
    list_dir, list_exports, make_append_memory, make_collect_jsx, model_for,
    model_settings_for, paper_mcp_server,
    product_git,
    paper_reachable, playwright_mcp_server, read_file, render_role_memory, role_for_stage,
    usage_dict, write_file,
)

load_dotenv(Path(__file__).parent / ".env")

import factory  # noqa: E402  D17: quality gate + fix loop for the in-process coding path
import builders  # noqa: E402  D18: stage 3 fans out into scoped parallel builders
import review   # noqa: E402  D19: review loop after publish + merge babysitter
import intake  # noqa: E402  D20: the debug lifecycle — bug runs, their envelopes, the shepherd
import execution_runtime as ownership
import tool_execution
import github_publication

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
    "LANTERN_MAX_TURNS",
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
# Stage-1 convergence (D25): 'paper' = Paper artboards on a design workstation (D9);
# 'html' = HTML prototypes + browser screenshots on the ec2 runner — no Paper seat needed.
DESIGN_MODES = ("paper", "html")
DESIGN_MODE_DEFAULT = os.environ.get("LANTERN_DESIGN_MODE_DEFAULT", "paper")
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


_BRIEF_HTML_COMMENT = re.compile(r"<!--.*?(?:-->|$)")


def brief_field(text: str, label: str) -> str:
    """The value of `- **<label>:** …` in a brief, or '' when the line is absent or blank.

    An inline `<!-- … -->` annotation is documentation, not value: the brief template
    ships `- **Coding mode:** human   <!-- human = … -->` on the same line, and the
    Tender briefs annotate `Product repo:` the same way (found 2026-09-12: the comment
    rode along into the repo URL and `auto`/`html` read as unset). Backticks and the
    surrounding whitespace are dropped too.
    """
    # [ \t]* not \s*: an empty field must not swallow the next line (found 2026-09-08).
    m = re.search(rf"^\s*-\s*\*\*{re.escape(label)}:\*\*[ \t]*(.*?)[ \t]*$",
                  text, re.M | re.I)
    if not m:
        return ""
    return _BRIEF_HTML_COMMENT.sub("", m.group(1)).strip().strip("`").strip()


def parse_brief_coding_mode(text: str) -> str:
    """`- **Coding mode:** auto|human` in a brief; anything else reads as unset ('')."""
    v = brief_field(text, "Coding mode").lower()
    return v if v in CODING_MODES else ""


def parse_brief_design_mode(text: str) -> str:
    """`- **Design mode:** paper|html` in a brief (D25); anything else reads as unset ('')."""
    v = brief_field(text, "Design mode").lower()
    return v if v in DESIGN_MODES else ""


def stage_runner_for(stage: str, design_mode: str | None = None) -> str:
    """Which daemon may claim a stage — the static table, except that stage 1's
    convergence runs on the ec2 runner when the run's design mode is 'html' (D25)."""
    if stage == "01-ui-ux.design" and (design_mode or "paper") == "html":
        return "ec2"
    return STAGE_RUNNER.get(stage, "ec2")


def parse_brief_product(text: str) -> tuple[str, str, str]:
    """Pull `- **Product repo:**` / `- **Base branch:**` / `- **Working branch:**` out
    of a brief. Returns (repo, base, working); working is '' when the run should get a
    fresh branch derived from its id (D15).

    Placeholder values (em-dash, TBD, or an unfilled <angle-bracket> template slot)
    read as 'not set' — an unfilled template must not look like a configured target.
    """
    def field(label: str) -> str:
        # brief_field: `- **Working branch:**` left blank (the template says "leave
        # blank for a fresh one") reads as '', not as the following line, and an
        # inline <!-- annotation --> is not part of the value.
        v = brief_field(text, label)
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


async def product_design_mode(conn, run_id: str) -> str:
    """The run's stage-1 convergence mode (D25): 'html' or 'paper' (also the answer for
    a run created before the column existed, or a database not yet migrated)."""
    try:
        row = await conn.fetchrow("SELECT design_mode FROM runs WHERE id = $1", run_id)
    except asyncpg.PostgresError:      # pre-D25 schema: init-db has not added the column yet
        return "paper"
    mode = row.get("design_mode") if row is not None else None
    return mode if mode in DESIGN_MODES else "paper"


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
intake.register_stages(STAGE_DIR, STAGE_RUNNER)   # D20: debug-lifecycle stages join the executor/claim maps


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
    if ownership.enabled():
        current = ownership.STAGE.get()
        if current is None or current.lease.execution_id != exec_id:
            raise ownership.leases.LeaseLost("usage does not belong to the bound execution")
    async with ownership.mutation(conn, stage=True):
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
    metadata = dict(metadata or {})
    if ownership.enabled():
        parent, child = ownership.RUN.get(), ownership.STAGE.get()
        if parent is None or parent.lease.run_id != run_id:
            raise ownership.leases.LeaseLost("artifact has no matching run ownership")
        if child is not None:
            if child.lease.run_id != run_id:
                raise ownership.leases.LeaseLost("artifact execution belongs to another run")
            metadata.update(stage_execution_id=child.lease.execution_id,
                            lease_fence=child.lease.fence)
    async with ownership.mutation(conn, stage=ownership.enabled() and ownership.STAGE.get() is not None):
        if ownership.enabled() and ownership.STAGE.get() is not None:
            actual_stage = await conn.fetchval("SELECT stage FROM stage_executions WHERE id=$1", ownership.STAGE.get().lease.execution_id)
            if not actual_stage or factory.stage_dir(actual_stage) != factory.stage_dir(stage):
                raise ownership.leases.LeaseLost("artifact stage differs from its owned execution")
        await conn.execute(
            "INSERT INTO artifacts (run_id, stage, kind, uri, metadata) VALUES ($1, $2, $3, $4, $5)",
            run_id, stage, kind, uri, json.dumps(metadata) if metadata else None)


def media_candidates(root: Path, floor_ts: float) -> list[Path]:
    """Collect only ordinary files after all worker writers have been stopped."""
    from tool_policy import confined
    files = []
    for candidate in root.rglob("*.webm"):
        path = confined(root, candidate.relative_to(root).parts)
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("media must be an ordinary file with one link")
        if info.st_size > 0 and info.st_mtime >= floor_ts:
            files.append(path)
    return sorted(files, key=lambda path: path.stat().st_mtime)


async def upload_stage_media(conn, run_id: str, sdir: str, execution_key: str,
                             *, media_root: Path | None = None) -> None:
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
        media = media_candidates(media_root or stage_path, floor_ts)
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
                with tempfile.TemporaryDirectory(prefix="lantern-upload-") as temporary:
                    staged = Path(temporary) / "recording.webm"
                    shutil.copyfile(f, staged)
                    with staged.open("rb") as recorded:
                        digest = hashlib.file_digest(recorded, "sha256").hexdigest()
                    proc = await asyncio.create_subprocess_exec(
                        "aws", "s3", "cp", str(staged), uri,
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
                                   "attempt": attempt, "session": session,
                                   "execution_key": execution_key, "sha256": digest})
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

INPROCESS_STAGE_LOCK = asyncio.Lock()


async def run_agent_stage(conn, run_id: str, stage: str, runner: str) -> None:
    # Legacy prompt helpers still use process environment for product context.
    # Serialize controller stages until those helpers are fully context-local.
    async with INPROCESS_STAGE_LOCK:
        async with ownership.stage_scope(conn, connect, run_id, stage, runner) as execution:
            await _run_agent_stage(conn, run_id, stage, runner, execution)


async def _run_agent_stage(conn, run_id: str, stage: str, runner: str, execution=None) -> None:
    role = role_for_stage(stage)                      # D18: '03-coding.<x>' is coding
    sdir = STAGE_DIR.get(stage) or factory.stage_dir(stage)   # D18: builder keys are dynamic
    if execution is not None:
        attempt, execution_key, exec_id = execution
    else:
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
    mcp_servers = []
    journal = factory.ExecutionJournal(run_id, stage, execution_key, "", "")
    selected_model = None
    worker = None
    worker_token = None
    durable = None
    accepted_provenance = None
    try:
        await log_event(conn, run_id, "orchestrator", "stage_started",
                        {"stage": stage, "attempt": attempt, "runner": runner})

        await render_role_memory(conn, role)   # instructions must read a fresh view
        # Same product access as a sandbox, via a host checkout instead of a mount, so
        # laptop/workstation runs see exactly what the box does (orchestrator reads
        # LANTERN_PRODUCT_DIR at call time).
        repo, branch = await product_target(conn, run_id)
        work = await product_work_branch(conn, run_id) if repo else ""
        work = builders.branch_for(work, stage)      # D18: a builder works on its own branch
        for var in ("LANTERN_PRODUCT_DIR", "LANTERN_PRODUCT_WRITABLE", "LANTERN_CODING_BRANCH",
                    "LANTERN_PRODUCT_WORK_BRANCH", "LANTERN_CODING_START_SHA", "LANTERN_BUILDER"):
            os.environ.pop(var, None)
        # D25: the orchestrator's prompt builder and artifact checks read the run's
        # design mode from the environment, like the product facts below.
        os.environ["LANTERN_DESIGN_MODE"] = await product_design_mode(conn, run_id)
        paper_needed = stage in PAPER_STAGES and os.environ["LANTERN_DESIGN_MODE"] == "paper"
        if role == "coding" and not repo:
            raise RuntimeError("auto-coding needs a product repo — set one with "
                               f"`pipeline.py set-product {run_id} --repo … --branch …"
                               " [--working-branch …]` or in Mission Control at "
                               f"/run/{run_id}/repo")
        if repo:
            checkout = await asyncio.to_thread(product_checkout, repo, branch, run_id, work, execution_key)
            os.environ["LANTERN_PRODUCT_DIR"] = str(checkout)
            os.environ["LANTERN_PRODUCT_ORIGIN"], os.environ["LANTERN_PRODUCT_BRANCH"] = repo, branch
            # D15: EVERY stage learns the working branch, not just coding — that is what
            # lets stages 1-2 and 4-7 orient on the code the run is actually working on.
            os.environ["LANTERN_PRODUCT_WORK_BRANCH"] = work
            if role == "coding":       # D14: writable, on the run's branch, bot identity (D19: role_for_stage maps 03-coding.fix to coding, so a fix execution is writable here too; 03-coding.review is not)
                start = await asyncio.to_thread(prepare_coding_checkout, checkout, work)
                os.environ["LANTERN_CODING_BRANCH"] = work
                os.environ["LANTERN_CODING_START_SHA"] = start
                os.environ["LANTERN_PRODUCT_WRITABLE"] = "1"
                if builders.name_for(stage):   # D18: which builder this execution is
                    os.environ["LANTERN_BUILDER"] = builders.name_for(stage)
        session = SQLAlchemySession.from_url(f"{run_id}:{stage}", url=db_urls()[0], create_tables=True)

        problem = check_stage_inputs(run_id, stage)
        if problem:
            raise RuntimeError(problem)
        if tool_execution.enabled():
            if paper_needed:
                raise RuntimeError("isolated tools cannot connect to the desktop Paper service")
            if not repo:
                raise RuntimeError("isolated tools require a disposable product checkout")
            from isolated_tools import IsolatedToolWorker
            media = REPO / "workflow/runs" / run_id / sdir / "media" / hashlib.sha256(execution_key.encode()).hexdigest()[:16]
            media.mkdir(parents=True, exist_ok=True)
            worker = IsolatedToolWorker(checkout, media, execution_key, SANDBOX_IMAGE,
                                        writable_product=role == "coding",
                                        protected_roots=[Path(__file__).parent])
            await asyncio.to_thread(worker.start)
            worker_token = tool_execution.CURRENT.set(worker)
        if role in BROWSER_ROLES:
            mcp_servers.append(playwright_mcp_server(run_id, stage))
        paper = None
        if paper_needed:
            if not await paper_reachable():
                raise RuntimeError(PAPER_PREFLIGHT_HINT)
            paper = paper_mcp_server()
            mcp_servers.append(paper)
        for s in mcp_servers:
            await s.connect()
        selected_model = model_for(role, stage)
        agent = Agent(
            name=role,
            model=selected_model,
            model_settings=model_settings_for(role, stage),
            instructions=build_instructions(role, run_id, stage),
            tools=stage_tools(role, run_id, stage, execution_key, paper),
            mcp_servers=mcp_servers,
        )
        kickoff = (f"Begin your {stage} session for run {run_id} (attempt {attempt}). Do not "
                   "reply with a plan — start calling tools now and keep working until the "
                   "report is on disk and append_memory has been called.")
        journal = factory.ExecutionJournal(run_id, stage, execution_key, agent.instructions, kickoff)
        import durable_execution
        if durable_execution.enabled():
            durable = durable_execution.DurableHooks(
                run_id, execution_key,
                on_usage=lambda usage: record_usage(conn, exec_id, usage, selected_model))

        async def run_turn(text: str):
            # D23: same retry policy as the container path — a throttled builder is a
            # retriable transport failure, not a failed stage.
            return await factory.with_retry(
                lambda: journal.attempt(lambda: Runner.run(agent, input=text, session=session,
                                                          max_turns=max_turns_for(role),
                                                          **({"hooks": durable} if durable else {}))),
                on_retry=lambda n, of, e, d: print(
                    f"[{run_id}] retry {n}/{of} after {type(e).__name__} — {d:.1f}s"))

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
        if worker is not None:
            # End every model-controlled writer before accepting/exporting files.
            # A fresh, never-started worker object permits only the controller's
            # subsequent ephemeral Git inspections; each command removes itself.
            cleanup = await asyncio.gather(*(s.cleanup() for s in mcp_servers), return_exceptions=True)
            mcp_servers.clear()
            for error in cleanup:
                if isinstance(error, BaseException):
                    raise error
            await asyncio.to_thread(worker.stop)
            inspection = IsolatedToolWorker(worker.product_root, worker.output_root,
                execution_key, worker.image_id, writable_product=role == "coding",
                protected_roots=[Path(__file__).parent])
            inspection.image_id = worker.image_id
            tool_execution.CURRENT.reset(worker_token)
            worker = inspection
            worker_token = tool_execution.CURRENT.set(worker)
        # D14: bundle the committed branch into the run folder while the checkout exists.
        finalize_problems = finalize_coding(run_id, stage, execution_key) if role == "coding" else []

        if finalize_problems:
            raise RuntimeError("coding handoff failed: " + "; ".join(finalize_problems))
        missing = await check_postconditions(conn, role, run_id, stage, execution_key)
        if missing:
            raise RuntimeError("postconditions failed: " + "; ".join(missing))
        if role == "coding":
            accepted_provenance = gate.get("provenance")
    except BaseException as exc:
        if journal is not None:
            journal.failed(exc, model_attempt=False)
        raise
    finally:
        primary_error = sys.exception()
        try:
            if journal is not None:
                journal.flush()
                usage = dict(journal.usage)
                if durable is not None:
                    for key, value in durable.usage.items():
                        usage[key] = max(usage.get(key) or 0, value)
                await record_usage(conn, exec_id, usage, selected_model)
        except BaseException as error:
            if primary_error is None:
                journal.failed(error, model_attempt=False)
                raise
            print(f"[{run_id}] usage bookkeeping failed: {factory.redact(str(error))}", file=sys.stderr)
        finally:
            try:
                cleanup_errors = await asyncio.gather(
                    *(s.cleanup() for s in mcp_servers), return_exceptions=True)
                for error in cleanup_errors:
                    if isinstance(error, BaseException):
                        if sys.exception() is None:
                            journal.failed(error, model_attempt=False)
                            raise error
                        print(f"[{run_id}] MCP cleanup failed: {factory.redact(str(error))}", file=sys.stderr)
            finally:
                try:
                    if worker is not None:
                        await asyncio.to_thread(worker.stop)
                finally:
                    if worker_token is not None:
                        tool_execution.CURRENT.reset(worker_token)
                    for var in ("LANTERN_PRODUCT_DIR", "LANTERN_PRODUCT_ORIGIN", "LANTERN_PRODUCT_BRANCH",
                                "LANTERN_PRODUCT_WORK_BRANCH", "LANTERN_PRODUCT_WRITABLE",
                                "LANTERN_CODING_BRANCH", "LANTERN_CODING_START_SHA", "LANTERN_BUILDER",
                                "LANTERN_DESIGN_MODE"):
                        os.environ.pop(var, None)   # cleanup even if ledger or MCP fails

    await upload_stage_media(conn, run_id, sdir, execution_key,
                             **({"media_root": worker.output_root} if worker else {}))

    # D18: a builder's report is in its own subdir — point the artifact row at the file
    # that exists, not at the stage report the integrator will write later.
    report = f"workflow/runs/{run_id}/{factory.exec_dir(sdir, factory.builder_of(stage))}/report.md"
    await insert_artifact(conn, run_id, sdir, "report", report)
    if accepted_provenance and accepted_provenance.get("status") == "verified":
        await insert_artifact(conn, run_id, sdir, "execution_evidence",
                              accepted_provenance["manifest"]["path"],
                              {"execution_key": execution_key, **accepted_provenance})
    if stage == "01-ui-ux.design":
        await register_design_artifacts(conn, run_id, sdir)
    async with ownership.mutation(conn, stage=True, finish=True):
        await conn.execute(
            "UPDATE stage_executions SET status = 'succeeded', output = $1, finished_at = now() WHERE id = $2",
            json.dumps({"final_output": final[-4000:], "report": report,
                        "provenance": accepted_provenance,
                        "diagnostics": str(durable.path) if durable else None}), exec_id,
        )
    if durable is not None:
        try:
            durable.finish(True)
        except OSError as exc:
            # The DB success is already committed; report the missing terminal
            # diagnostic without rewriting that established lifecycle outcome.
            print(f"[{run_id}] terminal diagnostic unavailable: {factory.redact(str(exc))}", file=sys.stderr)
    await log_event(conn, run_id, f"agent:{role}", "stage_succeeded", {"stage": stage})


async def run_agent_stage_docker(conn, run_id: str, stage: str, runner: str) -> None:
    if ownership.enabled() or tool_execution.enabled() or os.environ.get("LANTERN_TRUSTED_EVIDENCE") == "1":
        raise RuntimeError("leases, isolated tools and trusted evidence require the host controller executor (LANTERN_EXECUTOR=isolated)")
    async with ownership.stage_scope(conn, connect, run_id, stage, runner) as execution:
        await _run_agent_stage_docker(conn, run_id, stage, runner, execution)


async def _run_agent_stage_docker(conn, run_id: str, stage: str, runner: str, execution=None) -> None:
    """One stage in one ephemeral sandbox container (D10/D12).

    The host side owns the DB row lifecycle and the postcondition verdict; the
    container runs orchestrator.py with this execution's key and checks its own
    postconditions too (defense in depth — a compromised container exiting 0 still
    cannot pass without the report on the mounted run dir and its memory row).
    """
    role = role_for_stage(stage)                      # D18: '03-coding.<x>' is coding
    sdir = STAGE_DIR.get(stage) or factory.stage_dir(stage)   # D18: builder keys are dynamic
    if execution is not None:
        attempt, execution_key, exec_id = execution
    else:
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
    design_mode = await product_design_mode(conn, run_id)   # D25
    os.environ["LANTERN_DESIGN_MODE"] = design_mode      # the host re-check reads it too
    cmd = ["docker", "run", "--rm", "--name", name,
           "--cpus", SANDBOX_CPUS, "--memory", SANDBOX_MEMORY,
           "--add-host=host.docker.internal:host-gateway",
           "-v", f"{REPO}:/repo-src:ro",
           "-v", f"{run_dir}:/work/lantern/workflow/runs/{run_id}:rw",
           "-e", f"LANTERN_EXECUTION_KEY={execution_key}",
           "-e", f"LANTERN_DATABASE_URL={sandbox_db_url()}",
           "-e", f"LANTERN_DESIGN_MODE={design_mode}"]
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
    work = builders.branch_for(work, stage)      # D18: a builder works on its own branch
    if role == "coding" and not repo:
        raise RuntimeError("auto-coding needs a product repo — set one with "
                           f"`pipeline.py set-product {run_id} --repo … --branch …"
                           " [--working-branch …]` or in Mission Control at "
                           f"/run/{run_id}/repo")
    cmd += await asyncio.to_thread(product_mount_args, repo, branch, work)
    timeout_min = STAGE_TIMEOUT_MIN
    if role == "coding":
        # D14: the entrypoint puts the checkout on the run's branch and marks it
        # writable; commits carry the bot identity. Still no PAT in the container —
        # the bundle it writes into the run folder is the only way code leaves.
        timeout_min = CODING_TIMEOUT_MIN
        cmd += ["-e", f"LANTERN_CODING_BRANCH={work}",
                "-e", f"LANTERN_GIT_AUTHOR_NAME={GIT_AUTHOR_NAME}",
                "-e", f"LANTERN_GIT_AUTHOR_EMAIL={GIT_AUTHOR_EMAIL}"]
        if builders.name_for(stage):      # D18: which builder this container is
            cmd += ["-e", f"LANTERN_BUILDER={builders.name_for(stage)}"]
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
    verify_product = None
    if repo and stage in {"00-story.scout", "03-coding.review", "05-post-coding.validate"}:
        verify_product = await asyncio.to_thread(product_checkout, repo, branch, run_id, work, execution_key)
    missing = await check_postconditions(conn, role, run_id, stage, execution_key, verify_product)
    if missing:
        raise RuntimeError("postconditions failed (host re-check): " + "; ".join(missing))
    await render_role_memory(conn, role)   # keep the host's rendered view fresh
    await upload_stage_media(conn, run_id, sdir, execution_key)

    report = f"workflow/runs/{run_id}/{sdir}/report.md"
    await insert_artifact(conn, run_id, sdir, "report", report)
    if stage == "01-ui-ux.design":
        await register_design_artifacts(conn, run_id, sdir)
    async with ownership.mutation(conn, stage=True, finish=True):
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
            raw = resp.read(4 * 1024 * 1024 + 1)
            if len(raw) > 4 * 1024 * 1024:
                raise RuntimeError("GitHub response exceeded the bounded observation size")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise RuntimeError("GitHub error response exceeded the bounded observation size")
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


def _open_or_find_pr(owner: str, name: str, branch: str, base: str, title: str, body: str,
                     head: str) -> dict:
    # Legacy mode keeps its branch-only fallback, but PR reuse is read-only and
    # checks the same destination/revision identity as the leased publisher.
    request = {"repo": f"https://github.com/{owner}/{name}", "branch": branch,
               "base": base, "head_sha": head}
    before = github_publication.observe(_gh_api, request)
    if before.head != head:
        raise github_publication.PublicationHeld("branch changed before PR publication")
    return github_publication.publish(_gh_api, None, None, None, request, title, body, before)


def _publish_branch(run_id: str, repo: str, base: str, work: str = "", expected_head: str = "",
                    publication_request: dict | None = None, check_current=None,
                    begin_effect=None, complete_effect=None) -> dict:
    """Verify the coding handoff against the host mirror, land the branch in it, push it
    to the origin (https remotes; a local-path product repo is updated in place) and
    open or reuse the pull request. Returns the code_complete payload. Sync, testable."""
    sdir = REPO / "workflow" / "runs" / run_id / "03-coding"
    hf = sdir / "handoff.json"
    if not hf.is_file():
        raise RuntimeError("no 03-coding/handoff.json — the coding stage produced no branch")
    handoff = json.loads(hf.read_text(encoding="utf-8"))
    if expected_head and handoff.get("head_sha") != expected_head:
        raise RuntimeError("coding handoff changed after publication intent")
    branch = str(handoff.get("branch") or "")
    expected = work_branch(run_id, work)
    if branch != expected:
        raise RuntimeError(f"handoff names branch '{branch}', expected '{expected}'")
    # Inspect the destination before touching even the local mirror. Unavailable or
    # conflicting provider state cannot authorize publication in lease mode.
    before = github_publication.observe(_gh_api, publication_request) if publication_request else None
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
    if publication_request:
        publisher = github_publication.publish_split if publication_request.get("version") == 3 else github_publication.publish
        options = {"before": before, "check_current": check_current}
        if publication_request.get("version") == 3:
            options.update(begin_effect=begin_effect, complete_effect=complete_effect)
        payload.update(publisher(_gh_api, _git, _authed(repo), mirror, publication_request,
                                 f"{run_id}: {_run_title(run_id) or 'feature'}"[:250],
                                 pr_body(run_id, handoff, base), **options))
    elif repo.startswith("https://"):
        r = _git("push", "--quiet", _authed(repo), f"refs/heads/{branch}:refs/heads/{branch}", cwd=mirror)
        # A rejection requires inspection; never overwrite a newer remote head.
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
                                                    pr_body(run_id, handoff, base), head))
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
    if not ownership.enabled():
        return await _publish_coding_branch(conn, run_id)
    # Publication is a real host execution with its own lease and stable logical
    # operation key. A duplicate intent is never permission to issue the call again.
    async with ownership.stage_scope(conn, connect, run_id, "03-coding.publish", "host") as execution:
        handoff = _read_handoff(run_id, "03-coding") or {}
        head = handoff.get("head_sha")
        if not head:
            raise RuntimeError("publication requires a committed coding handoff")
        lease = ownership.STAGE.get().lease
        key = f"publish-v3:{run_id}:{head}"
        repo, base = await product_target(conn, run_id)
        work = await product_work_branch(conn, run_id)
        target = {"run_id": run_id, "head_sha": head, "branch": handoff.get("branch"),
                  "repo": repo, "base": base, "work": work}
        github_publication.destination(target)
        for prefix in ("publish", "publish-v2"):
            legacy = await ownership.leases.read_effect(conn, lease, f"{prefix}:{run_id}:{head}")
            if legacy is not None:
                raise github_publication.PublicationHeld("legacy publication intent requires operator inspection; refusing v3 replay")
        existing = await ownership.leases.read_effect(conn, lease, key)
        if existing is not None:
            request = existing.result.get("publication_request") if isinstance(existing.result, dict) else None
            if (not isinstance(request, dict) or request.get("version") != 3
                    or any(request.get(field) != value for field, value in target.items())):
                raise github_publication.PublicationHeld("publication request is unavailable or destination/revision changed")
        else:
            request = await asyncio.to_thread(github_publication.prepare_request, _gh_api, target, 3)
        effect = await ownership.leases.begin_effect(conn, lease, key, "publish_branch", request,
                                                     initial_result={"publication_request": request})
        if not effect.created and effect.status == "confirmed":
            # No duplicate may write GitHub, including a once-confirmed receipt:
            # branch, PR destination and revision must still match provider state.
            previous = effect.result if effect.status == "confirmed" else None
            if effect.status == "confirmed" and previous is None:
                raise github_publication.PublicationHeld("legacy publication receipt requires operator inspection")
            observed = await asyncio.to_thread(github_publication.reconcile, _gh_api, request, previous)
            result = {"bundle": handoff.get("bundle"), "base_sha": handoff.get("base_sha"),
                      "commit_count": len(handoff.get("commits", [])),
                      "commits": handoff.get("commits", [])[:40],
                      "files_changed": len(handoff.get("files_changed", [])),
                      "auto_committed": bool(handoff.get("auto_committed")),
                      **(effect.result if isinstance(effect.result, dict) else {}), **observed}
            async with ownership.mutation(conn, stage=True):
                await _check_publication_target(conn, run_id, request)
                await ownership.leases.reconcile_effect(conn, lease, key, request, result["pr_url"], result)
                await _record_coding_publication(conn, run_id, result)
        else:
            try:
                result = await _publish_coding_branch(conn, run_id, expected=request)
                async with ownership.mutation(conn, stage=True):
                    await _check_publication_target(conn, run_id, request)
                    if effect.created:
                        await ownership.leases.confirm_effect(conn, lease, key, result.get("pr_url"), result)
                    else:
                        await ownership.leases.reconcile_effect(conn, lease, key, request, result["pr_url"], result)
                    await _record_coding_publication(conn, run_id, result)
            except ownership.leases.LeaseLost:
                raise
            except Exception:
                if effect.created:
                    await ownership.leases.mark_effect_uncertain(conn, lease, key, {"publication_request": request})
                raise
        async with ownership.mutation(conn, stage=True, finish=True):
            await _check_publication_target(conn, run_id, request)
            await conn.execute("UPDATE stage_executions SET status='succeeded', finished_at=clock_timestamp() WHERE id=$1", execution[2])
        return result


async def _check_publication_target(conn, run_id: str, expected: dict, stage: bool = True) -> None:
    async with ownership.mutation(conn, stage=stage):
        current_repo, current_base = await product_target(conn, run_id)
        current_work = await product_work_branch(conn, run_id)
        current_handoff = _read_handoff(run_id, "03-coding") or {}
        if ((current_repo, current_base, current_work) != (expected["repo"], expected["base"], expected["work"])
                or current_handoff.get("head_sha") != expected["head_sha"]
                or current_handoff.get("branch") != expected["branch"]):
            raise github_publication.PublicationHeld("publication target or handoff changed before effect acceptance")


async def _publish_coding_branch(conn, run_id: str, expected: dict | None = None) -> dict:
    repo, base = await product_target(conn, run_id)
    if not repo:
        raise RuntimeError("auto-coding produced a branch but the run has no product repo to push to")
    work = await product_work_branch(conn, run_id)
    if expected:
        if (repo, base, work) != (expected["repo"], expected["base"], expected["work"]):
            raise RuntimeError("publication target changed after recorded intent")
        loop = asyncio.get_running_loop()
        def check_current():
            asyncio.run_coroutine_threadsafe(_check_publication_target(conn, run_id, expected), loop).result(timeout=30)
        async def begin_action(action):
            async with ownership.mutation(conn, stage=True):
                await _check_publication_target(conn, run_id, expected)
                request = github_publication.action_request(expected, action)
                return await ownership.leases.begin_effect(
                    conn, ownership.STAGE.get().lease, f"publish-v3:{run_id}:{expected['head_sha']}:{action}",
                    f"publish_{action}", request, initial_result=request)
        async def complete_action(action, effect, external_ref, result):
            async with ownership.mutation(conn, stage=True):
                await _check_publication_target(conn, run_id, expected)
                key = f"publish-v3:{run_id}:{expected['head_sha']}:{action}"
                lease = ownership.STAGE.get().lease
                if effect.created:
                    return await ownership.leases.confirm_effect(conn, lease, key, external_ref, result)
                return await ownership.leases.reconcile_effect(
                    conn, lease, key, github_publication.action_request(expected, action), external_ref, result)
        def begin_effect(action):
            return asyncio.run_coroutine_threadsafe(begin_action(action), loop).result(timeout=30)
        def complete_effect(action, effect, external_ref, result):
            return asyncio.run_coroutine_threadsafe(complete_action(action, effect, external_ref, result), loop).result(timeout=30)
        payload = await asyncio.to_thread(_publish_branch, run_id, repo, base, work,
                                         expected["head_sha"], expected, check_current, begin_effect, complete_effect)
    else:
        payload = await asyncio.to_thread(_publish_branch, run_id, repo, base, work)
    if not expected:
        await _record_coding_publication(conn, run_id, payload)
    return payload


async def _record_coding_publication(conn, run_id: str, payload: dict) -> None:
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
        if opt.get("prototype"):    # D25: html design mode
            rows.append((opt["prototype"], "design_prototype", {"option": opt.get("name")}))
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
            waiting = f"runner `{stage_runner_for(r['current_stage'], r.get('design_mode') if hasattr(r, 'get') else None)}`"
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
    if intake.is_bug_run(run_id):   # D20: the debug lifecycle has its own table and skip rule
        return await intake.advance_bug(conn, run_id, stage)
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
    async with ownership.run_scope(conn, connect, run_id):
        await _step_run(conn, run_id, runner)


async def _step_run(conn, run_id: str, runner: str = "ec2") -> None:
    """Execute the current stage of one claimed run, then gate or advance."""
    row = await conn.fetchrow("SELECT current_stage, coding_mode FROM runs WHERE id = $1", run_id)
    stage = row["current_stage"]
    mode = row["coding_mode"] or "human"
    _, _, stype, gate, _ = intake.stage_row(run_id, stage, FEATURE_STAGES)   # D20: bug runs read their own table
    extra: dict | None = None
    external_ref: str | None = None
    try:
        execute = run_agent_stage_docker if EXECUTOR == "docker" else run_agent_stage
        if stype == "agent":
            await execute(conn, run_id, stage, runner)
        elif stage == "03-coding" and mode == "auto":
            # D14: the coding agent implements the plan in a sandbox; the host then
            # verifies + pushes its branch and opens the PR — the gate's payload.
            # D18: with a `builders` list in the plan this fans out into N scoped
            # builders, merges them on the host and integrates once; with no builders
            # it is the single `execute` call it has always been.
            built = await builders.run_coding(conn, run_id, stage, runner, execute)
            extra = await publish_coding_branch(conn, run_id)
            if built:                                    # D18
                extra["builders"] = built
            extra = await review.after_publish(conn, run_id, extra, runner,   # D19: review rounds
                                               review.default_deps(execute=execute))
            external_ref = extra.get("pr_url")
        else:  # human stage: nothing to execute — the gate IS the stage
            print(f"[{run_id}] {stage} is a human stage (the developer's own session).")
        if ownership.enabled() and stage == "03-coding" and mode == "auto":
            request = (extra or {}).get("publication_request")
            if not isinstance(request, dict) or request.get("version") != 3:
                raise github_publication.PublicationHeld("gate requires observed v3 publication evidence")
            observed = await asyncio.to_thread(github_publication.reconcile, _gh_api, request, extra)
            extra.update(observed)
        async with ownership.mutation(conn, finish=True):
            if ownership.enabled() and stage == "03-coding" and mode == "auto":
                await _check_publication_target(conn, run_id, request, stage=False)
            if intake.is_bug_run(run_id):   # D20: debug lifecycle contracts are unchanged
                await intake.after_stage(conn, run_id, stage, gate, extra, external_ref)
            elif gate:
                await open_gate(conn, run_id, stage, gate, extra, external_ref)
            else:
                await advance(conn, run_id, stage)
    except ownership.leases.LeaseLost:
        # Recovery owns the expired attempt. A stale dispatcher cannot mark a
        # replacement failed or move its gate after losing its fence.
        raise
    except Exception as e:  # noqa: BLE001 — orchestrator must not die with a claim held
        async with ownership.mutation(conn, finish=True):
            await conn.execute(
                """UPDATE stage_executions SET status = 'failed', error = $1, error_class = $3, finished_at = now()
                   WHERE run_id = $2 AND status = 'running'""",
                factory.redact(str(e))[:4000], run_id, factory.classify_error(e))
            await conn.execute(
                "UPDATE runs SET status = 'failed', updated_at = now() WHERE id = $1", run_id)
            await log_event(conn, run_id, "orchestrator", "stage_failed", {"stage": stage, "error": factory.redact(str(e))[:500]})
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
    is overwritten by every completion path (gate/advance/fail). Lease-enabled
    dispatchers hold expired attempts for recovery; startup never blanket-requeues
    another process's executing work.
    """
    stages = [s for s, r in STAGE_RUNNER.items() if r == runner]
    # D25: stage 1's convergence is claimed by the workstation for Paper runs and by
    # the ec2 runner for html runs — the run's design_mode decides, not the table.
    if runner == "ec2":
        stages.append("01-ui-ux.design")
    design_mode = "html" if runner == "ec2" else "paper"
    async with conn.transaction():
        row = await conn.fetchrow(
            """SELECT id FROM runs WHERE status = 'running' AND current_stage = ANY($1::text[])
               AND (current_stage <> '01-ui-ux.design' OR coalesce(design_mode, 'paper') = $2)
               ORDER BY updated_at FOR UPDATE SKIP LOCKED LIMIT 1""", stages, design_mode)
        if not row:
            return None
        if ownership.enabled():
            return await ownership.claim(conn, row["id"])
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
                  coding_mode: str = "", working_branch: str = "",
                  design_mode: str = "") -> None:
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
    # Design mode (D25): same precedence; 'paper' unless the brief, the flag or the box
    # default asks for the Paper-free convergence.
    design_mode = (design_mode or parse_brief_design_mode(brief_text) or DESIGN_MODE_DEFAULT).lower()
    if design_mode not in DESIGN_MODES:
        sys.exit(f"design mode must be one of {', '.join(DESIGN_MODES)} — got '{design_mode}'")
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
                             coding_mode, design_mode)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
        run_id, str(brief), PIPELINE_VERSION, FEATURE_STAGES[0][0], by,
        product_repo or None, product_branch or None, working_branch or None, coding_mode,
        design_mode)
    await log_event(conn, run_id, f"human:{by}", "run_created",
                    {"brief": str(brief), "product_repo": product_repo,
                     "product_branch": product_branch,
                     "product_working_branch": working_branch, "coding_mode": coding_mode,
                     "design_mode": design_mode})
    await render_runboard(conn)
    print(f"run {run_id} created (coding mode: {coding_mode}, design mode: {design_mode}) — "
          "the pipeline takes it from here.")
    if product_repo:
        print(f"  work lands on: {work_branch(run_id, working_branch)}")
    if follow:
        local = os.environ.get("LANTERN_RUNNER", "ec2")
        waiting_on = None
        while True:
            row = await conn.fetchrow(
                "SELECT status, current_stage, design_mode FROM runs WHERE id = $1", run_id)
            if row["status"] not in ("running", "executing"):
                print(f"[{run_id}] status: {row['status']}")
                break
            if row["status"] == "executing":   # a daemon slot has it — just watch
                await asyncio.sleep(POLL_SECONDS)
                continue
            needed = stage_runner_for(row["current_stage"], row["design_mode"])
            if needed != local:
                if waiting_on != row["current_stage"]:
                    print(f"[{run_id}] {row['current_stage']} needs the '{needed}' runner — waiting for its daemon.")
                    waiting_on = row["current_stage"]
                await asyncio.sleep(POLL_SECONDS)
                continue
            if ownership.enabled():
                claimed = await ownership.claim(conn, run_id)
            else:
                claimed = await conn.execute(
                    "UPDATE runs SET status = 'executing', updated_at = now() WHERE id = $1 AND status = 'running'",
                    run_id)
            if not claimed or claimed.endswith(" 0"):  # another daemon won
                continue
            await step_run(conn, run_id, local)
    await conn.close()


async def recover_expired_runs(conn):
    recovered = await ownership.leases.recover_expired(conn)
    if tool_execution.enabled():
        from isolated_tools import cleanup_execution
        for run in recovered:
            for execution_id in run["execution_ids"]:
                key = await conn.fetchval("SELECT idempotency_key FROM stage_executions WHERE id=$1 AND status='failed'", execution_id)
                if key:
                    try:
                        await asyncio.to_thread(cleanup_execution, key)
                    except Exception as exc:
                        await log_event(conn, run["run_id"], "orchestrator", "worker_cleanup_failed",
                                        {"execution_id": execution_id, "error": factory.redact(str(exc))})
    return recovered


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
    # A new process is not proof that every other worker died. Only expired
    # ownership may be recovered; legacy unleased work is held for reconciliation.
    if ownership.enabled():
        await recover_expired_runs(conn)
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
            if ownership.enabled():
                await recover_expired_runs(conn)
            if runner == "ec2" and review.babysit_due() and not ownership.enabled():
                # Existing babysitting starts from waiting_gate. Until it owns a
                # distinct fenced operation it must not mutate an approved branch.
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


def _chmod_retry(func, path, _exc) -> None:
    os.chmod(path, stat.S_IWRITE)
    func(path)


def force_rmtree(path: Path) -> None:
    """Remove a git checkout on any platform, and say so when it cannot be removed.

    Git marks objects and packs read-only, which on Windows makes `shutil.rmtree` raise
    PermissionError. With `ignore_errors=True` that failure was silent and the directory
    survived, so the NEXT clone into it died with 'destination path already exists' —
    an error that names neither the cause nor the fix. It bites whenever one process
    checks out the same run twice: two stages under one daemon tick, and (D18) the
    scoped builders, which is where it was found.
    """
    if not path.exists():
        return
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_chmod_retry)
    else:                                    # pragma: no cover - 3.11 and older
        shutil.rmtree(path, onerror=_chmod_retry)


def product_checkout(repo: str, branch: str, run_id: str, work: str = "", execution_key: str = "") -> Path:
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
    # No stage may delete a path still mounted by an interrupted worker. Runtime
    # callers supply their unique attempt key; direct utility callers retain the
    # historical reusable path until migrated to explicit execution identities.
    dest = PRODUCT_MIRROR_DIR / "checkouts" / (
        hashlib.sha256(execution_key.encode()).hexdigest() if execution_key else run_id)
    if execution_key and dest.exists():
        raise RuntimeError("execution checkout already exists; use a new attempt, never replace a live worker mount")
    if not execution_key:
        force_rmtree(dest)
    if dest.exists():
        raise RuntimeError(
            f"could not clear the previous checkout at {dest} — remove it and retry "
            "(a file in it is locked by another process)")
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


async def cmd_set_design_mode(run_id: str, mode: str) -> None:
    """Switch how stage 1 converges (D25) — before the design execution has run. The
    typical use: a run parked at `01-ui-ux.design` waiting for a workstation nobody has."""
    if mode not in DESIGN_MODES:
        sys.exit(f"design mode must be one of {', '.join(DESIGN_MODES)}")
    conn = await connect()
    row = await conn.fetchrow("SELECT current_stage, status FROM runs WHERE id = $1", run_id)
    if not row:
        sys.exit(f"unknown run {run_id}")
    if STAGE_INDEX.get(row["current_stage"], 0) > STAGE_INDEX["01-ui-ux.design"]:
        sys.exit(f"{run_id} is past stage 1 ({row['current_stage']}) — the design mode no longer applies")
    await conn.execute("UPDATE runs SET design_mode = $1, updated_at = now() WHERE id = $2", mode, run_id)
    await log_event(conn, run_id, "human:cli", "design_mode_set", {"mode": mode})
    await render_runboard(conn)
    await conn.close()
    print(f"[{run_id}] design mode: {mode}"
          + (" — the ec2 daemon converges with HTML prototypes; no Paper workstation needed"
             if mode == "html" else " — the design workstation daemon converges in Paper"))


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


def set_qa_target(env_file: Path, role: str, base_url: str, user: str = "",
                  password: str = "", rotate: bool = False) -> dict:
    """Write one QA target (`LANTERN_QA_<DEV|STAGING>_{BASE_URL,USER,PASS}`) into an
    env file, in place, without printing a value.

    Why a command and not three `sed`s in a playbook: the daemon reads `.env` at start
    and SSM only fills names that are still unset (`load_ssm_qa_env`), so whatever this
    file says IS the stage-4/7 target. The first Tender run found the box's `.env` still
    carrying the dogfood-era `qa-dev` user for the Mission Control target; a playbook
    that only appended missing names would have pointed QA at Tender with a login that
    cannot exist there. Rules: the URL is always replaced; a new `user` replaces the old
    one and, because the credential pair belongs to one account on one app, regenerates
    the password unless one is given; an unchanged user keeps its password unless
    `rotate`; a missing password is always generated. Other lines, their order and
    comments are preserved; duplicate definitions collapse to one.
    Returns {"prefix", "base_url", "user", "password_changed", "created"}.
    """
    prefix = QA_TARGET_PREFIX.get(role)
    if not prefix:
        raise ValueError(f"role must be one of {', '.join(sorted(QA_TARGET_PREFIX))} — got '{role}'")
    if not base_url.startswith(("http://", "https://")):
        raise ValueError(f"base url must start with http:// or https:// — got '{base_url}'")
    names = {"url": prefix + "_BASE_URL", "user": prefix + "_USER", "pass": prefix + "_PASS"}
    env_file = Path(env_file)
    created = not env_file.exists()
    lines = env_file.read_text(encoding="utf-8").splitlines() if not created else []

    def current(name: str) -> str:
        vals = [ln.split("=", 1)[1] for ln in lines if ln.startswith(name + "=")]
        return vals[-1].strip() if vals else ""     # dotenv semantics: the last one wins

    old_user, old_pass = current(names["user"]), current(names["pass"])
    new_user = user.strip() or old_user
    if password:
        new_pass, changed = password, password != old_pass
    elif rotate or not old_pass or (user.strip() and new_user != old_user):
        new_pass, changed = secrets.token_urlsafe(12), True
    else:
        new_pass, changed = old_pass, False
    wanted = {names["url"]: base_url.strip(), names["user"]: new_user, names["pass"]: new_pass}

    out, done = [], set()
    for ln in lines:
        key = ln.split("=", 1)[0] if "=" in ln and not ln.lstrip().startswith("#") else None
        if key in wanted:
            if key not in done:                       # first definition wins the slot…
                out.append(f"{key}={wanted[key]}")
                done.add(key)
            continue                                  # …later duplicates are dropped
        out.append(ln)
    for key in (names["url"], names["user"], names["pass"]):
        if key not in done:
            out.append(f"{key}={wanted[key]}")
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("\n".join(out) + "\n", encoding="utf-8")
    if created and os.name != "nt":
        os.chmod(env_file, 0o600)
    return {"prefix": prefix, "base_url": wanted[names["url"]], "user": new_user,
            "password_changed": changed, "created": created}


def cmd_qa_target(role: str, base_url: str, user: str, password: str, rotate: bool,
                  env_file: str) -> None:
    path = Path(env_file) if env_file else Path(__file__).parent / ".env"
    try:
        r = set_qa_target(path, role, base_url, user, password, rotate)
    except ValueError as e:
        sys.exit(str(e))
    pw = "regenerated — sign the account up (again) on the target" if r["password_changed"] else "kept"
    print(f"{role} target → {path}{' (created)' if r['created'] else ''}\n"
          f"  {r['prefix']}_BASE_URL  {r['base_url']}\n"
          f"  {r['prefix']}_USER      {r['user'] or '(unset — pass --user)'}\n"
          f"  {r['prefix']}_PASS      {pw}\n"
          "The daemon reads this file at start: restart lantern-orchestrator when no stage "
          "is executing, then `pipeline.py qa-preflight --stage " + role + "` must print READY.")


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
        # login from inside a sandbox, credentials passed as env (never on argv), the
        # way a browser would: qa_login_probe.py fetches the form, carries its hidden
        # inputs (CSRF), takes the field names from the page and treats a redirect as
        # accepted (Tender's form is csrf + `email`; Mission Control's is `username`).
        login_ok = True
        if ok and user and pw:
            probe = ["docker", "run", "--rm", "--add-host=host.docker.internal:host-gateway",
                     "-v", f"{REPO}:/repo-src:ro",
                     "-e", f"QA_BASE_URL={base}", "-e", f"QA_USER={user}", "-e", f"QA_PASS={pw}",
                     "--entrypoint", "/opt/lantern/venv/bin/python", SANDBOX_IMAGE,
                     "/repo-src/tools/azure-runner/qa_login_probe.py"]
            out3, err3 = curl(probe)
            try:
                r3 = json.loads(out3.splitlines()[-1]) if out3 else {}
            except ValueError:
                r3 = {}
            login_ok = bool(r3.get("accepted"))
            detail = (f"accepted (field `{r3.get('user_field')}`)" if login_ok else
                      f"REJECTED — {r3.get('error') or 'the QA user/password do not log in with this form'}")
            print(f"  login     HTTP {r3.get('post') or r3.get('get') or 'FAILED'}  ({detail})"
                  f"{'  ' + err3 if err3 and not r3 else ''}")
        if ok and login_ok:
            print("\nREADY — a QA stage can reach this target and its login opens.")
        elif ok:
            print("\nNOT READY — the sandbox reaches the target but the provisioned login is "
                  f"rejected. Fix the account or the values ({prefix}_USER/_PASS), e.g. "
                  "`pipeline.py qa-target …` then seed the account on the app, and re-run this.")
        else:
            print("\nNOT REACHABLE FROM A SANDBOX. The host result above does not matter: "
                  "stage 4 runs in a container. A localhost-only, Tailscale-only, or "
                  "VPC-internal dev environment needs a route into the container network "
                  "(host.docker.internal, a published port, or a reachable hostname).")
    else:
        print("  sandbox   (skipped — LANTERN_EXECUTOR is not 'docker' here)")


REWORK_TARGETS = ("02-pre-coding", "03-coding", "04-qa-dev") + intake.BUG_REWORK_TARGETS   # D20


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
    index = intake.stage_index(run_id, STAGE_INDEX)   # D20: bug runs order by the debug lifecycle table
    if index.get(to_stage, 99) >= index.get(row["current_stage"], -1):
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


async def cmd_step(run_id: str, runner: str) -> None:
    """Execute a run's CURRENT stage once, in this process, in the foreground — one
    daemon tick for exactly one run, then exit.

    For a laptop without a daemon, and for watching one stage's output while debugging
    a prompt or a gate. Same claim, same executor, same gate/advance path as the
    daemon; the run's runner affinity is respected (a Paper stage still needs the
    workstation). Nothing loops: run it again for the next stage."""
    conn = await connect()
    row = await conn.fetchrow(
        "SELECT status, current_stage, design_mode FROM runs WHERE id = $1", run_id)
    if not row:
        sys.exit(f"unknown run {run_id}")
    if row["status"] != "running":
        sys.exit(f"{run_id} is '{row['status']}' at {row['current_stage']} — nothing to execute "
                 "(waiting_gate → approve/reject; failed → retry; executing → another process has it)")
    needed = stage_runner_for(row["current_stage"], row["design_mode"])
    if needed != runner:
        sys.exit(f"{row['current_stage']} needs the '{needed}' runner, this is '{runner}' "
                 "(pass --runner, or run the stage where its tools are)")
    claimed = await conn.execute(
        "UPDATE runs SET status = 'executing', updated_at = now() WHERE id = $1 AND status = 'running'", run_id)
    if claimed.endswith(" 0"):
        sys.exit(f"{run_id} was claimed by another process")
    print(f"[{run_id}] executing {row['current_stage']} in the foreground ({runner}, executor={EXECUTOR})")
    await step_run(conn, run_id, runner)
    after = await conn.fetchrow("SELECT status, current_stage FROM runs WHERE id = $1", run_id)
    print(f"[{run_id}] now '{after['status']}' at {after['current_stage']}")
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
      1. rate:  today's est spend > LANTERN_DAILY_SPEND_ALARM_USD (default 500 — the
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
    daily_limit = float(os.environ.get("LANTERN_DAILY_SPEND_ALARM_USD", "500"))
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
# Commands that need neither a database nor an Azure client. `main()` dispatches them
# before any client setup so they work on a bare laptop (`repos` reads the filesystem;
# `init-product` writes two files into another repo; `evals` reads run folders and scores).
LOCAL_ONLY_CMDS = {"repos", "init-product", "evals"}


def cmd_evals(argv: list[str]) -> None:
    """`pipeline.py evals build | run --suite <name> [--live] | report` (D20, tools/evals/).
    Local-only: reading run folders and scoring needs no Azure; `run --live` configures
    the client itself."""
    sys.path.insert(0, str(REPO / "tools" / "evals"))
    import evals_cli  # noqa: PLC0415 — deliberately lazy; the daemon never imports the evals
    evals_cli.main(argv)


# Commands that cannot do anything without a model: they execute agent turns.
# Everything else is database / run-folder / git work and must not need Azure.
MODEL_CMDS = frozenset({"daemon", "step", "ask", "babysit"})


def configure_model_client(required: bool) -> bool:
    """Point the Agents SDK at Azure OpenAI (Responses API — chat_completions drops
    image tool outputs, blinding vision critique loops; see orchestrator.py).

    Returns whether a client was configured. With `required` a missing configuration
    is a one-line exit; without it the command proceeds — a stage that later needs the
    model fails with the same readable error instead of the process dying.
    """
    try:
        client = azure_v1_client()
    except ModelStackError as e:
        if required:
            sys.exit(str(e))
        return False
    set_default_openai_client(client)
    set_default_openai_api(os.environ.get("LANTERN_OPENAI_API", "responses"))
    return True


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in LOCAL_ONLY_CMDS:
        if sys.argv[1] == "repos":
            cmd_repos()
            return
        if sys.argv[1] == "evals":      # D20: the factory's evals, no Azure client needed
            cmd_evals(sys.argv[2:])
            return
        import init_product      # D21: `pipeline.py init-product <path> [--force] [--dry-run]`
        sys.exit(init_product.main(sys.argv[2:]))
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
    p.add_argument("--design-mode", choices=DESIGN_MODES, default="",
                   help="how stage 1 converges (D25): paper = Paper artboards on a design "
                        "workstation (default); html = HTML prototypes + browser screenshots "
                        "on the ec2 runner, no Paper seat needed")
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
    p = sub.add_parser("set-design-mode", help="paper (design workstation) or html (ec2 runner, "
                                               "HTML prototypes + screenshots) for stage 1 (D25)")
    p.add_argument("run_id"); p.add_argument("mode", choices=DESIGN_MODES)
    p = sub.add_parser("publish", help="(re)push an auto-coding run's branch and open/refresh "
                                       "its PR from the 03-coding handoff")
    p.add_argument("run_id")
    p = sub.add_parser("daemon")
    p.add_argument("--runner", choices=["ec2", "workstation"],
                   default=os.environ.get("LANTERN_RUNNER", "ec2"))
    for name in ("approve", "reject"):
        p = sub.add_parser(name); p.add_argument("run_id"); p.add_argument("gate")
        p.add_argument("--by", required=True); p.add_argument("--note", default="")
    p = sub.add_parser("step", help="execute one run's current stage once, in the foreground, then exit "
                                    "(a single daemon tick — laptops and debugging)")
    p.add_argument("run_id")
    p.add_argument("--runner", choices=["ec2", "workstation"],
                   default=os.environ.get("LANTERN_RUNNER", "ec2"))
    p = sub.add_parser("retry"); p.add_argument("run_id")
    p = sub.add_parser("rework", help="send a failed/waiting run back to an earlier stage "
                                      "(D17 loop: validation or QA findings → the builder)")
    p.add_argument("run_id"); p.add_argument("--to", required=True, choices=REWORK_TARGETS)
    p.add_argument("--by", default=os.environ.get("USERNAME") or os.environ.get("USER", "unknown"))
    p.add_argument("--note", default="")
    p = sub.add_parser("qa-preflight", help="can a QA stage reach its target, from the sandbox?")
    p.add_argument("--stage", choices=sorted(QA_TARGET_PREFIX), default="qa-dev")
    p = sub.add_parser("qa-target", help="point a QA stage at a running app: write its URL, user "
                                         "and password into .env (values never printed)")
    p.add_argument("stage", choices=sorted(QA_TARGET_PREFIX))
    p.add_argument("--base-url", required=True, help="as a sandbox container reaches it, e.g. http://172.17.0.1:8000")
    p.add_argument("--user", default="", help="the QA account's login; a changed user regenerates the password")
    p.add_argument("--pass", dest="password", default="", help="use this password instead of generating one")
    p.add_argument("--rotate-pass", action="store_true", help="generate a new password even for an unchanged user")
    p.add_argument("--env-file", default="", help="default: tools/azure-runner/.env")
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
    # D21: install the factory's quality gate into a product repo. Dispatched before this
    # parser runs (LOCAL_ONLY_CMDS) — registered here so `--help` lists it.
    p = sub.add_parser("init-product", help="detect a product repo's stack, write its "
                                            "lantern.toml and note the factory in its AGENTS.md")
    p.add_argument("path"); p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    # D20: the debug lifecycle's front door + the factory's evals (intake.py, tools/evals/)
    p = sub.add_parser("bug", help="open a bug run from UNTRUSTED feedback (text or a file) at 01-triage")
    p.add_argument("feedback", help="the report text, or a path to a file holding it")
    p.add_argument("--source", choices=intake.SOURCES, default="user")
    p.add_argument("--by", default=os.environ.get("USERNAME") or os.environ.get("USER", "unknown"))
    p.add_argument("--product-repo", default=""); p.add_argument("--product-branch", default="")
    p.add_argument("--working-branch", default="")
    p.add_argument("--coding-mode", choices=CODING_MODES, default="",
                   help="who writes the fix: human (default) or the coding agent (auto)")
    p.add_argument("--shepherd", default="", help="human pinged at fix-ready (default LANTERN_DEFAULT_SHEPHERD)")
    p.add_argument("--run-id", default=""); p.add_argument("--slug", default="")
    p.add_argument("--follow", action="store_true")
    p = sub.add_parser("evals", help="the factory measures itself: build | run --suite <name> [--live] | report")
    p.add_argument("evals_args", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    # The model client is wired AFTER argparse, and only insisted on by the commands
    # that run an agent turn: `--help`, `init-db`, `status`, `approve`, … must work on a
    # box with no Azure credentials (bug-20260908-help-crash-without-env).
    configure_model_client(required=a.cmd in MODEL_CMDS
                           or (a.cmd in ("run", "bug") and a.follow))

    match a.cmd:
        case "init-db": asyncio.run(cmd_init_db())
        case "run":     asyncio.run(cmd_run(a.brief, a.run_id, a.by, a.follow,
                                            a.product_repo, a.product_branch, a.coding_mode,
                                            a.working_branch, a.design_mode))
        case "set-product":   asyncio.run(cmd_set_product(a.run_id, a.repo, a.branch,
                                                          a.working_branch))
        case "repos":   cmd_repos()
        case "set-coding-mode": asyncio.run(cmd_set_coding_mode(a.run_id, a.mode))
        case "set-design-mode": asyncio.run(cmd_set_design_mode(a.run_id, a.mode))   # D25
        case "publish":       asyncio.run(cmd_publish(a.run_id))
        case "daemon":  asyncio.run(cmd_daemon(a.runner))
        case "approve": asyncio.run(cmd_decide(a.run_id, a.gate, a.by, a.note, True))
        case "reject":  asyncio.run(cmd_decide(a.run_id, a.gate, a.by, a.note, False))
        case "step":    asyncio.run(cmd_step(a.run_id, a.runner))
        case "retry":   asyncio.run(cmd_retry(a.run_id))
        case "rework":  asyncio.run(cmd_rework(a.run_id, a.to, a.by, a.note))
        case "status":  asyncio.run(cmd_status(a.json))
        case "qa-preflight":  asyncio.run(cmd_qa_preflight(a.stage))
        case "qa-target":     cmd_qa_target(a.stage, a.base_url, a.user, a.password, a.rotate_pass, a.env_file)
        case "agents":  asyncio.run(cmd_agents())
        case "ask":     asyncio.run(cmd_ask(a.role, a.prompt, a.session, a.by,
                                            a.new, a.interactive, a.no_browser))
        case "runboard":      asyncio.run(cmd_runboard())
        case "usage":         asyncio.run(cmd_usage(a.days))
        case "usage-check":   asyncio.run(cmd_usage_check())
        case "render-memory": asyncio.run(cmd_render_memory(a.role))
        case "import-run":    asyncio.run(cmd_import_run(a.run_id, a.by, a.stage, a.status, a.gate))
        case "babysit":       asyncio.run(review.cmd_babysit(a.run_id, a.force))   # D19
        case "bug":           asyncio.run(intake.cmd_bug(a.feedback, a.source, a.by, a.product_repo,   # D20
                                                         a.product_branch, a.working_branch, a.coding_mode,
                                                         a.shepherd, a.run_id, a.slug, a.follow))
        case "evals":         cmd_evals(a.evals_args)   # D20


if __name__ == "__main__":
    main()
