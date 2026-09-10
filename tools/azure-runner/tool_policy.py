"""Execution-bound file capabilities. No SDK, database, or process-global identity.

This is a tool boundary, not an OS sandbox: coding shells still require isolated
compute. Keep the policy shared by both executors and test actual tool wrappers.
"""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re


ROLE_OUTPUTS = {
    "researcher": ("00-story", ("research.md", "research.json", "report.md")),
    "story": ("00-story", ("story.md", "story.json", "report.md")),
    "ui-ux": ("01-ui-ux", None),
    "pre-coding": ("02-pre-coding", None),
    "coding": ("03-coding", None),
    "reviewer": ("03-coding", ("report.md", "review/review.json", "review/round-*.md")),
    "qa-dev": ("04-qa-dev", None),
    "post-coding": ("05-post-coding", None),
    "validator": ("05-post-coding", ("report.md", "validation.md", "validation.json")),
    "security": ("06-security", None),
    "qa-staging": ("07-qa-staging", None),
    "debug": (None, None),
}
DEBUG_STAGES = {"01-triage", "02-repro", "03-root-cause", "05-regression", "06-postmortem"}
HOST_FILES = {
    ".collected.json", "gate.json", "gate.md", "handoff.json", "branch.bundle",
    "builders.json", "state.json", "media-manifest.json", "evidence-manifest.json",
}
# The design handoff is authored by ui-ux; coding handoffs are host-generated.
HOST_DIRS = {"trace", "babysit", "checkpoints"}
SECRET_NAMES = {".env", ".npmrc", ".pypirc", ".netrc", "credentials", "credentials.json"}
SECRET_DIRS = {".git", ".ssh", ".aws", ".azure", ".gnupg"}


def path_parts(path: str) -> tuple[str, ...]:
    """Accept portable relative paths only; reject NTFS streams and traversal."""
    if not isinstance(path, str) or not path or "\x00" in path:
        raise ValueError("path must be a non-empty relative path")
    norm = path.replace("\\", "/")
    if norm.startswith("/") or ":" in norm or ".." in norm.split("/"):
        raise ValueError("path must stay inside its relative root")
    parts = PurePosixPath(norm).parts
    # Windows strips trailing dots/spaces; refuse their portable ambiguity.
    if any(p.endswith((".", " ")) for p in parts):
        raise ValueError("ambiguous path component")
    return parts


def is_secret(parts: tuple[str, ...]) -> bool:
    for part in parts:
        name = part.lower()
        if name in SECRET_DIRS or name in SECRET_NAMES:
            return True
        if name.startswith(".env.") and name != ".env.example":
            return True
        if name.startswith(("id_rsa", "id_ed25519", "id_ecdsa", "id_dsa")):
            return True
        if name.endswith((".pem", ".key", ".p12", ".pfx")):
            return True
    return False


def confined(root: Path, parts: tuple[str, ...]) -> Path:
    root = root.resolve()
    candidate = root.joinpath(*parts)
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("path escapes its root through a link")
    # Do not allow aliases to turn a permitted filename into a protected file.
    for parent in (candidate, *candidate.parents):
        if parent == root:
            break
        if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
            raise ValueError("agent paths cannot traverse symbolic links or junctions")
    if is_secret(resolved.relative_to(root).parts):
        raise PermissionError("credential files and git metadata are not readable by agents")
    if resolved.is_file() and resolved.stat().st_nlink > 1:
        raise PermissionError("hard-linked files can alias another execution's data")
    return resolved


def readable(repo: Path, product: Path | None, path: str, run_id: str | None = None) -> Path:
    parts = path_parts(path)
    folded = tuple(p.casefold() for p in parts)
    if is_secret(parts):
        raise PermissionError("credential files and git metadata are not readable by agents")
    if folded and folded[0] == "product":
        if product is None or not product.is_dir():
            raise FileNotFoundError("no product repository is wired into this execution")
        return confined(product, parts[1:])
    if run_id and folded[:2] == ("workflow", "runs") and len(parts) > 2 and parts[2].casefold() != run_id.casefold():
        raise PermissionError("other runs are outside this execution's read scope")
    return confined(repo, parts)


