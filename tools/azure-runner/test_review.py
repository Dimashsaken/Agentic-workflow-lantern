"""Review loop + merge babysitter (D19): envelope, the bounded loop, PR reviews, babysitting.

    .venv/Scripts/python test_review.py      (no database, no Azure, no network; real git + bash)

Why these tests exist: the review loop decides WHEN a human is pinged and the babysitter
PUSHES to a branch a human already approved. Each property below is one a confused
execution, a lying envelope or a moved base could break:

1. The review envelope is validated, not trusted: ids unique, must_fix ⊆ findings and
   ⊇ every blocker/major, verdict approve ⇔ no blocker/major, the round's twin exists.
2. The loop is bounded and honest: approve stops it; request_changes runs ONE fix
   execution whose task block carries the must_fix list, publishes, reviews again; the
   rounds cap opens the gate with the last review; a failing execution never fails the
   already-published branch.
3. PR reviews are one COMMENT-event review per round, built without a network, posted
   only when a token exists, degraded (no inline comments) on a 422, never a failure.
4. The babysitter, on real git: base moves ahead → the merge commit lands on the branch
   and the quality gate re-runs; red → one fix execution; conflict → stops with the
   file list, an alarm and merge-conflict.md, and stays stopped until the base moves;
   merged → recorded and left alone. It never touches the base.
5. The runtime wiring: ROLE_FOR_STAGE / STAGE_DIR know the sub-stages and the coding
   role's fix execution gets the must_fix list in its task block.
"""

import asyncio
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import factory as f  # noqa: E402
import review as r  # noqa: E402

RUN = "feat-20260908-review-proof"
BRANCH = "feat/20260908-review-proof"


def git(*args, cwd: Path) -> str:
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, errors="replace")
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout.strip()


def rmtree(path: Path) -> None:
    r.force_rmtree(path)


class FakeConn:
    """Enough of asyncpg for the loop and the babysitter: records every statement."""

    def __init__(self):
        self.sql: list[tuple[str, tuple]] = []

    async def execute(self, q, *a):
        self.sql.append((" ".join(q.split()), a))
        return "UPDATE 1"

    async def fetchval(self, q, *a):
        self.sql.append((" ".join(q.split()), a))
        return 1

    async def fetchrow(self, q, *a):
        return None

    async def fetch(self, q, *a):
        return []

    def statements(self, needle: str) -> list[tuple[str, tuple]]:
        return [s for s in self.sql if needle in s[0]]


def finding(fid="R-1", severity="major", file="src/app.py", line=3, summary="off by one",
            suggestion="use <= not <"):
    return {"id": fid, "severity": severity, "file": file, "line": line,
            "summary": summary, "suggestion": suggestion}


def review_doc(round_no=1, verdict="approve", findings=None, must_fix=None, run_id=RUN):
    return {"kind": "review", "run_id": run_id, "round": round_no, "verdict": verdict,
            "findings": findings or [], "must_fix": must_fix or []}


