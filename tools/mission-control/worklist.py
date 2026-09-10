"""A compact, read-only queue. Decisions happen alongside their evidence."""

from urllib.parse import urlencode

from ui import H, ago, chip
import lifecycle


FILTERS = (("active", "Active"), ("review", "Needs review"),
           ("closed", "Completed"), ("all", "All work"))


def items(snap, now, *, stage_dir, stage_meta, gate_meta, short_name, blocked,
          report_verdict):
    pending = {}
    for approval in sorted(snap["pend"], key=lambda a: a["requested_at"]):
        pending.setdefault(approval["run_id"], approval)
    result = []
    executions = {}
    for execution in snap.get("latest_executions", ()):
        executions.setdefault(execution["run_id"], []).append(execution)
    for run in snap["runs"]:
        rid = run["id"]
        approval = pending.get(rid)
        stage = stage_dir.get(run["current_stage"], run["current_stage"])
        stage_label = stage_meta.get(stage, (stage.replace("-", " "),))[0].split(" · ", 1)[-1]
        verdict = report_verdict(rid, stage) if run["status"] not in ("done", "cancelled") else None
        when = run["updated_at"]
        href = f"/run/{rid}"
        stale = False
        if approval:
            state, label, tone = "review", "Needs review", "gate"
            detail = gate_meta.get(approval["gate"], (approval["gate"],))[0]
            when = approval["requested_at"]
            stale = (now - when).total_seconds() > 86400
            if verdict == "BLOCKED":
                detail += " · Report says blocked"
                tone = "blocked"
            href += f"#gate-{approval['id']}"
        elif run["status"] in ("done", "cancelled"):
            state, label, tone = "closed", ("Completed" if run["status"] == "done" else "Cancelled"), ""
            detail = stage_label
        elif run["status"] == "failed" or verdict == "BLOCKED":
            state, label, tone = "blocked", "Blocked", "blocked"
            detail = f"{stage_label} · Open to investigate"
        elif blocked(run, snap["online"]):
            state, label, tone = "blocked", "Blocked", "warn"
            detail = "Design workstation is offline"
        elif run["status"] == "waiting_gate":
            state, label, tone = "blocked", "Needs attention", "warn"
            detail = "Review is missing · Open to investigate"
        elif run["status"] == "executing":
            state, label, tone = "running", "Running", "ok"
            detail = stage_label
        else:
            state, label, tone = "queued", "Queued", ""
            detail = stage_label
        title = short_name(rid).replace("-", " ")
        title = title[:1].upper() + title[1:]
        repo = (dict(run).get("product_repo") or "").replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        cycle = lifecycle.build(run, executions.get(rid, ()), [approval] if approval else [])
        if state in ("running", "queued"):
            detail = cycle["now"]
        result.append(dict(id=rid, title=title, state=state, label=label, tone=tone,
                           detail=detail, href=href, when=when, stale=stale, repo=repo,
                           cycle=cycle,
                           owner=run["created_by"], kind="Bug" if rid.startswith("bug-") else "Feature"))
    order = {"review": 0, "blocked": 1, "running": 2, "queued": 3, "closed": 4}
    return sorted(result, key=lambda r: (order[r["state"]],
                  r["when"].timestamp() if r["state"] == "review" else -r["when"].timestamp(), r["id"]))


def render(rows, now, *, selected="active", query="", path="/"):
    selected = selected if selected in dict(FILTERS) else "active"
    query = query.strip()
    def included(row, key):
        return (key == "all" or (key == "active" and row["state"] != "closed")
                or (key == "review" and row["state"] == "review")
                or (key == "closed" and row["state"] == "closed"))
    tabs = []
    for key, label in FILTERS:
        count = sum(included(r, key) for r in rows)
        url = path + "?" + urlencode({"filter": key, "q": query})
        tabs.append(f"<a href='{H(url)}'{' class=on aria-current=page' if selected == key else ''}>"
                    f"{label}<span>{count}</span></a>")
    visible = [r for r in rows if included(r, selected) and query.casefold() in
               " ".join(str(r[k]) for k in ("id", "title", "repo", "owner", "detail")).casefold()]
    content = []
    last_group = None
    for row in visible:
        group = ("Needs attention" if row["state"] in ("review", "blocked") else
                 "Completed" if row["state"] == "closed" else "In progress")
        if group != last_group:
            content.append(f"<h2 class='work-group'>{group}</h2>")
            last_group = group
        meta = " · ".join(x for x in (row["kind"], row["repo"] or row["owner"]) if x)
        age_label = "Waiting " if row["state"] == "review" else "Updated "
        age = ago((now - row["when"]).total_seconds())
        content.append(
            f"<a class='work-row' data-k href='{H(row['href'])}'>"
            f"<span class='work-symbol state-{row['state']}' aria-hidden='true'>"
            f"{'◇' if row['kind'] == 'Feature' else '○'}</span>"
            f"<span class='work-name'><strong>{H(row['title'])}</strong><span>{H(meta)}</span></span>"
            f"<span class='work-detail'>{lifecycle.mini(row['cycle'])}<span>{H(row['detail'])}</span></span>"
            f"<span class='work-state'>{chip(row['label'], row['tone'])}</span>"
            f"<time class='work-age{' overdue' if row['stale'] else ''}' datetime='{row['when'].isoformat()}' "
            f"title='{H(age_label + age + ' · ' + row['when'].strftime('%b %d %H:%M UTC'))}'>"
            f"{'Waiting ' if row['stale'] else ''}{age}</time>"
            f"<span class='work-arrow' aria-hidden='true'>↗</span></a>")
    if not visible:
        if query:
            title, detail = "No matching work", "Try another name, repository, or owner."
            action = f"<a class='btn' href='{path}?filter={selected}'>Clear search</a>"
        elif selected == "review":
            title, detail, action = "You're all caught up", "Nothing needs your review right now.", ""
        elif selected == "closed":
            title, detail, action = "No completed work yet", "Finished and cancelled runs will appear here.", ""
        else:
            title, detail = "A clear start", "Describe what you want to build. Lantern will help you take it from there."
            action = "<a class='lnk' href='/chat'>Start a conversation →</a>"
        content.append(f"<div class='work-empty'><span aria-hidden='true'>◇</span><h2>{title}</h2>"
                       f"<p>{detail}</p>{action}</div>")
    search = (f"<form class='work-search' method='get' action='{path}' role='search'>"
              f"<input type='hidden' name='filter' value='{selected}'>"
              f"<input type='search' name='q' value='{H(query)}' aria-label='Search work' placeholder='Search work…'>"
              f"<button type='submit' aria-label='Search'>↵</button></form>")
    return ("<main class='page work-page' id='main-content'>"
            "<header class='work-heading'><div><span class='eyebrow'>Your workspace</span>"
            "<h1>Work</h1><p>Build, review, and keep things moving.</p></div>"
            "<a class='btn primary' href='/chat'>+ New work</a></header>"
            f"<div class='work-toolbar'><nav class='work-filters' aria-label='Filter work'>{''.join(tabs)}</nav>{search}</div>"
            f"<section class='work-list' aria-label='Work items'>{''.join(content)}</section></main>")
