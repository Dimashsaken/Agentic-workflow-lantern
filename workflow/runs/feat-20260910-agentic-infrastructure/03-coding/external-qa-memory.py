"""Record manual-engineering learnings through the actual bound memory tool."""
import asyncio
import importlib.util
from pathlib import Path
import sys
from dotenv import load_dotenv

load_dotenv(Path(sys.argv[1]))
spec = importlib.util.spec_from_file_location('restore_memory', Path(__file__).with_name('restore-memory.py'))
memory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(memory)
memory.PENDING = {
    'coding': '2026-09-11: Join a periodic authority check before a final check reuses its database connection; cancellation must stop owned recorder processes before joining a launcher that can wait for process exit.',
    'qa-dev': '2026-09-11: Root access through snap SSM does not guarantee permission to signal a distro-profiled packet observer; use bounded self-termination and independently verify cleanup, because a successful denial probe can otherwise leave its owned namespaces alive.',
    'post-coding': '2026-09-11: Cleanup must attempt every independently owned resource after a stop or inspect failure, aggregate errors and retain a failed outcome on uncertainty, because the first diagnostic failure must not skip unrelated resource cleanup.',
    'security': '2026-09-11: Exported-symbol equality does not preserve documented error-recovery semantics; a local dependency mitigation must record its behavior change, bind provenance to actual installed bytes and retain the distro advisory separately from the reviewed mitigation.',
}
asyncio.run(memory.main('external-qa-memory.json'))
