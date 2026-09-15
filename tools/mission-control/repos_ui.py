"""The Repositories pages and the Start work form (D27).

"Where do I connect the repository?" was the question Mission Control could not answer.
The only control was a per-run picker that appeared after a run already existed, and it
offered nothing on a host without LANTERN_WORKSPACE_ROOTS. The hosted coding agents we
compared (the Copilot agents panel, Jules, OpenHands Cloud, Claude Code on the web) work
the other way round: connect a repository once, see whether it is ready and why not, then
start work by picking the repository first. These renderers are that, over the
`product_repos` registry. Pure HTML builders: app.py owns the routes and the database.
"""
from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import quote

import delivery
import product_repos
from ui import H, ago, chip

MARK = {"ok": "✓", "warn": "!", "fail": "✕"}
STATE_WORD = {"ok": "passed", "warn": "warning", "fail": "blocking"}
PREFIXES = ("feat/", "fix/", "proto/")


def _ago(now: datetime, ts) -> str:
    return f"{ago((now - ts).total_seconds())} ago" if isinstance(ts, datetime) else ""


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


# ── shared pieces ────────────────────────────────────────────────────────────

def flow_html(kind: str = "github", base: str = "main", name: str = "",
              prefixes=PREFIXES) -> str:
    """How work reaches a repository, as six steps, true for this kind of target."""
    repo = f"<code>{H(name)}</code>" if name else "the product repository"
    b = f"<code>{H(base)}</code>"
    feat, fix = "<code>feat/&lt;date&gt;-&lt;slug&gt;</code>", "<code>fix/&lt;date&gt;-&lt;slug&gt;</code>"
    builders = ("Parallel builders commit on <code>&lt;run branch&gt;--&lt;name&gt;</code> branches that the host "
                "merges into the run branch before publishing")
    if kind == "local":
        builders += ", and those branches appear in this checkout too."
        publish = ("The host checks the handoff and writes the branch straight into this checkout. "
                   "Nothing is pushed and no pull request opens.")
        merge = f"You review the branch and merge it into {b} yourself."
    elif kind == "https":
        builders += "; they stay in the host's mirror."
        publish = ("The host checks the handoff holds only that branch, then pushes it with its "
                   "token. Pull requests open on GitHub only, so open the review on your git host.")
        merge = f"A human merges into {b} after QA, validation and security. Agents never merge."
    else:
        builders += "; they stay in the host's mirror."
        publish = (f"The host checks the handoff holds only that branch, pushes it as lantern-bot "
                   f"and opens a pull request into {b}.")
        merge = (f"A human merges on GitHub after QA, validation and security. Until then the "
                 f"babysitter merges {b} into the branch when it moves and re-runs the gate. "
                 "Agents never merge.")
    steps = [
        ("Connect once", f"The host keeps a mirror of {repo}. The GitHub token stays on the host; "
                         "every sandbox gets a read-only copy."),
        ("Read the base", f"Research, story, design and planning read {b} without changing it."),
        ("A branch per run", f"Automatic coding commits on {feat} ({fix} for bug runs), created "
                             f"from {b} inside a sandbox. {builders}"),
        ("Publish", publish),
        ("Review", "The review bot reads the branch and fixes land on the same branch. Then a human "
                   "approves code complete in Reviews, with the pull request open."),
        ("Merge", merge),
    ]
    items = "".join(f"<li><b>{H(t)}</b><span>{d}</span></li>" for t, d in steps)
    ns = ", ".join(f"<code>{H(p)}*</code>" for p in prefixes)
    never = ("<ul class='never' aria-label='What never happens'>"
             f"<li>No agent pushes to {b}, merges, or holds the token.</li>"
             f"<li>Agent branches stay inside {ns}.</li>"
             "<li>Product branches never land in the factory's own repository unless a run is "
             "marked dogfood.</li></ul>")
    return f"<ol class='flow'>{items}</ol>{never}"


