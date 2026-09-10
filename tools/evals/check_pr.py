"""The eval rule, as code (D20): a change to the factory's prompts or gates ships its
eval numbers, or the lint gate is red.

    python tools/evals/check_pr.py [--base <ref>] [--root <repo>]

Watched: agents/** (every role file except the rendered memory.md), factory.py,
intake.py, the scorers, and — inside orchestrator.py — the prompt builders and the gate
functions by NAME (a diff elsewhere in that file does not trip the rule). When a diff
touches any of those, tools/evals/REPORT.md must be part of the same diff AND carry the
fingerprint of the watched files as they are now (`pipeline.py evals report` writes it),
so an edited-but-not-regenerated report cannot pass.

Base resolution, in order: --base, $LANTERN_EVALS_BASE, origin/$LANTERN_PRODUCT_BRANCH,
$LANTERN_PRODUCT_BRANCH, origin/main, main. The diff is base...HEAD plus the working
tree. No resolvable base = the rule cannot apply; exit 0 with a note (never block on
infrastructure the check-out lacks). Exit codes: 0 pass, 1 rule violated.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
import re
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path

REPORT = "tools/evals/REPORT.md"
ORCHESTRATOR = "tools/azure-runner/orchestrator.py"
WATCHED_PATHS = (
    "tools/azure-runner/factory.py",
    "tools/azure-runner/intake.py",
    "tools/azure-runner/tool_policy.py",
    "tools/azure-runner/readonly_git.py",
    "tools/azure-runner/evidence.py",
    "tools/evals/scorers.py",
    "tools/evals/integrity.py",
)
WATCHED_GLOBS = ("agents/*/*.md", "agents/*/*/*.md")
UNWATCHED_GLOBS = ("agents/*/memory.md", "agents/_template/*")
PROMPT_BUILDERS = (
    "PHASE_NOTES", "build_instructions", "build_consult_instructions", "qa_target_note",
    "paper_file_note", "product_note", "product_env_block", "product_docs_block",
    "product_task_block", "coding_work_contract", "readonly_work_contract",
)
GATE_FUNCS = (
    "check_postconditions", "check_claimed_artifacts", "check_coding_handoff",
    "check_stage_inputs", "report_blocker", "finalize_coding",
    "stage_tools", "_resolve_read", "_writable", "_product_git", "make_collect_jsx",
)
WATCHED_UNITS = PROMPT_BUILDERS + GATE_FUNCS
FINGERPRINT_MARK = "lantern-evals-fingerprint:"
FINGERPRINT_RE = re.compile(r"<!--\s*" + re.escape(FINGERPRINT_MARK) + r"\s*([0-9a-f]{64})\s*-->")


def _norm(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def is_watched(path: str) -> bool:
    p = _norm(path)
    if p in WATCHED_PATHS:
        return True
    if any(fnmatch(p, g) for g in UNWATCHED_GLOBS):
        return False
    return any(fnmatch(p, g) for g in WATCHED_GLOBS)


def orchestrator_units(src: str) -> dict[str, str]:
    """Source of each watched top-level function / assignment in orchestrator.py."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return {"<syntax-error>": hashlib.sha256(src.encode()).hexdigest()}
    lines = src.splitlines()
    out: dict[str, str] = {}
    for node in tree.body:
        names: list[str] = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names = [node.name]
        elif isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        for name in names:
            if name in WATCHED_UNITS:
                start = node.lineno - 1
                if getattr(node, "decorator_list", None):
                    start = min(d.lineno for d in node.decorator_list) - 1
                out[name] = "\n".join(lines[start:node.end_lineno])
    return out


def touched_units(old_src: str | None, new_src: str | None) -> list[str]:
    """Watched orchestrator units whose source differs between two versions."""
    old = orchestrator_units(old_src or "")
    new = orchestrator_units(new_src or "")
    return sorted(n for n in set(old) | set(new) if old.get(n) != new.get(n))


def watched_files(root: Path) -> list[Path]:
    files = [root / p for p in WATCHED_PATHS if (root / p).is_file()]
    agents = root / "agents"
    if agents.is_dir():
        for f in sorted(agents.rglob("*.md")):
            if is_watched(f.relative_to(root).as_posix()):
                files.append(f)
    return sorted(set(files))


def fingerprint(root: Path) -> str:
    """sha256 over (path, content-hash) of every watched file plus the watched
    orchestrator units — what REPORT.md must have been generated against."""
    h = hashlib.sha256()
    for f in watched_files(root):
        rel = f.relative_to(root).as_posix()
        h.update(rel.encode())
        h.update(hashlib.sha256(f.read_bytes().replace(b"\r\n", b"\n")).digest())
    orch = root / ORCHESTRATOR
    if orch.is_file():
        for name, src in sorted(orchestrator_units(orch.read_text(encoding="utf-8", errors="replace")).items()):
            h.update(name.encode())
            h.update(hashlib.sha256(src.encode("utf-8")).digest())
    return h.hexdigest()


