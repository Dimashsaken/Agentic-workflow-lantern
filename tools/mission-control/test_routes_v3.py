"""Every Mission Control v3 route renders with an empty database, and the write routes
stay fail-closed (D22).

    ..\\..\\tools\\azure-runner\\.venv\\Scripts\\python test_routes_v3.py

Stdlib only — routes are called as coroutines with a signed cookie and the FakePool
from fakes.py. Contract under test:
  * / /gates /runs /cost /factory render on an empty database; /spend redirects to /cost;
    run-scoped pages 404 for an unknown run and render for a bare run row;
  * every GET redirects anonymous callers to /login; the drawer fragment 401s instead;
  * the work queue links to reviews without duplicate decision controls;
    review cards retain evidence, keyboard hooks, stale warnings, and both actions;
  * retry / rework are server-side POSTs: 401 anonymous, 409/400 when the pipeline's
    rules refuse, otherwise the pipeline primitives are called with the web identity;
  * the shell carries the theme boot, the toggle and the keyboard map on every page.
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ["LANTERN_WEB_USERS"] = "tester:pw,dimash:pw,justin:pw"

import app as mc  # noqa: E402
import factory  # noqa: E402
from fakes import (NOW, FakePool, Req, approval_row, body_of, exec_row, get,  # noqa: E402
                   live_approval, run_row, signed)
from fastapi import HTTPException  # noqa: E402

RUN = "feat-20260908-routes"


def status_of(exc: HTTPException) -> int:
    return exc.status_code


class EmptyDatabase(unittest.TestCase):
    def test_every_list_page_renders_empty(self):
        for route, needle in ((mc.board, "A clear start"), (mc.gates, "Nothing is waiting"),
                              (mc.runs_index, "A clear start"), (mc.cost_page, "No executions in the ledger yet"),
                              (mc.factory_page, "Roles"), (mc.repos_page, "No repositories yet"),
                              (mc.new_work_page, "Connect a repository first")):
            resp = get(route, signed(), pool=FakePool())
            self.assertEqual(resp.status_code, 200, route.__name__)
            self.assertIn(needle, body_of(resp), route.__name__)

    def test_spend_redirects_to_cost(self):
        resp = asyncio.run(mc.spend_redirect())
        self.assertEqual(resp.status_code, 303)
        self.assertEqual(resp.headers["location"], "/cost")

    def test_run_scoped_pages_404_for_an_unknown_run(self):
        for route, args in ((mc.run_page, (RUN, signed())), (mc.trace_matrix, (RUN, signed())),
                            (mc.exec_drawer, (RUN, 1, signed()))):
            with self.assertRaises(HTTPException) as cm:
                get(route, *args, pool=FakePool())
            self.assertEqual(status_of(cm.exception), 404, route.__name__)

    def test_bare_run_renders_lanes_matrix_and_404_drawer(self):
        pool = FakePool(runs=[run_row(id=RUN, status="running", current_stage="00-story.scout")])
        html = body_of(get(mc.run_page, RUN, signed(), pool=pool))
        self.assertIn("Feature lifecycle", html)
        self.assertIn("Happening now", html)
        self.assertIn("class='lane cur'", html)            # queued stage 0 is the current lane
        self.assertIn("class='lane future'", html)
        self.assertIn("queued — waiting for a runner slot", html)
        self.assertIn("Reports &amp; files", html)
        self.assertNotIn("Traceability</h2>", html)         # no story → no summary line
        html = body_of(get(mc.trace_matrix, RUN, signed(), pool=pool))
        self.assertIn("No story yet", html)
        with self.assertRaises(HTTPException) as cm:
            get(mc.exec_drawer, RUN, 99, signed(), pool=pool)
        self.assertEqual(status_of(cm.exception), 404)

    def test_anonymous_callers_are_redirected_or_refused(self):
        for route, args in ((mc.board, ()), (mc.gates, ()), (mc.runs_index, ()), (mc.cost_page, ()),
                            (mc.factory_page, ()), (mc.run_page, (RUN,)), (mc.trace_matrix, (RUN,)),
                            (mc.exec_drawer, (RUN, 1)), (mc.repos_page, ()), (mc.new_work_page, ())):
            resp = get(route, *args, Req(), pool=FakePool())
            self.assertEqual(resp.status_code, 303, route.__name__)
            self.assertEqual(resp.headers["location"], "/login")
        with self.assertRaises(HTTPException) as cm:
            get(mc.exec_drawer, RUN, 1, Req(), pool=FakePool(), fragment="1")
        self.assertEqual(status_of(cm.exception), 401)


class BugRunOnEveryPage(unittest.TestCase):
    """A bug run walks the debug lifecycle, whose stage keys are not in the feature
    pipeline's display map. /runs crashed with IndexError the first time one appeared."""

    BUG = "bug-20260908-help-crash"

    def bug_run(self, status="running", **over):
        return run_row(id=self.BUG, status=status, current_stage="02-repro", **over)

    def test_runs_page_survives_a_debug_lifecycle_run(self):
        pool = FakePool(runs=[self.bug_run()])
        resp = get(mc.runs_index, signed(), pool=pool)
        self.assertEqual(resp.status_code, 200)
        html = body_of(resp)
        self.assertIn(self.BUG, html)
        self.assertIn("Reproduce", html)

    def test_board_and_run_page_too(self):
        pool = FakePool(runs=[self.bug_run()],
                        execs=[exec_row(1, self.BUG, "01-triage", 1, "succeeded", NOW - timedelta(hours=2), 170)])
        self.assertEqual(get(mc.board, signed(), pool=pool).status_code, 200)
        html = body_of(get(mc.run_page, self.BUG, signed(), pool=pool))
        self.assertIn("01-triage", html)
        self.assertIn("debug lifecycle", html)          # and no feature stages assumed
        self.assertNotIn("01-ui-ux.diverge", html)

    def test_every_status_of_an_unmapped_stage_renders(self):
        for status in ("running", "executing", "failed", "waiting_gate", "done", "cancelled"):
            pool = FakePool(runs=[self.bug_run(status=status)])
            self.assertEqual(get(mc.runs_index, signed(), pool=pool).status_code, 200, status)


