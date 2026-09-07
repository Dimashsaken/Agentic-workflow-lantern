"""Proof that auto-coding (D14) is confined, evidence-based, and credential-free.

    .venv/Scripts/python test_coding_stage.py      (no database, no Azure, real git)

The coding stage is the first fleet stage that WRITES product code, so the properties
below are the ones a lying or confused sandbox could break:

1. **Writability is opt-in per execution.** Without LANTERN_PRODUCT_WRITABLE=1 the
   product tree keeps the read-only contract test_product_access.py proves and
   product_shell refuses to run at all. With it, writes stay inside the product tree
   and `.git/` stays off-limits — and the flag never leaks past the stage.
2. **The shell is scoped.** product_shell runs in the product root, the Azure/DB/GitHub
   secrets are stripped from its environment, and output is truncated, not dumped.
3. **The handoff is evidence, not a claim.** finalize_coding turns commits into a git
   bundle + handoff.json the host can verify; leftovers are committed (flagged), and an
   empty branch fails the stage instead of producing a hollow handoff.
4. **Only the run's branch can ride along.** A bundle carrying any other ref is rejected
   before anything is pushed.
5. **Publishing is verifiable without a network.** _publish_branch lands the bundle in a
   local-path product repo, refuses a mismatched branch, and builds the gate payload;
   the PR body carries the evidence pack.
6. Brief parsing: coding mode, branch naming, GitHub URL parsing.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

FAILURES = []
RUN_ID = "feat-20260907-coding-proof"
BRANCH = "feat/20260907-coding-proof"


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}{'' if cond else '  - ' + str(detail)[:300]}")
    if not cond:
        FAILURES.append(name)


def raises(fn, *a, **kw):
    try:
        fn(*a, **kw)
    except Exception as e:  # noqa: BLE001 — any refusal is a pass; we assert on the refusal
        return e
    return None


def git(*args, cwd: Path) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def make_repos(tmp: Path) -> tuple[Path, Path]:
    """A bare 'origin' with one commit on main, and a clone of it (the sandbox checkout)."""
    seed = tmp / "seed"
    seed.mkdir()
    git("init", "-q", "-b", "main", cwd=seed)
    git("config", "user.name", "seed", cwd=seed)
    git("config", "user.email", "seed@example.invalid", cwd=seed)
    (seed / "README.md").write_text("# product\n", encoding="utf-8")
    (seed / "src").mkdir()
    (seed / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    git("add", "-A", cwd=seed)
    git("commit", "-q", "-m", "initial", cwd=seed)
    origin = tmp / "origin.git"
    git("clone", "-q", "--bare", str(seed), str(origin), cwd=tmp)
    checkout = tmp / "checkout"
    git("clone", "-q", "--branch", "main", str(origin), str(checkout), cwd=tmp)
    return origin, checkout


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="lantern-coding-"))
    origin, checkout = make_repos(tmp)
    fake_repo = tmp / "lantern"                      # stand-in for the Lantern checkout
    (fake_repo / "workflow" / "runs" / RUN_ID / "02-pre-coding").mkdir(parents=True)
    (fake_repo / "workflow" / "runs" / RUN_ID / "brief.md").write_text(
        "# Feature Brief: Coding proof\n\n- **Coding mode:** auto\n", encoding="utf-8")
    (fake_repo / "workflow" / "runs" / RUN_ID / "02-pre-coding" / "task-plan.md").write_text(
        "# plan\n\n1. add a constant\n", encoding="utf-8")

    os.environ["LANTERN_PRODUCT_DIR"] = str(checkout)
    os.environ["LANTERN_PRODUCT_BRANCH"] = "main"
    os.environ["LANTERN_PRODUCT_ORIGIN"] = str(origin)
    os.environ.pop("LANTERN_PRODUCT_WRITABLE", None)
    os.environ.pop("LANTERN_CODING_BRANCH", None)
    os.environ.setdefault("LANTERN_DATABASE_URL",
                          "postgresql+asyncpg://lantern:none@localhost:5432/lantern")
    os.environ.setdefault("GITHUB_LANTERN_BOT_TOKEN", "")

    import orchestrator as o
    import pipeline as p
    o.REPO = fake_repo
    p.REPO = fake_repo
    p.GIT_TOKEN = ""            # never let a real token near these paths

    print("1. writability is opt-in per execution:")
    check("read-only by default", not o.product_writable())
    check("write to product/ refused when read-only", raises(o._writable, "product/src/new.py") is not None)
    e = raises(o._product_shell, "echo hi")
    check("product_shell refuses when read-only", isinstance(e, PermissionError), repr(e))
    check("stage_tools has no shell when read-only",
          all(getattr(t, "name", "") != "product_shell" for t in o.stage_tools("coding", RUN_ID, "03-coding", "k")))
    check("check_stage_inputs wants the approved plan for 03-coding",
          o.check_stage_inputs(RUN_ID, "03-coding") is None)
    (fake_repo / "workflow" / "runs" / RUN_ID / "02-pre-coding" / "task-plan.md").rename(
        fake_repo / "workflow" / "runs" / RUN_ID / "02-pre-coding" / "task-plan.md.bak")
    check("...and refuses without it", "task-plan" in (o.check_stage_inputs(RUN_ID, "03-coding") or ""))
    (fake_repo / "workflow" / "runs" / RUN_ID / "02-pre-coding" / "task-plan.md.bak").rename(
        fake_repo / "workflow" / "runs" / RUN_ID / "02-pre-coding" / "task-plan.md")

    p.prepare_coding_checkout(checkout, BRANCH)
    os.environ["LANTERN_CODING_BRANCH"] = BRANCH
    os.environ["LANTERN_PRODUCT_WRITABLE"] = "1"
    check("checkout is on the run's branch", git("rev-parse", "--abbrev-ref", "HEAD", cwd=checkout) == BRANCH)
    check("commit identity is the bot", git("config", "user.name", cwd=checkout) == p.GIT_AUTHOR_NAME)
    check("writable once the execution says so", o.product_writable())
    check("stage_tools adds the shell when writable",
          any(getattr(t, "name", "") == "product_shell" for t in o.stage_tools("coding", RUN_ID, "03-coding", "k")))
    target = o._writable("product/src/new.py")
    check("product/ write resolves inside the checkout", target.resolve().is_relative_to(checkout.resolve()))
    check("product/.. escape refused", raises(o._writable, "product/../outside.txt") is not None)
    check("product/.git refused", raises(o._writable, "product/.git/config") is not None)
    check("product root itself refused", raises(o._writable, "product") is not None)
    check("Lantern-side rendered views still refused", raises(o._writable, "workflow/RUNBOARD.md") is not None)

    print("2. the shell is scoped:")
    out = o._product_shell("ls")
    check("runs in the product root", "README.md" in out and out.startswith("exit 0"), out[:120])
    os.environ["AZURE_OPENAI_API_KEY"] = "sekret-should-not-leak"
    os.environ["GITHUB_LANTERN_BOT_TOKEN"] = "ghp-should-not-leak"
    out = o._product_shell('echo "${AZURE_OPENAI_API_KEY:-unset}/${GITHUB_LANTERN_BOT_TOKEN:-unset}/${LANTERN_DATABASE_URL:-unset}"')
    check("secrets stripped from the shell env", "unset/unset/unset" in out, out[:160])
    del os.environ["AZURE_OPENAI_API_KEY"]
    os.environ["GITHUB_LANTERN_BOT_TOKEN"] = ""
    out = o._product_shell("head -c 40000 /dev/zero | tr '\\0' x")
    check("long output is truncated, not dumped", "[truncated]" in out and len(out) < 26000, len(out))
    out = o._product_shell("exit 3")
    check("exit code is reported", out.startswith("exit 3"), out[:40])
    check("empty command refused", raises(o._product_shell, "  ") is not None)

    print("3. the handoff is evidence:")
    problems = o.finalize_coding(RUN_ID, "03-coding")
    check("empty branch fails the stage", any("no commits" in x for x in problems), problems)
    check("...and writes no handoff", not (fake_repo / "workflow/runs" / RUN_ID / "03-coding" / "handoff.json").exists())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("NEW = 2\n", encoding="utf-8")
    out = o._product_shell(f"git add -A && git commit -q -m '{RUN_ID}: task 1 — add NEW'")
    check("agent can commit through the shell", out.startswith("exit 0"), out[:200])
    msg = git("log", "-1", "--format=%B", cwd=checkout)
    check("commit carries the Lantern-Agent trailer (hook, D6)", "Lantern-Agent: coding" in msg, msg)
    check("commit is authored by the bot identity",
          git("log", "-1", "--format=%an", cwd=checkout) == p.GIT_AUTHOR_NAME)
    (checkout / "leftover.txt").write_text("forgot to commit me\n", encoding="utf-8")
    problems = o.finalize_coding(RUN_ID, "03-coding")
    check("finalize succeeds with commits", problems == [], problems)
    hf = fake_repo / "workflow/runs" / RUN_ID / "03-coding" / "handoff.json"
    h = json.loads(hf.read_text(encoding="utf-8"))
    check("handoff names the run's branch and base", h["branch"] == BRANCH and h["base"] == "main")
    check("two commits: the task and the auto-committed leftover",
          len(h["commits"]) == 2 and h["auto_committed"] is True, h["commits"])
    check("task commit comes first (oldest first)", "task 1" in h["commits"][0]["subject"], h["commits"])
    check("files_changed lists both files",
          sorted(h["files_changed"]) == ["leftover.txt", "src/new.py"], h["files_changed"])
    bundle = fake_repo / h["bundle"]
    check("bundle exists and is non-empty", bundle.is_file() and bundle.stat().st_size > 0)
    check("handoff verifies against the checkout", o.check_coding_handoff(RUN_ID, "03-coding", checkout) == [])
    check("handoff verifies against the origin (has the base)", o.check_coding_handoff(RUN_ID, "03-coding", origin) == [])
    check("postconditions include the handoff check for the coding role",
          "handoff" in o.check_coding_handoff.__doc__.lower())

    print("4. only the run's branch can ride along:")
    bad = bundle.with_name("bad.bundle")
    # A bundle that also carries main (whole history for that ref).
    subprocess.run(["git", "bundle", "create", str(bad), f"refs/heads/{BRANCH}", "refs/heads/main"],
                   cwd=checkout, capture_output=True)
    good_bundle_rel = h["bundle"]
    h["bundle"] = good_bundle_rel.replace("branch.bundle", "bad.bundle")
    hf.write_text(json.dumps(h), encoding="utf-8")
    problems = o.check_coding_handoff(RUN_ID, "03-coding", checkout)
    check("extra ref in the bundle is rejected", any("expected exactly" in x for x in problems), problems)
    h["bundle"] = good_bundle_rel
    hf.write_text(json.dumps(h), encoding="utf-8")
    h2 = dict(h, branch="main")
    hf.write_text(json.dumps(h2), encoding="utf-8")
    problems = o.check_coding_handoff(RUN_ID, "03-coding", None)
    check("a non-feat/fix branch is rejected", any("feat/" in x for x in problems), problems)
    hf.write_text(json.dumps(h), encoding="utf-8")

    print("5. publishing without a network:")
    e = raises(p._publish_branch, RUN_ID, str(origin), "main")
    check("publish lands the branch in a local-path product repo", e is None, repr(e))
    if e is None:
        head_in_origin = git("rev-parse", f"refs/heads/{BRANCH}", cwd=origin)
        check("origin now has the branch at the handoff head", head_in_origin == h["head_sha"])
        payload = p._publish_branch(RUN_ID, str(origin), "main")   # idempotent re-run
        check("payload carries branch/base/commits", payload["branch"] == BRANCH and payload["commit_count"] == 2
              and payload["pushed"] is False and payload["pr_url"] is None, payload)
        check("pr.md written into the run folder (D4)",
              (fake_repo / "workflow/runs" / RUN_ID / "03-coding" / "pr.md").is_file())
    h3 = dict(h, branch="feat/other")
    hf.write_text(json.dumps(h3), encoding="utf-8")
    e = raises(p._publish_branch, RUN_ID, str(origin), "main")
    check("publish refuses a branch that is not the run's", e is not None and "expected" in str(e), repr(e))
    hf.write_text(json.dumps(h), encoding="utf-8")
    body = p.pr_body(RUN_ID, h, "main")
    check("PR body is the evidence pack", RUN_ID in body and "task 1" in body and "do not merge" in body.lower(), body[:200])

    print("6. parsing:")
    check("feat run -> feat/ branch", p.coding_branch("feat-20260907-x") == "feat/20260907-x")
    check("bug run -> fix/ branch", p.coding_branch("bug-20260907-x") == "fix/20260907-x")
    check("brief: auto", p.parse_brief_coding_mode("- **Coding mode:** auto\n") == "auto")
    check("brief: backticked, mixed case", p.parse_brief_coding_mode("- **Coding mode:** `Human`\n") == "human")
    check("brief: nonsense reads as unset", p.parse_brief_coding_mode("- **Coding mode:** banana\n") == "")
    check("brief: missing reads as unset", p.parse_brief_coding_mode("# nothing\n") == "")
    check("github url parsed", p._github_repo("https://github.com/Owner/Repo.git") == ("Owner", "Repo"))
    check("non-github url is not a PR target", p._github_repo("https://gitlab.com/o/r") is None)

    # ── D15: continuing an EXISTING branch ───────────────────────────────────
    print("7. base + working branch (D15):")
    check("no working branch -> derived from the run id",
          p.work_branch("feat-20260907-x") == "feat/20260907-x")
    check("bug run, no working branch -> fix/",
          p.work_branch("bug-20260907-x") == "fix/20260907-x")
    check("a chosen working branch wins",
          p.work_branch("feat-20260907-x", "feat/existing") == "feat/existing")
    check("whitespace-only reads as unset",
          p.work_branch("feat-20260907-x", "   ") == "feat/20260907-x")

    # Build an origin whose feat/existing branch ALREADY carries work, the way a run
    # continuing someone else's branch would find it.
    tmp2 = Path(tempfile.mkdtemp(prefix="lantern-continue-"))
    origin2, seedco = make_repos(tmp2)
    git("checkout", "-q", "-b", "feat/existing", cwd=seedco)
    git("config", "user.name", "seed", cwd=seedco)
    git("config", "user.email", "seed@example.invalid", cwd=seedco)
    for n in (1, 2):
        (seedco / f"prior{n}.py").write_text(f"PRIOR = {n}\n", encoding="utf-8")
        git("add", "-A", cwd=seedco)
        git("commit", "-q", "-m", f"prior work {n}", cwd=seedco)
    git("push", "-q", "origin", "feat/existing", cwd=seedco)

    p.PRODUCT_MIRROR_DIR = tmp2 / "mirrors"
    co = p.product_checkout(str(origin2), "main", "feat-20260907-continue", "feat/existing")
    check("product_checkout lands on an existing working branch",
          git("rev-parse", "--abbrev-ref", "HEAD", cwd=co) == "feat/existing")
    before = git("rev-parse", "HEAD", cwd=co)
    start = p.prepare_coding_checkout(co, "feat/existing")
    check("prepare_coding_checkout is a no-op when HEAD is already there",
          git("rev-parse", "--abbrev-ref", "HEAD", cwd=co) == "feat/existing")
    check("...and returns the sha the stage starts from", start == before, f"{start} vs {before}")
    check("a missing working branch leaves the checkout on the base",
          git("rev-parse", "--abbrev-ref", "HEAD",
              cwd=p.product_checkout(str(origin2), "main", "feat-20260907-fresh",
                                     "feat/not-there")) == "main")

    # THE regression this section exists for. finalize_coding's old "did this stage do
    # work" test was `merge-base(base, HEAD)..HEAD is non-empty`. On a branch that
    # already has commits that is true before the agent does anything — so a stage that
    # produced NOTHING would pass, and the bundle would carry the prior commits into
    # the PR as if the agent had written them.
    run2 = "feat-20260907-continue"
    (fake_repo / "workflow" / "runs" / run2 / "03-coding").mkdir(parents=True)
    os.environ["LANTERN_PRODUCT_DIR"] = str(co)
    os.environ["LANTERN_PRODUCT_BRANCH"] = "main"
    os.environ["LANTERN_CODING_BRANCH"] = "feat/existing"

    os.environ.pop("LANTERN_CODING_START_SHA", None)
    probs_without = o.finalize_coding(run2, "03-coding")
    check("WITHOUT a start sha the vacuous check passes an idle stage",
          not probs_without, f"expected the old behaviour, got {probs_without}")

    os.environ["LANTERN_CODING_START_SHA"] = start
    probs_with = o.finalize_coding(run2, "03-coding")
    check("WITH a start sha an idle stage is caught",
          any("added no commits" in x for x in probs_with), probs_with)

    (co / "new_work.py").write_text("NEW = 1\n", encoding="utf-8")
    git("add", "-A", cwd=co)
    git("commit", "-q", "-m", "the agent's own commit", cwd=co)
    probs_real = o.finalize_coding(run2, "03-coding")
    check("...and real work passes", not probs_real, probs_real)
    hf2 = json.loads((fake_repo / "workflow" / "runs" / run2 / "03-coding"
                      / "handoff.json").read_text(encoding="utf-8"))
    check("handoff records the start sha", hf2.get("start_sha") == start, hf2.get("start_sha"))
    check("the bundle still spans base..HEAD, so the PR shows the whole branch",
          len(hf2["commits"]) == 3, [c["subject"] for c in hf2["commits"]])

    check("_publish_branch accepts the run's chosen working branch",
          p._publish_branch(run2, str(origin2), "main", "feat/existing")["branch"]
          == "feat/existing")
    check("...and still rejects a handoff naming a different branch",
          raises(p._publish_branch, run2, str(origin2), "main", "feat/somewhere-else")
          is not None)

    os.environ.pop("LANTERN_CODING_START_SHA", None)
    os.environ["LANTERN_PRODUCT_DIR"] = str(checkout)
    shutil.rmtree(tmp2, ignore_errors=True)

    print("8. the flag does not leak:")
    os.environ.pop("LANTERN_PRODUCT_WRITABLE", None)
    os.environ.pop("LANTERN_CODING_BRANCH", None)
    check("read-only again once the execution env is gone",
          not o.product_writable() and raises(o._writable, "product/src/new.py") is not None)

    shutil.rmtree(tmp, ignore_errors=True)
    if FAILURES:
        print(f"\n{len(FAILURES)} FAILED: {FAILURES}")
        return 1
    print("\nall auto-coding properties hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
