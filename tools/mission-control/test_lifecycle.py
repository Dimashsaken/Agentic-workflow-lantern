"""Lifecycle truth at the boundaries: gates, rework, shared stages, missing data."""

import json
import os
import unittest
from datetime import timedelta
from unittest.mock import patch

import app as mc
import lanes
import lifecycle as lc
from fakes import NOW, FakePool, approval_row, body_of, exec_row, get, run_row, signed

RUN = "feat-20260911-cycle"


class Lifecycle(unittest.TestCase):
    def run_at(self, stage, status="executing", **kw):
        return run_row(id=RUN, current_stage=stage, status=status, **kw)

    def execution(self, stage, **kw):
        return exec_row(kw.pop("id", 1), RUN, stage, **kw)

    def test_story_research_success_does_not_complete_story(self):
        model = lc.build(self.run_at("00-story.write"), [self.execution("00-story.scout")])
        self.assertEqual(len(model["phases"]), 8)
        self.assertEqual(model["current"]["state"], "current")
        self.assertEqual(model["next"], "Story approval → Design")

    def test_review_overrides_success_and_links_to_next_stage(self):
        model = lc.build(self.run_at("03-coding", "waiting_gate"),
                         [self.execution("03-coding.review")],
                         [approval_row(run_id=RUN, gate="code_complete")])
        self.assertEqual(model["current"]["state"], "review")
        self.assertEqual(model["next"], "After approval → QA dev")

    def test_rework_preserves_downstream_evidence_without_marking_it_complete(self):
        events = [dict(type="run_reworked", at=NOW, data=json.dumps({
            "from": "04-qa-dev", "to": "03-coding", "note": "Fails AC-2"}))]
        model = lc.build(self.run_at("03-coding"), [self.execution("04-qa-dev")], events=events)
        qa = next(p for p in model["phases"] if p["key"] == "04-qa-dev")
        self.assertEqual((qa["state"], qa["status"]), ("future", "Earlier activity"))
        self.assertIn("QA dev → Code", lc.render(model, NOW))
        self.assertIn("Fails AC-2", lc.render(model, NOW))

    def test_no_history_is_not_invented_success(self):
        model = lc.build(self.run_at("04-qa-dev"))
        self.assertEqual(model["phases"][0]["state"], "unknown")
        self.assertEqual(model["phases"][0]["status"], "No execution record")

    def test_bug_at_shared_coding_stage_keeps_debug_lifecycle(self):
        run = run_row(id="bug-20260911-crash", current_stage="03-coding", status="executing")
        model = lc.build(run)
        self.assertEqual(model["current"]["label"], "Fix")
        self.assertEqual(model["next"], "Code review / approval → Regression")
        self.assertNotIn("Design", [p["label"] for p in model["phases"]])
        self.assertFalse(lanes.build_lanes(run, [], [], NOW)["feature_run"])
        plan = next(p for p in model["phases"] if p["key"] == "02-pre-coding")
        self.assertTrue(plan["optional"])
        self.assertNotEqual(plan["state"], "past")

    def test_parallel_builders_and_review_attempts_keep_their_identity(self):
        execs = [self.execution("03-coding.api", id=1, status="running"),
                 self.execution("03-coding.ui", id=2, status="running"),
                 self.execution("03-coding.review", id=3, attempt=2)]
        model = lc.build(self.run_at("03-coding", coding_mode="auto"), execs)
        self.assertEqual(model["now"], "2 agents running in Code")
        html = lc.render(model, NOW)
        self.assertEqual(html.count("class='phase-execution'"), 3)
        self.assertIn("Attempt 2", html)
        self.assertIn("/exec/2", html)

    def test_feature_subphase_does_not_lose_road_ahead(self):
        run = self.run_at("03-coding.fix")
        self.assertEqual(lc.build(run)["current"]["label"], "Code")
        model = lanes.build_lanes(run, [], [], NOW)
        self.assertTrue(model["feature_run"])
        self.assertTrue(next(p for p in model["lanes"] if p["stage"] == "03-coding.fix")["current"])

    def test_old_running_record_is_not_an_active_agent_after_rework(self):
        event = dict(type="run_reworked", at=NOW, data={"from": "04-qa-dev", "to": "03-coding"})
        model = lc.build(self.run_at("03-coding", coding_mode="auto"),
                         [self.execution("03-coding.api", status="running")], events=[event])
        self.assertEqual(model["live"], [])
        self.assertIn("waiting for an execution", model["now"])
        self.assertIn("Earlier cycle", lc.render(model, NOW))
        self.assertIn("Recorded running", lc.render(model, NOW))

    def test_bug_planning_is_conditional_in_the_handoff(self):
        run = run_row(id="bug-20260911-crash", current_stage="03-root-cause", status="executing")
        self.assertEqual(lc.build(run)["next"], "Plan (large fixes) or Fix")

    def test_completion_does_not_claim_production_deployment(self):
        model = lc.build(self.run_at("07-qa-staging", "done"))
        self.assertEqual(model["now"], "Run completed")
        self.assertEqual(model["next"], "No further stages scheduled")
        model = lc.build(self.run_at("06-security"))
        self.assertEqual(model["next"], "Human deploy to staging → QA staging")

    def test_bug_closed_at_triage_does_not_claim_future_stages_ran(self):
        run = run_row(id="bug-20260911-duplicate", current_stage="01-triage", status="done")
        model = lc.build(run)
        self.assertTrue(all(p["status"] == "Not reached" for p in model["phases"][1:]))

    def test_failure_and_missing_gate_do_not_promise_automatic_progress(self):
        for state in ("failed", "waiting_gate"):
            model = lc.build(self.run_at("03-coding", state))
            self.assertNotIn("→ QA dev", model["next"])

    def test_stage_selection_and_evidence_links_render_on_real_route(self):
        users = patch.dict(os.environ, {"LANTERN_WEB_USERS": "tester:pw"})
        users.start()
        self.addCleanup(users.stop)
        pool = FakePool(runs=[self.run_at("03-coding")], execs=[self.execution("00-story.scout")])
        html = body_of(get(mc.run_page, RUN, signed(), stage="00-story", pool=pool))
        self.assertIn("Researcher → story writer", html)
        self.assertIn("href='#files-00-story'", html)
        self.assertIn("id='files-00-story'", html)
        self.assertIn("id='execution-history'", html)
        self.assertIn("stage=01-ui-ux#lifecycle", html)
        self.assertIn("aria-current=step", html)

    def test_untrusted_event_note_is_escaped_and_bad_json_is_ignored(self):
        events = [dict(type="run_reworked", at=NOW, data="{broken"),
                  dict(type="run_reworked", at=NOW + timedelta(seconds=1), data={
                      "from": "04-qa-dev", "to": "03-coding", "note": "<img onerror=evil>"})]
        html = lc.render(lc.build(self.run_at("03-coding"), events=events), NOW)
        self.assertNotIn("<img onerror", html)
        self.assertIn("&lt;img", html)


if __name__ == "__main__":
    unittest.main()
