"""Chat + Agents screens for Mission Control (docs/CHAT.md, D13).

The web face of consult mode (D11): talk to any fleet role, any user-created
agent, or the Lantern orchestrator, with past-chat history, live tool activity
over SSE, and every turn metered into the token ledger. All model work happens
in tools/azure-runner/chat_service.py; this module is routes + rendering only.

Wiring: app.py calls setup(...) with its own helpers (pool, auth, page shell)
and includes `router` — chat.py imports nothing from app.py, so there is no
import cycle and the login/gate rules stay defined in exactly one place.
"""

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

import chat_service as cs
from chat_service import BUS
from pipeline import est_cost_usd
from ui import H, ago, chip, fmt_int, fmt_money

router = APIRouter()
deps: dict = {}     # get_pool, current_user, page, render_markdown — set by app.setup
SSE_MAX_SECONDS = 300


def setup(**kw) -> APIRouter:
    deps.update(kw)
    return router


async def _pool():
    return await deps["get_pool"]()


def _user(request: Request) -> str | None:
    return deps["current_user"](request)


async def on_startup() -> None:
    """Upgrade the schema and fail any turn a previous process left 'running'."""
    p = await _pool()
    async with p.acquire() as conn:
        await cs.ensure_chat_tables(conn)
        await cs.reap_stale_turns(conn, BUS)


async def on_shutdown() -> None:
    """Release every open SSE stream, and make sure a turn the dying process
    cancels records itself as interrupted, not as a developer's Stop."""
    cs.SHUTTING_DOWN = True
    BUS.close_all()


# ── data helpers ─────────────────────────────────────────────────────────────

async def session_rows(p, limit: int = 60):
    """Sidebar data: sessions + per-session ledger + live flag, newest first."""
    return await p.fetch(
        """SELECT s.*, count(t.id)::int AS turns,
                  count(*) FILTER (WHERE t.status = 'running')::int AS live,
                  jsonb_agg(jsonb_build_array(t.model, t.input_tokens,
                            t.cached_input_tokens, t.output_tokens))
                    FILTER (WHERE t.total_tokens IS NOT NULL) AS tok_rows,
                  sum(t.total_tokens)::bigint AS tot
           FROM chat_sessions s LEFT JOIN chat_turns t ON t.session_id = s.id
           WHERE NOT s.archived
           GROUP BY s.id ORDER BY s.last_at DESC LIMIT $1""", limit)


def session_cost(row) -> float:
    rows = row["tok_rows"]
    if isinstance(rows, str):
        rows = json.loads(rows)
    return sum(est_cost_usd(inp, cached, outp, model)
               for model, inp, cached, outp in (rows or []))


def agent_label(directory: dict, slug: str) -> str:
    info = directory.get(slug)
    return info["name"] if info else slug


# ── rendering: sidebar + transcript blocks ───────────────────────────────────

def sidebar(sessions, directory, user: str, active_sid: str | None, now) -> str:
    mine = [s for s in sessions if s["created_by"] == user]
    theirs = [s for s in sessions if s["created_by"] != user]

    def item(s) -> str:
        cost = session_cost(s)
        live = "<span class='dot live'></span>" if s["live"] else ""
        on = " on" if s["id"] == active_sid else ""
        spend = H(fmt_money(cost)) if s["tot"] else "—"
        return (f"<a class='sess{on}' href='/chat/{H(s['id'])}'>"
                f"<span class='t1'>{live}<span class='ttl'>{H(s['title'] or '(untitled)')}</span></span>"
                f"<span class='t2'><span class='ag'>{H(agent_label(directory, s['agent']))}</span>"
                f"<span>{H(ago((now - s['last_at']).total_seconds()))}</span>"
                f"<span class='sp'>{spend}</span></span></a>")

    bits = ["<a class='newchat' href='/chat'>+ New conversation</a>"]
    if mine:
        today = [s for s in mine if (now - s["last_at"]).total_seconds() < 86400]
        earlier = [s for s in mine if s not in today]
        if today:
            bits.append("<div class='sgrp'>Today</div>" + "".join(item(s) for s in today))
        if earlier:
            bits.append("<div class='sgrp'>Earlier</div>" + "".join(item(s) for s in earlier))
    else:
        bits.append("<p class='sideempty'><b>Nothing yet.</b> Ask Lantern what's "
                    "blocked, or pick a specialist and ask what you'd ask a colleague.</p>")
    if theirs:
        bits.append("<div class='sgrp'>The team's</div>" + "".join(item(s) for s in theirs))
    return f"<aside class='chatside'>{''.join(bits)}</aside>"


