"""Lantern's Slack front door (D21) — Bolt for Python, Socket Mode, no public URL.

The invariant from docs/plans/symphony-alignment.md §3: **only a host-side service ever
writes approvals, and agents never touch Slack tokens.** This is that service — a few
hundred lines over the existing Postgres and pipeline.py, its own systemd unit
(infra/ec2/lantern-slack-bridge.service) beside Mission Control, no gateway in between.

What it does
  @lantern <idea>            one run per idea, one thread per run. The mention's ts becomes
                             the thread; it is stored on the run (runs.slack_thread_ts) and
                             is the correlation key for everything that follows.
  gate notifications         pending approvals post into the run's thread as Block Kit
                             messages with Approve / Reject buttons — for the gates
                             LANTERN_SLACK_GATES carries. staging_deploy and prod_signoff
                             stay Mission-Control/CLI-only (plan §4, S1.2) and post as text.
  Approve / Reject           ack within Slack's 3 s, THEN pipeline.cmd_decide with
                             by="slack:<user id>" — only for LANTERN_SLACK_APPROVERS.
                             Everyone else reads "not an approver"; nothing is written.
  /lantern-rework, /lantern-retry   the D17 loops, for LANTERN_SLACK_OPERATORS.
  state changes              events on a run that has a thread are relayed as replies.

Fail-closed: an empty allowlist means nobody may act; a refused click is logged with the
Slack identity; every write goes through pipeline.py with `by="slack:U…"`, so the audit
log reads `human:slack:U…` and Mission Control shows who decided. Slack workspace
membership is not an authorization boundary — the allowlists are.

Testable without Slack or a database: every handler is a plain function over an
injected client and a `Deps` bundle; `build_app()` is the only place slack_bolt is
imported, and `RealDeps` is the only place Postgres is touched.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
RUNNER = HERE.parent / "azure-runner"
if str(RUNNER) not in sys.path:
    sys.path.insert(0, str(RUNNER))

DEFAULT_GATES = ("story_signoff", "ux_signoff", "plan_signoff", "code_complete")
ALL_GATES = DEFAULT_GATES + ("staging_deploy", "prod_signoff")
REWORK_TARGETS = ("02-pre-coding", "03-coding", "04-qa-dev")
RELAY_EVENTS = {
    "stage_started": "▶ {stage} started",
    "stage_succeeded": "✓ {stage} passed",
    "stage_failed": "✗ {stage} failed{error}",
    "gate_opened": "⏸ gate `{gate}` is waiting for a human",
    "gate_approved": "✓ `{gate}` approved by {who}",
    "gate_rejected": "✗ `{gate}` rejected by {who} — run failed; rework or retry",
    "run_reworked": "↩ sent back to {to} by {who}",
    "run_retried": "↻ re-queued by {who}",
    "run_done": "🏁 run done — concept to live",
    "product_target_set": "📦 product target: {repo} @ {branch}",
}
GATE_ACTION_ID = "lantern_gate"
# Stripping the bot mention is cosmetic, so be liberal about the id shape rather
# than risk leaving "<@U…>" glued to the front of the idea text.
MENTION = re.compile(r"<@[A-Za-z0-9._-]+(?:\|[^>]*)?>")
KV = re.compile(r"\b(repo|mode|branch)=(\S+)")


def parse_users(raw: str | None) -> frozenset[str]:
    """`U123, U456` → {'U123','U456'}; Slack's <@U123> form is accepted too."""
    out = set()
    for part in re.split(r"[,\s]+", raw or ""):
        part = part.strip().strip("<>@").split("|")[0]
        if part:
            out.add(part)
    return frozenset(out)


