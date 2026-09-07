"""Behavior tests for feat-20260831-gate-latency (statusline-ledger).

Stdlib only — no database, no HTTP client, no pytest. Routes are exercised by
calling the coroutine endpoints directly with a fake pool and a signed cookie.

    cd tools/mission-control && python -m unittest test_gate_latency -v

Contract under test (task plan 02-pre-coding/task-plan.md):
  * snapshot() fetches per-gate median seconds + count over the last 30 days of
    decided approvals in ONE grouped query (approved+rejected, decided_at set).
  * Known gates render in GATE_META order; unknown historical gates are kept.
  * Zero-sample gates show `—` and `no decisions · n=0`, never `0h`.
  * Stale means strictly older than 24h; exact 24h is not stale; future
    timestamps clamp to 0s and are not stale.
  * Review cards keep Approve/Reject/evidence; stale ones add STALE treatment.
  * A latency-query failure hides only the ledger numbers, never the board.
"""

import asyncio
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import asyncpg  # noqa: E402

import app as mc  # noqa: E402
import ui  # noqa: E402

# app.py's load_dotenv may or may not find an .env — pin auth after import.
os.environ["LANTERN_WEB_USERS"] = "tester:pw"

NOW = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
DAY = 24 * 3600
KNOWN_GATES = list(mc.GATE_META)


def run_row(id="feat-20260901-fake", status="waiting_gate",
            current_stage="02-pre-coding", **over) -> dict:
    row = {
        "id": id, "status": status, "current_stage": current_stage,
        "created_by": "tester", "created_at": NOW - timedelta(days=2),
        "updated_at": NOW - timedelta(hours=1), "completed_at": None,
        "pipeline_version": 2, "brief": "workflow/briefs/fake.md",
        "product_repo": None, "product_branch": None,
    }
    row.update(over)
    return row


def approval_row(id=7, run_id="feat-20260901-fake", gate="plan_signoff",
                 age_seconds=20 * 3600, **over) -> dict:
    row = {
        "id": id, "run_id": run_id, "gate": gate, "status": "pending",
        "payload": None, "requested_at": NOW - timedelta(seconds=age_seconds),
        "decided_at": None, "decided_by": None, "decision_note": None,
    }
    row.update(over)
    return row


def live_approval(age_seconds, **over) -> dict:
    """An approval aged against real wall-clock time, for route-level tests
    (routes compute `now` themselves). The 30s margin keeps ago() on the
    whole-unit boundary ('20h', '4d') for the duration of a test run."""
    return approval_row(
        requested_at=datetime.now(timezone.utc)
        - timedelta(seconds=age_seconds + 30), **over)


def latency_row(gate, med, n) -> dict:
    return {"gate": gate, "med": med, "n": n}


class FakePool:
    """Answers the app's queries from canned rows; records every query."""

    def __init__(self, runs=(), pend=(), latency=(), fail_latency=False,
                 execs=(), arts=(), events=()):
        self.runs, self.pend, self.latency = list(runs), list(pend), list(latency)
        self.fail_latency = fail_latency
        self.execs, self.arts, self.events = list(execs), list(arts), list(events)
        self.queries: list[str] = []

    def _norm(self, sql: str) -> str:
        return " ".join(sql.lower().split())

    async def fetch(self, sql, *args):
        self.queries.append(sql)
        s = self._norm(sql)
        if "percentile_cont" in s:
            if self.fail_latency:
                raise asyncpg.PostgresError("aggregate blew up")
            return self.latency
        if "from runs" in s:
            if args:                                   # /gates: id = ANY($1)
                return [r for r in self.runs if r["id"] in args[0]]
            return self.runs
        if "from approvals" in s and "status='pending'" in s:
            if args:                                   # /run/{id}
                return [a for a in self.pend if a["run_id"] == args[0]]
            return self.pend
        if "from approvals" in s:                      # /gates decided history
            return []
        if "from runners" in s:
            return []
        if "distinct on" in s:
            return []
        if "from stage_executions" in s:
            if "where run_id" in s:
                return self.execs
            return []                                  # agg / today / feed
        if "from artifacts" in s:
            return self.arts
        if "from events" in s:
            return self.events
        raise AssertionError(f"unexpected fetch: {sql}")

    async def fetchrow(self, sql, *args):
        self.queries.append(sql)
        s = self._norm(sql)
        if "percentile_cont" in s:
            raise AssertionError(
                "gate latency must be one grouped fetch(), not a scalar fetchrow()")
        if "from runs" in s:
            return next((r for r in self.runs if r["id"] == args[0]), None)
        raise AssertionError(f"unexpected fetchrow: {sql}")


