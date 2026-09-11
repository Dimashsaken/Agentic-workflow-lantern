"""Configured local read-only inventory and actual role-memory tool receipts.

Loads credentials from the existing checkout's .env into this process only.
No schema changes, gate decisions or cleanup.
"""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
sys.path.insert(0,str(ROOT/'tools/azure-runner'))
load_dotenv(Path(os.environ['LANTERN_EXISTING_ENV_FILE']))
spec = importlib.util.spec_from_file_location('memory_receipts', OUT/'restore-memory.py')
memory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(memory)
memory.PENDING = {
 'coding': '2026-09-11: PostgreSQL UPDATE predicates use a statement snapshot even after waiting for a row lock; serialize maintenance and dispatcher ownership on the parent row, then query conflicting child executions in a fresh statement.',
 'security': '2026-09-11: TLS gateway acceptance needs decrypted request and pre-connect permits plus actual host egress denial; a CONNECT allowlist and a successful direct TLS recorder fixture do not establish those boundaries.',
 'post-coding': '2026-09-11: Test optional safety flags independently of neighboring runtime flags; an operator enabling a protected pilot must reach that protected entry point even when the older dispatcher mode remains configured. Retention inventories must include temporary maintenance clones and permanent descriptor growth, because deleting checkout bytes alone does not bound lifecycle overhead.',
 'qa-dev': '2026-09-11: Label redacted recorder command traces separately from replayable Playwright traces, because preventing credential capture removes DOM/network evidence and a one-second video cannot replace that diagnostic detail.'
}


async def main():
    await memory.main('bcd-memory.json')
    import execution_retention
    conn = await memory.orchestrator.asyncpg.connect(memory.orchestrator.db_urls()[1],timeout=8)
    try:
        result = await execution_retention.inventory(conn,Path.home()/'.lantern/product-mirrors/checkouts')
        result.update(environment='existing configured local PostgreSQL; read-only inventory', deleted_paths=0,
                      scope='configured checkout root only; maintenance TemporaryDirectory clones are not yet registered')
        (OUT/'bcd-retention-inventory.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({'entries':len(result['entries']),'known_bytes':result['known_bytes'],'eligible':sum(r['eligible'] for r in result['entries']),'apply':False}))
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
