"""The supported read-only Git grammar. Unknown options fail closed.

Git subcommands are not capabilities: `branch`, `tag`, and even `grep` have
write/execute forms. Enumerate useful inspection forms instead of chasing a denylist.
"""

import os
import re
import subprocess
from pathlib import Path

from tool_policy import SECRET_DIRS, SECRET_NAMES, confined, is_secret, path_parts


CONTENT_COMMANDS = {"log", "show", "diff", "grep"}
# Git applies these to historical trees as well as the current index. Excluding
# all .env variants here is deliberately conservative (.env.example remains
# available through read_file). Explicit user pathspecs cannot undo exclusions.
SECRET_GLOBS = sorted(SECRET_NAMES | SECRET_DIRS | {
    ".env.*", "id_rsa*", "id_ed25519*", "id_ecdsa*", "id_dsa*",
    "*.pem", "*.key", "*.p12", "*.pfx",
})
SECRET_PATHSPECS = [f":(glob,icase,exclude)**/{pattern}{suffix}"
                    for pattern in SECRET_GLOBS for suffix in ("", "/**")]


def repository_options(root: Path | None) -> list[str]:
    """Preserve line-ending semantics without inheriting arbitrary Git options.

    A Windows checkout may have been created under global core.autocrlf=true.
    Discarding that setting makes untouched CRLF files appear modified. Read only
    this scalar through Git, validate it, then pass it explicitly to inspection.
    """
    if root is None:
        return []
    config_env = environment()
    config_env.pop("GIT_CONFIG_GLOBAL", None)
    config_env.pop("GIT_CONFIG_NOSYSTEM", None)
    result = subprocess.run(["git", "config", "--get", "core.autocrlf"], cwd=root,
                            env=config_env, stdin=subprocess.DEVNULL,
                            capture_output=True, text=True, timeout=15)
    value = result.stdout.strip().lower()
    return ["-c", f"core.autocrlf={value}"] if result.returncode == 0 and value in {"true", "false", "input"} else []


def _commit(root: Path | None, value: str) -> None:
    """Do not let anonymous blob/tree IDs bypass the filename policy."""
    if root is None:
        raise ValueError("content inspection requires a product checkout")
    for revision in re.split(r"\.{2,3}", value.lstrip("^")):
        revision = revision or "HEAD"
        result = subprocess.run(
            ["git", "--no-pager", "rev-parse", "--verify", "--end-of-options", revision + "^{commit}"],
            cwd=root, env=environment(), stdin=subprocess.DEVNULL,
            capture_output=True, timeout=15,
        )
        if result.returncode:
            raise ValueError("use a commit revision and put file paths after --; anonymous blobs are not supported")


def _alias_exclusions(root: Path | None) -> list[str]:
    """Working-tree diff/grep must not follow innocent-named file aliases."""
    if root is None:
        raise ValueError("content inspection requires a product checkout")
    result = subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "ls-files", "-z"],
                            cwd=root, env=environment(), stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=30, check=True)
    exclusions = []
    for raw in result.stdout.split(b"\x00"):
        if not raw:
            continue
        name = os.fsdecode(raw)
        try:
            confined(root, path_parts(name))
        except (ValueError, OSError):
            exclusions.append(f":(literal,exclude){name}")
    return exclusions


DIFF_FLAGS = {"--stat", "--numstat", "--shortstat", "--name-only", "--name-status",
              "--patch", "-p", "--raw", "--summary", "--check", "--no-renames",
              "--find-renames", "--no-color", "--color=never", "--no-ext-diff",
              "--no-textconv", "--ignore-space-at-eol", "--ignore-all-space", "-w",
              "--ignore-space-change", "-b", "--exit-code", "--quiet", "--binary"}
HISTORY_FLAGS = {"--oneline", "--all", "--decorate", "--no-decorate", "--graph",
                 "--reverse", "--first-parent", "--no-merges", "--merges",
                 "--date-order", "--topo-order", "--no-patch", "-s"}