def render_checks(res: dict | None) -> str:
    if not res:
        return "<p class='sub'>Not checked yet. Use <b>Check again</b>.</p>"
    rows = []
    for it in res.get("items", []):
        state = it.get("state") or "warn"
        detail = f"<p>{delivery.md_code(it['detail'])}</p>" if it.get("detail") else ""
        fix = (f"<p class='fix'><b>Fix:</b> {delivery.md_code(it['fix'])}</p>"
               if it.get("fix") and state != "ok" else "")
        rows.append(
            f"<li class='ck {H(state)}'><span class='ck-mark' aria-hidden='true'>{MARK.get(state, '?')}</span>"
            f"<div><b>{delivery.md_code(it.get('title', ''))}</b>"
            f"<span class='sr-only'> ({STATE_WORD.get(state, state)})</span>{detail}{fix}</div></li>")
    when = res.get("checked_at") or ""
    stamp = f"<p class='sub'>Checked {H(when.replace('T', ' ')[:16])} UTC.</p>" if when else ""
    return f"<ul class='checks'>{''.join(rows)}</ul>{stamp}"


# ── /repos ───────────────────────────────────────────────────────────────────

def render_index(repos: list[dict], runs_by_repo: dict[str, list[dict]], discovered: list[dict],
                 unconnected: list[dict], now: datetime, *, error: str = "", prefill: str = "",
                 roots: str = "", registry_missing: bool = False) -> str:
    out = ["<header class='work-heading'><div><span class='eyebrow'>Your workspace</span>"
           "<h1>Repositories</h1><p>Connect each product repository once. Every run picks one, "
           "and its branches and pull requests land there.</p></div>"
           "<a class='btn primary' href='#connect'>Connect a repository</a></header>"]
    if error:
        out.append(f"<div class='notice' role='alert'><b>Not connected.</b> {H(error)}</div>")
    if registry_missing:
        out.append("<div class='notice'><b>The repository registry is missing.</b> Run "
                   "<code>python tools/azure-runner/pipeline.py init-db</code>, or restart Mission "
                   "Control, to create it.</div>")

    if repos:
        rows = []
        for r in repos:
            check = product_repos.parse_check(r.get("check_result"))
            label, tone = product_repos.status(check)
            runs = runs_by_repo.get(r["id"], [])
            live = sum(1 for x in runs if x.get("status") not in ("done", "cancelled"))
            meta = (f"base <code>{H(r.get('default_branch') or 'main')}</code> · {_plural(len(runs), 'run')}"
                    + (f" · {live} active" if live else ""))
            checked = _ago(now, r.get("checked_at"))
            kind = product_repos.KIND_LABEL.get(r.get("kind"), r.get("kind") or "repository")
            rows.append(
                f"<a class='repo-row' data-k href='/repos/{H(quote(r['id']))}'>"
                f"<span class='repo-name'><strong>{H(r['name'])}</strong><span>{H(r['url'])}</span></span>"
                f"<span class='repo-kind'>{chip(kind, 'tier')}"
                f"{chip('factory', 'warn') if r.get('is_factory') else ''}</span>"
                f"<span class='repo-meta'>{meta}<br>{H('checked ' + checked if checked else 'not checked yet')}</span>"
                f"<span class='repo-state'>{chip(label, tone)}</span></a>")
        out.append(f"<section class='repo-list' aria-label='Connected repositories'>{''.join(rows)}</section>")
    else:
        out.append("<div class='work-empty'><span aria-hidden='true'>◇</span><h2>No repositories yet</h2>"
                   "<p>Connect the product's GitHub repository below. Lantern checks access, the base "
                   "branch, pull-request permission and the quality gate before any run uses it.</p></div>")

    if unconnected:
        items = []
        for u in unconnected:
            field = "local_path" if u.get("kind") == "local" else "remote_url"
            action = ("<span class='repo-meta'>Factory repository: connect it below with the dogfood "
                      "box ticked</span>" if u.get("factory") else
                      f"<form method='post' action='/repos/connect'>"
                      f"<input type='hidden' name='{field}' value='{H(u['url'])}'>"
                      f"<button class='btn sm'>Connect</button></form>")
            items.append(
                f"<li><span class='repo-name'><strong>{H(u['name'])}</strong><span>{H(u['url'])}</span></span>"
                f"<span class='repo-meta'>{_plural(u['runs'], 'run')}</span>{action}</li>")
        out.append("<h2 class='sect'>Used by runs, not connected</h2><p class='sub'>Runs point at these "
                   "repositories, but nobody has connected them. Connecting one checks it and lists its "
                   f"runs.</p><ul class='repo-used'>{''.join(items)}</ul>")

    host_rows = []
    for d in discovered:
        tags = (chip("factory", "warn") if d.get("factory") else "") + (chip("connected", "ok") if d.get("connected") else "")
        host_rows.append(
            f"<label><input type='radio' name='local_path' value='{H(d['path'])}'>"
            f"<span class='nm'>{H(d['name'])}</span><span class='br'>{H(d.get('head_branch') or '—')}</span>"
            f"{tags}<span class='pt'>{H(d['path'])}</span></label>")
    host = (f"<div class='repolist'>{''.join(host_rows)}</div>" if host_rows else
            "<div class='warnbox'>No checkouts offered. The picker only looks inside "
            f"<code>LANTERN_WORKSPACE_ROOTS</code> (currently <code>{H(roots or '(none configured)')}</code>). "
            "That is a security boundary: set it on the host running Mission Control, or paste a URL above.</div>")
    out.append(
        "<form method='post' action='/repos/connect' class='pick' id='connect'>"
        "<h3>Connect a repository</h3>"
        "<p class='hint'>Paste the product repository's https URL. The host checks it with its own "
        "token, which never enters a sandbox. The first check of a large repository clones it and "
        "can take a minute.</p>"
        "<div class='row'>"
        "<label class='fld' style='flex:1 1 320px'><span class='lb'>Clone URL</span>"
        f"<input type='text' name='remote_url' placeholder='https://github.com/org/repo' value='{H(prefill)}' "
        "autocomplete='off' spellcheck='false'></label>"
        "<label class='fld'><span class='lb'>Base branch</span>"
        "<input type='text' name='base_branch' placeholder='default branch' autocomplete='off' spellcheck='false'></label>"
        "</div>"
        "<details class='hostpick'><summary>Or pick a checkout on this host</summary>"
        "<p class='hint'>A checkout is read from disk: agents see committed work only, and branches "
        f"land in it with no pull request.</p>{host}</details>"
        "<label class='checkline'><input type='checkbox' name='dogfood' value='1'> "
        "<span>This is the factory's own repository, connected for runs that change Lantern itself "
        "(dogfood)</span></label>"
        "<div class='row'><button class='btn primary'>Connect and check</button></div></form>")
    out.append("<section aria-labelledby='flow-h'><h2 class='sect' id='flow-h'>How work reaches a "
               "repository</h2><p class='sub'>The same path for every run, whichever surface started it: "
               "Mission Control, the CLI, chat or Slack.</p>" + flow_html() + "</section>")
    return "".join(out)


