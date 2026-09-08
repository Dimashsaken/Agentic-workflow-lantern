"""Behavior tests for the chat transcript's reading contract (docs/CHAT.md).

Stdlib only — no database, no HTTP client, no pytest. Rendering functions are
called directly; FastAPI and the model layer are stubbed when absent, so this
runs on a laptop without the runner venv.

    cd tools/mission-control && python -m unittest test_chat_ux -v

Contract under test:
  * The window is a fixed frame: the shell columns carry min-height:0 (without
    it a long transcript floors at its content height and the whole page
    scrolls), and the transcript owns its own scrollbar.
  * The client never scrolls on its own: it anchors the newest turn, follows
    only when the reader is already at the bottom, and offers a jump pill.
  * Thinking never reaches the transcript — chat_service publishes it live-only
    and trace_html has no branch that could render it.
  * Tool lines read as calls with folded results; long traces fold.
  * The composer stays usable while a turn runs (queue), recalls past messages,
    and a finished reply can be copied.
"""

import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "azure-runner"))

try:                                    # the runner venv has these
    import fastapi                      # noqa: F401
except ModuleNotFoundError:             # a bare laptop does not
    fa = types.ModuleType("fastapi")

    class _Router:
        def _deco(self, *a, **k):
            return lambda f: f
        get = post = _deco

    fa.APIRouter = _Router
    fa.Form = lambda *a, **k: None
    fa.HTTPException = type("HTTPException", (Exception,), {})
    fa.Request = object
    responses = types.ModuleType("fastapi.responses")
    responses.HTMLResponse = responses.RedirectResponse = object
    responses.StreamingResponse = object
    fa.responses = responses
    sys.modules["fastapi"], sys.modules["fastapi.responses"] = fa, responses

try:
    import chat_service                 # noqa: F401
except Exception:                       # noqa: BLE001 — no Azure env on a laptop
    cs = types.ModuleType("chat_service")
    cs.LANTERN_AGENT = "lantern"
    cs.BUS = object()
    sys.modules["chat_service"] = cs

try:
    import pipeline                     # noqa: F401
except Exception:                       # noqa: BLE001
    pl = types.ModuleType("pipeline")
    pl.est_cost_usd = lambda i, c, o, m: 0.0
    sys.modules["pipeline"] = pl

import chat  # noqa: E402
import ui  # noqa: E402

chat.deps.setdefault("render_markdown", lambda t: f"<p>{ui.H(t)}</p>")

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
CHAT_SERVICE = (HERE.parent / "azure-runner" / "chat_service.py").read_text(encoding="utf-8")


def turn(**over) -> dict:
    row = {
        "id": 1, "user_text": "why did QA fail?", "final_text": "Because the login timed out.",
        "trace": [], "status": "done", "error": None, "started_at": NOW,
        "finished_at": NOW + timedelta(seconds=42), "model": "gpt-5", "total_tokens": 1200,
        "input_tokens": 1000, "cached_input_tokens": 600, "output_tokens": 200,
    }
    row.update(over)
    return row


def tools(n: int) -> list:
    out = []
    for i in range(n):
        out.append({"kind": "tool", "name": f"read_file", "args": '{"path": "AGENTS.md"}'})
        out.append({"kind": "tool_done", "output": f"line a\nline b\nline {i}"})
    return out


class FixedWindow(unittest.TestCase):
    """The page never scrolls; the transcript does."""

    def test_shell_columns_cannot_floor_at_content_height(self):
        for rule in (".chatwrap{", ".chatside{", ".chatmain{"):
            block = ui.CSS.split(rule, 1)[1].split("}", 1)[0]
            self.assertIn("min-height:0", block, f"{rule} may grow past the frame")
        self.assertIn("overflow:hidden", ui.CSS.split(".chatwrap{", 1)[1].split("}", 1)[0])

    def test_transcript_owns_its_scroll(self):
        block = ui.CSS.split(".transcript{", 1)[1].split("}", 1)[0]
        self.assertIn("overflow-y:auto", block)
        self.assertIn("min-height:0", block)
        # We place the scroll ourselves — easing and browser anchoring fight us.
        self.assertNotIn("scroll-behavior:smooth", block)
        self.assertIn("overflow-anchor:none", block)

    def test_transcript_markup_carries_the_anchor_spacer(self):
        src = (HERE / "chat.py").read_text(encoding="utf-8")
        self.assertIn("class='tinner'", src)
        self.assertIn("class='tailpad'", src)
        self.assertIn(".tailpad{", ui.CSS)


