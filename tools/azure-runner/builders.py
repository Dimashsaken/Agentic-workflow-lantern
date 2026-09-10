"""Parallel scoped builders for stage 3 (D18) — Ray Fu's back-end/front-end engineers.

When `02-pre-coding/plan.json` declares a `builders` list, stage 3 stops being one
agent with the whole checkout and becomes N agents, each confined to its own write
scope, each on its own branch, run in batches; then the HOST merges their branches and
ONE integrator execution makes the merged branch green. When the plan declares no
builders, `run_coding` is a pass-through and stage 3 is byte-for-byte what it was.

    plan.json builders:  [{name, write_scope: [globs], tasks: [ids], criteria: [AC ids]}]
    execution keys:      03-coding.<name>  …  then  03-coding.integrate
    branches:            <run work branch>--<name>  →  merged into <run work branch>
    run folder:          03-coding/builders/<name>/{report.md,handoff.json,branch.bundle,gate.json}
                         03-coding/builders.json   the merge record
                         03-coding/{report.md,handoff.json,branch.bundle}   the integrator's

Three rules shape this module:

1. **The host merges, never an agent** (D6). A builder cannot see, fetch or push a
   sibling's branch; the only thing that crosses is the bundle it writes into the run
   folder, and the host verifies each one before it lands in the mirror.
2. **A conflict is a planning failure, not a puzzle to solve.** Two builders touching
   one file means the split was wrong, so the merge fails the stage with the file list
   and the rework hint instead of asking a model to resolve it.
3. **Parallelism is capped by the executor's own concurrency**, and is 1 in-process on
   purpose: the in-process path configures each execution through `os.environ`
   (LANTERN_PRODUCT_DIR, LANTERN_CODING_BRANCH, LANTERN_BUILDER), which two concurrent
   executions in one process would overwrite for each other. Docker gives each
   execution its own container and its own env, so there the cap is real parallelism.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import factory
import execution_runtime as ownership
from orchestrator import CODING_BRANCH_PREFIXES, check_coding_handoff

INTEGRATOR = factory.INTEGRATOR
CODING_STAGE = "03-coding"
PARALLELISM_DEFAULT = 2
MERGE_RECORD = factory.MERGE_RECORD       # factory owns the run-folder file shapes
merge_record = factory.merge_record


class BuilderError(RuntimeError):
    """The fan-out could not be set up, or a builder's handoff was rejected."""


class MergeConflict(BuilderError):
    """Two builders changed the same file — the split itself was wrong."""

    def __init__(self, builder: str, files: list[str], run_id: str):
        self.builder, self.files = builder, files
        shown = ", ".join(files[:12]) + (" …" if len(files) > 12 else "")
        super().__init__(
            f"builder '{builder}' conflicts with an already-merged builder in "
            f"{len(files)} file(s): {shown} — two builders were given the same file, so "
            "the split in 02-pre-coding/plan.json is wrong, not the code. Re-plan the "
            "write scopes (one surface, one builder) with "
            f"`pipeline.py rework {run_id} --to 02-pre-coding`, or drop the builders list "
            "to build this run with a single builder.")


# ── naming ───────────────────────────────────────────────────────────────────

name_for = factory.builder_of      # '03-coding.api' → 'api'; one definition, in factory


def stage_key(name: str) -> str:
    return f"{CODING_STAGE}.{name}"


def branch_for(work: str, stage: str) -> str:
    """The branch an execution of stage 3 works on.

    A named builder gets `<work>--<name>`; the plain stage and the integrator work on
    the run's branch itself, so `_publish_branch` still sees exactly one handoff for it.
    """
    name = name_for(stage)
    if not work or not name or name == INTEGRATOR:
        return work
    return f"{work}--{name}"


def check_branch(branch: str) -> str:
    """A builder branch must stay in the namespace D6 lets agents push to."""
    if not branch.startswith(CODING_BRANCH_PREFIXES):
        raise BuilderError(
            f"builder branch '{branch}' is outside the pushable namespace "
            f"{'|'.join(p + '*' for p in CODING_BRANCH_PREFIXES)} (D6)")
    return branch