@dataclass
class Config:
    bot_token: str = ""
    app_token: str = ""
    approvers: frozenset[str] = frozenset()
    operators: frozenset[str] = frozenset()
    channels: frozenset[str] = frozenset()          # empty = listen everywhere it is invited
    gates: tuple[str, ...] = DEFAULT_GATES           # gates that get buttons
    default_repo: str = ""
    base_branch: str = "main"
    coding_mode: str = "human"
    public_url: str = ""
    poll_s: float = 10.0

    @classmethod
    def from_env(cls, env: dict | None = None) -> "Config":
        e = env if env is not None else os.environ
        approvers = parse_users(e.get("LANTERN_SLACK_APPROVERS"))
        gates = tuple(g.strip() for g in (e.get("LANTERN_SLACK_GATES") or ",".join(DEFAULT_GATES)).split(",")
                      if g.strip())
        return cls(
            bot_token=e.get("LANTERN_SLACK_BOT_TOKEN", ""),
            app_token=e.get("LANTERN_SLACK_APP_TOKEN", ""),
            approvers=approvers,
            operators=parse_users(e.get("LANTERN_SLACK_OPERATORS")) or approvers,
            channels=parse_users(e.get("LANTERN_SLACK_CHANNELS")),
            gates=tuple(g for g in gates if g in ALL_GATES),
            default_repo=e.get("LANTERN_SLACK_DEFAULT_REPO", "") or e.get("LANTERN_PRODUCT_REPO", ""),
            base_branch=e.get("LANTERN_PRODUCT_BRANCH", "main") or "main",
            coding_mode=(e.get("LANTERN_SLACK_CODING_MODE", "human") or "human").lower(),
            public_url=(e.get("LANTERN_PUBLIC_URL", "") or "").rstrip("/"),
            poll_s=float(e.get("LANTERN_SLACK_POLL_S", "10") or 10),
        )


@dataclass
class Deps:
    """Everything a handler needs that is not Slack. Production: RealDeps(); tests: fakes."""
    config: Config
    decide: Callable[..., dict]          # (run_id, gate, by, note, approved) -> {ok, error?, output?}
    start_run: Callable[..., dict]       # (idea, brief_path, by, repo, base_branch, coding_mode) -> {ok, run_id?, ...}
    rework: Callable[..., dict]          # (run_id, to_stage, by, note)
    retry: Callable[..., dict]           # (run_id, by)
    log_event: Callable[..., None]       # (run_id|None, actor, type, data)
    store_thread: Callable[..., None]    # (run_id, channel, thread_ts)
    pending_gates: Callable[[], list[dict]] = lambda: []
    recent_events: Callable[[int], list[dict]] = lambda since: []
    now: Callable[[], float] = time.monotonic


def run_url(config: Config, run_id: str) -> str:
    return f"{config.public_url}/run/{run_id}" if config.public_url else f"workflow/runs/{run_id}/"


def _by(user: str) -> str:
    return f"slack:{user}"


def _ts(response) -> str | None:
    """Slack's own SlackResponse and a dict both answer .get(); anything else is a
    client that told us nothing, and a message with no ts is not a thread."""
    try:
        return (response or {}).get("ts")
    except AttributeError:
        return None


# ── @lantern <idea> ──────────────────────────────────────────────────────────

def mention_text(event: dict) -> str:
    return MENTION.sub("", event.get("text") or "").strip()


def parse_mention(text: str) -> dict:
    """{'verb': help|run|idea, 'rest': str, 'repo': str, 'mode': str, 'branch': str}.
    `repo=`, `mode=`, `branch=` tokens anywhere in the message are pulled out of the idea."""
    opts = {k: v for k, v in KV.findall(text)}
    rest = KV.sub("", text).strip()
    verb, _, tail = rest.partition(" ")
    verb = verb.lower()
    if verb in ("help", "?"):
        return {"verb": "help", "rest": "", **opts}
    if verb == "run" and tail.strip():
        return {"verb": "run", "rest": tail.strip().strip("<>"), **opts}
    return {"verb": "idea", "rest": rest, **opts}


HELP = (
    "*Lantern* — the software factory's Slack front door.\n"
    "• `@lantern <idea>` — draft a brief and start a run (add `repo=<url-or-path>` "
    "`mode=auto|human` `branch=<base>` to override the defaults). A thread opens per run; "
    "gates post there with Approve / Reject.\n"
    "• `@lantern run workflow/briefs/<slug>.md` — start a run from an existing brief.\n"
    "• `/lantern-rework <run-id> <02-pre-coding|03-coding|04-qa-dev> [note]` — send a failed "
    "or waiting run back (D17 loop).\n"
    "• `/lantern-retry <run-id>` — re-queue a failed run at its current stage.\n"
    "Only listed approvers may decide gates; only listed operators may start, rework or retry. "
    "`staging_deploy` and `prod_signoff` are decided in Mission Control, never here."
)