class Req:
    def __init__(self, cookies=None):
        self.cookies = cookies or {}


def signed() -> Req:
    return Req({mc.SESSION_COOKIE: mc.make_session("tester")})


def body_of(resp) -> str:
    return resp.body.decode("utf-8")


def get(route, *args, pool=None):
    mc.pool = pool
    try:
        return asyncio.run(route(*args))
    finally:
        mc.pool = None


# ── the grouped query contract ───────────────────────────────────────────────

class TestLatencySQL(unittest.TestCase):
    def test_one_grouped_query_constant(self):
        sql = " ".join(mc.LATENCY_SQL.lower().split())
        # median intent: percentile_cont interpolates even-sized cohorts and
        # picks the middle row of odd ones — not percentile_disc, not avg.
        self.assertIn("percentile_cont(0.5)", sql)
        self.assertIn("extract(epoch from decided_at - requested_at)", sql)
        self.assertIn("group by gate", sql)
        # approved AND rejected count as decisions; pending/expired never do.
        self.assertIn("status in ('approved','rejected')", sql)
        self.assertIn("decided_at is not null", sql)
        # the 30-day window is on the decision time, not the request time.
        self.assertIn("decided_at >= now() - interval '30 days'", sql)
        self.assertNotIn("requested_at >=", sql)


class TestGateLatencyRows(unittest.TestCase):
    def test_known_gates_in_stable_order_regardless_of_input_order(self):
        rows = [latency_row("prod_signoff", 100.0, 1),
                latency_row("ux_signoff", 200.0, 2)]
        out = mc.gate_latency_rows(rows)
        self.assertEqual([r["gate"] for r in out], KNOWN_GATES)

    def test_missing_gates_fill_with_zero_samples(self):
        out = mc.gate_latency_rows([latency_row("ux_signoff", 72000.0, 2)])
        by = {r["gate"]: r for r in out}
        self.assertEqual(by["ux_signoff"]["n"], 2)
        for g in KNOWN_GATES:
            if g != "ux_signoff":
                self.assertEqual(by[g]["n"], 0)
                self.assertIsNone(by[g]["med"])

    def test_unknown_gate_is_kept_after_known_ones(self):
        out = mc.gate_latency_rows([latency_row("legacy_gate", 50.0, 3)])
        self.assertEqual(out[-1]["gate"], "legacy_gate")
        self.assertEqual(out[-1]["n"], 3)
        self.assertEqual([r["gate"] for r in out[:-1]], KNOWN_GATES)

    def test_empty_input_yields_all_known_gates_empty(self):
        out = mc.gate_latency_rows([])
        self.assertEqual(len(out), len(KNOWN_GATES))
        self.assertTrue(all(r["n"] == 0 and r["med"] is None for r in out))


class TestLedgerMetrics(unittest.TestCase):
    def one(self, gate, med, n) -> dict:
        return mc.ledger_metrics([latency_row(gate, med, n)])[0]

    def test_zero_samples_show_dash_never_zero_hours(self):
        m = self.one("code_complete", None, 0)
        self.assertEqual(m["value"], "—")
        self.assertEqual(m["kind"], "dim")
        self.assertIn("no decisions · n=0", m["sub"])
        self.assertNotIn("0h", m["value"])

    def test_median_under_threshold_is_plain(self):
        m = self.one("ux_signoff", 20 * 3600.0, 2)
        self.assertEqual(m["value"], "20h")
        self.assertEqual(m["kind"], "")
        self.assertIn("UX sign-off", m["sub"])
        self.assertIn("n=2", m["sub"])

    def test_exact_24h_median_is_not_flagged(self):
        m = self.one("ux_signoff", float(DAY), 4)
        self.assertEqual(m["kind"], "")
        self.assertEqual(m["value"], "24h")

    def test_median_over_24h_gets_warning_kind(self):
        m = self.one("plan_signoff", 4 * DAY + 0.0, 2)
        self.assertEqual(m["value"], "4d")
        self.assertEqual(m["kind"], "warn")

    def test_unknown_gate_label_falls_back_to_raw_name(self):
        m = self.one("legacy_gate", 3600.0, 1)
        self.assertIn("legacy_gate", m["sub"])


