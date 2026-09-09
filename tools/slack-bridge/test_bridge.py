"""Slack front door — allowlists, ack timing, and who the write is recorded as (D21).

    ../azure-runner/.venv/Scripts/python test_bridge.py     (no Slack, no database)

Every handler is a plain function over an injected client and a `Deps` bundle, so the
whole surface is testable without a socket: a fake Slack client records what it was
asked to post, and a fake pipeline records what it was asked to do. The three properties
that matter, each with its own check:

  * a non-approver's click changes NOTHING, and says so to them alone;
  * `ack()` happens before the pipeline call — Slack gives handlers 3 seconds and
    `cmd_decide` (git, Postgres, a runboard render) does not fit in them;
  * an approval reaches `pipeline.cmd_decide` with `by="slack:<user id>"`, which is what
    makes the audit log say a person decided this.

`slack_bolt` is never imported — `build_app()` is the only place that touches it.
"""

import json
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "azure-runner"))

import bridge                                        # noqa: E402

APPROVER = "U_APPROVER"
OPERATOR = "U_OPERATOR"
STRANGER = "U_STRANGER"
CHANNEL = "C_RUNS"
RUN = "feat-20260908-status-facts"


class FakeClient:
    """Records Slack calls; `ts` values are deterministic so assertions can name them."""

    def __init__(self):
        self.posts, self.ephemeral, self.updates = [], [], []
        self._n = 0

    def chat_postMessage(self, **kw):
        self._n += 1
        kw["ts"] = f"ts{self._n}"
        self.posts.append(kw)
        return {"ok": True, "ts": kw["ts"]}

    def chat_postEphemeral(self, **kw):
        self.ephemeral.append(kw)
        return {"ok": True}

    def chat_update(self, **kw):
        self.updates.append(kw)
        return {"ok": True}


class FakePipeline:
    """What the bridge is allowed to do to the factory, recorded rather than done."""

    def __init__(self, ok=True, error=""):
        self.calls, self.events, self.threads = [], [], []
        self.ok, self.error = ok, error
        self.slow_s = 0.0

    def _res(self, run_id=None):
        if self.slow_s:
            time.sleep(self.slow_s)
        r = {"ok": self.ok, "output": "done"} if self.ok else {"ok": False, "error": self.error}
        if run_id:
            r["run_id"] = run_id
        return r

    def decide(self, run_id, gate, by, note, approved):
        self.calls.append(("decide", run_id, gate, by, note, approved))
        return self._res()

    def start_run(self, idea, brief_path, by, repo, base_branch, coding_mode):
        self.calls.append(("start_run", idea, brief_path, by, repo, base_branch, coding_mode))
        r = self._res(RUN)
        r["brief_path"] = "workflow/briefs/composed.md"
        return r

    def rework(self, run_id, to_stage, by, note):
        self.calls.append(("rework", run_id, to_stage, by, note))
        return self._res()

    def retry(self, run_id, by):
        self.calls.append(("retry", run_id, by))
        return self._res()

    def log_event(self, run_id, actor, type_, data):
        self.events.append((run_id, actor, type_, data))

    def store_thread(self, run_id, channel, thread_ts):
        self.threads.append((run_id, channel, thread_ts))


def deps(pipe=None, **over):
    pipe = pipe or FakePipeline()
    kw = {"bot_token": "x", "app_token": "y", "approvers": frozenset({APPROVER}),
          "operators": frozenset({OPERATOR, APPROVER}), "channels": frozenset({CHANNEL}),
          "default_repo": "/srv/app", "public_url": "http://box:8080"}
    kw.update(over)
    cfg = bridge.Config(**kw)
    d = bridge.Deps(config=cfg, decide=pipe.decide, start_run=pipe.start_run,
                    rework=pipe.rework, retry=pipe.retry, log_event=pipe.log_event,
                    store_thread=pipe.store_thread)
    return d, pipe


def gate_row(gate="story_signoff", **over):
    row = {"approval_id": 7, "run_id": RUN, "gate": gate, "requested_at": None,
           "payload": {"run_folder": f"workflow/runs/{RUN}/"},
           "slack_channel": CHANNEL, "slack_thread_ts": "ts_run", "created_by": "dimash",
           "notified": False}
    row.update(over)
    return row


