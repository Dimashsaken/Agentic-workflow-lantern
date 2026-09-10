"""Read-only disposable DB snapshot for authenticated browser QA."""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

import asyncpg


async def main():
    run_id = os.environ["QA_RUN_ID"]
    con = await asyncpg.connect(os.environ["LANTERN_DATABASE_URL"].replace("+asyncpg", ""), timeout=5)
    try:
        async with con.transaction(readonly=True):
            run = await con.fetchrow("SELECT id,status,current_stage,updated_at FROM runs WHERE id=$1", run_id)
            approvals = await con.fetch("SELECT id,gate,status,stage_execution_id,decided_at,decided_by,decision_note FROM approvals WHERE run_id=$1 ORDER BY id", run_id)
            executions = await con.fetch("SELECT id,stage,status,attempt,idempotency_key,input_tokens,output_tokens,total_tokens FROM stage_executions WHERE run_id=$1 ORDER BY id", run_id)
            assert run and run["status"] == "waiting_gate", "Expected waiting_gate run"
            assert len(approvals) == 1 and approvals[0]["gate"] == "story_signoff" and approvals[0]["status"] == "pending", "Expected exactly one pending story signoff"
            result = {"run": dict(run), "approvals": [dict(r) for r in approvals], "executions": [dict(r) for r in executions]}
            out = Path(sys.argv[1])
            result["recorded_at"] = datetime.now(timezone.utc).isoformat()
            runtime = Path(os.environ["QA_HARNESS_ROOT"])
            result["source_sha256"] = {f"tools/mission-control/{n}": hashlib.sha256((runtime / "tools/mission-control" / n).read_bytes()).hexdigest() for n in ("app.py", "ui.py", "traceability.py", "drawer.py")}
            out.write_text(json.dumps(result, default=str, indent=2) + "\n", encoding="utf-8")
            if len(sys.argv) > 2:
                before = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
                assert all(before[k] == json.loads(json.dumps(result, default=str))[k] for k in ("run", "approvals", "executions", "source_sha256")), "Browser changed protected state or runtime source"
            print("Disposable run, execution and pending approval state verified")
    finally:
        await con.close()


asyncio.run(main())