class ClientContract(unittest.TestCase):
    """What chat_js promises the reader."""

    def setUp(self):
        self.js = chat.chat_js("consult:me:lantern:x", "LANTERN", None)

    def test_streaming_never_moves_a_reader_who_scrolled_away(self):
        self.assertIn("if(follow){ tr.scrollTop = tr.scrollHeight", self.js)
        self.assertIn("function anchorLast()", self.js)
        # follow is only re-armed by the reader reaching the bottom (or the pill)
        self.assertIn("if(gap() < 40){ follow = true", self.js)

    def test_the_last_turn_is_found_past_the_spacer(self):
        # :last-of-type would match the spacer div and silently disable anchoring
        self.assertNotIn("'.turn:last-of-type'", self.js)
        self.assertIn("querySelectorAll('.turn')", self.js)

    def test_jump_pill_and_queue_exist(self):
        self.assertIn("jumplatest", self.js)
        self.assertIn("function drain()", self.js)
        self.assertIn("queue.push(text)", self.js)

    def test_composer_is_never_disabled_by_a_running_turn(self):
        self.assertNotIn("input.disabled = b", self.js)
        self.assertNotIn("function setBusy", self.js)

    def test_history_recall_and_draft_survival(self):
        self.assertIn("ArrowUp", self.js)
        self.assertIn("localStorage.setItem(DRAFT", self.js)

    def test_thinking_is_a_status_line_not_a_message(self):
        self.assertIn("case 'thinking': setPhase('Thinking')", self.js)
        # nothing appends the model's reasoning to the transcript
        self.assertNotIn("thinking.text", self.js)
        self.assertIn("esc to interrupt", self.js)

    def test_the_final_swap_holds_the_reader_s_position(self):
        self.assertIn("var keep = live.getBoundingClientRect().top", self.js)


class Transcript(unittest.TestCase):
    """Server-rendered turns: Claude Code anatomy, nothing invented."""

    def test_tool_line_reads_as_a_call(self):
        html = chat.trace_html([{"kind": "tool", "name": "read_file",
                                 "args": '{"path": "workflow/RUNBOARD.md"}'}])
        self.assertIn("read_file", html)
        self.assertIn("(workflow/RUNBOARD.md)", html)
        self.assertNotIn("&#x27;path&#x27;", html)

    def test_multi_argument_calls_keep_their_key_names(self):
        self.assertEqual(chat.args_summary('{"run_id": "r1", "stage": "04-qa-dev"}'),
                         "run_id=r1, stage=04-qa-dev")
        self.assertEqual(chat.args_summary("{}"), "")
        self.assertEqual(chat.args_summary("not json"), "not json")

    def test_result_headers_count_lines_then_chars(self):
        self.assertEqual(chat.out_summary("a\nb\nc"), "3 lines")
        self.assertEqual(chat.out_summary("abc"), "3 chars")
        self.assertEqual(chat.out_summary(""), "empty result")

    def test_a_long_trace_folds_instead_of_burying_the_answer(self):
        short = chat.trace_html(tools(chat.WORK_FOLD_AT))
        self.assertNotIn("workfold", short)
        long = chat.trace_html(tools(chat.WORK_FOLD_AT + 1))
        self.assertIn("workfold", long)
        self.assertIn(f"{chat.WORK_FOLD_AT + 1} tool calls", long)

    def test_thinking_never_renders_even_if_a_trace_carries_it(self):
        html = chat.trace_html([{"kind": "thinking", "text": "let me think about this"},
                                {"kind": "tool", "name": "read_file", "args": "{}"}])
        self.assertNotIn("think", html.lower())

    def test_chat_service_keeps_reasoning_off_the_record(self):
        self.assertIn('publish({"kind": "thinking"}, persist=False)', CHAT_SERVICE)
        self.assertNotIn('publish({"kind": "thinking"})', CHAT_SERVICE)
        self.assertIn('dtype.startswith("response.reasoning")', CHAT_SERVICE)

    def test_a_finished_reply_can_be_copied_an_empty_one_cannot(self):
        self.assertIn("class='copy'", chat.agent_block(turn(), "LANTERN"))
        self.assertNotIn("class='copy'",
                         chat.agent_block(turn(final_text=None, status="stopped"), "LANTERN"))

    def test_composer_says_what_this_agent_can_do_plus_the_queue_and_the_pill(self):
        # The line has to be TRUE per agent, not merely present: since D21 the
        # orchestrator can act (behind a typed confirmation) while every specialist
        # is still D11's read-only consult. A single hard-coded line would lie about
        # one of them.
        lantern = chat.composer("sid", "lantern", {"lantern": {"name": "Lantern"}},
                                0.32, 3, None, disabled=False)
        self.assertIn("acts only on your typed confirmation", lantern)
        self.assertNotIn("advisory, read-only", lantern)
        specialist = chat.composer("sid", "security", {"security": {"name": "security"}},
                                   0.0, 1, None, disabled=False)
        self.assertIn("advisory, read-only", specialist)
        for html in (lantern, specialist):
            self.assertIn("id='queued'", html)
            self.assertIn("id='jumplatest'", html)
        self.assertIn("$0.32 this chat", lantern)

    def test_a_disabled_composer_still_says_why_it_is_there(self):
        html = chat.composer("sid", "lantern", {"lantern": {"name": "Lantern"}},
                             0.0, 0, None, disabled=True)
        self.assertIn("disabled", html)
        self.assertIn("nothing billed yet", html)


