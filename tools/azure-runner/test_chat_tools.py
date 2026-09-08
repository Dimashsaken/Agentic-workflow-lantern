"""Write tools for the chat agent — the confirmation gate and the identity (D21).

    .venv/Scripts/python test_chat_tools.py      (no database, no network, no model)

The property under test is the one that makes agentic access safe: a write happens only
when the phrase is in the HUMAN'S OWN most recent message. Everything else here exists
to make that property observable — the executor is faked, the pipeline is never called,
and each check names what a real failure would let through.

Also covers the brief composer, since `start_run` refuses to create a run from a brief
that would not parse.
"""

import asyncio
import json
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
for var, dummy in (("AZURE_OPENAI_ENDPOINT", "https://test.invalid"),
                   ("AZURE_OPENAI_API_KEY", "test"),
                   ("LANTERN_MODEL_REASONING", "test-reasoning"),
                   ("LANTERN_MODEL_FAST", "test-fast"),
                   ("LANTERN_DATABASE_URL", "postgresql+asyncpg://x:y@127.0.0.1:1/none")):
    os.environ.setdefault(var, dummy)

import brief_composer                                    # noqa: E402
import chat_service as cs                                # noqa: E402
from agents.tool_context import ToolContext          # noqa: E402

USER = "dimash"
REPO = HERE.parents[1]


class FakeExecutor:
    """Stands in for PipelineExecutor: records calls, never touches Postgres or git."""

    def __init__(self, ok: bool = True, error: str = ""):
        self.calls: list[tuple] = []
        self.ok, self.error = ok, error

    def _res(self, run_id=None):
        out = {"ok": self.ok, "output": "pipeline said so"}
        if not self.ok:
            out["error"] = self.error or "refused"
        if run_id is not None:
            out["run_id"] = run_id if self.ok else None
        return out

    async def start_run(self, brief, run_id, by, repo, base, mode, working=""):
        self.calls.append(("start_run", brief, run_id, by, repo, base, mode, working))
        return self._res(run_id)

    async def decide(self, run_id, gate, by, note, approved):
        self.calls.append(("decide", run_id, gate, by, note, approved))
        return self._res()

    async def rework(self, run_id, to_stage, by, note):
        self.calls.append(("rework", run_id, to_stage, by, note))
        return self._res()

    async def retry(self, run_id, by):
        self.calls.append(("retry", run_id, by))
        return self._res()

    async def set_product(self, run_id, by, repo, branch, working=""):
        self.calls.append(("set_product", run_id, by, repo, branch, working))
        return self._res()


RUN = {"id": "feat-20260908-status-facts", "status": "waiting_gate",
       "current_stage": "00-story.write", "coding_mode": "human",
       "product_repo": "/repo", "product_branch": "main",
       "product_working_branch": None, "created_by": USER}
GATE = {"id": 7, "gate": "story_signoff",
        "requested_at": datetime.now(timezone.utc), "payload": {}}


def build(user_text: str, ex=None, run=RUN, gate=GATE):
    """The five tools, wired the way run_chat_turn wires them, with the database
    lookups faked. Returns (tools_by_name, executor, published_events)."""
    ex = ex or FakeExecutor()
    published: list[dict] = []
    cs._run_row = lambda run_id: _async(run if run and run_id == run["id"] else None)
    cs._pending_gate = lambda run_id, g: _async(
        gate if gate and run and run_id == run["id"] and g == gate["gate"] else None)
    tools = cs.make_write_tools(published.append, USER, user_text, None, executor=ex)
    return {t.name: t for t in tools}, ex, published


def _async(value):
    async def go():
        return value
    return go()


def call(tool, **kwargs) -> str:
    """Invoke a FunctionTool exactly as the SDK does — through its own ToolContext, so
    the schema, the argument parsing and the tool body are all under test, not a
    hand-called python function the model would never reach."""
    args = json.dumps(kwargs)
    ctx = ToolContext(context=None, tool_name=tool.name, tool_call_id="test",
                      tool_arguments=args)
    return asyncio.run(tool.on_invoke_tool(ctx, args))