def click(user, gate="story_signoff", decision="approve", ts="ts_gate"):
    return {"user": {"id": user}, "channel": {"id": CHANNEL},
            "message": {"ts": ts, "thread_ts": "ts_run"},
            "actions": [{"action_id": bridge.GATE_ACTION_ID,
                         "value": bridge.gate_value(RUN, gate, decision, 7)}]}


class Allowlists(unittest.TestCase):
    """Slack workspace membership is not an authorization boundary."""

    def test_a_non_approver_click_changes_nothing(self):
        d, pipe = deps()
        c = FakeClient()
        res = bridge.handle_gate_action(click(STRANGER), lambda: None, c, d)
        self.assertFalse(res["ok"])
        self.assertEqual(pipe.calls, [], "a stranger's click reached the pipeline")
        self.assertEqual(len(c.ephemeral), 1)
        self.assertIn("not an approver", c.ephemeral[0]["text"])
        self.assertEqual(c.updates, [], "the message was updated as if something happened")

    def test_a_refused_click_is_logged_with_the_slack_identity(self):
        d, pipe = deps()
        bridge.handle_gate_action(click(STRANGER), lambda: None, FakeClient(), d)
        run_id, actor, type_, data = pipe.events[-1]
        self.assertEqual(actor, f"human:slack:{STRANGER}")
        self.assertEqual(type_, "gate_decision_refused")
        self.assertEqual(data["why"], "not an approver")

    def test_an_operator_who_is_not_an_approver_cannot_decide_a_gate(self):
        d, pipe = deps()
        bridge.handle_gate_action(click(OPERATOR), lambda: None, FakeClient(), d)
        self.assertEqual(pipe.calls, [], "operator rights leaked into gate authority")

    def test_an_empty_approver_list_means_nobody(self):
        d, pipe = deps(approvers=frozenset())
        bridge.handle_gate_action(click(APPROVER), lambda: None, FakeClient(), d)
        self.assertEqual(pipe.calls, [], "an unset allowlist defaulted open")

    def test_a_non_operator_cannot_start_a_run(self):
        d, pipe = deps()
        c = FakeClient()
        res = bridge.handle_mention(
            {"user": STRANGER, "channel": CHANNEL, "ts": "ts1",
             "text": "<@U_BOT> build me a bulk export"}, c, d)
        self.assertFalse(res["ok"])
        self.assertEqual(pipe.calls, [])
        self.assertIn("not an operator", c.posts[0]["text"])

    def test_the_app_ignores_channels_it_was_not_pointed_at(self):
        d, pipe = deps()
        c = FakeClient()
        res = bridge.handle_mention(
            {"user": OPERATOR, "channel": "C_RANDOM", "ts": "t", "text": "<@U_BOT> hi"}, c, d)
        self.assertFalse(res["ok"])
        self.assertEqual(c.posts, [])
        self.assertEqual(pipe.calls, [])

    def test_slash_commands_check_the_operator_list(self):
        for handler, text in ((bridge.handle_rework, f"{RUN} 03-coding because QA failed"),
                              (bridge.handle_retry, RUN)):
            d, pipe = deps()
            said = []
            handler({"user_id": STRANGER, "text": text}, lambda: None, said.append, d)
            self.assertEqual(pipe.calls, [])
            self.assertIn("not an operator", said[0])


class AckTiming(unittest.TestCase):
    """Slack drops a handler that has not acked in 3 s; the pipeline call is slower."""

    def test_ack_happens_before_the_pipeline_is_touched(self):
        order = []
        d, pipe = deps()
        pipe.decide = lambda *a: (order.append("decide"), {"ok": True, "output": ""})[1]
        d.decide = pipe.decide
        bridge.handle_gate_action(click(APPROVER), lambda: order.append("ack"), FakeClient(), d)
        self.assertEqual(order[0], "ack")
        self.assertIn("decide", order)

    def test_a_slow_pipeline_call_does_not_delay_the_ack(self):
        d, pipe = deps()
        pipe.slow_s = 0.25                       # stands in for git + Postgres + render
        marks = {}
        t0 = time.monotonic()
        bridge.handle_gate_action(click(APPROVER),
                                  lambda: marks.setdefault("ack_at", time.monotonic() - t0),
                                  FakeClient(), d)
        total = time.monotonic() - t0
        self.assertLess(marks["ack_at"], 0.05)
        self.assertGreaterEqual(total, 0.25)

    def test_slash_commands_ack_first_too(self):
        for handler, text in ((bridge.handle_rework, f"{RUN} 03-coding note"),
                              (bridge.handle_retry, RUN)):
            order = []
            d, pipe = deps()
            pipe.slow_s = 0.05
            handler({"user_id": OPERATOR, "text": text},
                    lambda: order.append("ack"), order.append, d)
            self.assertEqual(order[0], "ack")