class DecisionCards(unittest.TestCase):
    """Confirmation cards (D21). The card is rendered by the SERVER from the trace, so
    what the reader sees is what the tool actually asked for — not the model's prose
    about it — and the phrase on screen is the one the server will match."""

    CARD = {"kind": "card", "verb": "approve", "subject": "story_signoff on feat-1",
            "phrase": "confirm approve story_signoff on feat-1",
            "title": "Approve `story_signoff` on `feat-1`",
            "lines": ["stage: 00-story.write", "recorded as: dimash"],
            "run_id": "feat-1", "gate": "story_signoff"}

    def test_the_card_shows_the_phrase_and_links_to_the_run(self):
        html = chat.card_html(self.CARD)
        self.assertIn("confirm approve story_signoff on feat-1", html)
        self.assertIn("needs your confirmation", html)
        self.assertIn("/run/feat-1", html)
        self.assertIn("stage: 00-story.write", html)
        self.assertIn("Nothing has happened yet", html)

    def test_a_card_is_never_folded_away_behind_the_tool_count(self):
        # Six-plus tool calls fold; a decision the reader has to make must not.
        trace = tools(8) + [self.CARD]
        html = chat.trace_html(trace)
        self.assertIn("tool calls</summary>", html)          # the work folded
        card = html.split("</details>")[-1]                  # what is left outside the fold
        self.assertIn("confirm approve story_signoff on feat-1", card)

    def test_an_executed_action_says_what_changed_and_who_it_was(self):
        ok = chat.action_html({"kind": "action", "action": "approved `story_signoff`",
                               "ok": True, "by": "dimash", "run_id": "feat-1",
                               "detail": "advancing."})
        self.assertIn("done", ok)
        self.assertIn("dimash", ok)
        self.assertIn("/run/feat-1", ok)
        bad = chat.action_html({"kind": "action", "action": "approved `x`", "ok": False,
                                "by": "dimash", "detail": "no pending approval"})
        self.assertIn("not applied", bad)
        self.assertIn("no pending approval", bad)

    def test_card_text_is_escaped_like_every_other_surface(self):
        html = chat.card_html({**self.CARD, "title": "<script>alert(1)</script>"})
        self.assertNotIn("<script>", html)

    def test_the_client_renders_cards_live_and_only_types_the_phrase(self):
        js = chat.chat_js("sid", "LANTERN", None)
        self.assertIn("case 'card':", js)
        self.assertIn("case 'action':", js)
        # "Type it for me" fills the composer; it must never send on the reader's behalf.
        usephrase = js.split(".usephrase")[1].split("});")[0]
        self.assertNotIn("submit()", usephrase)
        self.assertNotIn("/send", usephrase)


if __name__ == "__main__":
    unittest.main(verbosity=2)
