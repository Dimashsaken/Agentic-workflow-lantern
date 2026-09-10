"""Record pending engineering learnings through the real bound SDK tool.

Uses the existing configured database. Never creates schema, executions or approvals.
"""
import asyncio
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools/azure-runner"))
import orchestrator
import execution_runtime
from agents.tool_context import ToolContext

PENDING = {
    "coding": "2026-09-10: Before/after source hashes cannot prove which mutable code a test executed; use a separate read-only committed snapshot and a modify/test/restore negative control.",
    "qa-dev": "2026-09-10: Pair negative provenance tests with a matching controller receipt and forged writable mirror, because an always-unverified UI can falsely pass negative checks without ever displaying valid evidence.",
    "post-coding": "2026-09-10: Review optional lifecycle protections at every public entry point, including manual commands, and place durable success after resource cleanup and authoritative completion; disabling a scheduler path or finishing model turns alone does not establish the execution boundary.",
    "security": "2026-09-10: Before/after source hashes cannot establish what a test executed when that source remains writable; use a separate read-only committed snapshot and separately fence every future-authoritative write, including role memory.",
    "pre-coding": "2026-09-10: Model maintenance leases separately from stage-dispatch leases when maintenance runs after approval, because reusing an executing-run predicate can require changing pending-gate state and silently grant pipeline authority.",
}


async def main():
    if execution_runtime.enabled():
        raise RuntimeError("Manual engineering memory must not impersonate a leased stage")
    url = orchestrator.db_urls()[1]
    target = urlsplit(url)
    if target.hostname not in {"localhost", "127.0.0.1", "::1"} or target.port != 5432:
        raise RuntimeError("This recovery record is only for the configured localhost:5432 database")
    conn = await orchestrator.asyncpg.connect(url, timeout=8)
    try:
        identity = dict(await conn.fetchrow("SELECT current_database() AS database, current_setting('server_version') AS version, current_setting('data_directory') AS data_directory"))
        before = {table: await conn.fetchval(f"SELECT count(*) FROM {table}") for table in ("runs", "stage_executions", "approvals", "role_memory")}
        if not before["runs"] or not before["stage_executions"]:
            raise RuntimeError("Existing populated Lantern database required")
        approvals_before = await conn.fetchval("SELECT md5(coalesce(jsonb_agg(to_jsonb(a) ORDER BY id)::text,'')) FROM approvals a")
        entries = []
        for role, entry in PENDING.items():
            key = f"manual:feat-20260910-agentic-infrastructure:{role}:pending-{hashlib.sha256(entry.encode()).hexdigest()[:12]}"
            found = await conn.fetchrow("SELECT id, execution_key FROM role_memory WHERE execution_key=$1 AND entry=$2", key, entry)
            if found is None:
                tool = orchestrator.make_append_memory(role, "feat-20260910-agentic-infrastructure", "manual-engineering-continuation", key)
                arguments = json.dumps({"entry": entry})
                context = ToolContext(context=None, tool_name="append_memory", tool_call_id=key, tool_arguments=arguments)
                result = await tool.on_invoke_tool(context, arguments)
                if result != "memory entry recorded":
                    raise RuntimeError("append_memory did not confirm insertion")
                found = await conn.fetchrow("SELECT id, execution_key FROM role_memory WHERE execution_key=$1 AND entry=$2", key, entry)
            entries.append({"role": role, **dict(found), "tool": "append_memory", "fleet_stage": False})
        after = {table: await conn.fetchval(f"SELECT count(*) FROM {table}") for table in before}
        approvals_after = await conn.fetchval("SELECT md5(coalesce(jsonb_agg(to_jsonb(a) ORDER BY id)::text,'')) FROM approvals a")
        record = {"recorded_at": datetime.now(timezone.utc).isoformat(), "environment": "existing configured local PostgreSQL; not disposable; not a production certification", "identity": identity, "counts_before": before, "counts_after": after, "approval_snapshot_unchanged": approvals_before == approvals_after, "memory": entries, "migration_applied": False, "new_cluster_created": False}
        Path(__file__).with_name("configured-postgres-restored.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(record, indent=2))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