class ApprovalsCarryTheHuman(unittest.TestCase):

    def test_an_approval_reaches_the_pipeline_as_slack_user(self):
        d, pipe = deps()
        c = FakeClient()
        res = bridge.handle_gate_action(click(APPROVER), lambda: None, c, d)
        self.assertTrue(res["ok"])
        self.assertEqual(pipe.calls, [("decide", RUN, "story_signoff",
                                       f"slack:{APPROVER}", "decided from Slack", True)])
        self.assertEqual(res["by"], f"slack:{APPROVER}")

    def test_a_rejection_is_carried_as_a_rejection(self):
        d, pipe = deps()
        bridge.handle_gate_action(click(APPROVER, decision="reject"), lambda: None,
                                  FakeClient(), d)
        self.assertFalse(pipe.calls[0][5])

    def test_the_message_is_rewritten_so_the_buttons_cannot_be_clicked_twice(self):
        d, _ = deps()
        c = FakeClient()
        bridge.handle_gate_action(click(APPROVER), lambda: None, c, d)
        self.assertEqual(len(c.updates), 1)
        blocks = c.updates[0]["blocks"]
        self.assertNotIn("actions", [b["type"] for b in blocks])
        self.assertIn("approved", json.dumps(blocks))

    def test_a_pipeline_refusal_is_said_in_the_thread_not_swallowed(self):
        d, pipe = deps(); pipe.ok, pipe.error = False, "no pending approval"
        d.decide = pipe.decide
        c = FakeClient()
        res = bridge.handle_gate_action(click(APPROVER), lambda: None, c, d)
        self.assertFalse(res["ok"])
        self.assertIn("no pending approval", c.posts[-1]["text"])
        self.assertIn("not applied", json.dumps(c.updates[0]["blocks"]))

    def test_the_two_highest_stakes_gates_are_not_decidable_from_slack(self):
        d, pipe = deps()
        for gate in ("staging_deploy", "prod_signoff"):
            c = FakeClient()
            res = bridge.handle_gate_action(click(APPROVER, gate=gate), lambda: None, c, d)
            self.assertFalse(res["ok"])
            self.assertEqual(pipe.calls, [])
            self.assertIn("Mission Control", c.ephemeral[0]["text"])


class GateCards(unittest.TestCase):

    def test_a_slack_carried_gate_gets_buttons_and_the_others_do_not(self):
        cfg = deps()[0].config
        with_buttons = bridge.gate_blocks(gate_row("code_complete"), cfg)
        self.assertIn("actions", [b["type"] for b in with_buttons])
        without = bridge.gate_blocks(gate_row("prod_signoff"), cfg)
        self.assertNotIn("actions", [b["type"] for b in without])
        self.assertIn("Mission Control", json.dumps(without))

    def test_the_card_carries_what_is_being_decided(self):
        cfg = deps()[0].config
        blocks = bridge.gate_blocks(
            gate_row("code_complete", payload={"pr_url": "https://github.com/o/r/pull/3",
                                               "branch": "feat/x"}), cfg)
        text = json.dumps(blocks)
        self.assertIn("pull/3", text)
        self.assertIn("feat/x", text)
        self.assertIn(f"http://box:8080/run/{RUN}", text)

    def test_button_values_round_trip(self):
        v = json.loads(bridge.gate_value(RUN, "story_signoff", "approve", 7))
        self.assertEqual(v, {"run_id": RUN, "gate": "story_signoff",
                             "decision": "approve", "approval_id": 7})

    def test_a_pending_gate_posts_once_into_the_runs_thread(self):
        d, pipe = deps()
        d.pending_gates = lambda: [gate_row()]
        c = FakeClient()
        self.assertEqual(bridge.notify_pending_gates(c, d), 1)
        self.assertEqual(c.posts[0]["channel"], CHANNEL)
        self.assertEqual(c.posts[0]["thread_ts"], "ts_run")
        self.assertEqual(pipe.events[-1][2], "slack_gate_posted")
        # already-notified rows are skipped, so a poll loop does not spam the thread
        d.pending_gates = lambda: [gate_row(notified=True)]
        self.assertEqual(bridge.notify_pending_gates(FakeClient(), d), 0)

    def test_a_run_with_no_thread_gets_one_before_the_gate_card(self):
        d, pipe = deps()
        d.pending_gates = lambda: [gate_row(slack_channel=None, slack_thread_ts=None)]
        c = FakeClient()
        bridge.notify_pending_gates(c, d)
        self.assertEqual(len(c.posts), 2)                    # the head, then the card
        self.assertEqual(pipe.threads, [(RUN, CHANNEL, "ts1")])
        self.assertEqual(c.posts[1]["thread_ts"], "ts1")


