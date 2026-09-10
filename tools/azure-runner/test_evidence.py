"""Evidence resolution rejects fabricated locations without mistaking it for truth."""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import evidence
import factory as f
import orchestrator as o
from test_factory import Base, RUN, git, write_md, write_json


class Evidence(Base):
    def test_product_and_run_references_resolve(self):
        write_md(self.rd / "04-qa-dev/results.txt", "test_save: PASS\n")
        refs = [{"path": "product/src/api/items.py", "line": 2},
                {"path": "04-qa-dev/results.txt", "line": 1}]
        self.assertEqual(evidence.validation_problems(refs, self.rd, self.product), [])
        self.assertEqual(evidence.validation_problems("product/src/api/items.py:1; 04-qa-dev/results.txt:1",
                                                     self.rd, self.product), [])

    def test_sentence_missing_file_empty_file_and_invalid_line_fail(self):
        write_md(self.rd / "04-qa-dev/empty.txt", "")
        for refs in ("all tests passed", "does-not-exist.py", "product/src/api/items.py:999",
                     "04-qa-dev/empty.txt", [{"path": "product/src/api/items.py", "line": True}],
                     [{"path": "product/src/api/items.py", "line": 0}], [], [None], True):
            with self.subTest(refs=refs):
                self.assertTrue(evidence.validation_problems(refs, self.rd, self.product))

    def test_secret_traversal_cross_run_and_self_references_fail(self):
        write_md(self.rd / "05-post-coding/validation.md", "claim")
        for path in ("../outside", "/etc/passwd", "product/.env", "product/.git/config",
                     "workflow/runs/another/04-qa-dev/report.md", "05-post-coding/validation.md",
                     "05-post-coding/VALIDATION.MD", "WORKFLOW/RUNS/another/04-qa-dev/report.md"):
            with self.subTest(path=path):
                self.assertTrue(evidence.validation_problems([{"path": path}], self.rd, self.product))

    def test_product_evidence_cannot_pass_without_a_checkout(self):
        self.assertTrue(evidence.validation_problems("product/src/api/items.py:1", self.rd, None))

    def test_research_paths_cannot_escape_into_an_existing_host_file(self):
        (self.tmp / "outside.txt").write_text("exists")
        self.assertEqual(f._paths_exist(["../outside.txt"], self.product), ["../outside.txt"])

    def test_validation_envelope_uses_the_resolver(self):
        self.story()
        write_md(self.rd / "05-post-coding/validation.md", "review")
        data = {"kind": "validation", "run_id": RUN, "fix_now": [], "verdict": "pass",
                "criteria": [{"id": f"AC-{i}", "status": "covered",
                              "evidence": [{"path": "product/src/api/items.py", "line": 1}]}
                             for i in (1, 2, 3)]}
        write_json(self.rd / "05-post-coding/validation.json", data)
        self.assertEqual(f.check_envelope(RUN, "05-post-coding.validate", self.product), [])
        data["criteria"][0]["evidence"][0]["line"] = 500
        write_json(self.rd / "05-post-coding/validation.json", data)
        self.assertIn("AC-1: evidence line 500", "\n".join(f.check_envelope(RUN, "05-post-coding.validate", self.product)))

    def review(self):
        base = git("rev-parse", "HEAD", cwd=self.product)
        (self.product / "src/api/items.py").write_text("def items():\n    return [1]\n")
        git("add", "-A", cwd=self.product)
        git("commit", "-qm", "change", cwd=self.product)
        head = git("rev-parse", "HEAD", cwd=self.product)
        return {"base_sha": base, "head_sha": head}

    def test_review_file_and_line_resolve_to_the_committed_revision(self):
        handoff = self.review()
        finding = {"id": "R-1", "file": "src/api/items.py", "line": 2}
        self.assertEqual(evidence.review_problems([finding], handoff, self.product), [])
        # An uncommitted edit cannot manufacture a line in the published revision.
        (self.product / "src/api/items.py").write_text("line\n" * 100)
        finding["line"] = 80
        self.assertTrue(evidence.review_problems([finding], handoff, self.product))

    def test_review_rejects_unchanged_file_and_wrong_head(self):
        handoff = self.review()
        self.assertTrue(evidence.review_problems([{"id": "R-1", "file": "README.md", "line": 1}], handoff, self.product))
        handoff["head_sha"] = handoff["base_sha"]
        self.assertTrue(evidence.review_problems([], handoff, self.product))

    def test_review_allows_general_findings_for_missing_work(self):
        handoff = self.review()
        self.assertEqual(evidence.review_problems([{"id": "R-1", "file": "", "line": None}], handoff, self.product), [])

    def test_deleted_file_is_valid_only_without_a_new_line(self):
        base = git("rev-parse", "HEAD", cwd=self.product)
        git("rm", "README.md", cwd=self.product)
        git("commit", "-qm", "delete", cwd=self.product)
        handoff = {"base_sha": base, "head_sha": git("rev-parse", "HEAD", cwd=self.product)}
        self.assertEqual(evidence.review_problems([{"file": "README.md", "line": None}], handoff, self.product), [])
        self.assertTrue(evidence.review_problems([{"file": "README.md", "line": 1}], handoff, self.product))

    def test_report_status_is_an_explicit_postcondition(self):
        report = self.rd / "06-security/report.md"
        conn = AsyncMock()
        conn.fetchval.return_value = 1
        with patch.object(o, "REPO", f.REPO):
            for text in ("", "looks great", "- **Status:** WAIVED\n", "Status: IN-PROGRESS\n"):
                write_md(report, text)
                problems = asyncio.run(o.check_postconditions(conn, "security", RUN, "06-security", "key"))
                self.assertTrue(problems, text)
            for text in ("Status: PASS\n", "- **Status:** PASS-WITH-NOTES\n"):
                write_md(report, text)
                self.assertEqual(asyncio.run(o.check_postconditions(conn, "security", RUN, "06-security", "key")), [])
            write_md(report, "Status: PASS\n\nStatus: BLOCKED\n## Open questions\nWhich repo?\n")
            self.assertTrue(asyncio.run(o.check_postconditions(conn, "security", RUN, "06-security", "key")))


if __name__ == "__main__":
    import unittest
    unittest.main()
