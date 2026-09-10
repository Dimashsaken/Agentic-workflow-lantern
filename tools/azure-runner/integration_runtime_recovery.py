"""Kill a real Azure dispatcher after durable model usage, then fence recovery.

Only the explicitly configured disposable validation database is accepted. Does
not approve gates or replay SDK state. Retains the interrupted workspace/logs.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlparse

import asyncpg
import durable_execution
import execution_leases


async def main(args):
    url = os.environ["LANTERN_VALIDATION_DATABASE_URL"].replace("postgresql+asyncpg:", "postgresql:")
    if not urlparse(url).path.lstrip("/").startswith("lantern_validation"):
        raise ValueError("requires disposable lantern_validation database")
    workspace = Path(args.workspace).resolve()
    if workspace.exists():
        raise ValueError("requires a new workspace")
    workspace.mkdir(parents=True)
    diagnostics = workspace / "diagnostics"
    env = dict(os.environ, LANTERN_EXECUTION_LEASES="1", LANTERN_ISOLATED_TOOLS="1",
               LANTERN_LEASE_TTL="15", LANTERN_DIAGNOSTICS_DIR=str(diagnostics))
    run_id = "feat-20260910-live-inprocess-" + args.tag
    command = [sys.executable, "-u", str(Path(__file__).with_name("integration_validation.py")),
               "--executor", "inprocess", "--workspace", str(workspace / "run"),
               "--tag", args.tag, "--output", str(workspace / "normal-result.json")]
    record = {"kind": "real_azure_controller_kill_and_postgres_recovery", "run_id": run_id,
              "started_at": datetime.now(timezone.utc).isoformat(), "sdk_replay": False}
    conn = await asyncpg.connect(url)
    child = None
    try:
        if await conn.fetchval("SELECT count(*) FROM runs WHERE id NOT LIKE 'feat-20260910-live-%'"):
            raise ValueError("disposable database contains foreign runs")
        with (workspace / "controller.log").open("w", encoding="utf-8") as log:
            child = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 240
            snapshot = None
            while time.monotonic() < deadline:
                for path in diagnostics.glob("*.jsonl"):
                    data = durable_execution.read_diagnostics(path)
                    if data["usage"].get("requests", 0) > 0 and data["incomplete"]:
                        snapshot = (path, data)
                        break
                if snapshot or child.poll() is not None:
                    break
                await asyncio.sleep(.1)
            if snapshot is None or child.poll() is not None:
                raise RuntimeError("no active Azure response boundary observed; inspect retained controller.log")
            child.kill()
            child.wait(timeout=10)
        path, data = snapshot
        harness = workspace / "run/harness"
        record["harness_source_sha256"] = {
            str(path.relative_to(harness)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((harness / "tools/azure-runner").glob("*.py"))}
        # Reload after process death; write completion and DB callback can race
        # with kill, so the fsynced observations are the primary known lower bound.
        data = durable_execution.read_diagnostics(path)
        record["diagnostics"] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                  "usage": data["usage"], "incomplete": data["incomplete"],
                                  "event_kinds": [r["kind"] for r in data["rows"]]}
        before = [dict(r) for r in await conn.fetch("SELECT id,status,requests,input_tokens,output_tokens,total_tokens,idempotency_key FROM stage_executions WHERE run_id=$1", run_id)]
        record["before_recovery"] = before
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            recovered = await execution_leases.recover_expired(conn)
            own = [r for r in recovered if r["run_id"] == run_id]
            if own:
                record["recovery"] = own
                break
            await asyncio.sleep(1)
        record["after_recovery"] = [dict(r) for r in await conn.fetch("SELECT id,status,requests,input_tokens,output_tokens,total_tokens,idempotency_key FROM stage_executions WHERE run_id=$1", run_id)]
        record["gates"] = [dict(r) for r in await conn.fetch("SELECT gate,status,decided_by FROM approvals WHERE run_id=$1", run_id)]
        record["run_status"] = await conn.fetchval("SELECT status FROM runs WHERE id=$1", run_id)
        from isolated_tools import cleanup_execution
        record["cleanup"] = [await asyncio.to_thread(cleanup_execution, r["idempotency_key"]) for r in before]
        record["passed"] = bool(record.get("recovery")) and record["run_status"] == "failed" and not record["gates"] and data["incomplete"] and data["usage"].get("requests", 0) > 0
        record["limits"] = "Unfinished response/tool tail is unknown; persisted usage is a lower bound. Recovery holds for explicit retry; no SDK resumption or external publication was tested."
    finally:
        if child and child.poll() is None:
            child.kill()
            child.wait(timeout=10)
        await conn.close()
        record["finished_at"] = datetime.now(timezone.utc).isoformat()
        Path(args.output).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2))
    return record["passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--tag", required=True)
    raise SystemExit(0 if asyncio.run(main(parser.parse_args())) else 1)
