"""Proof that the session-1 postcondition change is sound under concurrency.

    .venv/Scripts/python test_verification.py     (needs LANTERN_DATABASE_URL + init-db)

Two executions of the SAME role run concurrently: A does real work and records
memory; B writes nothing. The pipeline must fail B.

- The OLD check (pre-2026-08-26) diffed the role's shared memory.md file. A's append
  changes the file, so B's diff also sees a change — B passes having written nothing.
  That is a verification failure, not a data race: the check the pipeline's
  trustworthiness rests on silently stops checking at N>1.
- The NEW check queries role_memory for a row with B's execution_key, which no other
  execution can insert. B fails; A passes. A retry attempt gets a fresh key, so it
  cannot ride on attempt 1's row either.

Keep this file: it is the evidence for why memory lives in Postgres (D10).
"""

import asyncio
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from orchestrator import db_urls  # noqa: E402

ROLE = "test-verification-role"


def old_memory_check(memory_before: str, memory_now: str) -> bool:
    """The pre-session-1 predicate, verbatim logic from check_postconditions:
    'memory appended' == 'the shared file changed since my stage started'."""
    return memory_now != memory_before


async def new_memory_check(conn: asyncpg.Connection, execution_key: str) -> bool:
    """The session-1 predicate: THIS execution inserted at least one row."""
    return bool(await conn.fetchval(
        "SELECT count(*) FROM role_memory WHERE execution_key = $1", execution_key))


async def main() -> None:
    conn = await asyncpg.connect(db_urls()[1])
    failures: list[str] = []

    def check(name: str, ok: bool) -> None:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            failures.append(name)

    try:
        # Two concurrent executions of the same role. A works, B writes nothing.
        key_a = "test-run-A:04-qa-dev:1"
        key_b = "test-run-B:04-qa-dev:1"
        await conn.execute("DELETE FROM role_memory WHERE role = $1", ROLE)

        # ── the old world: one shared memory.md per role ──
        shared_file_before_a = "# memory\n- old entry\n"
        shared_file_before_b = shared_file_before_a          # B started at the same time
        shared_file_now = shared_file_before_a + "- 2026-08-26: A's learning\n"  # only A appended

        print("old check (shared-file diff):")
        check("A (which wrote) passes", old_memory_check(shared_file_before_a, shared_file_now))
        check("B (which wrote NOTHING) also passes — the unsoundness",
              old_memory_check(shared_file_before_b, shared_file_now))

        # ── the new world: rows keyed by execution ──
        await conn.execute(
            """INSERT INTO role_memory (role, run_id, stage, execution_key, entry)
               VALUES ($1, 'test-run-A', '04-qa-dev', $2, 'A''s learning')""", ROLE, key_a)

        print("new check (role_memory row per execution_key):")
        check("A (which wrote) passes", await new_memory_check(conn, key_a))
        check("B (which wrote nothing) FAILS", not await new_memory_check(conn, key_b))
        check("a retry of A (attempt 2, fresh key) cannot reuse attempt 1's row",
              not await new_memory_check(conn, "test-run-A:04-qa-dev:2"))
    finally:
        await conn.execute("DELETE FROM role_memory WHERE role = $1", ROLE)
        await conn.close()

    if failures:
        sys.exit("TEST FAILED: " + "; ".join(failures))
    print("all checks passed — the new postcondition is sound where the old one was not")


if __name__ == "__main__":
    asyncio.run(main())
