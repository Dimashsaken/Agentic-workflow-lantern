"""Which repository a run points at: one definition for every surface (D27).

Before D27 a product repository was a raw string on a run. It was typed into a brief, a
CLI flag, a Slack default or the per-run picker, compared byte for byte, and never
checked for what it *was*. That is how the first three Tender runs (2026-09-11) put their
`feat/*` branches into the factory's own repository: the briefs named this repository's
URL with a `product/tender-whatsapp` base, and nothing asked whether the target was the
control plane itself.

This module is the dependency-light half of the fix — no database driver, no model:

* `canonical()` / `identity()` give one spelling per repository, so
  `https://github.com/o/r`, `…/r.git`, `…/r/` and `git@github.com:o/r.git` are one
  repository wherever a target is stored or compared. GitHub SSH forms become the https
  URL the host's token can fetch, push and open pull requests with. Credentials pasted
  into a URL never survive.
* `is_factory()` says whether a target is the factory's own repository: this checkout,
  any clone or worktree of it, or its origin. Choosing it needs an explicit dogfood
  acknowledgement (`--dogfood`, or the checkbox in Mission Control).
* `check()` is the readiness checklist the Repositories page shows: can this host read
  the repository, does the base branch exist, will branches be pushed and pull requests
  opened, does the base carry the quality gate automatic coding needs (D24), is the base
  protected. Git, GitHub and the publication mode are injected, so the tests run it
  against real temporary repositories with no network.
* `upsert()` / `touch()` write the `product_repos` registry through whatever connection
  the caller already holds, and tolerate a database that predates the table.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tomllib
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlsplit

REPO = Path(__file__).resolve().parents[2]      # the factory's own checkout

KIND_LABEL = {"github": "GitHub", "https": "Git remote", "http": "Git remote (http)",
              "ssh": "SSH remote", "local": "Checkout on this host"}

_SCP = re.compile(r"^(?P<user>[A-Za-z0-9._~-]+)@(?P<host>[A-Za-z0-9.-]+):(?P<path>[^\s\\]+)$")
_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
_URL = re.compile(r"^(https?|ssh)://", re.I)
_GH_PATH = re.compile(
    r"^/?(?P<owner>[A-Za-z0-9][A-Za-z0-9-]{0,38})/(?P<name>[A-Za-z0-9._-]+?)(?:\.git)?/*$")

# Registry writes swallow only "this database predates the table" — by class name, so
# this module never has to import the database driver.
SCHEMA_MISSING = frozenset({"UndefinedTableError", "UndefinedColumnError"})


# ── spelling ─────────────────────────────────────────────────────────────────

def _strip(ref: str | None) -> str:
    return (ref or "").strip().strip("\"'").strip()


def is_local(ref: str | None) -> bool:
    """A path on the host: the rule `sync_product_mirror` applies, plus `~` and `\\`."""
    r = _strip(ref)
    return bool(r) and (r.startswith(("/", ".", "~", "\\")) or bool(_DRIVE.match(r)))


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def github(ref: str | None) -> tuple[str, str] | None:
    """(owner, name) for any spelling of a github.com repository, else None."""
    r = _strip(ref)
    if not r or is_local(r):
        return None
    if _URL.match(r):
        if _host(r) not in ("github.com", "www.github.com"):
            return None
        try:
            path = urlsplit(r).path
        except ValueError:
            return None
    else:
        m = _SCP.match(r)
        if not m or m.group("host").lower() != "github.com":
            return None
        path = m.group("path")
    m = _GH_PATH.match(path or "")
    if not m or m.group("name") in (".", ".."):
        return None
    return m.group("owner"), m.group("name")


def kind(ref: str | None) -> str:
    """'github' | 'https' | 'http' | 'ssh' | 'local', or '' for something that is not a
    repository reference. It describes the canonical form: `git@github.com:o/r` is
    'github', because that is the https URL it becomes."""
    r = _strip(ref)
    if not r:
        return ""
    if is_local(r):
        return "local"
    if github(r):
        return "github"
    low = r.lower()
    for scheme in ("https", "http", "ssh"):
        if low.startswith(scheme + "://"):
            return scheme if _host(r) else ""
    return "ssh" if _SCP.match(r) else ""


def canonical(ref: str | None) -> str:
    """The one spelling a registry row and a run store."""
    r = _strip(ref)
    if not r:
        return ""
    if is_local(r):
        try:
            return str(Path(r).expanduser().resolve())
        except (OSError, RuntimeError, ValueError):
            return r
    gh = github(r)
    if gh:
        return f"https://github.com/{gh[0]}/{gh[1]}"
    if _URL.match(r):
        try:
            parts = urlsplit(r)
            port = parts.port
        except ValueError:
            return r
        host = (parts.hostname or "").lower()
        if not host:
            return r
        scheme = parts.scheme.lower()
        # An ssh login is part of the address; an https user:password never is.
        login = f"{parts.username}@" if scheme == "ssh" and parts.username else ""
        return f"{scheme}://{login}{host}{f':{port}' if port else ''}{parts.path.rstrip('/')}"
    m = _SCP.match(r)
    if m:
        return f"{m.group('user')}@{m.group('host').lower()}:{m.group('path').rstrip('/')}"
    return r


def identity(ref: str | None) -> str:
    """The comparison key: two references to one repository have the same identity."""
    c = canonical(ref)
    k = kind(c)
    if k == "local":
        return os.path.normcase(os.path.normpath(c))
    if k == "github":
        return c.casefold()
    if k in ("https", "http", "ssh"):
        return c.removesuffix(".git").rstrip("/")
    return c


def display_name(ref: str | None) -> str:
    """'owner/name' for a remote, the folder name for a checkout."""
    c = canonical(ref)
    gh = github(c)
    if gh:
        return f"{gh[0]}/{gh[1]}"
    if kind(c) == "local":
        return Path(c).name or c
    segs = [s for s in re.split(r"[/:]", c.removesuffix(".git")) if s]
    return "/".join(segs[-2:]) if len(segs) >= 3 else c


def repo_id(ref: str | None) -> str:
    """A stable, readable id for the registry row and the /repos/<id> URL."""
    ident = identity(ref)
    if not ident:
        return ""
    readable = re.sub(r"[^a-z0-9]+", "-", display_name(ref).lower()).strip("-")[:48].strip("-")
    return f"{readable or 'repo'}-{hashlib.sha256(ident.encode('utf-8')).hexdigest()[:6]}"


# ── the factory's own repository ─────────────────────────────────────────────

def run_git(*args: str, cwd: Path | str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          timeout=120, errors="replace")


def _git_out(*args: str, cwd: Path | str) -> str:
    try:
        r = run_git(*args, cwd=cwd)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def origin_of(path: Path | str) -> str:
    """`remote.origin.url` of a repository on disk ('' when it has none)."""
    p = Path(path)
    return _git_out("config", "--get", "remote.origin.url", cwd=p) if p.is_dir() else ""


def factory_identities() -> frozenset[str]:
    """Every identity that means 'the factory's own repository'."""
    return _factory_identities(str(REPO))