FLAGS = {
    "log": DIFF_FLAGS | HISTORY_FLAGS,
    "show": DIFF_FLAGS | (HISTORY_FLAGS - {"--all"}),
    "diff": DIFF_FLAGS | {"--cached", "--staged"},
    "branch": {"--list", "-l", "--all", "-a", "--remotes", "-r", "-v", "-vv",
               "--verbose", "--no-color", "--show-current"},
    "tag": {"--list", "-l", "--no-color"},
    "ls-files": {"--cached", "-c", "--deleted", "-d", "--modified", "-m",
                 "--others", "--exclude-standard", "--stage", "-s", "--unmerged", "-u", "-z"},
    "ls-tree": {"-r", "-t", "-l", "--name-only", "--name-status", "--full-tree", "-z"},
    "grep": {"-n", "--line-number", "-i", "--ignore-case", "-I", "-w", "--word-regexp",
             "-F", "--fixed-strings", "-E", "--extended-regexp", "-l", "--files-with-matches",
             "-L", "--files-without-match", "-c", "--count", "-v", "--invert-match",
             "--all-match", "--and", "--or", "--not", "(", ")", "--cached", "--no-color"},
    "shortlog": {"-s", "--summary", "-n", "--numbered", "-e", "--email", "--all"},
    "blame": {"--line-porcelain", "--porcelain", "--incremental", "-p", "-w", "-l", "-s",
              "--show-name", "--show-number", "--root"},
    "rev-parse": {"--verify", "--quiet", "-q", "--short", "--abbrev-ref", "--symbolic-full-name",
                  "--is-inside-work-tree", "--is-bare-repository", "--show-toplevel"},
    "describe": {"--tags", "--always", "--all", "--long", "--exact-match", "--dirty"},
    "status": {"--short", "-s", "--branch", "-b", "--porcelain", "--porcelain=v1", "--porcelain=v2",
               "--untracked-files=no", "--untracked-files=normal", "--untracked-files=all", "-z"},
}
VALUES = {
    "log": {"-n", "--max-count", "--since", "--until", "--author", "--grep", "--format", "--pretty", "--date", "-S", "-G"},
    "show": {"--format", "--pretty", "--date"},
    "diff": {"--unified", "-U", "-S", "-G", "--diff-filter"},
    "branch": {"--format", "--sort", "--contains", "--no-contains", "--merged", "--no-merged"},
    "tag": {"--format", "--sort", "--contains", "--no-contains", "--merged", "--no-merged"},
    "grep": {"-e", "--regexp", "-A", "-B", "-C", "--max-depth"},
    "blame": {"-L"},
    "describe": {"--match", "--exclude", "--abbrev"},
}


def _operand(value: str, *, path: bool = False) -> None:
    # rev:path is useful for reading a committed file; it must obey file policy.
    candidate = value
    if ":" in value:
        if path or value.startswith(":") or value.count(":") != 1:
            raise ValueError("Git pathspec magic and absolute paths are not supported")
        _, candidate = value.split(":", 1)
    parts = path_parts(candidate)
    if is_secret(parts):
        raise PermissionError("credential files and git metadata are outside Git tool access")


def argv(subcommand: str, args: list[str] | None = None, *, root: Path | None = None) -> list[str]:
    if subcommand not in FLAGS:
        raise ValueError(f"'{subcommand}' is not a supported read-only Git command")
    if args is not None and (not isinstance(args, list) or not all(isinstance(a, str) and a and "\x00" not in a for a in args)):
        raise ValueError("Git args must be a list of non-empty strings")
    tokens = args or []
    i, paths = 0, False
    normalized = []
    grep_pattern = any(t in {"-e", "--regexp"} or t.startswith("--regexp=") for t in tokens)
    while i < len(tokens):
        token = tokens[i]
        if token == "--" and not paths:
            paths = True
        elif not paths and token in FLAGS[subcommand]:
            pass
        elif not paths and token.partition("=")[0] in VALUES.get(subcommand, set()):
            if "=" not in token:
                i += 1
                if i == len(tokens):
                    raise ValueError(f"missing value for {token}")
                # Some Git options take OPTIONAL values only after '='. Passing
                # a separate token could let it become a new, unchecked option.
                token += ("=" if token.startswith("--") else "") + tokens[i]
        elif not paths and re.fullmatch(r"-(?:n|U|A|B|C)?\d+", token) and subcommand in {"log", "show", "diff", "grep", "tag"}:
            pass
        elif not paths and token.startswith("-"):
            raise ValueError(f"flag not allowed in read-only Git: {token}")
        elif subcommand == "grep" and not paths and not grep_pattern:
            grep_pattern = True
        else:
            _operand(token, path=paths)
            if subcommand in CONTENT_COMMANDS and not paths:
                if subcommand == "show" and ":" in token:
                    revision, filename = token.split(":", 1)
                    if any(c in filename for c in "*?["):
                        raise ValueError("show revision:path requires a literal file path")
                    _commit(root, revision)
                else:
                    _commit(root, token)
            elif subcommand == "blame":
                # Blame accepts exactly one literal filename; Git itself checks
                # revision arguments. Refuse linked working-tree aliases too.
                if root is not None and (paths or (root / token).exists()):
                    confined(root, path_parts(token))
        normalized.append(token)
        i += 1
    # Listing cannot turn into a ref mutation, even with bare positional operands.
    mode = ["--list"] if subcommand in {"branch", "tag"} and "--show-current" not in tokens else []
    no_drivers = ["--no-ext-diff", "--no-textconv"] if subcommand in {"log", "show", "diff"} else []
    if subcommand in CONTENT_COMMANDS:
        if "--" not in normalized:
            normalized.append("--")
        normalized += SECRET_PATHSPECS
        if subcommand in {"diff", "grep"}:
            normalized += _alias_exclusions(root)
    return ["git", "--no-pager", "--no-optional-locks", "-c", "core.pager=cat",
            "-c", "core.fsmonitor=false", *repository_options(root), subcommand, *mode, *no_drivers, *normalized]


def environment() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env.update(GIT_PAGER="cat", GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1",
               GIT_CONFIG_GLOBAL=os.devnull, GIT_OPTIONAL_LOCKS="0")
    return env
