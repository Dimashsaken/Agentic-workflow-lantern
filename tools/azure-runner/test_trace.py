"""Execution traces (D22): written for every stage execution, never carrying a secret.

    .venv/Scripts/python test_trace.py

Stdlib only — no database, no model, no Agents SDK objects: fake run results with the
attributes write_trace reads (new_items / raw_item / output / context_wrapper.usage).
Contract under test:
  * the file lands at <stage-dir>/trace/<key>.json with a Windows-safe name and carries
    the compiled prompt, the kickoff, the tool calls in order and the merged usage;
  * the "# QA target" section is dropped and a QA password never reaches the file —
    neither through the prompt nor through a tool output — while prose that merely
    mentions "token" stays readable;
  * outputs pair with their calls by call id (out of order) or by position (no id);
  * args/outputs are truncated but their full lengths are kept;
  * nothing here can raise into the stage: garbage in → a line on stderr, no exception.
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import factory  # noqa: E402

RUN, STAGE = "feat-20260908-trace", "04-qa-dev"
KEY = f"{RUN}:{STAGE}:2"
PASSWORD = "Sup3r-Secret!Pw"


def call(name, args, cid=None):
    raw = SimpleNamespace(name=name, arguments=args, call_id=cid, type="function_call")
    return SimpleNamespace(type="tool_call_item", raw_item=raw)


def output(text, cid=None):
    raw = {"type": "function_call_output", "call_id": cid, "output": text}
    return SimpleNamespace(type="tool_call_output_item", raw_item=raw, output=text)


def result(items, final="done", inp=100, cached=40, out=10, requests=2):
    usage = SimpleNamespace(requests=requests, input_tokens=inp, output_tokens=out,
                            total_tokens=inp + out,
                            input_tokens_details=SimpleNamespace(cached_tokens=cached))
    return SimpleNamespace(new_items=items, final_output=final,
                           context_wrapper=SimpleNamespace(usage=usage))


PROMPT = (
    "# Software Factory (codename Lantern)\n\nThe token ledger is the only basis for spend.\n"
    "Agents act on GitHub as lantern-bot; the bot token never enters a sandbox.\n\n"
    "# Your assignment\nYou are the **qa-dev** agent.\n\n"
    "# QA target (dev environment)\n- **Base URL:** `http://172.17.0.1:8080` — open THIS address.\n"
    f"- **Login:** username `qa-dev` / password `{PASSWORD}` — provisioned test credentials.\n"
    "Never invent or guess credentials.\n\n"
    "# qa-dev/charter.md\n## Mission\nBreak the feature before users can.\n"
)


class TraceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lantern-trace-"))
        self._repo = factory.REPO
        factory.REPO = self.tmp
        self._env = dict(os.environ)
        os.environ["LANTERN_QA_DEV_PASS"] = PASSWORD
        os.environ["QA_PASS"] = PASSWORD
        os.environ["LANTERN_WEB_USERS"] = "justin:Web-Pass-99,qa:qa-web-pw"
        os.environ["LANTERN_DATABASE_URL"] = "postgresql+asyncpg://lantern:DbPw-123@localhost:5432/lantern"
        os.environ.pop("LANTERN_PRICE_JSON", None)

    def tearDown(self):
        factory.REPO = self._repo
        os.environ.clear()
        os.environ.update(self._env)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, results, prompt=PROMPT, kickoff="Begin your 04-qa-dev session."):
        err = io.StringIO()
        with redirect_stderr(err):
            path = factory.write_trace(RUN, STAGE, KEY, prompt, kickoff, results)
        return path, err.getvalue()

    # ── placement and shape ──────────────────────────────────────────────────

    def test_file_lands_in_the_stage_trace_dir_with_a_safe_name(self):
        path, _ = self.write([result([call("read_file", '{"path": "brief.md"}', "c1"),
                                      output("# Brief", "c1")])])
        self.assertIsNotNone(path)
        self.assertEqual(path.parent, self.tmp / "workflow" / "runs" / RUN / STAGE / "trace")
        self.assertNotIn(":", path.name)
        self.assertTrue(path.name.endswith(".json"))
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["kind"], "trace")
        self.assertEqual(data["execution_key"], KEY)
        self.assertEqual(data["stage"], STAGE)
        self.assertEqual(data["kickoff"], "Begin your 04-qa-dev session.")
        self.assertIn("# Your assignment", data["instructions"])
        self.assertEqual(len(data["tool_calls"]), 1)
        self.assertEqual(data["tool_calls"][0]["name"], "read_file")
        self.assertEqual(data["tool_calls"][0]["output"], "# Brief")
        self.assertEqual(data["usage"], {"requests": 2, "input_tokens": 100, "output_tokens": 10,
                                         "total_tokens": 110, "cached_input_tokens": 40})

    def test_read_trace_finds_it_by_key(self):
        self.write([result([])])
        data = factory.read_trace(RUN, STAGE, KEY)
        self.assertIsNotNone(data)
        self.assertEqual(data["execution_key"], KEY)
        self.assertIsNone(factory.read_trace(RUN, STAGE, f"{RUN}:{STAGE}:9"))

    # ── redaction ────────────────────────────────────────────────────────────

    def test_qa_target_section_is_dropped_and_the_password_never_lands(self):
        path, _ = self.write([result([])])
        text = path.read_text(encoding="utf-8")
        self.assertNotIn(PASSWORD, text)
        self.assertNotIn("172.17.0.1", text)                 # the whole section is gone
        data = json.loads(text)
        self.assertIn("# QA target\n[redacted", data["instructions"])
        self.assertIn("# qa-dev/charter.md", data["instructions"])   # the next section survives
        self.assertIn("# Your assignment", data["instructions"])
        self.assertTrue(data["redaction"]["qa_target_dropped"])

    def test_prose_mentioning_tokens_stays_readable(self):
        path, _ = self.write([result([])])
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("The token ledger is the only basis for spend.", data["instructions"])
        self.assertIn("the bot token never enters a sandbox", data["instructions"])

    def test_password_in_a_tool_output_or_args_is_masked(self):
        items = [call("product_shell", f'{{"command": "curl -u qa:{PASSWORD} http://x"}}', "c1"),
                 output(f"QA_PASS={PASSWORD}\nAuthorization: Bearer eyJabcdefghijk.lmnopqrstuvw.xyz0123456789\n"
                        "token: abcdef123456 password: hunter2 ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123", "c1")]
        path, _ = self.write([result(items)])
        text = path.read_text(encoding="utf-8")
        for secret in (PASSWORD, "eyJabcdefghijk", "abcdef123456", "hunter2",
                       "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123", "Web-Pass-99", "qa-web-pw", "DbPw-123"):
            self.assertNotIn(secret, text, secret)
        data = json.loads(text)
        self.assertIn("[redacted]", data["tool_calls"][0]["args"])
        self.assertIn("QA_PASS=[redacted]", data["tool_calls"][0]["output"])

    def test_known_env_secret_values_are_scrubbed_even_without_a_keyword(self):
        # A credential can be echoed by a tool with no "password:" label in front of it.
        path, _ = self.write([result([call("read_file", "{}", "c1"),
                                      output(f"the form accepted {PASSWORD} and logged in", "c1")])])
        text = path.read_text(encoding="utf-8")
        self.assertNotIn(PASSWORD, text)
        self.assertIn("the form accepted [redacted] and logged in", text)

    def test_a_dictionary_word_password_does_not_scrub_the_whole_trace(self):
        """The local dev database password is literally "lantern". Masking it wherever it
        appeared turned every `lantern.toml` path in a trace into `[redacted].toml` — a
        fail-safe that destroyed the artifact the drawer exists to show. A bare lowercase
        word is left to the keyword and URL patterns, which still catch it as a credential."""
        os.environ["LANTERN_DATABASE_URL"] = "postgresql+asyncpg://lantern:lantern@localhost:5432/lantern"
        self.assertNotIn("lantern", factory.secret_values())
        out = factory.redact('read_file {"path":"product/lantern.toml"}')
        self.assertIn("product/lantern.toml", out)                 # the path survives
        # …but the same word AS a credential is still masked
        self.assertEqual(factory.redact("psql postgresql://lantern:lantern@db:5432/lantern"),
                         "psql postgresql://lantern:[redacted]@db:5432/lantern")
        self.assertIn("[redacted]", factory.redact("PGPASSWORD=lantern"))
        self.assertIn("[redacted]", factory.redact("password: lantern"))
        # a long or mixed value is still scrubbed everywhere it appears
        os.environ["QA_PASS"] = "correct-horse-42"
        self.assertIn("correct-horse-42", factory.secret_values())
        self.assertNotIn("correct-horse-42", factory.redact("the log said correct-horse-42 once"))
        os.environ["QA_PASS"] = "extraordinarily"          # 15 lowercase letters — long enough
        self.assertIn("extraordinarily", factory.secret_values())

    def test_url_credentials_and_short_values(self):
        self.assertEqual(factory.redact("git fetch https://bot:s3cretpw@github.com/x"),
                         "git fetch https://bot:[redacted]@github.com/x")
        os.environ["QA_PASS"] = "ab"            # too short to scrub: "cabin" must survive
        self.assertIn("cabin", factory.redact("a cabin in the woods"))
        self.assertEqual(factory.redact(""), "")

    def test_redact_handles_absent_qa_section(self):
        out = factory.redact("# A\n\nplain text\n\n# B\nmore")
        self.assertEqual(out, "# A\n\nplain text\n\n# B\nmore")

    # ── tool-call extraction ─────────────────────────────────────────────────

    def test_calls_keep_order_and_pair_outputs_by_id_or_position(self):
        items = [call("list_dir", '{"path": "."}', "a"), call("read_file", '{"path": "x"}', "b"),
                 output("X CONTENT", "b"), output("dir listing", "a"),
                 call("write_file", '{"path": "y"}'), output("wrote y")]
        calls = factory.extract_tool_calls([result(items)])
        self.assertEqual([c["name"] for c in calls], ["list_dir", "read_file", "write_file"])
        self.assertEqual([c["order"] for c in calls], [1, 2, 3])
        self.assertEqual(calls[0]["output"], "dir listing")
        self.assertEqual(calls[1]["output"], "X CONTENT")
        self.assertEqual(calls[2]["output"], "wrote y")           # positional fallback

    def test_turn_numbers_and_usage_merge_across_fix_rounds(self):
        r1 = result([call("a", "{}", "1"), output("o", "1")], inp=100, cached=50, out=10, requests=1)
        r2 = result([call("b", "{}", "2"), output("o", "2")], inp=200, cached=100, out=20, requests=3)
        path, _ = self.write([r1, r2])
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual([c["turn"] for c in data["tool_calls"]], [1, 2])
        self.assertEqual(len(data["turns"]), 2)
        self.assertEqual(data["usage"]["input_tokens"], 300)
        self.assertEqual(data["usage"]["cached_input_tokens"], 150)
        self.assertEqual(data["usage"]["requests"], 4)

    def test_args_and_outputs_are_truncated_with_full_lengths_kept(self):
        big_args = "x" * (factory.TRACE_ARGS_MAX + 500)
        big_out = "y" * (factory.TRACE_OUTPUT_MAX + 5000)
        calls = factory.extract_tool_calls([result([call("t", big_args, "1"), output(big_out, "1")])])
        self.assertEqual(len(calls[0]["args"]), factory.TRACE_ARGS_MAX)
        self.assertEqual(calls[0]["args_chars"], factory.TRACE_ARGS_MAX + 500)
        self.assertEqual(len(calls[0]["output"]), factory.TRACE_OUTPUT_MAX)
        self.assertEqual(calls[0]["output_chars"], factory.TRACE_OUTPUT_MAX + 5000)

    def test_dict_arguments_and_non_string_outputs_are_serialised(self):
        raw = {"name": "mcp_tool", "arguments": {"a": 1}, "call_id": "z"}
        item = SimpleNamespace(type="tool_call_item", raw_item=raw)
        out = SimpleNamespace(type="tool_call_output_item", raw_item={"call_id": "z"}, output={"ok": True})
        calls = factory.extract_tool_calls([result([item, out])])
        self.assertEqual(calls[0]["name"], "mcp_tool")
        self.assertEqual(json.loads(calls[0]["args"]), {"a": 1})
        self.assertEqual(json.loads(calls[0]["output"]), {"ok": True})

    # ── never raises ─────────────────────────────────────────────────────────

    def test_garbage_never_raises(self):
        class Bad:
            @property
            def new_items(self):
                raise RuntimeError("boom")
        err = io.StringIO()
        with redirect_stderr(err):
            p1 = factory.write_trace(RUN, STAGE, KEY, None, None, [object(), Bad()])
            p2 = factory.write_trace(RUN, STAGE, KEY, PROMPT, "k", None)
        self.assertIsNone(p1)
        self.assertIn("not written", err.getvalue())
        self.assertIsNotNone(p2)                    # None results = an empty trace, still written

    def test_a_failing_disk_only_prints(self):
        factory.REPO = self.tmp / "missing" / "file.txt"
        (self.tmp / "missing").mkdir()
        (self.tmp / "missing" / "file.txt").write_text("not a dir", encoding="utf-8")
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertIsNone(factory.write_trace(RUN, STAGE, KEY, PROMPT, "k", [result([])]))
        self.assertIn("not written", err.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