class TestStale(unittest.TestCase):
    def test_exact_24h_is_not_stale(self):
        self.assertFalse(mc.is_stale(DAY))

    def test_just_over_24h_is_stale(self):
        self.assertTrue(mc.is_stale(DAY + 1))

    def test_zero_and_future_clamp_are_not_stale(self):
        self.assertFalse(mc.is_stale(0))
        self.assertFalse(mc.is_stale(-300))     # future requested_at

    def test_ago_clamps_future_to_zero(self):
        self.assertEqual(ui.ago(-300), "0s")

    def test_ago_humane_units(self):
        self.assertEqual(ui.ago(20 * 3600), "20h")
        self.assertEqual(ui.ago(4 * DAY), "4d")


# ── board card composition ───────────────────────────────────────────────────

def snap_for(runs, pend, latency=(), **kw) -> dict:
    """Assemble a snapshot dict through the real snapshot() with a fake pool."""
    p = FakePool(runs=runs, pend=pend, latency=list(latency), **kw)
    return asyncio.run(mc.snapshot(p)), p


class TestReviewCards(unittest.TestCase):
    def card(self, age_seconds):
        run = run_row()
        a = approval_row(age_seconds=age_seconds)
        snap, _ = snap_for([run], [a])
        col, html = mc.build_card(run, snap, NOW)
        self.assertEqual(col, "review")
        return html

    def test_fresh_card_has_age_and_controls_but_no_stale(self):
        html = self.card(20 * 3600)
        self.assertIn("20h", html)
        self.assertNotIn("STALE", html)
        self.assertNotIn("stale", html)
        self.assertIn("/gate/7/approve", html)
        self.assertIn("/gate/7/reject", html)
        self.assertIn("href='/gates'", html)           # evidence link

    def test_exact_24h_card_is_not_stale(self):
        self.assertNotIn("STALE", self.card(DAY))

    def test_over_24h_card_shows_stale_treatment_and_keeps_controls(self):
        html = self.card(4 * DAY)
        self.assertIn("STALE", html)
        self.assertIn("kcard hot stale", html)
        self.assertIn("4d", html)
        self.assertIn("/gate/7/approve", html)
        self.assertIn("/gate/7/reject", html)
        self.assertIn("href='/gates'", html)

    def test_just_over_24h_is_stale(self):
        self.assertIn("STALE", self.card(DAY + 60))

    def test_future_requested_at_renders_0s_not_stale(self):
        html = self.card(-600)
        self.assertIn("0s", html)
        self.assertNotIn("STALE", html)


class TestGateCardPreserved(unittest.TestCase):
    def test_gate_card_still_shows_pending_age_and_decision_forms(self):
        a = approval_row(age_seconds=20 * 3600)
        html = mc.gate_card(a, run_row(), NOW)
        self.assertIn("waiting 20h", html)
        self.assertIn("/gate/7/approve", html)
        self.assertIn("/gate/7/reject", html)


# ── ledger rendering ─────────────────────────────────────────────────────────

class TestLedgerRender(unittest.TestCase):
    def test_header_wording_and_all_known_gates(self):
        html = ui.gate_ledger(mc.ledger_metrics(mc.gate_latency_rows(
            [latency_row("ux_signoff", 72000.0, 2),
             latency_row("plan_signoff", 4 * DAY + 0.0, 2)])))
        self.assertIn("GATE LATENCY · LAST 30 DAYS", html)
        self.assertIn("Median time to decision · UTC", html)
        self.assertIn("20h", html)
        self.assertIn("4d", html)
        for label in ("UX sign-off", "plan sign-off", "code-complete",
                      "staging deploy", "prod sign-off"):
            self.assertIn(label, html)

    def test_zero_state_copy(self):
        html = ui.gate_ledger(mc.ledger_metrics(mc.gate_latency_rows([])))
        self.assertIn("—", html)
        self.assertIn("no decisions · n=0", html)
        self.assertNotIn("0h", html)

    def test_error_state_copy(self):
        html = ui.gate_ledger(None)
        self.assertIn("Gate latency unavailable — refresh.", html)


