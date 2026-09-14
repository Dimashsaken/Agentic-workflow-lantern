"""Azure OpenAI smoke test: probe the deployments the model stack routes to (or the
names given as arguments) with one tiny completion each, and say which tier each
deployment serves. Exits 1 when any probe fails, so a deploy recipe can run it as a
preflight before pointing a tier at a name and restarting the daemon.

    .venv/Scripts/python smoke_test.py                              # the configured tiers
    .venv/Scripts/python smoke_test.py gpt-5.6-terra gpt-5.6-luna   # candidates first
"""

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from orchestrator import MODEL_TIERS, ModelStackError, azure_v1_client, deployment_for_tier  # noqa: E402


def configured() -> dict[str, list[str]]:
    """{deployment: [tiers it serves]} from LANTERN_MODEL_* with the fallback chain applied."""
    serves: dict[str, list[str]] = {}
    for tier in MODEL_TIERS:
        serves.setdefault(deployment_for_tier(tier), []).append(tier)
    return serves


async def main() -> int:
    try:
        client = azure_v1_client()
    except ModelStackError as e:
        print(f"[FAIL] {e}")
        return 1

    if len(sys.argv) > 1:
        names = sys.argv[1:]
    else:
        # models.list() returns Azure's whole catalog, not this resource's deployments
        # (verified 2026-08-25: 207 entries, one real deployment). Probe only the
        # configured routing by default; pass names as args to probe others.
        try:
            serves = configured()
        except ModelStackError as e:
            print(f"[FAIL] {e}")
            return 1
        names = sorted(serves)
        for name in names:
            tiers = serves[name]
            print(f"       {name}: {', '.join(tiers)} tier{'s' if len(tiers) > 1 else ''}")

    failed = 0
    for name in names:
        try:
            r = await client.chat.completions.create(
                model=name,
                messages=[{"role": "user", "content": "Reply with exactly: pong"}],
                max_completion_tokens=200,
            )
            print(f"[OK]   {name}: {r.choices[0].message.content!r}")
        except Exception as e:  # noqa: BLE001 — report and continue probing
            failed += 1
            print(f"[FAIL] {name}: {type(e).__name__}: {e}")
    if failed:
        print(f"{failed} of {len(names)} deployment(s) failed — never point a tier at a name that fails.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