def handle_mention(event: dict, client, deps: Deps) -> dict:
    """`app_mention`: an operator's idea becomes a brief, a run and a thread."""
    cfg = deps.config
    user = event.get("user") or ""
    channel = event.get("channel") or ""
    thread_ts = event.get("thread_ts") or event.get("ts") or ""
    if cfg.channels and channel not in cfg.channels:
        deps.log_event(None, f"human:{_by(user)}", "slack_ignored",
                       {"channel": channel, "why": "not a listened channel"})
        return {"ok": False, "reason": "channel not listened"}
    parsed = parse_mention(mention_text(event))
    if parsed["verb"] == "help":
        client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=HELP)
        return {"ok": True, "verb": "help"}
    if user not in cfg.operators:
        client.chat_postMessage(
            channel=channel, thread_ts=thread_ts,
            text=f"<@{user}> not an operator — starting runs from Slack is limited to "
                 "LANTERN_SLACK_OPERATORS. Ask an operator, or use Mission Control.")
        deps.log_event(None, f"human:{_by(user)}", "slack_refused",
                       {"verb": parsed["verb"], "channel": channel, "text": parsed["rest"][:300]})
        return {"ok": False, "reason": "not an operator"}
    repo = parsed.get("repo") or cfg.default_repo
    mode = (parsed.get("mode") or cfg.coding_mode).lower()
    base = parsed.get("branch") or cfg.base_branch
    if parsed["verb"] == "idea" and not parsed["rest"]:
        client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=HELP)
        return {"ok": False, "reason": "empty idea"}
    if parsed["verb"] == "idea" and not repo:
        client.chat_postMessage(
            channel=channel, thread_ts=thread_ts,
            text="Which repository? Add `repo=<url-or-on-box-path>` to the message "
                 "(or set LANTERN_SLACK_DEFAULT_REPO on the bridge).")
        return {"ok": False, "reason": "no repo"}
    res = deps.start_run(
        idea=parsed["rest"] if parsed["verb"] == "idea" else "",
        brief_path=parsed["rest"] if parsed["verb"] == "run" else "",
        by=_by(user), repo=repo, base_branch=base, coding_mode=mode)
    if not res.get("ok"):
        client.chat_postMessage(channel=channel, thread_ts=thread_ts,
                                text=f"Could not start a run: {res.get('error') or res.get('output') or 'unknown error'}")
        return {"ok": False, "reason": res.get("error", "start failed")}
    run_id = res["run_id"]
    deps.store_thread(run_id, channel, thread_ts)
    client.chat_postMessage(
        channel=channel, thread_ts=thread_ts,
        text=(f"Run `{run_id}` created by <@{user}> (coding mode: {mode}, repo: {repo}).\n"
              f"Brief: `{res.get('brief_path', '?')}` · {run_url(cfg, run_id)}\n"
              "This thread follows the run; gates post here."))
    return {"ok": True, "run_id": run_id, "thread_ts": thread_ts}


# ── gate notifications: Block Kit with Approve / Reject ──────────────────────

def _age(requested_at) -> str:
    if not requested_at:
        return ""
    if isinstance(requested_at, str):
        try:
            requested_at = datetime.fromisoformat(requested_at)
        except ValueError:
            return ""
    s = (datetime.now(timezone.utc) - requested_at).total_seconds()
    return f"{int(s // 3600)} h" if s >= 3600 else f"{int(s // 60)} min"


def gate_value(run_id: str, gate: str, decision: str, approval_id) -> str:
    return json.dumps({"run_id": run_id, "gate": gate, "decision": decision,
                       "approval_id": approval_id})


