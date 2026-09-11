"""Invoke actual bound append_memory tools on the existing configured database."""
import asyncio
import importlib.util
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv(Path(os.environ['LANTERN_EXISTING_ENV_FILE']))
folder=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('actual_memory',folder/'restore-memory.py')
memory=importlib.util.module_from_spec(spec);spec.loader.exec_module(memory)
memory.PENDING={
 'coding':'2026-09-11: A repair tested with a scripted child can still fail in the real stage handoff; exercise artifact writes with every ownership flag and verify the child clone retains the exact base ref before treating parent-loop tests as end-to-end evidence.',
 'qa-dev':'2026-09-11: Probe cancellation a second time while recorder shutdown is still pending, because receipt validation alone cannot show that an interrupted writer has quiesced before the controller returns.',
 'post-coding':'2026-09-11: A bounded historical-path index must preserve the write protocol across rollback and mixed-version writers; a permanent completeness marker can silently lose ancestor protection after a legacy writer adds a path. Keep registry locks out of slow clone work, and validate final maintenance changes against the inherited scope rather than a reread plan. Compatibility metadata can reject an old reader yet still change which OS lock newer readers acquire; keep each execution lock identity permanent.',
 'security':'2026-09-11: Validate proxy preconnect and TLS-denial hooks against the exact packaged core, because request-header address edits can be replaced during server allocation and setting a client error in ClientHello may not stop TLS. A patched dependency resolver is separate evidence from actual hook and host packet-denial acceptance.'
}
asyncio.run(memory.main('c3-foundation-memory.json'))