class ConfirmationMatching(unittest.TestCase):
    """`confirmed()` is the whole safety property — it must be forgiving about typing
    and unforgiving about everything else."""

    def test_phrase_is_found_regardless_of_case_and_punctuation(self):
        phrase = cs.confirmation_phrase("approve", "story_signoff on feat-1")
        for text in ("confirm approve story_signoff on feat-1",
                     "CONFIRM APPROVE STORY_SIGNOFF ON FEAT-1",
                     "ok — confirm approve story_signoff on feat-1, please",
                     "confirm  approve   story-signoff  on  feat 1"):
            self.assertTrue(cs.confirmed(text, phrase), text)

    def test_near_misses_are_not_confirmations(self):
        phrase = cs.confirmation_phrase("approve", "story_signoff on feat-1")
        for text in ("", "yes", "approve it", "go ahead, approve story_signoff on feat-1",
                     "confirm approve story_signoff on feat-2",
                     "confirm reject story_signoff on feat-1",
                     "do NOT confirm approve"):
            self.assertFalse(cs.confirmed(text, phrase), text)


class ServerSideConfirmation(unittest.TestCase):
    """No phrase → a card and nothing else. The model cannot talk its way past this."""

    def test_decide_gate_without_a_phrase_does_not_decide(self):
        tools, ex, published = build("approve the story gate for me")
        out = call(tools["decide_gate"], run_id=RUN["id"], gate="story_signoff",
                   decision="approve", note="looks right")
        self.assertEqual(ex.calls, [], "a gate was decided with no confirmation")
        self.assertIn("NOT DONE", out)
        self.assertIn(cs.confirmation_phrase("approve", f"story_signoff on {RUN['id']}"), out)
        self.assertEqual([e["kind"] for e in published], ["card"])

    def test_a_phrase_from_an_older_turn_does_not_carry_over(self):
        # The developer confirmed LAST turn; this turn they said something else. The
        # tools are rebuilt per turn over the CURRENT message, so the old phrase is gone.
        tools, ex, _ = build("thanks, what did it cost?")
        call(tools["decide_gate"], run_id=RUN["id"], gate="story_signoff",
             decision="approve", note="")
        self.assertEqual(ex.calls, [], "an older turn's confirmation approved a gate")

    def test_the_model_cannot_confirm_on_the_humans_behalf(self):
        # The only text the server reads is the human turn; a model that writes the
        # phrase into its own arguments changes nothing.
        tools, ex, _ = build("what is waiting?")
        out = call(tools["decide_gate"], run_id=RUN["id"], gate="story_signoff",
                   decision="approve",
                   note=cs.confirmation_phrase("approve", f"story_signoff on {RUN['id']}"))
        self.assertEqual(ex.calls, [])
        self.assertIn("NOT DONE", out)

    def test_confirmed_gate_decision_reaches_the_pipeline_as_the_human(self):
        phrase = cs.confirmation_phrase("approve", f"story_signoff on {RUN['id']}")
        tools, ex, published = build(phrase)
        out = call(tools["decide_gate"], run_id=RUN["id"], gate="story_signoff",
                   decision="approve", note="criteria match the brief")
        self.assertEqual(ex.calls, [("decide", RUN["id"], "story_signoff", USER,
                                     "criteria match the brief", True)])
        self.assertIn("DONE", out)
        self.assertEqual([e["kind"] for e in published], ["action"])
        self.assertEqual(published[0]["by"], USER)

    def test_rejection_is_its_own_phrase(self):
        approve = cs.confirmation_phrase("approve", f"story_signoff on {RUN['id']}")
        tools, ex, _ = build(approve)
        call(tools["decide_gate"], run_id=RUN["id"], gate="story_signoff",
             decision="reject", note="wrong scope")
        self.assertEqual(ex.calls, [], "an approval phrase authorised a rejection")

    def test_rework_needs_its_own_confirmation(self):
        tools, ex, _ = build("send it back to coding")
        out = call(tools["rework"], run_id=RUN["id"], to_stage="03-coding", note="QA found a bug")
        self.assertEqual(ex.calls, [])
        self.assertIn(cs.confirmation_phrase("rework", f"{RUN['id']} to 03-coding"), out)

        tools, ex, _ = build(cs.confirmation_phrase("rework", f"{RUN['id']} to 03-coding"))
        call(tools["rework"], run_id=RUN["id"], to_stage="03-coding", note="QA found a bug")
        self.assertEqual(ex.calls, [("rework", RUN["id"], "03-coding", USER, "QA found a bug")])

    def test_a_pipeline_refusal_is_reported_as_a_refusal(self):
        phrase = cs.confirmation_phrase("approve", f"story_signoff on {RUN['id']}")
        tools, ex, published = build(phrase, ex=FakeExecutor(ok=False, error="no pending approval"))
        out = call(tools["decide_gate"], run_id=RUN["id"], gate="story_signoff",
                   decision="approve", note="")
        self.assertIn("REFUSED", out)
        self.assertIn("no pending approval", out)
        self.assertFalse(published[0]["ok"])


