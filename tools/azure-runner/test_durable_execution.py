"""Durable SDK hook controls; subprocess kill is real, model objects are fixtures."""
import asyncio
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace as NS

import durable_execution as d


class Diagnostics(unittest.IsolatedAsyncioTestCase):
    async def test_response_deduplication_and_missing_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            observed = []
            async def save(value):
                observed.append(value)
            hooks = d.DurableHooks("run", "run:stage:1", save, tmp)
            response = NS(response_id="r1", usage=NS(requests=1, input_tokens=17,
                          output_tokens=3, total_tokens=20))
            await hooks.on_llm_start(None, None, "private prompt", [])
            await hooks.on_llm_end(None, None, response)
            await hooks.on_llm_end(None, None, response)
            await hooks.on_llm_end(None, None, NS(response_id="r2", usage=None))
            data = d.read_diagnostics(hooks.path)
            self.assertEqual(data["usage"]["input_tokens"], 17)
            self.assertEqual(len(observed), 1)
            self.assertTrue(data["incomplete"])
            self.assertNotIn("private prompt", hooks.path.read_text())
            hooks.finish(False)
            self.assertFalse(d.read_diagnostics(hooks.path)["incomplete"])
            with self.assertRaises(FileExistsError):
                d.DurableHooks("run", "run:stage:1", root=tmp)

    async def test_tool_payloads_not_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            hooks = d.DurableHooks("run", "run:stage:1", root=tmp)
            context = NS(tool_call_id="call", tool_arguments="private")
            await hooks.on_tool_start(context, None, NS(name="shell"))
            await hooks.on_tool_end(context, None, NS(name="shell"), "private")
            self.assertNotIn("private", hooks.path.read_text())
            self.assertEqual(d.read_diagnostics(hooks.path)["rows"][-1]["kind"], "tool_completed")

    async def test_real_process_death_preserves_complete_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = """import asyncio, sys, time
from types import SimpleNamespace as N
from durable_execution import DurableHooks
h=DurableHooks('run','killed:1',root=sys.argv[1])
asyncio.run(h.on_llm_end(None,None,N(response_id='fixture',usage=N(requests=1,input_tokens=17))))
h.write('tool_started',name='synthetic-blocking-tool')
print(str(h.path),flush=True)
time.sleep(60)
"""
            child = subprocess.Popen([sys.executable, "-u", "-c", script, tmp],
                                     cwd=Path(__file__).parent, stdout=subprocess.PIPE, text=True)
            try:
                path = Path(await asyncio.to_thread(child.stdout.readline))
                child.kill()
                child.wait(timeout=10)
                result = d.read_diagnostics(str(path).strip())
                self.assertEqual(result["usage"], {"requests": 1, "input_tokens": 17})
                self.assertEqual(result["rows"][-1]["kind"], "tool_started")
                self.assertTrue(result["incomplete"])
            finally:
                if child.poll() is None:
                    child.kill()
                child.wait(timeout=10)
                child.stdout.close()

    async def test_torn_tail_only_and_identity_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            hooks = d.DurableHooks("run", "run:1", root=tmp)
            with hooks.path.open("ab") as out:
                out.write(b'{"partial":')
            self.assertEqual(len(d.read_diagnostics(hooks.path)["rows"]), 1)
            with hooks.path.open("ab") as out:
                out.write(b'\n')
            with self.assertRaises(json.JSONDecodeError):
                d.read_diagnostics(hooks.path)


if __name__ == "__main__":
    unittest.main()
