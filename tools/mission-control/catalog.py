"""The factory catalog (Mission Control v3, D22): what this factory is made of, read-only.

Answers "which roles exist and what are they for, which stages and gates, which model
runs which tier at what effort, what does each product's quality gate run, how good is
the factory on its own evals, and which runs fan out into builders" — from files and the
environment, never from an agent's claim:

  roles        agents/<role>/charter.md (mission), tier_for() (routing), the per-agent
               tool matrix in docs/AGENT-TOOLING.md §6
  stages/gates pipeline.FEATURE_STAGES + the human names Mission Control already uses
  model stack  LANTERN_MODEL_* / LANTERN_EFFORT_* with the fallback chain resolved
  products     <product>/lantern.toml [quality] for every run's product repo + this repo
  evals        tools/evals/REPORT.md when session 3 (D20) has produced one
  builders     02-pre-coding/plan.json `builders` when a plan declares them (D18)

Pure over a repo path + an env mapping; tested by test_catalog.py from fixture files.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Mapping

import factory
from orchestrator import (DEFAULT_EFFORT, EFFORT_LEVELS, MODEL_TIERS, ROLE_FOR_STAGE,
                          TIER_FALLBACK, tier_for)
from pipeline import FEATURE_STAGES
from ui import H, chip

TIER_PURPOSE = {
    "reasoning": "research, scoping, planning, review, security, debug, ui-ux design",
    "coding": "the stage-3 builder in auto mode",
    "fast": "volume execution: QA charter runs, ui-ux divergence",
}
INTENDED_DEPLOYMENT = {"reasoning": "gpt-5.6-terra", "coding": "gpt-5.6-luna", "fast": "gpt-5.6-luna"}
KNOBS = [
    ("LANTERN_EFFORT_CHAT", "reasoning effort for interactive consults (overrides the tier)", ""),
    ("LANTERN_FIX_ROUNDS", "quality-gate fix rounds before a red coding stage fails", "3"),
    ("LANTERN_EXECUTOR", "how stages run: inprocess or docker sandboxes", "inprocess"),
    ("LANTERN_SANDBOX_IMAGE", "sandbox image for docker executions", "lantern-sandbox"),
    ("LANTERN_MAX_CONCURRENCY", "daemon slots on this host", "2"),
    ("LANTERN_STAGE_TIMEOUT_MIN", "wall-clock cap per stage execution (minutes)", "45"),
    ("LANTERN_CODING_TIMEOUT_MIN", "wall-clock cap for a coding execution (minutes)", "120"),
    ("LANTERN_CODING_MAX_TURNS", "agent turns a coding execution may take", "400"),
    ("LANTERN_CODING_BRANCH_PREFIXES", "branch namespace agents may push to (D6)", "feat,fix,proto"),
    ("LANTERN_DAILY_SPEND_ALARM_USD", "daily spend tripwire (alarm, not a block)", "50"),
    ("LANTERN_CREDIT_POOL_USD", "the Azure credit pool the pool alarms measure against", "25000"),
]


def _mission(charter: str) -> str:
    """First paragraph under '## Mission' (or the first prose line), one line, capped."""
    m = re.search(r"^##\s+Mission\s*$(.*?)(?=^##\s|\Z)", charter, re.M | re.S)
    body = m.group(1) if m else charter
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip() and not p.strip().startswith("#")]
    text = " ".join(paras[0].split()) if paras else ""
    return text[:260] + ("…" if len(text) > 260 else "")


def parse_tool_matrix(doc: str) -> dict[str, dict]:
    """docs/AGENT-TOOLING.md §6: | Agent | MCP / CLIs | Credentials (SSM) | May write to |."""
    out: dict[str, dict] = {}
    sect = doc.split("Per-agent connection matrix", 1)[-1]
    for line in sect.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or cells[0].lower() in ("agent", "") or set(cells[0]) <= {"-"}:
            continue
        role = re.sub(r"\s*\(.*?\)", "", cells[0]).strip()
        out[role] = {"tools": cells[1], "credentials": cells[2], "writes": cells[3]}
    return out


def _clean(md: str) -> str:
    """Strip markdown code ticks and bold markers; a lone * (a glob) is content."""
    return re.sub(r"`|\*\*", "", md)


def roles(repo: Path) -> list[dict]:
    matrix = parse_tool_matrix(_safe_read(repo / "docs" / "AGENT-TOOLING.md") or "")
    out = []
    agents = repo / "agents"
    if not agents.is_dir():
        return out
    for d in sorted(agents.iterdir()):
        charter = d / "charter.md"
        if not d.is_dir() or d.name.startswith("_") or not charter.is_file():
            continue
        role = d.name
        stages = [s for s, r in ROLE_FOR_STAGE.items() if r == role]
        tiers = sorted({tier_for(role, s) for s in stages} | {tier_for(role)})
        tool_row = matrix.get(role, {})
        memory = _safe_read(d / "memory.md") or ""
        out.append({
            "role": role, "mission": _mission(_safe_read(charter) or ""),
            "tier": tier_for(role), "tiers": tiers, "stages": stages,
            "tools": _clean(tool_row.get("tools", "")), "credentials": _clean(tool_row.get("credentials", "")),
            "writes": _clean(tool_row.get("writes", "")),
            "memory_entries": sum(1 for ln in memory.splitlines() if ln.lstrip().startswith("- ")),
            "has_skills": (d / "skills.md").is_file(),
        })
    return out


def _safe_read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def model_stack(env: Mapping[str, str]) -> dict:
    tiers = []
    for tier in MODEL_TIERS:
        var = f"LANTERN_MODEL_{tier.upper()}"
        configured = (env.get(var) or "").strip()
        t, resolved, via = tier, configured, None
        while not resolved and t in TIER_FALLBACK:
            t = TIER_FALLBACK[t]
            resolved = (env.get(f"LANTERN_MODEL_{t.upper()}") or "").strip()
            via = t if resolved else None
        raw = (env.get(f"LANTERN_EFFORT_{tier.upper()}") or "").strip().lower()
        effort = raw or DEFAULT_EFFORT[tier]
        effort_note = ""
        if effort in ("default", "none", "off"):
            effort_note = "deployment default"
        elif effort not in EFFORT_LEVELS:
            effort_note = f"invalid → {DEFAULT_EFFORT[tier]}"
            effort = DEFAULT_EFFORT[tier]
        tiers.append({"tier": tier, "var": var, "configured": configured or None,
                      "deployment": resolved or None, "via": via,
                      "effort": effort, "effort_default": not raw, "effort_note": effort_note,
                      "purpose": TIER_PURPOSE[tier], "intended": INTENDED_DEPLOYMENT[tier]})
    knobs = [{"var": v, "what": w, "value": (env.get(v) or "").strip() or None, "default": d}
             for v, w, d in KNOBS]
    prices = {k: env.get(k) for k in ("LANTERN_PRICE_IN_PER_M", "LANTERN_PRICE_CACHED_IN_PER_M",
                                      "LANTERN_PRICE_OUT_PER_M", "LANTERN_PRICE_JSON")}
    return {"tiers": tiers, "knobs": knobs, "prices": prices,
            "endpoint": bool((env.get("AZURE_OPENAI_ENDPOINT") or "").strip())}


def product_quality(repo_ref: str, label: str = "") -> dict:
    """One product's lantern.toml [quality] commands. Remote URLs are not fetched here —
    the coding stage reads the file inside the checkout at run time."""
    entry = {"repo": repo_ref, "label": label or repo_ref, "local": False, "exists": False,
             "commands": [], "timeout_s": None, "source": None, "error": None}
    if re.match(r"^(https?://|git@|ssh://)", repo_ref):
        entry["error"] = "remote repository — its lantern.toml is read inside the checkout at coding time"
        return entry
    root = Path(repo_ref)
    entry["local"] = True
    if not root.is_dir():
        entry["error"] = "path is not a directory on this host"
        return entry
    entry["exists"] = True
    cfg = factory.quality_config(root)
    entry["commands"] = [{"name": n, "command": c} for n, c in cfg["commands"]]
    entry["timeout_s"] = cfg["timeout_s"]
    entry["source"] = cfg.get("source")
    entry["error"] = cfg.get("error")
    return entry


def builders_from_plans(plans: list[tuple[str, Path]]) -> list[dict]:
    """(run_id, plan.json path) → the builders a plan declares (D18), if any."""
    out = []
    for run_id, path in plans:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        blds = data.get("builders") if isinstance(data, dict) else None
        if isinstance(blds, list) and blds:
            out.append({"run_id": run_id, "builders": [b for b in blds if isinstance(b, dict)]})
    return out


def build_catalog(repo: Path, env: Mapping[str, str], product_repos: list[str],
                  stage_meta: dict, gate_meta: dict, plans: list[tuple[str, Path]] | None = None) -> dict:
    stages = []
    for stage, sdir, stype, gate, runner in FEATURE_STAGES:
        stages.append({"stage": stage, "dir": sdir, "type": stype, "runner": runner, "gate": gate,
                       "role": ROLE_FOR_STAGE.get(stage, "developer" if stype == "human" else "?"),
                       "tier": tier_for(ROLE_FOR_STAGE.get(stage, "coding"), stage) if stype == "agent" else None,
                       "name": stage_meta.get(sdir, (sdir, "", ""))[0],
                       "desc": stage_meta.get(sdir, (sdir, "", ""))[2],
                       "gate_title": gate_meta.get(gate, (gate, ""))[0] if gate else None,
                       "gate_desc": gate_meta.get(gate, (gate, ""))[1] if gate else None,
                       "envelope": factory.ENVELOPES.get(stage)})
    products = [product_quality(str(repo), "this repository (dogfood gate)")]
    seen = {str(repo).replace("\\", "/").rstrip("/").lower()}
    for r in product_repos:
        if not r:
            continue
        norm = r.replace("\\", "/").rstrip("/").lower()
        if norm in seen:
            continue
        seen.add(norm)
        products.append(product_quality(r))
    evals = _safe_read(repo / "tools" / "evals" / "REPORT.md")
    return {"roles": roles(repo), "stages": stages, "model_stack": model_stack(env),
            "products": products, "evals": evals,
            "builders": builders_from_plans(plans or [])}


# ── rendering ────────────────────────────────────────────────────────────────

def render_catalog(c: dict, render_markdown) -> str:
    out = []
    # roles
    cards = []
    for r in c["roles"]:
        stages = ", ".join(r["stages"]) if r["stages"] else "consult only"
        cards.append(
            f"<div class='ccard'><div class='cn'>{H(r['role'])}{chip(r['tier'], 'tier')}</div>"
            f"<div class='cm'>{H(r['mission']) or '<i>no mission paragraph in charter.md</i>'}</div>"
            f"<div class='cr'><span title='stage keys'>⟶ {H(stages)}</span></div>"
            + (f"<div class='cr'><span title='tools'>🧰 {H(r['tools'][:140])}</span></div>" if r["tools"] else "")
            + (f"<div class='cr'><span title='may write to'>✎ {H(r['writes'][:120])}</span>"
               f"<span>· {r['memory_entries']} memory entries</span></div>" if r["writes"] else
               f"<div class='cr'><span>{r['memory_entries']} memory entries</span></div>")
            + "</div>")
    out.append(f"<h2 class='sect'>Roles <small class='caps' style='margin-left:8px'>{len(c['roles'])}</small></h2>"
               "<p class='sub'>One agent, one purpose, hard boundaries — from agents/&lt;role&gt;/charter.md, "
               "routed by tier_for(), tools from docs/AGENT-TOOLING.md §6.</p>"
               f"<div class='cat'>{''.join(cards)}</div>")
    # stages + gates
    rows = []
    for s in c["stages"]:
        env = f"<code>{H(s['envelope'][1])}</code>" if s["envelope"] else "<span class='dim'>—</span>"
        gate = (f"<b>{H(s['gate'])}</b><br><span class='dim'>{H(s['gate_title'])}</span>" if s["gate"]
                else "<span class='dim'>advance</span>")
        rows.append(f"<tr><td class='m'>{H(s['stage'])}</td><td>{H(s['name'])}</td>"
                    f"<td class='m'>{H(s['role'])}{' · ' + chip(s['tier'], 'tier') if s['tier'] else ''}</td>"
                    f"<td class='m'>{H(s['runner'])}</td><td>{env}</td><td>{gate}</td></tr>")
    out.append("<h2 class='sect'>Stages and gates</h2><p class='sub'>The fixed pipeline "
               "(pipeline.FEATURE_STAGES): every execution key, who runs it, the typed envelope it "
               "must leave, and the human gate that follows.</p>"
               "<div class='stripwrap'><table class='cattbl'><tr><th>Execution</th><th>Stage</th>"
               f"<th>Role · tier</th><th>Runner</th><th>Envelope</th><th>Gate</th></tr>{''.join(rows)}</table></div>")
    # model stack
    ms = c["model_stack"]
    rows = []
    for t in ms["tiers"]:
        dep = (f"<b>{H(t['deployment'])}</b>" + (f" <span class='dim'>via {H(t['via'])} fallback</span>" if t["via"] else "")
               if t["deployment"] else "<span style='color:var(--danger)'>unset — stages cannot start</span>")
        eff = H(t["effort"]) + (" <span class='dim'>(default)</span>" if t["effort_default"] else "") + \
              (f" <span class='dim'>{H(t['effort_note'])}</span>" if t["effort_note"] else "")
        rows.append(f"<tr><td class='m'>{chip(t['tier'], 'tier')}</td><td>{H(t['purpose'])}</td>"
                    f"<td class='m'>{dep}</td><td class='m'>{eff}</td>"
                    f"<td class='dim'><code>{H(t['var'])}</code> · intended {H(t['intended'])}</td></tr>")
    knobs = "".join(
        f"<tr><td class='m'><code>{H(k['var'])}</code></td><td>{H(k['what'])}</td>"
        f"<td class='m'>{H(k['value']) if k['value'] else '<span class=dim>' + H(k['default'] or 'unset') + ' (default)</span>'}</td></tr>"
        for k in ms["knobs"])
    endpoint = ("Azure OpenAI endpoint configured" if ms["endpoint"]
                else "no AZURE_OPENAI_ENDPOINT in this process — model calls are off here")
    out.append("<h2 class='sect'>Model stack</h2><p class='sub'>Three tiers (D16): the strongest "
               "model thinks and reviews, the cheapest builds. Each tier is one env var with a "
               f"fallback chain coding → fast → reasoning. {H(endpoint)}.</p>"
               "<div class='stripwrap'><table class='cattbl'><tr><th>Tier</th><th>Purpose</th>"
               f"<th>Deployment</th><th>Effort</th><th>Config</th></tr>{''.join(rows)}</table></div>"
               "<h3 class='caps' style='margin:18px 0 0'>Knobs</h3>"
               f"<div class='stripwrap'><table class='cattbl'><tr><th>Variable</th><th>What</th><th>Value</th></tr>{knobs}</table></div>"
               f"<p class='envnote'>Prices per 1M tokens: in {H(ms['prices'].get('LANTERN_PRICE_IN_PER_M') or '4')} · "
               f"cached {H(ms['prices'].get('LANTERN_PRICE_CACHED_IN_PER_M') or '1')} · "
               f"out {H(ms['prices'].get('LANTERN_PRICE_OUT_PER_M') or '20')}"
               f"{' · per-deployment table set' if ms['prices'].get('LANTERN_PRICE_JSON') else ''} — estimates until invoices confirm them.</p>")
    # products
    rows = []
    for p in c["products"]:
        if p["error"]:
            body = f"<span class='dim'>{H(p['error'])}</span>"
        elif p["commands"]:
            body = "<br>".join(f"<b>{H(x['name'])}</b> <code>{H(x['command'])}</code>" for x in p["commands"])
            body += f"<br><span class='dim'>timeout {p['timeout_s']}s · {H(p['source'] or '')}</span>"
        else:
            body = ("<span style='color:var(--warning)'>no lantern.toml [quality] — nothing runs as code after "
                    "the coding agent's turn</span>")
        rows.append(f"<tr><td class='m'>{H(p['label'])}<br><span class='dim'><code>{H(p['repo'])}</code></span></td><td>{body}</td></tr>")
    out.append("<h2 class='sect'>Products and their quality gates</h2><p class='sub'>What runs as code "
               "after every coding turn (D17): each product repo's <code>lantern.toml [quality]</code>. "
               "Red output goes back to the builder for a bounded number of fix rounds.</p>"
               f"<div class='stripwrap'><table class='cattbl'><tr><th>Product</th><th>Commands</th></tr>{''.join(rows)}</table></div>")
    # evals
    if c["evals"]:
        out.append("<h2 class='sect'>Evals</h2><p class='sub'>tools/evals/REPORT.md — the factory measuring "
                   "itself (D20).</p><div class='artbox' style='max-height:560px'><div class='prose'>"
                   f"{render_markdown(c['evals'])}</div></div>")
    else:
        out.append("<h2 class='sect'>Evals</h2><p class='sub'>No <code>tools/evals/REPORT.md</code> yet. When the "
                   "evals suite (D20) produces one, its numbers render here — plan coverage, validator "
                   "agreement, classification accuracy, repro rate.</p>")
    # builders
    if c["builders"]:
        rows = []
        for b in c["builders"]:
            for x in b["builders"]:
                rows.append(f"<tr><td class='m'><a href='/run/{H(b['run_id'])}'>{H(b['run_id'])}</a></td>"
                            f"<td class='m'>{H(str(x.get('name', '?')))}</td>"
                            f"<td><code>{H(', '.join(map(str, x.get('write_scope') or [])))}</code></td>"
                            f"<td class='m'>{H(', '.join(map(str, x.get('tasks') or [])))}</td>"
                            f"<td class='m'>{H(', '.join(map(str, x.get('criteria') or [])))}</td></tr>")
        out.append("<h2 class='sect'>Parallel builders</h2><p class='sub'>Plans that fan stage 3 out into "
                   "scoped builders (D18): each confined to its write scope, merged by the host.</p>"
                   "<div class='stripwrap'><table class='cattbl'><tr><th>Run</th><th>Builder</th><th>Write scope</th>"
                   f"<th>Tasks</th><th>Criteria</th></tr>{''.join(rows)}</table></div>")
    else:
        out.append("<h2 class='sect'>Parallel builders</h2><p class='sub'>No plan declares <code>builders</code> "
                   "yet. When a task plan splits stage 3 into scoped builders (D18), they are listed here "
                   "with their write scopes.</p>")
    return "".join(out)
