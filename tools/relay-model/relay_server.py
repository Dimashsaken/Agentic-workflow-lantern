"""A stand-in model endpoint: OpenAI-compatible chat completions that RELAY every
request to a directory and wait for whoever answers — a person at a terminal or another
agent — so a pipeline stage can be driven end to end without a model provider.

    python tools/relay-model/relay_server.py --dir ~/.lantern/relay --port 4141

Point the harness at it (nothing in the harness changes — it is the same Agents SDK
code path the Azure deployments use, minus the provider):

    AZURE_OPENAI_ENDPOINT=http://127.0.0.1:4141   AZURE_OPENAI_API_KEY=relay
    LANTERN_OPENAI_API=chat_completions            LANTERN_MODEL_REASONING=relay-brain
    LANTERN_MODEL_TIMEOUT_S=3600                   # a hand-driven turn is slow

What this is FOR: validating the factory's mechanics (tool policy, envelopes, gates,
postconditions, publication) with a brain you control, debugging a stage prompt
without spending Azure credits, and demonstrating a stage turn by turn. What it is
NOT: a model provider (D7 stands — every fleet brain is an Azure OpenAI deployment).

Protocol (files under --dir):
  inbox/<seq>.json      the full request as the SDK sent it (messages, tools, …)
  inbox/<seq>.view.md   a compact rendering of what is NEW since the last reply
  inbox/system-<h>.md   the system prompt, written once per distinct prompt
  inbox/tools-<h>.json  the tool schemas, written once per distinct tool set
  outbox/<seq>.json     the answer: {"content": "...", "tool_calls": [{"name", "arguments"}]}
The server blocks until outbox/<seq>.json exists, then returns it as a chat completion.
A request the SDK retries (same messages) reuses its sequence number, so a slow answer
is never answered twice. relay_brain.py is the matching command-line client.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

VIEW_CHARS = int(os.environ.get("RELAY_VIEW_CHARS", "6000"))


def _h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


class Relay:
    def __init__(self, root: Path, max_wait_s: float) -> None:
        self.root = root
        self.inbox = root / "inbox"
        self.outbox = root / "outbox"
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.outbox.mkdir(parents=True, exist_ok=True)
        self.state_path = root / "state.json"
        self.max_wait_s = max_wait_s
        self.state = {"seq": 0, "pending": {}}
        if self.state_path.is_file():
            try:
                self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
            except ValueError:
                pass
        self.lock = asyncio.Lock()

    def _save(self) -> None:
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state), encoding="utf-8")
        tmp.replace(self.state_path)

    # ── rendering ────────────────────────────────────────────────────────────
    def _render_view(self, seq: int, body: dict, sys_ref: str, tools_ref: str, new_tools: bool) -> str:
        msgs = body.get("messages", [])
        tools = body.get("tools") or []
        # New = everything after the last assistant message (that was our previous reply).
        last_assistant = max((i for i, m in enumerate(msgs) if m.get("role") == "assistant"), default=-1)
        fresh = msgs[last_assistant + 1:] if last_assistant >= 0 else [m for m in msgs if m.get("role") != "system"]
        out = [f"# request {seq}", f"- model: {body.get('model')}  messages: {len(msgs)}  tools: {len(tools)}",
               f"- system prompt: {sys_ref}", f"- tool schemas: {tools_ref}" + ("  (NEW — read them)" if new_tools else "")]
        if tools:
            out.append("- tool names: " + ", ".join(t.get("function", {}).get("name", "?") for t in tools))
        if last_assistant >= 0:
            prev = msgs[last_assistant]
            calls = prev.get("tool_calls") or []
            out.append(f"\n## your previous reply (message {last_assistant})")
            if prev.get("content"):
                out.append(str(prev["content"])[:800])
            for c in calls:
                fn = c.get("function", {})
                out.append(f"- called {fn.get('name')} (id {c.get('id')}) args: {str(fn.get('arguments'))[:300]}")
        out.append(f"\n## new messages ({len(fresh)})")
        for i, m in enumerate(fresh, start=last_assistant + 1):
            role = m.get("role")
            content = m.get("content")
            if isinstance(content, list):
                content = "\n".join(str(p.get("text", p)) if isinstance(p, dict) else str(p) for p in content)
            content = "" if content is None else str(content)
            note = ""
            if len(content) > VIEW_CHARS:
                note = f"\n… [truncated: {len(content)} chars total — `relay_brain.py show {seq} --message {i}` for all of it]"
                content = content[:VIEW_CHARS]
            head = f"### [{i}] {role}"
            if role == "tool":
                head += f" (tool_call_id {m.get('tool_call_id')})"
            out.append(head)
            out.append(content + note)
        return "\n".join(out) + "\n"

    # ── the request/response cycle ───────────────────────────────────────────
    async def handle(self, body: dict) -> dict:
        msgs = body.get("messages", [])
        fingerprint = _h(json.dumps(msgs, sort_keys=True, ensure_ascii=False))
        async with self.lock:
            seq = self.state["pending"].get(fingerprint)
            if seq is None:
                self.state["seq"] += 1
                seq = self.state["seq"]
                self.state["pending"][fingerprint] = seq
                sys_text = next((str(m.get("content") or "") for m in msgs if m.get("role") == "system"), "")
                sys_ref = "(none)"
                if sys_text:
                    sp = self.inbox / f"system-{_h(sys_text)}.md"
                    if not sp.is_file():
                        sp.write_text(sys_text, encoding="utf-8")
                    sys_ref = f"{sp}  ({len(sys_text)} chars)"
                tools = body.get("tools") or []
                tools_text = json.dumps(tools, indent=1, ensure_ascii=False)
                tp = self.inbox / f"tools-{_h(tools_text)}.json"
                new_tools = not tp.is_file()
                if new_tools:
                    tp.write_text(tools_text, encoding="utf-8")
                (self.inbox / f"{seq:04d}.json").write_text(
                    json.dumps(body, indent=1, ensure_ascii=False), encoding="utf-8")
                (self.inbox / f"{seq:04d}.view.md").write_text(
                    self._render_view(seq, body, sys_ref, str(tp), new_tools), encoding="utf-8")
                self._save()
                print(f"[relay] request {seq} ({len(msgs)} messages) waiting for an answer", flush=True)
        answer = self.outbox / f"{seq:04d}.json"
        deadline = time.monotonic() + self.max_wait_s
        while not answer.is_file():
            if time.monotonic() > deadline:
                return {"error": {"message": f"relay: no answer for request {seq} within {self.max_wait_s:.0f}s",
                                  "type": "relay_timeout"}}
            await asyncio.sleep(0.5)
        try:
            out = json.loads(answer.read_text(encoding="utf-8"))
        except ValueError as e:
            return {"error": {"message": f"relay: outbox/{seq:04d}.json is not valid JSON: {e}", "type": "relay_bad_answer"}}
        calls = []
        for i, c in enumerate(out.get("tool_calls") or []):
            args = c.get("arguments", {})
            calls.append({"id": f"call_{seq}_{i}", "type": "function",
                          "function": {"name": c["name"],
                                       "arguments": args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)}})
        content = out.get("content")
        message: dict = {"role": "assistant", "content": content if content else (None if calls else "")}
        if calls:
            message["tool_calls"] = calls
        prompt_tokens = max(1, len(json.dumps(msgs, ensure_ascii=False)) // 4)
        completion_tokens = max(1, len(json.dumps(out, ensure_ascii=False)) // 4)
        print(f"[relay] request {seq} answered: {len(calls)} tool call(s)"
              + (", final text" if not calls else ""), flush=True)
        return {"id": f"relay-{seq}", "object": "chat.completion", "created": int(time.time()),
                "model": body.get("model", "relay"),
                "choices": [{"index": 0, "message": message,
                             "finish_reason": "tool_calls" if calls else "stop"}],
                "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                          "total_tokens": prompt_tokens + completion_tokens}}


def build_app(relay: Relay) -> FastAPI:
    app = FastAPI(title="lantern relay model")

    @app.post("/openai/v1/chat/completions")
    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        body = await request.json()
        if body.get("stream"):
            return JSONResponse({"error": {"message": "relay: streaming is not supported", "type": "relay_unsupported"}}, 400)
        result = await relay.handle(body)
        if "error" in result:
            return JSONResponse(result, 503)
        return result

    @app.get("/openai/v1/models")
    @app.get("/v1/models")
    async def models():
        return {"object": "list", "data": [{"id": "relay-brain", "object": "model"}]}

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok", "seq": relay.state["seq"]}

    return app


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dir", default=os.environ.get("RELAY_DIR", str(Path.home() / ".lantern" / "relay")))
    ap.add_argument("--port", type=int, default=int(os.environ.get("RELAY_PORT", "4141")))
    ap.add_argument("--max-wait", type=float, default=float(os.environ.get("RELAY_MAX_WAIT_S", "3500")),
                    help="seconds to wait for an answer before returning a 503 (the SDK retries)")
    a = ap.parse_args()
    import uvicorn
    relay = Relay(Path(a.dir).expanduser().resolve(), a.max_wait)
    print(f"[relay] serving on http://127.0.0.1:{a.port}/openai/v1 — inbox at {relay.inbox}", flush=True)
    uvicorn.run(build_app(relay), host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