# ── /repos/<id> ──────────────────────────────────────────────────────────────

def render_detail(repo: dict, check: dict | None, runs: list[dict], models: dict[str, dict],
                  now: datetime, *, error: str = "", prefixes=PREFIXES) -> str:
    label, tone = product_repos.status(check)
    rid = repo["id"]
    base = repo.get("default_branch") or "main"
    kind = repo.get("kind") or ""
    meta = [f"<span class='mono'>{H(repo['url'])}</span>", f"base <code>{H(base)}</code>"]
    if repo.get("connected_by"):
        meta.append(f"connected by {H(repo['connected_by'])}"
                    + (f" {H(_ago(now, repo.get('connected_at')))}" if repo.get("connected_at") else ""))
    usable = bool(check and check.get("usable")) and not repo.get("archived")
    start = (f"<a class='btn primary' href='/new?repo={H(quote(rid))}'>Start work in this repository</a>"
             if usable else
             "<span class='btn' aria-disabled='true'>Start work in this repository</span>"
             "<span class='repo-meta'>Fix the blocking checks first.</span>")
    out = [f"<a class='back-link' href='/repos'>← Repositories</a>"
           f"<header class='repo-head'><div class='caps'>Repository</div><h1>{H(repo['name'])}</h1>"
           f"<div class='repo-chips'>{chip(product_repos.KIND_LABEL.get(kind, kind or 'repository'), 'tier')}"
           f"{chip(label, tone)}{chip('archived') if repo.get('archived') else ''}</div>"
           f"<p class='meta'>{' · '.join(meta)}</p>"
           f"<div class='repo-actions'>{start}"
           f"<form method='post' action='/repos/{H(quote(rid))}/check'><button class='btn'>Check again</button></form>"
           f"</div></header>"]
    if error:
        out.append(f"<div class='notice' role='alert'><b>Check failed.</b> {H(error)}</div>")
    if repo.get("is_factory"):
        out.append("<div class='notice'><b>The factory's own repository.</b> Runs that target it change "
                   "Lantern itself, and each one has to be marked dogfood. Product work belongs in the "
                   "product's own repository.</div>")
    out.append("<section aria-labelledby='ready-h'><h2 class='sect' id='ready-h'>Readiness</h2>"
               "<p class='sub'>What the host found the last time it checked. A blocking item stops runs "
               "from starting; a warning limits what a run can do.</p>" + render_checks(check) + "</section>")
    out.append("<section aria-labelledby='flow-h'><h2 class='sect' id='flow-h'>Where work lands</h2>"
               + flow_html(kind or "github", base, repo["name"], prefixes) + "</section>")
    if runs:
        rows = []
        for r in runs:
            m = models.get(r["id"]) or {}
            pr = (f"<a href='{H(m['pr_url'])}' target='_blank' rel='noopener'>"
                  f"{H('#' + str(m['pr_number']) if m.get('pr_number') else 'open')}</a>"
                  if m.get("pr_url") else "—")
            rows.append(
                f"<tr><td><a href='/run/{H(r['id'])}'>{H(r['id'])}</a></td>"
                f"<td>{H(r.get('status') or '')}<br><span class='dim'>{H(r.get('current_stage') or '')}</span></td>"
                f"<td><code>{H(m.get('base') or base)}</code> ← <code>{H(m.get('branch') or '')}</code></td>"
                f"<td>{pr}</td><td>{chip(m.get('headline') or '', m.get('tone') or '')}</td></tr>")
        table = ("<div class='mwrap'><table class='cattbl repo-runs'><thead><tr><th scope='col'>Run</th>"
                 "<th scope='col'>Status</th><th scope='col'>Base ← branch</th><th scope='col'>Pull request</th>"
                 f"<th scope='col'>Where it is</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>")
    else:
        table = "<p class='sub'>No run has targeted this repository yet.</p>"
    out.append(f"<section aria-labelledby='runs-h'><h2 class='sect' id='runs-h'>Runs on this repository</h2>{table}</section>")
    if not repo.get("archived"):
        out.append("<details class='disclosure'><summary>Archive this repository</summary>"
                   "<p class='sub'>Archiving hides it from pickers and the Start work form. Runs that already "
                   "target it keep working, and connecting it again restores it.</p>"
                   f"<form method='post' action='/repos/{H(quote(rid))}/archive' "
                   "onsubmit=\"return confirm('Archive this repository?')\">"
                   "<button class='btn danger sm'>Archive</button></form></details>")
    return "".join(out)


