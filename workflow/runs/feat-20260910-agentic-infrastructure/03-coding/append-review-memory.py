"""Append independent review learning using the actual bound tool."""
import asyncio
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("restore_memory", Path(__file__).with_name("restore-memory.py"))
memory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(memory)
memory.PENDING = {
    "coding": "2026-09-10: Persist immutable provider identity, base revision, and the observed old remote ref before publication; a confirmed local effect receipt is insufficient after a provider ref or PR moves, so reobserve before reuse and before opening the human gate.",
    "post-coding": "2026-09-10: Publication receipts, artifacts and success events must share the final target-and-fence acceptance transaction; provider success followed by a changed destination must leave a held intent rather than independently accepted local success evidence.",
}
asyncio.run(memory.main("continuation3-final-memory.json"))
