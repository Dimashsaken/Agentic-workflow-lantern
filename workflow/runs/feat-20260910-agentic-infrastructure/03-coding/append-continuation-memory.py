"""New review learnings, same actual tool and honest manual identities."""
import asyncio
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("restore_memory", Path(__file__).with_name("restore-memory.py"))
memory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(memory)
memory.PENDING = {
    "qa-dev": "2026-09-10: Verify scenario timestamps against decoded video frames because a Playwright context wall timer may start before captured media, producing offsets outside the final recording.",
    "security": "2026-09-10: A cleanup eligibility check is not a concurrency boundary; worker allocation, launch and retirement must share an exclusion lock and irreversible tombstone, because a delayed start can mount a path after cleanup has inspected it.",
}
asyncio.run(memory.main("continuation3-memory.json"))
