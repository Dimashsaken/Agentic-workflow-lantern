"""Swim-lane math and ordering from fixture execution rows (Mission Control v3, D22).

    ..\\..\\tools\\azure-runner\\.venv\\Scripts\\python test_lanes.py

Stdlib only, no database: build_lanes() takes rows and returns the lane model that
render_lanes() draws. Contract under test:
  * one lane per stage execution key, executed lanes in the order they first started,
    then the pipeline's remaining stages as ghost lanes in pipeline order;
  * every attempt gets a slot = its ordinal in the run's time line and a bar width
    proportional to its duration (never below the floor);
  * per-lane duration, tier, tokens and estimated cost come from the ledger, with
    unmetered rows counted rather than priced at $0;
  * gate diamonds hang off the lanes whose stage the pipeline gates, showing the latest
    approval row's state;
  * stage-3 sub-phases (builders, review rounds — D18/D19) become lanes of their own,
    routed to the right role and tier, sorted after the coding stage.
"""

import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app as mc  # noqa: E402  (imports pipeline/orchestrator once for everyone)
import lanes  # noqa: E402
from fakes import NOW, approval_row, exec_row, run_row  # noqa: E402
from pipeline import est_cost_usd  # noqa: E402

RUN = "feat-20260908-lanes"
T0 = NOW - timedelta(hours=4)


def story_run():
    """The status-facts shape: scout passed, story blocked then passed, gate open."""
    run = run_row(id=RUN, status="waiting_gate", current_stage="00-story.write")
    execs = [
        exec_row(8, RUN, "00-story.scout", 1, "succeeded", T0, 280, inp=1_086_140, cached=960_299, out=8_711),
        exec_row(9, RUN, "00-story.write", 1, "failed", T0 + timedelta(seconds=280), 124,
                 inp=202_318, cached=177_801, out=6_048, error="postconditions failed: BLOCKED\nmore"),
        exec_row(10, RUN, "00-story.write", 2, "succeeded", T0 + timedelta(seconds=520), 107,
                 inp=411_388, cached=370_335, out=4_112),
    ]
    approvals = [approval_row(4, RUN, "story_signoff", "pending")]
    return run, execs, approvals


