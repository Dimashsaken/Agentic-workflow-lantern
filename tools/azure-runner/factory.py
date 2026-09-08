"""Software-factory mechanics (D17): typed envelopes, write scope, quality gate, fix loop.

Pure functions over the run folder and a product checkout — no database, no network, no
Agents SDK import — so the container path (orchestrator.main), the in-process path
(pipeline.run_agent_stage) and the tests share ONE implementation. The rule every
function here serves: agents propose, code disposes (docs/plans/software-factory-
alignment.md §1.3). An agent's claim is never evidence; a file the harness can check is.

Envelopes — the typed handoff beside each stage's markdown report:
    00-story.scout          research.json   what the codebase already has (paths must exist)
    00-story.write          story.json      numbered acceptance criteria — THE contract
    02-pre-coding           plan.json       tasks → criteria, the builder's write scope
    05-post-coding.validate validation.json every criterion: covered | missing | skipped |
                                            off-spec | insecure, with evidence

Quality gate — after the coding agent's turn the product's own test/lint/typecheck
commands (lantern.toml [quality]) run as CODE; only failures go back to the agent, at
most LANTERN_FIX_ROUNDS times, then the stage fails honestly. The gate also refuses
commits outside the plan's write scope (Ray Fu's folder-scoped engineers).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

AC_ID = re.compile(r"^AC-\d+$")
VALIDATION_STATUSES = ("covered", "missing", "skipped", "off-spec", "insecure")
RISK_LEVELS = ("low", "medium", "high")
TASK_SIZES = ("XS", "S", "M", "L", "XL")
QUALITY_KEYS = ("test", "lint", "typecheck", "build")     # run order
QUALITY_TIMEOUT_DEFAULT = 900
QUALITY_TAIL = 3000
FIX_ROUNDS_DEFAULT = 3
GATE_FILE = "gate.json"

# stage key -> (typed envelope, human-readable twin). Both are required: the JSON is
# what code and downstream agents read, the markdown is what a human approves.
ENVELOPES = {
    "00-story.scout": ("research", "research.json", "research.md"),
    "00-story.write": ("story", "story.json", "story.md"),
    "02-pre-coding": ("plan", "plan.json", "task-plan.md"),
    "05-post-coding.validate": ("validation", "validation.json", "validation.md"),
    "03-coding.review": ("review", "review/review.json", "review/round-<n>.md"),  # D19: <n> = the round
}


def stage_dir(stage: str) -> str:
    return stage.split(".", 1)[0]


def run_dir(run_id: str) -> Path:
    return REPO / "workflow" / "runs" / run_id


def _load_json(path: Path) -> tuple[dict | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        return None, f"cannot read {path.name}: {e}"
    except ValueError as e:
        return None, f"{path.name} is not valid JSON: {e}"
    if not isinstance(data, dict):
        return None, f"{path.name} must be a JSON object"
    return data, None


def _is_list_of_dicts(v) -> bool:
    return isinstance(v, list) and all(isinstance(x, dict) for x in v)


def _nonempty_str(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _str_list(v) -> bool:
    return isinstance(v, list) and all(_nonempty_str(x) for x in v)


# ── envelopes ────────────────────────────────────────────────────────────────

def story_criteria(run_id: str) -> list[str] | None:
    """Acceptance-criterion ids from story.json, or None when the run has no story
    (runs imported at a later stage). Invalid JSON also reads as None — the story
    stage's own postcondition reports the defect where it was made."""
    data, err = _load_json(run_dir(run_id) / "00-story" / "story.json") \
        if (run_dir(run_id) / "00-story" / "story.json").is_file() else (None, None)
    if not data:
        return None
    ids = [c.get("id") for c in data.get("acceptance_criteria", []) if isinstance(c, dict)]
    return [i for i in ids if isinstance(i, str)]