@dataclass(frozen=True)
class StageAccess:
    repo: Path
    product: Path | None
    run_id: str
    role: str
    stage: str
    output_dir: str
    product_write: bool = False
    product_scope: tuple[str, ...] | None = None

    def __post_init__(self):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", self.run_id):
            raise ValueError("invalid run id")
        if self.role not in ROLE_OUTPUTS:
            raise ValueError("unknown role has no capabilities")
        path_parts(self.output_dir)
        expected, _ = ROLE_OUTPUTS[self.role]
        actual = self.output_dir.split("/")[0]
        if (expected and actual != expected) or (self.role == "debug" and actual not in DEBUG_STAGES):
            raise ValueError("role and output directory do not match")
        if self.product_write and self.role != "coding":
            raise ValueError("only coding can have a writable product")

    def read(self, path: str) -> Path:
        return readable(self.repo, self.product, path, self.run_id)

    def write(self, path: str, *, append: bool = False, binary: bool = False) -> Path:
        parts = path_parts(path)
        folded = tuple(p.casefold() for p in parts)
        if folded and folded[0] == "product":
            if not self.product_write or self.product is None:
                raise PermissionError("this role's product checkout is READ-ONLY")
            if len(parts) < 2:
                raise ValueError("write a file inside the product tree")
            target = confined(self.product, parts[1:])
            if self.product_scope is not None:
                from factory import path_in_scope
                if not path_in_scope("/".join(parts[1:]), list(self.product_scope)):
                    raise PermissionError("product path is outside the approved write scope")
            return target
        base = ("workflow", "runs", self.run_id, *path_parts(self.output_dir))
        if folded[:len(base)] != tuple(p.casefold() for p in base) or len(parts) <= len(base):
            raise PermissionError("write only inside this execution's stage output directory")
        relative = folded[len(base):]
        name = relative[-1]
        host_file = name.lower() in HOST_FILES
        if self.role == "ui-ux" and relative == ("handoff.json",):
            host_file = False
        if host_file or any(p.lower() in HOST_DIRS for p in relative):
            raise PermissionError("artifact is written by the harness, never by agent file tools")
        if relative[0] == "builders" or (self.role == "coding" and relative[0] == "review"):
            raise PermissionError("other executions' outputs are read-only")
        if self.role == "post-coding" and name in {"validation.md", "validation.json"}:
            raise PermissionError("validation belongs to the independent validator")
        _, allowed = ROLE_OUTPUTS[self.role]
        if allowed and not any(PurePosixPath(*relative).match(p) for p in allowed):
            raise PermissionError("artifact belongs to another role")
        if self.role in {"story", "validator", "reviewer"} and relative == ("report.md",) and not append:
            raise PermissionError("append this execution's section to the shared report")
        if not binary and ("media" in relative or name.lower().endswith((".webm", ".mp4", ".png", ".jpg", ".jpeg", ".pdf", ".zip"))):
            raise PermissionError("binary evidence must come from a recording or export tool")
        return confined(self.repo, parts)

    @property
    def exports(self) -> bool:
        return self.role == "ui-ux" and self.stage in {"01-ui-ux", "01-ui-ux.design"}


def render_capabilities() -> str:
    lines = ["# Agent file and tool capabilities", "",
             "Generated by `python tools/azure-runner/tool_policy.py`. Do not hand-edit.", "",
             "All roles can read repository files, their own run, and the product checkout, excluding "
             "conventional credential filenames and filesystem aliases. This is not a content secret scanner; "
             "all have validated read-only Git and execution-bound memory append. "
             "The product shell is a separate OS containment boundary.", "",
             "| Role | Artifact write scope within its run | Product shell | Desktop exports |",
             "|---|---|---|---|"]
    for role, (directory, files) in ROLE_OUTPUTS.items():
        scope = directory or "current debug stage"
        if files:
            scope += ": " + ", ".join(f"`{f}`" for f in files)
        else:
            scope += "/ (host artifacts excluded)"
        if role == "coding":
            scope += "; each builder has its own subdirectory"
        lines.append(f"| {role} | {scope} | {'auto mode only' if role == 'coding' else 'no'} | "
                     f"{'design phase only' if role == 'ui-ux' else 'no'} |")
    lines += ["", "Later roles append to shared reports. Coding file writes also obey the plan's "
              "product scope. Gate records, traces, manifests and coding handoffs are reserved "
              "for the harness. Text file tools cannot manufacture binary media evidence.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    print(render_capabilities(), end="")
