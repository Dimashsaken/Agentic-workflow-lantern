"""The run page's "Where the code goes" card (D27), built from plain rows — no database.

    ..\\azure-runner\\.venv\\Scripts\\python -m unittest test_delivery -v

The card has to answer, at every point in a run's life, the question the Tender runs
left open: which repository does this code land in, on which branch, is there a pull
request yet, and has a human merged it. A pushed branch and an opened pull request are
separate steps, a local checkout gets no pull request, and only a human merges.
"""
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "azure-runner"))

import delivery  # noqa: E402

T0 = datetime(2026, 9, 15, 8, 0, tzinfo=timezone.utc)
GH = "https://github.com/Career-Hackers/careerhackers-ai-ats"
RUN = "feat-20260915-export"
BRANCH = "feat/20260915-export"
PR = GH + "/pull/12"


def run(**over):
    row = {"id": RUN, "status": "running", "current_stage": "00-story.write", "product_repo": GH,
           "product_branch": "main", "product_working_branch": None, "coding_mode": "auto"}
    row.update(over)
    return row


def ev(type_, minutes, **data):
    return {"type": type_, "at": T0 + timedelta(minutes=minutes), "data": json.dumps(data)}


def gate(status="pending", **payload):
    return {"gate": "code_complete", "status": status, "payload": json.dumps(payload),
            "decided_by": None if status == "pending" else "justin", "external_ref": payload.get("pr_url")}


def states(model):
    return {s["key"]: s["state"] for s in model["steps"]}


PUBLISHED = ev("branch_published", 10, branch=BRANCH, head_sha="abcdef1234567890", pushed=True, pr_url=PR)