# ── /new ─────────────────────────────────────────────────────────────────────

def render_new(repos: list[dict], selected: str, fields: dict, now: datetime, *, error: str = "",
               design_default: str = "paper", prefixes=PREFIXES) -> str:
    head = ("<header class='work-heading'><div><span class='eyebrow'>Start work</span>"
            "<h1>What should the factory build?</h1><p>Pick the repository first: the run's branch and "
            "pull request land there.</p></div>"
            "<a class='lnk' href='/chat'>Or describe it to Lantern in chat →</a></header>")
    active = [(r, product_repos.parse_check(r.get("check_result")) or {})
              for r in repos if not r.get("archived")]
    if not active:
        return head + ("<div class='work-empty'><span aria-hidden='true'>◇</span><h2>Connect a repository first</h2>"
                       "<p>A run has to know which codebase it changes. Connect the product's repository, "
                       "and Lantern checks it before any run starts.</p>"
                       "<a class='btn primary' href='/repos#connect'>Connect a repository</a></div>")
    sel = next((r for r, _ in active if r["id"] == selected), None) or next(
        (r for r, c in active if c.get("usable")), active[0][0])
    data = {}
    for r, c in active:
        data[r["id"]] = {"name": r["name"], "kind": r.get("kind") or "",
                         "base": r.get("default_branch") or "main",
                         "branches": list(c.get("branches") or [])[:300],
                         "usable": bool(c.get("usable")), "factory": bool(r.get("is_factory")),
                         "gate": bool((c.get("gate") or {}).get("test")),
                         "status": product_repos.status(c or None)[0]}
    sc = data[sel["id"]]
    base = fields.get("base_branch") or sc["base"]
    branches = sc["branches"] or [sc["base"]]
    mode = fields.get("coding_mode") or "human"
    design = fields.get("design_mode") or design_default
    today = f"{now:%Y%m%d}"

    repo_opts = "".join(
        f"<option value='{H(r['id'])}'{' selected' if r['id'] == sel['id'] else ''}>"
        f"{H(r['name'])} · {H(data[r['id']]['status'])}</option>" for r, _ in active)
    base_opts = "".join(f"<option{' selected' if b == base else ''}>{H(b)}</option>" for b in branches)
    work_opts = "<option value=''>A new branch for this run</option>" + "".join(
        f"<option{' selected' if b == fields.get('working_branch') else ''}>{H(b)}</option>"
        for b in branches if b.startswith(tuple(prefixes)))

    def radio(name, value, current, title, text):
        return (f"<label class='opt'><input type='radio' name='{name}' value='{value}'"
                f"{' checked' if value == current else ''}><span><b>{H(title)}</b>{H(text)}</span></label>")

    modes = (radio("coding_mode", "human", mode, "A developer",
                   "The assigned developer implements the approved plan in their own session and opens the pull request.")
             + radio("coding_mode", "auto", mode, "The coding agent",
                     "It implements the plan in a sandbox; the host pushes the branch and opens the pull request."))
    designs = (radio("design_mode", "paper", design, "Paper", "Artboards on a design workstation.")
               + radio("design_mode", "html", design, "HTML prototypes",
                       "Prototypes and screenshots on the runner, no Paper seat needed."))
    out = [head]
    if error:
        out.append(f"<div class='notice' role='alert'><b>Not started.</b> {H(error)}</div>")
    payload = json.dumps({"repos": data, "today": today, "prefixes": list(prefixes)}).replace("</", "<\\/")
    out.append(
        "<form method='post' action='/new' class='newwork' id='newwork'>"
        "<fieldset><legend>Repository</legend><div class='frow'>"
        f"<label class='fld'><span>Product repository</span><select name='repo_id' required>{repo_opts}</select></label>"
        "</div>"
        f"<p class='hint'><span id='repo-status'>{H(sc['status'])}</span> · "
        f"<a id='repo-link' href='/repos/{H(quote(sel['id']))}'>see its checks</a> · "
        "<a href='/repos#connect'>connect another repository</a></p>"
        f"<label class='checkline' id='dogfood-line'{'' if sc['factory'] else ' hidden'}>"
        f"<input type='checkbox' name='dogfood' value='1'{' checked' if fields.get('dogfood') else ''}> "
        "<span>This run changes the factory itself (dogfood). Its branch and pull request land in "
        "Lantern's own repository.</span></label></fieldset>"
        "<fieldset><legend>The work</legend>"
        "<div class='frow'><label class='fld wide'><span>Title <em>two to five words; it names the run, "
        "the brief and the branch</em></span>"
        f"<input type='text' name='title' required maxlength='80' autocomplete='off' value='{H(fields.get('title', ''))}'></label></div>"
        "<div class='frow'><label class='fld wide'><span>Problem <em>who has it and why it matters, in "
        "your words</em></span>"
        f"<textarea name='problem' required rows='4'>{H(fields.get('problem', ''))}</textarea></label></div>"
        "<div class='frow'><label class='fld wide'><span>Must-haves <em>optional, one per line; they seed "
        "the acceptance criteria</em></span>"
        f"<textarea name='must_haves' rows='3'>{H(fields.get('must_haves', ''))}</textarea></label></div>"
        "</fieldset>"
        "<fieldset><legend>Branches</legend><div class='frow'>"
        "<label class='fld'><span>Base branch <em>what the run branches from and the pull request "
        f"targets</em></span><select name='base_branch'>{base_opts}</select></label>"
        f"<label class='fld'><span>Work lands on</span><select name='working_branch'>{work_opts}</select></label>"
        "</div></fieldset>"
        f"<fieldset><legend>Who writes the code</legend><div class='frow'>{modes}</div>"
        f"<p class='hint' id='gate-hint'{'' if mode == 'auto' and not sc['gate'] else ' hidden'}>This "
        "repository has no quality gate yet. Automatic coding stops before its first turn until "
        "<code>lantern.toml</code> with a test command is merged into the base branch.</p></fieldset>"
        f"<fieldset><legend>Design</legend><div class='frow'>{designs}</div></fieldset>"
        "<p class='dest-preview' id='preview' aria-live='polite'>"
        f"Run <code id='pv-run'>feat-{today}-…</code>. Work lands on <code id='pv-branch'>feat/{today}-…</code>, "
        f"from <code id='pv-base'>{H(base)}</code> in <b id='pv-repo'>{H(sc['name'])}</b>; "
        "<span id='pv-pr'>a pull request opens after coding</span>. A human merges it.</p>"
        "<button class='btn primary'>Start run</button></form>"
        f"<script type='application/json' id='newwork-data'>{payload}</script>"
        "<script>" + NEW_JS + "</script>")
    return "".join(out)