def gate_blocks(g: dict, cfg: Config) -> list[dict]:
    """One pending approval as a message: what is being decided, links, then buttons
    (only for Slack-carried gates)."""
    run_id, gate = g["run_id"], g["gate"]
    payload = g.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            payload = {}
    lines = [f"*Gate `{gate}`* on `{run_id}` — waiting {_age(g.get('requested_at')) or 'now'}"]
    if payload.get("pr_url"):
        lines.append(f"PR: {payload['pr_url']}")
    if payload.get("branch"):
        lines.append(f"Branch: `{payload['branch']}`")
    if payload.get("run_folder"):
        lines.append(f"Run folder: `{payload['run_folder']}`")
    lines.append(f"Decide with the artifact in front of you: {run_url(cfg, run_id)}")
    blocks: list[dict] = [{"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}}]
    if gate in cfg.gates:
        blocks.append({"type": "actions", "block_id": f"gate:{g.get('approval_id')}", "elements": [
            {"type": "button", "action_id": GATE_ACTION_ID, "style": "primary",
             "text": {"type": "plain_text", "text": "Approve"},
             "value": gate_value(run_id, gate, "approve", g.get("approval_id")),
             "confirm": {"title": {"type": "plain_text", "text": f"Approve {gate}?"},
                         "text": {"type": "mrkdwn", "text": f"`{run_id}` advances to the next stage as you."},
                         "confirm": {"type": "plain_text", "text": "Approve"},
                         "deny": {"type": "plain_text", "text": "Back"}}},
            {"type": "button", "action_id": GATE_ACTION_ID, "style": "danger",
             "text": {"type": "plain_text", "text": "Reject"},
             "value": gate_value(run_id, gate, "reject", g.get("approval_id")),
             "confirm": {"title": {"type": "plain_text", "text": f"Reject {gate}?"},
                         "text": {"type": "mrkdwn", "text": f"`{run_id}` is marked failed; rework or retry after."},
                         "confirm": {"type": "plain_text", "text": "Reject"},
                         "deny": {"type": "plain_text", "text": "Back"}}},
        ]})
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text":
                       "Approvers only (LANTERN_SLACK_APPROVERS). The decision is recorded as `human:slack:<you>`."}]})
    else:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text":
                       f"`{gate}` is decided in Mission Control or the CLI, not from Slack (plan §4 S1.2)."}]})
    return blocks


def decided_blocks(value: dict, user: str, ok: bool, message: str) -> list[dict]:
    verdict = ("✓ approved" if value["decision"] == "approve" else "✗ rejected") if ok else "⚠ not applied"
    text = (f"*Gate `{value['gate']}`* on `{value['run_id']}` — {verdict} by <@{user}>"
            + (f"\n{message}" if message else ""))
    return [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]


def notify_pending_gates(client, deps: Deps) -> int:
    """Post every pending, not-yet-posted approval into its run's thread. A run without a
    thread gets one created in the first listened channel (when configured). Idempotent:
    a `slack_gate_posted` event per approval id is the memory."""
    cfg = deps.config
    posted = 0
    for g in deps.pending_gates():
        if g.get("notified"):
            continue
        channel, thread = g.get("slack_channel"), g.get("slack_thread_ts")
        if not thread:
            if not cfg.channels:
                continue
            channel = sorted(cfg.channels)[0]
            head = client.chat_postMessage(
                channel=channel,
                text=f"Run `{g['run_id']}` (by {g.get('created_by', '?')}) — {run_url(cfg, g['run_id'])}")
            thread = _ts(head)
            if not thread:
                continue
            deps.store_thread(g["run_id"], channel, thread)
        msg = client.chat_postMessage(channel=channel, thread_ts=thread,
                                      text=f"gate {g['gate']} on {g['run_id']} is waiting",
                                      blocks=gate_blocks(g, cfg))
        deps.log_event(g["run_id"], "slack-bridge", "slack_gate_posted",
                       {"approval_id": g.get("approval_id"), "gate": g["gate"], "channel": channel,
                        "thread_ts": thread, "ts": _ts(msg), "buttons": g["gate"] in cfg.gates})
        posted += 1
    return posted


# ── button clicks: ack first, then decide as the human ───────────────────────