def builder_names(run_id: str) -> list[str]:
    """The plan's builder names in plan order — [] for a single-builder run."""
    return [str(b["name"]) for b in factory.plan_builders(run_id)]


# ── batching ─────────────────────────────────────────────────────────────────

def max_concurrency() -> int:
    """The dispatcher's own cap — and 1 in-process, where env is shared (see §3 above)."""
    try:
        import pipeline                     # late: pipeline imports this module
    except ImportError:                     # pragma: no cover - pipeline is always there
        return 1
    return 1 if pipeline.EXECUTOR != "docker" else max(1, int(pipeline.MAX_CONCURRENCY))


def parallelism(cap: int | None = None) -> int:
    """How many builders may run at once: LANTERN_BUILDER_PARALLELISM, never above the
    executor's concurrency and never below 1."""
    try:
        want = int(os.environ.get("LANTERN_BUILDER_PARALLELISM", PARALLELISM_DEFAULT))
    except ValueError:
        want = PARALLELISM_DEFAULT
    return max(1, min(want, max_concurrency() if cap is None else cap))


def batches(names: list[str], size: int) -> list[list[str]]:
    size = max(1, size)
    return [names[i:i + size] for i in range(0, len(names), size)]


async def fan_out(conn, run_id: str, runner: str, names: list[str], execute, size: int,
                  connect=None) -> None:
    """Run each builder's execution, `size` at a time, in plan order.

    A batch runs to completion before the next starts, and one failure fails the stage:
    a merge is only meaningful when every branch it merges is green.
    """
    async def execute_independent(name):
        if connect is None:
            if conn is not None:
                raise BuilderError("parallel builders require independent database connections")
            return await execute(None, run_id, stage_key(name), runner)
        child_conn = await connect()
        try:
            return await execute(child_conn, run_id, stage_key(name), runner)
        finally:
            await child_conn.close()

    for batch in batches(names, size):
        if len(batch) == 1:
            await execute(conn, run_id, stage_key(batch[0]), runner)
            continue
        done = await asyncio.gather(
            *(execute_independent(n) for n in batch),
            return_exceptions=True)
        for name, out in zip(batch, done):
            if isinstance(out, BaseException):
                if isinstance(out, ownership.leases.LeaseLost):
                    raise out
                raise BuilderError(f"builder '{name}' failed: {out}") from out


# ── git (host side) ──────────────────────────────────────────────────────────

def _git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          timeout=600, errors="replace",
                          env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})


def _rev(repo: Path, ref: str) -> str:
    r = _git("rev-parse", "--verify", "-q", f"{ref}^{{commit}}", cwd=repo)
    return r.stdout.strip() if r.returncode == 0 else ""


def seed_branches(repo: str, base: str, work: str, names: list[str]) -> tuple[Path, str]:
    """Create every builder's branch at ONE start point, in the host mirror.

    All builders start from the same commit — the run's branch if it already exists
    (a continued branch, D15), otherwise the base — so the merge is a fan-in from a
    single point and each builder's `base..HEAD` is exactly its own work.
    """
    import pipeline                                 # late: pipeline imports this module
    mirror = pipeline.sync_product_mirror(repo)
    start = _rev(mirror, work) or _rev(mirror, base)
    if not start:
        raise BuilderError(f"neither the run branch '{work}' nor the base '{base}' exists "
                           f"in {repo} — nothing for the builders to start from")
    for name in names:
        branch = check_branch(f"{work}--{name}")
        r = _git("branch", "-f", branch, start, cwd=mirror)
        if r.returncode != 0:
            raise BuilderError(f"could not create builder branch '{branch}': "
                               f"{pipeline._scrub(r.stderr)[-300:]}")
    return mirror, start


