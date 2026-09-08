"""Proof that parallel scoped builders (D18) partition the work and re-assemble it.

    .venv/Scripts/python test_builders.py      (no database, no Azure, real git)

Stage 3 with a `builders` list is the first place two agents write the same repository
for the same run, so the properties below are the ones a bad split or a lying builder
could break:

1. **The plan declares a partition, and code checks it is one.** Unique branch-safe
   names, every task assigned exactly once, no glob claimed twice — a plan that fails
   these never reaches a builder.
2. **Each builder is confined.** LANTERN_BUILDER narrows the write scope to that
   builder's globs, its report/gate/handoff live in its own subdirectory, and the HOST
   holds its handoff to ITS scope even though the host has no LANTERN_BUILDER set.
3. **The host merges; a conflict fails the stage.** Two bundles land in the mirror and
   fan into one run branch in plan order. When two builders really did touch one file,
   the stage fails with the file list instead of asking a model to resolve it.
4. **Parallelism is bounded.** Batches never exceed the cap, and the cap can never
   exceed the executor's own concurrency.
5. **Without builders, nothing changes.** run_coding is a pass-through.
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("LANTERN_DATABASE_URL",
                      "postgresql+asyncpg://lantern:none@localhost:5432/lantern")

import factory  # noqa: E402
import orchestrator as o  # noqa: E402
import pipeline as p  # noqa: E402
import builders as b  # noqa: E402

p.GIT_TOKEN = ""          # never let a real token near these paths
RUN = "feat-20260908-builders-proof"
WORK = "feat/20260908-builders-proof"


def git(*args, cwd: Path) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


STORY = {
    "kind": "story", "run_id": RUN, "title": "Saved items",
    "user_story": "As a user I want to save items so that I can find them later.",
    "acceptance_criteria": [
        {"id": "AC-1", "text": "A user can save an item.", "edge_cases": []},
        {"id": "AC-2", "text": "The docs describe saving.", "edge_cases": []},
    ],
    "non_goals": [],
}

PLAN = {
    "kind": "plan", "run_id": RUN,
    "tasks": [{"id": 1, "title": "save endpoint", "size": "S", "hitl": False, "criteria": ["AC-1"]},
              {"id": 2, "title": "document saving", "size": "XS", "hitl": False, "criteria": ["AC-2"]}],
    "write_scope": ["src/**", "docs/**"],
    "schema_changes": False, "hitl_required": False, "deferred_criteria": [],
    "builders": [
        {"name": "api", "write_scope": ["src/**"], "tasks": [1], "criteria": ["AC-1"]},
        {"name": "docs", "write_scope": ["docs/**"], "tasks": [2], "criteria": ["AC-2"]},
    ],
}

CODING_ENV = ("LANTERN_PRODUCT_DIR", "LANTERN_PRODUCT_WRITABLE", "LANTERN_CODING_BRANCH",
              "LANTERN_CODING_START_SHA", "LANTERN_PRODUCT_BRANCH", "LANTERN_BUILDER",
              "LANTERN_BUILDER_PARALLELISM")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="builders-"))
        self.saved_env = {k: os.environ.get(k) for k in CODING_ENV}
        for k in CODING_ENV:
            os.environ.pop(k, None)
        self.repo_backup, self.o_backup = factory.REPO, o.REPO
        factory.REPO = o.REPO = self.tmp / "lantern"
        self.rd = factory.REPO / "workflow" / "runs" / RUN
        (self.rd / "02-pre-coding").mkdir(parents=True)

    def tearDown(self):
        factory.REPO, o.REPO = self.repo_backup, self.o_backup
        for k, v in self.saved_env.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def plan(self, **over) -> dict:
        data = json.loads(json.dumps(PLAN))
        data.update(over)
        self.write(self.rd / "02-pre-coding" / "plan.json", data)
        (self.rd / "02-pre-coding" / "task-plan.md").write_text("# plan\n", encoding="utf-8")
        return data

    def story(self) -> None:
        self.write(self.rd / "00-story" / "story.json", STORY)
        (self.rd / "00-story" / "story.md").write_text("# story\n", encoding="utf-8")


# ── 1. the plan declares a partition ─────────────────────────────────────────

class PlanValidation(Base):
    def problems(self, **over) -> str:
        self.story()
        self.plan(**over)
        return "\n".join(factory.check_envelope(RUN, "02-pre-coding"))

    def test_a_good_split_validates(self):
        self.assertEqual(self.problems(), "")

    def test_no_builders_key_is_still_valid(self):
        self.story()
        data = json.loads(json.dumps(PLAN))
        data.pop("builders")
        self.write(self.rd / "02-pre-coding" / "plan.json", data)
        (self.rd / "02-pre-coding" / "task-plan.md").write_text("# plan\n", encoding="utf-8")
        self.assertEqual(factory.check_envelope(RUN, "02-pre-coding"), [])
        self.assertEqual(factory.plan_builders(RUN), [])

    def test_a_task_built_twice_is_refused(self):
        probs = self.problems(builders=[
            {"name": "api", "write_scope": ["src/**"], "tasks": [1, 2], "criteria": ["AC-1"]},
            {"name": "docs", "write_scope": ["docs/**"], "tasks": [2], "criteria": ["AC-2"]}])
        self.assertIn("task 2 is assigned to both 'api' and 'docs'", probs)

    def test_a_task_nobody_builds_is_refused(self):
        probs = self.problems(builders=[
            {"name": "api", "write_scope": ["src/**"], "tasks": [1], "criteria": ["AC-1"]}])
        self.assertIn("tasks assigned to no builder: 2", probs)

    def test_an_unknown_task_id_is_refused(self):
        probs = self.problems(builders=[
            {"name": "api", "write_scope": ["src/**"], "tasks": [1], "criteria": ["AC-1"]},
            {"name": "docs", "write_scope": ["docs/**"], "tasks": [2, 9], "criteria": ["AC-2"]}])
        self.assertIn("builders claim task ids the plan does not define: 9", probs)

    def test_an_overlapping_glob_is_refused(self):
        probs = self.problems(builders=[
            {"name": "api", "write_scope": ["src/**", "docs/**"], "tasks": [1], "criteria": ["AC-1"]},
            {"name": "docs", "write_scope": ["docs/**"], "tasks": [2], "criteria": ["AC-2"]}])
        self.assertIn("glob 'docs/**' is listed under both 'api' and 'docs'", probs)

    def test_duplicate_and_unsafe_names_are_refused(self):
        probs = self.problems(builders=[
            {"name": "api", "write_scope": ["src/**"], "tasks": [1], "criteria": []},
            {"name": "api", "write_scope": ["docs/**"], "tasks": [2], "criteria": []}])
        self.assertIn("duplicate builder name 'api'", probs)
        probs = self.problems(builders=[
            {"name": "API/back end", "write_scope": ["src/**"], "tasks": [1], "criteria": []},
            {"name": "docs", "write_scope": ["docs/**"], "tasks": [2], "criteria": []}])
        self.assertIn("name must be lowercase letters, digits and single dashes", probs)

    def test_the_integrator_name_is_reserved(self):
        probs = self.problems(builders=[
            {"name": "integrate", "write_scope": ["src/**"], "tasks": [1], "criteria": []},
            {"name": "docs", "write_scope": ["docs/**"], "tasks": [2], "criteria": []}])
        self.assertIn("is reserved for the host's integration execution", probs)

    def test_a_builder_needs_a_scope_and_tasks(self):
        probs = self.problems(builders=[
            {"name": "api", "write_scope": [], "tasks": [], "criteria": []},
            {"name": "docs", "write_scope": ["docs/**"], "tasks": [1, 2], "criteria": []}])
        self.assertIn("api: write_scope must list at least one path glob", probs)
        self.assertIn("api: tasks must list the plan task ids", probs)

    def test_criteria_are_checked_against_the_story(self):
        probs = self.problems(builders=[
            {"name": "api", "write_scope": ["src/**"], "tasks": [1], "criteria": ["AC-9"]},
            {"name": "docs", "write_scope": ["docs/**"], "tasks": [2], "criteria": ["AC-2"]}])
        self.assertIn("api: criteria the story does not define: AC-9", probs)


# ── 2. naming stays inside the D6 push namespace ─────────────────────────────

class Naming(unittest.TestCase):
    def test_stage_keys_map_to_names_and_branches(self):
        self.assertEqual(b.name_for("03-coding.api"), "api")
        self.assertEqual(b.name_for("03-coding"), "")
        self.assertEqual(b.name_for("05-post-coding.validate"), "")
        self.assertEqual(b.stage_key("api"), "03-coding.api")
        self.assertEqual(b.branch_for(WORK, "03-coding.api"), WORK + "--api")
        self.assertEqual(b.branch_for(WORK, "03-coding"), WORK)

    def test_the_integrator_works_on_the_run_branch_itself(self):
        # so _publish_branch still sees exactly ONE handoff for the run's branch
        self.assertEqual(b.branch_for(WORK, "03-coding.integrate"), WORK)

    def test_builder_branches_stay_in_the_pushable_namespace(self):
        self.assertEqual(b.check_branch(WORK + "--api"), WORK + "--api")
        self.assertTrue((WORK + "--api").startswith(o.CODING_BRANCH_PREFIXES))
        self.assertTrue(b.branch_for("fix/20260908-x", "03-coding.api")
                        .startswith(o.CODING_BRANCH_PREFIXES))
        with self.assertRaises(b.BuilderError) as e:
            b.check_branch("develop--api")
        self.assertIn("outside the pushable namespace", str(e.exception))

    def test_the_builder_comes_from_the_stage_key_not_the_environment(self):
        # THE regression: LANTERN_BUILDER is set only for the agent's turn. The
        # in-process path clears it before check_postconditions runs, and the docker
        # host never sets it at all — so a check that reads the env looks in the stage
        # directory and fails a builder that did everything right. Observed on the
        # first live run of this feature (2026-09-08).
        saved = os.environ.pop("LANTERN_BUILDER", None)
        try:
            self.assertEqual(factory.builder_of("03-coding.api"), "api")
            self.assertEqual(factory.builder_of("03-coding.integrate"), "integrate")
            self.assertEqual(factory.builder_of("03-coding"), "")
            self.assertEqual(factory.builder_of("05-post-coding.validate"), "")
            self.assertEqual(factory.current_builder(), "")
            self.assertEqual(
                factory.exec_dir("03-coding", factory.builder_of("03-coding.api")),
                "03-coding/builders/api")
            self.assertEqual(
                factory.exec_dir("03-coding", factory.builder_of("03-coding.integrate")),
                "03-coding")
        finally:
            if saved is not None:
                os.environ["LANTERN_BUILDER"] = saved

    def test_every_builder_stage_key_routes_to_the_coding_role(self):
        for key in ("03-coding.api", "03-coding.docs-and-tests", "03-coding.integrate"):
            self.assertEqual(o.role_for_stage(key), "coding")
        self.assertEqual(o.role_for_stage("04-qa-dev"), "qa-dev")
        self.assertIsNone(o.role_for_stage("99-nonsense"))


# ── 3. LANTERN_BUILDER narrows the write scope ───────────────────────────────

class BuilderScope(Base):
    def test_scope_resolves_per_builder_and_falls_back_to_the_plan(self):
        self.plan()
        self.assertEqual(factory.write_scope(RUN), ["src/**", "docs/**"])   # no builder set
        os.environ["LANTERN_BUILDER"] = "api"
        self.assertEqual(factory.write_scope(RUN), ["src/**"])
        self.assertEqual(factory.check_write_scope(RUN, ["src/api/save.py"]), [])
        probs = factory.check_write_scope(RUN, ["docs/guide.md"])
        self.assertIn("builder 'api's write scope", probs[0])
        self.assertIn("docs/guide.md", probs[0])
        os.environ["LANTERN_BUILDER"] = "docs"
        self.assertEqual(factory.write_scope(RUN), ["docs/**"])
        os.environ["LANTERN_BUILDER"] = "not-in-the-plan"
        self.assertEqual(factory.write_scope(RUN), ["src/**", "docs/**"])

    def test_the_integrator_gets_the_union_of_every_builders_scope(self):
        self.plan()
        os.environ["LANTERN_BUILDER"] = "integrate"
        self.assertEqual(factory.write_scope(RUN), ["docs/**", "src/**"])
        self.assertEqual(factory.check_write_scope(RUN, ["src/a.py", "docs/b.md"]), [])
        self.assertTrue(factory.check_write_scope(RUN, ["infra/c.tf"]))

    def test_a_run_without_builders_is_unaffected_by_the_env(self):
        data = json.loads(json.dumps(PLAN))
        data.pop("builders")
        self.write(self.rd / "02-pre-coding" / "plan.json", data)
        os.environ["LANTERN_BUILDER"] = "api"
        self.assertEqual(factory.write_scope(RUN), ["src/**", "docs/**"])

    def test_the_prompt_tells_a_builder_who_it_is(self):
        self.story()
        self.plan()
        os.environ["LANTERN_BUILDER"] = "api"
        note = factory.coding_gate_note(RUN, self.tmp / "nowhere")
        self.assertIn("you are **`api`**", note)
        self.assertIn("task 1: save endpoint", note)
        self.assertIn("AC-1", note)
        self.assertIn("`docs`", note)                     # its sibling, building in parallel
        self.assertIn("03-coding/builders/api/", note)
        self.assertIn("`src/**`", note)
        self.assertNotIn("`docs/**`", note)               # not its surface
        os.environ["LANTERN_BUILDER"] = "integrate"
        note = factory.coding_gate_note(RUN, self.tmp / "nowhere")
        self.assertIn("You are the integrator", note)
        self.assertIn("make the merged", note)
        self.assertIn("`docs/**`", note)                  # the union

    def test_no_builder_brief_without_a_split(self):
        self.plan()
        self.assertEqual(factory.builder_brief(RUN), "")
        os.environ["LANTERN_BUILDER"] = "api"
        self.assertIn("one builder of several", factory.builder_brief(RUN))


# ── 4. batching ──────────────────────────────────────────────────────────────

class Batching(unittest.TestCase):
    def setUp(self):
        self.saved = os.environ.get("LANTERN_BUILDER_PARALLELISM")
        os.environ.pop("LANTERN_BUILDER_PARALLELISM", None)

    def tearDown(self):
        os.environ.pop("LANTERN_BUILDER_PARALLELISM", None)
        if self.saved is not None:
            os.environ["LANTERN_BUILDER_PARALLELISM"] = self.saved

    def test_parallelism_defaults_to_two_and_never_exceeds_the_cap(self):
        self.assertEqual(b.parallelism(cap=4), b.PARALLELISM_DEFAULT)
        os.environ["LANTERN_BUILDER_PARALLELISM"] = "5"
        self.assertEqual(b.parallelism(cap=4), 4)          # the executor's cap wins
        self.assertEqual(b.parallelism(cap=1), 1)          # in-process: one at a time
        os.environ["LANTERN_BUILDER_PARALLELISM"] = "0"
        self.assertEqual(b.parallelism(cap=4), 1)
        os.environ["LANTERN_BUILDER_PARALLELISM"] = "banana"
        self.assertEqual(b.parallelism(cap=4), b.PARALLELISM_DEFAULT)

    def test_inprocess_concurrency_is_one_because_env_is_shared(self):
        executor = p.EXECUTOR
        try:
            p.EXECUTOR, p.MAX_CONCURRENCY = "inprocess", 3
            self.assertEqual(b.max_concurrency(), 1)
            p.EXECUTOR, p.MAX_CONCURRENCY = "docker", 3
            self.assertEqual(b.max_concurrency(), 3)
        finally:
            p.EXECUTOR = executor

    def test_batches_split_in_plan_order(self):
        self.assertEqual(b.batches(["a", "b", "c", "d", "e"], 2),
                         [["a", "b"], ["c", "d"], ["e"]])
        self.assertEqual(b.batches(["a", "b"], 1), [["a"], ["b"]])
        self.assertEqual(b.batches(["a", "b"], 0), [["a"], ["b"]])   # never zero

    def test_fan_out_never_exceeds_the_cap(self):
        for size, expected_peak in ((1, 1), (2, 2), (3, 3)):
            live = peak = 0
            order = []

            async def execute(conn, run_id, stage, runner):
                nonlocal live, peak
                live += 1
                peak = max(peak, live)
                order.append(stage)
                await asyncio.sleep(0.02)
                live -= 1

            asyncio.run(b.fan_out(None, RUN, "ec2", ["a", "b", "c", "d", "e"],
                                  execute, size))
            self.assertEqual(peak, expected_peak, f"size={size}")
            self.assertEqual(order[:2] if size > 1 else order[:1],
                             [b.stage_key(n) for n in (["a", "b"] if size > 1 else ["a"])])
            self.assertEqual(len(order), 5)

    def test_one_failed_builder_fails_the_stage(self):
        async def execute(conn, run_id, stage, runner):
            if stage.endswith("boom"):
                raise RuntimeError("quality gate RED")

        with self.assertRaises(b.BuilderError) as e:
            asyncio.run(b.fan_out(None, RUN, "ec2", ["ok", "boom"], execute, 2))
        self.assertIn("builder 'boom' failed", str(e.exception))
        self.assertIn("quality gate RED", str(e.exception))


# ── 5. the real thing: two builders, two bundles, one merged branch ──────────

class Merge(Base):
    def setUp(self):
        super().setUp()
        self.story()
        self.plan()
        seed = self.tmp / "seed"
        seed.mkdir()
        git("init", "-q", "-b", "main", cwd=seed)
        git("config", "user.name", "seed", cwd=seed)
        git("config", "user.email", "seed@example.invalid", cwd=seed)
        (seed / "src").mkdir()
        (seed / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
        (seed / "docs").mkdir()
        (seed / "docs" / "README.md").write_text("# product\n", encoding="utf-8")
        git("add", "-A", cwd=seed)
        git("commit", "-q", "-m", "initial", cwd=seed)
        self.origin = self.tmp / "origin.git"
        git("clone", "-q", "--bare", str(seed), str(self.origin), cwd=self.tmp)

    def build(self, name: str, files: dict[str, str]) -> Path:
        """Run one builder for real: clone its branch, write, commit, finalize_coding."""
        co = self.tmp / f"co-{name}"
        branch = f"{WORK}--{name}"
        git("clone", "-q", "--branch", branch, str(self.origin), str(co), cwd=self.tmp)
        git("config", "user.name", "lantern-bot", cwd=co)
        git("config", "user.email", "bot@example.invalid", cwd=co)
        start = git("rev-parse", "HEAD", cwd=co)
        for rel, text in files.items():
            path = co / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        git("add", "-A", cwd=co)
        git("commit", "-q", "-m", f"{RUN}: {name} — task work", cwd=co)
        os.environ.update({"LANTERN_PRODUCT_DIR": str(co), "LANTERN_PRODUCT_WRITABLE": "1",
                           "LANTERN_CODING_BRANCH": branch, "LANTERN_PRODUCT_BRANCH": "main",
                           "LANTERN_CODING_START_SHA": start, "LANTERN_BUILDER": name})
        # the dispatcher passes the full stage key; the builder comes from it, not env
        problems = o.finalize_coding(RUN, b.stage_key(name))
        self.assertEqual(problems, [], f"{name}: {problems}")
        return co

    def test_two_builders_merge_into_one_run_branch(self):
        mirror, start = b.seed_branches(str(self.origin), "main", WORK, ["api", "docs"])
        self.assertEqual(mirror, self.origin.resolve())
        self.assertEqual(git("rev-parse", f"{WORK}--api", cwd=self.origin), start)

        self.build("api", {"src/save.py": "def save():\n    return True\n"})
        self.build("docs", {"docs/saving.md": "# Saving\n"})

        # Each builder's evidence is in ITS OWN subdirectory — the stage dir is still
        # free for the integrator's single handoff.
        for name in ("api", "docs"):
            d = self.rd / "03-coding" / "builders" / name
            self.assertTrue((d / "handoff.json").is_file(), f"{name} handoff")
            self.assertTrue((d / "branch.bundle").is_file(), f"{name} bundle")
            h = json.loads((d / "handoff.json").read_text(encoding="utf-8"))
            self.assertEqual(h["branch"], f"{WORK}--{name}")
            self.assertEqual(h["builder"], name)
            self.assertEqual(h["bundle"],
                             f"workflow/runs/{RUN}/03-coding/builders/{name}/branch.bundle")
        self.assertFalse((self.rd / "03-coding" / "handoff.json").exists())

        # The HOST holds each handoff to THAT builder's scope, with no env of its own.
        os.environ.pop("LANTERN_BUILDER", None)
        self.assertEqual(o.check_coding_handoff(RUN, "03-coding", self.origin, builder="api"), [])
        self.assertEqual(o.check_coding_handoff(RUN, "03-coding", self.origin, builder="docs"), [])

        record = b.merge(RUN, str(self.origin), "main", WORK, ["api", "docs"], start)

        head = git("rev-parse", WORK, cwd=self.origin)
        self.assertEqual(record["head_sha"], head)
        self.assertEqual([x["name"] for x in record["builders"]], ["api", "docs"])
        for name in ("api", "docs"):
            sha = git("rev-parse", f"{WORK}--{name}", cwd=self.origin)
            self.assertEqual(subprocess.run(
                ["git", "merge-base", "--is-ancestor", sha, head], cwd=self.origin,
                capture_output=True).returncode, 0, f"{name} is not in the merged branch")
        tree = git("ls-tree", "-r", "--name-only", WORK, cwd=self.origin).split()
        self.assertIn("src/save.py", tree)
        self.assertIn("docs/saving.md", tree)
        self.assertTrue((self.rd / "03-coding" / "builders.json").is_file())
        self.assertTrue((self.rd / "03-coding" / "builders.md").is_file())
        self.assertEqual(factory.merge_record(RUN)["start_sha"], start)
        # --no-ff, so each builder's work stays one readable arc a reviewer can follow
        self.assertEqual(len(git("rev-list", "--merges", f"{start}..{WORK}",
                                 cwd=self.origin).split()), 2)
        subjects = git("log", "--format=%s", f"{start}..{WORK}", cwd=self.origin)
        self.assertIn(f"{RUN}: merge builder api", subjects)
        self.assertIn(f"{RUN}: merge builder docs", subjects)

    def test_the_whole_per_builder_path_works_with_no_environment(self):
        """The postcondition path, exactly as the host runs it: env cleared first."""
        b.seed_branches(str(self.origin), "main", WORK, ["api", "docs"])
        co = self.build("api", {"src/save.py": "def save():\n    return True\n"})
        stage = b.stage_key("api")
        for var in CODING_ENV:                       # the host has none of these
            os.environ.pop(var, None)

        gate = factory.run_quality_gate(RUN, stage, co, f"{RUN}:{stage}:1", 0)
        self.assertTrue(gate["passed"], gate["results"])
        self.assertEqual(gate["builder"], "api")
        self.assertTrue((self.rd / "03-coding" / "builders" / "api" / "gate.json").is_file())
        self.assertFalse((self.rd / "03-coding" / "gate.json").exists())
        self.assertEqual(
            factory.check_quality_gate(RUN, "03-coding", f"{RUN}:{stage}:1", "api"), [])
        # and finalize, called with the stage key, still lands in the builder's subdir
        os.environ.update({"LANTERN_PRODUCT_DIR": str(co), "LANTERN_PRODUCT_WRITABLE": "1",
                           "LANTERN_CODING_BRANCH": f"{WORK}--api",
                           "LANTERN_PRODUCT_BRANCH": "main"})
        os.environ.pop("LANTERN_BUILDER", None)
        self.assertEqual(o.finalize_coding(RUN, stage), [])
        h = json.loads((self.rd / "03-coding" / "builders" / "api" / "handoff.json")
                       .read_text(encoding="utf-8"))
        self.assertEqual(h["builder"], "api")
        os.environ.pop("LANTERN_PRODUCT_WRITABLE", None)
        self.assertEqual(
            o.check_coding_handoff(RUN, "03-coding", self.origin, factory.builder_of(stage)), [])

    def test_a_conflict_fails_the_stage_with_the_file_list(self):
        # Non-identical globs can still overlap as SETS ('src/**' ⊃ 'src/api/**'), which
        # the plan check cannot decide — so the merge is the second line of defence.
        self.plan(write_scope=["src/**"], builders=[
            {"name": "api", "write_scope": ["src/**"], "tasks": [1], "criteria": ["AC-1"]},
            {"name": "docs", "write_scope": ["src/api/**"], "tasks": [2], "criteria": ["AC-2"]}])
        _, start = b.seed_branches(str(self.origin), "main", WORK, ["api", "docs"])
        self.build("api", {"src/api/shared.py": "MODE = 'api'\n"})
        self.build("docs", {"src/api/shared.py": "MODE = 'docs'\n"})
        os.environ.pop("LANTERN_BUILDER", None)

        with self.assertRaises(b.MergeConflict) as e:
            b.merge(RUN, str(self.origin), "main", WORK, ["api", "docs"], start)
        msg = str(e.exception)
        self.assertIn("src/api/shared.py", msg)
        self.assertEqual(e.exception.files, ["src/api/shared.py"])
        self.assertEqual(e.exception.builder, "docs")     # the one that could not land
        self.assertIn(f"pipeline.py rework {RUN} --to 02-pre-coding", msg)
        self.assertIn("the split in 02-pre-coding/plan.json is wrong", msg)

    def test_a_builder_writing_outside_its_scope_is_refused(self):
        b.seed_branches(str(self.origin), "main", WORK, ["api", "docs"])
        self.build("api", {"src/save.py": "x = 1\n", "docs/sneaky.md": "not mine\n"})
        os.environ.pop("LANTERN_BUILDER", None)
        problems = o.check_coding_handoff(RUN, "03-coding", self.origin, builder="api")
        self.assertTrue(problems)
        self.assertIn("docs/sneaky.md", problems[0])
        # The host has no LANTERN_BUILDER, so the message must still name whose scope
        # it was: 'the plan's' would send a reviewer to widen the wrong list.
        self.assertIn("builder 'api's write scope", problems[0])
        self.assertIn("src/**", problems[0])

    def test_the_merge_refuses_a_handoff_that_is_not_the_builders_branch(self):
        _, start = b.seed_branches(str(self.origin), "main", WORK, ["api", "docs"])
        self.build("api", {"src/save.py": "x = 1\n"})
        self.build("docs", {"docs/saving.md": "# hi\n"})
        os.environ.pop("LANTERN_BUILDER", None)
        hf = self.rd / "03-coding" / "builders" / "api" / "handoff.json"
        h = json.loads(hf.read_text(encoding="utf-8"))
        hf.write_text(json.dumps({**h, "branch": WORK}), encoding="utf-8")
        with self.assertRaises(b.BuilderError) as e:
            b.merge(RUN, str(self.origin), "main", WORK, ["api", "docs"], start)
        self.assertIn("expected", str(e.exception))

    def test_the_published_branch_must_contain_every_builder(self):
        _, start = b.seed_branches(str(self.origin), "main", WORK, ["api", "docs"])
        self.build("api", {"src/save.py": "x = 1\n"})
        self.build("docs", {"docs/saving.md": "# hi\n"})
        os.environ.pop("LANTERN_BUILDER", None)
        b.merge(RUN, str(self.origin), "main", WORK, ["api", "docs"], start)

        # The integrator's handoff, forged to point at a commit that predates the merge:
        # the ancestry check is what stops a third of the feature vanishing into the PR.
        sdir = self.rd / "03-coding"
        api = json.loads((sdir / "builders" / "api" / "handoff.json").read_text(encoding="utf-8"))
        sdir.joinpath("handoff.json").write_text(json.dumps(
            {**api, "branch": WORK, "head_sha": start, "builder": None}), encoding="utf-8")
        shutil.copy(sdir / "builders" / "api" / "branch.bundle", sdir / "branch.bundle")
        problems = o.check_coding_handoff(RUN, "03-coding", self.origin)
        self.assertTrue(any("is NOT an ancestor" in x for x in problems), problems)
        self.assertTrue(any("api" in x for x in problems))

    def test_a_head_the_repo_cannot_see_is_not_reported_as_a_dropped_builder(self):
        """'I cannot see that commit' is not 'that commit is wrong'.

        _publish_branch checks the handoff against the MIRROR before landing the
        bundle, so the integrator's head is not there yet. Asking anyway reported every
        builder as missing and failed a perfectly good merge — seen on the first live
        two-builder run (2026-09-08).
        """
        _, start = b.seed_branches(str(self.origin), "main", WORK, ["api", "docs"])
        self.build("api", {"src/save.py": "x = 1\n"})
        self.build("docs", {"docs/saving.md": "# hi\n"})
        os.environ.pop("LANTERN_BUILDER", None)
        b.merge(RUN, str(self.origin), "main", WORK, ["api", "docs"], start)

        # An integrator handoff whose head exists only in its own (gone) checkout.
        sdir = self.rd / "03-coding"
        api = json.loads((sdir / "builders" / "api" / "handoff.json").read_text(encoding="utf-8"))
        unseen = "0" * 39 + "1"
        sdir.joinpath("handoff.json").write_text(json.dumps(
            {**api, "branch": WORK, "head_sha": unseen, "builder": None}), encoding="utf-8")
        shutil.copy(sdir / "builders" / "api" / "branch.bundle", sdir / "branch.bundle")
        problems = o.check_coding_handoff(RUN, "03-coding", self.origin)
        self.assertFalse(any("is NOT an ancestor" in x for x in problems), problems)


# ── 6. the checkout the second builder reuses ────────────────────────────────

class CheckoutReuse(Base):
    """Sequential builders check the same run out twice in ONE process.

    git marks objects read-only, so on Windows `shutil.rmtree(..., ignore_errors=True)`
    left the first builder's checkout in place and the second builder's clone died with
    'destination path already exists' — found on the first live run of this feature.
    """

    def test_force_rmtree_removes_a_read_only_git_checkout(self):
        co = self.tmp / "checkout"
        (co / ".git" / "objects").mkdir(parents=True)
        obj = co / ".git" / "objects" / "deadbeef"
        obj.write_text("packed object", encoding="utf-8")
        obj.chmod(0o444)                                  # what git actually does
        (co / "file.py").write_text("x = 1\n", encoding="utf-8")
        p.force_rmtree(co)
        self.assertFalse(co.exists())
        p.force_rmtree(co)                                # absent is not an error

    def test_a_directory_that_survives_is_named_not_swallowed(self):
        seed = self.tmp / "seed"
        seed.mkdir()
        git("init", "-q", "-b", "main", cwd=seed)
        git("config", "user.name", "t", cwd=seed)
        git("config", "user.email", "t@example.invalid", cwd=seed)
        (seed / "a.txt").write_text("a\n", encoding="utf-8")
        git("add", "-A", cwd=seed)
        git("commit", "-q", "-m", "seed", cwd=seed)
        mirror_backup = p.PRODUCT_MIRROR_DIR
        p.PRODUCT_MIRROR_DIR = self.tmp / "mirrors"
        try:
            first = p.product_checkout(str(seed), "main", RUN)
            self.assertTrue((first / "a.txt").is_file())
            for f in first.rglob("*"):                    # make it maximally unremovable
                if f.is_file():
                    f.chmod(0o444)
            second = p.product_checkout(str(seed), "main", RUN)   # the reuse that broke
            self.assertTrue((second / "a.txt").is_file())
            self.assertEqual(first, second)
        finally:
            p.PRODUCT_MIRROR_DIR = mirror_backup


# ── 7. no builders in the plan = today's single builder, untouched ───────────

class PassThrough(Base):
    def test_run_coding_without_builders_calls_execute_once(self):
        data = json.loads(json.dumps(PLAN))
        data.pop("builders")
        self.write(self.rd / "02-pre-coding" / "plan.json", data)
        calls = []

        async def execute(conn, run_id, stage, runner):
            calls.append((run_id, stage, runner))

        out = asyncio.run(b.run_coding(None, RUN, "03-coding", "ec2", execute))
        self.assertEqual(calls, [(RUN, "03-coding", "ec2")])
        self.assertEqual(out, [])

    def test_no_plan_at_all_is_also_a_pass_through(self):
        calls = []

        async def execute(conn, run_id, stage, runner):
            calls.append(stage)

        self.assertEqual(asyncio.run(b.run_coding(None, RUN, "03-coding", "ec2", execute)), [])
        self.assertEqual(calls, ["03-coding"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
