"""The daily queue preserves actionable work while reducing default information."""

import os
import unittest
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import app as mc
import chat
from fakes import NOW, FakePool, approval_row, body_of, get, run_row, signed


class WorkQueue(unittest.TestCase):
    def setUp(self):
        os.environ["LANTERN_WEB_USERS"] = "tester:pw"

    def rows(self, runs, approvals=(), online=None):
        snap = {"runs": runs, "pend": approvals, "online": online or {}}
        with patch.object(mc, "report_text", return_value=None):
            return mc.work_rows(snap, NOW)

    def test_reviews_are_oldest_first_then_blocked_and_running(self):
        runs = [run_row(id="running", status="executing"), run_row(id="new"),
                run_row(id="failed", status="failed"), run_row(id="old")]
        gates = [approval_row(run_id="new", requested_at=NOW - timedelta(hours=1)),
                 approval_row(run_id="old", requested_at=NOW - timedelta(days=2))]
        self.assertEqual([r["id"] for r in self.rows(runs, gates)], ["old", "new", "failed", "running"])

    def test_pending_approval_outranks_even_a_closed_run(self):
        rows = self.rows([run_row(status="done")], [approval_row()])
        self.assertEqual(rows[0]["state"], "review")

    def test_workstation_and_missing_gate_are_actionable(self):
        rows = self.rows([run_row(id="design", status="running", current_stage="01-ui-ux.design"),
                          run_row(id="missing")])
        self.assertTrue(all(r["state"] == "blocked" for r in rows))
        self.assertIn("offline", next(r for r in rows if r["id"] == "design")["detail"])
        self.assertIn("missing", next(r for r in rows if r["id"] == "missing")["detail"])

    def test_report_block_is_not_hidden_by_executing_status(self):
        with patch.object(mc, "report_text", return_value="- **Status:** BLOCKED"):
            rows = mc.work_rows({"runs": [run_row(status="executing")], "pend": [], "online": {}}, NOW)
        self.assertEqual(rows[0]["state"], "blocked")

    def test_filters_and_search_preserve_scope_and_history(self):
        rows = self.rows([run_row(id="feat-20260901-old", status="done", updated_at=NOW-timedelta(days=90)),
                          run_row(id="feat-20260901-search", status="executing", product_repo="org/project", created_by="Alice")])
        active = mc.worklist.render(rows, NOW)
        self.assertNotIn("href='/run/feat-20260901-old'", active)
        closed = mc.worklist.render(rows, NOW, selected="closed")
        self.assertIn("href='/run/feat-20260901-old'", closed)
        self.assertNotIn("href='/run/feat-20260901-search'", closed)
        for term in ("ALICE", "project", "search"):
            html = mc.worklist.render(rows, NOW, query=term)
            self.assertEqual(html.count("class='work-row'"), 1)
            self.assertIn("filter=closed&amp;q=" + term, html)

    def test_no_match_and_empty_filter_have_distinct_recovery(self):
        rows = self.rows([run_row(status="executing")])
        html = mc.worklist.render(rows, NOW, selected="review", query="no match")
        self.assertIn("No matching work", html)
        self.assertIn("href='/?filter=review'", html)
        self.assertIn("You're all caught up", mc.worklist.render(rows, NOW, selected="review"))
        self.assertIn("No completed work yet", mc.worklist.render(rows, NOW, selected="closed"))

    def test_untrusted_text_and_search_are_escaped(self):
        rows = self.rows([run_row(id="<script>alert(1)</script>", status="executing", created_by="<img src=x>")])
        html = mc.worklist.render(rows, NOW, query="\"'><svg onload=alert(1)>")
        self.assertNotIn("<svg onload", html)
        html = mc.worklist.render(rows, NOW)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img src=x>", html)

    def test_each_run_has_one_link_and_no_quick_approval_form(self):
        run = run_row()
        html = body_of(get(mc.board, signed(), pool=FakePool(runs=[run], approvals=[approval_row()])))
        self.assertEqual(html.count("class='work-row'"), 1)
        self.assertNotIn("data-decide data-gate=", html)
        self.assertIn("#gate-", html)


class ChatEntry(unittest.TestCase):
    def render(self, **kwargs):
        directory = {
            "lantern": {"name": "Lantern", "kind": "orchestrator"},
            "security": {"name": "Security", "kind": "fleet"},
        }
        with patch.object(chat.cs, "agent_directory", new=AsyncMock(return_value=directory)), \
             patch.object(chat, "session_rows", new=AsyncMock(return_value=[])), \
             patch.object(chat.cs, "chat_configured", return_value=(True, "")):
            return body_of(get(chat.chat_hub, signed(), pool=FakePool(), **kwargs))

    def test_lantern_is_default_with_native_specialist_picker(self):
        html = self.render()
        self.assertIn("<option value='lantern' selected>", html)
        self.assertIn("<details class='agent-picker'>", html)
        self.assertNotIn("class='acard", html)
        self.assertIn("action='/chat/new'", html)
        self.assertIn("Actions need your confirmation", html)

    def test_run_scoped_specialist_link_stays_selected(self):
        html = self.render(agent="security", run="feat-20260911-review")
        self.assertIn("<option value='security' selected>", html)
        self.assertIn("<details class='agent-picker' open>", html)
        self.assertIn("name='run_id' value='feat-20260911-review'", html)
        self.assertIn("Advice only · read-only", html)


if __name__ == "__main__":
    unittest.main()
