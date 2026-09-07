"""Host-local git repo discovery for the product-target picker (D15).

The point of this module is the *boundary*, not the walk. A repo picker on a web UI
is a filesystem-read primitive: whatever path it admits gets cloned by the host,
bind-mounted into a sandbox, exposed to agents through `read_file('product/…')` and
`product_git('grep')`, and — since D15 — has its own AGENTS.md/README pasted into a
system prompt and billed. So the rules are:

  * `LANTERN_WORKSPACE_ROOTS` is the whole boundary. Unset means the picker offers
    NOTHING, not everything. There is no "browse anywhere" mode.
  * `contains()` is the only function a write route may use to admit a user-supplied
    path, and it resolves BOTH sides before comparing — comparing an unresolved user
    path against a resolved root is the standard symlink bypass.
  * Discovery returns directory and branch names only. Never file contents, never a
    listing of anything that is not a git repo.

It lives here rather than in pipeline.py deliberately: the daemon, the CLI, app.py and
chat.py all import pipeline, and a filesystem walker there would put this scan surface
in every one of those processes. Verification of a chosen target stays in pipeline.py
(`verify_product_target`) because the CLI needs it too.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

# `~/work/<repo>` is already this project's convention for product checkouts on the
# box (docs/AGENT-TOOLING.md §4), so the default is host-relative and matches what the
# box already does. NEVER default to Path.home() or "/": an over-broad default fails
# OPEN, and this is the one setting where failing open is a security bug.
DEFAULT_ROOT_NAME = "work"

MAX_DEPTH = 3          # <root>/a/b/c
MAX_REPOS = 200
SCAN_BUDGET_S = 3.0    # a network drive under a root must not hang the event loop
CACHE_TTL_S = 30.0     # the board auto-reloads every 30s; do not re-walk per tick

# Directories that are never a product repo and are expensive to descend.
SKIP_NAMES = frozenset({
    "node_modules", ".venv", "venv", "env", "__pycache__", ".cache", ".tox",
    "dist", "build", "out", "target", "vendor", "coverage", ".terraform",
    "Library", "AppData", "Application Data", "OneDriveTemp", "$RECYCLE.BIN",
    "System Volume Information", "Program Files", "Program Files (x86)", "Windows",
})

_cache: dict[tuple[str, ...], tuple[float, list[dict]]] = {}


def workspace_roots() -> list[Path]:
    """Directories the picker may look inside — THE security boundary.

    `LANTERN_WORKSPACE_ROOTS` is os.pathsep-separated (';' on Windows, ':' elsewhere).
    Unset falls back to ~/work when it exists, and otherwise to nothing at all.
    """
    raw = os.environ.get("LANTERN_WORKSPACE_ROOTS", "").strip()
    if not raw:
        default = Path.home() / DEFAULT_ROOT_NAME
        return [default.resolve()] if default.is_dir() else []
    roots: list[Path] = []
    for part in raw.split(os.pathsep):
        part = part.strip().strip('"')
        if not part:
            continue
        try:
            p = Path(part).expanduser().resolve()
        except (OSError, RuntimeError):
            continue
        if p.is_dir() and p not in roots:
            roots.append(p)
    return roots


def is_repo(path: Path) -> bool:
    """A git repo, working tree or worktree. `.git` is a directory in a normal clone
    and a FILE in a linked worktree — miss the file case and every worktree on the
    developer's machine becomes invisible."""
    try:
        return (path / ".git").exists()
    except OSError:
        return False


def head_branch(repo: Path) -> str:
    """The checked-out branch, read straight out of .git/HEAD.

    Deliberately not `git rev-parse --abbrev-ref HEAD`: discovery may see 200 repos and
    200 subprocesses on a box already running two sandboxes is a real cost. Branch
    *lists* are fetched with real git, but only for the one repo the user selects.
    """
    try:
        dot = repo / ".git"
        if dot.is_file():   # linked worktree: 'gitdir: <path>'
            gitdir = dot.read_text(encoding="utf-8", errors="replace").strip()
            gitdir = gitdir.split(":", 1)[1].strip() if ":" in gitdir else ""
            head = Path(gitdir) / "HEAD" if gitdir else None
        else:
            head = dot / "HEAD"
        if head is None or not head.is_file():
            return ""
        text = head.read_text(encoding="utf-8", errors="replace").strip()
        if text.startswith("ref: refs/heads/"):
            return text[len("ref: refs/heads/"):]
        return text[:12] + " (detached)" if text else ""
    except (OSError, ValueError, IndexError):
        return ""


def _describe(repo: Path, root: Path) -> dict:
    try:
        mtime = (repo / ".git").stat().st_mtime
    except OSError:
        mtime = 0.0
    return {
        "path": str(repo),
        "name": repo.name,
        "root": str(root),
        "rel": str(repo.relative_to(root)) if repo != root else ".",
        "head_branch": head_branch(repo),
        "mtime": mtime,
    }


def discover_repos(roots: list[Path] | None = None, max_depth: int = MAX_DEPTH,
                   use_cache: bool = True) -> list[dict]:
    """Git repos under the configured roots, on the filesystem of whichever host is
    running this process. Bounded in depth, count and wall clock; never raises."""
    roots = workspace_roots() if roots is None else roots
    key = tuple(str(r) for r in roots)
    now = time.monotonic()
    if use_cache and key in _cache and now - _cache[key][0] < CACHE_TTL_S:
        return _cache[key][1]

    found: list[dict] = []
    deadline = now + SCAN_BUDGET_S
    for root in roots:
        if is_repo(root):          # a root that is itself a repo still counts
            found.append(_describe(root, root))
            continue
        stack: list[tuple[Path, int]] = [(root, 0)]
        while stack:
            if len(found) >= MAX_REPOS or time.monotonic() > deadline:
                break
            current, depth = stack.pop()
            try:
                entries = list(os.scandir(current))
            except (PermissionError, OSError):
                continue           # "not yours" is exactly what should stay hidden
            for entry in entries:
                try:
                    # follow_symlinks=False: a symlink is the escape hatch out of a root.
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                if entry.name in SKIP_NAMES or entry.name.startswith("."):
                    continue
                child = Path(entry.path)
                if is_repo(child):
                    # A repo is a LEAF: record it and stop. This is what keeps the walk
                    # cheap and stops it wandering into vendored submodule trees.
                    found.append(_describe(child, root))
                    if len(found) >= MAX_REPOS:
                        break
                elif depth + 1 < max_depth:
                    stack.append((child, depth + 1))

    found.sort(key=lambda r: (-r["mtime"], r["name"].lower()))
    if use_cache:
        _cache[key] = (now, found)
    return found


def contains(path: str) -> Path | None:
    """Resolve a user-supplied path and return it ONLY if it is a git repo inside a
    configured root. The single admission point for any path a route accepts.

    Returns None for: an empty path, an unresolvable one, anything outside every root,
    and anything that is not a git repo. Callers must treat None as a refusal — never
    fall back to the raw input.
    """
    if not (path or "").strip():
        return None
    try:
        p = Path(path.strip().strip('"')).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    roots = workspace_roots()
    if not any(p == r or p.is_relative_to(r) for r in roots):
        return None
    if not is_repo(p):
        return None
    return p


def roots_label() -> str:
    """Human-readable roots, for the UI header and refusal messages."""
    roots = workspace_roots()
    return ", ".join(str(r) for r in roots) if roots else "(none configured)"