def check_envelope(run_id: str, stage: str, product_root: Path | None = None) -> list[str]:
    """Presence AND validity of a stage's typed envelope (plus its markdown twin).

    Returns problems (empty = valid). Cross-stage checks (plan ↔ story, validation ↔
    story) run only when the story exists, so runs imported after stage 0 still work;
    path-existence checks run only when a product checkout is given.
    """
    spec = ENVELOPES.get(stage)
    if not spec:
        return []
    kind, json_name, md_name = spec
    sdir = stage_dir(stage)
    d = run_dir(run_id) / sdir
    problems: list[str] = []
    if "<n>" in md_name:        # D19: a per-round twin, named by the envelope's round
        md_name = md_name.replace("<n>", _peek_round(d / json_name))
    md = d / md_name
    if not md.is_file() or md.stat().st_size == 0:
        problems.append(f"{sdir}/{md_name} missing or empty — the human-readable twin of "
                        f"{json_name} (what the gate approver reads)")
    jp = d / json_name
    if not jp.is_file():
        problems.append(f"{sdir}/{json_name} missing — the typed envelope downstream stages "
                        "and the gates read; write it exactly as your skills describe")
        return problems
    data, err = _load_json(jp)
    if err:
        return problems + [f"{sdir}/{err}"]
    if data.get("kind") != kind:
        problems.append(f"{sdir}/{json_name}: kind must be '{kind}' (got {data.get('kind')!r})")
    if data.get("run_id") != run_id:
        problems.append(f"{sdir}/{json_name}: run_id must be '{run_id}'")
    checker = {"research": _check_research, "story": _check_story,
               "plan": _check_plan, "validation": _check_validation,
               "review": _check_review}[kind]   # D19
    problems.extend(f"{sdir}/{json_name}: {p}" for p in checker(data, run_id, product_root))
    return problems


def _paths_exist(paths: list[str], product_root: Path | None) -> list[str]:
    """Paths an agent cites that do not exist in the checkout — fabrications."""
    if product_root is None or not (product_root / ".git").exists():
        return []
    missing = []
    for p in paths:
        rel = str(p).replace("\\", "/").strip().rstrip("/")
        if rel.startswith("product/"):
            rel = rel[len("product/"):]
        if not rel or not (product_root / rel).exists():
            missing.append(str(p))
    return missing


def _check_research(data: dict, run_id: str, product_root: Path | None) -> list[str]:
    p: list[str] = []
    if not _is_list_of_dicts(data.get("patterns")):
        p.append("patterns must be a list of {path, note}")
    else:
        for i, x in enumerate(data["patterns"]):
            if not _nonempty_str(x.get("path")) or not _nonempty_str(x.get("note")):
                p.append(f"patterns[{i}] needs a non-empty path and note")
    if not _is_list_of_dicts(data.get("risks")):
        p.append("risks must be a list of {risk, severity} (an empty list is allowed)")
    else:
        for i, x in enumerate(data["risks"]):
            if not _nonempty_str(x.get("risk")) or x.get("severity") not in RISK_LEVELS:
                p.append(f"risks[{i}] needs a risk and a severity in {'/'.join(RISK_LEVELS)}")
    if not _str_list(data.get("likely_files")) or not data.get("likely_files"):
        p.append("likely_files must list at least one path the feature will touch")
    sim = data.get("similar_features", [])
    if not _is_list_of_dicts(sim):
        p.append("similar_features must be a list of {name, paths}")
    cited = ([x.get("path") for x in data.get("patterns", []) if isinstance(x, dict)]
             + list(data.get("likely_files") or [])
             + [q for x in sim if isinstance(x, dict) for q in (x.get("paths") or [])])
    missing = _paths_exist([c for c in cited if isinstance(c, str)], product_root)
    if missing:
        p.append("paths that do not exist in the product checkout (a path you did not open "
                 f"is a fabrication): {', '.join(missing[:10])}")
    return p


def _check_story(data: dict, run_id: str, product_root: Path | None) -> list[str]:
    p: list[str] = []
    if not _nonempty_str(data.get("title")):
        p.append("title is required")
    if not _nonempty_str(data.get("user_story")):
        p.append("user_story is required (As a … I want … so that …)")
    acs = data.get("acceptance_criteria")
    if not _is_list_of_dicts(acs) or not acs:
        return p + ["acceptance_criteria must be a non-empty list of {id, text, edge_cases}"]
    seen: set[str] = set()
    for i, c in enumerate(acs):
        cid = c.get("id")
        if not isinstance(cid, str) or not AC_ID.match(cid):
            p.append(f"acceptance_criteria[{i}].id must look like AC-1, AC-2, …")
            continue
        if cid in seen:
            p.append(f"duplicate acceptance criterion id {cid}")
        seen.add(cid)
        if not _nonempty_str(c.get("text")):
            p.append(f"{cid}: text is required — one observable, testable outcome")
        if not _str_list(c.get("edge_cases", [])):
            p.append(f"{cid}: edge_cases must be a list of strings (empty is allowed)")
    if not _str_list(data.get("non_goals", [])):
        p.append("non_goals must be a list of strings")
    return p


