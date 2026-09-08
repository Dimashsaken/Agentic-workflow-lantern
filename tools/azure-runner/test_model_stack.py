"""Model stack (D16): tier routing, deployment fallback chain, reasoning effort.

    .venv/Scripts/python test_model_stack.py      (no network, no database)

Why this exists: routing policy is one function (`tier_for`) and one env contract; a
silent regression here would quietly run the planner on the cheap deployment or the
QA volume work at maximum effort. The fallback chain is what lets a resource with a
single deployment still run every stage — that must stay true.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import orchestrator as o  # noqa: E402  (loads .env at import; tests isolate os.environ)


def env(**values: str):
    return mock.patch.dict(os.environ, values, clear=True)


class TierRouting(unittest.TestCase):
    def test_judgement_roles_are_reasoning(self):
        for role in ("ui-ux", "pre-coding", "post-coding", "security", "debug"):
            self.assertEqual(o.tier_for(role), "reasoning", role)
        self.assertEqual(o.tier_for("ui-ux", "01-ui-ux.design"), "reasoning")

    def test_coding_role_is_coding_tier(self):
        self.assertEqual(o.tier_for("coding", "03-coding"), "coding")
        self.assertEqual(o.tier_for("coding"), "coding")

    def test_volume_work_is_fast(self):
        self.assertEqual(o.tier_for("qa-dev", "04-qa-dev"), "fast")
        self.assertEqual(o.tier_for("qa-staging", "07-qa-staging"), "fast")
        self.assertEqual(o.tier_for("ui-ux", "01-ui-ux.diverge"), "fast")

    def test_every_pipeline_role_has_a_tier(self):
        for stage, role in o.ROLE_FOR_STAGE.items():
            self.assertIn(o.tier_for(role, stage), o.MODEL_TIERS, (stage, role))


class DeploymentResolution(unittest.TestCase):
    def setUp(self):
        o._ROUTING_NOTES.clear()

    def test_full_stack_routes_each_tier_to_its_own_deployment(self):
        with env(LANTERN_MODEL_REASONING="r", LANTERN_MODEL_CODING="c", LANTERN_MODEL_FAST="f"):
            self.assertEqual(o.model_for("pre-coding", "02-pre-coding"), "r")
            self.assertEqual(o.model_for("coding", "03-coding"), "c")
            self.assertEqual(o.model_for("qa-dev", "04-qa-dev"), "f")
            self.assertEqual(o.model_for("ui-ux", "01-ui-ux.diverge"), "f")

    def test_single_deployment_still_routes_everything(self):
        with env(LANTERN_MODEL_REASONING="sol"):
            self.assertEqual(o.model_for("coding", "03-coding"), "sol")
            self.assertEqual(o.model_for("qa-dev", "04-qa-dev"), "sol")
            self.assertEqual(o.model_for("security", "06-security"), "sol")

    def test_coding_falls_back_to_fast_before_reasoning(self):
        with env(LANTERN_MODEL_REASONING="r", LANTERN_MODEL_FAST="f"):
            self.assertEqual(o.model_for("coding", "03-coding"), "f")

    def test_blank_value_counts_as_unset(self):
        with env(LANTERN_MODEL_REASONING="r", LANTERN_MODEL_CODING="  ", LANTERN_MODEL_FAST=""):
            self.assertEqual(o.model_for("coding", "03-coding"), "r")

    def test_reasoning_deployment_is_mandatory(self):
        with env():
            with self.assertRaises(SystemExit):
                o.model_for("pre-coding", "02-pre-coding")

    def test_unknown_tier_rejected(self):
        with env(LANTERN_MODEL_REASONING="r"):
            with self.assertRaises(ValueError):
                o.deployment_for_tier("cheap")


class ReasoningEffort(unittest.TestCase):
    def setUp(self):
        o._ROUTING_NOTES.clear()

    def test_token_max_defaults(self):
        with env():
            self.assertEqual(o.effort_for("reasoning"), "high")
            self.assertEqual(o.effort_for("coding"), "high")
            self.assertEqual(o.effort_for("fast"), "medium")

    def test_override_off_and_bogus(self):
        with env(LANTERN_EFFORT_FAST="LOW", LANTERN_EFFORT_CODING="default",
                 LANTERN_EFFORT_REASONING="bogus"):
            self.assertEqual(o.effort_for("fast"), "low")
            self.assertIsNone(o.effort_for("coding"))
            self.assertEqual(o.effort_for("reasoning"), "high")   # bogus → default, noted once

    def test_model_settings_carry_the_effort(self):
        with env(LANTERN_MODEL_REASONING="r"):
            self.assertEqual(o.model_settings_for("pre-coding").reasoning.effort, "high")
            self.assertEqual(o.model_settings_for("qa-dev", "04-qa-dev").reasoning.effort, "medium")
        with env(LANTERN_EFFORT_FAST="off"):
            self.assertIsNone(o.model_settings_for("qa-dev", "04-qa-dev").reasoning)

    def test_chat_override_only_applies_to_chat(self):
        with env(LANTERN_EFFORT_CHAT="low"):
            self.assertEqual(o.model_settings_for("security", purpose="chat").reasoning.effort, "low")
            self.assertEqual(o.model_settings_for("security").reasoning.effort, "high")
        with env(LANTERN_EFFORT_CHAT="off"):
            self.assertIsNone(o.model_settings_for("security", purpose="chat").reasoning)


if __name__ == "__main__":
    unittest.main(verbosity=2)