# Keeps the preview honest while the form is filled in: the run id and branch are the
# ones pipeline.py will derive (brief_composer.slugify, mirrored), and the base and
# working-branch options follow the repository picked. Without JavaScript the form still
# posts, and the server derives the same names.
NEW_JS = """
(function () {
  var f = document.getElementById('newwork'); if (!f) return;
  var D = JSON.parse(document.getElementById('newwork-data').textContent);
  var el = function (id) { return document.getElementById(id); };
  function slug(t) {
    var s = (t || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
    if (s.length <= 40) return s || 'idea';
    var cut = s.slice(0, 41);
    cut = cut.slice(1).indexOf('-') >= 0 ? cut.slice(0, cut.lastIndexOf('-')) : s.slice(0, 40);
    return cut.replace(/^-+|-+$/g, '') || 'idea';
  }
  function fill(select, values, selected, blank) {
    while (select.options.length) select.remove(0);
    if (blank) select.add(new Option(blank, '', false, false));
    values.forEach(function (v) { select.add(new Option(v, v, v === selected, v === selected)); });
  }
  function repo() { return D.repos[f.elements['repo_id'].value]; }
  function refresh() {
    var r = repo(); if (!r) return;
    var s = slug(f.elements['title'].value), work = f.elements['working_branch'].value;
    var base = f.elements['base_branch'].value || r.base;
    var picked = f.querySelector('input[name=coding_mode]:checked');
    var auto = picked && picked.value === 'auto';
    el('pv-run').textContent = 'feat-' + D.today + '-' + s;
    el('pv-branch').textContent = work || ('feat/' + D.today + '-' + s);
    el('pv-base').textContent = base;
    el('pv-repo').textContent = r.name;
    el('pv-pr').textContent = r.kind === 'local' ? 'the branch lands in the checkout, with no pull request'
      : !auto ? 'the developer pushes it and opens a pull request into ' + base
      : r.kind === 'github' ? 'the host pushes it and opens a pull request into ' + base
      : 'the host pushes it; open the review on your git host';
    el('dogfood-line').hidden = !r.factory;
    el('gate-hint').hidden = !(auto && !r.gate);
  }
  f.elements['repo_id'].addEventListener('change', function () {
    var r = repo(); if (!r) return;
    var branches = r.branches.length ? r.branches : [r.base];
    fill(f.elements['base_branch'], branches, r.base);
    fill(f.elements['working_branch'], branches.filter(function (b) {
      return D.prefixes.some(function (p) { return b.indexOf(p) === 0; });
    }), '', 'A new branch for this run');
    el('repo-status').textContent = r.status;
    el('repo-link').href = '/repos/' + encodeURIComponent(f.elements['repo_id'].value);
    refresh();
  });
  f.addEventListener('input', refresh);
  f.addEventListener('change', refresh);
  refresh();
})();
"""