def trace_html(trace) -> str:
    """The agent's visible work: tool lines with folded results, in order."""
    if isinstance(trace, str):
        try:
            trace = json.loads(trace)
        except ValueError:
            trace = []
    out = []
    for ev in trace or []:
        k = ev.get("kind")
        if k == "tool":
            out.append(f"<div class='tl'><span class='g'>⏺</span>"
                       f"<span class='tn'>{H(ev.get('name', '?'))}</span>"
                       f"<span class='ta' title='{H(ev.get('args', ''))}'>"
                       f"{H(ev.get('args', ''))}</span></div>")
        elif k == "tool_done":
            o = ev.get("output", "")
            out.append(f"<details class='tlo'><summary>result · {len(o)} chars</summary>"
                       f"<pre>{H(o)}</pre></details>")
        elif k == "specialist":
            out.append(f"<div class='tl spec'><span class='g'>↳</span>"
                       f"<span class='tn'>asked {H(ev.get('role', '?'))}</span>"
                       f"<span class='ta'>{H(ev.get('question', ''))}</span></div>")
        elif k == "specialist_done":
            tok = ev.get("tokens")
            tok_s = f" · {fmt_int(tok)} tok" if tok else ""
            out.append(f"<details class='tlo'><summary>{H(ev.get('role', '?'))} answered"
                       f"{H(tok_s)}</summary><pre>{H(ev.get('answer', ''))}</pre></details>")
        elif k == "note":
            out.append(f"<div class='tl'><span class='g'>·</span>"
                       f"<span class='ta'>{H(ev.get('text', ''))}</span></div>")
    return f"<div class='work'>{''.join(out)}</div>" if out else ""


def turn_ledger(turn) -> str:
    if turn["total_tokens"] is None:
        return "<div class='tfoot'><span>unmetered</span></div>"
    cost = est_cost_usd(turn["input_tokens"], turn["cached_input_tokens"],
                        turn["output_tokens"], turn["model"])
    cached = (f"{round(turn['cached_input_tokens'] / turn['input_tokens'] * 100)}% cached"
              if turn["input_tokens"] else "")
    dur = ""
    if turn["finished_at"]:
        dur = ago((turn["finished_at"] - turn["started_at"]).total_seconds())
    bits = [f"<span class='m'>{H(turn['model'] or '—')}</span>",
            f"<span>{fmt_int(turn['total_tokens'])} tok</span>"]
    if cached:
        bits.append(f"<span>{H(cached)}</span>")
    bits.append(f"<span>{H(fmt_money(cost))}</span>")
    if dur:
        bits.append(f"<span>{H(dur)}</span>")
    return f"<div class='tfoot'>{''.join(bits)}</div>"


def user_block(turn) -> str:
    return (f"<div class='msg you'><span class='who'>You"
            f"<span class='tm'>{turn['started_at']:%H:%M}</span></span>"
            f"<div class='utext'>{H(turn['user_text'])}</div></div>")


def agent_block(turn, label: str) -> str:
    """One finished agent reply: work trace + rendered answer + ledger."""
    bits = [f"<span class='who'>{H(label)}</span>", trace_html(turn["trace"])]
    if turn["status"] == "failed":
        bits.append(f"<div class='terr'>{H(turn['error'] or 'failed')}</div>")
    elif turn["status"] == "stopped":
        bits.append("<div class='tstop'>Stopped by the developer — the reply above "
                    "is incomplete.</div>")
    if turn["final_text"]:
        bits.append(f"<div class='prose atext'>{deps['render_markdown'](turn['final_text'])}</div>")
    if turn["status"] != "running":
        bits.append(turn_ledger(turn))
    return f"<div class='msg agent'>{''.join(bits)}</div>"


def turn_html(turn, label: str) -> str:
    return (f"<div class='turn' data-turn='{turn['id']}'>{user_block(turn)}"
            f"{agent_block(turn, label)}</div>")


def composer(sid_or_new: str, agent_slug: str, directory: dict, session_est: float,
             turns: int, run_id: str | None, disabled: bool) -> str:
    label = agent_label(directory, agent_slug)
    ph = ("Ask Lantern — Enter to send, Shift+Enter for a new line"
          if agent_slug == cs.LANTERN_AGENT else
          f"Ask {label} — Enter to send, Shift+Enter for a new line")
    billed = (f"{fmt_money(session_est)} this chat" if turns and session_est
              else "nothing billed yet")
    scope = f"<b>run {H(run_id)}</b><span>·</span>" if run_id else ""
    dis = " disabled" if disabled else ""
    return f"""<div class='composer'><div class='cbox'>
      <div class='crow'>
        <textarea id='cinput' placeholder='{H(ph)}' rows='1'{dis}></textarea>
        <button class='send' id='csend' title='Send (Enter)'{dis}>↑</button>
      </div>
      <div class='cfoot'>{scope}<b>{H(label)} consult</b><span>·</span>
        <span>advisory, read-only</span><span>·</span>
        <span id='cbilled'>{H(billed)}</span></div>
    </div></div>"""


# ── the client: streaming, sending, stopping ─────────────────────────────────

