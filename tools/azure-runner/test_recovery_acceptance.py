"""Regression controls for independent recovery/security review findings."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import execution_runtime as ownership
import execution_leases as leases
import orchestrator
import pipeline
from agents.tool_context import ToolContext


class Acceptance(unittest.IsolatedAsyncioTestCase):
    async def test_unsupported_legacy_docker_and_babysitter_stop_before_effects(self):
        import review
        with patch.dict(os.environ, {"LANTERN_EXECUTION_LEASES": "1"}), \
             patch.object(pipeline, "_run_agent_stage_docker", AsyncMock()) as docker, \
             patch.object(review, "default_deps") as deps:
            with self.assertRaisesRegex(RuntimeError, "host controller"):
                await pipeline.run_agent_stage_docker(AsyncMock(), "run", "03-coding", "host")
            with self.assertRaisesRegex(RuntimeError, "babysitting is held"):
                await review.babysit_run(AsyncMock(), "run")
            docker.assert_not_awaited()
            deps.assert_not_called()

    async def test_artifact_checks_child_fence_and_stage(self):
        conn = AsyncMock()
        parent = ownership.Ownership(leases.Lease("run", "owner", 3), AsyncMock())
        child = ownership.Ownership(leases.Lease("run", "owner", 1, 42, 3), AsyncMock())
        pt, ct = ownership.RUN.set(parent), ownership.STAGE.set(child)
        seen = []
        @asynccontextmanager
        async def check(conn, lease):
            seen.append(lease)
            yield
        try:
            with patch.dict(os.environ, {"LANTERN_EXECUTION_LEASES": "1"}), patch.object(leases, "fenced_transaction", check):
                conn.fetchval.return_value = "04-qa-dev"
                with self.assertRaisesRegex(leases.LeaseLost, "artifact stage"):
                    await pipeline.insert_artifact(conn, "run", "03-coding", "report", "report.md")
                conn.execute.assert_not_awaited()
                conn.fetchval.return_value = "03-coding.builder"
                await pipeline.insert_artifact(conn, "run", "03-coding", "report", "report.md")
                self.assertEqual(seen, [child.lease, child.lease])
                conn.execute.assert_awaited_once()
        finally:
            ownership.STAGE.reset(ct)
            ownership.RUN.reset(pt)

    async def test_memory_refuses_unowned_and_wrong_execution(self):
        conn = AsyncMock()
        @asynccontextmanager
        async def accepted(*args, **kwargs):
            yield
        for mismatch in ("no-owner", "wrong-key", "valid"):
            conn.reset_mock()
            conn.fetchval.return_value = mismatch == "valid"
            child = ownership.Ownership(leases.Lease("run", "owner", 1, 42, 3), AsyncMock())
            token = ownership.STAGE.set(None if mismatch == "no-owner" else child)
            try:
                with patch.dict(os.environ, {"LANTERN_EXECUTION_LEASES": "1"}), \
                     patch.object(orchestrator.asyncpg, "connect", AsyncMock(return_value=conn)), \
                     patch.object(orchestrator, "render_role_memory", AsyncMock()), \
                     patch.object(leases, "fenced_transaction", accepted):
                    tool = orchestrator.make_append_memory("coding", "run", "03-coding", "run:03-coding:1")
                    arguments = json.dumps({"entry": "dated concrete test learning"})
                    context = ToolContext(context=None, tool_name="append_memory", tool_call_id="fixture", tool_arguments=arguments)
                    result = await tool.on_invoke_tool(context, arguments)
                self.assertEqual(conn.execute.await_count, int(mismatch == "valid"))
                self.assertEqual(result == "memory entry recorded", mismatch == "valid")
                conn.close.assert_awaited_once()
            finally:
                ownership.STAGE.reset(token)

    async def test_changed_publication_target_refuses_thread(self):
        with patch.object(pipeline, "product_target", AsyncMock(return_value=("changed", "main"))), \
             patch.object(pipeline, "product_work_branch", AsyncMock(return_value="feat/example")), \
             patch.object(pipeline, "_publish_branch") as publish:
            with self.assertRaisesRegex(RuntimeError, "target changed"):
                await pipeline._publish_coding_branch(AsyncMock(), "run", expected={
                    "repo": "original", "base": "main", "work": "feat/example", "head_sha": "a"*40})
            publish.assert_not_called()

    async def test_same_process_stage_environment_is_serial(self):
        seen, peak, active = [], 0, 0
        @asynccontextmanager
        async def stage(*args):
            yield None
        async def execute(conn, run, *args):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            seen.append(run)
            await asyncio.sleep(.01)
            active -= 1
        with patch.object(ownership, "stage_scope", stage), \
             patch.object(pipeline, "INPROCESS_STAGE_LOCK", asyncio.Lock()), \
             patch.object(pipeline, "_run_agent_stage", execute):
            await asyncio.gather(*(pipeline.run_agent_stage(None, run, "03-coding", "host") for run in ("one", "two")))
        self.assertEqual(peak, 1)
        self.assertEqual(seen, ["one", "two"])


class Checkouts(unittest.TestCase):
    def test_media_rejects_hardlinks_and_respects_attempt_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            own, other = root / "one", root / "two"
            own.mkdir()
            other.mkdir()
            good = own / "recording.webm"
            good.write_bytes(b"fixture")
            (other / "unrelated.webm").write_bytes(b"other")
            self.assertEqual(pipeline.media_candidates(own, 0), [good])
            protected = root / "controller-secret.txt"
            protected.write_bytes(b"sentinel")
            os.link(protected, own / "linked.webm")
            with self.assertRaises((ValueError, PermissionError)):
                pipeline.media_candidates(own, 0)
            self.assertEqual(protected.read_bytes(), b"sentinel")

    def test_source_hash_reader_rejects_oversized_and_linked_files(self):
        import evidence_manifest
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.write_bytes(b"12345")
            with self.assertRaisesRegex(ValueError, "bounded ordinary"):
                evidence_manifest.source_bytes(source, 4)
            os.link(source, Path(temp) / "other")
            with self.assertRaisesRegex(ValueError, "one link"):
                evidence_manifest.source_bytes(source)

    def test_distinct_attempts_never_replace_old_mount(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            seed = root / "seed"
            seed.mkdir()
            def git(*args):
                subprocess.run(["git", *args], cwd=seed, capture_output=True, check=True)
            git("init", "-q", "-b", "main")
            git("config", "user.name", "fixture")
            git("config", "user.email", "fixture@example.invalid")
            (seed / "source.txt").write_text("original")
            git("add", ".")
            git("commit", "-qm", "fixture")
            with patch.object(pipeline, "PRODUCT_MIRROR_DIR", root / "mirrors"):
                first = pipeline.product_checkout(str(seed), "main", "run", "", "run:stage:1")
                (first / "source.txt").write_text("old worker owns this")
                second = pipeline.product_checkout(str(seed), "main", "run", "", "run:stage:2")
                self.assertNotEqual(first, second)
                self.assertEqual((first / "source.txt").read_text(), "old worker owns this")
                self.assertEqual((second / "source.txt").read_text(), "original")
                with self.assertRaisesRegex(RuntimeError, "new attempt"):
                    pipeline.product_checkout(str(seed), "main", "run", "", "run:stage:1")


if __name__ == "__main__":
    unittest.main()