def _check_plan(data: dict, run_id: str, product_root: Path | None) -> list[str]:
    p: list[str] = []
    tasks = data.get("tasks")
    if not _is_list_of_dicts(tasks) or not tasks:
        p.append("tasks must be a non-empty list of {id, title, size, hitl, criteria}")
        tasks = []
    referenced: set[str] = set()
    for i, t in enumerate(tasks):
        if not _nonempty_str(t.get("title")):
            p.append(f"tasks[{i}] needs a title")
        if t.get("size") is not None and t.get("size") not in TASK_SIZES:
            p.append(f"tasks[{i}].size must be one of {'/'.join(TASK_SIZES)}")
        if not isinstance(t.get("hitl", False), bool):
            p.append(f"tasks[{i}].hitl must be true/false")
        crit = t.get("criteria", [])
        if not _str_list(crit) and crit != []:
            p.append(f"tasks[{i}].criteria must be a list of acceptance-criterion ids")
        else:
            referenced.update(crit)
    scope = data.get("write_scope")
    if not _str_list(scope) or not scope:
        p.append("write_scope must list at least one path glob the builder may change "
                 "(e.g. \"src/api/**\", \"tests/**\") — it is enforced on every commit")
    for key in ("schema_changes", "hitl_required"):
        if not isinstance(data.get(key), bool):
            p.append(f"{key} must be true or false")
    deferred = data.get("deferred_criteria", [])
    if not _is_list_of_dicts(deferred):
        p.append("deferred_criteria must be a list of {id, reason}")
        deferred = []
    story_ids = story_criteria(run_id)
    if story_ids is not None:
        unknown = sorted(referenced - set(story_ids))
        if unknown:
            p.append(f"tasks reference criteria the story does not define: {', '.join(unknown)}")
        deferred_ids = {x.get("id") for x in deferred if _nonempty_str(x.get("reason"))}
        uncovered = [c for c in story_ids if c not in referenced and c not in deferred_ids]
        if uncovered:
            p.append("acceptance criteria with no task and no deferral reason: "
                     f"{', '.join(uncovered)} — every criterion is either planned or "
                     "explicitly deferred (deferred_criteria: [{id, reason}])")
    return p


def _check_validation(data: dict, run_id: str, product_root: Path | None) -> list[str]:
    p: list[str] = []
    crit = data.get("criteria")
    if not _is_list_of_dicts(crit) or not crit:
        return p + ["criteria must be a non-empty list of {id, status, evidence}"]
    seen: set[str] = set()
    all_covered = True
    for i, c in enumerate(crit):
        cid = c.get("id")
        if not isinstance(cid, str) or not AC_ID.match(cid):
            p.append(f"criteria[{i}].id must look like AC-1")
            continue
        if cid in seen:
            p.append(f"duplicate criterion {cid} — each acceptance criterion appears exactly once")
        seen.add(cid)
        if c.get("status") not in VALIDATION_STATUSES:
            p.append(f"{cid}: status must be one of {'/'.join(VALIDATION_STATUSES)}")
        elif c["status"] != "covered":
            all_covered = False
        if not _nonempty_str(c.get("evidence")):
            p.append(f"{cid}: evidence is required — the file, test, video timestamp or "
                     "report line that proves the status (never 'looks fine')")
    fix_now = data.get("fix_now", [])
    if not _is_list_of_dicts(fix_now):
        p.append("fix_now must be a list of {id, title, criterion}")
        fix_now = []
    story_ids = story_criteria(run_id)
    if story_ids is not None and set(story_ids) != seen:
        missing = sorted(set(story_ids) - seen)
        extra = sorted(seen - set(story_ids))
        if missing:
            p.append(f"criteria not validated: {', '.join(missing)} — every story criterion "
                     "gets a verdict, including the ones the plan deferred (status: skipped)")
        if extra:
            p.append(f"criteria the story does not define: {', '.join(extra)}")
    expected = "pass" if (all_covered and not fix_now) else "fail"
    if data.get("verdict") not in ("pass", "fail"):
        p.append("verdict must be 'pass' or 'fail'")
    elif data["verdict"] != expected:
        p.append(f"verdict says '{data['verdict']}' but the criteria say '{expected}' — the "
                 "verdict is computed from the statuses and fix_now, not chosen")
    if expected == "fail":
        # A valid envelope with a FAIL verdict is the validator doing its job — but the
        # run cannot advance on it. The stage fails honestly; the fix happens in stage 3.
        bad = [f"{c.get('id')}={c.get('status')}" for c in crit
               if isinstance(c, dict) and c.get("status") != "covered"]
        p.append("validation verdict FAIL — " + ", ".join(bad[:12])
                 + (f"; fix-now: {len(fix_now)}" if fix_now else "")
                 + f" — fix on the branch, then `pipeline.py rework {run_id} --to 03-coding`"
                 " (auto mode) or `retry` once the developer has pushed the fix")
    return p