class LaneModel(unittest.TestCase):
    def setUp(self):
        self.run, self.execs, self.approvals = story_run()
        self.model = lanes.build_lanes(self.run, self.execs, self.approvals, NOW)
        self.by = {ln["stage"]: ln for ln in self.model["lanes"]}

    def test_executed_lanes_first_in_time_order_then_ghosts_in_pipeline_order(self):
        keys = [ln["stage"] for ln in self.model["lanes"]]
        self.assertEqual(keys[:2], ["00-story.scout", "00-story.write"])
        self.assertEqual(keys[2:], ["01-ui-ux.diverge", "01-ui-ux.design", "02-pre-coding",
                                    "03-coding", "04-qa-dev", "05-post-coding",
                                    "05-post-coding.validate", "06-security", "07-qa-staging"])
        self.assertTrue(all(ln["future"] for ln in self.model["lanes"][2:]))
        self.assertFalse(self.by["00-story.scout"]["future"])

    def test_slots_are_ordinals_and_widths_scale_with_duration(self):
        scout, write = self.by["00-story.scout"], self.by["00-story.write"]
        self.assertEqual(self.model["columns"], 3)
        self.assertEqual([a["slot"] for a in scout["attempts"]], [1])
        self.assertEqual([a["slot"] for a in write["attempts"]], [2, 3])
        self.assertEqual(scout["attempts"][0]["width_pct"], 100)          # the longest
        self.assertEqual(write["attempts"][1]["width_pct"], round(107 / 280 * 100))
        self.assertEqual([a["attempt"] for a in write["attempts"]], [1, 2])
        self.assertEqual([a["kind"] for a in write["attempts"]], ["bad", "ok"])
        self.assertEqual(write["attempts"][0]["error"], "postconditions failed: BLOCKED")

    def test_width_floor_keeps_a_two_second_attempt_visible(self):
        execs = self.execs + [exec_row(11, RUN, "01-ui-ux.diverge", 1, "succeeded",
                                       T0 + timedelta(seconds=700), 2)]
        model = lanes.build_lanes(self.run, execs, self.approvals, NOW)
        by = {ln["stage"]: ln for ln in model["lanes"]}
        self.assertEqual(by["01-ui-ux.diverge"]["attempts"][0]["width_pct"], lanes.MIN_WIDTH_PCT)
        self.assertEqual(model["columns"], 4)

    def test_lane_totals_come_from_the_ledger(self):
        write = self.by["00-story.write"]
        self.assertEqual(write["attempt_count"], 2)
        self.assertEqual(write["tokens"], (202_318 + 6_048) + (411_388 + 4_112))
        self.assertAlmostEqual(write["cost"],
                               est_cost_usd(202_318, 177_801, 6_048, "gpt-5.6-sol")
                               + est_cost_usd(411_388, 370_335, 4_112, "gpt-5.6-sol"))
        self.assertEqual(write["seconds"], 124 + 107)
        self.assertEqual(write["status"], "succeeded")
        self.assertEqual(write["models"], ["gpt-5.6-sol"])
        self.assertEqual(self.model["retries"], 1)
        self.assertEqual(self.model["executions"], 3)
        self.assertAlmostEqual(self.model["cost"], sum(ln["cost"] for ln in self.model["lanes"]))

    def test_unmetered_rows_are_counted_not_priced(self):
        execs = [exec_row(1, RUN, "00-story.scout", 1, "succeeded", T0, 10, inp=None)]
        model = lanes.build_lanes(self.run, execs, [], NOW)
        lane = model["lanes"][0]
        self.assertEqual(lane["unmetered"], 1)
        self.assertEqual(lane["tokens"], 0)
        self.assertEqual(lane["cost"], 0.0)
        self.assertFalse(lane["attempts"][0]["metered"])
        self.assertEqual(model["unmetered"], 1)

    def test_tier_and_role_per_lane(self):
        self.assertEqual(self.by["00-story.scout"]["role"], "researcher")
        self.assertEqual(self.by["00-story.scout"]["tier"], "reasoning")
        self.assertEqual(self.by["01-ui-ux.diverge"]["tier"], "fast")
        self.assertEqual(self.by["01-ui-ux.design"]["tier"], "reasoning")
        self.assertEqual(self.by["04-qa-dev"]["tier"], "fast")
        self.assertEqual(self.by["03-coding"]["tier"], "coding")
        self.assertTrue(self.by["03-coding"]["human"])

    def test_gate_diamonds_follow_the_pipeline_and_show_the_latest_approval(self):
        write = self.by["00-story.write"]
        self.assertEqual(write["gate"], "story_signoff")
        self.assertEqual(write["approval"]["status"], "pending")
        self.assertEqual(write["approval"]["kind"], "wait")
        self.assertEqual(write["approval"]["id"], 4)
        self.assertIsNone(self.by["00-story.scout"]["gate"])              # no gate after the scout
        self.assertEqual(self.by["01-ui-ux.design"]["gate"], "ux_signoff")
        self.assertIsNone(self.by["01-ui-ux.design"]["approval"])
        self.assertEqual(self.by["03-coding"]["gate"], "code_complete")

    def test_latest_approval_wins_when_a_gate_was_rejected_then_reopened(self):
        approvals = [approval_row(1, RUN, "story_signoff", "rejected", age_seconds=9000,
                                  decided_by="justin", decided_at=NOW - timedelta(hours=2),
                                  decision_note="tighten AC-2"),
                     approval_row(2, RUN, "story_signoff", "pending", age_seconds=600)]
        model = lanes.build_lanes(self.run, self.execs, approvals, NOW)
        write = next(ln for ln in model["lanes"] if ln["stage"] == "00-story.write")
        self.assertEqual(write["approval"]["id"], 2)
        self.assertEqual(write["approval"]["kind"], "wait")
        model2 = lanes.build_lanes(self.run, self.execs, approvals[:1], NOW)
        write2 = next(ln for ln in model2["lanes"] if ln["stage"] == "00-story.write")
        self.assertEqual(write2["approval"]["kind"], "bad")
        self.assertEqual(write2["approval"]["note"], "tighten AC-2")

    def test_current_lane_is_marked(self):
        self.assertTrue(self.by["00-story.write"]["current"])
        self.assertFalse(self.by["00-story.scout"]["current"])

    def test_execution_keys_and_trace_flags(self):
        model = lanes.build_lanes(self.run, self.execs, self.approvals, NOW,
                                  traces={f"{RUN}:00-story.write:2"})
        by = {ln["stage"]: ln for ln in model["lanes"]}
        a1, a2 = by["00-story.write"]["attempts"]
        self.assertEqual(a2["execution_key"], f"{RUN}:00-story.write:2")
        self.assertTrue(a2["has_trace"])
        self.assertFalse(a1["has_trace"])


