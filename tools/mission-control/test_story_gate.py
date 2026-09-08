"""The story_signoff gate card renders the story itself (D17).

    cd tools/mission-control && python -m unittest test_story_gate -v

Stdlib only, no server, no login: gate_card() is called directly with fake rows, the
way test_gate_latency.py does, against a temporary run folder. What the approver must
see is 00-story/story.md — the acceptance criteria — not just the stage report.
"""

import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("LANTERN_WEB_USERS", "tester:pw")
import app as mc  # noqa: E402

NOW = datetime(2026, 9, 8, 9, 0, 0, tzinfo=timezone.utc)
RUN = "feat-20260908-story-card"


def run_row(**over) -> dict:
    row = {"id": RUN, "status": "waiting_gate", "current_stage": "00-story.write",
           "created_by": "tester", "created_at": NOW - timedelta(hours=2),
           "updated_at": NOW - timedelta(minutes=5), "completed_at": None,
           "pipeline_version": 3, "brief": "workflow/briefs/fake.md",
           "product_repo": None, "product_branch": None}
    row.update(over)
    return row


def approval_row(**over) -> dict:
    row = {"id": 42, "run_id": RUN, "gate": "story_signoff", "status": "pending",
           "payload": '{"stage": "00-story.write", "run_folder": "workflow/runs/x/"}',
           "requested_at": NOW - timedelta(minutes=3), "decided_at": None,
           "decided_by": None, "decision_note": None}
    row.update(over)
    return row


class StoryGateCard(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mc-story-"))
        self.repo_backup = mc.REPO
        mc.REPO = self.tmp
        d = self.tmp / "workflow" / "runs" / RUN / "00-story"
        d.mkdir(parents=True)
        (d / "story.md").write_text(
            "# Story — x\n\n## Acceptance criteria\n\n| ID | Criterion | Edge cases |\n"
            "|----|-----------|------------|\n| AC-1 | The JSON carries branch facts. | nulls |\n",
            encoding="utf-8")

    def tearDown(self):
        mc.REPO = self.repo_backup
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_story_signoff_renders_the_story_inline(self):
        html = mc.gate_card(approval_row(), run_row(), NOW)
        self.assertIn("Approve the story", html)                   # GATE_META title
        self.assertIn("The story being approved", html)
        self.assertIn("AC-1", html)
        self.assertIn("The JSON carries branch facts.", html)
        self.assertIn("/gate/42/approve", html)
        self.assertIn("starts 1 · UI/UX design", html)             # next stage after the gate

    def test_other_gates_do_not_show_a_story(self):
        html = mc.gate_card(approval_row(gate="plan_signoff"), run_row(current_stage="02-pre-coding"), NOW)
        self.assertNotIn("The story being approved", html)

    def test_missing_story_file_degrades_quietly(self):
        (self.tmp / "workflow" / "runs" / RUN / "00-story" / "story.md").unlink()
        html = mc.gate_card(approval_row(), run_row(), NOW)
        self.assertIn("Approve the story", html)
        self.assertNotIn("The story being approved", html)

    def test_stage_meta_and_gate_tables_know_stage_zero(self):
        self.assertIn("00-story", mc.STAGE_META)
        self.assertEqual(mc.BOARD_DIRS[0], "00-story")
        self.assertEqual(list(mc.GATE_META)[0], "story_signoff")
        self.assertEqual(mc.GATE_SHORT["story_signoff"], "story sign-off")
        self.assertEqual(mc.DIR_ROLE["00-story"], "story")


if __name__ == "__main__":
    unittest.main(verbosity=2)