def chat_js(sid: str, label: str, running_turn: int | None) -> str:
    cfg = json.dumps({"sid": sid, "label": label, "running": running_turn})
    return """
<script>
(function(){
  var CFG = """ + cfg + """;
  var tr = document.getElementById('transcript');
  var input = document.getElementById('cinput'), send = document.getElementById('csend');
  var live = null, liveText = null, liveWork = null, liveTimer = null, t0 = 0, tools = 0;
  var lastUserText = null;

  function esc(s){var d=document.createElement('span');d.textContent=s;return d.innerHTML}
  function atBottom(){return tr.scrollHeight - tr.scrollTop - tr.clientHeight < 120}
  function pin(force){if(force || atBottom()) tr.scrollTop = tr.scrollHeight}

  function setBusy(b){
    if(input){input.disabled = b} if(send){send.disabled = b}
    if(!b && input){input.focus()}
  }

  function workingLine(){
    var w = document.createElement('div'); w.className='workingline'; w.id='working';
    w.innerHTML = "<span class='dot'></span><span id='wtext'>Working</span>" +
      "<button class='stop' id='wstop'>Stop</button>";
    w.querySelector('#wstop').onclick = function(){
      fetch('/chat/' + encodeURIComponent(CFG.sid) + '/stop', {method:'POST'});
    };
    return w;
  }

  function startLive(turnId, userText){
    var turn = document.querySelector("[data-turn='" + turnId + "']");
    if(turn && turn.querySelector('.msg.agent')) return;   // already live or finished
    tools = 0; t0 = Date.now();
    if(userText) lastUserText = userText;
    else if(turn){ var ut = turn.querySelector('.utext');
      if(ut) lastUserText = ut.textContent; }
    if(!turn){
      turn = document.createElement('div');
      turn.className = 'turn'; turn.dataset.turn = turnId;
      var now = new Date(), hm = ('0'+now.getUTCHours()).slice(-2)+':'+('0'+now.getUTCMinutes()).slice(-2);
      if(userText){
        turn.innerHTML = "<div class='msg you'><span class='who'>You<span class='tm'>" +
          hm + "</span></span><div class='utext'>" + esc(userText) + "</div></div>";
      }
      var host = tr.firstElementChild || tr;
      host.appendChild(turn);
    }
    var ag = document.createElement('div');
    ag.className = 'msg agent';
    ag.innerHTML = "<span class='who'>" + esc(CFG.label) +
      "</span><div class='work' id='live-work'></div>" +
      "<div class='atext streaming' id='live-text'></div>";
    turn.appendChild(ag);
    ag.appendChild(workingLine());
    live = turn; liveWork = turn.querySelector('#live-work');
    liveText = turn.querySelector('#live-text');
    liveTimer = setInterval(function(){
      var el = document.getElementById('wtext');
      if(el){var s = Math.floor((Date.now()-t0)/1000);
        el.textContent = 'Working — ' + s + 's' + (tools ? ' · ' + tools + ' tool call' + (tools>1?'s':'') : '');}
    }, 1000);
    setBusy(true); pin(true);
  }

  function resetLive(){       // SSE reconnect replays the whole turn — rebuild clean
    if(liveWork) liveWork.innerHTML = '';
    if(liveText) liveText.textContent = '';
    tools = 0;
  }

  function money(x){ return x <= 0 ? '—' : (x < 0.01 ? '<$0.01' : '$' + x.toFixed(2)); }
  function updateTotals(s){   // the final event carries the session ledger (server-priced)
    if(!s) return;
    var c = document.getElementById('tot-cost'), l = document.getElementById('tot-line');
    var b = document.getElementById('cbilled');
    if(c) c.textContent = s.tokens ? money(s.est_usd) : '—';
    if(l) l.textContent = s.tokens.toLocaleString() + ' tok · ' + s.turns + ' turn' +
      (s.turns === 1 ? '' : 's') + (s.unmetered ? ' · ' + s.unmetered + ' unmetered' : '');
    if(b) b.textContent = s.tokens && s.est_usd ? money(s.est_usd) + ' this chat' : 'nothing billed yet';
  }

  function endLive(turnId, ok){
    if(liveTimer){clearInterval(liveTimer); liveTimer = null;}
    var w = document.getElementById('working'); if(w) w.remove();
    // the server titled the session on its first turn — reflect it without a reload
    var ttl = document.querySelector('.chathead input.ttl');
    if(ttl && !ttl.value && lastUserText){ ttl.value = lastUserText.slice(0, 80); }
    var mine = document.querySelector('.sess.on');
    if(mine){
      var d = mine.querySelector('.dot'); if(d) d.remove();
      var st = mine.querySelector('.ttl');
      if(st && st.textContent === '(untitled)' && lastUserText){
        st.textContent = lastUserText.slice(0, 80); }
    }
    if(!live){setBusy(false); return}
    if(liveText) liveText.classList.remove('streaming');
    if(ok){
      fetch('/chat/' + encodeURIComponent(CFG.sid) + '/turn/' + turnId)
        .then(function(r){return r.text()})
        .then(function(html){
          if(!live) return;
          var probe = document.createElement('div'); probe.innerHTML = html;
          var fresh = probe.firstElementChild;
          live.replaceWith(fresh);
          live = liveText = liveWork = null;
          pin(false);
        })
        .catch(function(){ live = liveText = liveWork = null });  // streamed text stands
    } else { live = liveText = liveWork = null; }
    setBusy(false);
  }

  function toolLine(ev){
    tools++;
    var d = document.createElement('div'); d.className = 'tl' + (ev.kind==='specialist' ? ' spec' : '');
    if(ev.kind === 'tool'){
      d.innerHTML = "<span class='g'>⏺</span><span class='tn'>" + esc(ev.name||'?') +
        "</span><span class='ta'>" + esc(ev.args||'') + "</span>";
    } else {
      d.innerHTML = "<span class='g'>↳</span><span class='tn'>asked " + esc(ev.role||'?') +
        "</span><span class='ta'>" + esc(ev.question||'') + "</span>";
    }
    liveWork.appendChild(d); pin(false);
  }
  function toolOut(ev){
    var d = document.createElement('details'); d.className = 'tlo';
    var head = ev.kind === 'specialist_done'
      ? esc(ev.role||'?') + ' answered' + (ev.tokens ? ' · ' + ev.tokens + ' tok' : '')
      : 'result · ' + (ev.output||'').length + ' chars';
    d.innerHTML = '<summary>' + head + '</summary><pre>' +
      esc(ev.kind === 'specialist_done' ? (ev.answer||'') : (ev.output||'')) + '</pre>';
    liveWork.appendChild(d); pin(false);
  }

  var es = new EventSource('/chat/' + encodeURIComponent(CFG.sid) + '/events');
  var opened = false;
  es.onopen = function(){ if(opened && live) resetLive(); opened = true; };
  es.onmessage = function(m){
    var ev; try { ev = JSON.parse(m.data) } catch(e){ return }
    switch(ev.kind){
      case 'turn_started': startLive(ev.turn_id, ev.user_text); break;
      case 'delta': if(liveText){liveText.textContent += ev.text; pin(false)} break;
      case 'tool': case 'specialist': if(liveWork) toolLine(ev); break;
      case 'tool_done': case 'specialist_done': if(liveWork) toolOut(ev); break;
      case 'final': updateTotals(ev.session); endLive(ev.turn_id, true); break;
      case 'totals': updateTotals(ev.session); break;
      case 'idle':
        // Nothing is running server-side, yet this page shows a live turn: the
        // process that owned it is gone. Swap in the row's real (reaped) state.
        if(live){ endLive(live.dataset.turn, true); }
        break;
      case 'error': if(live){var d=document.createElement('div');d.className='terr';
          d.textContent = ev.message || 'failed';
          live.querySelector('.msg.agent').appendChild(d);} endLive(0, false); break;
      case 'stopped': if(live){var d2=document.createElement('div');d2.className='tstop';
          d2.textContent = 'Stopped — the reply is incomplete.';
          live.querySelector('.msg.agent').appendChild(d2);} endLive(0, false); break;
    }
  };

  function autosize(){ input.style.height='auto';
    input.style.height = Math.min(input.scrollHeight, 220) + 'px'; }
  function submit(){
    var text = (input.value || '').trim();
    if(!text || input.disabled) return;
    input.value = ''; autosize();
    function giveBack(msg){ input.value = text; autosize(); if(msg) alert(msg); }
    fetch('/chat/' + encodeURIComponent(CFG.sid) + '/send', {
      method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:'text=' + encodeURIComponent(text)})
    .then(function(r){
      if(r.status === 409){ giveBack('A turn is already running — stop it or wait.'); return null }
      if(!r.ok){ giveBack('Send failed (' + r.status + ')'); return null }
      return r.json();
    })
    .then(function(j){ if(j) startLive(j.turn_id, text) })
    .catch(function(){ giveBack('Send failed — is Mission Control still up? Your text is back in the box.') });
  }
  if(input){
    input.addEventListener('input', autosize);
    input.addEventListener('keydown', function(e){
      if(e.key === 'Enter' && !e.shiftKey){ e.preventDefault(); submit(); }
    });
    send.addEventListener('click', submit);
    autosize(); if(!input.disabled) input.focus();
  }
  document.addEventListener('keydown', function(e){   // Esc interrupts, like Claude Code
    if(e.key === 'Escape' && live){
      fetch('/chat/' + encodeURIComponent(CFG.sid) + '/stop', {method:'POST'});
    }
  });
  if(CFG.running){ startLive(CFG.running, null); }
  pin(true);
})();
</script>"""