class Mentions(unittest.TestCase):

    def test_an_idea_opens_a_run_and_a_thread(self):
        d, pipe = deps()
        c = FakeClient()
        res = bridge.handle_mention(
            {"user": OPERATOR, "channel": CHANNEL, "ts": "ts_thread",
             "text": "<@U_BOT> let editors bulk-export candidates mode=auto"}, c, d)
        self.assertTrue(res["ok"])
        verb, idea, brief, by, repo, base, mode = pipe.calls[0]
        self.assertEqual(verb, "start_run")
        self.assertEqual(idea, "let editors bulk-export candidates")
        self.assertEqual(by, f"slack:{OPERATOR}")
        self.assertEqual((repo, base, mode), ("/srv/app", "main", "auto"))
        self.assertEqual(pipe.threads, [(RUN, CHANNEL, "ts_thread")])
        self.assertEqual(c.posts[0]["thread_ts"], "ts_thread")

    def test_options_are_parsed_out_of_the_idea_text(self):
        p = bridge.parse_mention("build a thing repo=/srv/other mode=auto branch=develop")
        self.assertEqual(p["verb"], "idea")
        self.assertEqual(p["rest"], "build a thing")
        self.assertEqual((p["repo"], p["mode"], p["branch"]), ("/srv/other", "auto", "develop"))

    def test_run_takes_an_existing_brief(self):
        d, pipe = deps()
        bridge.handle_mention(
            {"user": OPERATOR, "channel": CHANNEL, "ts": "t",
             "text": "<@U_BOT> run workflow/briefs/status-facts.md"}, FakeClient(), d)
        self.assertEqual(pipe.calls[0][1], "")                       # no idea
        self.assertEqual(pipe.calls[0][2], "workflow/briefs/status-facts.md")

    def test_help_needs_no_rights_and_starts_nothing(self):
        d, pipe = deps()
        c = FakeClient()
        bridge.handle_mention({"user": STRANGER, "channel": CHANNEL, "ts": "t",
                               "text": "<@U_BOT> help"}, c, d)
        self.assertEqual(pipe.calls, [])
        self.assertIn("@lantern", c.posts[0]["text"])

    def test_no_repo_anywhere_is_a_question_not_a_run(self):
        d, pipe = deps(default_repo="")
        c = FakeClient()
        bridge.handle_mention({"user": OPERATOR, "channel": CHANNEL, "ts": "t",
                               "text": "<@U_BOT> do the thing"}, c, d)
        self.assertEqual(pipe.calls, [])
        self.assertIn("repo=", c.posts[0]["text"])

    def test_a_failed_start_says_why(self):
        d, pipe = deps(); pipe.ok, pipe.error = False, "brief not found"
        d.start_run = pipe.start_run
        c = FakeClient()
        res = bridge.handle_mention({"user": OPERATOR, "channel": CHANNEL, "ts": "t",
                                     "text": "<@U_BOT> something"}, c, d)
        self.assertFalse(res["ok"])
        self.assertIn("brief not found", c.posts[0]["text"])


