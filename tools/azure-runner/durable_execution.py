"""Fsynced SDK diagnostics outside worker mounts; never an SDK replay journal.

Completed provider responses are metered individually. A missing response or an
unfinished tool call remains unknown after death. No prompt, arguments, tool
output or credential is needed to establish that boundary.
"""
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone

from agents import RunHooks
from tool_policy import confined


def enabled():
    return os.environ.get("LANTERN_EXECUTION_LEASES") == "1" or os.environ.get("LANTERN_DURABLE_DIAGNOSTICS") == "1"


def directory():
    root = Path(os.environ.get("LANTERN_DIAGNOSTICS_DIR", str(Path.home() / ".lantern" / "diagnostics"))).resolve()
    import tool_execution
    worker = tool_execution.CURRENT.get()
    if worker:
        for mount in (worker.product_root, worker.output_root):
            if root.is_relative_to(mount) or mount.is_relative_to(root):
                raise ValueError("diagnostics authority overlaps a worker mount")
    root.mkdir(parents=True, exist_ok=True)
    return root


class DurableHooks(RunHooks):
    def __init__(self, run_id, execution_key, on_usage=None, root=None):
        self.run_id, self.execution_key = run_id, execution_key
        self.on_usage = on_usage
        self.usage = {}
        self.seen = set()
        self.sequence = 0
        root = Path(root) if root else directory()
        root.mkdir(parents=True, exist_ok=True)
        self.path = confined(root, (hashlib.sha256(execution_key.encode()).hexdigest() + ".jsonl",))
        # New attempt keys are mandatory; never append to a previous process's
        # identity or treat its serialized history as safe to resume.
        with self.path.open("xb") as out:
            out.flush()
            os.fsync(out.fileno())
        self.write("execution_started", sdk_replay=False)

    def write(self, kind, **data):
        self.sequence += 1
        row = {"run_id": self.run_id, "execution_key": self.execution_key,
               "sequence": self.sequence, "at": datetime.now(timezone.utc).isoformat(),
               "kind": kind, **data}
        with self.path.open("ab") as out:
            out.write(json.dumps(row, allow_nan=False).encode() + b"\n")
            out.flush()
            os.fsync(out.fileno())

    async def on_llm_start(self, context, agent, system_prompt, input_items):
        self.write("model_started")

    async def on_llm_end(self, context, agent, response):
        response_id = getattr(response, "response_id", None)
        if response_id and response_id in self.seen:
            return
        usage = getattr(response, "usage", None)
        values = {}
        for key in ("requests", "input_tokens", "output_tokens", "total_tokens"):
            value = getattr(usage, key, None)
            if type(value) is int and value >= 0:
                values[key] = value
        cached = getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", None)
        if type(cached) is int and cached >= 0:
            values["cached_input_tokens"] = cached
        self.write("model_completed", response_id=response_id, usage=values)
        if response_id:
            self.seen.add(response_id)
        for key, value in values.items():
            self.usage[key] = self.usage.get(key, 0) + value
        if self.on_usage and values:
            await self.on_usage(dict(self.usage))

    async def on_tool_start(self, context, agent, tool):
        self.write("tool_started", name=tool.name, call_id=getattr(context, "tool_call_id", None))

    async def on_tool_end(self, context, agent, tool, result):
        self.write("tool_completed", name=tool.name, call_id=getattr(context, "tool_call_id", None))

    def finish(self, succeeded):
        self.write("execution_finished", succeeded=bool(succeeded), usage=self.usage)


def read_diagnostics(path):
    """Recover complete durable rows, tolerating only a torn final append."""
    rows = []
    raw = Path(path).read_bytes()
    lines = raw.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if not line.endswith(b"\n") and index == len(lines) - 1:
            break
        row = json.loads(line)
        if row.get("sequence") != len(rows) + 1:
            raise ValueError("diagnostic sequence is not contiguous")
        if rows and (row.get("run_id"), row.get("execution_key")) != (rows[0]["run_id"], rows[0]["execution_key"]):
            raise ValueError("diagnostic execution identity changed")
        rows.append(row)
    usage = {}
    for row in rows:
        if row["kind"] == "model_completed":
            for key, value in row["usage"].items():
                usage[key] = usage.get(key, 0) + value
    return {"rows": rows, "usage": usage,
            "incomplete": not rows or rows[-1]["kind"] != "execution_finished"}
