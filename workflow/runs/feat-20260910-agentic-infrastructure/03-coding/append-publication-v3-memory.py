"""Persist the reviewed split-effect learning via the actual memory tool."""
import asyncio
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("restore_memory", Path(__file__).with_name("restore-memory.py"))
memory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(memory)
memory.PENDING = {
    "coding": "2026-09-11: A missing child intent only proves an external action never started when every version of the parent protocol required that intent first; version new protocols and hold older aggregate attempts rather than retrofit this absence proof.",
    "post-coding": "2026-09-11: Absence of a per-action intent permits first execution only when every version of that protocol persists intent before its external call; legacy aggregate records and lost intent responses must remain held because absence of a provider result cannot prove the operation never started.",
}
asyncio.run(memory.main("publication-v3-memory.json"))