# ── review envelope (D19) ────────────────────────────────────────────────────
# 03-coding/review/review.json — the review bot's verdict on the published branch,
# one file per round beside it (round-<n>.md). Presence AND validity: the verdict is
# COMPUTED from the findings (approve ⇔ no blocker/major), must_fix names real findings
# and every blocker/major, so a fix execution that works the must_fix list can actually
# turn the next round green instead of chasing a verdict the reviewer never explained.

REVIEW_VERDICTS = ("approve", "request_changes")
REVIEW_SEVERITIES = ("blocker", "major", "minor", "nit")
REVIEW_MUST_FIX = ("blocker", "major")


def _peek_round(path: Path) -> str:
    """The `round` of a review envelope as text, or '?' — it names the markdown twin."""
    data, _ = _load_json(path) if path.is_file() else (None, None)
    r = (data or {}).get("round")
    return str(r) if isinstance(r, int) and not isinstance(r, bool) else "?"


def _check_review(data: dict, run_id: str, product_root: Path | None) -> list[str]:
    p: list[str] = []
    rnd = data.get("round")
    if not isinstance(rnd, int) or isinstance(rnd, bool) or rnd < 1:
        p.append("round must be a positive integer (1 = the first review of this branch)")
    findings = data.get("findings")
    if not isinstance(findings, list) or not all(isinstance(x, dict) for x in findings):
        return p + ["findings must be a list of {id, severity, file, line, summary, suggestion} "
                    "(an empty list is allowed — it means approve)"]
    seen: set[str] = set()
    serious: set[str] = set()
    for i, x in enumerate(findings):
        fid = x.get("id")
        if not _nonempty_str(fid):
            p.append(f"findings[{i}].id is required (R-1, R-2, …)")
            continue
        if fid in seen:
            p.append(f"duplicate finding id {fid}")
        seen.add(fid)
        sev = x.get("severity")
        if sev not in REVIEW_SEVERITIES:
            p.append(f"{fid}: severity must be one of {'/'.join(REVIEW_SEVERITIES)}")
        elif sev in REVIEW_MUST_FIX:
            serious.add(fid)
        if not _nonempty_str(x.get("summary")):
            p.append(f"{fid}: summary is required — what is wrong, in one sentence")
        if not isinstance(x.get("file", ""), str):
            p.append(f"{fid}: file must be a path string ('' when it is not about one file)")
        line = x.get("line")
        if line is not None and (not isinstance(line, int) or isinstance(line, bool) or line < 1):
            p.append(f"{fid}: line must be a positive integer or null")
        if sev in REVIEW_MUST_FIX and not _nonempty_str(x.get("suggestion")):
            p.append(f"{fid}: a {sev} needs a suggestion — the smallest change that resolves it")
    must_fix = data.get("must_fix", [])
    if not _str_list(must_fix):
        p.append("must_fix must be a list of finding ids")
        must_fix = []
    unknown = [m for m in must_fix if m not in seen]
    if unknown:
        p.append(f"must_fix names findings that do not exist: {', '.join(unknown)}")
    missing = sorted(serious - set(must_fix))
    if missing:
        p.append(f"every blocker/major is must-fix — add {', '.join(missing)} to must_fix, or "
                 "lower the severity if it is really minor")
    expected = "approve" if not serious else "request_changes"
    verdict = data.get("verdict")
    if verdict not in REVIEW_VERDICTS:
        p.append(f"verdict must be one of {'/'.join(REVIEW_VERDICTS)}")
    elif verdict != expected:
        p.append(f"verdict says '{verdict}' but the findings say '{expected}' — approve ⇔ no "
                 "blocker/major; the verdict is computed from the severities, not chosen")
    return p


