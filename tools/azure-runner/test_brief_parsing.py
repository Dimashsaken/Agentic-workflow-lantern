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


if __name__ == "__main__":
    unittest.main(verbosity=2)
