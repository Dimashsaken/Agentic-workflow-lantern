"""Failed SDK runs keep their available evidence and never silently become success."""

import asyncio
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from agents.exceptions import MaxTurnsExceeded
import factory as f
import orchestrator as o
import pipeline as p
from test_factory import Base, RUN, RateLimitError
from test_trace import result, call, output


class ExecutionJournal(Base):
    def journal(self):
        return f.ExecutionJournal(RUN, "06-security", "key", "instructions", "begin")

    def partial_error(self, kind=MaxTurnsExceeded):
        err = kind("API_TOKEN=SecretToken987")
        err.run_data = result([call("read_file", '{"path":"product/app.py"}', "a"),
                               output("source", "a")], inp=200, out=20)
        return err

    def trace(self):
        return json.loads(f.trace_path(RUN, "06-security", "key").read_text())

    def test_completed_and_partial_usage_survive_a_later_failure(self):
        journal = self.journal()

        async def scenario():
            await journal.attempt(AsyncMock(return_value=result([], inp=100, out=10)))
            await journal.attempt(AsyncMock(side_effect=self.partial_error()))

        with redirect_stderr(io.StringIO()), self.assertRaises(MaxTurnsExceeded):
            asyncio.run(scenario())
        trace = self.trace()
        self.assertEqual(trace["usage"]["input_tokens"], 300)
        self.assertEqual(trace["usage"]["output_tokens"], 30)
        self.assertEqual(trace["tool_calls"][0]["name"], "read_file")
        self.assertEqual(trace["failure"]["class"], "terminal")
        self.assertNotIn("SecretToken987", json.dumps(trace))
        self.assertFalse(trace["usage_incomplete"])

    def test_unknown_failed_usage_stays_unknown(self):
        journal = self.journal()
        with redirect_stderr(io.StringIO()), self.assertRaises(RuntimeError):
            asyncio.run(journal.attempt(AsyncMock(side_effect=RuntimeError("transport lost"))))
        self.assertEqual(self.trace()["usage"], {})
        self.assertTrue(self.trace()["usage_incomplete"])

    def test_same_exception_is_not_accounted_twice_at_outer_boundary(self):
        journal = self.journal()
        err = self.partial_error()
        with redirect_stderr(io.StringIO()):
            journal.failed(err)
            journal.failed(err, model_attempt=False)
        self.assertEqual(journal.usage["input_tokens"], 200)

    def test_transport_retry_after_tool_calls_is_not_blind_replay(self):
        invoke = AsyncMock(side_effect=self.partial_error(RateLimitError))
        sleep = AsyncMock()
        with self.assertRaises(RateLimitError):
            asyncio.run(f.with_retry(invoke, attempts=3, sleep=sleep))
        self.assertEqual(invoke.await_count, 1)
        sleep.assert_not_called()

    def test_transport_retry_before_tools_still_recovers(self):
        err = RateLimitError("429")
        invoke = AsyncMock(side_effect=[err, result([], inp=50)])
        journal = self.journal()
        with redirect_stderr(io.StringIO()):
            asyncio.run(f.with_retry(lambda: journal.attempt(invoke), sleep=AsyncMock(), attempts=1))
        self.assertEqual(journal.usage["input_tokens"], 50)
        self.assertNotIn("failure", self.trace())
        self.assertTrue(self.trace()["usage_incomplete"])

    def test_inprocess_executor_records_usage_before_propagating_failure(self):
        conn = AsyncMock()
        conn.fetchval.side_effect = [1, 42]
        err = self.partial_error()
        ledger = AsyncMock()
        with patch.object(p, "REPO", f.REPO), patch.object(o, "REPO", f.REPO), \
             patch.object(p, "render_role_memory", AsyncMock()), \
             patch.object(p, "product_target", AsyncMock(return_value=("", "main"))), \
             patch.object(p.SQLAlchemySession, "from_url", return_value=None), \
             patch.object(p, "db_urls", return_value=("unused", "unused")), \
             patch.object(p, "check_stage_inputs", return_value=None), \
             patch.object(p, "model_for", return_value="test-deployment"), \
             patch.object(p, "build_instructions", return_value="test instructions"), \
             patch.object(p.Runner, "run", AsyncMock(side_effect=err)), \
             patch.object(p, "record_usage", ledger), redirect_stderr(io.StringIO()):
            with self.assertRaises(MaxTurnsExceeded):
                asyncio.run(p.run_agent_stage(conn, RUN, "06-security", "local"))
        ledger.assert_awaited_once()
        self.assertEqual(ledger.call_args.args[2]["input_tokens"], 200)
        trace = f.read_trace(RUN, "06-security", f"{RUN}:06-security:1")
        self.assertEqual(trace["failure"]["type"], "MaxTurnsExceeded")

    def test_container_executor_emits_known_usage_on_failure(self):
        conn = AsyncMock()
        stdout = io.StringIO()
        with patch.object(o, "REPO", f.REPO), \
             patch.object(o.sys, "argv", ["orchestrator.py", RUN, "06-security", "--execution-key", "key"]), \
             patch.object(o, "db_connect", AsyncMock(return_value=conn)), \
             patch.object(o, "azure_v1_client", return_value=None), \
             patch.object(o, "set_default_openai_client"), \
             patch.object(o, "render_role_memory", AsyncMock()), \
             patch.object(o, "model_for", return_value="test-deployment"), \
             patch.object(o, "build_instructions", return_value="test instructions"), \
             patch.object(o.Runner, "run", AsyncMock(side_effect=self.partial_error())), \
             redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            with self.assertRaises(MaxTurnsExceeded):
                asyncio.run(o.main())
        usage = p.parse_usage_line(stdout.getvalue())
        self.assertEqual(usage["input_tokens"], 200)
        self.assertEqual(usage["model"], "test-deployment")
        self.assertEqual(self.trace()["failure"]["type"], "MaxTurnsExceeded")
        conn.close.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