# ── write scope ──────────────────────────────────────────────────────────────

def glob_to_regex(glob: str) -> re.Pattern:
    """`src/api/**` matches everything under src/api; `*.py` one segment; `**/x.py` any depth."""
    g = glob.replace("\\", "/").strip().lstrip("./")
    out, i = [], 0
    while i < len(g):
        ch = g[i]
        if g.startswith("**/", i):
            out.append("(?:.*/)?"); i += 3
        elif g.startswith("**", i):
            out.append(".*"); i += 2
        elif ch == "*":
            out.append("[^/]*"); i += 1
        elif ch == "?":
            out.append("[^/]"); i += 1
        else:
            out.append(re.escape(ch)); i += 1
    pat = "".join(out)
    if g.endswith("/"):            # a directory glob covers its subtree
        pat += ".*"
    return re.compile("^" + pat + "$")


def path_in_scope(path: str, globs: list[str]) -> bool:
    rel = path.replace("\\", "/").lstrip("./")
    return any(glob_to_regex(g).match(rel) for g in globs)


def write_scope(run_id: str) -> list[str] | None:
    """The plan's write_scope globs, or None when the run has no plan.json (older runs)."""
    jp = run_dir(run_id) / "02-pre-coding" / "plan.json"
    if not jp.is_file():
        return None
    data, err = _load_json(jp)
    if not data:
        return None
    scope = data.get("write_scope")
    return [s for s in scope if _nonempty_str(s)] if isinstance(scope, list) and scope else None


def check_write_scope(run_id: str, files_changed: list[str]) -> list[str]:
    scope = write_scope(run_id)
    if scope is None:
        return []
    outside = [f for f in files_changed if not path_in_scope(f, scope)]
    if not outside:
        return []
    shown = ", ".join(outside[:8]) + (" …" if len(outside) > 8 else "")
    return [f"{len(outside)} changed path(s) fall outside the plan's write scope "
            f"{scope}: {shown} — the scope is a planning decision: revert the change, or "
            "widen write_scope in 02-pre-coding/plan.json with the reason in the report"]


# ── quality gate ─────────────────────────────────────────────────────────────

def quality_config(root: Path) -> dict:
    """Commands from <product>/lantern.toml [quality]; absent file = no commands."""
    cfg = {"commands": [], "timeout_s": QUALITY_TIMEOUT_DEFAULT, "source": None}
    toml = root / "lantern.toml"
    if not toml.is_file():
        return cfg
    try:
        data = tomllib.loads(toml.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        cfg["error"] = f"lantern.toml unreadable: {e}"
        return cfg
    q = data.get("quality") or {}
    cfg["source"] = "lantern.toml [quality]"
    for key in QUALITY_KEYS:
        cmd = q.get(key)
        if _nonempty_str(cmd):
            cfg["commands"].append((key, cmd.strip()))
    t = q.get("timeout_s")
    if isinstance(t, int) and t > 0:
        cfg["timeout_s"] = t
    return cfg


def _gate_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("AZURE_", "LANTERN_DATABASE", "GITHUB_", "POSTHOG_"))}
    env.setdefault("HOME", str(Path.home()))
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["CI"] = "1"
    # The interpreter running the harness — the product's own commands can use it
    # ($LANTERN_PYTHON) when the product IS Lantern; other products ignore it.
    env["LANTERN_PYTHON"] = sys.executable.replace("\\", "/")
    return env


def run_command(cmd: str, root: Path, timeout_s: int) -> dict:
    shell = ["bash", "-c", cmd] if os.name == "nt" else ["bash", "-lc", cmd]
    t0 = time.monotonic()
    try:
        r = subprocess.run(shell, cwd=root, timeout=timeout_s, env=_gate_env(),
                           capture_output=True, text=True, errors="replace",
                           stdin=subprocess.DEVNULL)
        out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr.strip() else "")
        code = r.returncode
    except subprocess.TimeoutExpired as e:
        out = f"killed after {timeout_s}s\n" + (e.stdout or "" if isinstance(e.stdout, str) else "")
        code = 124
    except OSError as e:
        out, code = f"could not start: {e}", 127
    return {"exit": code, "passed": code == 0, "seconds": round(time.monotonic() - t0, 1),
            "output_tail": out[-QUALITY_TAIL:]}