class SlashCommands(unittest.TestCase):

    def test_rework_reaches_the_pipeline_with_the_note(self):
        d, pipe = deps()
        said = []
        bridge.handle_rework({"user_id": OPERATOR, "text": f"{RUN} 03-coding QA found a bug"},
                             lambda: None, said.append, d)
        self.assertEqual(pipe.calls, [("rework", RUN, "03-coding", f"slack:{OPERATOR}",
                                       "QA found a bug")])
        self.assertIn("03-coding", said[0])

    def test_a_bad_rework_target_is_refused_with_the_usage(self):
        d, pipe = deps()
        said = []
        bridge.handle_rework({"user_id": OPERATOR, "text": f"{RUN} 06-security"},
                             lambda: None, said.append, d)
        self.assertEqual(pipe.calls, [])
        self.assertIn("02-pre-coding", said[0])

    def test_retry_reaches_the_pipeline(self):
        d, pipe = deps()
        said = []
        bridge.handle_retry({"user_id": OPERATOR, "text": RUN}, lambda: None, said.append, d)
        self.assertEqual(pipe.calls, [("retry", RUN, f"slack:{OPERATOR}")])


class EventRelay(unittest.TestCase):

    def test_only_runs_with_a_thread_are_relayed_and_the_watermark_advances(self):
        d, _ = deps()
        d.recent_events = lambda since: [
            {"id": 11, "run_id": RUN, "actor": "orchestrator", "type": "stage_succeeded",
             "data": {"stage": "00-story.write"}, "slack_channel": CHANNEL,
             "slack_thread_ts": "ts_run"},
            {"id": 12, "run_id": "other", "actor": "orchestrator", "type": "stage_succeeded",
             "data": {"stage": "x"}, "slack_channel": None, "slack_thread_ts": None},
            {"id": 13, "run_id": RUN, "actor": "orchestrator", "type": "usage_recorded",
             "data": {}, "slack_channel": CHANNEL, "slack_thread_ts": "ts_run"},
        ]
        c = FakeClient()
        self.assertEqual(bridge.relay_events(c, d, 10), 13)
        self.assertEqual(len(c.posts), 1)
        self.assertIn("00-story.write", c.posts[0]["text"])

    def test_a_json_encoded_data_column_is_handled(self):
        d, _ = deps()
        d.recent_events = lambda since: [
            {"id": 20, "run_id": RUN, "actor": f"human:slack:{APPROVER}", "type": "gate_approved",
             "data": json.dumps({"gate": "story_signoff"}), "slack_channel": CHANNEL,
             "slack_thread_ts": "ts_run"}]
        c = FakeClient()
        bridge.relay_events(c, d, 0)
        self.assertIn("story_signoff", c.posts[0]["text"])
        self.assertIn(f"slack:{APPROVER}", c.posts[0]["text"])


class ConfigParsing(unittest.TestCase):

    def test_user_lists_accept_the_shapes_people_paste(self):
        self.assertEqual(bridge.parse_users("U1, U2  U3"), frozenset({"U1", "U2", "U3"}))
        self.assertEqual(bridge.parse_users("<@U1|dimash>,<@U2>"), frozenset({"U1", "U2"}))
        self.assertEqual(bridge.parse_users(None), frozenset())

    def test_operators_default_to_the_approvers(self):
        cfg = bridge.Config.from_env({"LANTERN_SLACK_APPROVERS": "U1 U2"})
        self.assertEqual(cfg.operators, frozenset({"U1", "U2"}))

    def test_the_default_gate_set_excludes_the_two_high_stakes_gates(self):
        cfg = bridge.Config.from_env({})
        self.assertNotIn("staging_deploy", cfg.gates)
        self.assertNotIn("prod_signoff", cfg.gates)
        self.assertIn("code_complete", cfg.gates)

    def test_an_unknown_gate_name_in_the_env_is_dropped(self):
        cfg = bridge.Config.from_env({"LANTERN_SLACK_GATES": "code_complete,everything"})
        self.assertEqual(cfg.gates, ("code_complete",))

    def test_the_bridge_never_imports_slack_outside_build_app(self):
        src = (HERE / "bridge.py").read_text(encoding="utf-8")
        before = src.split("def build_app", 1)[0]
        self.assertNotIn("import slack_bolt", before)
        self.assertNotIn("from slack_bolt", before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
