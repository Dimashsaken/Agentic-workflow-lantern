"""Readable lifecycle over the real pipeline, separate from execution history.

Run position is authoritative. Old downstream executions remain history after
rework; a successful agent call alone does not complete a multi-agent stage.
"""

import json
from urllib.parse import urlencode

from intake import BUG_STAGES, is_bug_run
from pipeline import FEATURE_STAGES
from lanes import role_for, seconds_of
from ui import H, dur


PHASES = {
    "00-story": ("Story", "Researcher → story writer", "Map the codebase and agree on acceptance criteria."),
    "01-ui-ux": ("Design", "UI/UX", "Choose the user flow and prepare the design handoff."),
    "02-pre-coding": ("Plan", "Pre-coding", "Review the implementation plan and any schema changes."),
    "03-coding": ("Code", "Developer / coding agents → reviewer", "Implement, run the code checks, and review the pull request."),
    "04-qa-dev": ("QA dev", "QA", "Exercise the feature and record evidence against the criteria."),
    "05-post-coding": ("Validate", "Post-coding → validator", "Review the changes and verify every acceptance criterion."),
    "06-security": ("Security", "Security → human deploy", "Review security risks before a human deploys to staging."),
    "07-qa-staging": ("QA staging", "QA → human sign-off", "Test on staging and request production sign-off."),
    "01-triage": ("Triage", "Debug", "Classify the report and check for duplicates."),
    "02-repro": ("Reproduce", "Debug", "Reproduce the bug and capture a regression test."),
    "03-root-cause": ("Root cause", "Debug", "Find the cause and scope the fix."),
    "05-regression": ("Regression", "QA", "Verify the fix and run the regression checks."),
    "06-postmortem": ("Learn", "Debug", "Record what escaped and what should change."),
}
GATES = {
    "story_signoff": "Story approval", "ux_signoff": "Design approval",
    "plan_signoff": "Plan approval", "code_complete": "Code review / approval",
    "staging_deploy": "Human deploy to staging", "prod_signoff": "Production sign-off",
    "triage_signoff": "Triage approval", "repro_signoff": "Reproduction approval",
}


def directory(stage):
    return stage.split(".", 1)[0]


def build(run, execs=(), approvals=(), events=()):
    bug = is_bug_run(run["id"])
    table = BUG_STAGES if bug else FEATURE_STAGES
    dirs = list(dict.fromkeys(s[1] for s in table))
    current = directory(run["current_stage"])
    if current not in dirs:
        dirs.append(current)
    index = dirs.index(current)
    pending = sorted((a for a in approvals if a["status"] == "pending"), key=lambda a: a["requested_at"])
    reworks = []
    for event in sorted(events, key=lambda e: e["at"]):
        if event["type"] != "run_reworked":
            continue
        data = event["data"]
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (ValueError, TypeError):
                continue
        if isinstance(data, dict) and all(isinstance(data.get(k), str) and data[k] for k in ("from", "to")):
            reworks.append(dict(data, at=event["at"]))
    phases = []
    for i, key in enumerate(dirs):
        attempts = sorted((e for e in execs if directory(e["stage"]) == key), key=lambda e: (e["started_at"], e["id"]))
        optional = bug and key == "02-pre-coding"
        label, owner, description = PHASES.get(key, (key, "Unmapped stage", "Inspect the execution details for this stage."))
        if bug and key == "03-coding":
            label = "Fix"
        if i == index and pending:
            state, status = "review", "Needs you"
        elif i > index and run["status"] in ("done", "cancelled"):
            state, status = "future", "Not reached"
        elif run["status"] == "done":
            state, status = ("past", "Passed") if attempts else ("unknown", "No execution record")
        elif i == index:
            state, status = {
                "failed": ("failed", "Stopped"), "executing": ("current", "Running"),
                "waiting_gate": ("review", "Awaiting review"), "cancelled": ("unknown", "Cancelled"),
            }.get(run["status"], ("current", "Queued"))
        elif i < index:
            state, status = ("past", "Passed") if attempts else ("unknown", "No execution record")
        else:
            state, status = "future", ("Earlier activity" if attempts else "Upcoming")
        if optional and not attempts and i != index and run["status"] not in ("done", "cancelled"):
            state, status = "future", "If needed" if i > index else "Not recorded"
        gate = next((s[3] for s in reversed(table) if s[1] == key and s[3]), None)
        phases.append(dict(key=key, label=label, owner=owner, description=description,
                           state=state, status=status, current=i == index, attempts=attempts,
                           gate=gate, optional=optional))
    active = phases[index]
    nxt = phases[index + 1]["label"] if index + 1 < len(phases) else "Run complete"
    if bug and current == "03-root-cause":
        nxt = "Plan (large fixes) or Fix"
    latest = {e["stage"]: e for e in active["attempts"]}
    cutoff = reworks[-1]["at"] if reworks else None
    live = [e for e in latest.values() if e["status"] == "running"
            and (not cutoff or e["started_at"] >= cutoff)
            and run["status"] == "executing"]
    if run["status"] in ("done", "cancelled") and not pending:
        now = "Run completed" if run["status"] == "done" else "Run cancelled"
        next_text = "No further stages scheduled"
    elif pending:
        now = GATES.get(pending[0]["gate"], pending[0]["gate"])
        next_text = f"After approval → {nxt}"
    elif run["status"] == "failed":
        now, next_text = f"{active['label']} stopped", "Resolve the failure, then retry or rework"
    elif run["status"] == "waiting_gate":
        now, next_text = "Approval record unavailable", "Restore the review before continuing"
    else:
        now = (f"{len(live)} agents running in {active['label']}" if len(live) > 1 else
               f"{role_for(live[0]['stage']).replace('-', ' ').capitalize()} is working" if live else
               "Developer implementation" if current == "03-coding" and dict(run).get("coding_mode") != "auto" else
               f"{active['label']} · waiting for an execution")
        next_text = f"{GATES[active['gate']]} → {nxt}" if active["gate"] else nxt
        if active["optional"]:
            next_text += " · planning applies to large fixes"
    if current not in PHASES and run["status"] not in ("done", "cancelled"):
        next_text = "Inspect the execution history for this stage"
    return dict(phases=phases, current=active, pending=pending, now=now, next=next_text, live=live,
                reworks=reworks, bug=bug, run_id=run["id"])