class WhereTheCodeGoes(unittest.TestCase):
    def test_before_coding_it_says_where_the_branch_will_come_from(self):
        m = delivery.build(run(), branch=BRANCH)
        self.assertEqual(states(m), {"repo": "done", "branch": "todo", "pr": "todo",
                                     "approval": "todo", "merge": "todo"})
        self.assertIn("`feat/20260915-export` is created from `main` when coding starts", m["steps"][1]["text"])
        self.assertEqual((m["name"], m["headline"]), ("Career-Hackers/careerhackers-ai-ats", "No branch yet"))

    def test_continuing_an_existing_branch_says_so(self):
        m = delivery.build(run(product_working_branch="feat/20260901-old"), branch="feat/20260901-old")
        self.assertIn("Continues the existing `feat/20260901-old`", m["steps"][1]["text"])

    def test_no_repository_is_a_stop_with_the_way_to_fix_it(self):
        m = delivery.build(run(product_repo=None), branch=BRANCH)
        self.assertEqual(m["steps"][0]["state"], "fail")
        self.assertEqual(m["steps"][0]["href"], f"/run/{RUN}/repo")
        self.assertIn("no repository connected", delivery.render_line(m, RUN))

    def test_the_whole_life_coding_pushed_pr_approved_merged(self):
        m = delivery.build(run(current_stage="03-coding"), branch=BRANCH)
        self.assertEqual((states(m)["branch"], m["headline"]), ("now", "Coding"))

        m = delivery.build(run(current_stage="03-coding"), [PUBLISHED],
                           [gate("pending", pr_url=PR, pr_number=12)], branch=BRANCH)
        self.assertEqual(states(m), {"repo": "done", "branch": "done", "pr": "done",
                                     "approval": "now", "merge": "todo"})
        self.assertEqual((m["pr_number"], m["headline"], m["pr_url"]), (12, "PR #12", PR))
        self.assertIn("`abcdef12`", m["steps"][1]["text"])

        m = delivery.build(run(current_stage="04-qa-dev"), [PUBLISHED],
                           [gate("approved", pr_url=PR, pr_number=12)], branch=BRANCH)
        self.assertEqual((states(m)["approval"], states(m)["merge"]), ("done", "now"))
        self.assertIn("by justin", m["steps"][3]["text"])
        self.assertIn("babysitter", m["steps"][4]["text"])

        merged = ev("branch_merged", 90, branch=BRANCH, base="main", via="github", pr_number=12)
        m = delivery.build(run(current_stage="07-qa-staging"), [merged, PUBLISHED],
                           [gate("approved", pr_url=PR)], branch=BRANCH)
        self.assertEqual((states(m)["merge"], m["headline"]), ("done", "Merged"))
        self.assertEqual(m["pr_number"], 12, "the number is read back from the URL")

    def test_a_pull_request_that_could_not_be_opened_says_how_to_retry(self):
        pushed = ev("branch_published", 10, branch=BRANCH, head_sha="1" * 40, pushed=True, pr_url=None)
        refused = ev("pr_not_opened", 11, branch=BRANCH, error="token cannot open pull requests")
        m = delivery.build(run(current_stage="03-coding"), [pushed, refused],
                           [gate("pending", compare_url=GH + "/compare/main...x", pushed=True)], branch=BRANCH)
        pr = m["steps"][2]
        self.assertEqual(pr["state"], "warn")
        self.assertIn("token cannot open pull requests", pr["text"])
        self.assertIn(f"pipeline.py publish {RUN}", pr["text"])
        self.assertEqual(pr["link"], "Compare")
        self.assertEqual(m["headline"], "Branch pushed")

    def test_a_conflict_shows_until_the_branch_moves_again(self):
        approved = [gate("approved", pr_url=PR, pr_number=12)]
        conflict = ev("merge_conflict", 40, branch=BRANCH, base="main", files=["app.py"])
        m = delivery.build(run(current_stage="05-post-coding"), [PUBLISHED, conflict], approved, branch=BRANCH)
        self.assertEqual((states(m)["merge"], m["headline"]), ("warn", "Merge conflict"))
        moved = ev("branch_updated", 60, branch=BRANCH, base="main", merge_sha="2" * 40, gate="green")
        m = delivery.build(run(current_stage="05-post-coding"), [PUBLISHED, conflict, moved], approved, branch=BRANCH)
        self.assertEqual(states(m)["merge"], "now")
        self.assertIn("`22222222`", m["steps"][1]["text"], "the head follows the babysitter's merge")

    def test_a_closed_pull_request_is_a_stop(self):
        closed = ev("pr_closed", 50, branch=BRANCH, merged=False, closed=True, via="github")
        m = delivery.build(run(current_stage="06-security"), [PUBLISHED, closed],
                           [gate("approved", pr_url=PR)], branch=BRANCH)
        self.assertEqual((states(m)["merge"], m["headline"]), ("fail", "Pull request closed"))

    def test_a_local_checkout_gets_its_branch_in_place_and_no_pull_request(self):
        landed = ev("branch_published", 10, branch=BRANCH, head_sha="3" * 40, pushed=False, pr_url=None)
        m = delivery.build(run(product_repo="/srv/work/app", current_stage="03-coding"), [landed],
                           [gate("pending", pushed=False)], branch=BRANCH)
        self.assertEqual(states(m)["branch"], "warn")
        self.assertIn("landed in the checkout", m["steps"][1]["text"])
        self.assertEqual(states(m)["pr"], "skip")
        self.assertEqual(m["headline"], "Branch in the checkout", "a landed branch is past coding")
        self.assertIn(" · <a href='/run/feat-20260915-export/repo' class='lnk'>change</a>",
                      delivery.render_line(m, RUN))

    def test_human_coding_leaves_branch_and_pull_request_to_the_developer(self):
        m = delivery.build(run(coding_mode="human", current_stage="03-coding"), branch=BRANCH)
        self.assertEqual(states(m)["branch"], "now")
        self.assertIn("assigned developer", m["steps"][1]["text"])
        self.assertIn("developer opens it", m["steps"][2]["text"])

    def test_the_factory_repository_is_flagged(self):
        m = delivery.build(run(product_repo="https://github.com/Dimashsaken/Agentic-workflow-lantern"),
                           branch=BRANCH, factory=True)
        self.assertEqual(m["steps"][0]["state"], "warn")
        self.assertIn("factory repository", delivery.render_card(m, RUN, "/repos/x"))
        self.assertIn("factory repository", delivery.render_line(m, RUN))

    def test_events_this_card_does_not_read_are_ignored(self):
        noise = {"type": "stage_started", "at": T0, "data": "not json"}
        m = delivery.build(run(), [noise, {"type": "branch_published", "at": None, "data": None}], branch=BRANCH)
        self.assertEqual(states(m)["branch"], "warn", "a published event without data is still a publication")
        self.assertEqual(m["headline"], "Branch not pushed")


class Rendering(unittest.TestCase):
    def test_the_card_escapes_and_marks_code(self):
        m = delivery.build(run(product_branch="<main>"), [PUBLISHED],
                           [gate("pending", pr_url=PR, pr_number=12)], branch=BRANCH)
        html = delivery.render_card(m, RUN, "/repos/career-hackers-careerhackers-ai-ats-abc123")
        self.assertIn("Where the code goes", html)
        self.assertIn("href='/repos/career-hackers-careerhackers-ai-ats-abc123'", html)
        self.assertIn("&lt;main&gt;", html)
        self.assertNotIn("<main>", html)
        self.assertIn(f"href='{PR}' target='_blank' rel='noopener'", html)
        self.assertIn("<code>feat/20260915-export</code>", html)
        self.assertIn("class='sr-only'", html, "each step's state is spoken, not only coloured")

    def test_md_code_keeps_an_unmatched_backtick_literal(self):
        self.assertEqual(delivery.md_code("a `b` c"), "a <code>b</code> c")
        self.assertEqual(delivery.md_code("a `b"), "a `b")
        self.assertEqual(delivery.md_code("<x>"), "&lt;x&gt;")


if __name__ == "__main__":
    unittest.main(verbosity=2)
