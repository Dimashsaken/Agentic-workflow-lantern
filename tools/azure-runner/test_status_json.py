"""Behavior tests for machine-readable pipeline status.

    python3 -m unittest test_status_json -v
"""

import asyncio
import contextlib
import io
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pipeline  # noqa: E402

UPDATED = datetime(2026, 9, 7, 6, 5, 4, tzinfo=timezone.utc)
REQUESTED = datetime(2026, 9, 7, 5, 57, 3, tzinfo=timezone.utc)


def run_row(**over):
    row = {
        "id": "feat-20260907-status-json",
        "status": "running",
        "current_stage": "03-coding",
        "updated_at": UPDATED,
        "coding_mode": "auto",
        "product_repo": None,
    }
    row.update(over)
    return row


def gate_row(**over):
    row = {
        "run_id": "feat-20260907-status-json",
        "gate": "code_complete",
        "requested_at": REQUESTED,
    }
    row.update(over)
    return row


class FakeConnection:
    def __init__(self, runs=(), gates=()):
        self.runs = list(runs)
        self.gates = list(gates)
        self.queries = []
        self.closed = False

    async def fetch(self, sql):
        self.queries.append(sql)
        if "FROM runs" in sql:
            return self.runs
        if "FROM approvals" in sql:
            return self.gates
        raise AssertionError(f"unexpected fetch: {sql}")

    async def close(self):
        self.closed = True


def capture_status(conn, json_mode):
    original = pipeline.connect

    async def connect():
        return conn

    pipeline.connect = connect
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output):
            asyncio.run(pipeline.cmd_status(json_mode))
    finally:
        pipeline.connect = original
    return output.getvalue()


class TestStatusPayload(unittest.TestCase):
    def test_shape_and_timestamps_are_exact(self):
        payload = pipeline.status_payload([run_row()], [gate_row()])
        self.assertEqual(set(payload), {"runs", "pending_gates"})
        self.assertEqual(set(payload["runs"][0]), {
            "id", "status", "current_stage", "updated_at", "coding_mode", "product_repo"
        })
        self.assertEqual(set(payload["pending_gates"][0]), {
            "run_id", "gate", "requested_at"
        })
        self.assertEqual(payload["runs"][0]["updated_at"], UPDATED.isoformat())
        self.assertEqual(payload["pending_gates"][0]["requested_at"], REQUESTED.isoformat())
        self.assertTrue(payload["runs"][0]["updated_at"].endswith("+00:00"))
        self.assertIsNone(payload["runs"][0]["product_repo"])
        self.assertEqual(payload["runs"][0]["coding_mode"], "auto")

    def test_empty_inputs(self):
        self.assertEqual(pipeline.status_payload([], []), {
            "runs": [], "pending_gates": []
        })


class TestStatusCommand(unittest.TestCase):
    def test_json_mode_uses_two_queries_and_only_prints_json(self):
        conn = FakeConnection([run_row()], [gate_row()])
        output = capture_status(conn, True)
        self.assertEqual(len(conn.queries), 2)
        self.assertIn("product_repo", conn.queries[0])
        self.assertIn("FROM runs", conn.queries[0])
        self.assertIn("FROM approvals", conn.queries[1])
        self.assertEqual(json.loads(output), pipeline.status_payload(conn.runs, conn.gates))
        self.assertEqual(output.count("\n"), 1)
        self.assertNotIn("pending gate:", output)
        self.assertTrue(conn.closed)

    def test_human_output_is_unchanged_for_rows(self):
        conn = FakeConnection(
            [run_row(), run_row(
                id="feat-20260907-human", status="waiting_gate",
                current_stage="02-pre-coding", coding_mode="human",
                product_repo="https://example.invalid/repo")],
            [gate_row(run_id="feat-20260907-human", gate="plan_signoff")],
        )
        output = capture_status(conn, False)
        expected = (
            "feat-20260907-status-json                running       03-coding          updated 2026-09-07 06:05  [auto-coding]\n"
            "feat-20260907-human                      waiting_gate  02-pre-coding      updated 2026-09-07 06:05\n"
            "  pending gate: feat-20260907-human -> plan_signoff (since 2026-09-07 05:57)\n"
        )
        self.assertEqual(output, expected)

    def test_human_empty_output_is_unchanged(self):
        self.assertEqual(capture_status(FakeConnection(), False), "no active runs\n")


if __name__ == "__main__":
    unittest.main()