# ── routes: chat hub ─────────────────────────────────────────────────────────

@router.get("/chat", response_class=HTMLResponse)
async def chat_hub(request: Request, agent: str = "", run: str = "", error: str = ""):
    user = _user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    p = await _pool()
    now = datetime.now(timezone.utc)
    async with p.acquire() as conn:
        directory = await cs.agent_directory(conn)
    sessions = await session_rows(p)
    ok, why = cs.chat_configured()
    sel = agent if agent in directory else cs.LANTERN_AGENT

    cards = []
    info = directory[cs.LANTERN_AGENT]
    cards.append(f"""<label class='acard hero{' sel' if sel == cs.LANTERN_AGENT else ''}'
        data-agent='{cs.LANTERN_AGENT}'><span class='an'>Lantern</span>
      <div class='ad'>{H(info["desc"])}</div>
      <div class='am'><span>orchestrator</span><span>reads the pipeline database</span>
        <span>hands questions to specialists</span></div></label>""")
    for slug, i in directory.items():
        if i["kind"] == "orchestrator":
            continue
        kind = "fleet role" if i["kind"] == "fleet" else "custom"
        browser = ("<span title='This role drives a browser on pipeline runs; web consults "
                   "run without it for now — use pipeline.py ask -i when a live browser "
                   "matters.'>browser: CLI only</span>" if i.get("browser_role") else "")
        cards.append(f"""<label class='acard{' sel' if sel == slug else ''}' data-agent='{H(slug)}'>
          <span class='an'>{H(i["name"])}</span><div class='ad'>{H(i["desc"])}</div>
          <div class='am'><span>{kind}</span><span>{H(i["model_pref"])}</span>{browser}</div>
        </label>""")

    notice = "" if ok else (f"<div class='notice'><b>Chat can't reach a model.</b> "
                            f"{H(why)} on the server, then reload. History below still works.</div>")
    err = f"<div class='notice'><b>{H(error)}</b></div>" if error else ""
    run_chip = (f"<p class='sub'>This conversation will be scoped to run "
                f"<code>{H(run)}</code> — the agent reads its run folder first.</p>"
                if run else "")

    main = f"""<main class='chatmain'><div class='hub'><div class='inner'>
      <h1>Talk to the fleet</h1>
      <p class='lede'>One question, one agent. Lantern sees the whole pipeline and pulls
        specialists in; each role answers from its own charter, skills and memory. Consults
        are advisory and read-only — work that changes the product goes through a run.</p>
      {notice}{err}{run_chip}
      <form id='newform' method='post' action='/chat/new'>
        <input type='hidden' name='agent' id='agentfield' value='{H(sel)}'>
        <input type='hidden' name='run_id' value='{H(run)}'>
        <div class='agrid'>{''.join(cards)}</div>
        <div class='composer' style='border-top:0;padding:16px 0 0'><div class='cbox'>
          <div class='crow'>
            <textarea name='text' id='cinput' rows='1' {'' if ok else 'disabled '}
              placeholder='Ask — Enter to send, Shift+Enter for a new line'></textarea>
            <button class='send' id='csend' {'' if ok else 'disabled '}title='Send (Enter)'>↑</button>
          </div>
          <div class='cfoot'><b id='selname'>{H(agent_label(directory, sel))} consult</b>
            <span>·</span><span>advisory, read-only</span>
            <span>·</span><span>nothing billed yet</span></div>
        </div></div>
      </form>
      <p class='sub' style='margin-top:18px'>Need a new kind of specialist?
        <a href='/agents' style='color:var(--dawn-3)'>Create an agent →</a></p>
    </div></div></main>
    <script>
    (function(){{
      var f = document.getElementById('agentfield'), nm = document.getElementById('selname');
      var input = document.getElementById('cinput');
      document.querySelectorAll('.acard').forEach(function(c){{
        c.addEventListener('click', function(){{
          document.querySelectorAll('.acard.sel').forEach(function(x){{x.classList.remove('sel')}});
          c.classList.add('sel'); f.value = c.dataset.agent;
          nm.textContent = (c.querySelector('.an').textContent) + ' consult';
          if(input) input.focus();
        }});
      }});
      if(input){{
        input.addEventListener('input', function(){{ input.style.height='auto';
          input.style.height = Math.min(input.scrollHeight, 220) + 'px'; }});
        input.addEventListener('keydown', function(e){{
          if(e.key === 'Enter' && !e.shiftKey){{ e.preventDefault();
            if(input.value.trim()) document.getElementById('newform').submit(); }}
        }});
        input.focus();
      }}
    }})();
    </script>"""

    body = f"<div class='chatwrap'>{sidebar(sessions, directory, user, None, now)}{main}</div>"
    return HTMLResponse(deps["page"]("Chat — Lantern Mission Control", body, user,
                                     "/chat", f"{now:%H:%M}", auto_reload=False))


