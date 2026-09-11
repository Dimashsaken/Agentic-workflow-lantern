"""The rework decision reaches the task block of the stage it targets (D17 loop as code).

    .venv/Scripts/python test_rework_context.py      (no database, no Azure)

Found 2026-09-11 on feat-20260911-tender-onboarding: `rework --to 03-coding` after a
post-coding fix-now item re-ran coding with the day-one task block; the agent re-read
the approved review, found "no code change warranted" and handed back the unchanged
head. The human's note lived only in gate-decisions.md and the event log.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import orchestrator as o  # noqa: E402

RUN = "feat-20260911-rework-proof"

DECISIONS = """# Gate decisions

## code_complete — APPROVED

- **Decided by:** dimash
- **When:** 2026-09-11 18:08 UTC
- **Note:** looks fine

## rework -> 03-coding — REWORKED

- **Decided by:** dimash
- **When:** 2026-09-11 18:53 UTC
- **Note:** Post-coding fix-now: remove the tracked tender_whatsapp.egg-info/ metadata, drop the egg_base workaround, ignore generated *.egg-info.
"""


class ReworkContext(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rework-"))
        self.patch = mock.patch.object(o, "REPO", self.tmp)
        self.patch.start()
        self.rd = self.tmp / "workflow" / "runs" / RUN
        for d, files in (("03-coding", ["report.md"]), ("04-qa-dev", ["report.md", "bugs.md"]),
                         ("05-post-coding", ["report.md", "debt-tickets.md"])):
            (self.rd / d).mkdir(parents=True)
            for f in files:
                (self.rd / d / f).write_text("x\n", encoding="utf-8")
        (self.rd / "gate-decisions.md").write_text(DECISIONS, encoding="utf-8")

    def tearDown(self):
        self.patch.stop()

    def test_the_targeted_stage_gets_the_note_and_the_later_stages_files(self):
        block = o.rework_context(RUN, "03-coding")
        self.assertIn("running AGAIN", block)
        self.assertIn("rework, decided by dimash (2026-09-11 18:53 UTC)", block)
        self.assertIn("remove the tracked tender_whatsapp.egg-info/", block)
        for p in (f"workflow/runs/{RUN}/04-qa-dev/report.md", f"workflow/runs/{RUN}/04-qa-dev/bugs.md",
                  f"workflow/runs/{RUN}/05-post-coding/report.md", f"workflow/runs/{RUN}/05-post-coding/debt-tickets.md"):
            self.assertIn(p, block)
        self.assertNotIn(f"workflow/runs/{RUN}/03-coding/report.md", block)   # its own dir is not "later"
        self.assertIn("changes nothing is a failed execution", block)
        # The review and fix sub-executions of the same stage dir see it too.
        self.assertIn("running AGAIN", o.rework_context(RUN, "03-coding.review"))
        # It is part of the task block, after the plan and before the deliverable line.
        task = o.product_task_block(RUN, "03-coding")
        self.assertLess(task.index("running AGAIN"), task.index("This stage's deliverable"))

    def test_a_rejected_gate_of_this_stage_counts_as_being_sent_back(self):
        # From an open code_complete the operator cannot `rework --to 03-coding` (not an
        # earlier stage); the path is `reject` + `retry`, and the note must reach coding.
        with (self.rd / "gate-decisions.md").open("a", encoding="utf-8") as fh:
            fh.write("\n## code_complete — REJECTED\n\n- **Decided by:** dimash\n"
                     "- **When:** 2026-09-11 20:50 UTC\n- **Note:** attempt 4 changed nothing; do the egg-info cleanup.\n")
        block = o.rework_context(RUN, "03-coding")
        self.assertIn("gate `code_complete` rejected, decided by dimash (2026-09-11 20:50 UTC)", block)
        self.assertIn("attempt 4 changed nothing", block)
        self.assertIn(f"workflow/runs/{RUN}/05-post-coding/debt-tickets.md", block)
        self.assertEqual(o.rework_context(RUN, "02-pre-coding"), "")
        with (self.rd / "gate-decisions.md").open("a", encoding="utf-8") as fh:
            fh.write("\n## plan_signoff — REJECTED\n\n- **Decided by:** dimash\n- **When:** later\n- **Note:** replan\n")
        self.assertIn("replan", o.rework_context(RUN, "02-pre-coding"))
        self.assertEqual(o.rework_context(RUN, "03-coding"), "")

    def test_other_stages_and_other_decisions_get_nothing(self):
        self.assertEqual(o.rework_context(RUN, "04-qa-dev"), "")
        self.assertEqual(o.rework_context(RUN, "05-post-coding"), "")
        # A later decision (the rework was followed by an approval) ends the context.
        with (self.rd / "gate-decisions.md").open("a", encoding="utf-8") as fh:
            fh.write("\n## code_complete — APPROVED\n\n- **Decided by:** dimash\n- **When:** later\n- **Note:** ok\n")
        self.assertEqual(o.rework_context(RUN, "03-coding"), "")
        # No decisions file, no context; a run that never existed, no crash.
        (self.rd / "gate-decisions.md").unlink()
        self.assertEqual(o.rework_context(RUN, "03-coding"), "")
        self.assertEqual(o.rework_context("feat-never", "03-coding"), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
