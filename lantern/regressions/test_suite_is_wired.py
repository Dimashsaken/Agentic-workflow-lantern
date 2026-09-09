"""Sentinel: the cumulative regression suite exists and is discovered by the gate (D20).

Every bug run adds a `test_<slug>.py` beside this file; this repo's lantern.toml runs the
directory on every coding run. Zero tests would make `unittest discover` exit 5 and
turn the gate red, so this file also guarantees the suite is never empty.
"""

import py_compile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


class RegressionSuite(unittest.TestCase):
    def test_every_regression_test_compiles(self):
        files = sorted(HERE.glob("test_*.py"))
        self.assertTrue(files)
        for f in files:
            py_compile.compile(str(f), doraise=True)

    def test_readme_explains_the_rule(self):
        self.assertIn("every run", (HERE / "README.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