class ImportedAndSubPhaseLanes(unittest.TestCase):
    def test_run_imported_at_qa_shows_earlier_stages_as_passed_not_future(self):
        run = run_row(id=RUN, status="running", current_stage="04-qa-dev")
        model = lanes.build_lanes(run, [], [], NOW)
        by = {ln["stage"]: ln for ln in model["lanes"]}
        for k in ("00-story.scout", "00-story.write", "02-pre-coding", "03-coding"):
            self.assertTrue(by[k]["passed_without_execution"], k)
            self.assertFalse(by[k]["future"], k)
        self.assertTrue(by["04-qa-dev"]["current"])
        self.assertFalse(by["04-qa-dev"]["future"])
        self.assertTrue(by["05-post-coding"]["future"])
        self.assertEqual(model["columns"], 1)
        self.assertEqual(model["executions"], 0)

    def test_builders_and_review_rounds_become_lanes_after_the_coding_stage(self):
        run = run_row(id=RUN, status="waiting_gate", current_stage="03-coding", coding_mode="auto")
        t = T0
        execs = [exec_row(1, RUN, "02-pre-coding", 1, "succeeded", t, 60)]
        t += timedelta(seconds=60)
        execs.append(exec_row(2, RUN, "03-coding.api", 1, "succeeded", t, 300))
        execs.append(exec_row(3, RUN, "03-coding.docs", 1, "succeeded", t + timedelta(seconds=1), 200))
        t += timedelta(seconds=310)
        execs.append(exec_row(4, RUN, "03-coding.integrate", 1, "succeeded", t, 90))
        t += timedelta(seconds=90)
        execs.append(exec_row(5, RUN, "03-coding.review", 1, "succeeded", t, 40))
        execs.append(exec_row(6, RUN, "03-coding.fix", 1, "succeeded", t + timedelta(seconds=40), 80))
        execs.append(exec_row(7, RUN, "03-coding.review", 2, "succeeded", t + timedelta(seconds=120), 30))
        approvals = [approval_row(9, RUN, "plan_signoff", "approved", decided_by="dimash",
                                  decided_at=T0 + timedelta(seconds=50)),
                     approval_row(10, RUN, "code_complete", "pending", age_seconds=100)]
        model = lanes.build_lanes(run, execs, approvals, NOW)
        keys = [ln["stage"] for ln in model["lanes"]]
        self.assertEqual(keys[:8], ["00-story.scout", "00-story.write", "01-ui-ux.diverge",
                                    "01-ui-ux.design", "02-pre-coding", "03-coding",
                                    "03-coding.api", "03-coding.docs"])
        self.assertEqual(keys[8:11], ["03-coding.integrate", "03-coding.review", "03-coding.fix"])
        by = {ln["stage"]: ln for ln in model["lanes"]}
        self.assertEqual(by["03-coding.api"]["role"], "coding")
        self.assertEqual(by["03-coding.api"]["tier"], "coding")
        self.assertEqual(by["03-coding.review"]["role"], "reviewer")
        self.assertEqual(by["03-coding.review"]["tier"], "reasoning")
        self.assertEqual(by["03-coding.review"]["attempt_count"], 2)
        self.assertEqual(lanes.pipe_index("03-coding.api"), 5.5)
        # the human coding lane carries the gate; builder lanes do not
        self.assertEqual(by["03-coding"]["gate"], "code_complete")
        self.assertEqual(by["03-coding"]["approval"]["kind"], "wait")
        self.assertIsNone(by["03-coding.api"]["gate"])
        self.assertEqual(by["02-pre-coding"]["approval"]["kind"], "ok")
        self.assertEqual(by["02-pre-coding"]["approval"]["decided_by"], "dimash")
        self.assertTrue(by["03-coding"]["passed_without_execution"])
        self.assertEqual(model["columns"], 7)


class LaneRendering(unittest.TestCase):
    def setUp(self):
        run, execs, approvals = story_run()
        self.model = lanes.build_lanes(run, execs, approvals, NOW, traces={f"{RUN}:00-story.scout:1"})
        self.html = lanes.render_lanes(self.model, RUN, mc.GATE_SHORT, mc.GATE_META, mc.STAGE_META)

    def test_bars_open_the_drawer_and_carry_keyboard_focus(self):
        self.assertIn(f"href='/run/{RUN}/exec/8' data-drawer data-k", self.html)
        self.assertIn(f"href='/run/{RUN}/exec/10' data-drawer data-k", self.html)
        self.assertIn("class='pill bad'", self.html)
        self.assertIn("✕", self.html)                       # failed attempt marker
        self.assertIn("--slot:3;--w:38%", self.html)
        self.assertIn("style='--n:3'", self.html)

    def test_gate_diamonds_and_ghost_lanes(self):
        self.assertIn("◆", self.html)
        self.assertIn("class='gaterow wait'", self.html)
        self.assertIn("waiting on a human", self.html)
        self.assertIn("decide ↗", self.html)
        self.assertIn("class='gaterow future'", self.html)
        self.assertIn("class='lane future'", self.html)
        self.assertIn("human stage — no execution row", self.html)
        self.assertIn("not started", self.html)

    def test_tier_chips_cost_and_status(self):
        self.assertIn("chip tier'>reasoning", self.html)
        self.assertIn("chip tier'>fast", self.html)
        self.assertIn("Succeeded", self.html)
        self.assertIn("1,095k tok", self.html)
        self.assertIn("· trace", self.html)
        self.assertIn("· no trace", self.html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