def handle_gate_action(body: dict, ack: Callable[[], None], client, deps: Deps) -> dict:
    """`block_actions` for Approve / Reject. ack() is the FIRST statement — Slack gives
    3 s, and cmd_decide (git, DB, runboard render) may take longer. Approvers only."""
    ack()
    cfg = deps.config
    user = (body.get("user") or {}).get("id") or ""
    action = (body.get("actions") or [{}])[0]
    try:
        value = json.loads(action.get("value") or "{}")
    except ValueError:
        value = {}
    channel = (body.get("channel") or {}).get("id") or ""
    message = body.get("message") or {}
    ts = message.get("ts") or ""
    thread = message.get("thread_ts") or ts
    run_id, gate, decision = value.get("run_id", ""), value.get("gate", ""), value.get("decision", "")
    if user not in cfg.approvers:
        client.chat_postEphemeral(channel=channel, user=user, thread_ts=thread,
                                  text="not an approver — gate decisions from Slack are limited to "
                                       "LANTERN_SLACK_APPROVERS. Nothing was changed.")
        deps.log_event(run_id or None, f"human:{_by(user)}", "gate_decision_refused",
                       {"gate": gate, "decision": decision, "channel": "slack", "why": "not an approver"})
        return {"ok": False, "reason": "not an approver"}
    if gate not in cfg.gates:
        client.chat_postEphemeral(channel=channel, user=user, thread_ts=thread,
                                  text=f"`{gate}` is not decided from Slack — use Mission Control.")
        return {"ok": False, "reason": "gate not slack-carried"}
    res = deps.decide(run_id, gate, _by(user), "decided from Slack", decision == "approve")
    ok = bool(res.get("ok"))
    msg = "" if ok else (res.get("error") or res.get("output") or "pipeline refused")
    if ts:
        client.chat_update(channel=channel, ts=ts,
                           text=f"{gate} on {run_id}: {'decided' if ok else 'not applied'} by {user}",
                           blocks=decided_blocks(value, user, ok, msg))
    if not ok:
        client.chat_postMessage(channel=channel, thread_ts=thread,
                                text=f"<@{user}> the decision was not applied: {msg}")
    return {"ok": ok, "run_id": run_id, "gate": gate, "decision": decision, "by": _by(user), "message": msg}


# ── slash commands: rework / retry ───────────────────────────────────────────

def handle_rework(command: dict, ack: Callable[[], None], respond: Callable[[str], None], deps: Deps) -> dict:
    ack()
    user = command.get("user_id") or ""
    parts = (command.get("text") or "").split(None, 2)
    if user not in deps.config.operators:
        respond("not an operator — rework from Slack is limited to LANTERN_SLACK_OPERATORS.")
        deps.log_event(None, f"human:{_by(user)}", "slack_refused", {"verb": "rework", "text": command.get("text", "")[:300]})
        return {"ok": False, "reason": "not an operator"}
    if len(parts) < 2 or parts[1] not in REWORK_TARGETS:
        respond(f"usage: /lantern-rework <run-id> <{'|'.join(REWORK_TARGETS)}> [note]")
        return {"ok": False, "reason": "usage"}
    run_id, to_stage = parts[0], parts[1]
    note = parts[2] if len(parts) > 2 else ""
    res = deps.rework(run_id, to_stage, _by(user), note)
    respond(f"`{run_id}` sent back to `{to_stage}`." if res.get("ok")
            else f"rework refused: {res.get('error') or res.get('output') or 'unknown'}")
    return {"ok": bool(res.get("ok")), "run_id": run_id, "to": to_stage, "by": _by(user)}


def handle_retry(command: dict, ack: Callable[[], None], respond: Callable[[str], None], deps: Deps) -> dict:
    ack()
    user = command.get("user_id") or ""
    run_id = (command.get("text") or "").strip().split(None, 1)[0] if (command.get("text") or "").strip() else ""
    if user not in deps.config.operators:
        respond("not an operator — retry from Slack is limited to LANTERN_SLACK_OPERATORS.")
        deps.log_event(None, f"human:{_by(user)}", "slack_refused", {"verb": "retry", "text": run_id})
        return {"ok": False, "reason": "not an operator"}
    if not run_id:
        respond("usage: /lantern-retry <run-id>")
        return {"ok": False, "reason": "usage"}
    res = deps.retry(run_id, _by(user))
    respond(f"`{run_id}` re-queued at its current stage." if res.get("ok")
            else f"retry refused: {res.get('error') or res.get('output') or 'unknown'}")
    return {"ok": bool(res.get("ok")), "run_id": run_id, "by": _by(user)}