def report_fingerprint(text: str) -> str | None:
    m = FINGERPRINT_RE.search(text or "")
    return m.group(1) if m else None


def evaluate(changed_paths: list[str], touched: list[str], report_changed: bool,
             fingerprint_ok: bool | None) -> list[str]:
    """The rule, pure. Returns problems (empty = pass)."""
    watched = sorted({_norm(p) for p in changed_paths if is_watched(p)})
    if touched:
        watched.append(f"{ORCHESTRATOR} ({', '.join(touched)})")
    if not watched:
        return []
    if not report_changed:
        return [f"the diff changes factory prompts/gates ({'; '.join(watched)}) but not {REPORT} - "
                "run `pipeline.py evals report` (after `evals build` / `evals run`) and commit it: "
                "changes to prompts or gates ship their eval numbers (D20)"]
    if fingerprint_ok is False:
        return [f"{REPORT} is in the diff but was not generated against the current watched files "
                f"({'; '.join(watched)}) - run `pipeline.py evals report` again after your last "
                "prompt/gate edit"]
    return []


# ── git plumbing ─────────────────────────────────────────────────────────────

def _git(args: list[str], root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          errors="replace", timeout=120)


def resolve_base(root: Path, base: str | None) -> str | None:
    candidates = []
    if base:
        candidates.append(base)
    env_base = os.environ.get("LANTERN_EVALS_BASE", "").strip()
    if env_base:
        candidates.append(env_base)
    pb = os.environ.get("LANTERN_PRODUCT_BRANCH", "").strip()
    if pb:
        candidates += [f"origin/{pb}", pb]
    candidates += ["origin/main", "main"]
    for c in candidates:
        if _git(["rev-parse", "--verify", "-q", f"{c}^{{commit}}"], root).returncode == 0:
            return c
    return None


def git_changes(root: Path, base: str) -> tuple[list[str], str | None, str | None]:
    """(changed paths base...HEAD ∪ working tree, orchestrator at base, orchestrator now)."""
    mb = _git(["merge-base", base, "HEAD"], root).stdout.strip() or base
    paths: set[str] = set()
    for args in (["diff", "--name-only", f"{mb}..HEAD"], ["diff", "--name-only", "HEAD"],
                 ["ls-files", "--others", "--exclude-standard"]):
        r = _git(args, root)
        if r.returncode == 0:
            paths.update(ln.strip() for ln in r.stdout.splitlines() if ln.strip())
    show = _git(["show", f"{mb}:{ORCHESTRATOR}"], root)
    old = show.stdout if show.returncode == 0 else None
    orch = root / ORCHESTRATOR
    new = orch.read_text(encoding="utf-8", errors="replace") if orch.is_file() else None
    return sorted(paths), old, new


def check(root: Path, base: str | None = None) -> tuple[int, str]:
    if _git(["rev-parse", "--is-inside-work-tree"], root).returncode != 0:
        return 0, "check_pr: not a git checkout - the eval rule cannot apply here"
    resolved = resolve_base(root, base)
    if not resolved:
        return 0, ("check_pr: no base branch to diff against (set --base, LANTERN_EVALS_BASE or "
                   "LANTERN_PRODUCT_BRANCH) - the eval rule cannot apply here")
    paths, old, new = git_changes(root, resolved)
    touched = touched_units(old, new) if (ORCHESTRATOR in paths) else []
    report_changed = REPORT in paths
    fp_ok: bool | None = None
    if report_changed:
        rp = root / REPORT
        fp_ok = rp.is_file() and report_fingerprint(rp.read_text(encoding="utf-8", errors="replace")) == fingerprint(root)
    problems = evaluate(paths, touched, report_changed, fp_ok)
    if problems:
        return 1, "check_pr FAILED (base " + resolved + "):\n- " + "\n- ".join(problems)
    watched_n = sum(1 for p in paths if is_watched(p)) + (1 if touched else 0)
    return 0, (f"check_pr: ok (base {resolved}, {len(paths)} changed path(s), "
               f"{watched_n} watched, REPORT.md {'updated' if report_changed else 'not needed'})")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="fail a diff that changes factory prompts/gates without eval numbers")
    ap.add_argument("--base", default=None, help="branch/ref to diff against")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    a = ap.parse_args(argv)
    code, msg = check(Path(a.root), a.base)
    print(msg, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