def mini(model):
    """One accessible, compact route per work item; the entire item is a link."""
    route = " → ".join(p["label"] for p in model["phases"])
    progress = "".join(f"<i class='phase-{p['state']}' title='{H(p['label'] + ': ' + p['status'])}'></i>"
                       for p in model["phases"])
    current = model["current"]
    return (f"<span class='mini-route' role='img' aria-label='{H(route + '. Current: ' + current['label'] + ', ' + current['status'])}'>"
            f"{progress}</span><small class='mini-caption'>{H(current['label'])}"
            f"<span> · {model['phases'].index(current) + 1}/{len(model['phases'])}</span></small>")


def render(model, now, selected=""):
    chosen = next((p for p in model["phases"] if p["key"] == selected), model["current"])
    steps = []
    for i, phase in enumerate(model["phases"]):
        href = f"/run/{model['run_id']}?" + urlencode({"stage": phase["key"]}) + "#lifecycle"
        glyph = "✓" if phase["state"] == "past" else "!" if phase["state"] == "failed" else "◇" if phase["state"] == "review" else str(i + 1)
        steps.append(f"<li class='phase-{phase['state']}{' phase-selected' if phase == chosen else ''}'>"
                     f"<a href='{H(href)}'{' aria-current=step' if phase['current'] else ''}>"
                     f"<span class='phase-node'>{glyph}</span><strong>{H(phase['label'])}</strong>"
                     f"<small>{H(phase['status'])}</small></a></li>")
    loop = ""
    if model["reworks"]:
        event = model["reworks"][-1]
        label = lambda s: PHASES.get(directory(s), (s,))[0]
        loop = (f"<div class='cycle-return'><b>↶ Rework {len(model['reworks'])}</b> "
                f"{H(label(event['from']))} → {H(label(event['to']))}"
                f"<span>{event['at']:%b %d, %H:%M} UTC · {H(str(event.get('note') or 'Sent back for another pass'))}</span></div>")
    rows = []
    # Keep every running agent visible; cap only historical entries.
    running = model["live"] if chosen["current"] else []
    history = [e for e in reversed(chosen["attempts"]) if e not in running][:4]
    for e in running + history:
        phase_name = e["stage"].split(".", 1)[-1] if "." in e["stage"] else role_for(e["stage"])
        name = phase_name.upper() if phase_name in ("api", "ui") else phase_name.replace('-', ' ').capitalize()
        old = bool(model["reworks"] and e["started_at"] < model["reworks"][-1]["at"])
        recorded = " · Earlier cycle" if old else ""
        status = e["status"].capitalize() if e["status"] != "running" or e in running else "Recorded running"
        rows.append(f"<a class='phase-execution' data-drawer data-k href='/run/{H(model['run_id'])}/exec/{e['id']}' "
                    f"title='Started {e['started_at']:%b %d, %H:%M} UTC'>"
                    f"<span><strong>{H(name)}</strong>"
                    f"<small>{H(role_for(e['stage']))} · Attempt {e['attempt']}{recorded}</small></span>"
                    f"<span>{H(status)}</span><time>{H(dur(seconds_of(e, now)))}</time><span>↗</span></a>")
    empty = ("This stage has not started. Its executions will appear here." if chosen["state"] == "future" and not chosen["attempts"]
             else "No execution recorded for this stage.")
    gate = (f"<span class='phase-gate'>◇ {H(GATES[chosen['gate']])}</span>" if chosen["gate"] else "")
    if chosen["current"] and model["pending"]:
        gate = f"<a class='phase-gate' href='#gate-{model['pending'][0]['id']}'>Open review →</a>"
    evidence = (f"<a class='lnk' href='#files-{H(chosen['key'])}'>Reports &amp; files →</a>"
                if chosen["attempts"] or chosen["current"] else "")
    return (f"<section class='lifecycle' id='lifecycle' aria-label='Run lifecycle'>"
            f"<div class='lifecycle-heading'><h2>{'Bug lifecycle' if model['bug'] else 'Feature lifecycle'}</h2>"
            "<span>Select a stage to inspect its work</span></div>"
            f"<ol class='phase-path'>{''.join(steps)}</ol>{loop}"
            f"<div class='handoff'><div><span>Happening now</span><strong>{H(model['now'])}</strong></div>"
            f"<span class='handoff-arrow' aria-hidden='true'>→</span><div><span>Up next</span><strong>{H(model['next'])}</strong></div></div>"
            f"<div class='phase-inspector'><div class='phase-heading'><div><h3>{H(chosen['label'])}"
            f"<small>{H(chosen['owner'])}</small></h3><p>{H(chosen['description'])}</p></div>{gate}</div>"
            f"{''.join(rows) or '<p class=phase-empty>' + empty + '</p>'}"
            f"<div class='phase-foot'>{evidence}<a class='lnk' href='#execution-history'>Full execution history →</a></div></div></section>")
