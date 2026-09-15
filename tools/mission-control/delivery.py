"""Where a run's code goes, and how far it has got (D27).

The run page used to name the target in one line (repository, base, branch) and said
nothing about what happened to that branch afterwards, so "is the code actually in our
repository?" had no answer on screen. Every fact already exists: the run row names the
repository and branches, `branch_published` says whether the host pushed and which pull
request it opened, the `code_complete` approval carries the same payload, and the merge
babysitter records `merge_conflict`, `branch_merged` and `pr_closed`. This module turns
those rows into five steps a person can read: repository, branch, pull request,
approval, merge. The hosted coding agents we compared keep the same separation — a
pushed branch and an opened pull request are different states, and only a human merges.

Pure functions over plain rows: no database and no pipeline import. The caller resolves
the branch name with `pipeline.work_branch` and says whether the target is the factory.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import product_repos
from ui import H, chip

# The event types this module reads; the run page asks the database for exactly these.
EVENT_TYPES = ("branch_published", "pr_not_opened", "branch_updated", "merge_conflict",
               "babysit_push_refused", "branch_merged", "pr_closed")
_EPOCH = datetime.min.replace(tzinfo=timezone.utc)
MARK = {"done": "✓", "now": "●", "todo": "○", "warn": "!", "fail": "✕", "skip": "–"}
STATE_WORD = {"done": "done", "now": "in progress", "todo": "not yet", "warn": "needs attention",
              "fail": "stopped", "skip": "not applicable"}


def _data(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _at(e: dict) -> datetime:
    at = e.get("at")
    if isinstance(at, datetime):
        return at if at.tzinfo else at.replace(tzinfo=timezone.utc)
    return _EPOCH


def coding_reached(run: dict) -> bool:
    """Has the run got to (or past) the coding stage? Bug runs revisit stage numbers."""
    stage = run.get("current_stage") or ""
    if stage.startswith("03-coding") or run.get("status") == "done":
        return True
    if (run.get("id") or "").startswith("bug-"):
        return stage.startswith(("05-", "06-"))
    try:
        return int(stage[:2]) > 3
    except ValueError:
        return False


def build(run, events=(), approvals=(), branch: str = "", factory: bool = False) -> dict:
    run = dict(run)
    rid = run.get("id") or ""
    repo = run.get("product_repo") or ""
    base = run.get("product_branch") or "main"
    working = run.get("product_working_branch") or ""
    branch = branch or working or "(derived from the run id)"
    k = product_repos.kind(repo) if repo else ""
    name = product_repos.display_name(repo) if repo else ""
    auto = (run.get("coding_mode") or "human") == "auto"
    evs = sorted((dict(e) for e in events if dict(e).get("type") in EVENT_TYPES), key=_at)

    def last(*types):
        return next((e for e in reversed(evs) if e["type"] in types), None)

    pub_e = last("branch_published")
    pub = _data(pub_e["data"]) if pub_e else {}
    moved = last("branch_published", "branch_updated")
    head = ""
    for e in reversed(evs):
        d = _data(e["data"])
        if e["type"] in ("branch_published", "branch_updated") and (d.get("head_sha") or d.get("merge_sha")):
            head = str(d.get("head_sha") or d.get("merge_sha"))
            break
    gates = [dict(a) for a in approvals if dict(a).get("gate") == "code_complete"]
    gate = gates[-1] if gates else None
    payload = _data(gate.get("payload")) if gate else {}
    ext = str((gate or {}).get("external_ref") or "")
    pr_url = str(pub.get("pr_url") or payload.get("pr_url") or (ext if ext.startswith("http") else ""))
    pr_number = payload.get("pr_number") or pub.get("pr_number")
    if not pr_number and pr_url:
        m = re.search(r"/pull/(\d+)", pr_url)
        pr_number = int(m.group(1)) if m else None
    compare = str(payload.get("compare_url") or "")
    pushed = bool(pub.get("pushed") or payload.get("pushed"))
    not_opened = last("pr_not_opened")
    merged, closed, conflict = last("branch_merged"), last("pr_closed"), last("merge_conflict")
    conflict_open = bool(conflict and not (moved and _at(moved) > _at(conflict)))
    gate_status = str((gate or {}).get("status") or "")
    decided_by = str((gate or {}).get("decided_by") or "")
    reached = coding_reached(run) or bool(gate)

    steps: list[dict] = []

    def step(key, label, state, text, href="", link=""):
        steps.append({"key": key, "label": label, "state": state, "text": text,
                      "href": href, "link": link})

    # 1. repository
    if not repo:
        step("repo", "Repository", "fail",
             "Not connected. Planning and coding stop until the run knows its codebase.",
             f"/run/{rid}/repo", "Connect one")
    elif factory:
        step("repo", "Repository", "warn",
             f"`{name}` is the factory's own repository: branches land next to Lantern's code.")
    else:
        step("repo", "Repository", "done",
             f"`{name}` · {product_repos.KIND_LABEL.get(k, 'repository')}")

    # 2. branch
    if not repo:
        step("branch", "Branch", "todo", f"`{branch}` once a repository is connected")
    elif not auto:
        state = "done" if gate_status == "approved" else ("now" if reached else "todo")
        step("branch", "Branch", state,
             f"The assigned developer commits on `{branch}` in their own session")
    elif pub_e:
        if pushed:
            step("branch", "Branch", "done",
                 f"`{branch}` pushed" + (f" at `{head[:8]}`" if head else ""))
        elif k == "local":
            step("branch", "Branch", "warn",
                 f"`{branch}` landed in the checkout on the host; nothing was pushed")
        else:
            step("branch", "Branch", "warn", f"`{branch}` is in the host mirror but was not pushed")
    elif reached:
        step("branch", "Branch", "now",
             f"The coding agent commits on `{branch}` in a sandbox; the host publishes it "
             "after the quality gate")
    elif working:
        step("branch", "Branch", "todo", f"Continues the existing `{branch}` when coding starts")
    else:
        step("branch", "Branch", "todo", f"`{branch}` is created from `{base}` when coding starts")

    # 3. pull request
    pr_label = f"#{pr_number}" if pr_number else "Pull request"
    if not repo:
        step("pr", "Pull request", "todo", "Opened once the branch exists")
    elif pr_url:
        step("pr", "Pull request", "done", f"{pr_label} into `{base}`", pr_url, "Open")
    elif not_opened:
        err = str(_data(not_opened["data"]).get("error") or "the host could not open it")
        step("pr", "Pull request", "warn",
             f"Branch pushed without a pull request: {err[:140]}. `pipeline.py publish {rid}` retries.",
             compare, "Compare" if compare else "")
    elif compare:
        step("pr", "Pull request", "warn", "Branch pushed; no pull request yet", compare, "Compare")
    elif k == "local":
        step("pr", "Pull request", "skip", "None for a checkout on the host; review the branch there")
    elif k in ("https", "http", "ssh") and pub_e:
        step("pr", "Pull request", "skip",
             "Lantern opens pull requests on GitHub only; open the review on your git host")
    elif not auto:
        step("pr", "Pull request", "todo", "The developer opens it when the branch is ready")
    else:
        step("pr", "Pull request", "todo", f"The host opens it into `{base}` after publishing the branch")

    # 4. approval (the code_complete gate)
    if gate_status == "pending":
        step("approval", "Approval", "now", "Waiting for a human in Reviews", "/gates", "Review")
    elif gate_status == "approved":
        step("approval", "Approval", "done",
             "Code complete approved" + (f" by {decided_by}" if decided_by else ""))
    elif gate_status == "rejected":
        step("approval", "Approval", "fail", "Sent back" + (f" by {decided_by}" if decided_by else ""))
    else:
        step("approval", "Approval", "todo",
             "A human approves code complete with the pull request in front of them")

    # 5. merge — humans only; the babysitter (auto mode) keeps an approved branch mergeable
    if merged:
        via = _data(merged["data"]).get("via")
        step("merge", "Merge", "done",
             f"Merged into `{base}`" + (" (reported by GitHub)" if via == "github" else ""))
    elif closed:
        step("merge", "Merge", "fail", "The pull request was closed without merging")
    elif conflict_open:
        step("merge", "Merge", "warn",
             f"Conflicts with `{base}`: the babysitter stopped; resolve it on the branch")
    elif gate_status == "approved" and auto:
        step("merge", "Merge", "now",
             f"Waiting for a human to merge; the babysitter keeps `{branch}` mergeable")
    elif gate_status == "approved":
        step("merge", "Merge", "now", "Waiting for the developer to merge")
    else:
        step("merge", "Merge", "todo", "A human merges after QA, validation and security. Agents never merge.")

    if not repo:
        headline, tone = "No repository", "warn"
    elif merged:
        headline, tone = "Merged", "ok"
    elif closed:
        headline, tone = "Pull request closed", "blocked"
    elif conflict_open:
        headline, tone = "Merge conflict", "warn"
    elif pr_url:
        headline, tone = (f"PR #{pr_number}" if pr_number else "Pull request open"), "gate"
    elif pub_e and pushed:
        headline, tone = "Branch pushed", "ok"
    elif pub_e and k == "local":
        headline, tone = "Branch in the checkout", "warn"
    elif pub_e:
        headline, tone = "Branch not pushed", "warn"
    elif reached and auto:
        headline, tone = "Coding", ""
    else:
        headline, tone = "No branch yet", ""
    return {"run_id": rid, "repo": repo, "name": name, "kind": k, "factory": bool(factory),
            "base": base, "branch": branch, "continuing": bool(working), "auto": auto,
            "pr_url": pr_url, "pr_number": pr_number, "compare_url": compare, "head_sha": head,
            "pushed": pushed, "merged": bool(merged), "steps": steps,
            "headline": headline, "tone": tone}


def md_code(text: str) -> str:
    """Escape, then turn `backtick` spans into <code> — the only markup step texts carry."""
    parts = H(str(text)).split("`")
    if len(parts) % 2 == 0:                 # an unmatched backtick stays literal
        parts[-2:] = ["`".join(parts[-2:])]
    return "".join(f"<code>{p}</code>" if i % 2 else p for i, p in enumerate(parts))


def _link(s: dict) -> str:
    if not (s.get("href") and s.get("link")):
        return ""
    ext = " target='_blank' rel='noopener'" if s["href"].startswith("http") else ""
    return f" <a href='{H(s['href'])}'{ext}>{H(s['link'])}</a>"


def render_steps(model: dict) -> str:
    return "".join(
        f"<li class='st-{H(s['state'])}'><b><span class='st-mark' aria-hidden='true'>"
        f"{MARK.get(s['state'], '')}</span>{H(s['label'])}"
        f"<span class='sr-only'> ({STATE_WORD.get(s['state'], s['state'])})</span></b>"
        f"<span>{md_code(s['text'])}{_link(s)}</span></li>"
        for s in model["steps"])


def route_html(model: dict) -> str:
    if not model["repo"]:
        return ""
    return (f"<span class='dest-branches' title='pull request base, then the branch the work lands on'>"
            f"<code>{H(model['base'])}</code><span aria-hidden='true'> ← </span>"
            f"<span class='sr-only'> receives </span><code>{H(model['branch'])}</code></span>")


def render_card(model: dict, run_id: str, repo_href: str = "") -> str:
    """The run page's 'Where the code goes' card."""
    if model["name"] and repo_href:
        repo_bit = f"<a class='dest-repo' href='{H(repo_href)}'>{H(model['name'])}</a>"
    else:
        repo_bit = f"<b class='dest-repo'>{H(model['name'] or 'No repository')}</b>"
    chips = chip(model["headline"], model["tone"])
    if model["factory"]:
        chips += chip("factory repository", "warn")
    return (f"<section class='dest' aria-labelledby='dest-h'>"
            f"<div class='dest-head'><h2 id='dest-h'>Where the code goes</h2>"
            f"<a class='lnk' href='/run/{H(run_id)}/repo'>Change repository or branch</a></div>"
            f"<div class='dest-route'>{repo_bit}{route_html(model)}{chips}</div>"
            f"<ol class='dest-steps'>{render_steps(model)}</ol></section>")


def render_line(model: dict, run_id: str, repo_href: str = "") -> str:
    """One line for the run header: where the code lands, and how far it got."""
    if not model["repo"]:
        return (f"<a href='/run/{H(run_id)}/repo'>"
                + chip("no repository connected · planning and coding block · connect one", "warn")
                + "</a>")
    name = (f"<a href='{H(repo_href)}'>{H(model['name'])}</a>" if repo_href
            else f"<b>{H(model['name'])}</b>")
    return (f"Code lands in {name} · <code>{H(model['base'])}</code> ← "
            f"<code>{H(model['branch'])}</code> · {H(model['headline'])}"
            + (" " + chip("factory repository", "warn") if model["factory"] else "")
            + f" · <a href='/run/{H(run_id)}/repo' class='lnk'>change</a>")