class GuardsBeforeTheCard(unittest.TestCase):
    """A card must describe something real, so the lookups happen first."""

    def test_unknown_run_is_named_not_carded(self):
        tools, ex, published = build("confirm approve story_signoff on feat-nope")
        out = call(tools["decide_gate"], run_id="feat-nope", gate="story_signoff",
                   decision="approve", note="")
        self.assertIn("no run", out)
        self.assertEqual(ex.calls, [])
        self.assertEqual(published, [])

    def test_a_gate_that_is_not_pending_is_refused(self):
        tools, ex, _ = build("confirm approve code_complete on " + RUN["id"])
        out = call(tools["decide_gate"], run_id=RUN["id"], gate="code_complete",
                   decision="approve", note="")
        self.assertIn("no pending", out)
        self.assertEqual(ex.calls, [])

    def test_decision_must_be_approve_or_reject(self):
        tools, ex, _ = build("confirm maybe")
        self.assertIn("approve", call(tools["decide_gate"], run_id=RUN["id"],
                                      gate="story_signoff", decision="maybe", note=""))
        self.assertEqual(ex.calls, [])

    def test_rework_target_is_checked_against_the_pipeline_list(self):
        tools, ex, _ = build("confirm rework x")
        out = call(tools["rework"], run_id=RUN["id"], to_stage="06-security", note="")
        self.assertIn("02-pre-coding", out)
        self.assertEqual(ex.calls, [])


class ReversibleToolsActDirectly(unittest.TestCase):
    """retry and set_product are stage-local and reversible — no confirmation turn."""

    def test_retry_runs_on_the_first_call(self):
        tools, ex, published = build("retry it")
        out = call(tools["retry"], run_id=RUN["id"])
        self.assertEqual(ex.calls, [("retry", RUN["id"], USER)])
        self.assertIn("DONE", out)
        self.assertEqual(published[0]["by"], USER)

    def test_set_product_runs_on_the_first_call_and_needs_a_repo(self):
        tools, ex, _ = build("point it at the repo")
        self.assertIn("which repository", call(tools["set_product"], run_id=RUN["id"],
                                               product_repo="", base_branch="", working_branch=""))
        self.assertEqual(ex.calls, [])
        call(tools["set_product"], run_id=RUN["id"], product_repo="/srv/app",
             base_branch="", working_branch="")
        self.assertEqual(ex.calls, [("set_product", RUN["id"], USER, "/srv/app", "main", "")])


class StartRunComposition(unittest.TestCase):
    """An idea becomes a brief that the pipeline's own parsers accept — or a question."""

    def test_an_idea_without_a_repo_asks_instead_of_guessing(self):
        tools, ex, published = build("start something")
        out = call(tools["start_run"], idea="Let editors bulk-export candidates",
                   brief_path="", product_repo="", base_branch="", coding_mode="auto",
                   must_haves="")
        self.assertEqual(ex.calls, [])
        self.assertEqual(published, [])
        self.assertIn("repo", out.lower())

    def test_an_idea_without_a_coding_mode_asks_for_one(self):
        tools, ex, _ = build("start something")
        out = call(tools["start_run"], idea="Bulk export", brief_path="",
                   product_repo="/srv/app", base_branch="", coding_mode="", must_haves="")
        self.assertEqual(ex.calls, [])
        self.assertIn("coding mode", out.lower())

    def test_a_complete_idea_cards_first_then_creates_the_run(self):
        tools, ex, published = build("start it")
        out = call(tools["start_run"], idea="Let editors bulk-export candidates",
                   brief_path="", product_repo="/srv/app", base_branch="main",
                   coding_mode="auto", must_haves="CSV download\nEmail on completion")
        self.assertEqual(ex.calls, [], "a run was created without confirmation")
        self.assertIn("NOT DONE", out)
        self.assertEqual(published[-1]["kind"], "card")
        slug = published[-1]["subject"]
        self.assertIn("bulk-export", slug)

    def test_exactly_one_of_idea_or_brief_path(self):
        tools, _, _ = build("go")
        self.assertIn("exactly one", call(tools["start_run"], idea="a", brief_path="b",
                                          product_repo="", base_branch="", coding_mode="",
                                          must_haves=""))
        self.assertIn("exactly one", call(tools["start_run"], idea="", brief_path="",
                                          product_repo="", base_branch="", coding_mode="",
                                          must_haves=""))

    def test_a_brief_path_that_does_not_exist_is_named(self):
        tools, ex, _ = build("go")
        out = call(tools["start_run"], idea="", brief_path="workflow/briefs/nope.md",
                   product_repo="/srv/app", base_branch="", coding_mode="human", must_haves="")
        self.assertIn("no brief", out)
        self.assertEqual(ex.calls, [])