def merge(run_id: str, repo: str, base: str, work: str, names: list[str],
          start: str = "", *, persist: bool = True) -> dict:
    """Land each builder's bundle in the mirror, then build the run's branch from them.

    Reset `work` to the shared start point and `git merge --no-ff` each builder branch
    in PLAN order (so the history reads the way the plan does), in a throwaway clone —
    the mirror may be bare, and a local-path product repo must not grow a worktree.
    The merged branch is pushed back into the mirror, which is where the integrator's
    checkout comes from. ``persist=False`` defers the authoritative merge record
    until the async caller rechecks its run fence after the Git work returns.
    """
    import pipeline                                 # late: pipeline imports this module
    mirror = pipeline.sync_product_mirror(repo)
    if not start:
        start = _rev(mirror, work) or _rev(mirror, base)
    if not start:
        raise BuilderError(f"no start point for '{work}' in {repo}")
    sdir = factory.run_dir(run_id) / CODING_STAGE

    entries: list[dict] = []
    for name in names:
        branch = check_branch(f"{work}--{name}")
        problems = check_coding_handoff(run_id, CODING_STAGE, verify_in=mirror, builder=name)
        if problems:
            raise BuilderError(f"builder '{name}' handoff rejected: " + "; ".join(problems))
        handoff = json.loads(
            (sdir / factory.BUILDERS_DIR / name / "handoff.json").read_text(encoding="utf-8"))
        if handoff.get("branch") != branch:
            raise BuilderError(f"builder '{name}' handed off branch "
                               f"'{handoff.get('branch')}', expected '{branch}'")
        bundle = factory.REPO / handoff["bundle"]
        r = _git("fetch", "--quiet", str(bundle),
                 f"+refs/heads/{branch}:refs/heads/{branch}", cwd=mirror)
        if r.returncode != 0:
            raise BuilderError(f"could not land builder '{name}' in the mirror: "
                               f"{pipeline._scrub(r.stderr)[-300:]}")
        if _rev(mirror, branch) != handoff.get("head_sha"):
            raise BuilderError(f"builder '{name}': mirror head does not match its handoff")
        entries.append({"name": name, "branch": branch, "head_sha": handoff["head_sha"],
                        "commits": len(handoff.get("commits") or []),
                        "files_changed": list(handoff.get("files_changed") or [])})

    tmp = Path(tempfile.mkdtemp(prefix="lantern-merge-"))
    try:
        wt = tmp / "merge"
        r = _git("clone", "--quiet", "--no-hardlinks", str(mirror), str(wt))
        if r.returncode != 0:
            raise BuilderError(f"could not clone the mirror to merge: "
                               f"{pipeline._scrub(r.stderr)[-300:]}")
        _git("config", "user.name", pipeline.GIT_AUTHOR_NAME, cwd=wt)
        _git("config", "user.email", pipeline.GIT_AUTHOR_EMAIL, cwd=wt)
        _git("config", "commit.gpgsign", "false", cwd=wt)
        r = _git("checkout", "-q", "-B", work, start, cwd=wt)
        if r.returncode != 0:
            raise BuilderError(f"could not start '{work}' at {start[:12]}: "
                               f"{r.stderr.strip()[-300:]}")
        for e in entries:
            r = _git("merge", "--no-ff", "-m",
                     f"{run_id}: merge builder {e['name']} ({e['branch']})", e["head_sha"],
                     cwd=wt)
            if r.returncode != 0:
                conflicts = [ln.strip() for ln in _git(
                    "diff", "--name-only", "--diff-filter=U", cwd=wt).stdout.splitlines()
                    if ln.strip()]
                _git("merge", "--abort", cwd=wt)
                raise MergeConflict(e["name"], conflicts, run_id)
        head = _rev(wt, "HEAD")
        r = _git("push", "--quiet", "--force", str(mirror),
                 f"HEAD:refs/heads/{work}", cwd=wt)
        if r.returncode != 0:
            raise BuilderError(f"could not put the merged '{work}' back in the mirror: "
                               f"{pipeline._scrub(r.stderr)[-300:]}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    record = {
        "kind": "builder_merge", "run_id": run_id, "branch": work, "base": base,
        "start_sha": start, "head_sha": head,
        "merged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "builders": entries,
    }
    if persist:
        write_merge_record(record)
    return record