def write_review(doc: dict, md: bool = True) -> None:
    d = r.review_dir(doc["run_id"])
    d.mkdir(parents=True, exist_ok=True)
    (d / "review.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    if md:
        (d / f"round-{doc['round']}.md").write_text(f"# review round {doc['round']}\n\n{doc['verdict']}\n",
                                                   encoding="utf-8")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="review-"))
        self.repo_backup = f.REPO
        f.REPO = self.tmp / "lantern"
        self.rd = f.REPO / "workflow" / "runs" / RUN
        (self.rd / "03-coding").mkdir(parents=True)
        self.handoff = {"kind": "coding_branch", "run_id": RUN, "branch": BRANCH, "base": "main",
                        "base_sha": "a" * 40, "head_sha": "b" * 40,
                        "commits": [{"sha": "b" * 40, "subject": f"{RUN}: task 1"}],
                        "files_changed": ["src/app.py"], "bundle": f"workflow/runs/{RUN}/03-coding/branch.bundle"}
        (self.rd / "03-coding" / "handoff.json").write_text(json.dumps(self.handoff), encoding="utf-8")
        self.env = mock.patch.dict(os.environ, {"LANTERN_REVIEW_ROUNDS": "2"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        f.REPO = self.repo_backup
        rmtree(self.tmp)

    def deps(self, **over) -> r.Deps:
        self.calls: list[tuple] = []
        self.events: list[tuple] = []
        self.alarms: list[str] = []

        async def execute(conn, run_id, stage, runner):
            self.calls.append(("execute", stage))

        async def publish(conn, run_id):
            self.calls.append(("publish",))
            return {"head_sha": "c" * 40, "commit_count": 2, "pushed": False, "pr_url": None}

        async def product(conn, run_id):
            return ("", "main", BRANCH)

        async def event(conn, run_id, actor, type_, data=None):
            self.events.append((actor, type_, data or {}))

        base = dict(execute=execute, publish=publish, product=product,
                    mirror=lambda repo: Path(repo), event=event, alarm=self.alarms.append)
        base.update(over)
        return r.Deps(**base)


# ── 1. the envelope ──────────────────────────────────────────────────────────

class Envelope(Base):
    def check(self, doc, md=True):
        write_review(doc, md)
        return "\n".join(f.check_envelope(RUN, r.REVIEW_STAGE))

    def test_registered_and_valid_approve(self):
        self.assertIn(r.REVIEW_STAGE, f.ENVELOPES)
        self.assertEqual(self.check(review_doc()), "")

    def test_valid_request_changes(self):
        doc = review_doc(2, "request_changes", [finding(), finding("R-2", "nit", line=None, suggestion="")],
                         ["R-1"])
        self.assertEqual(self.check(doc), "")

    def test_round_twin_must_exist(self):
        probs = self.check(review_doc(3), md=False)
        self.assertIn("review/round-3.md missing", probs)

    def test_ids_unique_and_must_fix_subset(self):
        doc = review_doc(1, "request_changes", [finding("R-1"), finding("R-1")], ["R-1", "R-9"])
        probs = self.check(doc)
        self.assertIn("duplicate finding id R-1", probs)
        self.assertIn("must_fix names findings that do not exist: R-9", probs)

    def test_verdict_is_computed(self):
        probs = self.check(review_doc(1, "approve", [finding()], ["R-1"]))
        self.assertIn("findings say 'request_changes'", probs)
        probs = self.check(review_doc(1, "request_changes", [finding(severity="nit")], []))
        self.assertIn("findings say 'approve'", probs)
        probs = self.check(review_doc(1, "maybe", [], []))
        self.assertIn("verdict must be one of approve/request_changes", probs)

    def test_every_blocker_or_major_is_must_fix(self):
        doc = review_doc(1, "request_changes", [finding("R-1", "blocker"), finding("R-2", "major")], ["R-1"])
        self.assertIn("add R-2 to must_fix", self.check(doc))

    def test_shape_rules(self):
        doc = review_doc(1, "request_changes",
                         [finding("R-1", "huge"), finding("R-2", "blocker", summary="", suggestion=""),
                          finding("R-3", "minor", line=-4), {"severity": "nit"}],
                         ["R-1", "R-2"])
        probs = self.check(doc)
        self.assertIn("R-1: severity must be one of", probs)
        self.assertIn("R-2: summary is required", probs)
        self.assertIn("R-2: a blocker needs a suggestion", probs)
        self.assertIn("R-3: line must be a positive integer or null", probs)
        self.assertIn("findings[3].id is required", probs)
        self.assertIn("round-?.md missing", self.check(dict(review_doc(), round="one"), md=False))
        self.assertIn("round must be a positive integer", self.check(dict(review_doc(), round=0)))

    def test_kind_and_run_id_still_checked(self):
        d = r.review_dir(RUN)
        d.mkdir(parents=True, exist_ok=True)
        (d / "review.json").write_text(json.dumps(review_doc(run_id="other")), encoding="utf-8")
        (d / "round-1.md").write_text("# r\n", encoding="utf-8")
        probs = "\n".join(f.check_envelope(RUN, r.REVIEW_STAGE))
        self.assertIn("run_id must be", probs)


# ── 2. the loop ──────────────────────────────────────────────────────────────

class Loop(Base):
    def scripted(self, verdicts: list[str], on_fix=None):
        """A fake executor: review executions write the scripted verdict for their
        round; fix executions call on_fix(task_block) and record."""
        rounds_seen = []

        async def execute(conn, run_id, stage, runner):
            self.calls.append(("execute", stage))
            if stage == r.REVIEW_STAGE:
                n = r.read_state(run_id)["round"]
                rounds_seen.append(n)
                v = verdicts[n - 1]
                if v == "raise":
                    raise RuntimeError("postconditions failed: review.json invalid")
                if v == "wrong_round":
                    write_review(review_doc(n + 5, "approve"))
                    return
                fs = [finding(f"R-{n}", summary=f"round {n} bug")] if v == "request_changes" else []
                write_review(review_doc(n, v, fs, [x["id"] for x in fs]))
            elif stage == r.FIX_STAGE:
                st = r.read_state(run_id)
                self.assertEqual(st["phase"], "fix")
                if on_fix:
                    on_fix(r.task_block(run_id, r.FIX_STAGE), st)
        return execute, rounds_seen

    def run_loop(self, deps, payload=None):
        conn = FakeConn()
        out = asyncio.run(r.after_publish(conn, RUN, payload or {"branch": BRANCH, "pr_url": None}, "ec2", deps))
        return conn, out

    def test_approve_on_round_two_means_one_fix(self):
        blocks = []
        execute, seen = self.scripted(["request_changes", "approve"],
                                      on_fix=lambda block, st: blocks.append((block, st)))
        conn, out = self.run_loop(self.deps(execute=execute))
        self.assertEqual([c for c in self.calls], [("execute", r.REVIEW_STAGE), ("execute", r.FIX_STAGE),
                                                    ("publish",), ("execute", r.REVIEW_STAGE)])
        rv = out["review"]
        self.assertEqual(rv["verdict"], "approve")
        self.assertEqual(rv["fix_executions"], 1)
        self.assertFalse(rv["capped"])
        self.assertEqual([x["round"] for x in rv["rounds"]], [1, 2])
        self.assertEqual(rv["rounds"][0]["fixed"]["head_sha"], "c" * 40)
        self.assertEqual(out["head_sha"], "c" * 40)                     # the republished payload wins
        # must_fix reached the fix execution's task block, with the finding's detail
        block, st = blocks[0]
        self.assertEqual(st["fix"]["must_fix"], ["R-1"])
        self.assertIn("R-1", block)
        self.assertIn("round 1 bug", block)
        self.assertIn("use <= not <", block)
        self.assertIn("Ignore the plan", block)
        # the second review's block knows about round 1 and the fix
        self.assertEqual(seen, [1, 2])
        self.assertEqual([e[1] for e in self.events].count("review_round"), 2)
        self.assertEqual(r.read_state(RUN)["phase"], "done")

    def test_never_approve_is_capped_with_the_last_review_attached(self):
        execute, _ = self.scripted(["request_changes", "request_changes", "request_changes"])
        conn, out = self.run_loop(self.deps(execute=execute))
        self.assertEqual(self.calls, [("execute", r.REVIEW_STAGE), ("execute", r.FIX_STAGE),
                                      ("publish",), ("execute", r.REVIEW_STAGE)])
        rv = out["review"]
        self.assertTrue(rv["capped"])
        self.assertEqual(rv["verdict"], "request_changes")
        self.assertEqual(rv["last"]["must_fix"], ["R-2"])
        self.assertEqual(rv["last"]["items"][0]["summary"], "round 2 bug")
        self.assertIn("review_capped", [e[1] for e in self.events])

    def test_one_round_never_fixes_and_zero_skips(self):
        with mock.patch.dict(os.environ, {"LANTERN_REVIEW_ROUNDS": "1"}):
            execute, _ = self.scripted(["request_changes"])
            conn, out = self.run_loop(self.deps(execute=execute))
        self.assertEqual(self.calls, [("execute", r.REVIEW_STAGE)])
        self.assertTrue(out["review"]["capped"])
        with mock.patch.dict(os.environ, {"LANTERN_REVIEW_ROUNDS": "0"}):
            conn, out = self.run_loop(self.deps())
        self.assertEqual(self.calls, [])
        self.assertEqual(out["review"]["verdict"], "skipped")

    def test_review_block_carries_round_context(self):
        r.write_state(RUN, phase="review", round=2, max_rounds=3,
                      history=[{"round": 1, "verdict": "request_changes", "must_fix": ["R-1"],
                                "fixed": {"head_sha": "c" * 40, "commits": 2}}])
        block = r.task_block(RUN, r.REVIEW_STAGE)
        self.assertIn("2 of 3", block)
        self.assertIn(BRANCH, block)
        self.assertIn("aaaaaaaaaaaa..bbbbbbbbbbbb", block)
        self.assertIn("round 1: request_changes, must-fix R-1", block)
        self.assertIn("round-1.md", block)
        self.assertEqual(r.task_block(RUN, "04-qa-dev"), "")

    def test_failed_review_execution_opens_the_gate_without_it(self):
        execute, _ = self.scripted(["raise"])
        conn, out = self.run_loop(self.deps(execute=execute))
        self.assertEqual(self.calls, [("execute", r.REVIEW_STAGE)])
        self.assertEqual(out["review"]["verdict"], "error")
        self.assertIn("postconditions failed", out["review"]["rounds"][0]["error"])
        failed = conn.statements("SET status = 'failed'")
        self.assertEqual(failed[0][1][1:], (RUN, r.REVIEW_STAGE, "terminal"))
        self.assertIn("review_failed", [e[1] for e in self.events])

    def test_wrong_round_in_review_json_is_an_error(self):
        execute, _ = self.scripted(["wrong_round"])
        conn, out = self.run_loop(self.deps(execute=execute))
        self.assertEqual(out["review"]["verdict"], "error")
        self.assertIn("not round 1", out["review"]["rounds"][0]["error"])

    def test_failed_fix_keeps_the_review(self):
        async def execute(conn, run_id, stage, runner):
            self.calls.append(("execute", stage))
            if stage == r.REVIEW_STAGE:
                write_review(review_doc(1, "request_changes", [finding()], ["R-1"]))
            else:
                raise RuntimeError("coding handoff failed: added no commits")
        conn, out = self.run_loop(self.deps(execute=execute))
        self.assertEqual(self.calls, [("execute", r.REVIEW_STAGE), ("execute", r.FIX_STAGE)])
        rv = out["review"]
        self.assertEqual(rv["verdict"], "request_changes")
        self.assertIn("added no commits", rv["rounds"][0]["fix_error"])
        self.assertEqual(rv["last"]["must_fix"], ["R-1"])
        self.assertEqual(conn.statements("SET status = 'failed'")[0][1][1:], (RUN, r.FIX_STAGE, "terminal"))

    def test_pr_review_is_posted_per_round_when_a_pr_exists(self):
        posted = []

        def gh_api(method, path, data=None):
            posted.append((method, path, data))
            return 201, {"html_url": "https://github.com/o/n/pull/7#pullrequestreview-1", "id": 1}
        execute, _ = self.scripted(["approve"])
        conn, out = self.run_loop(self.deps(execute=execute, gh_api=gh_api, public_url="https://mc"),
                                  {"branch": BRANCH, "pr_url": "https://github.com/o/n/pull/7"})
        self.assertEqual(posted[0][1], "/repos/o/n/pulls/7/reviews")
        self.assertTrue(out["review"]["rounds"][0]["pr_review"]["posted"])
        self.assertIn("https://mc/run/" + RUN, posted[0][2]["body"])
        # and without a PR (local-path repo) nothing is attempted, nothing fails
        posted.clear()
        execute, _ = self.scripted(["approve"])
        conn, out = self.run_loop(self.deps(execute=execute, gh_api=gh_api))
        self.assertEqual(posted, [])
        self.assertFalse(out["review"]["rounds"][0]["pr_review"]["posted"])


# ── 3. PR reviews ────────────────────────────────────────────────────────────

class PullRequestReview(unittest.TestCase):
    def test_request_body_is_one_comment_review_with_inline_findings(self):
        doc = review_doc(2, "request_changes",
                         [finding("R-1", "blocker", "src/a.py", 10, "crash | on empty", "guard"),
                          finding("R-2", "major", "tests/test_a.py", None, "missing test", "add one"),
                          finding("R-3", "nit", "", None, "naming", "")], ["R-1", "R-2"])
        req = r.pr_review_request(doc, RUN, "https://mc.example")
        self.assertEqual(req["event"], "COMMENT")
        self.assertIn("round 2: REQUEST CHANGES", req["body"])
        self.assertIn("2 must-fix, 3 finding(s)", req["body"])
        self.assertIn("R-1 ★", req["body"])
        self.assertIn("crash / on empty", req["body"])           # a pipe cannot break the table
        self.assertIn("https://mc.example/run/" + RUN, req["body"])
        self.assertIn("a human merges", req["body"])
        self.assertEqual([c["path"] for c in req["comments"]], ["src/a.py"])     # only file+line findings
        self.assertEqual(req["comments"][0]["line"], 10)
        self.assertIn("Suggestion: guard", req["comments"][0]["body"])
        self.assertIn("No findings.", r.pr_review_request(review_doc(), RUN)["body"])

    def test_no_token_means_run_folder_only(self):
        res = r.post_pr_review("o", "n", 7, review_doc(), run_id=RUN, gh_api=None)
        self.assertFalse(res["posted"])
        self.assertIn("GITHUB_LANTERN_BOT_TOKEN", res["reason"])

    def test_422_falls_back_to_body_only(self):
        calls = []

        def gh_api(method, path, data=None):
            calls.append(data)
            if data["comments"]:
                return 422, {"message": "line must be part of the diff"}
            return 200, {"html_url": "u", "id": 9}
        doc = review_doc(1, "request_changes", [finding()], ["R-1"])
        res = r.post_pr_review("o", "n", 7, doc, run_id=RUN, gh_api=gh_api)
        self.assertTrue(res["posted"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]["comments"], [])
        self.assertIn("R-1", calls[1]["body"])

    def test_api_trouble_is_never_a_failure(self):
        def boom(method, path, data=None):
            raise OSError("network down")
        res = r.post_pr_review("o", "n", 7, review_doc(), run_id=RUN, gh_api=boom)
        self.assertFalse(res["posted"])
        self.assertIn("network down", res["reason"])
        res = r.post_pr_review("o", "n", 7, review_doc(), run_id=RUN,
                               gh_api=lambda m, p, d=None: (403, {"message": "Resource not accessible"}))
        self.assertFalse(res["posted"])
        self.assertIn("403", res["reason"])


# ── 4. the babysitter, on real git ───────────────────────────────────────────

class Babysitter(Base):
    def setUp(self):
        super().setUp()
        self.seed = self.tmp / "seed"
        self.seed.mkdir()
        git("init", "-q", "-b", "main", cwd=self.seed)
        git("config", "user.name", "seed", cwd=self.seed)
        git("config", "user.email", "seed@example.invalid", cwd=self.seed)
        (self.seed / "README.md").write_text("# product\n", encoding="utf-8")
        (self.seed / "src").mkdir()
        (self.seed / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
        (self.seed / "lantern.toml").write_text('[quality]\ntest = "test -f README.md"\n', encoding="utf-8")
        git("add", "-A", cwd=self.seed)
        git("commit", "-q", "-m", "initial", cwd=self.seed)
        git("checkout", "-q", "-b", BRANCH, cwd=self.seed)
        (self.seed / "src" / "feature.py").write_text("FEATURE = True\n", encoding="utf-8")
        git("add", "-A", cwd=self.seed)
        git("commit", "-q", "-m", f"{RUN}: task 1", cwd=self.seed)
        git("checkout", "-q", "main", cwd=self.seed)
        self.origin = self.tmp / "origin.git"
        git("clone", "-q", "--bare", str(self.seed), str(self.origin), cwd=self.tmp)
        git("remote", "add", "origin", str(self.origin), cwd=self.seed)
        self.head_before = git("rev-parse", BRANCH, cwd=self.origin)

    def deps(self, **over) -> r.Deps:
        async def product(conn, run_id):
            return (str(self.origin), "main", BRANCH)
        return super().deps(product=product, **over)

    def advance_main(self, path="docs/notes.md", content="notes\n"):
        p = self.seed / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        git("add", "-A", cwd=self.seed)
        git("commit", "-q", "-m", "someone else's work on main", cwd=self.seed)
        git("push", "-q", "origin", "main", cwd=self.seed)
        return git("rev-parse", "main", cwd=self.origin)

    def run_it(self, deps=None, force=False):
        self.conn = FakeConn()
        return asyncio.run(r.babysit_run(self.conn, RUN, "ec2", deps or self.deps(), force=force))

    def test_up_to_date_does_nothing(self):
        res = self.run_it()
        self.assertEqual(res["outcome"], "up_to_date")
        self.assertEqual(self.calls, [])
        self.assertEqual(git("rev-parse", BRANCH, cwd=self.origin), self.head_before)

    def test_base_moves_ahead_branch_is_updated_and_regated(self):
        main = self.advance_main()
        res = self.run_it()
        self.assertEqual(res["outcome"], "updated", res)
        self.assertEqual(res["gate"], "green")
        head = git("rev-parse", BRANCH, cwd=self.origin)
        self.assertNotEqual(head, self.head_before)
        parents = git("log", "-1", "--format=%P", head, cwd=self.origin).split()
        self.assertEqual(sorted(parents), sorted([self.head_before, main]))     # a real merge commit
        self.assertIn("Lantern-Agent: babysitter", git("log", "-1", "--format=%B", head, cwd=self.origin))
        self.assertEqual(git("rev-parse", "main", cwd=self.origin), main)          # the base is untouched
        self.assertEqual(self.calls, [])                                           # no agent turn spent
        gate_md = (self.rd / "03-coding" / "babysit" / "regate-1.md").read_text(encoding="utf-8")
        self.assertIn("GREEN", gate_md)
        self.assertIn("test -f README.md", (self.rd / "03-coding" / "babysit" / "regate-1.json").read_text(encoding="utf-8"))
        self.assertIn("branch_updated", [e[1] for e in self.events])
        self.assertTrue(self.conn.statements("INSERT INTO stage_executions"))
        self.assertEqual(self.conn.statements("INSERT INTO stage_executions")[0][1][1], r.REGATE_STAGE)
        self.assertEqual(r.read_babysit_state(RUN)["outcome"], "updated")
        self.assertEqual(self.run_it()["outcome"], "up_to_date")                  # idempotent

    def test_conflict_stops_with_the_file_list_and_an_alarm(self):
        self.advance_main("src/app.py", "VALUE = 2\n")
        git("checkout", "-q", BRANCH, cwd=self.seed)
        (self.seed / "src" / "app.py").write_text("VALUE = 3\n", encoding="utf-8")
        git("commit", "-q", "-am", f"{RUN}: change value", cwd=self.seed)
        git("push", "-q", "origin", BRANCH, cwd=self.seed)
        git("checkout", "-q", "main", cwd=self.seed)
        branch_head = git("rev-parse", BRANCH, cwd=self.origin)
        res = self.run_it()
        self.assertEqual(res["outcome"], "conflict")
        self.assertEqual(res["files"], ["src/app.py"])
        report = (self.rd / "03-coding" / "merge-conflict.md").read_text(encoding="utf-8")
        self.assertIn("`src/app.py`", report)
        self.assertIn("never resolves conflicts", report)
        self.assertEqual(len(self.alarms), 1)
        self.assertIn("src/app.py", self.alarms[0])
        self.assertIn("merge_conflict", [e[1] for e in self.events])
        self.assertEqual(git("rev-parse", BRANCH, cwd=self.origin), branch_head)   # nothing pushed
        self.assertEqual(self.calls, [])
        # stays stopped at this base; --force retries; a moved base retries
        self.assertEqual(self.run_it()["outcome"], "waiting_for_base")
        self.assertEqual(self.run_it(force=True)["outcome"], "conflict")
        self.advance_main("docs/more.md")
        self.assertEqual(self.run_it()["outcome"], "conflict")

    def test_red_regate_spends_one_fix_execution(self):
        self.advance_main("lantern.toml", '[quality]\ntest = "test -f FIXED"\n')
        blocks = []

        async def execute(conn, run_id, stage, runner):
            self.calls.append(("execute", stage))
            self.assertEqual(stage, r.FIX_STAGE)
            st = r.read_state(run_id)
            self.assertEqual(st["fix"]["source"], "regate")
            blocks.append(r.task_block(run_id, r.FIX_STAGE))
            # the fix execution, as the sandbox + publish would leave it: a commit on the branch
            co = self.tmp / "fixco"
            git("clone", "-q", "--branch", BRANCH, str(self.origin), str(co), cwd=self.tmp)
            git("config", "user.name", "bot", cwd=co)
            git("config", "user.email", "bot@example.invalid", cwd=co)
            (co / "FIXED").write_text("", encoding="utf-8")
            git("add", "-A", cwd=co)
            git("commit", "-q", "-m", f"{RUN}: fix after merge", cwd=co)
            git("push", "-q", "origin", BRANCH, cwd=co)

        res = self.run_it(self.deps(execute=execute))
        self.assertEqual(res["outcome"], "fixed", res)
        self.assertEqual(self.calls, [("execute", r.FIX_STAGE), ("publish",)])
        self.assertIn("test -f FIXED", blocks[0])
        self.assertIn("merged branch is red", blocks[0])
        self.assertIn("regate_red", [e[1] for e in self.events])
        self.assertIn("branch_updated", [e[1] for e in self.events])
        self.assertTrue(git("merge-base", "--is-ancestor", "main", BRANCH, cwd=self.origin) == "")
        self.assertEqual(self.alarms, [])
        self.assertEqual(self.conn.statements("UPDATE stage_executions SET status = $1")[0][1][0], "failed")

    def test_red_regate_with_a_failing_fix_alarms_and_waits(self):
        base = self.advance_main("lantern.toml", '[quality]\ntest = "exit 1"\n')

        async def execute(conn, run_id, stage, runner):
            self.calls.append(("execute", stage))
            raise RuntimeError("quality gate RED after 3 fix round(s)")

        res = self.run_it(self.deps(execute=execute))
        self.assertEqual(res["outcome"], "failed")
        self.assertEqual(len(self.alarms), 1)
        self.assertIn("RED", self.alarms[0])
        self.assertEqual(r.read_babysit_state(RUN)["base_sha"], base)
        self.assertEqual(self.conn.statements("SET status = 'failed'")[-1][1][1:], (RUN, r.FIX_STAGE, "terminal"))
        # the merge commit IS on the branch (a human sees the truth): the next pass finds the
        # branch up to date and spends nothing more until the base moves again
        self.assertEqual(git("merge-base", "--is-ancestor", "main", BRANCH, cwd=self.origin), "")
        self.assertEqual(self.run_it(self.deps(execute=execute))["outcome"], "up_to_date")
        self.assertEqual(len(self.alarms), 0)

    def test_merged_branch_is_recorded_and_left_alone(self):
        git("merge", "-q", "--no-ff", "-m", "merge by a human", BRANCH, cwd=self.seed)
        git("push", "-q", "origin", "main", cwd=self.seed)
        res = self.run_it()
        self.assertEqual(res["outcome"], "merged")
        self.assertEqual(res["via"], "git")
        self.assertIn("branch_merged", [e[1] for e in self.events])
        self.assertEqual(self.calls, [])

    def test_github_merge_detection_prefers_the_api(self):
        (self.rd / "03-coding" / "handoff.json").write_text(
            json.dumps(dict(self.handoff, pr_number=12)), encoding="utf-8")
        asked = []

        def gh_api(method, path, data=None):
            asked.append(path)
            return 200, {"merged": True, "state": "closed", "merge_commit_sha": "m" * 40}
        ms = r.merged_status(self.deps(gh_api=gh_api), "https://github.com/o/n.git", self.origin,
                             "main", BRANCH, r.load_handoff(RUN))
        self.assertEqual(asked, ["/repos/o/n/pulls/12"])
        self.assertTrue(ms["merged"])
        self.assertEqual(ms["via"], "github")
        closed = r.merged_status(self.deps(gh_api=lambda m, p, d=None: (200, {"merged": False, "state": "closed"})),
                                 "https://github.com/o/n", self.origin, "main", BRANCH, r.load_handoff(RUN))
        self.assertFalse(closed["merged"])
        self.assertTrue(closed["closed"])
        # API trouble degrades to git ancestry, never raises
        ms = r.merged_status(self.deps(gh_api=lambda m, p, d=None: (500, {})), "https://github.com/o/n",
                             self.origin, "main", BRANCH, r.load_handoff(RUN))
        self.assertEqual(ms["via"], "git")

    def test_regate_local_and_the_docker_command(self):
        gate = r.regate_local(self.seed, RUN, "k")
        self.assertTrue(gate["passed"])
        self.assertEqual(gate["stage"], r.REGATE_STAGE)
        self.assertEqual(gate["configured"], ["test"])
        cmd = r.regate_docker_cmd(self.deps(executor="docker", repo_root=f.REPO), self.origin, "abc", RUN, f"{RUN}:{r.REGATE_STAGE}:2")
        self.assertEqual(cmd[:2], ["docker", "run"])
        self.assertIn("--entrypoint", cmd)
        self.assertEqual(cmd[cmd.index("--entrypoint") + 1], "bash")
        self.assertIn(f"{self.origin}:/product-src.git:ro", cmd)
        self.assertIn(f"{f.REPO}:/repo-src:ro", cmd)
        self.assertIn("review.py regate-local", cmd[-1])
        self.assertIn("checkout --quiet abc", cmd[-1])
        self.assertIn("--user", cmd)
        line = r.REGATE_MARKER + json.dumps(gate)
        self.assertEqual(r.parse_regate_line("noise\n" + line + "\n"), gate)
        self.assertIsNone(r.parse_regate_line("nothing here"))


# ── knobs ────────────────────────────────────────────────────────────────────

class CheckoutReuse(unittest.TestCase):
    """The bug the first live review round found (2026-09-08): a run's product checkout is
    re-cloned per stage, and after the CODING stage it holds git objects written 0444. The
    old `shutil.rmtree(..., ignore_errors=True)` left them on Windows, so the next stage's
    clone died with "already exists and is not an empty directory" — the review execution,
    and equally stage 4+ of any auto run on an in-process runner. Tested here because the
    review loop is what exposed it; the fix lives in pipeline.product_checkout."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="reuse-"))

    def tearDown(self):
        r.force_rmtree(self.tmp)

    def test_force_rmtree_removes_read_only_files(self):
        d = self.tmp / "tree" / "deep"
        d.mkdir(parents=True)
        ro = d / "object"
        ro.write_text("x", encoding="utf-8")
        os.chmod(ro, stat.S_IREAD)
        shutil.rmtree(self.tmp / "tree", ignore_errors=True)          # what the old code did
        if ro.exists():                                               # Windows: still there
            r.force_rmtree(self.tmp / "tree")
        self.assertFalse((self.tmp / "tree").exists())

    def test_product_checkout_can_be_recreated_after_a_commit(self):
        os.environ.setdefault("LANTERN_DATABASE_URL", "postgresql+asyncpg://lantern:none@localhost:5432/lantern")
        import pipeline as p
        seed = self.tmp / "seed"
        seed.mkdir()
        git("init", "-q", "-b", "main", cwd=seed)
        git("config", "user.name", "t", cwd=seed)
        git("config", "user.email", "t@example.invalid", cwd=seed)
        (seed / "app.py").write_text("V = 1\n", encoding="utf-8")
        git("add", "-A", cwd=seed)
        git("commit", "-q", "-m", "seed", cwd=seed)
        mirrors, run = self.tmp / "mirrors", "feat-20260908-reuse"
        with mock.patch.object(p, "PRODUCT_MIRROR_DIR", mirrors):
            co = p.product_checkout(str(seed), "main", run)
            # the coding stage: a commit in the checkout writes read-only loose objects
            git("config", "user.name", "bot", cwd=co)
            git("config", "user.email", "bot@example.invalid", cwd=co)
            git("checkout", "-q", "-b", "feat/20260908-reuse", cwd=co)
            (co / "new.py").write_text("NEW = 2\n", encoding="utf-8")
            git("add", "-A", cwd=co)
            git("commit", "-q", "-m", "work", cwd=co)
            self.assertTrue([f for f in (co / ".git" / "objects").rglob("*") if f.is_file()])
            again = p.product_checkout(str(seed), "main", run)        # the next stage
        self.assertEqual(again, co)
        self.assertTrue((again / "app.py").is_file())
        self.assertFalse((again / "new.py").exists())                 # a fresh tree, as designed


class NotBuilders(Base):
    """D18 and D19 both name executions `03-coding.<x>`, and D18 reads that tail as a
    BUILDER name. Without a reservation a fix execution would be put on a `--fix` branch
    nobody created, its handoff would land under builders/fix/, and a review execution
    in a container would read the base instead of the run's branch. Found while merging
    the two branches, so the guard is tested from this side."""

    def test_review_sub_stages_are_not_builder_names(self):
        import builders as b
        for stage in (r.REVIEW_STAGE, r.FIX_STAGE, r.REGATE_STAGE):
            self.assertEqual(f.builder_of(stage), "", stage)
            self.assertEqual(b.branch_for(BRANCH, stage), BRANCH, stage)
            self.assertEqual(f.exec_dir("03-coding", f.builder_of(stage)), "03-coding")
        self.assertEqual(f.builder_of("03-coding.api"), "api")          # a real builder still is one
        self.assertEqual(b.branch_for(BRANCH, "03-coding.api"), f"{BRANCH}--api")
        self.assertEqual(f.builder_of("03-coding.integrate"), "integrate")

    def test_a_plan_cannot_claim_them(self):
        d = self.rd / "02-pre-coding"
        d.mkdir(parents=True, exist_ok=True)
        (d / "task-plan.md").write_text("# plan\n", encoding="utf-8")
        for name in ("review", "fix", "regate"):
            (d / "plan.json").write_text(json.dumps({
                "kind": "plan", "run_id": RUN,
                "tasks": [{"id": 1, "title": "t", "hitl": False, "criteria": []}],
                "write_scope": ["src/**"], "schema_changes": False, "hitl_required": False,
                "builders": [{"name": name, "write_scope": ["src/**"], "tasks": [1], "criteria": []}],
            }), encoding="utf-8")
            probs = "\n".join(f.check_envelope(RUN, "02-pre-coding"))
            self.assertIn(f"'{name}' is reserved for the review loop", probs)


class Knobs(unittest.TestCase):
    def test_rounds_and_cadence_env(self):
        with mock.patch.dict(os.environ, {"LANTERN_REVIEW_ROUNDS": "3", "LANTERN_BABYSIT_MINUTES": "0"}):
            self.assertEqual(r.review_rounds(), 3)
            self.assertEqual(r.babysit_minutes(), 1)                 # floor
        with mock.patch.dict(os.environ, {"LANTERN_REVIEW_ROUNDS": "nope"}):
            self.assertEqual(r.review_rounds(), r.REVIEW_ROUNDS_DEFAULT)
        with mock.patch.dict(os.environ, {"LANTERN_REVIEW_ROUNDS": "-2"}):
            self.assertEqual(r.review_rounds(), 0)

    def test_babysit_due_once_per_interval(self):
        with mock.patch.dict(os.environ, {"LANTERN_BABYSIT_MINUTES": "30"}):
            r._last_tick = 0.0
            self.assertTrue(r.babysit_due(now=1000.0))
            self.assertFalse(r.babysit_due(now=1000.0 + 29 * 60))
            self.assertTrue(r.babysit_due(now=1000.0 + 31 * 60))
        r._last_tick = 0.0


# ── 5. wiring ────────────────────────────────────────────────────────────────

class Wiring(Base):
    def test_stage_maps_and_the_task_block_hook(self):
        os.environ.setdefault("LANTERN_DATABASE_URL", "postgresql+asyncpg://lantern:none@localhost:5432/lantern")
        import orchestrator as o
        import pipeline as p
        self.assertEqual(o.ROLE_FOR_STAGE[r.REVIEW_STAGE], "reviewer")
        self.assertEqual(o.ROLE_FOR_STAGE[r.FIX_STAGE], "coding")
        self.assertEqual(p.STAGE_DIR[r.REVIEW_STAGE], "03-coding")
        self.assertEqual(p.STAGE_DIR[r.FIX_STAGE], "03-coding")
        self.assertNotIn(r.REVIEW_STAGE, p.STAGE_INDEX)              # never a pipeline step of its own
        self.assertEqual(o.tier_for("reviewer"), "reasoning")
        self.assertTrue((o.REPO / "agents" / "reviewer" / "charter.md").is_file())
        self.assertIn(o.MEMORY_MARKER, (o.REPO / "agents" / "reviewer" / "memory.md").read_text(encoding="utf-8"))
        # the coding role's fix execution sees the must_fix list in its task block
        seed = self.tmp / "p"
        seed.mkdir()
        git("init", "-q", cwd=seed)
        write_review(review_doc(1, "request_changes", [finding("R-1", summary="the bug")], ["R-1"]))
        r.write_state(RUN, phase="fix", round=1, max_rounds=2, history=[],
                      fix={"source": "review", "round": 1, "must_fix": ["R-1"]})
        backup = o.REPO
        o.REPO = f.REPO
        try:
            with mock.patch.dict(os.environ, {"LANTERN_PRODUCT_DIR": str(seed)}):
                block = o.product_task_block(RUN, r.FIX_STAGE)
                plain = o.product_task_block(RUN, "03-coding")
        finally:
            o.REPO = backup
        self.assertIn("R-1", block)
        self.assertIn("the bug", block)
        self.assertNotIn("must-fix list", plain)


if __name__ == "__main__":
    unittest.main(verbosity=2)