@router.post("/chat/new")
async def chat_new(request: Request, agent: str = Form(...), text: str = Form(""),
                   run_id: str = Form("")):
    user = _user(request)
    if not user:
        raise HTTPException(401, "sign in required")
    ok, why = cs.chat_configured()
    if not ok:
        return RedirectResponse(f"/chat?error={H(why)}", status_code=303)
    if not text.strip():
        return RedirectResponse(f"/chat?agent={agent}&run={run_id}", status_code=303)
    p = await _pool()
    async with p.acquire() as conn:
        directory = await cs.agent_directory(conn)
        if agent not in directory:
            return RedirectResponse("/chat?error=unknown+agent", status_code=303)
        sid = await cs.create_session(conn, user, agent, run_id.strip() or None)
    await _start_turn(p, sid, text.strip(), user)
    return RedirectResponse(f"/chat/{sid}", status_code=303)


# ── routes: one conversation ─────────────────────────────────────────────────

async def _load_session(p, sid: str):
    s = await p.fetchrow("SELECT * FROM chat_sessions WHERE id = $1", sid)
    if not s:
        raise HTTPException(404, "no such conversation")
    return s


async def _start_turn(p, sid: str, text: str, user: str) -> int:
    """Create the turn row, register it on the bus, launch the runner task."""
    session = await _load_session(p, sid)
    async with p.acquire() as conn:
        await cs.reap_stale_turns(conn, BUS, sid)
    if BUS.active(sid):
        raise HTTPException(409, "a turn is already running in this conversation")
    turn_id = await p.fetchval(
        """INSERT INTO chat_turns (session_id, asked_by, user_text)
           VALUES ($1, $2, $3) RETURNING id""", sid, user, text)
    try:
        BUS.start(sid, turn_id)
    except RuntimeError:            # two sends raced past the active check
        await p.execute(
            """UPDATE chat_turns SET status='failed', error=$2, finished_at=now()
               WHERE id = $1""", turn_id, "another turn started first")
        raise HTTPException(409, "a turn is already running in this conversation")
    BUS.publish(sid, {"kind": "turn_started", "turn_id": turn_id,
                      "user_text": text, "by": user})
    task = asyncio.create_task(cs.run_chat_turn(p, session, turn_id, text, user))
    BUS.attach_task(sid, task)
    return turn_id