@lru_cache(maxsize=8)
def _factory_identities(root: str) -> frozenset[str]:
    ids = {identity(root)}
    top = _git_out("rev-parse", "--show-toplevel", cwd=root)
    if top:
        ids.add(identity(top))
    # A linked worktree's common git dir sits in the main checkout.
    common = _git_out("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=root)
    if common:
        ids.add(identity(str(Path(common).parent)))
    origin = origin_of(root)
    if origin:
        ids.add(identity(origin))
    return frozenset(i for i in ids if i)


def is_factory(ref: str | None) -> bool:
    """True for the factory checkout, any clone or worktree of it, and its origin."""
    c = canonical(ref)
    if not c:
        return False
    ids = factory_identities()
    if identity(c) in ids:
        return True
    if kind(c) == "local" and Path(c).is_dir():
        top = _git_out("rev-parse", "--show-toplevel", cwd=c)
        if top and identity(top) in ids:
            return True
        origin = origin_of(top or c)        # a bare mirror or a clone remembers its origin
        if origin and identity(origin) in ids:
            return True
    return False



def origin_from_config(path: Path | str) -> str:
    """`remote.origin.url` read straight from the git config file, with no subprocess:
    for long lists of checkouts. '' for a linked worktree (its .git is a file)."""
    p = Path(path)
    cfg = p / ".git" / "config" if (p / ".git").is_dir() else p / "config"
    try:
        text = cfg.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    section = re.search(r'^\[remote "origin"\]\s*$(.*?)(?=^\[|\Z)', text, re.M | re.S)
    url = re.search(r"^\s*url\s*=\s*(.+?)\s*$", section.group(1), re.M) if section else None
    return _config_value(url.group(1)) if url else ""


def _config_value(raw: str) -> str:
    """A git config value as git reads it: quotes removed, backslash escapes undone (a
    Windows clone records its origin with doubled backslashes), an unquoted comment dropped."""
    escapes = {"n": "\n", "t": "\t", "b": "\b"}
    out, quoted, i = [], False, 0
    while i < len(raw):
        ch = raw[i]
        if ch == '"':
            quoted = not quoted
        elif ch == "\\" and i + 1 < len(raw):
            i += 1
            out.append(escapes.get(raw[i], raw[i]))
        elif ch in "#;" and not quoted:
            break
        else:
            out.append(ch)
        i += 1
    return "".join(out).strip()


def looks_like_factory(path: str) -> bool:
    """`is_factory()` for a list of checkouts on disk, without starting git: the path's
    identity, or the origin recorded in its git config. The connect route still runs the
    full `is_factory()` before anything is recorded."""
    ids = factory_identities()
    if identity(path) in ids:
        return True
    origin = origin_from_config(path)
    return bool(origin) and identity(origin) in ids

# ── readiness ────────────────────────────────────────────────────────────────

def _defaults() -> dict:
    import execution_runtime  # noqa: PLC0415
    import pipeline  # noqa: PLC0415 — pipeline imports this module; resolve it at call time
    from orchestrator import CODING_BRANCH_PREFIXES  # noqa: PLC0415
    return {"sync": pipeline.sync_product_mirror, "git": pipeline._git, "gh_api": pipeline._gh_api,
            "token": bool(pipeline.GIT_TOKEN), "leased": execution_runtime.enabled(),
            "prefixes": tuple(CODING_BRANCH_PREFIXES)}


def _clip(text: str, n: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def git_reason(error) -> str:
    """What git said, without the mirror bookkeeping in front of it: the host's mirror
    path is noise to the person deciding what access to grant."""
    text = re.sub(r"^product mirror (clone|fetch) failed:\s*", "", str(error))
    return re.sub(r"Cloning into (bare repository )?'[^']*'\.\.\.\s*", "", text).strip()


def access_fix(repo: str, k: str, token: bool) -> str:
    gh = github(repo)
    if k == "local":
        return "Check that the path exists on the machine running Lantern and is a git repository."
    if gh and not token:
        return ("This host has no `GITHUB_LANTERN_BOT_TOKEN`, so it can only read public "
                "repositories. Set the bot token for the host (tools/azure-runner/.env, or SSM "
                "on the box), then check again.")
    if gh:
        return (f"Give the bot account behind `GITHUB_LANTERN_BOT_TOKEN` (lantern-bot) access to "
                f"`{gh[0]}/{gh[1]}`: invite it as a collaborator with Write access (an "
                "organisation owner may have to approve the invitation), or add the repository "
                "to the fine-grained token's repository access. Then check again.")
    return "Make sure this host can clone the URL with its own credentials, then check again."


def _heads(git, mirror: Path) -> list[str]:
    r = git("for-each-ref", "--format=%(refname)", "refs/heads", cwd=mirror)
    names = [ln.strip()[len("refs/heads/"):] for ln in r.stdout.splitlines()
             if ln.strip().startswith("refs/heads/")]
    return sorted(n for n in names if n)


def _default_branch(git, mirror: Path, heads: list[str], k: str) -> str:
    if k == "local":
        r = git("symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD", cwd=mirror)
        name = r.stdout.strip().split("/", 1)[-1] if r.returncode == 0 else ""
        if name in heads:
            return name
    r = git("symbolic-ref", "--quiet", "--short", "HEAD", cwd=mirror)
    head = r.stdout.strip() if r.returncode == 0 else ""
    if k != "local" and head in heads:
        return head                                  # a mirror's HEAD is the origin's default
    for name in ("main", "master"):
        if name in heads:
            return name
    return head if head in heads else (heads[0] if heads else "")


def check(ref: str, base: str = "", *, sync=None, git=None, gh_api=None, token=None,
          leased=None, prefixes=None) -> dict:
    """Readiness of `ref` as a product target, as a checklist. A repository problem is
    never raised: the problems ARE the result. Items are {key, state, title, detail, fix}
    with state 'ok' | 'warn' | 'fail'."""
    if None in (sync, git, gh_api, token, leased, prefixes):
        d = _defaults()
        sync, git, gh_api = sync or d["sync"], git or d["git"], gh_api or d["gh_api"]
        token = d["token"] if token is None else token
        leased = d["leased"] if leased is None else leased
        prefixes = prefixes or d["prefixes"]
    items: list[dict] = []

    def add(key: str, state: str, title: str, detail: str = "", fix: str = "") -> None:
        items.append({"key": key, "state": state, "title": title, "detail": detail, "fix": fix})

    c, k = canonical(ref), kind(ref)
    res = {"ref": _strip(ref), "repo": c, "kind": k, "name": display_name(c) if k else _strip(ref),
           "id": repo_id(c) if k else "", "is_factory": False, "reachable": False, "error": None,
           "branches": [], "branch_count": 0, "default_branch": "", "base": (base or "").strip(),
           "base_exists": False, "base_sha": None,
           "gate": {"present": False, "test": "", "error": None}, "docs": [], "github": None,
           "publish": "none", "usable": False, "ready": False, "auto_ready": False,
           "items": items, "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if not k:
        add("reference", "fail", "Not a repository reference",
            f"`{_strip(ref) or '(empty)'}` is neither a clone URL nor a path.",
            "Paste the repository's https clone URL, for example `https://github.com/org/repo`.")
        return res

    res["is_factory"] = is_factory(c)
    if res["is_factory"]:
        add("factory", "fail", "This is the factory's own repository",
            "Lantern's control plane lives here. A run pointed at it creates its branches and "
            "pull requests in this repository, next to the pipeline's own code.",
            "Connect the product's own repository. Only a run that changes the factory itself "
            "should target this one, and it has to be marked as dogfood.")

    try:
        mirror = Path(sync(c))
    except (RuntimeError, OSError, subprocess.SubprocessError) as e:
        res["error"] = str(e)[:600]
        add("access", "fail", "This host cannot read the repository", _clip(git_reason(e), 300),
            access_fix(c, k, bool(token)))
        return res
    res["reachable"] = True
    heads = _heads(git, mirror)
    res["branches"], res["branch_count"] = heads[:300], len(heads)
    res["default_branch"] = _default_branch(git, mirror, heads, k)
    b = res["base"] or res["default_branch"] or "main"
    res["base"] = b
    add("access", "ok", "Reachable from this host",
        f"{len(heads)} branch{'' if len(heads) == 1 else 'es'}. " + (
            "Read straight from the checkout on disk: agents see committed work only."
            if k == "local" else
            "The host keeps a mirror; sandboxes get a read-only copy and never the token."))

    rv = git("rev-parse", "--verify", "--quiet", f"refs/heads/{b}^{{commit}}", cwd=mirror)
    if rv.returncode == 0 and rv.stdout.strip():
        res["base_exists"], res["base_sha"] = True, rv.stdout.strip()
        add("base", "ok", f"Base branch `{b}` exists",
            f"At `{res['base_sha'][:10]}`. Runs branch from it, and their pull requests target it.")
        _gate_and_docs(res, add, git, mirror, b)
    else:
        shown = ", ".join(f"`{h}`" for h in heads[:12]) + (" …" if len(heads) > 12 else "")
        add("base", "fail", f"No branch `{b}`", f"Branches: {shown or 'none'}.",
            "Choose one of the repository's branches as the base.")

    _publishing(res, add, c, k, b, gh_api, bool(token), bool(leased), tuple(prefixes))
    res["usable"] = res["reachable"] and res["base_exists"]
    res["ready"] = res["usable"] and not res["is_factory"]
    blocked = any(i["state"] == "fail" and i["key"] != "factory" for i in items)
    res["auto_ready"] = bool(res["usable"] and res["gate"]["test"] and not blocked)
    return res


def _gate_and_docs(res: dict, add, git, mirror: Path, base: str) -> None:
    show = git("show", f"refs/heads/{base}:lantern.toml", cwd=mirror)
    if show.returncode == 0:
        test, err = "", None
        try:
            quality = tomllib.loads(show.stdout).get("quality") or {}
            test = str(quality.get("test") or "").strip() if isinstance(quality, dict) else ""
        except tomllib.TOMLDecodeError as e:
            err = _clip(e, 200)
        res["gate"] = {"present": True, "test": test, "error": err}
        if test:
            add("gate", "ok", "Quality gate configured",
                f"`lantern.toml` on `{base}` runs `{_clip(test, 140)}` after every coding round.")
        else:
            add("gate", "warn", "lantern.toml has no test command",
                "Automatic coding refuses to start without `[quality].test` (D24); human coding "
                "is unaffected." + (f" The file does not parse: {err}" if err else ""),
                f"Add `test = \"…\"` under `[quality]` and merge it into `{base}`.")
    else:
        add("gate", "warn", f"No quality gate on `{base}`",
            "Automatic coding refuses to start without `lantern.toml` and a test command (D24). "
            "Human coding works without it.",
            "From the Lantern repository run `python tools/azure-runner/pipeline.py init-product "
            "<path to a checkout>`, review the commands it detects, and merge `lantern.toml` into "
            f"`{base}` through a normal pull request.")
    docs = [n for n in ("AGENTS.md", "CLAUDE.md", "README.md")
            if git("cat-file", "-e", f"refs/heads/{base}:{n}", cwd=mirror).returncode == 0]
    res["docs"] = docs
    agent_docs = [n for n in docs if n != "README.md"]
    if agent_docs:
        add("docs", "ok", "Agent instructions found",
            f"{' and '.join(f'`{n}`' for n in agent_docs)} on `{base}`: every stage reads the "
            "codebase's own conventions.")
    else:
        add("docs", "warn", "No AGENTS.md on the base branch",
            "Agents orient from `README.md` only." if docs else
            "Agents get no written conventions for this codebase.",
            "Add an `AGENTS.md` that says how to build, test and structure a change; "
            "`init-product` appends a starter block.")


def _publishing(res: dict, add, c: str, k: str, base: str, gh_api, token: bool, leased: bool,
                prefixes: tuple[str, ...]) -> None:
    ns = ", ".join(f"`{p}*`" for p in prefixes)
    if leased and k != "github":
        add("publish", "fail", "This host cannot publish to this target",
            "Leased publication (`LANTERN_EXECUTION_LEASES=1`) only publishes to GitHub "
            "repositories, so a run would stop at code complete.",
            "Use the repository's `https://github.com/…` URL.")
        return
    if k == "local":
        res["publish"] = "in_place"
        add("publish", "warn", "Branches land in this checkout, with no pull request",
            f"Automatic coding writes its branch ({ns}) straight into this repository on disk. "
            "Nothing is pushed and no pull request opens. Git refuses to move a branch that is "
            "checked out here, and uncommitted work is invisible to agents.",
            "For review on GitHub, connect the repository's https URL instead.")
        return
    if k in ("ssh", "http"):
        add("publish", "fail", "The host cannot push to this URL",
            "Branches are pushed only over https with the host's token, so a run would stop "
            "with its branch in the host mirror.",
            "Connect the repository's https clone URL instead.")
        return
    if k == "https":
        res["publish"] = "push"
        add("publish", "warn", "Branches are pushed; pull requests are not opened",
            f"Lantern pushes {ns} branches to this remote but opens pull requests on GitHub only.",
            "Open the review on your git host when a run reaches code complete.")
        return
    owner, name = github(c) or ("", "")
    if not token:
        add("publish", "fail", "No bot token on this host",
            "Without `GITHUB_LANTERN_BOT_TOKEN` the host cannot push branches or open pull "
            "requests.", access_fix(c, k, False))
        return
    try:
        status, body = gh_api("GET", f"/repos/{owner}/{name}")
    except (RuntimeError, OSError, ValueError) as e:
        add("publish", "warn", "GitHub did not answer", _clip(e, 200), "Check again later.")
        return
    if status != 200 or not isinstance(body, dict):
        add("publish", "fail", "GitHub does not show this repository to the bot token",
            f"GitHub answered {status}.", access_fix(c, k, True))
        return
    perms = body.get("permissions") if isinstance(body.get("permissions"), dict) else {}
    can_push = bool(perms.get("push") or perms.get("maintain") or perms.get("admin"))
    res["github"] = {"private": body.get("private"), "archived": body.get("archived"),
                     "default_branch": body.get("default_branch"), "push": can_push if perms else None}
    if body.get("archived"):
        add("publish", "fail", "The repository is archived on GitHub",
            "An archived repository is read-only: branches cannot be pushed.",
            "Unarchive it on GitHub, or connect the repository that replaced it.")
        return
    if perms and not can_push:
        add("publish", "fail", "The bot token can read but not push",
            "Runs would stop at publication: branches cannot be pushed and pull requests cannot "
            "be opened.", f"Give lantern-bot Write access to `{owner}/{name}`.")
        return
    res["publish"] = "pull_request"
    if perms:
        add("publish", "ok", "Pull requests open automatically",
            f"The host pushes each run's branch ({ns}) and opens a pull request into `{base}` "
            f"as the bot. Agents never push to `{base}` and never merge.")
    else:
        add("publish", "warn", "Push permission not reported",
            "GitHub did not return the token's permissions; publication is attempted at code "
            "complete.")
    if not res["base_exists"]:
        return
    try:
        st, br = gh_api("GET", f"/repos/{owner}/{name}/branches/{quote(base, safe='/')}")
    except (RuntimeError, OSError, ValueError):
        return
    if st == 200 and isinstance(br, dict):
        if br.get("protected"):
            add("protection", "ok", f"`{base}` is protected",
                "Changes reach it through pull requests under the repository's rules.")
        else:
            add("protection", "warn", f"`{base}` is not protected",
                "Agents never push to it, but nothing stops an unreviewed merge.",
                f"In GitHub add a branch rule or ruleset for `{base}`: require a pull request "
                f"with at least one approving review, and let lantern-bot push only {ns} branches.")


def status(res: dict | None) -> tuple[str, str]:
    """(label, chip kind) summarising a check for lists and pickers."""
    if not res:
        return "Not checked", ""
    if not res.get("kind"):
        return "Not a repository", "blocked"
    if not res.get("reachable"):
        return "Needs access", "blocked"
    if not res.get("base_exists"):
        return "Base branch missing", "blocked"
    if res.get("is_factory"):
        return "Factory · dogfood only", "warn"
    if any(i.get("state") == "fail" for i in res.get("items", [])):
        return "Needs attention", "blocked"
    if res.get("auto_ready"):
        return "Ready", "ok"
    return "Ready for human coding", "warn"


def _ascii(text: str) -> str:
    """Terminal text a cp1252 Windows console prints without mojibake."""
    for uni, plain in (("…", "..."), ("·", "-"), ("—", "-"), ("←", "<-"), ("’", "'")):
        text = text.replace(uni, plain)
    return text


def render_text(res: dict) -> str:
    """The checklist for a terminal: ASCII only, because Windows consoles are not UTF-8."""
    return _ascii(_render_text(res))


def _render_text(res: dict) -> str:
    mark = {"ok": "ok  ", "warn": "warn", "fail": "FAIL"}
    lines = [f"{res.get('name') or res.get('ref')}  [{KIND_LABEL.get(res.get('kind'), 'unknown')}]"
             f"  {res.get('repo') or ''}"]
    for it in res.get("items", []):
        lines.append(f"  [{mark.get(it['state'], it['state'])}] {it['title']}")
        if it.get("detail"):
            lines.append(f"         {it['detail']}")
        if it.get("fix") and it["state"] != "ok":
            lines.append(f"         fix: {it['fix']}")
    lines.append(f"  => {status(res)[0]}")
    return "\n".join(lines)


def parse_check(value) -> dict | None:
    """A stored check_result (jsonb arrives as text through asyncpg) as a dict."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


# ── the registry (product_repos) ─────────────────────────────────────────────

async def upsert(conn, res: dict, by: str, default_branch: str = "") -> str:
    """Insert or refresh the registry row for a checked repository; returns its id.
    Connecting again un-archives the row and replaces its last check."""
    await conn.execute(
        """INSERT INTO product_repos (id, url, name, kind, default_branch, is_factory,
                                      check_result, checked_at, connected_by)
           VALUES ($1, $2, $3, $4, $5, $6, $7, now(), $8)
           ON CONFLICT (id) DO UPDATE SET url = EXCLUDED.url, name = EXCLUDED.name,
               kind = EXCLUDED.kind, default_branch = EXCLUDED.default_branch,
               is_factory = EXCLUDED.is_factory, check_result = EXCLUDED.check_result,
               checked_at = now(), archived = false, updated_at = now()""",
        res["id"], res["repo"], res["name"], res["kind"],
        default_branch or res.get("base") or res.get("default_branch") or "main",
        bool(res.get("is_factory")), json.dumps(res), by)
    return res["id"]


async def touch(conn, repo: str, base: str, by: str) -> None:
    """Record that a run points at `repo`, registering it when nobody connected it first.
    Never fails a run for a database that predates the registry."""
    c = canonical(repo)
    if not c:
        return
    try:
        await conn.execute(
            """INSERT INTO product_repos (id, url, name, kind, default_branch, is_factory,
                                          connected_by, last_used_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, now())
               ON CONFLICT (id) DO UPDATE SET last_used_at = now(), updated_at = now()""",
            repo_id(c), c, display_name(c), kind(c), base or "main", is_factory(c), by)
    except Exception as e:  # noqa: BLE001 — only the not-yet-migrated case is tolerated
        if type(e).__name__ not in SCHEMA_MISSING:
            raise
