"""DB-backed check for D25 claim routing: a run parked at 01-ui-ux.design is claimed by
the ec2 daemon only in design mode html, and by the workstation daemon only in paper.

    .venv/bin/python integration_design_mode.py     (needs LANTERN_DATABASE_URL + init-db)

Inserts two throwaway runs (ids prefixed `itest-`), claims with both runners, then
deletes them. No agent executes: the claim is rolled back by resetting the status.
"""

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pipeline  # noqa: E402


async def main() -> int:
    conn = await pipeline.connect()
    ids = {"html": "itest-design-html", "paper": "itest-design-paper"}
    try:
        await conn.execute("DELETE FROM events WHERE run_id = ANY($1)", list(ids.values()))
        await conn.execute("DELETE FROM runs WHERE id = ANY($1)", list(ids.values()))
        for mode, rid in ids.items():
            await conn.execute(
                """INSERT INTO runs (id, brief, pipeline_version, current_stage, created_by, design_mode)
                   VALUES ($1, 'itest', $2, '01-ui-ux.design', 'itest', $3)""",
                rid, pipeline.PIPELINE_VERSION, mode)
        failures = []

        async def claim_all(runner: str) -> set[str]:
            """Drain the claim queue; real runs claimed on the way are handed back at
            the end (holding them 'executing' meanwhile so the loop terminates)."""
            got: set[str] = set()
            borrowed: list[str] = []
            try:
                while True:
                    rid = await pipeline.claim_run(conn, runner)
                    if not rid:
                        break
                    if rid.startswith("itest-"):
                        got.add(rid)
                    else:
                        borrowed.append(rid)
            finally:
                if borrowed:
                    await conn.execute("UPDATE runs SET status='running' WHERE id = ANY($1)", borrowed)
            return got

        ec2 = await claim_all("ec2")
        if ec2 != {ids["html"]}:
            failures.append(f"ec2 claimed {sorted(ec2)} — expected only the html run")
        await conn.execute("UPDATE runs SET status='running' WHERE id = ANY($1)", list(ids.values()))
        ws = await claim_all("workstation")
        if ws != {ids["paper"]}:
            failures.append(f"workstation claimed {sorted(ws)} — expected only the paper run")
        for f in failures:
            print("  FAIL ", f)
        if not failures:
            print("  PASS  ec2 claims the html design run, the workstation claims the paper one")
        return 1 if failures else 0
    finally:
        await conn.execute("DELETE FROM events WHERE run_id = ANY($1)", list(ids.values()))
        await conn.execute("DELETE FROM runs WHERE id = ANY($1)", list(ids.values()))
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
