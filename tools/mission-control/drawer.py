"""The execution drawer (Mission Control v3, D22): everything one stage execution did.

Opened from a lane bar (fetch → aside) or as its own page (/run/<id>/exec/<n>): the
ledger row, the compiled system prompt and kickoff, the tool-call timeline, the report,
the typed envelope with its validation result, gate.md when the coding gate ran, the
memory entries this execution appended, and the loop actions — retry and rework-to —
posted server-side to the pipeline functions. Approvals stay human: the drawer never
decides a gate.

The data half (load_execution) reads the run folder and takes the DB rows as inputs;
the HTML half (render_drawer) renders the model. Tested by test_drawer.py from a
fixture trace file, no database.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import factory
from pipeline import REWORK_TARGETS, STAGE_INDEX, est_cost_usd
from ui import H, chip, dur, fmt_int, fmt_money, json_block

from lanes import STATUS_LABEL, role_for, seconds_of, tier_of

TRACE_NOTE = ("No trace file for this execution. Traces are written for every execution "
              "since D22 (2026-09-08); earlier executions carry only the ledger row, the "
              "report and the run folder.")


def _g(row, key, default=None):
    try:
        v = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if v is None else v


def load_trace(stage_root: Path, execution_key: str) -> dict | None:
    """The trace for one execution from <stage-dir>/trace/, by filename first, then
    by the key inside each file."""
    tdir = stage_root / factory.TRACE_DIR
    direct = tdir / factory.trace_filename(execution_key)
    candidates = [direct] if direct.is_file() else (sorted(tdir.glob("*.json")) if tdir.is_dir() else [])
    for p in candidates:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("kind") == "trace" and (
                p == direct or data.get("execution_key") == execution_key):
            return data
    return None


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_execution(run, e, run_root: Path, memory_rows, now: datetime,
                   validate=factory.check_envelope) -> dict:
    """The drawer model for one stage_executions row `e` of run `run`.

    run_root: workflow/runs/<run-id>; memory_rows: role_memory rows keyed by this
    execution; validate(run_id, stage) → problems for the stage's envelope (the real
    factory.check_envelope by default — tests pass a fake).
    """
    run_id = run["id"]
    stage = e["stage"]
    sdir = stage.split(".", 1)[0]
    stage_root = run_root / sdir
    key = _g(e, "idempotency_key") or f"{run_id}:{stage}:{_g(e, 'attempt', 1)}"
    seconds = seconds_of(e, now)
    inp, cached, outp = _g(e, "input_tokens"), _g(e, "cached_input_tokens"), _g(e, "output_tokens")
    tot = _g(e, "total_tokens")
    model = {
        "run_id": run_id, "exec_id": e["id"], "stage": stage, "dir": sdir,
        "phase": stage.split(".", 1)[1] if "." in stage else "",
        "role": role_for(stage), "tier": tier_of(stage),
        "attempt": _g(e, "attempt", 1), "status": e["status"], "runner": _g(e, "runner", "ec2"),
        "started_at": e["started_at"], "finished_at": _g(e, "finished_at"),
        "seconds": seconds, "model": _g(e, "model"), "requests": _g(e, "requests"),
        "input_tokens": inp, "cached_input_tokens": cached, "output_tokens": outp,
        "total_tokens": tot, "metered": tot is not None,
        "cost": est_cost_usd(inp, cached, outp, _g(e, "model")),
        "error": _g(e, "error", "") or "", "execution_key": key,
        "trace": load_trace(stage_root, key),
        "report": _read(stage_root / "report.md"),
        "envelope": None, "gate": None, "gate_md": None, "memory": [],
        "actions": {"retry": False, "rework_to": []},
    }
    spec = factory.ENVELOPES.get(stage)
    if spec:
        kind, json_name, md_name = spec
        data = _json(stage_root / json_name)
        problems = validate(run_id, stage)
        model["envelope"] = {"kind": kind, "file": f"{sdir}/{json_name}", "twin": f"{sdir}/{md_name}",
                             "data": data, "present": data is not None,
                             "problems": list(problems), "valid": data is not None and not problems}
    gate = _json(stage_root / factory.GATE_FILE)
    if isinstance(gate, dict):
        model["gate"] = {"data": gate, "mine": gate.get("execution_key") == key,
                         "passed": bool(gate.get("passed")), "round": gate.get("round"),
                         "results": gate.get("results", [])}
        model["gate_md"] = _read(stage_root / "gate.md")
    model["memory"] = [{"entry": _g(m, "entry", ""), "created_at": _g(m, "created_at")}
                       for m in (memory_rows or [])]
    # Loop actions (D17 primitives). Retry re-queues a FAILED run at its current stage;
    # rework sends a failed or waiting run back to an earlier REWORK_TARGETS stage.
    cur_i = STAGE_INDEX.get(run["current_stage"], -1)
    if run["status"] == "failed":
        model["actions"]["retry"] = True
    if run["status"] in ("failed", "waiting_gate"):
        model["actions"]["rework_to"] = [t for t in REWORK_TARGETS if STAGE_INDEX.get(t, 99) < cur_i]
    return model


# ── rendering ────────────────────────────────────────────────────────────────

def _when(ts) -> str:
    return f"{ts:%b %d %H:%M:%S}" if ts else "—"


def _tool_table(calls: list[dict]) -> str:
    if not calls:
        return "<p class='dnote'>The agent made no tool calls in this execution.</p>"
    rows = []
    for c in calls:
        secs = f"{c['seconds']:.1f}s" if isinstance(c.get("seconds"), (int, float)) else "—"
        out_chars = c.get("output_chars") or 0
        size = fmt_int(out_chars) + " ch" if c.get("output") is not None else "no output"
        cut_a = (f" … +{fmt_int(c['args_chars'] - len(c['args']))} ch"
                 if c.get("args_chars", 0) > len(c.get("args") or "") else "")
        cut_o = (f"\n… +{fmt_int(out_chars - len(c['output']))} ch not kept in the trace"
                 if c.get("output") is not None and out_chars > len(c["output"]) else "")
        rows.append(
            f"<tr class='trow' title='click for arguments and output'>"
            f"<td class='n'>{c['order']}</td><td class='nm'>{H(c['name'])}</td>"
            f"<td class='a'>{H(c.get('args') or '')}</td><td class='r'>{H(size)}</td>"
            f"<td class='r'>{H(secs)}</td></tr>"
            f"<tr class='tout'><td colspan='5'>"
            f"<pre>args (turn {c.get('turn', 1)}): {H(c.get('args') or '')}{H(cut_a)}</pre>"
            + (f"<pre>{H(c['output'])}{H(cut_o)}</pre>" if c.get("output") is not None else "")
            + "</td></tr>")
    return (f"<table class='tcalls'><tr><th>#</th><th>tool</th><th>arguments</th>"
            f"<th class='r'>result size</th><th class='r'>seconds</th></tr>{''.join(rows)}</table>"
            "<p class='dnote'>Per-call timing needs a streamed run; the SDK's final result "
            "carries order and payloads only — the ledger row above has the wall time.</p>")


def render_drawer(m: dict, render_markdown, stage_meta: dict, fragment: bool = True) -> str:
    run_id = m["run_id"]
    st = STATUS_LABEL.get(m["status"], (m["status"], ""))
    name = stage_meta.get(m["dir"], (m["dir"],))[0]
    tr = m["trace"]
    head = (f"<div class='dhead'><div><h2>{H(m['stage'])} · attempt {m['attempt']}</h2>"
            f"<div class='dsub'>{chip(*st)}{chip(m['tier'], 'tier')}<span>{H(m['role'])} · "
            f"{H(m['runner'])} · {H(name)}</span>"
            f"<span><a href='/run/{H(run_id)}' style='color:var(--dawn-3)'>{H(run_id)}</a></span>"
            f"</div></div>"
            + ("<button class='tbtn dclose' type='button' title='Esc'>close ✕</button>" if fragment
               else f"<a class='tbtn dclose' href='/run/{H(run_id)}'>← run</a>")
            + "</div>")
    if m["metered"]:
        pct = round((m["cached_input_tokens"] or 0) / m["input_tokens"] * 100) if m["input_tokens"] else 0
        tok = (f"{fmt_int(m['total_tokens'])}<small> · {fmt_int(m['input_tokens'])} in "
               f"({pct}% cached) · {fmt_int(m['output_tokens'])} out · {m['requests'] or '?'} req</small>")
        money = fmt_money(m["cost"])
    else:
        tok, money = "unmetered<small> · no usage line</small>", "—"
    grid = (f"<div class='dgrid'>"
            f"<div><div class='k'>Started</div><div class='v'>{H(_when(m['started_at']))}</div></div>"
            f"<div><div class='k'>Finished</div><div class='v'>{H(_when(m['finished_at']))}</div></div>"
            f"<div><div class='k'>Duration</div><div class='v'>{H(dur(m['seconds']))}</div></div>"
            f"<div><div class='k'>Model</div><div class='v'>{H(m['model'] or '—')}"
            f"<small> · {H(m['tier'])} tier</small></div></div>"
            f"<div><div class='k'>Tokens</div><div class='v'>{tok}</div></div>"
            f"<div><div class='k'>Est. cost</div><div class='v'>{H(money)}</div></div>"
            f"<div><div class='k'>Execution key</div><div class='v'><small>{H(m['execution_key'])}</small></div></div>"
            f"</div>")
    parts = [head, grid]
    if m["error"]:
        parts.append(f"<div class='scard err' style='margin:0'>{H(m['error'][:1200])}</div>")

    # actions
    acts = []
    if m["actions"]["retry"]:
        acts.append(f"<form method='post' action='/run/{H(run_id)}/retry' "
                    f"onsubmit=\"return confirm('Re-queue {H(run_id)} at its current stage?')\">"
                    f"<button class='btn primary sm'>Retry — fresh attempt, same session memory</button></form>")
    if m["actions"]["rework_to"]:
        opts = "".join(f"<option value='{H(t)}'>{H(t)}</option>" for t in m["actions"]["rework_to"])
        acts.append(f"<form method='post' action='/run/{H(run_id)}/rework' "
                    f"onsubmit=\"return confirm('Send {H(run_id)} back? Pending approvals expire.')\">"
                    f"<select name='to_stage' style='min-width:170px'>{opts}</select>"
                    f"<input type='text' name='note' placeholder='why — lands in gate-decisions.md'>"
                    f"<button class='btn sm'>Rework to this stage</button></form>")
    if acts:
        parts.append(f"<div class='dacts'>{''.join(acts)}<span class='hint'>Server-side calls to the "
                     "pipeline's retry / rework primitives, recorded with your name. Approvals are "
                     "never decided here.</span></div>")
    elif not fragment or True:
        parts.append("<p class='dnote' style='margin-top:10px'>No loop action applies: retry needs a "
                     "failed run, rework a failed or waiting one with an earlier stage to return to.</p>")

    # prompt + kickoff
    if tr:
        cut = (f" · {fmt_int(tr.get('instructions_chars', 0) - len(tr.get('instructions') or ''))} ch cut"
               if tr.get("instructions_chars", 0) > len(tr.get("instructions") or "") else "")
        red = tr.get("redaction") or {}
        rnote = ("QA target section redacted · " if red.get("qa_target_dropped") else "") + \
                "secrets masked before the file was written"
        parts.append(
            f"<div class='dsect'><h3>Compiled system prompt <small>{fmt_int(tr.get('instructions_chars', 0))} ch{cut} · "
            f"{H(rnote)}</small></h3>"
            f"<details class='dfold'><summary>Show the prompt the agent ran with</summary>"
            f"<div class='inner'><pre class='prompt'>{H(tr.get('instructions') or '')}</pre></div></details>"
            f"<details class='dfold'><summary>Kickoff (the first user turn)</summary>"
            f"<div class='inner'><pre class='prompt'>{H(tr.get('kickoff') or '')}</pre></div></details></div>")
        calls = tr.get("tool_calls") or []
        parts.append(f"<div class='dsect'><h3>Tool calls <small>{len(calls)} in "
                     f"{len(tr.get('turns') or [])} turn(s)</small></h3>{_tool_table(calls)}</div>")
        turns = tr.get("turns") or []
        if len(turns) > 1:
            rows = "".join(
                f"<tr><td class='n'>{t.get('turn')}</td><td>{fmt_int((t.get('usage') or {}).get('total_tokens'))} tok</td>"
                f"<td class='a'>{H((t.get('final_output') or '')[:160])}</td></tr>" for t in turns)
            parts.append(f"<div class='dsect'><h3>Turns <small>build turn + fix rounds</small></h3>"
                         f"<table class='tcalls'><tr><th>#</th><th>tokens</th><th>final output</th></tr>{rows}</table></div>")
    else:
        parts.append(f"<div class='dsect'><h3>Compiled prompt &amp; tool calls</h3><p class='dnote'>{H(TRACE_NOTE)}</p></div>")

    # report
    if m["report"]:
        parts.append(f"<div class='dsect'><h3>Report <small>{H(m['dir'])}/report.md</small></h3>"
                     f"<details class='dfold' open><summary>Rendered</summary>"
                     f"<div class='inner prose'>{render_markdown(m['report'])}</div></details></div>")
    else:
        parts.append(f"<div class='dsect'><h3>Report</h3><p class='dnote'>No {H(m['dir'])}/report.md on disk.</p></div>")

    # envelope
    env = m["envelope"]
    if env:
        if not env["present"]:
            vres = chip("missing", "blocked") + f" <span>{H(env['file'])} is not on disk</span>"
        elif env["valid"]:
            vres = chip("valid", "ok") + f" <span>{H(env['file'])} passed factory.check_envelope</span>"
        else:
            vres = chip("invalid", "blocked") + f" <span>{len(env['problems'])} problem(s)</span>"
        probs = ("<ul>" + "".join(f"<li>{H(p)}</li>" for p in env["problems"]) + "</ul>") if env["problems"] else ""
        parts.append(f"<div class='dsect'><h3>Envelope <small>{H(env['kind'])}.json · the typed contract</small></h3>"
                     f"<div class='vres'>{vres}</div>{probs}"
                     + (f"<details class='dfold'><summary>Pretty JSON</summary><div class='inner'>"
                        f"{json_block(env['data'])}</div></details>" if env["present"] else "")
                     + "</div>")

    # gate
    if m["gate"]:
        g = m["gate"]
        owner = ("this execution" if g["mine"] else
                 f"another attempt ({H(str(g['data'].get('execution_key')))}) — did not run for this one")
        verdict = chip("green", "ok") if g["passed"] else chip("red", "blocked")
        checks = "".join(f"<tr><td class='nm'>{H(r.get('name', ''))}</td><td>{'pass' if r.get('passed') else 'FAIL'}</td>"
                         f"<td class='r'>{r.get('exit')}</td><td class='r'>{r.get('seconds')}s</td></tr>"
                         for r in g["results"])
        parts.append(f"<div class='dsect'><h3>Quality gate <small>gate.json · round {g['round']} · {owner}</small></h3>"
                     f"<div class='vres'>{verdict}</div>"
                     f"<table class='tcalls'><tr><th>check</th><th>result</th><th class='r'>exit</th><th class='r'>s</th></tr>{checks}</table>"
                     + (f"<details class='dfold'><summary>gate.md</summary><div class='inner prose'>"
                        f"{render_markdown(m['gate_md'])}</div></details>" if m["gate_md"] else "")
                     + "</div>")

    # memory
    if m["memory"]:
        items = "".join(f"<li><span class='tm'>{_when(x['created_at'])}</span> — {H(x['entry'])}</li>"
                        for x in m["memory"])
        parts.append(f"<div class='dsect'><h3>Memory appended <small>{len(m['memory'])} row(s) keyed by this execution</small></h3>"
                     f"<ul class='memlist'>{items}</ul></div>")
    else:
        parts.append("<div class='dsect'><h3>Memory appended</h3><p class='dnote'>No role_memory row is keyed "
                     "by this execution — for a succeeded execution that means the postcondition ran "
                     "before D10's keyed check, or the row was consolidated.</p></div>")
    return f"<div class='dwrap'>{''.join(parts)}</div>"