def write_merge_record(record: dict) -> None:
    """Publish the accepted merge facts; leased callers hold the run fence here."""
    sdir = factory.run_dir(record['run_id']) / CODING_STAGE
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / MERGE_RECORD).write_text(json.dumps(record, indent=2), encoding="utf-8")
    (sdir / "builders.md").write_text(render_merge_md(record), encoding="utf-8")


def render_merge_md(record: dict) -> str:
    lines = [f"# Parallel builders — {record['run_id']}", "",
             f"- **Branch:** `{record['branch']}` (built from `{record['start_sha'][:12]}`)",
             f"- **Merged head:** `{record['head_sha'][:12]}` at {record['merged_at']}", "",
             "| builder | branch | commits | files |", "|---------|--------|---------|-------|"]
    for b in record["builders"]:
        lines.append(f"| {b['name']} | `{b['branch']}` | {b['commits']} | "
                     f"{len(b['files_changed'])} |")
    lines += ["", "Each builder ran in its own execution, confined to its own write scope, "
              "and the host merged the branches in plan order (`--no-ff`, so each builder's "
              "work is one readable arc). The integrator execution then made the merged "
              "branch green; its handoff is the stage's handoff."]
    return "\n".join(lines) + "\n"


# ── the stage ────────────────────────────────────────────────────────────────

async def run_coding(conn, run_id: str, stage: str, runner: str, execute) -> list[dict]:
    """Stage 3 in auto mode. Returns the builder summary for the code_complete payload.

    No `builders` in the plan → `execute(conn, run_id, stage, runner)`, unchanged, and
    an empty list. Otherwise: seed the branches, run the builders in batches, merge on
    the host, then run the single integrator execution whose handoff the host publishes.
    """
    names = builder_names(run_id)
    if not names:
        await execute(conn, run_id, stage, runner)
        return []
    import pipeline                                 # late: pipeline imports this module
    repo, base = await pipeline.product_target(conn, run_id)
    if not repo:
        raise BuilderError("parallel builders need a product repo — set one with "
                           f"`pipeline.py set-product {run_id} --repo … --branch …`")
    work = await pipeline.product_work_branch(conn, run_id)
    size = parallelism()
    async with ownership.mutation(conn):
        await pipeline.log_event(conn, run_id, "orchestrator", "builders_seed_intended",
                                 {"branch": work, "builders": names})
    # Git subprocesses in a thread are not revocable. Lost ownership prevents
    # acceptance, while interrupted work remains held for mirror reconciliation.
    _, start = await asyncio.to_thread(seed_branches, repo, base, work, names)
    async with ownership.mutation(conn):
        await pipeline.log_event(conn, run_id, "orchestrator", "builders_fanout",
                                 {"builders": names, "branch": work, "start_sha": start,
                                  "parallelism": size})
    print(f"[{run_id}] stage 3 fans out into {len(names)} builder(s) "
          f"({', '.join(names)}), {size} at a time, from {start[:12]}")

    await fan_out(conn, run_id, runner, names, execute, size, connect=pipeline.connect)

    async with ownership.mutation(conn):
        await pipeline.log_event(conn, run_id, "orchestrator", "builders_merge_intended",
                                 {"branch": work, "start_sha": start, "builders": names})
    record = await asyncio.to_thread(merge, run_id, repo, base, work, names, start, persist=False)
    async with ownership.mutation(conn):
        write_merge_record(record)
        await pipeline.log_event(conn, run_id, "orchestrator", "builders_merged",
                                 {"branch": work, "head_sha": record["head_sha"],
                                  "builders": [b["name"] for b in record["builders"]]})
    print(f"[{run_id}] merged {len(names)} builder branch(es) into {work} "
          f"@ {record['head_sha'][:12]} — integrating")

    await execute(conn, run_id, stage_key(INTEGRATOR), runner)
    return [{"name": b["name"], "branch": b["branch"], "commits": b["commits"],
             "files_changed": len(b["files_changed"])} for b in record["builders"]]