@router.get("/chat/{sid}/events")
async def chat_events(sid: str, request: Request):
    if not _user(request):
        raise HTTPException(401, "sign in required")

    async def stream():
        replay, q = BUS.subscribe(sid)
        try:
            for ev in replay:
                yield f"data: {json.dumps(ev)}\n\n"
            if not replay:
                # A client reconnecting after a restart lands here while its page
                # still shows a working turn — reap so the fragment it fetches
                # says «interrupted» instead of pretending to run.
                p = await _pool()
                async with p.acquire() as conn:
                    await cs.reap_stale_turns(conn, BUS, sid)
                yield f"data: {json.dumps({'kind': 'idle'})}\n\n"
            # Bounded lifetime: EventSource reconnects on its own (replay rebuilds a
            # live turn), and no stream can hold a restart hostage for long.
            # uvicorn --timeout-graceful-shutdown is the real cap; this is the belt.
            deadline = asyncio.get_running_loop().time() + SSE_MAX_SECONDS
            while asyncio.get_running_loop().time() < deadline:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'kind': 'ping'})}\n\n"
                    continue
                if ev is None:      # server going down — end cleanly, client reconnects
                    break
                yield f"data: {json.dumps(ev)}\n\n"
        finally:
            BUS.unsubscribe(sid, q)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@router.post("/chat/{sid}/send")
async def chat_send(sid: str, request: Request, text: str = Form(...)):
    user = _user(request)
    if not user:
        raise HTTPException(401, "sign in required")
    ok, why = cs.chat_configured()
    if not ok:
        raise HTTPException(503, why)
    if not text.strip():
        raise HTTPException(400, "empty message")
    p = await _pool()
    turn_id = await _start_turn(p, sid, text.strip(), user)
    return {"turn_id": turn_id}


@router.post("/chat/{sid}/stop")
async def chat_stop(sid: str, request: Request):
    if not _user(request):
        raise HTTPException(401, "sign in required")
    return {"stopped": BUS.stop(sid)}


@router.post("/chat/{sid}/rename")
async def chat_rename(sid: str, request: Request, title: str = Form("")):
    if not _user(request):
        raise HTTPException(401, "sign in required")
    p = await _pool()
    await p.execute("UPDATE chat_sessions SET title = $2 WHERE id = $1",
                    sid, " ".join(title.split())[:120] or None)
    return RedirectResponse(f"/chat/{sid}", status_code=303)


@router.post("/chat/{sid}/archive")
async def chat_archive(sid: str, request: Request):
    if not _user(request):
        raise HTTPException(401, "sign in required")
    p = await _pool()
    await p.execute("UPDATE chat_sessions SET archived = true WHERE id = $1", sid)
    return RedirectResponse("/chat", status_code=303)


@router.get("/chat/{sid}/turn/{turn_id}", response_class=HTMLResponse)
async def chat_turn_fragment(sid: str, turn_id: int, request: Request):
    """A finished turn, server-rendered — the client swaps its live block for this
    so markdown rendering stays in one place (python-markdown, no JS lib)."""
    if not _user(request):
        raise HTTPException(401, "sign in required")
    p = await _pool()
    turn = await p.fetchrow(
        "SELECT * FROM chat_turns WHERE id = $1 AND session_id = $2", turn_id, sid)
    if not turn:
        raise HTTPException(404, "no such turn")
    s = await _load_session(p, sid)
    async with p.acquire() as conn:
        directory = await cs.agent_directory(conn)
    return HTMLResponse(turn_html(turn, agent_label(directory, s["agent"])))