# ── state relay: events → thread replies ─────────────────────────────────────

def relay_events(client, deps: Deps, since_id: int) -> int:
    """Post relayed event types for runs with a thread; returns the new watermark."""
    last = since_id
    for ev in deps.recent_events(since_id):
        last = max(last, int(ev["id"]))
        tmpl = RELAY_EVENTS.get(ev.get("type", ""))
        if not tmpl or not ev.get("slack_thread_ts"):
            continue
        data = ev.get("data") or {}
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except ValueError:
                data = {}
        who = (ev.get("actor") or "").replace("human:", "")
        text = tmpl.format(stage=data.get("stage") or data.get("after_stage") or "", gate=data.get("gate", ""),
                           who=who, to=data.get("to", ""), repo=data.get("repo", ""),
                           branch=data.get("branch", ""),
                           error=(" — " + str(data.get("error"))[:200]) if data.get("error") else "")
        client.chat_postMessage(channel=ev["slack_channel"], thread_ts=ev["slack_thread_ts"], text=text)
    return last


# ── production wiring ────────────────────────────────────────────────────────

def _run(coro):
    return asyncio.run(coro)


class RealDeps:
    """Deps over pipeline.py + Postgres. Each call opens its own connection: the bridge
    is low-volume and Bolt runs handlers on worker threads without a shared loop."""

    def __init__(self, config: Config):
        self.config = config
        from chat_service import PipelineExecutor      # the same wrapper the Chat tab uses
        self._exec = PipelineExecutor()
        self.now = time.monotonic

    def _db(self):
        import asyncpg
        from orchestrator import db_urls
        return asyncpg.connect(db_urls()[1])

    def decide(self, run_id, gate, by, note, approved) -> dict:
        return _run(self._exec.decide(run_id, gate, by, note, approved))

    def rework(self, run_id, to_stage, by, note) -> dict:
        return _run(self._exec.rework(run_id, to_stage, by, note))

    def retry(self, run_id, by) -> dict:
        return _run(self._exec.retry(run_id, by))

    def start_run(self, idea, brief_path, by, repo, base_branch, coding_mode) -> dict:
        import brief_composer
        if idea:
            title = " ".join(idea.split())[:80]
            res = brief_composer.compose(
                {"title": title, "problem": idea, "product_repo": repo, "base_branch": base_branch,
                 "coding_mode": coding_mode,
                 "existing_context": "Opened from Slack; the researcher maps the codebase first."},
                by=by)
            if not res["ok"]:
                return {"ok": False, "error": "; ".join(res["problems"] + [f"missing {m}" for m in res["missing"]])}
            try:
                path = brief_composer.write_brief(res["slug"], res["markdown"])
            except FileExistsError as e:
                return {"ok": False, "error": str(e)}
            brief_path = str(path.relative_to(brief_composer.REPO)).replace("\\", "/")
        out = _run(self._exec.start_run(brief_path, None, by, repo, base_branch, coding_mode, ""))
        out["brief_path"] = brief_path
        return out

    def log_event(self, run_id, actor, type_, data) -> None:
        async def go():
            conn = await self._db()
            try:
                await conn.execute("INSERT INTO events (run_id, actor, type, data) VALUES ($1,$2,$3,$4)",
                                   run_id, actor, type_, json.dumps(data or {}))
            finally:
                await conn.close()
        _run(go())

    def store_thread(self, run_id, channel, thread_ts) -> None:
        async def go():
            conn = await self._db()
            try:
                await conn.execute(
                    "UPDATE runs SET slack_channel = $2, slack_thread_ts = $3 WHERE id = $1",
                    run_id, channel, thread_ts)
                await conn.execute("INSERT INTO events (run_id, actor, type, data) VALUES ($1,$2,$3,$4)",
                                   run_id, "slack-bridge", "slack_thread_linked",
                                   json.dumps({"channel": channel, "thread_ts": thread_ts}))
            finally:
                await conn.close()
        _run(go())

    def pending_gates(self) -> list[dict]:
        async def go():
            conn = await self._db()
            try:
                rows = await conn.fetch(
                    """SELECT a.id AS approval_id, a.run_id, a.gate, a.requested_at, a.payload,
                              r.slack_channel, r.slack_thread_ts, r.created_by,
                              EXISTS (SELECT 1 FROM events e WHERE e.type = 'slack_gate_posted'
                                        AND e.data->>'approval_id' = a.id::text) AS notified
                       FROM approvals a JOIN runs r ON r.id = a.run_id
                       WHERE a.status = 'pending' ORDER BY a.requested_at""")
                return [dict(r) for r in rows]
            finally:
                await conn.close()
        return _run(go())

    def recent_events(self, since_id: int) -> list[dict]:
        async def go():
            conn = await self._db()
            try:
                rows = await conn.fetch(
                    """SELECT e.id, e.run_id, e.actor, e.type, e.data, r.slack_channel, r.slack_thread_ts
                       FROM events e JOIN runs r ON r.id = e.run_id
                       WHERE e.id > $1 ORDER BY e.id LIMIT 200""", since_id)
                return [dict(r) for r in rows]
            finally:
                await conn.close()
        return _run(go())

    def max_event_id(self) -> int:
        async def go():
            conn = await self._db()
            try:
                return await conn.fetchval("SELECT coalesce(max(id), 0) FROM events")
            finally:
                await conn.close()
        return int(_run(go()))


