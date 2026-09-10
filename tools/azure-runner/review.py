"""Review loop and merge babysitter (D19) — the two halves of Boundary's rule for a PR:

    "Do not notify a human until the review bot is happy — at most N rounds, then a
     human. After the human approves, keep the branch mergeable until a human merges."

Review loop (`after_publish`, called by pipeline.step_run right after the coding branch
is published): run the `reviewer` role as execution `03-coding.review`; on
`request_changes` run a fix execution `03-coding.fix` (the `coding` role, writable, on
the same branch, its task block = the review's must_fix list), publish again, review
again — at most LANTERN_REVIEW_ROUNDS reviews. Approve, or rounds exhausted, or an
execution failing: the `code_complete` gate opens with the last review attached and the
human decides. The human is pinged once, at the end.

Merge babysitter (`babysit_run`, `pipeline.py babysit`, a daemon tick every
LANTERN_BABYSIT_MINUTES): for runs past an approved code_complete whose PR is not merged,
merge the base into the run branch (a host trial merge first — a conflict stops with
03-coding/merge-conflict.md and an alarm), push the merge commit, re-run the product's
lantern.toml quality commands as code (`03-coding.regate` — in the sandbox image under
the docker executor, in a temp clone otherwise), and spend one fix execution only when
that gate is red. It records `branch_merged` when GitHub says the PR merged. It never
merges into the base: humans merge (D6, D14).

Pure where it can be: the envelope shape lives in factory.py (`_check_review`), git runs
through subprocess, and everything that needs the runtime (executions, publishing, the
DB, GitHub, the alarm webhook) arrives through `Deps`, so test_review.py exercises the
loop and the babysitter with fakes and real git, no database and no network.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

import factory

REVIEW_STAGE = "03-coding.review"
FIX_STAGE = "03-coding.fix"
REGATE_STAGE = "03-coding.regate"
CODING_DIR = "03-coding"
# Sub-stage executions share the coding stage's run-folder dir (pipeline.STAGE_DIR).
SUB_STAGE_DIRS = {REVIEW_STAGE: CODING_DIR, FIX_STAGE: CODING_DIR, REGATE_STAGE: CODING_DIR}
# Executions that get the writable checkout + shell, like 03-coding itself (D14).
WRITABLE_STAGES = {FIX_STAGE}
# Executions whose system prompt gets a task block from this module.
TASK_BLOCK_STAGES = {REVIEW_STAGE, FIX_STAGE}
REVIEW_ROUNDS_DEFAULT = 2
BABYSIT_MINUTES_DEFAULT = 30
REVIEW_DIR = "review"          # 03-coding/review/{round-<n>.md, review.json, state.json}
BABYSIT_DIR = "babysit"        # 03-coding/babysit/{state.json, regate-<n>.json, regate-<n>.md}
STATE_FILE = "state.json"
CONFLICT_FILE = "merge-conflict.md"
REGATE_MARKER = "LANTERN_REGATE "
BOT_TRAILER = "Lantern-Agent: babysitter"
PR_URL = re.compile(r"^https://github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)")
GITHUB_REPO = re.compile(r"^https://github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?/?$")


# ── knobs ────────────────────────────────────────────────────────────────────

def _env_int(name: str, default: int, floor: int) -> int:
    try:
        return max(floor, int(os.environ.get(name, default)))
    except ValueError:
        return default


def review_rounds() -> int:
    """How many review executions a branch gets before a human sees it (0 = no review)."""
    return _env_int("LANTERN_REVIEW_ROUNDS", REVIEW_ROUNDS_DEFAULT, 0)


def babysit_minutes() -> int:
    return _env_int("LANTERN_BABYSIT_MINUTES", BABYSIT_MINUTES_DEFAULT, 1)


# ── run-folder files (D4: the run folder is the only handoff channel) ────────

def review_dir(run_id: str) -> Path:
    return factory.run_dir(run_id) / CODING_DIR / REVIEW_DIR


def babysit_dir(run_id: str) -> Path:
    return factory.run_dir(run_id) / CODING_DIR / BABYSIT_DIR


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    data, _ = factory._load_json(path)
    return data


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def load_review(run_id: str) -> dict | None:
    """The current review envelope (the last round's), or None."""
    return _read_json(review_dir(run_id) / "review.json")


def load_handoff(run_id: str) -> dict:
    return _read_json(factory.run_dir(run_id) / CODING_DIR / "handoff.json") or {}


def read_state(run_id: str) -> dict:
    return _read_json(review_dir(run_id) / STATE_FILE) or {}


def write_state(run_id: str, **fields) -> dict:
    """review/state.json — what the next execution is for (round, phase, must_fix …).

    Written by the HOST before each execution; read by the prompt builder in whichever
    process runs the agent (the sandbox sees it through the run-dir mount), so the
    round number and the fix list never travel through env vars or the model's memory.
    """
    st = {"kind": "review_state", "run_id": run_id,
          "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **fields}
    _write_json(review_dir(run_id) / STATE_FILE, st)
    return st


def read_babysit_state(run_id: str) -> dict:
    return _read_json(babysit_dir(run_id) / STATE_FILE) or {}


def write_babysit_state(run_id: str, **fields) -> dict:
    st = {"kind": "babysit_state", "run_id": run_id,
          "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **fields}
    _write_json(babysit_dir(run_id) / STATE_FILE, st)
    return st


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── the review envelope, summarised for events, gate payloads and prompts ────

def review_summary(review: dict) -> dict:
    findings = [f for f in review.get("findings", []) if isinstance(f, dict)]
    by = {s: sum(1 for f in findings if f.get("severity") == s) for s in factory.REVIEW_SEVERITIES}
    must = [m for m in review.get("must_fix", []) if isinstance(m, str)]
    return {
        "round": review.get("round"), "verdict": review.get("verdict"),
        "findings": len(findings), **{f"{s}s": n for s, n in by.items()},
        "must_fix": must,
        "items": [{k: f.get(k) for k in ("id", "severity", "file", "line", "summary")}
                  for f in findings[:20]],
        "file": f"workflow/runs/{review.get('run_id')}/{CODING_DIR}/{REVIEW_DIR}/round-{review.get('round')}.md",
    }


def _finding_line(f: dict) -> str:
    where = f.get("file") or ""
    if where and f.get("line"):
        where += f":{f['line']}"
    sug = f" → {f['suggestion']}" if f.get("suggestion") else ""
    return f"- **{f.get('id')}** [{f.get('severity')}] `{where or 'general'}` — {f.get('summary')}{sug}"


# ── prompt blocks (hooked into orchestrator.product_task_block) ──────────────

def task_block(run_id: str, stage: str) -> str:
    """The task block for a review round or a fix execution, from review/state.json.

    Empty when there is no state (a manual `orchestrator.py` run of these stages).
    """
    st = read_state(run_id)
    if not st:
        return ""
    if stage == REVIEW_STAGE:
        return _review_block(run_id, st)
    if stage == FIX_STAGE:
        return _fix_block(run_id, st)
    return ""


def _review_block(run_id: str, st: dict) -> str:
    h = load_handoff(run_id)
    n, total = st.get("round", 1), st.get("max_rounds", review_rounds())
    out = [f"\n\n## This review round — {n} of {total}\n",
           f"You are the review bot for branch `{h.get('branch', '?')}`. Review EXACTLY the "
           f"handoff range `{str(h.get('base_sha', ''))[:12]}..{str(h.get('head_sha', ''))[:12]}` "
           f"({len(h.get('commits', []))} commit(s), {len(h.get('files_changed', []))} file(s) — "
           f"`read_file('workflow/runs/{run_id}/{CODING_DIR}/handoff.json')`). The checkout "
           "under `product/` is on that branch, read-only.\n"]
    hist = [x for x in st.get("history", []) if isinstance(x, dict)]
    if hist:
        out.append("\nEarlier rounds on this branch:\n")
        for x in hist:
            fixed = x.get("fixed")
            out.append(f"- round {x.get('round')}: {x.get('verdict')}"
                       + (f", must-fix {', '.join(x.get('must_fix', []))}" if x.get("must_fix") else "")
                       + (f"; a fix execution then added {fixed.get('commits')} commit(s) up to "
                          f"`{str(fixed.get('head_sha', ''))[:12]}`" if fixed else "")
                       + (f"; the fix execution FAILED: {x['fix_error'][:160]}" if x.get("fix_error") else "")
                       + "\n")
        out.append(f"Read `{CODING_DIR}/{REVIEW_DIR}/round-{n - 1}.md` and the `## Fix — round {n - 1}` "
                   f"section of `{CODING_DIR}/report.md`; verify each earlier must-fix id in the new "
                   "diff and carry forward, same id, anything not actually resolved.\n")
    out.append(f"\nDeliverables: `{CODING_DIR}/{REVIEW_DIR}/round-{n}.md`, "
               f"`{CODING_DIR}/{REVIEW_DIR}/review.json` with `\"round\": {n}` (skills §4 — validated: "
               "approve ⇔ no blocker/major, must_fix ⊇ every blocker/major), a `## Review — round "
               f"{n}` section APPENDED to `{CODING_DIR}/report.md` with its own `- **Status:**` line, "
               "and append_memory. "
               + ("This is the LAST round: whatever you write goes to the human as-is.\n" if n >= total
                  else "If you request changes, a fix execution works your must_fix list and you "
                       "review again.\n"))
    return "".join(out)


def _fix_block(run_id: str, st: dict) -> str:
    fix = st.get("fix") or {}
    h = load_handoff(run_id)
    branch = h.get("branch", "?")
    if fix.get("source") == "regate":
        gate = fix.get("gate") or {}
        brief = factory.gate_failure_brief(gate) if gate.get("results") else "(no failure output recorded)"
        return (f"\n\n## Your task in THIS execution: the merged branch is red\n"
                f"The merge babysitter (D19) merged `{fix.get('base')}` "
                f"(`{str(fix.get('base_sha', ''))[:12]}`) into `{branch}` — merge commit "
                f"`{str(fix.get('merge_sha', ''))[:12]}`, already on the branch you are checked out "
                "on — and the product's own quality commands then FAILED. Fix what the merge "
                "broke and nothing else: no new features, no plan tasks. Re-run the failing "
                "command with product_shell until green, commit (`" + run_id + ": fix after "
                "merge — <what>`), append a `## Regate fix` section to `03-coding/report.md` "
                "(own `- **Status:**` line) saying what broke and what you changed, and "
                "append_memory. Ignore the plan's task list above for this execution — it was "
                "already implemented.\n\nFailures (only):\n\n" + brief + "\n")
    review = load_review(run_id) or {}
    findings = {f.get("id"): f for f in review.get("findings", []) if isinstance(f, dict)}
    must = [findings[i] for i in fix.get("must_fix", []) if i in findings]
    rest = [f for i, f in findings.items() if i not in set(fix.get("must_fix", []))]
    n = fix.get("round", review.get("round", 1))
    out = [f"\n\n## Your task in THIS execution: the review's must-fix list (round {n})\n",
           f"The review bot requested changes on `{branch}` (see "
           f"`{CODING_DIR}/{REVIEW_DIR}/round-{n}.md`). The branch is checked out here, writable, "
           "with every earlier commit in place. Ignore the plan's task list above for this "
           "execution — it was already implemented; your job is the list below.\n",
           "\nFix EVERY item, in order:\n\n"]
    out += [_finding_line(f) + "\n" for f in must] or ["- (the review named no must-fix ids)\n"]
    if rest:
        out.append("\nOther findings — fix them only if it is cheap and adjacent:\n\n")
        out += [_finding_line(f) + "\n" for f in rest]
    out.append("\nRules: a test for every behaviour change; one commit per item "
               f"(`{run_id}: fix {must[0].get('id') if must else 'R-n'} — <what>`); run the gate "
               "commands yourself before you finish; then APPEND a `## Fix — round "
               f"{n}` section to `{CODING_DIR}/report.md` (own `- **Status:**` line) with one line "
               "per id saying what changed, and append_memory. If an item is wrong — the reviewer "
               "misread the code — say so under that id in the report and leave the code; the "
               "next review round decides. A `Status: BLOCKED` is for a contradiction you "
               "cannot resolve, not for disagreement.\n")
    return "".join(out)


# ── runtime dependencies, injectable ────────────────────────────────────────

@dataclass
class Deps:
    """Everything this module needs from the rest of the runtime. `default_deps()` binds
    the real pipeline; tests build one with fakes and real git."""
    execute: Callable[..., Awaitable[None]]        # (conn, run_id, stage, runner) -> None
    publish: Callable[..., Awaitable[dict]]        # (conn, run_id) -> code_complete payload
    product: Callable[..., Awaitable[tuple]]       # (conn, run_id) -> (repo, base, work_branch)
    mirror: Callable[[str], Path]                  # repo -> refreshed host mirror (or the local path)
    event: Callable[..., Awaitable[None]]          # (conn, run_id, actor, type, data) -> None
    gh_api: Callable[..., tuple] | None = None     # (method, path, data) -> (status, obj); None = no token
    alarm: Callable[[str], None] = print           # LANTERN_ALARM_WEBHOOK + stdout in production
    executor: str = "inprocess"                    # inprocess | docker
    sandbox_image: str = "lantern-sandbox"
    sandbox_cpus: str = "1.5"
    sandbox_memory: str = "2500m"
    repo_root: Path | None = None                  # the Lantern checkout, mounted /repo-src in the sandbox
    authed: Callable[[str], str] = lambda repo: repo   # repo -> push URL with credentials (host only)
    git_identity: tuple[str, str] = ("lantern-bot", "lantern-bot@users.noreply.github.com")
    public_url: str = ""


def default_deps(execute: Callable | None = None) -> Deps:
    """Bind the real pipeline. Imported lazily: pipeline imports this module at load."""
    import pipeline as p  # noqa: PLC0415

    async def product(conn, run_id: str) -> tuple[str, str, str]:
        repo, base = await p.product_target(conn, run_id)
        work = await p.product_work_branch(conn, run_id) if repo else ""
        return repo, base, work

    return Deps(
        execute=execute or (p.run_agent_stage_docker if p.EXECUTOR == "docker" else p.run_agent_stage),
        publish=p.publish_coding_branch, product=product, mirror=p.sync_product_mirror,
        event=p.log_event, gh_api=p._gh_api if p.GIT_TOKEN else None, alarm=p._post_alarm,
        executor=p.EXECUTOR, sandbox_image=p.SANDBOX_IMAGE, sandbox_cpus=p.SANDBOX_CPUS,
        sandbox_memory=p.SANDBOX_MEMORY, repo_root=p.REPO, authed=p._authed,
        git_identity=(p.GIT_AUTHOR_NAME, p.GIT_AUTHOR_EMAIL), public_url=p.PUBLIC_URL)


async def _mark_failed(conn, run_id: str, stage: str, err: Exception) -> None:
    """A sub-stage execution that raised inside our loop is not step_run's to close —
    it only knows the run's current stage. Close its row here, never raise."""
    try:
        await conn.execute(
            """UPDATE stage_executions SET status = 'failed', error = $1, error_class = $4, finished_at = now()
               WHERE run_id = $2 AND stage = $3 AND status = 'running'""",
            factory.redact(str(err))[:4000], run_id, stage, factory.classify_error(err))
    except Exception as e:  # noqa: BLE001
        print(f"[{run_id}] could not mark {stage} failed: {e}", file=sys.stderr)


# ── the review loop ──────────────────────────────────────────────────────────

async def after_publish(conn, run_id: str, payload: dict, runner: str = "ec2",
                        deps: Deps | None = None) -> dict:
    """Review → fix → publish → review …, bounded; returns the code_complete payload with
    a `review` block attached. Never raises: the branch is already published, and the
    gate must open for the human either way — with the last review, or the reason
    there is none."""
    deps = deps or default_deps()
    rounds = review_rounds()
    summary: dict[str, Any] = {"max_rounds": rounds, "rounds": [], "verdict": None,
                               "capped": False, "fix_executions": 0}
    payload = dict(payload)
    if rounds < 1:
        summary["verdict"] = "skipped"
        payload["review"] = summary
        return payload
    history: list[dict] = []
    for n in range(1, rounds + 1):
        write_state(run_id, phase="review", round=n, max_rounds=rounds, history=history)
        try:
            await deps.execute(conn, run_id, REVIEW_STAGE, runner)
            review = load_review(run_id)
            if not review or review.get("round") != n:
                raise RuntimeError(f"{CODING_DIR}/{REVIEW_DIR}/review.json missing or not round {n} "
                                   "after the review execution")
        except Exception as e:  # noqa: BLE001 — a failed review must not fail a published branch
            await _mark_failed(conn, run_id, REVIEW_STAGE, e)
            entry = {"round": n, "verdict": "error", "error": factory.redact(str(e))[:600]}
            history.append(entry)
            summary["verdict"] = "error"
            await deps.event(conn, run_id, "orchestrator", "review_failed", entry)
            print(f"[{run_id}] review round {n} FAILED — the gate opens without it: {e}",
                  file=sys.stderr)
            break
        entry = review_summary(review)
        entry["pr_review"] = await asyncio.to_thread(_post_review_for, payload, review, run_id, deps)
        history.append(entry)
        summary["verdict"] = review.get("verdict")
        await deps.event(conn, run_id, "agent:reviewer", "review_round",
                         {k: entry[k] for k in ("round", "verdict", "findings", "must_fix", "pr_review")})
        print(f"[{run_id}] review round {n}/{rounds}: {review.get('verdict')} "
              f"({entry['findings']} finding(s), must-fix {len(entry['must_fix'])})")
        if review.get("verdict") == "approve":
            break
        if n >= rounds:
            summary["capped"] = True
            await deps.event(conn, run_id, "orchestrator", "review_capped",
                             {"rounds": rounds, "must_fix": entry["must_fix"]})
            print(f"[{run_id}] review rounds exhausted with request_changes — a human decides")
            break
        write_state(run_id, phase="fix", round=n, max_rounds=rounds, history=history,
                    fix={"source": "review", "round": n, "must_fix": entry["must_fix"]})
        summary["fix_executions"] += 1
        try:
            await deps.execute(conn, run_id, FIX_STAGE, runner)
            fresh = await deps.publish(conn, run_id)
        except Exception as e:  # noqa: BLE001
            await _mark_failed(conn, run_id, FIX_STAGE, e)
            entry["fix_error"] = factory.redact(str(e))[:600]
            await deps.event(conn, run_id, "orchestrator", "review_fix_failed",
                             {"round": n, "error": entry["fix_error"]})
            print(f"[{run_id}] fix execution after round {n} FAILED — the gate opens with the "
                  f"review: {e}", file=sys.stderr)
            break
        payload.update(fresh)
        entry["fixed"] = {"head_sha": fresh.get("head_sha"), "commits": fresh.get("commit_count")}
    summary["rounds"] = history
    summary["last"] = history[-1] if history else None
    write_state(run_id, phase="done", round=len(history), max_rounds=rounds, history=history,
                verdict=summary["verdict"], capped=summary["capped"])
    payload["review"] = summary
    return payload


# ── GitHub: one PR review per round, from the bot identity (D6) ─────────────

def pr_review_request(review: dict, run_id: str, public_url: str = "") -> dict:
    """The body of POST /repos/{o}/{n}/pulls/{pr}/reviews. Always a COMMENT event: a bot
    APPROVE could satisfy a "one approving review" branch rule and a bot REQUEST_CHANGES
    would have to be dismissed by hand after a human overrules it at code_complete —
    the verdict is advisory, the human decides, so it goes in the text."""
    findings = [f for f in review.get("findings", []) if isinstance(f, dict)]
    must = set(review.get("must_fix", []))
    verdict = str(review.get("verdict", "")).upper().replace("_", " ")
    n = review.get("round")
    head = [f"**Lantern review — round {n}: {verdict}** "
            f"({len(must)} must-fix, {len(findings)} finding(s))", ""]
    if findings:
        head += ["| id | severity | where | finding | suggestion |", "|---|---|---|---|---|"]
        for f in findings:
            where = f.get("file") or ""
            if where and f.get("line"):
                where += f":{f['line']}"
            head.append(f"| {f.get('id')}{' ★' if f.get('id') in must else ''} | {f.get('severity')} | "
                        f"`{where or '-'}` | {str(f.get('summary', '')).replace('|', '/')} | "
                        f"{str(f.get('suggestion') or '').replace('|', '/')} |")
        head.append("")
        head.append("★ = must-fix (a fix execution works these on this branch).")
    else:
        head.append("No findings.")
    if public_url:
        head += ["", f"Mission Control: {public_url}/run/{run_id}"]
    head += ["", f"_Posted by the Lantern review bot from `workflow/runs/{run_id}/{CODING_DIR}/"
             f"{REVIEW_DIR}/review.json`. Advisory: a human approves `code_complete` and a human "
             "merges._"]
    comments = [{"path": f["file"], "line": int(f["line"]), "side": "RIGHT",
                 "body": f"**{f.get('id')}** [{f.get('severity')}] {f.get('summary')}"
                         + (f"\n\nSuggestion: {f['suggestion']}" if f.get("suggestion") else "")}
                for f in findings
                if isinstance(f.get("file"), str) and f.get("file")
                and isinstance(f.get("line"), int) and not isinstance(f.get("line"), bool)
                and f.get("line", 0) > 0]
    return {"event": "COMMENT", "body": "\n".join(head), "comments": comments}


def post_pr_review(owner: str, name: str, pr_number: int, review: dict, *, run_id: str = "",
                   gh_api: Callable[..., tuple] | None = None, public_url: str = "") -> dict:
    """Post the round's findings as ONE pull-request review. No token → nothing posted,
    nothing raised: the run folder is the record either way."""
    if gh_api is None:
        return {"posted": False, "reason": "no GITHUB_LANTERN_BOT_TOKEN on the host — review "
                                           "kept in the run folder only"}
    req = pr_review_request(review, run_id, public_url)
    path = f"/repos/{owner}/{name}/pulls/{pr_number}/reviews"
    try:
        status, body = gh_api("POST", path, req)
        if status == 422 and req["comments"]:
            # A finding on a line outside the PR diff makes GitHub refuse the whole
            # review; the findings are all in the body anyway — post without inline ones.
            status, body = gh_api("POST", path, {**req, "comments": []})
        if status in (200, 201) and isinstance(body, dict):
            return {"posted": True, "url": body.get("html_url"), "id": body.get("id"),
                    "inline": len(req["comments"]) if status in (200, 201) else 0}
        msg = body.get("message") if isinstance(body, dict) else str(body)
        return {"posted": False, "reason": f"GitHub answered {status}: {str(msg)[:300]}"}
    except Exception as e:  # noqa: BLE001 — never a failure
        return {"posted": False, "reason": f"{type(e).__name__}: {str(e)[:300]}"}


def _post_review_for(payload: dict, review: dict, run_id: str, deps: Deps) -> dict:
    m = PR_URL.match(str(payload.get("pr_url") or ""))
    if not m:
        return {"posted": False, "reason": "no GitHub pull request for this branch"}
    return post_pr_review(m.group(1), m.group(2), int(m.group(3)), review, run_id=run_id,
                          gh_api=deps.gh_api, public_url=deps.public_url)


# ── git plumbing for the babysitter ──────────────────────────────────────────

def _git(*args: str, cwd: Path | None = None, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          errors="replace", timeout=timeout,
                          env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})


def _sha(ref: str, cwd: Path) -> str | None:
    r = _git("rev-parse", "--verify", "-q", ref, cwd=cwd)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def _is_ancestor(ancestor: str, descendant: str, cwd: Path) -> bool:
    return _git("merge-base", "--is-ancestor", ancestor, descendant, cwd=cwd).returncode == 0


def force_rmtree(path: Path) -> None:
    """rmtree that survives git's read-only objects.

    git writes loose objects and packs mode 0444, and on Windows a read-only file cannot
    be unlinked — so `shutil.rmtree(..., ignore_errors=True)` leaves the tree behind and
    the next `git clone` into that path dies with "already exists and is not an empty
    directory". Found live on 2026-09-08: the review execution is the first stage that
    reuses a run's checkout right after the coding stage committed into it.
    """
    def _chmod_retry(fn, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            fn(p)
        except OSError:
            pass
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_chmod_retry)
    else:
        shutil.rmtree(path, onerror=_chmod_retry)


def _scrub(text: str, authed: str, plain: str) -> str:
    if authed != plain and "@" in authed:
        cred = authed.split("//", 1)[1].split("@", 1)[0]
        text = text.replace(cred, "***")
    return text


def github_repo(url: str) -> tuple[str, str] | None:
    m = GITHUB_REPO.match((url or "").strip())
    return (m.group(1), m.group(2)) if m else None


def trial_merge(mirror: Path, base: str, branch: str, run_id: str,
                identity: tuple[str, str]) -> dict:
    """Clone the mirror to a temp dir, merge origin/<base> into <branch> with the bot
    identity. Returns {clean, clone, merge_sha | files}. The caller removes `clone`."""
    clone = Path(tempfile.mkdtemp(prefix=f"lantern-babysit-{run_id[:24]}-"))
    r = _git("clone", "--quiet", "--no-hardlinks", "--branch", branch, str(mirror), str(clone))
    if r.returncode != 0:
        force_rmtree(clone)
        raise RuntimeError(f"could not clone the mirror on {branch}: {r.stderr.strip()[-300:]}")
    _git("config", "user.name", identity[0], cwd=clone)
    _git("config", "user.email", identity[1], cwd=clone)
    _git("config", "commit.gpgsign", "false", cwd=clone)
    base_sha = _sha(f"refs/remotes/origin/{base}", clone)
    if not base_sha:
        force_rmtree(clone)
        raise RuntimeError(f"base branch {base} is not in the mirror")
    msg = (f"{run_id}: merge {base} ({base_sha[:12]}) into {branch}\n\n"
           "Kept mergeable by the Lantern merge babysitter (D19) after a human approved "
           f"code_complete; the product's quality gate re-ran on the result.\n\n{BOT_TRAILER}")
    m = _git("merge", "--no-ff", "--no-edit", "-m", msg, f"origin/{base}", cwd=clone)
    if m.returncode != 0:
        files = [ln.strip() for ln in _git("diff", "--name-only", "--diff-filter=U", cwd=clone)
                 .stdout.splitlines() if ln.strip()]
        _git("merge", "--abort", cwd=clone)
        return {"clean": False, "clone": clone, "files": files, "base_sha": base_sha,
                "stderr": (m.stdout + m.stderr).strip()[-600:]}
    return {"clean": True, "clone": clone, "merge_sha": _sha("HEAD", clone), "base_sha": base_sha}


def push_branch(clone: Path, mirror: Path, repo: str, branch: str, authed: str) -> dict:
    """Land the clone's branch in the mirror, then in the origin when it is https.
    A local-path product repo IS the mirror; git refuses the push when that repo has the
    branch checked out (the D15 caveat) — reported, never forced."""
    r = _git("push", "--quiet", str(mirror), f"HEAD:refs/heads/{branch}", cwd=clone)
    if r.returncode != 0:
        return {"pushed": False, "where": "mirror", "error": r.stderr.strip()[-400:]}
    if repo.startswith("https://"):
        r = _git("push", "--quiet", authed, f"refs/heads/{branch}:refs/heads/{branch}", cwd=mirror)
        if r.returncode != 0:
            return {"pushed": False, "where": "origin",
                    "error": _scrub(r.stderr.strip()[-400:], authed, repo)}
    return {"pushed": True}


def conflict_report(run_id: str, base: str, branch: str, base_sha: str, files: list[str],
                    stderr: str = "") -> Path:
    p = factory.run_dir(run_id) / CODING_DIR / CONFLICT_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"# Merge conflict — {run_id}\n\n"
        f"- **Branch:** `{branch}`\n- **Base:** `{base}` at `{base_sha}`\n- **When:** {_now()}\n"
        f"- **Found by:** the merge babysitter (D19) — a trial merge of the base into the branch\n\n"
        "## Conflicting files\n\n" + "".join(f"- `{f}`\n" for f in files)
        + ("\n## git said\n\n```\n" + stderr + "\n```\n" if stderr else "")
        + "\n## What happens now\n\n"
        "The babysitter stopped: it never resolves conflicts and never merges into the base. "
        f"A human resolves it on the branch (`git fetch origin && git checkout {branch} && "
        f"git merge origin/{base}`, resolve, commit, push). The babysitter re-checks the branch "
        f"when `{base}` moves again, or now with `pipeline.py babysit {run_id} --force`.\n",
        encoding="utf-8")
    return p


# ── the regate: the product's quality commands, as code, on the merged branch ─

def regate_local(root: Path, run_id: str, execution_key: str = "") -> dict:
    """factory.run_quality_gate minus the write-scope check (a merge commit legitimately
    touches whatever the base touched) and minus the gate.json side effect (that file
    belongs to the coding execution). Same record shape, so render_gate_md and
    gate_failure_brief apply."""
    cfg = factory.quality_config(root)
    results = [{"name": name, "command": cmd, **factory.run_command(cmd, root, cfg["timeout_s"])}
               for name, cmd in cfg["commands"]]
    gate = {"kind": "quality_gate", "run_id": run_id, "stage": REGATE_STAGE,
            "execution_key": execution_key, "round": 0, "source": cfg.get("source"),
            "configured": [n for n, _ in cfg["commands"]],
            "passed": all(r["passed"] for r in results), "results": results, "ran_at": _now()}
    if cfg.get("error"):
        gate["passed"] = False
        gate["results"].append({"name": "config", "command": "lantern.toml", "exit": 1,
                                "passed": False, "seconds": 0.0, "output_tail": cfg["error"]})
    return gate


def regate_docker_cmd(deps: Deps, mirror: Path, sha: str, run_id: str, execution_key: str) -> list[str]:
    """The sandbox invocation for a regate: the image, the mirror mounted read-only, this
    repo mounted read-only, and bash instead of the agent entrypoint. The container clones
    the merged branch and runs this module's `regate-local`, which prints the record."""
    name = f"lantern-{run_id}-regate-{execution_key.rsplit(':', 1)[-1]}".replace(".", "-")
    script = ("git config --global --add safe.directory /product-src.git && "
              "git config --global --add safe.directory /product-src.git/.git && "
              "git clone --quiet --no-hardlinks /product-src.git /work/product && "
              f"git -C /work/product checkout --quiet {sha} && cd /work/product && "
              "/opt/lantern/venv/bin/python /repo-src/tools/azure-runner/review.py regate-local "
              f"{run_id} --execution-key {execution_key}")
    return ["docker", "run", "--rm", "--name", name, "--user", "1000:1000",
            "--cpus", deps.sandbox_cpus, "--memory", deps.sandbox_memory,
            "-e", "HOME=/work", "-e", "CI=1",
            "-v", f"{mirror}:/product-src.git:ro", "-v", f"{deps.repo_root}:/repo-src:ro",
            "--entrypoint", "bash", deps.sandbox_image, "-c", script]


def parse_regate_line(output: str) -> dict | None:
    for line in reversed(output.splitlines()):
        if line.startswith(REGATE_MARKER):
            try:
                data = json.loads(line[len(REGATE_MARKER):])
                return data if isinstance(data, dict) and "passed" in data else None
            except ValueError:
                return None
    return None


def run_regate(deps: Deps, clone: Path, mirror: Path, sha: str, run_id: str,
               execution_key: str) -> dict:
    if deps.executor != "docker":
        return regate_local(clone, run_id, execution_key)
    cfg = factory.quality_config(clone)
    budget = cfg["timeout_s"] * max(1, len(cfg["commands"])) + 300
    cmd = regate_docker_cmd(deps, mirror, sha, run_id, execution_key)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=budget)
        out = (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired as e:
        subprocess.run(["docker", "kill", cmd[4]], capture_output=True)
        out = f"killed after {budget}s\n" + (e.stdout.decode(errors='replace') if isinstance(e.stdout, bytes) else (e.stdout or ""))
    except OSError as e:
        out = f"could not start docker: {e}"
    gate = parse_regate_line(out)
    if gate is None:
        return {"kind": "quality_gate", "run_id": run_id, "stage": REGATE_STAGE,
                "execution_key": execution_key, "round": 0, "source": "sandbox",
                "configured": [n for n, _ in cfg["commands"]], "passed": False, "ran_at": _now(),
                "results": [{"name": "sandbox", "command": " ".join(cmd[:3]) + " …", "exit": 1,
                             "passed": False, "seconds": 0.0, "output_tail": out[-3000:]}]}
    return gate


def _write_regate(run_id: str, attempt: int, gate: dict) -> tuple[Path, Path]:
    d = babysit_dir(run_id)
    jp, mp = d / f"regate-{attempt}.json", d / f"regate-{attempt}.md"
    _write_json(jp, gate)
    mp.write_text(factory.render_gate_md(gate), encoding="utf-8")
    return jp, mp


# ── merged? ──────────────────────────────────────────────────────────────────

def merged_status(deps: Deps, repo: str, mirror: Path, base: str, branch: str,
                  handoff: dict) -> dict:
    """{'merged': bool, 'closed': bool, 'via': 'github'|'git', ...}. GitHub is asked when
    the run has a PR number and the host has a token (squash merges leave no ancestry);
    otherwise ancestry in the mirror decides."""
    gh = github_repo(repo)
    pr = handoff.get("pr_number")
    if gh and pr and deps.gh_api is not None:
        try:
            status, body = deps.gh_api("GET", f"/repos/{gh[0]}/{gh[1]}/pulls/{int(pr)}")
        except Exception as e:  # noqa: BLE001
            status, body = 0, {"message": str(e)[:200]}
        if status == 200 and isinstance(body, dict):
            return {"merged": bool(body.get("merged")), "closed": body.get("state") == "closed",
                    "via": "github", "pr_number": int(pr),
                    "merge_commit_sha": body.get("merge_commit_sha")}
    head = _sha(f"refs/heads/{branch}", mirror)
    if head is None:
        return {"merged": False, "closed": False, "via": "git", "missing_branch": True}
    return {"merged": _is_ancestor(head, f"refs/heads/{base}", mirror), "closed": False, "via": "git"}


# ── babysit one run ──────────────────────────────────────────────────────────

async def babysit_run(conn, run_id: str, runner: str = "ec2", deps: Deps | None = None,
                      force: bool = False) -> dict:
    """One babysitting pass over one run. Returns {'outcome': …} — one of
    no_product | no_branch | merged | pr_closed | up_to_date | waiting_for_base | conflict |
    push_refused | updated | fixed | failed."""
    deps = deps or default_deps()
    repo, base, branch = await deps.product(conn, run_id)
    if not repo or not branch:
        return {"outcome": "no_product"}
    mirror = await asyncio.to_thread(deps.mirror, repo)
    handoff = load_handoff(run_id)
    ms = await asyncio.to_thread(merged_status, deps, repo, mirror, base, branch, handoff)
    if ms.get("missing_branch"):
        return {"outcome": "no_branch", "branch": branch}
    if ms["merged"]:
        await deps.event(conn, run_id, "orchestrator", "branch_merged",
                         {"branch": branch, "base": base, **{k: v for k, v in ms.items() if k != "merged"}})
        write_babysit_state(run_id, outcome="merged", via=ms["via"], branch=branch, base=base)
        print(f"[{run_id}] {branch} is merged into {base} ({ms['via']}) — babysitting ends")
        return {"outcome": "merged", **ms}
    if ms.get("closed"):
        await deps.event(conn, run_id, "orchestrator", "pr_closed", {"branch": branch, **ms})
        write_babysit_state(run_id, outcome="pr_closed", branch=branch, base=base)
        return {"outcome": "pr_closed", **ms}
    base_sha = _sha(f"refs/heads/{base}", mirror)
    head = _sha(f"refs/heads/{branch}", mirror)
    if not base_sha:
        return {"outcome": "no_branch", "branch": base}
    if _is_ancestor(base_sha, head, mirror):
        write_babysit_state(run_id, outcome="up_to_date", base_sha=base_sha, head_sha=head,
                            branch=branch, base=base)
        return {"outcome": "up_to_date", "base_sha": base_sha, "head_sha": head}
    prior = read_babysit_state(run_id)
    if (not force and prior.get("base_sha") == base_sha
            and prior.get("outcome") in ("conflict", "push_refused", "failed")):
        return {"outcome": "waiting_for_base", "since": prior.get("outcome"), "base_sha": base_sha}

    tm = await asyncio.to_thread(trial_merge, mirror, base, branch, run_id, deps.git_identity)
    clone: Path = tm["clone"]
    try:
        if not tm["clean"]:
            path = conflict_report(run_id, base, branch, base_sha, tm["files"], tm.get("stderr", ""))
            data = {"branch": branch, "base": base, "base_sha": base_sha, "files": tm["files"],
                    "report": f"workflow/runs/{run_id}/{CODING_DIR}/{CONFLICT_FILE}"}
            await deps.event(conn, run_id, "orchestrator", "merge_conflict", data)
            write_babysit_state(run_id, outcome="conflict", **data)
            deps.alarm(f":warning: Lantern merge babysitter — {run_id}: `{branch}` conflicts with "
                       f"`{base}` ({len(tm['files'])} file(s): {', '.join(tm['files'][:6])}"
                       f"{' …' if len(tm['files']) > 6 else ''}). See {data['report']}. A human "
                       f"resolves it on the branch; the babysitter resumes when {base} moves.")
            return {"outcome": "conflict", **data}
        merge_sha = tm["merge_sha"]
        pushed = await asyncio.to_thread(push_branch, clone, mirror, repo, branch, deps.authed(repo))
        if not pushed["pushed"]:
            data = {"branch": branch, "base": base, "base_sha": base_sha, "merge_sha": merge_sha, **pushed}
            await deps.event(conn, run_id, "orchestrator", "babysit_push_refused", data)
            write_babysit_state(run_id, outcome="push_refused", **data)
            deps.alarm(f":warning: Lantern merge babysitter — {run_id}: merged `{base}` into "
                       f"`{branch}` but could not push it ({pushed['where']}): {pushed['error'][:200]}")
            return {"outcome": "push_refused", **data}
        # The regate — a stage execution row without a model: code ran, not an agent.
        attempt = await conn.fetchval(
            "SELECT coalesce(max(attempt), 0) + 1 FROM stage_executions WHERE run_id = $1 AND stage = $2",
            run_id, REGATE_STAGE)
        attempt = int(attempt or 1)
        execution_key = f"{run_id}:{REGATE_STAGE}:{attempt}"
        exec_id = await conn.fetchval(
            """INSERT INTO stage_executions (run_id, stage, runner, attempt, status, idempotency_key, heartbeat_at)
               VALUES ($1, $2, $3, $4, 'running', $5, now()) RETURNING id""",
            run_id, REGATE_STAGE, runner, attempt, execution_key)
        await deps.event(conn, run_id, "orchestrator", "stage_started",
                         {"stage": REGATE_STAGE, "attempt": attempt, "runner": runner,
                          "merge_sha": merge_sha, "base_sha": base_sha})
        gate = await asyncio.to_thread(run_regate, deps, clone, mirror, merge_sha, run_id, execution_key)
        jp, mp = _write_regate(run_id, attempt, gate)
        await conn.execute(
            "UPDATE stage_executions SET status = $1, output = $2, finished_at = now() WHERE id = $3",
            "succeeded" if gate["passed"] else "failed",
            json.dumps({"gate": f"workflow/runs/{run_id}/{CODING_DIR}/{BABYSIT_DIR}/{mp.name}",
                        "passed": gate["passed"], "configured": gate.get("configured", []),
                        "merge_sha": merge_sha, "base_sha": base_sha}), exec_id)
        await deps.event(conn, run_id, "orchestrator",
                         "stage_succeeded" if gate["passed"] else "regate_red",
                         {"stage": REGATE_STAGE, "merge_sha": merge_sha, "base_sha": base_sha,
                          "failed": [r["name"] for r in gate.get("results", []) if not r.get("passed")]})
        if gate["passed"]:
            data = {"branch": branch, "base": base, "base_sha": base_sha, "merge_sha": merge_sha,
                    "gate": "green", "configured": gate.get("configured", [])}
            await deps.event(conn, run_id, "orchestrator", "branch_updated", data)
            write_babysit_state(run_id, outcome="updated", **data)
            await asyncio.to_thread(_comment_updated, deps, repo, handoff, run_id, data)
            print(f"[{run_id}] {branch} updated with {base} ({base_sha[:12]}) — gate green")
            return {"outcome": "updated", **data}
        # Red: one fix execution, then publish through the normal handoff path.
        write_state(run_id, phase="fix", round=read_state(run_id).get("round", 0),
                    max_rounds=review_rounds(), history=read_state(run_id).get("history", []),
                    fix={"source": "regate", "base": base, "base_sha": base_sha,
                         "merge_sha": merge_sha, "gate": gate})
        try:
            await deps.execute(conn, run_id, FIX_STAGE, runner)
            fresh = await deps.publish(conn, run_id)
        except Exception as e:  # noqa: BLE001
            await _mark_failed(conn, run_id, FIX_STAGE, e)
            data = {"branch": branch, "base": base, "base_sha": base_sha, "merge_sha": merge_sha,
                    "error": str(e)[:600], "gate": f"workflow/runs/{run_id}/{CODING_DIR}/{BABYSIT_DIR}/{mp.name}"}
            await deps.event(conn, run_id, "orchestrator", "babysit_failed", data)
            write_babysit_state(run_id, outcome="failed", **data)
            deps.alarm(f":rotating_light: Lantern merge babysitter — {run_id}: `{base}` merged into "
                       f"`{branch}` (pushed), the quality gate is RED and the fix execution failed: "
                       f"{str(e)[:200]}. See {data['gate']}. The branch needs a human.")
            return {"outcome": "failed", **data}
        data = {"branch": branch, "base": base, "base_sha": base_sha, "merge_sha": merge_sha,
                "gate": "fixed", "head_sha": fresh.get("head_sha"), "commits": fresh.get("commit_count")}
        await deps.event(conn, run_id, "orchestrator", "branch_updated", data)
        write_babysit_state(run_id, outcome="fixed", **data)
        await asyncio.to_thread(_comment_updated, deps, repo, handoff, run_id, data)
        print(f"[{run_id}] {branch} updated with {base} and fixed — head {str(fresh.get('head_sha', ''))[:12]}")
        return {"outcome": "fixed", **data}
    finally:
        force_rmtree(clone)


def _comment_updated(deps: Deps, repo: str, handoff: dict, run_id: str, data: dict) -> None:
    gh = github_repo(repo)
    pr = handoff.get("pr_number")
    if not (gh and pr and deps.gh_api is not None):
        return
    try:
        deps.gh_api("POST", f"/repos/{gh[0]}/{gh[1]}/issues/{int(pr)}/comments",
                    {"body": f"Merge babysitter: merged `{data['base']}` (`{data['base_sha'][:12]}`) "
                             f"into this branch — quality gate {data['gate']}"
                             + (f" ({', '.join(data['configured'])})" if data.get("configured") else "")
                             + ". Kept mergeable for a human to merge (Lantern D19)."})
    except Exception as e:  # noqa: BLE001
        print(f"[{run_id}] PR comment failed: {e}", file=sys.stderr)


# ── the daemon tick and the CLI ──────────────────────────────────────────────

ELIGIBLE_SQL = """
SELECT r.id FROM runs r
WHERE r.coding_mode = 'auto' AND r.product_repo IS NOT NULL
  AND r.status IN ('running', 'waiting_gate', 'done')
  AND r.current_stage >= '04'
  AND EXISTS (SELECT 1 FROM approvals a WHERE a.run_id = r.id
              AND a.gate = 'code_complete' AND a.status = 'approved')
  AND NOT EXISTS (SELECT 1 FROM events e WHERE e.run_id = r.id
                  AND e.type IN ('branch_merged', 'pr_closed'))
ORDER BY r.updated_at
"""
_last_tick = 0.0


def babysit_due(now: float | None = None) -> bool:
    """True once per LANTERN_BABYSIT_MINUTES (and at daemon start)."""
    global _last_tick
    t = time.monotonic() if now is None else now
    if _last_tick and t - _last_tick < babysit_minutes() * 60:
        return False
    _last_tick = t
    return True


async def babysit_tick(conn, runner: str = "ec2", deps: Deps | None = None) -> list[dict]:
    """Every eligible run once. A failing run never stops the others."""
    deps = deps or default_deps()
    out = []
    for row in await conn.fetch(ELIGIBLE_SQL):
        run_id = row["id"]
        try:
            res = await babysit_run(conn, run_id, runner, deps)
        except Exception as e:  # noqa: BLE001
            res = {"outcome": "error", "error": str(e)[:600]}
            try:
                await deps.event(conn, run_id, "orchestrator", "babysit_failed", res)
            except Exception:  # noqa: BLE001
                pass
            print(f"[{run_id}] babysit error: {e}", file=sys.stderr)
        out.append({"run_id": run_id, **res})
    return out


async def babysit_slot(connect, runner: str) -> None:
    """One daemon slot: own connection, own errors."""
    conn = await connect()
    try:
        await babysit_tick(conn, runner)
    except Exception as e:  # noqa: BLE001
        print(f"babysit tick failed: {e}", file=sys.stderr)
    finally:
        await conn.close()


async def cmd_babysit(run_id: str | None, force: bool = False) -> None:
    import pipeline as p  # noqa: PLC0415
    conn = await p.connect()
    try:
        runner = os.environ.get("LANTERN_RUNNER", "ec2")
        if run_id:
            if not await conn.fetchval("SELECT 1 FROM runs WHERE id = $1", run_id):
                sys.exit(f"unknown run: {run_id}")
            results = [{"run_id": run_id, **await babysit_run(conn, run_id, runner, force=force)}]
        else:
            results = await babysit_tick(conn, runner)
            if not results:
                print("no run is past an approved code_complete with an unmerged branch")
        for r in results:
            extra = {k: v for k, v in r.items() if k not in ("run_id", "outcome")}
            print(f"[{r['run_id']}] {r['outcome']}"
                  + (f" — {json.dumps(extra, default=str)[:400]}" if extra else ""))
        await p.render_runboard(conn)
    finally:
        await conn.close()


def _main() -> None:
    """`review.py regate-local <run-id> [--execution-key K]` — run the quality commands in
    the CURRENT directory and print the record; the sandbox regate calls this."""
    import argparse  # noqa: PLC0415
    ap = argparse.ArgumentParser(prog="review")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("regate-local")
    p.add_argument("run_id")
    p.add_argument("--execution-key", default="")
    a = ap.parse_args()
    if a.cmd == "regate-local":
        gate = regate_local(Path.cwd(), a.run_id, a.execution_key)
        print(REGATE_MARKER + json.dumps(gate))
        sys.exit(0 if gate["passed"] else 1)


if __name__ == "__main__":
    _main()
