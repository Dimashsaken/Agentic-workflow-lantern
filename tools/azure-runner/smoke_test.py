"""Azure OpenAI smoke test: list the resource's deployments, then run one tiny
completion against each (or against one named as an argument).

    .venv/Scripts/python smoke_test.py [deployment-name]
"""

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from orchestrator import azure_v1_client  # noqa: E402


async def main() -> None:
    client = azure_v1_client()

    if len(sys.argv) > 1:
        names = sys.argv[1:]
    else:
        # models.list() returns Azure's whole catalog, not this resource's deployments
        # (verified 2026-08-25: 207 entries, one real deployment). Probe only the
        # configured routing by default; pass names as args to probe others.
        import os
        names = sorted({os.environ.get("LANTERN_MODEL_REASONING", ""),
                        os.environ.get("LANTERN_MODEL_FAST", "")} - {""})
        if not names:
            print("No LANTERN_MODEL_* set and no names given; nothing to probe.")
            return

    for name in names:
        try:
            r = await client.chat.completions.create(
                model=name,
                messages=[{"role": "user", "content": "Reply with exactly: pong"}],
                max_completion_tokens=200,
            )
            print(f"[OK]   {name}: {r.choices[0].message.content!r}")
        except Exception as e:  # noqa: BLE001 — report and continue probing
            print(f"[FAIL] {name}: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