# ── routes ───────────────────────────────────────────────────────────────────

class TestRoutes(unittest.TestCase):
    def test_board_renders_ledger_between_statusline_and_columns(self):
        pool = FakePool(
            runs=[run_row()], pend=[live_approval(4 * DAY)],
            latency=[latency_row("ux_signoff", 72000.0, 2),
                     latency_row("plan_signoff", 4 * DAY + 0.0, 2)])
        html = body_of(get(mc.board, signed(), pool=pool))
        self.assertIn("GATE LATENCY · LAST 30 DAYS", html)
        self.assertIn("STALE", html)
        for col in ("Queued", "Running", "Blocked", "Review", "Done"):
            self.assertIn(col, html)
        self.assertIn("/gate/7/approve", html)
        i_status = html.index("statusline")
        i_ledger = html.index("GATE LATENCY")
        i_board = html.index("class='kb'")
        self.assertLess(i_status, i_ledger)
        self.assertLess(i_ledger, i_board)

    def test_board_survives_latency_query_failure(self):
        pool = FakePool(runs=[run_row()], pend=[live_approval(4 * DAY)],
                        fail_latency=True)
        html = body_of(get(mc.board, signed(), pool=pool))
        self.assertIn("Gate latency unavailable — refresh.", html)
        self.assertIn("/gate/7/approve", html)          # cards still decidable
        self.assertIn("Review", html)

    def test_board_with_zero_decided_and_zero_pending(self):
        html = body_of(get(mc.board, signed(), pool=FakePool()))
        self.assertIn("no decisions · n=0", html)
        self.assertNotIn("0h", html)
        self.assertIn("Nothing needs you", html)

    def test_board_query_count_is_constant(self):
        small = FakePool(runs=[run_row()], pend=[])
        get(mc.board, signed(), pool=small)
        runs = [run_row(id=f"feat-20260901-r{i}") for i in range(5)]
        pend = [approval_row(id=i, run_id=r["id"],
                             gate=KNOWN_GATES[i % len(KNOWN_GATES)])
                for i, r in enumerate(runs)]
        big = FakePool(runs=runs, pend=pend,
                       latency=[latency_row(g, 3600.0, 1) for g in KNOWN_GATES])
        get(mc.board, signed(), pool=big)
        self.assertEqual(len(small.queries), len(big.queries))

    def test_board_redirects_anonymous(self):
        resp = get(mc.board, Req(), pool=FakePool())
        self.assertEqual(resp.status_code, 303)
        self.assertEqual(resp.headers["location"], "/login")

    def test_runs_page_unaffected_by_snapshot_reshape(self):
        pool = FakePool(runs=[run_row()], pend=[live_approval(4 * DAY)])
        resp = get(mc.runs_index, signed(), pool=pool)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("feat-20260901-fake", body_of(resp))

    def test_runs_redirects_anonymous(self):
        resp = get(mc.runs_index, Req(), pool=FakePool())
        self.assertEqual(resp.status_code, 303)

    def test_gates_page_shows_pending_age(self):
        pool = FakePool(runs=[run_row()], pend=[live_approval(20 * 3600)])
        html = body_of(get(mc.gates, signed(), pool=pool))
        self.assertIn("waiting 20h", html)
        self.assertIn("/gate/7/approve", html)

    def test_gates_redirects_anonymous(self):
        resp = get(mc.gates, Req(), pool=FakePool())
        self.assertEqual(resp.status_code, 303)
        self.assertEqual(resp.headers["location"], "/login")

    def test_run_detail_still_shows_pending_age_no_median_context(self):
        run = run_row()
        pool = FakePool(runs=[run], pend=[live_approval(20 * 3600)])
        html = body_of(get(mc.run_page, run["id"], signed(), pool=pool))
        self.assertIn("waiting 20h", html)
        self.assertIn("/gate/7/approve", html)
        # the rejected attempt-1 run-detail median/context block must not exist
        self.assertNotIn("GATE LATENCY", html)

    def test_run_detail_redirects_anonymous(self):
        resp = get(mc.run_page, "feat-20260901-fake", Req(), pool=FakePool())
        self.assertEqual(resp.status_code, 303)


if __name__ == "__main__":
    unittest.main()