@router.get("/chat/{sid}", response_class=HTMLResponse)
async def chat_session(sid: str, request: Request):
    user = _user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    p = await _pool()
    now = datetime.now(timezone.utc)
    s = await _load_session(p, sid)
    async with p.acquire() as conn:
        await cs.reap_stale_turns(conn, BUS, sid)
        directory = await cs.agent_directory(conn)
    turns = await p.fetch(
        "SELECT * FROM chat_turns WHERE session_id = $1 ORDER BY id", sid)
    sessions = await session_rows(p)
    label = agent_label(directory, s["agent"])
    info = directory.get(s["agent"], {"desc": "(this agent was removed)",
                                      "kind": "?", "model_pref": "?"})
    ok, why = cs.chat_configured()

    active = BUS.active(sid)
    running_id = active["turn_id"] if active else None
    blocks = []
    for t in turns:
        if t["id"] == running_id:
            # The user's message is server-rendered; the agent's side of a LIVE turn
            # is built entirely by the SSE replay, so nothing renders twice.
            blocks.append(f"<div class='turn' data-turn='{t['id']}'>{user_block(t)}</div>")
            continue
        blocks.append(turn_html(t, label))
    if not turns:
        blocks.append("<p class='empty' style='border:0;margin-top:26px'><b>Say the "
                      "first thing.</b> This agent reads the repo before it answers, "
                      "so ask the real question.</p>")

    # session ledger
    tok_rows = [(t["model"], t["input_tokens"], t["cached_input_tokens"], t["output_tokens"])
                for t in turns if t["total_tokens"] is not None]
    est = sum(est_cost_usd(i, c, o, m) for m, i, c, o in tok_rows)
    tot = sum(t["total_tokens"] or 0 for t in turns)
    unmetered = sum(1 for t in turns if t["total_tokens"] is None and t["status"] != "running")
    unm = f" · {unmetered} unmetered" if unmetered else ""

    chips = [chip(info.get("kind", "?"), ""), chip(info.get("model_pref", "?"), "")]
    if s["run_id"]:
        chips.append(f"<a href='/run/{H(s['run_id'])}'>{chip('run ' + s['run_id'], 'gate')}</a>")
    if info.get("browser_role"):
        chips.append(chip("browser: CLI only", "warn"))
    notice = "" if ok else (f"<div class='notice' style='margin:12px 28px 0'>"
                            f"<b>Chat can't reach a model.</b> {H(why)} — history is "
                            f"readable, sending is off.</div>")

    head = f"""<div class='chathead' id='sessmeta'>
      <div style='min-width:0'>
        <span class='anm'>{H(label)}</span>
        <form class='rename' method='post' action='/chat/{H(sid)}/rename'>
          <input class='ttl' name='title' value='{H(s["title"] or "")}'
            placeholder='(untitled)' onchange='this.form.submit()'></form>
        <div class='adesc'>{H(info["desc"])}</div>
        <div class='chips'>{''.join(chips)}</div>
      </div>
      <div class='totals'><span class='v' id='tot-cost'>{H(fmt_money(est)) if tot else '—'}</span>
        <span id='tot-line'>{fmt_int(tot)} tok · {len(turns)} turn{'s' if len(turns) != 1 else ''}{H(unm)}</span><br>
        started {s['created_at']:%b %d} by {H(s['created_by'])} ·
        <a href='#' onclick="if(confirm('Archive this conversation? History is kept, it just leaves the list.')){{fetch('/chat/{H(sid)}/archive',{{method:'POST'}}).then(function(){{location='/chat'}})}};return false"
          style='text-decoration:underline'>archive</a></div>
    </div>"""

    main = (f"<main class='chatmain'>{head}{notice}"
            f"<div class='transcript' id='transcript'>"
            f"<div style='max-width:920px;margin:0 auto'>{''.join(blocks)}</div></div>"
            + composer(sid, s["agent"], directory, est, len(turns), s["run_id"],
                       disabled=not ok)
            + chat_js(sid, label, running_id))

    body = f"<div class='chatwrap'>{sidebar(sessions, directory, user, sid, now)}{main}</div>"
    title = (s["title"] or label)[:60]
    return HTMLResponse(deps["page"](f"{title} — Lantern Chat", body, user, "/chat",
                                     f"{now:%H:%M}", auto_reload=False))


# ── routes: the agent roster ─────────────────────────────────────────────────

