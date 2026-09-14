"""Regression for bug-20260908-help-crash-without-env (D20 cumulative suite).

`pipeline.py` used to wire the Azure OpenAI client BEFORE building its argparse tree,
so on a machine without `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY` every
invocation — `--help`, `bug --help`, `init-db`, `status` — died with a credentials
traceback instead of doing its database-only work or printing usage.

The test launches the real entry point in a clean subprocess with both variables
present but BLANK (what a copied `.env.example` looks like; `load_dotenv` does not
override an existing key, so the checkout's own `.env` cannot leak credentials into
the test) and expects usage text, exit 0 and no traceback. A control run with dummy
credentials separates "help crashed on credentials" from "the module does not import".
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PIPELINE = REPO / "tools" / "azure-runner" / "pipeline.py"
BLANK = {"AZURE_OPENAI_ENDPOINT": "", "AZURE_OPENAI_API_KEY": "", "AZURE_OPENAI_API_VERSION": "",
         "LANTERN_MODEL_REASONING": "", "LANTERN_MODEL_CODING": "", "LANTERN_MODEL_FAST": ""}


def run_cli(*args: str, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, **BLANK, **(extra_env or {})}
    return subprocess.run([sys.executable, str(PIPELINE), *args], capture_output=True,
                          text=True, env=env, cwd=str(REPO), timeout=120)


class HelpWithoutModelCredentials(unittest.TestCase):
    def assert_usage(self, r: subprocess.CompletedProcess, needle: str) -> None:
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertIn("usage:", r.stdout)
        self.assertIn(needle, r.stdout)
        self.assertNotIn("Traceback", r.stderr)
        self.assertNotIn("Missing credentials", r.stderr)

    def test_top_level_help(self):
        self.assert_usage(run_cli("--help"), "init-db")

    def test_bug_subcommand_help(self):
        self.assert_usage(run_cli("bug", "--help"), "--source")

    def test_control_run_with_dummy_credentials(self):
        r = run_cli("--help", extra_env={"AZURE_OPENAI_ENDPOINT": "https://x.openai.azure.com",
                                         "AZURE_OPENAI_API_KEY": "dummy"})
        self.assert_usage(r, "daemon")

    def test_model_commands_fail_with_one_readable_line(self):
        # `daemon` cannot do anything without a model: a one-line exit, not a traceback.
        r = run_cli("daemon")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Azure OpenAI is not configured", r.stderr)
        self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