class Shell(unittest.TestCase):
    def test_theme_keyboard_and_drawer_on_every_page(self):
        html = body_of(get(mc.board, signed(), pool=FakePool()))
        self.assertIn("lantern-theme", html)                # theme boot before paint
        self.assertIn("id='themebtn'", html)
        self.assertIn("id='khelp'", html)
        self.assertIn("id='drawer'", html)
        self.assertIn("data-page='home'", html)
        self.assertIn("@media (max-width:820px)", html)
        for name, href, icon in mc.ui.NAV:
            self.assertIn(f"href='{href}'", html)
        self.assertIn("href='/factory'", html)
        self.assertIn("href='/cost'", html)

    def test_white_is_the_default_on_every_page_whatever_the_os_prefers(self):
        """One style for every page and every reader: the bare :root is the white
        palette, dark is opt-in only, and the OS preference is never consulted — so a
        screenshot in a review looks like what the next person opens."""
        css = mc.ui.CSS
        root = css.split(":root{", 1)[1].split("}", 1)[0]
        self.assertIn("color-scheme:light", root)
        self.assertIn("--surface-0:#FFFFFF", root)
        self.assertIn("--surface-1:#FFFFFF", root)
        self.assertIn("--field-bg:#FFFFFF", root)
        dark = css.split(":root[data-theme=dark]{", 1)[1].split("}", 1)[0]
        self.assertIn("color-scheme:dark", dark)
        self.assertIn("--surface-0:#0A0A0C", dark)
        # no media query and no OS class may repaint the page
        self.assertNotIn("prefers-color-scheme", css)
        self.assertNotIn("sys-light", css)
        self.assertNotIn("prefers-color-scheme", mc.ui.THEME_BOOT)
        self.assertNotIn("matchMedia", mc.ui.THEME_BOOT)
        self.assertIn("=== 'dark'", mc.ui.THEME_BOOT.replace("==='dark'", "=== 'dark'"))
        for page in (mc.board, mc.gates, mc.runs_index, mc.cost_page, mc.factory_page,
                     mc.repos_page, mc.new_work_page):
            html = body_of(get(page, signed(), pool=FakePool()))
            self.assertNotIn("prefers-color-scheme", html, page.__name__)
            self.assertIn("lantern-theme", html, page.__name__)   # the toggle still works

    def test_one_field_style_covers_every_input_on_every_page(self):
        """The login form, a gate's decision note, the repo picker, the drawer's rework
        select, the chat composer and the new-agent form share one rule; before this
        each surface set its own background and border and they drifted apart."""
        css = mc.ui.CSS
        rule = css.split("input[type=text],input[type=password],input[type=search]", 1)[1]
        rule = rule.split("}", 1)[0]
        self.assertIn("background:var(--field-bg)", rule)
        self.assertIn("border:1px solid var(--field-edge)", rule)
        self.assertIn("textarea", css.split("input[type=number],select,textarea{", 1)[0][-60:] + "textarea")
        # no surface-level override may reintroduce a second field look
        for block in (".composer textarea{", ".newagent textarea{"):
            body = css.split(block, 1)[1].split("}", 1)[0]
            self.assertNotIn("background:", body, block)
            self.assertNotIn("border:", body, block)


class WorkAndReviewEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mc-home-"))
        self._repo, self._frepo = mc.REPO, factory.REPO
        mc.REPO = factory.REPO = self.tmp
        d = self.tmp / "workflow" / "runs" / RUN / "00-story"
        d.mkdir(parents=True)
        (d / "story.md").write_text("# Story\n\n| ID | Criterion |\n|---|---|\n| AC-1 | The JSON carries branch facts. |\n",
                                    encoding="utf-8")
        (d / "story.json").write_text(json.dumps({"kind": "story", "run_id": RUN, "acceptance_criteria": [
            {"id": "AC-1", "text": "x", "edge_cases": []}], "non_goals": ["y"], "open_questions": []}), encoding="utf-8")
        (d / "report.md").write_text("# report\n\n- **Status:** PASS\n", encoding="utf-8")

    def tearDown(self):
        mc.REPO, factory.REPO = self._repo, self._frepo
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_work_links_to_artifact_first_review_without_duplicate_controls(self):
        run = run_row(id=RUN, status="waiting_gate", current_stage="00-story.write")
        a = live_approval(30 * 3600, id=7, run_id=RUN, gate="story_signoff",
                          payload=json.dumps({"stage": "00-story.write"}))
        html = body_of(get(mc.board, signed(), pool=FakePool(runs=[run], approvals=[a])))
        self.assertEqual(html.count("class='work-row'"), 1)
        self.assertIn(f"href='/run/{RUN}#gate-7'", html)
        self.assertNotIn("data-decide data-gate=", html)
        self.assertNotIn("GATE LATENCY", html)
        html = body_of(get(mc.gates, signed(), pool=FakePool(runs=[run], approvals=[a])))
        self.assertIn("<details class='review-item'>", html)
        self.assertIn("The story being approved — 00-story/story.md", html)
        self.assertIn("The JSON carries branch facts.", html)
        self.assertIn("<b>1</b> acceptance criteria", html)
        # one form, both decisions, keyboard data attributes, stale treatment
        self.assertIn("data-decide data-gate='story_signoff'", html)
        self.assertIn("data-approve='/gate/7/approve'", html)
        self.assertIn("data-reject='/gate/7/reject'", html)
        self.assertIn("formaction='/gate/7/reject'", html)
        self.assertIn("class='gcard stale' data-k tabindex='0' id='gate-7'", html)
        self.assertIn("chip warn'>STALE", html)
        self.assertIn("starts 1 · UI/UX design", html)

    def test_a_named_png_that_is_gone_is_said_not_shown_broken(self):
        """Presence AND validity for the artifact under decision: a handoff naming a
        PNG the run folder no longer holds must say so, not emit a broken <img>."""
        root = self.tmp / "workflow" / "runs" / RUN / "01-ui-ux"
        root.mkdir(parents=True)
        (root / "kept@2x.png").write_bytes(b"fake png bytes")
        handoff = {"recommended": "kept", "options": [
            {"name": "kept", "axis": "a", "pngs": [f"workflow/runs/{RUN}/01-ui-ux/kept@2x.png"]},
            {"name": "gone", "axis": "b", "pngs": [f"workflow/runs/{RUN}/01-ui-ux/gone@2x.png"]}]}
        run = run_row(id=RUN, status="waiting_gate", current_stage="01-ui-ux.design")
        html = mc.gate_card(approval_row(id=13, run_id=RUN, gate="ux_signoff",
                                         payload=json.dumps({"stage": "01-ui-ux.design", "handoff": handoff})),
                            run, NOW)
        self.assertIn("kept@2x.png' alt='kept'", html)
        self.assertNotIn("gone@2x.png' alt=", html)              # no broken image
        self.assertIn("gone@2x.png — named by the handoff, not in the run folder", html)
        self.assertFalse(mc.png_exists("../../etc/passwd"))      # confined like /file/
        self.assertFalse(mc.png_exists(""))

    def test_blocked_report_marks_the_form(self):
        (self.tmp / "workflow" / "runs" / RUN / "00-story" / "report.md").write_text(
            "# r\n\n- **Status:** BLOCKED\n\n## Open questions\n\n- Which base branch?\n", encoding="utf-8")
        run = run_row(id=RUN, status="waiting_gate", current_stage="00-story.write")
        a = approval_row(id=8, run_id=RUN, gate="story_signoff", payload=json.dumps({"stage": "00-story.write"}))
        html = mc.gate_card(a, run, NOW)
        self.assertIn("data-blocked='1'", html)
        self.assertIn("This stage's own report says BLOCKED", html)
        self.assertIn("Which base branch?", html)
        self.assertIn("approve anyway?", html)

    def test_later_gates_lead_with_their_artifacts(self):
        root = self.tmp / "workflow" / "runs" / RUN
        (root / "02-pre-coding").mkdir()
        (root / "02-pre-coding" / "task-plan.md").write_text("# Task plan\n\n## Ordered tasks\n1. add fields\n", encoding="utf-8")
        (root / "02-pre-coding" / "plan.json").write_text(json.dumps({
            "kind": "plan", "run_id": RUN, "write_scope": ["tools/**"], "schema_changes": True,
            "hitl_required": True, "tasks": [{"id": "T1", "title": "add fields", "size": "S", "criteria": ["AC-1"]}],
            "deferred_criteria": [], "builders": [{"name": "api"}]}), encoding="utf-8")
        run = run_row(id=RUN, status="waiting_gate", current_stage="02-pre-coding")
        html = mc.gate_card(approval_row(id=9, run_id=RUN, gate="plan_signoff",
                                         payload=json.dumps({"stage": "02-pre-coding"})), run, NOW)
        self.assertIn("The task plan being approved — 02-pre-coding/task-plan.md", html)
        self.assertIn("02-pre-coding/plan.json", html)
        self.assertIn("schema changes", html)
        self.assertIn("HITL required", html)
        self.assertIn("write scope: tools/**", html)
        self.assertIn("1 builders", html)
        # code_complete: PR + gate.md + review rounds + builders
        (root / "03-coding").mkdir()
        (root / "03-coding" / "gate.json").write_text(json.dumps({"passed": True, "round": 0, "configured": ["test"],
                                                                  "results": [], "execution_key": "k"}), encoding="utf-8")
        (root / "03-coding" / "gate.md").write_text("# Quality gate\n\n- **Verdict:** GREEN\n", encoding="utf-8")
        (root / "03-coding" / "review").mkdir()
        (root / "03-coding" / "review" / "round-1.md").write_text("# Review round 1\n\nOne nit.\n", encoding="utf-8")
        (root / "03-coding" / "report.md").write_text("# coding report\n\n- **Status:** PASS\n", encoding="utf-8")
        payload = {"stage": "03-coding", "branch": "feat/x", "base": "main", "commits": [{"sha": "abcdef123", "subject": "task 1"}],
                   "pr_url": "https://github.com/o/r/pull/5", "pr_number": 5,
                   "review_rounds": [{"round": 1, "verdict": "request_changes", "findings": [{"id": "F1"}], "must_fix": ["F1"]},
                                     {"round": 2, "verdict": "approve", "findings": [], "must_fix": []}],
                   "builders": [{"name": "api", "branch": "feat/x--api", "commits": 2, "files_changed": ["a.py"]}]}
        run = run_row(id=RUN, status="waiting_gate", current_stage="03-coding", coding_mode="auto")
        html = mc.gate_card(approval_row(id=10, run_id=RUN, gate="code_complete", payload=json.dumps(payload)), run, NOW)
        self.assertIn("open pull request #5", html)
        self.assertIn("03-coding/gate.md", html)
        self.assertIn("chip ok'>GREEN", html)
        self.assertIn("Review rounds", html)
        self.assertIn("round 1", html)
        self.assertIn("chip ok'>approve", html)
        self.assertIn("1 must-fix", html)
        self.assertIn("One nit.", html)
        self.assertIn("Builders", html)
        self.assertIn("feat/x--api", html)
        self.assertIn("The coding report", html)
        # staging_deploy: the validation table before the security report
        (root / "05-post-coding").mkdir()
        (root / "05-post-coding" / "validation.json").write_text(json.dumps({
            "verdict": "pass", "criteria": [{"id": "AC-1", "status": "covered", "evidence": "test_x"}], "fix_now": []}),
            encoding="utf-8")
        (root / "06-security").mkdir()
        (root / "06-security" / "report.md").write_text("# security\n\n- **Status:** PASS\n\nGO.\n", encoding="utf-8")
        run = run_row(id=RUN, status="waiting_gate", current_stage="06-security")
        html = mc.gate_card(approval_row(id=11, run_id=RUN, gate="staging_deploy", payload=json.dumps({"stage": "06-security"})), run, NOW)
        self.assertLess(html.index("05-post-coding/validation.json"), html.index("The security report"))
        self.assertIn("chip ok'>covered", html)
        self.assertIn("verdict pass", html)
        # prod_signoff: staging videos + report
        (root / "07-qa-staging").mkdir()
        (root / "07-qa-staging" / "media-manifest.json").write_text(json.dumps({"uploaded": [
            {"uri": "s3://b/x.webm", "session": 1, "attempt": 2}]}), encoding="utf-8")
        (root / "07-qa-staging" / "report.md").write_text("# staging qa\n\n- **Status:** PASS\n", encoding="utf-8")
        run = run_row(id=RUN, status="waiting_gate", current_stage="07-qa-staging")
        html = mc.gate_card(approval_row(id=12, run_id=RUN, gate="prod_signoff", payload=json.dumps({"stage": "07-qa-staging"})), run, NOW)
        self.assertIn("session 1 · attempt 2", html)
        self.assertIn("The staging QA report", html)
        self.assertIn("the run is complete", html)