def build_app(deps: Deps):
    """The Bolt app with every handler bound. The only slack_bolt import in the module."""
    from slack_bolt import App
    app = App(token=deps.config.bot_token)

    @app.event("app_mention")
    def _mention(event, client):
        handle_mention(event, client, deps)

    @app.action(GATE_ACTION_ID)
    def _gate(ack, body, client):
        handle_gate_action(body, ack, client, deps)

    @app.command("/lantern-rework")
    def _rework(ack, command, respond):
        handle_rework(command, ack, respond, deps)

    @app.command("/lantern-retry")
    def _retry(ack, command, respond):
        handle_retry(command, ack, respond, deps)

    return app


def poll_forever(client, deps, stop: threading.Event, first_event_id: int) -> None:
    since = first_event_id
    while not stop.is_set():
        try:
            notify_pending_gates(client, deps)
            since = relay_events(client, deps, since)
        except Exception as e:                       # noqa: BLE001 — a poll tick must not kill the bridge
            print(f"[slack-bridge] poll error: {type(e).__name__}: {e}", file=sys.stderr)
        stop.wait(deps.config.poll_s)


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv(HERE / ".env")
    load_dotenv(RUNNER / ".env")
    cfg = Config.from_env()
    missing = [n for n, v in (("LANTERN_SLACK_BOT_TOKEN", cfg.bot_token),
                              ("LANTERN_SLACK_APP_TOKEN", cfg.app_token)) if not v]
    if missing:
        sys.exit("slack bridge: set " + ", ".join(missing))
    if not cfg.approvers:
        print("[slack-bridge] LANTERN_SLACK_APPROVERS is empty — gates cannot be decided from Slack "
              "(fail-closed).", file=sys.stderr)
    deps = RealDeps(cfg)
    app = build_app(deps)
    from slack_bolt.adapter.socket_mode import SocketModeHandler
    stop = threading.Event()
    threading.Thread(target=poll_forever, args=(app.client, deps, stop, deps.max_event_id()),
                     daemon=True, name="lantern-slack-poll").start()
    print(f"[slack-bridge] socket mode; approvers={len(cfg.approvers)} operators={len(cfg.operators)} "
          f"gates={','.join(cfg.gates)} channels={','.join(sorted(cfg.channels)) or 'any'}")
    try:
        SocketModeHandler(app, cfg.app_token).start()
    finally:
        stop.set()


if __name__ == "__main__":
    main()
