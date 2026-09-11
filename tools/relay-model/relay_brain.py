"""Command-line client for relay_server.py — how a person or another agent answers the
harness's model requests, one turn at a time.

    relay_brain.py [--dir D] wait [--timeout S]        block until a request needs an answer; print its view
    relay_brain.py [--dir D] show <seq> [--message N] [--tools] [--all]
    relay_brain.py [--dir D] reply <seq> [--text "…"] [--call NAME ARGS]...
    relay_brain.py [--dir D] status

ARGS is a JSON object, or @path to a file holding one. Inside it, a string value of the
form "@@path" is replaced by that file's content — the way to hand a long file body to
write_file without escaping it on a command line. Several --call flags in one reply are
executed by the harness in parallel and their results come back together.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


def _root(a) -> Path:
    return Path(a.dir).expanduser().resolve()


def _pending(root: Path) -> list[int]:
    inbox, outbox = root / "inbox", root / "outbox"
    if not inbox.is_dir():
        return []
    seqs = sorted(int(p.stem) for p in inbox.glob("[0-9][0-9][0-9][0-9].json"))
    return [s for s in seqs if not (outbox / f"{s:04d}.json").is_file()]


def cmd_wait(a) -> int:
    root = _root(a)
    deadline = time.monotonic() + a.timeout
    while True:
        pend = _pending(root)
        if pend:
            seq = pend[0]
            print((root / "inbox" / f"{seq:04d}.view.md").read_text(encoding="utf-8"))
            return 0
        if time.monotonic() > deadline:
            print(f"no request pending after {a.timeout:.0f}s — the stage has ended, or the harness is still working")
            return 3
        time.sleep(1.0)


def cmd_show(a) -> int:
    root = _root(a)
    body = json.loads((root / "inbox" / f"{a.seq:04d}.json").read_text(encoding="utf-8"))
    if a.tools:
        for t in body.get("tools") or []:
            fn = t.get("function", {})
            print(f"## {fn.get('name')}\n{fn.get('description', '')}\n{json.dumps(fn.get('parameters', {}), indent=1)}\n")
        return 0
    msgs = body.get("messages", [])
    picks = range(len(msgs)) if a.all else ([a.message] if a.message is not None else [len(msgs) - 1])
    for i in picks:
        m = msgs[i]
        content = m.get("content")
        if isinstance(content, list):
            content = "\n".join(str(p.get("text", p)) if isinstance(p, dict) else str(p) for p in content)
        print(f"### [{i}] {m.get('role')}" + (f" (tool_call_id {m.get('tool_call_id')})" if m.get("tool_call_id") else ""))
        print("" if content is None else str(content))
        for c in m.get("tool_calls") or []:
            print(f"- tool_call {c.get('id')}: {c.get('function', {}).get('name')} {c.get('function', {}).get('arguments')}")
        print()
    return 0


def _load_args(raw: str) -> dict:
    text = Path(raw[1:]).read_text(encoding="utf-8") if raw.startswith("@") else raw
    args = json.loads(text)
    if not isinstance(args, dict):
        raise SystemExit("tool arguments must be a JSON object")
    for k, v in list(args.items()):
        if isinstance(v, str) and v.startswith("@@"):
            args[k] = Path(v[2:]).read_text(encoding="utf-8")
    return args


def cmd_reply(a) -> int:
    root = _root(a)
    target = root / "outbox" / f"{a.seq:04d}.json"
    if target.is_file():
        print(f"request {a.seq} is already answered", file=sys.stderr)
        return 2
    if not (root / "inbox" / f"{a.seq:04d}.json").is_file():
        print(f"no request {a.seq} in the inbox", file=sys.stderr)
        return 2
    calls = [{"name": name, "arguments": _load_args(raw)} for name, raw in (a.call or [])]
    if not calls and not a.text:
        print("a reply needs --text and/or at least one --call", file=sys.stderr)
        return 2
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps({"content": a.text or "", "tool_calls": calls}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    tmp.replace(target)
    print(f"answered request {a.seq}: {len(calls)} tool call(s)" + (" + text" if a.text else ""))
    return 0


def cmd_status(a) -> int:
    root = _root(a)
    inbox = root / "inbox"
    seqs = sorted(int(p.stem) for p in inbox.glob("[0-9][0-9][0-9][0-9].json")) if inbox.is_dir() else []
    pend = set(_pending(root))
    for s in seqs:
        print(f"{s:04d}  {'PENDING' if s in pend else 'answered'}")
    if not seqs:
        print("no requests yet")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="answer relay_server.py requests")
    ap.add_argument("--dir", default=os.environ.get("RELAY_DIR", str(Path.home() / ".lantern" / "relay")))
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("wait"); p.add_argument("--timeout", type=float, default=900)
    p = sub.add_parser("show"); p.add_argument("seq", type=int); p.add_argument("--message", type=int)
    p.add_argument("--tools", action="store_true"); p.add_argument("--all", action="store_true")
    p = sub.add_parser("reply"); p.add_argument("seq", type=int); p.add_argument("--text", default="")
    p.add_argument("--call", nargs=2, action="append", metavar=("NAME", "ARGS"))
    sub.add_parser("status")
    a = ap.parse_args(argv)
    return {"wait": cmd_wait, "show": cmd_show, "reply": cmd_reply, "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