@router.get("/agents", response_class=HTMLResponse)
async def agents_page(request: Request, error: str = ""):
    user = _user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    p = await _pool()
    now = datetime.now(timezone.utc)
    async with p.acquire() as conn:
        directory = await cs.agent_directory(conn)
        archived = [r for r in await cs.custom_agent_rows(conn, include_archived=True)
                    if r["archived"]]
    mem = {r["role"]: r["n"] for r in await p.fetch(
        "SELECT role, count(*)::int AS n FROM role_memory GROUP BY role")}
    use = {r["agent"]: r for r in await p.fetch(
        """SELECT s.agent, count(DISTINCT s.id)::int AS sessions,
                  sum(t.total_tokens)::bigint AS tok,
                  jsonb_agg(jsonb_build_array(t.model, t.input_tokens,
                            t.cached_input_tokens, t.output_tokens))
                    FILTER (WHERE t.total_tokens IS NOT NULL) AS tok_rows
           FROM chat_sessions s LEFT JOIN chat_turns t ON t.session_id = s.id
           GROUP BY s.agent""")}

    def stats(slug: str) -> str:
        u = use.get(slug)
        n_mem = mem.get(slug, 0)
        bits = [f"<span>{n_mem} memor{'ies' if n_mem != 1 else 'y'}</span>"]
        if u and u["sessions"]:
            cost = session_cost(u)
            bits.append(f"<span>{u['sessions']} chat{'s' if u['sessions'] != 1 else ''}</span>")
            bits.append(f"<span>{H(fmt_money(cost)) if u['tok'] else '—'}</span>")
        else:
            bits.append("<span>never consulted here</span>")
        return "".join(bits)

    fleet_cards, custom_cards = [], []
    for slug, i in directory.items():
        if i["kind"] == "orchestrator":
            continue
        go = (f"<a class='btn sm' style='text-decoration:none' "
              f"href='/chat?agent={H(slug)}'>Consult →</a>")
        if i["kind"] == "fleet":
            browser = chip("browser: CLI only", "warn") if i.get("browser_role") else ""
            fleet_cards.append(
                f"<div class='acard'><span class='an'>{H(i['name'])}</span>"
                f"<div class='ad'>{H(i['desc'])}</div>"
                f"<div class='am'>{stats(slug)}</div>"
                f"<div class='arow'>{chip(i['model_pref'], '')}{browser}"
                f"<span class='go'>{go}</span></div></div>")
        else:
            r = i["row"]
            arch = (f"<form method='post' action='/agents/{H(slug)}/archive' "
                    f"onsubmit=\"return confirm('Archive {H(i['name'])}? Chats are kept.')\" "
                    f"style='display:inline'><button class='btn sm'>Archive</button></form>")
            custom_cards.append(
                f"<div class='acard'><span class='an'>{H(i['name'])}</span>"
                f"<div class='ad'>{H(i['desc'])}</div>"
                f"<div class='am'>{stats(slug)}<span>by {H(r['created_by'])}</span></div>"
                f"<div class='arow'>{chip(i['model_pref'], '')}{arch}"
                f"<span class='go'>{go}</span></div></div>")

    arch_html = ""
    if archived:
        rows = "".join(
            f"<div class='att'><span class='tm'>{a['created_at']:%b %d}</span>"
            f"<span class='rn'>{H(a['name'])}</span>"
            f"<span class='er ok' style='color:var(--text-dim)'>{H(a['purpose'][:110])}</span>"
            f"<span class='at'><form method='post' action='/agents/{H(a['slug'])}/restore'>"
            f"<button class='btn sm'>Restore</button></form></span></div>"
            for a in archived)
        arch_html = (f"<details style='margin-top:22px'><summary class='caps' "
                     f"style='cursor:pointer'>Archived · {len(archived)}</summary>"
                     f"<section class='feed' style='margin-top:8px;border:0;padding:0'>"
                     f"{rows}</section></details>")

    err = f"<div class='notice'><b>{H(error)}</b></div>" if error else ""
    body = f"""<main class='page'><div style='max-width:1100px;margin:0 auto'>
      <h1 style='margin-top:22px;font-size:var(--text-lg);font-weight:600'>The roster</h1>
      <p class='lede'>Fleet roles are defined in <code>agents/&lt;role&gt;/</code> — the same
        charter, skills and memory the pipeline loads. Custom agents live in the database,
        learn through their own memory, and consult with the same read-only toolset.
        Anyone on the team can create one.</p>{err}
      <h2 class='sect'>The fleet</h2>
      <div class='agrid roster'>{''.join(fleet_cards)}</div>
      <h2 class='sect'>Custom agents</h2>
      <div class='agrid roster'>{''.join(custom_cards) if custom_cards else ''}</div>
      {"<p class='empty' style='border:0'><b>None yet.</b> The form below makes one in under a minute.</p>" if not custom_cards else ''}
      <div class='newagent'><h3>New agent</h3>
        <form method='post' action='/agents/new'>
          <div class='frow'>
            <input type='text' name='name' placeholder='Name — e.g. Release Notes' required maxlength='60'>
            <input type='text' name='purpose' placeholder='What it is for — one honest line' required maxlength='200' style='flex:2'>
          </div>
          <details><summary class='caps' style='cursor:pointer'>Instructions — optional</summary>
            <p class='hint'>Leave empty and Lantern composes working instructions from the
              purpose (ground answers in the repo, admit unknowns, record durable learnings).
              Write your own to override.</p>
            <textarea name='instructions' placeholder='You are …'></textarea>
          </details>
          <div class='frow' style='margin-top:12px;align-items:center'>
            <label class='radio'><input type='radio' name='model_pref' value='reasoning' checked>
              reasoning model — judgement work</label>
            <label class='radio'><input type='radio' name='model_pref' value='fast'>
              fast model — volume work</label>
            <button class='btn primary' style='margin-left:auto'>Create agent</button>
          </div>
        </form></div>
      {arch_html}
      <p class='footnote'>Custom agents are consult-only (D11): repo read tools +
        append_memory, no writes, no gates. A custom agent that needs to act in the
        pipeline becomes a real role: <code>agents/_template/</code>.</p>
    </div></main>"""
    return HTMLResponse(deps["page"]("Agents — Lantern Mission Control", body, user,
                                     "/agents", f"{now:%H:%M}"))


@router.post("/agents/new")
async def agents_new(request: Request, name: str = Form(...), purpose: str = Form(...),
                     instructions: str = Form(""), model_pref: str = Form("reasoning")):
    user = _user(request)
    if not user:
        raise HTTPException(401, "sign in required")
    p = await _pool()
    async with p.acquire() as conn:
        try:
            slug = await cs.create_custom_agent(conn, name, purpose, instructions,
                                                model_pref, user)
        except ValueError as e:
            return RedirectResponse(f"/agents?error={H(str(e))}", status_code=303)
    return RedirectResponse(f"/chat?agent={slug}", status_code=303)


@router.post("/agents/{slug}/archive")
async def agents_archive(slug: str, request: Request):
    if not _user(request):
        raise HTTPException(401, "sign in required")
    p = await _pool()
    await p.execute(
        "UPDATE custom_agents SET archived = true, updated_at = now() WHERE slug = $1", slug)
    return RedirectResponse("/agents", status_code=303)


@router.post("/agents/{slug}/restore")
async def agents_restore(slug: str, request: Request):
    if not _user(request):
        raise HTTPException(401, "sign in required")
    p = await _pool()
    await p.execute(
        "UPDATE custom_agents SET archived = false, updated_at = now() WHERE slug = $1", slug)
    return RedirectResponse("/agents", status_code=303)