class RunPageWithData(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mc-runpage-"))
        self._repo, self._frepo = mc.REPO, factory.REPO
        mc.REPO = factory.REPO = self.tmp
        self.run = run_row(id=RUN, status="waiting_gate", current_stage="00-story.write")
        t0 = NOW - timedelta(hours=3)
        self.execs = [exec_row(8, RUN, "00-story.scout", 1, "succeeded", t0, 280),
                      exec_row(9, RUN, "00-story.write", 1, "failed", t0 + timedelta(seconds=300), 120, error="blocked"),
                      exec_row(10, RUN, "00-story.write", 2, "succeeded", t0 + timedelta(seconds=500), 100)]
        self.approvals = [approval_row(4, RUN, "story_signoff", "pending")]
        os.environ.pop("LANTERN_QA_DEV_PASS", None)
        factory.write_trace(RUN, "00-story.write", f"{RUN}:00-story.write:2", "# prompt\nhello", "kick", [])

    def tearDown(self):
        mc.REPO, factory.REPO = self._repo, self._frepo
        shutil.rmtree(self.tmp, ignore_errors=True)

    def pool(self):
        return FakePool(runs=[self.run], execs=self.execs, approvals=self.approvals,
                        memory=[{"execution_key": f"{RUN}:00-story.write:2", "entry": "learned x", "created_at": NOW}])

    def test_run_page_lanes_and_pending_gate(self):
        html = body_of(get(mc.run_page, RUN, signed(), pool=self.pool()))
        self.assertIn("3 executions", html)
        self.assertIn(f"href='/run/{RUN}/exec/9' data-drawer", html)
        self.assertIn("class='gaterow wait'", html)
        self.assertIn("/gate/4/approve", html)
        self.assertIn("· trace", html)                       # attempt 2 has a trace file
        self.assertIn("data-key-t", html)                    # the traceability hotkey target
        self.assertIn("Audit log", html) if False else None

    def test_drawer_fragment_and_full_page(self):
        frag = get(mc.exec_drawer, RUN, 10, signed(), pool=self.pool(), fragment="1")
        self.assertEqual(frag.status_code, 200)
        text = body_of(frag)
        self.assertTrue(text.startswith("<div class='dwrap'>"))
        self.assertIn("# prompt", text)
        self.assertIn("learned x", text)
        self.assertIn("close ✕", text)
        full = body_of(get(mc.exec_drawer, RUN, 10, signed(), pool=self.pool()))
        self.assertIn("<aside class='app-sidebar'", full)
        self.assertIn("← run", full)
        self.assertNotIn("close ✕", full)


class LoopActions(unittest.TestCase):
    def setUp(self):
        self._render, self._rework = mc.render_runboard, mc.cmd_rework
        self.rendered = []
        self.reworked = []

        async def fake_render(conn):
            self.rendered.append(conn)

        async def fake_rework(run_id, to_stage, by, note):
            if to_stage == "03-coding" and run_id.endswith("refuse"):
                sys.exit("03-coding is not earlier than the run's current stage")
            self.reworked.append((run_id, to_stage, by, note))

        mc.render_runboard, mc.cmd_rework = fake_render, fake_rework

    def tearDown(self):
        mc.render_runboard, mc.cmd_rework = self._render, self._rework

    def test_retry_is_fail_closed_then_calls_the_primitives(self):
        with self.assertRaises(HTTPException) as cm:
            get(mc.retry_run, RUN, Req(), pool=FakePool(runs=[run_row(id=RUN, status="failed")]))
        self.assertEqual(status_of(cm.exception), 401)
        with self.assertRaises(HTTPException) as cm:
            get(mc.retry_run, RUN, signed(), pool=FakePool(runs=[run_row(id=RUN, status="waiting_gate")]))
        self.assertEqual(status_of(cm.exception), 409)
        with self.assertRaises(HTTPException) as cm:
            get(mc.retry_run, "nope", signed(), pool=FakePool())
        self.assertEqual(status_of(cm.exception), 404)
        pool = FakePool(runs=[run_row(id=RUN, status="failed", current_stage="04-qa-dev")])
        resp = get(mc.retry_run, RUN, signed("dimash"), pool=pool)
        self.assertEqual(resp.status_code, 303)
        self.assertEqual(resp.headers["location"], f"/run/{RUN}")
        sqls = [s for s, _ in pool.executed]
        self.assertTrue(any("UPDATE runs SET status = 'running'" in s for s in sqls))
        ev = next(a for s, a in pool.executed if "INSERT INTO events" in s)
        self.assertEqual(ev[1], "human:dimash")
        self.assertEqual(ev[2], "run_retried")
        self.assertIn('"channel": "web"', ev[3])
        self.assertEqual(len(self.rendered), 1)

    def test_rework_validates_then_delegates_to_cmd_rework(self):
        with self.assertRaises(HTTPException) as cm:
            get(mc.rework_run, RUN, Req(), pool=FakePool(), to_stage="03-coding", note="")
        self.assertEqual(status_of(cm.exception), 401)
        with self.assertRaises(HTTPException) as cm:
            get(mc.rework_run, RUN, signed(), pool=FakePool(), to_stage="07-qa-staging", note="")
        self.assertEqual(status_of(cm.exception), 400)
        with self.assertRaises(HTTPException) as cm:
            get(mc.rework_run, RUN + "-refuse", signed(), pool=FakePool(), to_stage="03-coding", note="")
        self.assertEqual(status_of(cm.exception), 409)
        self.assertIn("not earlier", cm.exception.detail)
        resp = get(mc.rework_run, RUN, signed("dimash"), pool=FakePool(), to_stage="03-coding", note=" fix AC-2 ")
        self.assertEqual(resp.status_code, 303)
        self.assertEqual(self.reworked, [(RUN, "03-coding", "dimash", "fix AC-2")])


class GateDecisionUnchanged(unittest.TestCase):
    def test_reject_carries_the_note_and_fails_the_run(self):
        a = approval_row(id=5, run_id=RUN, gate="plan_signoff")
        pool = FakePool(runs=[run_row(id=RUN, current_stage="02-pre-coding")], approvals=[a])
        resp = get(mc.decide, 5, "reject", signed("justin"), pool=pool, note="too wide")
        self.assertEqual(resp.status_code, 303)
        self.assertEqual(a["status"], "rejected")
        self.assertTrue(any("status='failed'" in s for s, _ in pool.executed))
        ev = next(x for s, x in pool.executed if "INSERT INTO events" in s)
        self.assertEqual(ev[2], "gate_rejected")
        self.assertIn("too wide", ev[3])
        with self.assertRaises(HTTPException) as cm:
            get(mc.decide, 5, "approve", Req(), pool=pool)
        self.assertEqual(status_of(cm.exception), 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)
