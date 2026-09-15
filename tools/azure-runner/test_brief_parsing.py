"""Brief field parsing — the template's blank fields must read as unset.

    .venv/Scripts/python test_brief_parsing.py      (no database, no Azure)

Found 2026-09-08 on the first stage-0 run: `- **Working branch:**` left blank (as the
template instructs) was parsed as the NEXT line, and `pipeline.py run` refused
"- **Coding mode:** human" as a branch name. A run that cannot be created is the
cheapest possible failure to guard.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pipeline as p  # noqa: E402

BRIEF = """# Feature Brief: x

- **Run ID:** feat-20260908-x
- **Product repo:** C:/repos/product
- **Base branch:** main
- **Working branch:**
- **Coding mode:** human

## Problem
"""


class BriefFields(unittest.TestCase):
    def test_blank_working_branch_is_unset_not_the_next_line(self):
        repo, base, work = p.parse_brief_product(BRIEF)
        self.assertEqual((repo, base, work), ("C:/repos/product", "main", ""))
        self.assertEqual(p.parse_brief_coding_mode(BRIEF), "human")

    def test_filled_fields_and_placeholders(self):
        text = BRIEF.replace("- **Working branch:**", "- **Working branch:** feat/x-continue")
        self.assertEqual(p.parse_brief_product(text)[2], "feat/x-continue")
        text = BRIEF.replace("- **Working branch:**", "- **Working branch:** <existing feat/* branch or blank>")
        self.assertEqual(p.parse_brief_product(text)[2], "")
        text = BRIEF.replace("- **Base branch:** main", "- **Base branch:** TBD")
        self.assertEqual(p.parse_brief_product(text)[1], "")

    def test_blank_coding_mode_is_unset(self):
        text = BRIEF.replace("- **Coding mode:** human", "- **Coding mode:**")
        self.assertEqual(p.parse_brief_coding_mode(text), "")
        text = BRIEF.replace("- **Coding mode:** human", "- **Coding mode:** `auto`")
        self.assertEqual(p.parse_brief_coding_mode(text), "auto")

    def test_trailing_spaces_and_case(self):
        text = BRIEF.replace("- **Working branch:**", "- **working branch:**   fix/y   ")
        self.assertEqual(p.parse_brief_product(text)[2], "fix/y")

    def test_inline_html_comment_is_annotation_not_value(self):
        # Found 2026-09-12 creating feat-20260911-tender-onboarding: the brief annotates
        # the repo line, and the comment rode along into the URL handed to git.
        text = BRIEF.replace(
            "- **Product repo:** C:/repos/product",
            "- **Product repo:** https://github.com/org/repo   <!-- seed lives here for now -->")
        self.assertEqual(p.parse_brief_product(text)[0], "https://github.com/org/repo")
        text = BRIEF.replace("- **Coding mode:** human",
                             "- **Coding mode:** auto   <!-- human = …; auto = … (D14) -->")
        self.assertEqual(p.parse_brief_coding_mode(text), "auto")
        text = BRIEF + "- **Design mode:** html <!-- paper = …; html = … (D25) -->\n"
        self.assertEqual(p.parse_brief_design_mode(text), "html")
        # A field that is ONLY an annotation is blank, and an unclosed comment does not
        # leak its text into the value either.
        text = BRIEF.replace("- **Working branch:**", "- **Working branch:** <!-- fresh -->")
        self.assertEqual(p.parse_brief_product(text)[2], "")
        text = BRIEF.replace("- **Base branch:** main", "- **Base branch:** main <!-- unclosed")
        self.assertEqual(p.parse_brief_product(text)[1], "main")

    def test_the_shipped_template_reads_as_its_defaults(self):
        template = Path(__file__).resolve().parents[2] / "workflow" / "briefs" / "_TEMPLATE.md"
        text = template.read_text(encoding="utf-8")
        self.assertEqual(p.parse_brief_coding_mode(text), "human")
        self.assertEqual(p.parse_brief_design_mode(text), "paper")
        self.assertEqual(p.parse_brief_product(text), ("", "main", ""))

    def test_the_tender_briefs_parse_to_their_targets(self):
        briefs = Path(__file__).resolve().parents[2] / "workflow" / "briefs"
        for name in ("tender-onboarding", "tender-catalog-orders", "tender-escalations"):
            text = (briefs / f"{name}.md").read_text(encoding="utf-8")
            with self.subTest(brief=name):
                # Tender lives in its own repository since 2026-09-14. Before that these
                # briefs named this factory repository with a product/tender-whatsapp base,
                # which is how the Tender runs landed their branches here (D27).
                self.assertEqual(
                    p.parse_brief_product(text),
                    ("https://github.com/Dimashsaken/tender-whatsapp", "main", ""))
                self.assertFalse(p.product_repos.is_factory(p.parse_brief_product(text)[0]))
                self.assertEqual(p.parse_brief_coding_mode(text), "auto")
                self.assertEqual(p.parse_brief_design_mode(text), "html")


if __name__ == "__main__":
    unittest.main(verbosity=2)
