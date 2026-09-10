"""Observed-state reconciliation for the host's GitHub publication effect.

Reads are deliberately separate from writes: a duplicate intent is permission only
to inspect. A branch without the matching PR is partial, not successful publication.
No comments, labels, approvals, merges or automatic replay are issued here.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from urllib.parse import quote, urlencode


class PublicationHeld(RuntimeError):
    """The provider outcome cannot safely be accepted or replayed."""


def destination(request):
    if not isinstance(request, dict):
        raise PublicationHeld("publication request is missing")
    match = re.fullmatch(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?", request.get("repo", ""))
    if not match:
        raise PublicationHeld("leased publication requires an explicit GitHub destination")
    owner, name = match.groups()
    if owner in {".", ".."} or name in {".", ".."}:
        raise PublicationHeld("invalid GitHub destination")
    for field in ("branch", "base"):
        value = request.get(field)
        if (not isinstance(value, str) or not value or value.startswith(("-", "/"))
                or any(part in value for part in ("..", "@{", "//", "\\"))
                or re.search(r"[\s~^:?*\[\x00-\x1f\x7f]", value)
                or any(part.startswith(".") or part.endswith((".lock", ".")) for part in value.split("/"))
                or value.endswith("/")):
            raise PublicationHeld("invalid publication ref")
    if request["branch"] == request["base"] or not request["branch"].startswith(("feat/", "fix/", "proto/")):
        raise PublicationHeld("publication must target a separate agent branch")
    if not re.fullmatch(r"[0-9a-f]{40}", request.get("head_sha", "")):
        raise PublicationHeld("publication requires an exact commit SHA")
    return owner, name


def _repository_and_base(api, request):
    owner, name = destination(request)
    root = f"/repos/{owner}/{name}"
    status, repo = api("GET", root)
    if (status != 200 or not isinstance(repo, dict) or type(repo.get("id")) is not int
            or repo["id"] <= 0 or str(repo.get("full_name", "")).casefold() != f"{owner}/{name}".casefold()):
        raise PublicationHeld("GitHub repository identity unavailable or malformed")
    status, base = api("GET", root + "/git/ref/heads/" + quote(request["base"], safe=""))
    if (status != 200 or not isinstance(base, dict) or base.get("ref") != "refs/heads/" + request["base"]
            or not isinstance(base.get("object"), dict) or base["object"].get("type") != "commit"
            or not isinstance(base["object"].get("sha"), str) or not re.fullmatch(r"[0-9a-f]{40}", base["object"]["sha"])):
        raise PublicationHeld("GitHub base revision unavailable or malformed")
    return repo["id"], base["object"]["sha"]


def prepare_request(api, request, version=2):
    """Capture immutable provider identities BEFORE persisting the new intent."""
    repository_id, base_sha = _repository_and_base(api, request)
    if version not in (2, 3):
        raise PublicationHeld("unsupported publication request version")
    result = {**request, "version": version, "repository_id": repository_id,
              "base_sha": base_sha, "expected_remote_sha": None}
    initial = observe(api, result)
    result["expected_remote_sha"] = initial.head
    return result


@dataclass(frozen=True)
class Observation:
    head: str | None
    pr: dict | None

    def complete(self, request):
        return self.head == request["head_sha"] and self.pr is not None and self.pr["head"]["sha"] == self.head


def _pr_identity(pr, owner, name, branch, base, repository_id=None, base_sha=None):
    """Validate every returned item, including contradictory filtered responses."""
    try:
        number = pr["number"]
        correct = (type(number) is int and number > 0 and pr["state"] == "open"
                   and pr.get("merged_at") is None
                   and pr["html_url"] == f"https://github.com/{owner}/{name}/pull/{number}"
                   and pr["head"]["repo"]["full_name"].casefold() == f"{owner}/{name}".casefold()
                   and pr["base"]["repo"]["full_name"].casefold() == f"{owner}/{name}".casefold()
                   and pr["head"]["ref"] == branch and pr["base"]["ref"] == base
                   and (repository_id is None or (type(pr["head"]["repo"].get("id")) is int
                                                   and type(pr["base"]["repo"].get("id")) is int
                                                   and pr["head"]["repo"].get("id") == repository_id
                                                   and pr["base"]["repo"].get("id") == repository_id))
                   and (base_sha is None or pr["base"].get("sha") == base_sha)
                   and re.fullmatch(r"[0-9a-f]{40}", pr["head"]["sha"]))
    except (KeyError, TypeError, AttributeError):
        correct = False
    if not correct:
        raise PublicationHeld("GitHub PR response has conflicting or malformed destination/revision identity")


def observe(api, request, max_pages=20):
    """Bounded complete pagination; any unavailable/contradictory read holds."""
    owner, name = destination(request)
    if request.get("version") in (2, 3):
        repository_id, base_sha = _repository_and_base(api, request)
        if (type(request.get("repository_id")) is not int or request["repository_id"] != repository_id
                or request.get("base_sha") != base_sha
                or (request.get("expected_remote_sha") is not None
                    and not re.fullmatch(r"[0-9a-f]{40}", request["expected_remote_sha"]))):
            raise PublicationHeld("GitHub repository or base revision changed after publication intent")
    root = f"/repos/{owner}/{name}"
    status, ref = api("GET", root + "/git/ref/heads/" + quote(request["branch"], safe=""))
    if status == 404:
        head = None
    elif (status == 200 and isinstance(ref, dict)
          and ref.get("ref") == "refs/heads/" + request["branch"]
          and isinstance(ref.get("object"), dict)
          and ref["object"].get("type") == "commit"
          and isinstance(ref["object"].get("sha"), str)
          and re.fullmatch(r"[0-9a-f]{40}", ref["object"]["sha"])):
        head = ref["object"]["sha"]
    else:
        raise PublicationHeld("GitHub branch observation unavailable or malformed")
    found = []
    for page in range(1, max_pages + 1):
        query = urlencode({"state": "all", "head": f"{owner}:{request['branch']}", "per_page": 100, "page": page})
        status, prs = api("GET", root + "/pulls?" + query)
        if status != 200 or not isinstance(prs, list) or len(prs) > 100:
            raise PublicationHeld("GitHub PR observation unavailable or malformed")
        for pr in prs:
            _pr_identity(pr, owner, name, request["branch"], request["base"], request.get("repository_id"), request.get("base_sha"))
            found.append(pr)
        if len(prs) < 100:
            break
    else:
        raise PublicationHeld("GitHub PR pagination incomplete")
    if len(found) > 1:
        raise PublicationHeld("multiple GitHub PRs match the publication branch")
    if found and found[0]["head"]["sha"] != head:
        raise PublicationHeld("GitHub branch and PR observations disagree; inspect again")
    return Observation(head, found[0] if found else None)


def receipt(request, observation, reused=True):
    if not observation.complete(request):
        raise PublicationHeld("publication is absent, partial, or at a different revision; refusing replay")
    request_json = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return {"publication_request": dict(request), "observed_head_sha": observation.head,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "request_sha256": hashlib.sha256(request_json.encode()).hexdigest(),
            "branch": request["branch"], "base": request["base"], "head_sha": request["head_sha"],
            "pushed": True, "pr_url": observation.pr["html_url"],
            "pr_number": observation.pr["number"], "pr_reused": reused}


def reconcile(api, request, previous=None):
    """Read-only even for confirmed duplicates. Old unbound receipts fail closed."""
    if previous is not None and (not isinstance(previous, dict) or previous.get("publication_request") != request):
        raise PublicationHeld("legacy or changed publication receipt requires operator inspection")
    observed = receipt(request, observe(api, request))
    if previous is not None and (previous.get("pr_url") != observed["pr_url"] or previous.get("pr_number") != observed["pr_number"]):
        raise PublicationHeld("confirmed publication PR identity changed")
    return observed


def push_cas(git, remote, branch, head, observed_head, cwd):
    """Git's server-side ref CAS prevents overwriting a concurrently changed ref.

    Push the immutable SHA, never a mutable local branch ref. An empty expected
    value asserts remote absence; a nonempty value is the exact observed object.
    No fallback to unconditional force is permitted.
    """
    if not re.fullmatch(r"[0-9a-f]{40}", head) or (observed_head is not None and not re.fullmatch(r"[0-9a-f]{40}", observed_head)):
        raise PublicationHeld("CAS requires exact commit identities")
    result = git("push", "--quiet", f"--force-with-lease=refs/heads/{branch}:{observed_head or ''}",
                 remote, f"{head}:refs/heads/{branch}", cwd=cwd)
    if result.returncode:
        raise PublicationHeld("publication push failed or observed ref changed; reconcile before retry")


def publish(api, git, remote, cwd, request, title, body, before=None, check_current=None):
    """Only call for a newly persisted intent; every mutation has a preceding read."""
    owner, name = destination(request)
    before = before or observe(api, request)
    if before.complete(request):
        return receipt(request, before)
    if request.get("version") == 2 and before.head != request["expected_remote_sha"]:
        raise PublicationHeld("remote revision changed after publication intent")
    if before.head != request["head_sha"]:
        if check_current:
            check_current()
        push_cas(git, remote, request["branch"], request["head_sha"], before.head, cwd)
    after = observe(api, request)
    if after.head != request["head_sha"]:
        raise PublicationHeld("published branch revision changed before PR publication")
    if after.pr:
        return receipt(request, after)
    if check_current:
        check_current()
    try:
        status, pr = api("POST", f"/repos/{owner}/{name}/pulls",
                         {"title": title, "head": request["branch"], "base": request["base"], "body": body})
        # Never trust a create response alone; a timeout/422 can also mean that a
        # concurrent request created the PR. Observe once and never repeat POST.
    except (OSError, TimeoutError):
        pass
    return receipt(request, observe(api, request), reused=False)


def action_request(request, action):
    if request.get("version") != 3 or action not in ("branch", "pr"):
        raise PublicationHeld("split publication requires a v3 branch or PR intent")
    return {"publication_request": dict(request), "action": action}


def publish_split(api, git, remote, cwd, request, title, body, before=None,
                  check_current=None, begin_effect=None, complete_effect=None):
    """Resume only effects whose durable before-action intent does not exist yet.

    Callbacks are host-owned, fenced database operations. An existing action can
    only be confirmed by fresh provider state; absence of its desired result is
    never permission to retry. A missing PR action after an observed branch push
    permits a new PR intent and one POST, because this v3 protocol always persists
    that intent before invoking the provider. V1/v2 parents cannot enter this path.
    """
    if request.get("version") != 3 or not all(callable(fn) for fn in (check_current, begin_effect, complete_effect)):
        raise PublicationHeld("split publication requires bound host effect callbacks")
    owner, name = destination(request)
    observed = before or observe(api, request)
    branch_effect = begin_effect("branch")
    if observed.head != request["head_sha"]:
        if not branch_effect.created:
            raise PublicationHeld("existing branch intent is unresolved; refusing push replay")
        if observed.head != request["expected_remote_sha"]:
            raise PublicationHeld("remote revision changed after publication intent")
        check_current()
        push_cas(git, remote, request["branch"], request["head_sha"], observed.head, cwd)
        observed = observe(api, request)
    if observed.head != request["head_sha"]:
        raise PublicationHeld("branch effect is not observed at the intended revision")
    branch_ref = f"https://github.com/{owner}/{name}/tree/{request['head_sha']}"
    branch_result = {**action_request(request, "branch"), "head_sha": observed.head,
                     "observed_at": datetime.now(timezone.utc).isoformat()}
    if branch_effect.status == "confirmed" and branch_effect.external_ref != branch_ref:
        raise PublicationHeld("confirmed branch effect identity changed")
    complete_effect("branch", branch_effect, branch_ref, branch_result)

    # Refresh after the branch receipt transaction. A takeover, repository change,
    # branch move or changed PR cannot be hidden by the earlier observation.
    observed = observe(api, request)
    if observed.head != request["head_sha"]:
        raise PublicationHeld("branch changed before PR intent")
    pr_effect = begin_effect("pr")
    reused = observed.pr is not None
    if observed.pr is None:
        if not pr_effect.created:
            raise PublicationHeld("existing PR intent is unresolved; refusing POST replay")
        check_current()
        try:
            api("POST", f"/repos/{owner}/{name}/pulls",
                {"title": title, "head": request["branch"], "base": request["base"], "body": body})
        except (OSError, TimeoutError):
            pass
        observed = observe(api, request)
    result = receipt(request, observed, reused=reused)
    if pr_effect.status == "confirmed" and (pr_effect.external_ref != result["pr_url"]
            or not isinstance(pr_effect.result, dict) or pr_effect.result.get("pr_number") != result["pr_number"]):
        raise PublicationHeld("confirmed PR effect identity changed")
    complete_effect("pr", pr_effect, result["pr_url"], result)
    return result
