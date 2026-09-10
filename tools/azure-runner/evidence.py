"""Resolve claims to confined artifacts and the revision under review.

Resolution proves that evidence exists, not that its prose is true. Execution
provenance and semantic acceptance remain separate checks and human review.
"""

import re
import subprocess
from pathlib import Path

from tool_policy import confined, is_secret, path_parts
import readonly_git
import tool_execution


def references(value) -> list[dict]:
    """Typed references preferred; compact path[:line] strings remain supported."""
    if isinstance(value, str):
        out = []
        for text in value.split(";"):
            match = re.fullmatch(r"\s*([^:\n;]+?)(?::([1-9][0-9]*))?\s*", text)
            if not match:
                raise ValueError("use a path[:line] reference, not a sentence or URL")
            ref = {"path": match[1].strip()}
            if match[2]:
                ref["line"] = int(match[2])
            out.append(ref)
        return out
    if not isinstance(value, list) or not value or not all(isinstance(r, dict) for r in value):
        raise ValueError("evidence is required: a non-empty list of {path, line?} references")
    return value


def resolve(run: Path, product: Path | None, reference: dict) -> Path:
    if not isinstance(reference.get("path"), str):
        raise ValueError("evidence path must be a relative file path")
    parts = path_parts(reference["path"])
    folded = tuple(p.casefold() for p in parts)
    if is_secret(parts):
        raise ValueError("credential files are not admissible evidence")
    if folded[:2] == ("workflow", "runs"):
        if len(parts) < 4 or folded[2] != run.name.casefold():
            raise ValueError("evidence must belong to this run")
        parts = parts[3:]
        root = run
    elif parts and re.match(r"^\d{2}-", parts[0]):
        root = run
    else:
        if product is None:
            raise ValueError("product evidence requires the reviewed product checkout")
        root = product
        if folded and folded[0] == "product":
            parts = parts[1:]
    if root == run and parts and parts[0].casefold() == "05-post-coding" and parts[-1].casefold() in {"validation.json", "validation.md"}:
        raise ValueError("validation cannot cite itself as evidence")
    path = confined(root, parts)
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"evidence file missing or empty: {reference['path']}")
    line = reference.get("line")
    if line is not None:
        if type(line) is not int or line < 1:
            raise ValueError("evidence line must be a positive integer")
        if path.stat().st_size > 8_000_000:
            raise ValueError("line evidence exceeds the 8 MB text limit; cite a smaller artifact")
        try:
            count = len(path.read_text(encoding="utf-8").splitlines())
        except UnicodeError as exc:
            raise ValueError("line references require a UTF-8 text file") from exc
        if line > count:
            raise ValueError(f"evidence line {line} exceeds {count} lines in {reference['path']}")
    return path


def validation_problems(value, run: Path, product: Path | None) -> list[str]:
    try:
        refs = references(value)
    except ValueError as exc:
        return [str(exc)]
    problems = []
    for ref in refs:
        try:
            resolve(run, product, ref)
        except (OSError, ValueError) as exc:
            problems.append(str(exc))
    return problems


def _git(root: Path, *args: str) -> str:
    result = tool_execution.run(["git", "--no-pager", "-c", "core.fsmonitor=false", *args],
                            cwd=root, env=readonly_git.environment(), stdin=subprocess.DEVNULL,
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    if result.returncode:
        raise ValueError("cannot resolve reviewed revision or diff in the product checkout")
    return result.stdout


def review_problems(findings: list[dict], handoff: dict, product: Path) -> list[str]:
    base, head = handoff.get("base_sha"), handoff.get("head_sha")
    if not all(isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40,64}", sha) for sha in (base, head)):
        return ["review requires the handoff's base_sha and head_sha"]
    try:
        if _git(product, "rev-parse", "HEAD").strip() != head:
            return ["product checkout differs from the handoff head_sha; review the published revision"]
        changed = set(_git(product, "diff", "--name-only", "--no-renames", "-z", base, head, "--").split("\0")) - {""}
        problems = []
        for finding in findings:
            path, line = finding.get("file"), finding.get("line")
            if not path:
                if line is not None:
                    problems.append(f"{finding.get('id')}: a line requires a file")
                continue
            try:
                parts = path_parts(path)
                if parts and parts[0] == "product":
                    parts = parts[1:]
                if is_secret(parts):
                    raise ValueError("credential paths are not review evidence")
                relative = "/".join(parts)
                if relative not in changed:
                    raise ValueError("file is outside the reviewed diff; use a general finding for missing work")
                if line is not None:
                    if type(line) is not int or line < 1:
                        raise ValueError("line must be a positive integer")
                    # Read the immutable git blob, not a possibly modified worktree.
                    content = _git(product, "show", f"{head}:{relative}")
                    if line > len(content.splitlines()):
                        raise ValueError("line is outside the file at the reviewed revision")
                # Deleted files are valid file-level findings with line=null.
            except (OSError, ValueError) as exc:
                problems.append(f"{finding.get('id')}: {exc}")
        return problems
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return [str(exc)]
