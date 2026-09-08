"""Cost aggregation and the tripwires (Mission Control v3, D22).

    ..\\..\\tools\\azure-runner\\.venv\\Scripts\\python test_cost.py

Stdlib only, no database: aggregate() over the grouped rows the route fetches, and
tripwire() against an explicit env — the same two ceilings pipeline.cmd_usage_check
watches, with what has already fired read from usage-check events.
"""

import os
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app as mc  # noqa: E402
import cost  # noqa: E402
from fakes import NOW, agg_row  # noqa: E402
from pipeline import est_cost_usd  # noqa: E402


class Aggregate(unittest.TestCase):
    def setUp(self):
        os.environ.pop("LANTERN_PRICE_JSON", None)

    def test_groups_by_key_sums_tokens_and_cost_across_models(self):
        rows = [agg_row("run_id", "r1", "gpt-5.6-sol", 100_000, 80_000, 5_000, n=2),
                agg_row("run_id", "r1", "gpt-5.6-luna", 50_000, 10_000, 1_000, n=1),
                agg_row("run_id", "r2", "gpt-5.6-sol", 10_000, 0, 500, n=1)]
        out = cost.aggregate(rows, "run_id")
        self.assertEqual([g["run_id"] for g in out], ["r1", "r2"])           # costliest first
        r1 = out[0]
        self.assertEqual(r1["n"], 3)
        self.assertEqual(r1["inp"], 150_000)
        self.assertEqual(r1["models"], ["gpt-5.6-luna", "gpt-5.6-sol"])
        self.assertAlmostEqual(r1["cost"], est_cost_usd(100_000, 80_000, 5_000, "gpt-5.6-sol")
                               + est_cost_usd(50_000, 10_000, 1_000, "gpt-5.6-luna"))
        self.assertEqual(r1["cached_pct"], 60)

    def test_unmetered_pile_counts_executions_but_never_dollars(self):
        rows = [agg_row("day", date(2026, 9, 8), None, 0, 0, 0, n=3, unmetered=3),
                agg_row("day", date(2026, 9, 8), "gpt-5.6-sol", 1000, 0, 10, n=1)]
        g = cost.aggregate(rows, "day")[0]
        self.assertEqual(g["n"], 4)
        self.assertEqual(g["unmetered"], 3)
        self.assertEqual(g["metered_n"], 1)
        self.assertAlmostEqual(g["cost"], est_cost_usd(1000, 0, 10, "gpt-5.6-sol"))
        self.assertEqual(g["models"], ["gpt-5.6-sol"])
        only = cost.aggregate([agg_row("day", date(2026, 9, 7), None, 0, 0, 0, n=2, unmetered=2)], "day")[0]
        self.assertEqual(only["cost"], 0.0)
        self.assertIsNone(only["cached_pct"])

    def test_empty(self):
        self.assertEqual(cost.aggregate([], "run_id"), [])


class Tripwire(unittest.TestCase):
    ENV = {"LANTERN_DAILY_SPEND_ALARM_USD": "50", "LANTERN_CREDIT_POOL_USD": "25000",
           "LANTERN_POOL_SPENT_OFFSET_USD": "100"}

    def test_under_everything(self):
        t = cost.tripwire(12.5, 300.0, self.ENV)
        self.assertEqual(t["daily_limit"], 50.0)
        self.assertAlmostEqual(t["today_pct"], 25.0)
        self.assertFalse(t["over_daily"])
        self.assertEqual(t["drawn"], 400.0)                                 # offset included
        self.assertAlmostEqual(t["pool_pct"], 1.6)
        self.assertIsNone(t["highest_crossed"])
        self.assertEqual(t["next_threshold"]["pct"], 25)
        self.assertEqual([x["crossed"] for x in t["thresholds"]], [False, False, False])

    def test_over_daily_and_pool_thresholds_with_alarm_history(self):
        events = [{"type": "spend_alarm", "data": {"est_usd": 61.0}, "at": NOW - timedelta(hours=1)},
                  {"type": "pool_alarm", "data": {"threshold": 25}, "at": NOW - timedelta(days=3)},
                  {"type": "pool_alarm", "data": {"threshold": "bogus"}, "at": NOW}]
        t = cost.tripwire(61.0, 13_000.0, self.ENV, events)
        self.assertTrue(t["over_daily"])
        self.assertEqual(t["daily_fired_at"], NOW - timedelta(hours=1))
        self.assertEqual(t["highest_crossed"], 50)
        by = {x["pct"]: x for x in t["thresholds"]}
        self.assertTrue(by[25]["crossed"] and by[50]["crossed"] and not by[75]["crossed"])
        self.assertEqual(by[25]["fired_at"], NOW - timedelta(days=3))
        self.assertIsNone(by[50]["fired_at"])                              # crossed, not yet alarmed
        self.assertEqual(t["next_threshold"]["pct"], 75)

    def test_defaults_when_env_is_empty(self):
        t = cost.tripwire(0.0, 0.0, {})
        self.assertEqual(t["daily_limit"], 50.0)
        self.assertEqual(t["pool"], 25000.0)
        self.assertEqual(t["offset"], 0.0)


class Render(unittest.TestCase):
    def test_tripwire_block_states_the_facts(self):
        t = cost.tripwire(61.0, 13_000.0, Tripwire.ENV,
                          [{"type": "pool_alarm", "data": {"threshold": 25}, "at": NOW}])
        html = cost.render_tripwires(t)
        self.assertIn("$61.00", html)
        self.assertIn("over — alarm pending", html)
        self.assertIn("50% crossed", html)
        self.assertIn("fired Sep 08", html)
        self.assertIn("fired? no", html)                                   # 50 % crossed, not alarmed
        self.assertIn("$13,100.00", html)

    def test_tables(self):
        groups = cost.aggregate([agg_row("run_id", "feat-x", "gpt-5.6-sol", 1000, 500, 10, n=2, unmetered=1)], "run_id")
        html = cost.render_by_run(groups)
        self.assertIn("href='/run/feat-x'", html)
        self.assertIn("(1 unmetered)", html)
        self.assertIn("500 · 50%", html)
        days = cost.aggregate([agg_row("day", date(2026, 9, 8), "gpt-5.6-sol", 100, 0, 1, n=1)], "day")
        self.assertIn("Sep 08", cost.render_by_day(days, 50.0))
        self.assertIn("No executions in the ledger yet", cost.render_by_run([]))
        models = cost.aggregate([agg_row("model", "gpt-5.6-sol", "gpt-5.6-sol", 100, 0, 1, n=1)], "model")
        self.assertIn("gpt-5.6-sol", cost.render_by_model(models))


if __name__ == "__main__":
    unittest.main(verbosity=2)
