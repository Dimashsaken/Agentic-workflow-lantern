"""`pipeline.py review <run>` — re-run only the review loop on a published handoff.

    .venv/Scripts/python test_review_rerun.py      (no database, no Azure, no docker)

Two runs on 2026-09-12 lost a review round after the coding work was already on the
branch (an Azure 429 past the retry budget; unattended-upgrades restarting docker under
a review container). `retry` re-runs coding, which now rightly fails as a no-op, and
`publish` only re-pushes. This command re-runs the loop, marks the orphaned execution,
and refreshes or opens the gate — and refuses when a sandbox is still alive.
"""

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pipeline as p  # noqa: E402

RUN = "feat-20260912-review-rerun"


class FakeConn:
    def __init__(self, run_row, pending=None, running=()):
        self.run_row, self.pending, self.running = dict(run_row), pending, list(running)
        self.executed: list[tuple[str, tuple]] = []
        self.closed = False

    async def fetchrow(self, q, *a):
        if "FROM runs" in q:
            return self.run_row
        if "FROM approvals" in q:
            return self.pending
        raise AssertionError(q)

    async def fetch(self, q, *a):
        if "UPDATE stage_executions" in q:
            rows = [{"id": i, "stage": s} for i, s in self.running if s in a[2]]
            self.running = [(i, s) for i, s in self.running if s not in a[2]]
            self.executed.append((q, a))
            return rows
        raise AssertionError(q)

    async def execute(self, q, *a):
        self.executed.append((q, a))
        if "UPDATE runs SET status" in q:
            self.run_row["status"] = q.split("status = '")[1].split("'")[0]
        return "UPDATE 1"

    async def close(self):
        self.closed = True

    def statuses(self):
        return [q.split("status = '")[1].split("'")[0] for q, _ in self.executed if "UPDATE runs SET status" in q]


class ReviewRerun(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.gates = []

        async def log_event(conn, run_id, actor, type_, data=None):
            self.events.append((actor, type_, data or {}))

        async def render_runboard(conn):
            pass

        async def publish(conn, run_id):
            return {"branch": "feat/x", "pushed": True, "pr_url": None}

        async def after_publish(conn, run_id, payload, runner, deps):
            self.calls = (runner, payload)
            return {**payload, "review": {"verdict": "approve", "rounds": [{"round": 10}]}}

        async def open_gate(conn, run_id, stage, gate, extra=None, external_ref=None):
            self.gates.append((stage, gate, extra))
            await conn.execute("UPDATE runs SET status = 'waiting_gate', updated_at = now() WHERE id = $1", run_id)

        self.addCleanup(mock.patch.stopall)
        for name, fn in (("log_event", log_event), ("render_runboard", render_runboard),
                         ("publish_coding_branch", publish), ("open_gate", open_gate)):
            mock.patch.object(p, name, fn).start()
        mock.patch.object(p.review, "after_publish", after_publish).start()
        mock.patch.object(p.review, "default_deps", lambda execute=None: "deps").start()
        mock.patch.object(p, "_read_handoff", lambda run_id, sdir: {"kind": "coding_branch"}).start()
        mock.patch.object(p, "_live_sandboxes", lambda run_id: []).start()

    def run_cmd(self, conn):
        mock.patch.object(p, "connect", mock.AsyncMock(return_value=conn)).start()
        asyncio.run(p.cmd_review(RUN, "ec2"))

    def test_orphaned_executing_run_gets_its_review_and_gate(self):
        conn = FakeConn({"status": "executing", "current_stage": "03-coding", "coding_mode": "auto"},
                        running=[(135, "03-coding.review"), (99, "04-qa-dev")])
        self.run_cmd(conn)
        self.assertEqual(conn.running, [(99, "04-qa-dev")])            # only review/fix rows are closed
        self.assertEqual(conn.statuses(), ["executing", "waiting_gate"])
        self.assertEqual([g[1] for g in self.gates], ["code_complete"])
        self.assertEqual(self.gates[0][2]["review"]["verdict"], "approve")
        self.assertIn("review_rerun", [e[1] for e in self.events])
        self.assertEqual(self.events[0][2]["orphaned"], [{"id": 135, "stage": "03-coding.review"}])
        self.assertTrue(conn.closed)

    def test_pending_gate_is_refreshed_not_duplicated(self):
        pending = {"id": 7, "payload": json.dumps({"branch": "feat/x", "review": {"verdict": "error"}})}
        conn = FakeConn({"status": "waiting_gate", "current_stage": "03-coding", "coding_mode": "auto"}, pending=pending)
        self.run_cmd(conn)
        self.assertEqual(self.gates, [])
        upd = [a for q, a in conn.executed if "UPDATE approvals SET payload" in q]
        self.assertEqual(len(upd), 1)
        self.assertEqual(json.loads(upd[0][0])["review"]["verdict"], "approve")
        self.assertEqual(upd[0][2], 7)
        self.assertEqual(conn.run_row["status"], "waiting_gate")

    def test_refusals(self):
        with self.assertRaises(SystemExit):
            self.run_cmd(FakeConn({"status": "executing", "current_stage": "04-qa-dev", "coding_mode": "auto"}))
        with self.assertRaises(SystemExit):
            self.run_cmd(FakeConn({"status": "done", "current_stage": "03-coding", "coding_mode": "auto"}))
        with self.assertRaises(SystemExit):
            self.run_cmd(FakeConn({"status": "waiting_gate", "current_stage": "03-coding", "coding_mode": "human"}))
        mock.patch.object(p, "_live_sandboxes", lambda run_id: [f"lantern-{RUN}-03-coding-review-4"]).start()
        with self.assertRaises(SystemExit):
            self.run_cmd(FakeConn({"status": "executing", "current_stage": "03-coding", "coding_mode": "auto"}))
        mock.patch.object(p, "_live_sandboxes", lambda run_id: []).start()
        mock.patch.object(p, "_read_handoff", lambda run_id, sdir: None).start()
        with self.assertRaises(SystemExit):
            self.run_cmd(FakeConn({"status": "failed", "current_stage": "03-coding", "coding_mode": "auto"}))

    def test_a_failing_loop_marks_the_run_failed_and_re_raises(self):
        async def boom(conn, run_id, payload, runner, deps):
            raise RuntimeError("sandbox exited 1")
        mock.patch.object(p.review, "after_publish", boom).start()
        conn = FakeConn({"status": "failed", "current_stage": "03-coding", "coding_mode": "auto"})
        with self.assertRaises(RuntimeError):
            self.run_cmd(conn)
        self.assertEqual(conn.statuses(), ["executing", "failed"])
        self.assertIn("review_rerun_failed", [e[1] for e in self.events])


if __name__ == "__main__":
    unittest.main(verbosity=2)