class BriefComposer(unittest.TestCase):
    """The composed brief has to parse with the SAME functions `pipeline.py run` uses."""

    def setUp(self):
        self.fields = {"title": "Bulk export for editors",
                       "problem": "Editors copy rows by hand every Friday.",
                       "outcome": "One click produces a CSV.",
                       "must_haves": ["CSV in under 10 s", "audit event per export"],
                       "product_repo": "https://github.com/org/app",
                       "base_branch": "main", "coding_mode": "auto"}

    def test_a_composed_brief_parses_back(self):
        import pipeline
        res = brief_composer.compose(self.fields, by=USER,
                                     today=datetime(2026, 9, 8, tzinfo=timezone.utc))
        self.assertTrue(res["ok"], res["problems"] + res["missing"])
        self.assertEqual(res["slug"], "bulk-export-for-editors")
        self.assertEqual(res["run_id"], "feat-20260908-bulk-export-for-editors")
        repo, base, work = pipeline.parse_brief_product(res["markdown"])
        self.assertEqual((repo, base, work), ("https://github.com/org/app", "main", ""))
        self.assertEqual(pipeline.parse_brief_coding_mode(res["markdown"]), "auto")
        self.assertIn("- CSV in under 10 s", res["markdown"])
        self.assertIn("## Non-goals", res["markdown"])

    def test_missing_required_fields_are_reported_not_invented(self):
        res = brief_composer.compose({"title": "x"}, by=USER)
        self.assertFalse(res["ok"])
        self.assertIn("problem", res["missing"])
        self.assertIn("product_repo", res["missing"])

    def test_auto_mode_without_a_repo_is_a_problem(self):
        res = brief_composer.compose({**self.fields, "product_repo": ""}, by=USER)
        self.assertFalse(res["ok"])
        self.assertTrue(any("product repo" in p for p in res["problems"]))

    def test_a_blank_working_branch_stays_blank(self):
        # The 2026-09-08 parser bug: an empty field swallowed the next line.
        import pipeline
        res = brief_composer.compose(self.fields, by=USER)
        self.assertEqual(pipeline.parse_brief_product(res["markdown"])[2], "")

    def test_a_hand_written_brief_is_never_overwritten(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            briefs = Path(d)
            (briefs / "mine.md").write_text("# Feature Brief: mine\n", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                brief_composer.write_brief("mine", "# composed\n", briefs_dir=briefs)
            # a composed brief carries the marker and may be refreshed
            brief_composer.write_brief("auto", f"# x\n{brief_composer.MARKER} -->\n", briefs_dir=briefs)
            brief_composer.write_brief("auto", f"# y\n{brief_composer.MARKER} -->\n", briefs_dir=briefs)
            self.assertIn("# y", (briefs / "auto.md").read_text(encoding="utf-8"))

    def test_a_slug_cannot_escape_the_briefs_directory(self):
        for bad in ("../../etc/passwd", "a/b", "", "UPPER"):
            with self.assertRaises(ValueError):
                brief_composer.brief_path(bad)


class AgentWiring(unittest.TestCase):
    """Who gets hands, and what the prompt tells them about using them."""

    def test_only_the_orchestrator_is_given_write_tools(self):
        src = (HERE / "chat_service.py").read_text(encoding="utf-8")
        builder = src.split("async def build_chat_agent", 1)[1]
        fleet_and_custom = builder.split('if info["kind"] == "fleet":', 1)[1]
        self.assertNotIn("make_write_tools", fleet_and_custom,
                         "a fleet-role or custom consult was given write tools — D11's line")
        self.assertIn("make_write_tools",
                      builder.split('if info["kind"] == "fleet":', 1)[0])

    def test_a_turn_without_a_signed_in_human_gets_no_write_tools(self):
        src = (HERE / "chat_service.py").read_text(encoding="utf-8")
        self.assertIn("if by else []", src)

    def test_the_protocol_is_in_the_prompt_when_the_tools_are(self):
        with_hands = cs.build_lantern_instructions(USER, can_write=True)
        without = cs.build_lantern_instructions(USER, can_write=False)
        self.assertIn("decision card", with_hands)
        flat = " ".join(with_hands.split())
        self.assertIn("cannot confirm on their behalf", flat)
        self.assertIn(USER, with_hands)
        self.assertIn("read-only", without)
        self.assertNotIn("decision card", without)

    def test_the_tools_close_over_this_turns_text(self):
        src = (HERE / "chat_service.py").read_text(encoding="utf-8")
        self.assertIn("by=by, user_text=user_text", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