def changed_files_since(root: Path, since_sha: str | None) -> list[str]:
    """Committed (since_sha..HEAD) plus uncommitted paths — what the builder touched."""
    files: list[str] = []
    if since_sha:
        r = subprocess.run(["git", "diff", "--name-only", f"{since_sha}..HEAD"], cwd=root,
                           capture_output=True, text=True, errors="replace")
        if r.returncode == 0:
            files += [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    r = subprocess.run(["git", "status", "--porcelain"], cwd=root,
                       capture_output=True, text=True, errors="replace")
    if r.returncode == 0:
        for ln in r.stdout.splitlines():
            path = ln[3:].strip()
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            if path:
                files.append(path.strip('"'))
    return sorted(set(files))


def run_quality_gate(run_id: str, stage: str, root: Path, execution_key: str, round_no: int,
                     since_sha: str | None = None) -> dict:
    """Run the product's quality commands + the write-scope check; write gate.json/gate.md.

    Always writes the files, even with nothing configured, so a host re-check can tell
    'no commands' (passed, configured=[]) from 'the gate never ran' (no file).
    """
    cfg = quality_config(root)
    results = []
    for name, cmd in cfg["commands"]:
        res = run_command(cmd, root, cfg["timeout_s"])
        results.append({"name": name, "command": cmd, **res})
    scope = write_scope(run_id)
    if scope is not None:
        changed = changed_files_since(root, since_sha)
        problems = check_write_scope(run_id, changed)
        results.append({"name": "write-scope", "command": f"changed paths ⊆ {scope}",
                        "exit": 1 if problems else 0, "passed": not problems, "seconds": 0.0,
                        "output_tail": problems[0] if problems else f"{len(changed)} changed path(s), all in scope"})
    gate = {
        "kind": "quality_gate", "run_id": run_id, "stage": stage,
        "execution_key": execution_key, "round": round_no,
        "source": cfg.get("source"), "configured": [n for n, _ in cfg["commands"]],
        "passed": all(r["passed"] for r in results),
        "results": results,
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if cfg.get("error"):
        gate["passed"] = False
        gate["results"].append({"name": "config", "command": "lantern.toml", "exit": 1,
                                "passed": False, "seconds": 0.0, "output_tail": cfg["error"]})
    d = run_dir(run_id) / stage_dir(stage)
    d.mkdir(parents=True, exist_ok=True)
    (d / GATE_FILE).write_text(json.dumps(gate, indent=2), encoding="utf-8")
    (d / "gate.md").write_text(render_gate_md(gate), encoding="utf-8")
    return gate


def render_gate_md(gate: dict) -> str:
    lines = [f"# Quality gate — {gate['run_id']} · {gate['stage']}", "",
             f"- **Verdict:** {'GREEN' if gate['passed'] else 'RED'}",
             f"- **Round:** {gate['round']} (0 = after the first build turn)",
             f"- **Source:** {gate.get('source') or 'no lantern.toml [quality] in the product — nothing ran'}",
             f"- **Execution:** `{gate['execution_key']}` at {gate['ran_at']}", "",
             "| check | exit | seconds |", "|-------|------|---------|"]
    for r in gate["results"]:
        lines.append(f"| {r['name']} | {r['exit']} | {r['seconds']} |")
    for r in gate["results"]:
        if not r["passed"]:
            lines += ["", f"## {r['name']} — FAILED", "", f"`{r['command']}`", "",
                      "```", r["output_tail"].rstrip(), "```"]
    if not gate["configured"]:
        lines += ["", "> No quality commands are configured for this product. Add a "
                  "`[quality]` table to its `lantern.toml` (see workflow/templates/"
                  "lantern.toml) so the factory can run tests, lint and typecheck as code."]
    return "\n".join(lines) + "\n"


def gate_failure_brief(gate: dict) -> str:
    """Only the failures, deliberately — passing output never re-enters the agent's context."""
    parts = []
    for r in gate["results"]:
        if not r["passed"]:
            parts.append(f"### {r['name']} (exit {r['exit']})\n`{r['command']}`\n```\n"
                         f"{r['output_tail'].rstrip()}\n```")
    return "\n\n".join(parts)


def fix_prompt(gate: dict, round_no: int, max_rounds: int) -> str:
    return (f"# Quality gate: RED (fix round {round_no} of {max_rounds})\n"
            "The product's own quality commands ran as code after your turn. Only the "
            "failures are below; passing output is withheld on purpose. Fix them: edit, "
            "re-run the FAILING command yourself with product_shell until it is green, "
            "commit (`<run-id>: fix — <what>`), then reply. A `write-scope` failure means "
            "a change landed outside the plan's write_scope — revert it or move it. If a "
            "failure is pre-existing and unrelated to your change, say so under "
            "`## Deviations` in your report — the gate still has to be green to hand off.\n\n"
            + gate_failure_brief(gate))


def check_quality_gate(run_id: str, sdir: str, execution_key: str) -> list[str]:
    """Postcondition: THIS execution's gate.json says green. Missing = degrade (an older
    sandbox image, or a human-mode stage) with a note, never a silent pass elsewhere."""
    gp = run_dir(run_id) / sdir / GATE_FILE
    if not gp.is_file():
        print(f"[factory] {sdir}/{GATE_FILE} absent — quality gate not enforced for this "
              "execution (older sandbox image or no coding_turns)", file=sys.stderr)
        return []
    gate, err = _load_json(gp)
    if err:
        return [f"{sdir}/{err}"]
    if gate.get("execution_key") != execution_key:
        return [f"{sdir}/{GATE_FILE} belongs to execution {gate.get('execution_key')!r}, not "
                f"this one — the gate did not run for this attempt"]
    if not gate.get("passed"):
        failed = [r["name"] for r in gate.get("results", []) if not r.get("passed")]
        return [f"quality gate RED after {gate.get('round', 0)} fix round(s): "
                f"{', '.join(failed) or 'unknown'} — see {sdir}/gate.md; the branch is not "
                "handed off until the product's own checks pass"]
    return []


def coding_gate_note(run_id: str, root: Path | None) -> str:
    """What the builder will be held to — in the prompt, not discovered at handoff."""
    scope = write_scope(run_id)
    cfg = quality_config(root) if root is not None and root.exists() else {"commands": []}
    rounds = int(os.environ.get("LANTERN_FIX_ROUNDS", FIX_ROUNDS_DEFAULT))
    lines = ["\n\n## The gate your branch must pass (code, not opinion)"]
    if cfg["commands"]:
        lines.append("After your turn the harness runs, from the product root: "
                     + "; ".join(f"`{c}`" for _, c in cfg["commands"])
                     + f". Red output comes back to you (failures only) for at most {rounds} "
                     "fix rounds; still red = the stage fails and no branch is handed off. "
                     "Run these yourself before you finish.")
    else:
        lines.append("This product has no `lantern.toml [quality]` commands, so no tests run "
                     "as code after your turn — run the product's own test command through "
                     "product_shell yourself, and add a `lantern.toml` (see "
                     "workflow/templates/lantern.toml) as part of your task if the plan allows.")
    if scope:
        lines.append("Write scope from the approved plan — commits touching other paths are "
                     "refused at handoff: " + ", ".join(f"`{g}`" for g in scope) + ".")
    return "\n".join(lines)


# ── the bounded fix loop ─────────────────────────────────────────────────────

def fix_rounds() -> int:
    try:
        return max(0, int(os.environ.get("LANTERN_FIX_ROUNDS", FIX_ROUNDS_DEFAULT)))
    except ValueError:
        return FIX_ROUNDS_DEFAULT


async def coding_turns(run_turn, kickoff: str, *, run_id: str, stage: str, root: Path,
                       execution_key: str, since_sha: str | None = None,
                       max_rounds: int | None = None) -> tuple[list, dict]:
    """Build turn → gate → (failures → fix turn)*, bounded. `run_turn(text)` is the agent
    turn (Runner.run in production, a fake in tests); returns (results, final gate)."""
    rounds = fix_rounds() if max_rounds is None else max_rounds
    results = [await run_turn(kickoff)]
    round_no = 0
    while True:
        gate = run_quality_gate(run_id, stage, root, execution_key, round_no, since_sha)
        if gate["passed"] or round_no >= rounds:
            return results, gate
        round_no += 1
        results.append(await run_turn(fix_prompt(gate, round_no, rounds)))


def merge_usage(usages: list[dict]) -> dict:
    """Sum the token ledgers of several Runner.run results (the fix loop is one stage)."""
    out: dict[str, int] = {}
    for u in usages:
        for k, v in (u or {}).items():
            if isinstance(v, (int, float)):
                out[k] = out.get(k, 0) + int(v)
    return out
