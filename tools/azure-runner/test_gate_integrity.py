"""No empty greens, no contradictory verdicts, no builder-edited gate policy."""

import asyncio
from copy import deepcopy
import json
from unittest.mock import AsyncMock, patch

from test_factory import Base, RUN, git, write_json
import factory as f


class GateIntegrity(Base):
    def green(self):
        return f.run_quality_gate(RUN, "03-coding", self.product, "key", 0)

    def test_malformed_quality_policy_is_a_red_gate(self):
        for text in ('quality = "invalid"', '[quality]\nlint = "exit 0"',
                     '[quality]\ntest = false', '[quality]\ntest = ""',
                     '[quality]\ntest = "exit 0"\ntimeout_s = true'):
            with self.subTest(text=text):
                (self.product / "lantern.toml").write_text(text)
                with patch.object(f, "run_command") as run:
                    gate = self.green()
                self.assertFalse(gate["passed"])
                run.assert_not_called()

    def test_missing_tests_stop_before_any_model_call(self):
        (self.product / "lantern.toml").unlink()
        turn = AsyncMock()
        with self.assertRaisesRegex(ValueError, "held"):
            asyncio.run(f.coding_turns(turn, "build", run_id=RUN, stage="03-coding",
                                      root=self.product, execution_key="key"))
        turn.assert_not_called()
        self.assertTrue(f.check_quality_gate(RUN, "03-coding", "key"))

    def test_agent_cannot_make_a_failing_policy_green_by_replacing_it(self):
        policy = self.product / "lantern.toml"
        policy.write_text('[quality]\ntest = "exit 1"\n')

        async def turn(_):
            policy.write_text('[quality]\ntest = "echo fabricated green"\n')
            return {}

        with patch.object(f, "run_command") as run:
            _, gate = asyncio.run(f.coding_turns(turn, "build", run_id=RUN, stage="03-coding",
                                               root=self.product, execution_key="key", max_rounds=0))
        self.assertFalse(gate["passed"])
        self.assertIn("changed during this execution", gate["results"][-1]["output_tail"])
        run.assert_not_called()

    def test_command_cannot_replace_policy_during_the_gate(self):
        def command(*_):
            (self.product / "lantern.toml").write_text('[quality]\ntest = "exit 0"\n')
            return {"passed": True, "exit": 0, "seconds": 0, "output_tail": ""}
        with patch.object(f, "run_command", side_effect=command):
            gate = self.green()
        self.assertFalse(gate["passed"])

    def test_gate_summary_cannot_override_its_results(self):
        gate = self.green()
        self.assertTrue(gate["passed"], gate)
        corruptions = [
            {"kind": "claim"}, {"run_id": "other"}, {"stage": "04-qa-dev"},
            {"stage": "03-coding.api"}, {"builder": "api"}, {"round": True},
            {"configured": []}, {"configured": ["test", "lint"]},
            {"configured": ["test", "test"]}, {"configured": [False]},
            {"results": []}, {"results": "everything passed"}, {"results": ["test passed"]},
            {"passed": "true"}, {"config_sha256": "unverified"},
        ]
        for update in corruptions:
            with self.subTest(update=update):
                bad = {**deepcopy(gate), **update}
                write_json(self.rd / "03-coding/gate.json", bad)
                self.assertTrue(f.check_quality_gate(RUN, "03-coding", "key"))
        for update in ({"exit": 1}, {"exit": False}, {"passed": "yes"}, {"name": "fake"}, {"command": ""}):
            bad = deepcopy(gate)
            bad["results"][0].update(update)
            write_json(self.rd / "03-coding/gate.json", bad)
            self.assertTrue(f.check_quality_gate(RUN, "03-coding", "key"))

    def test_missing_and_stale_gates_are_not_legacy_success(self):
        self.assertTrue(f.check_quality_gate(RUN, "03-coding", "key"))
        self.green()
        self.assertEqual(f.check_quality_gate(RUN, "03-coding", "key"), [])
        self.assertTrue(f.check_quality_gate(RUN, "03-coding", "next-key"))

    def test_scope_tracks_both_sides_of_renames_and_literal_untracked_names(self):
        baseline = git("rev-parse", "HEAD", cwd=self.product)
        git("mv", "README.md", "renamed.md", cwd=self.product)
        unusual = "name with spaces.txt"
        (self.product / unusual).write_text("new file")
        changed = f.changed_files_since(self.product, baseline)
        self.assertIn("README.md", changed)
        self.assertIn("renamed.md", changed)
        self.assertIn(unusual, changed)
        self.assertTrue(f.check_write_scope(RUN, changed, scope=["renamed.md", unusual]))

    def test_scope_inspection_error_holds_the_gate(self):
        write_json(self.rd / "02-pre-coding/plan.json", {"write_scope": ["src/**"]})
        with patch.object(f, "changed_files_since", side_effect=ValueError("Git inspection failed")):
            gate = self.green()
        self.assertFalse(gate["passed"])
        self.assertEqual(gate["results"][-1]["name"], "write-scope")
        with self.assertRaises(ValueError):
            f.changed_files_since(self.product, "missing-commit")


if __name__ == "__main__":
    import unittest
    unittest.main()
