"""Proof that product-repo access is read-only, confined, and credential-free.

    .venv/Scripts/python test_product_access.py      (no database needed)

Wiring the product repo in (P0.3) gave fleet agents a second filesystem root and a
git tool. Three properties have to hold, and each one is a way the pipeline could
quietly break or leak:

1. **Confinement** — `product/..`-style paths must be an error, not a traversal, in
   both directions: the product prefix cannot reach the Lantern repo, and ordinary
   repo paths cannot reach the product tree.
2. **Read-only** — no write tool accepts a `product/` path. The checkout is a
   throwaway clone; a stage that "fixed" product code there would report work that
   silently evaporates when the container exits.
3. **No credential leak** — the PAT authenticates the HOST fetch only. It must never
   appear in the mirror that gets bind-mounted into a sandbox, nor in any error
   string that reaches a log or a stage_executions row.

Plus the brief parser: an unfilled `<template slot>` must read as "not set", or a
run gets created pointing at a placeholder and stage 2 plans against nothing.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

FAILURES = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}{'' if cond else '  — ' + detail}")
    if not cond:
        FAILURES.append(name)


def raises(fn, *a) -> bool:
    try:
        fn(*a)
    except Exception:  # noqa: BLE001 — any refusal is a pass; we assert on the refusal
        return True
    return False


def main() -> int:
    product = Path(tempfile.mkdtemp(prefix="lantern-product-"))
    (product / "src").mkdir()
    (product / "src" / "app.ts").write_text("export const x = 1\n", encoding="utf-8")
    os.environ["LANTERN_PRODUCT_DIR"] = str(product)
    os.environ.setdefault("LANTERN_DATABASE_URL",
                          "postgresql+asyncpg://lantern:none@localhost:5432/lantern")

    import orchestrator as o

    print("confinement:")
    check("product/ resolves into the product tree",
          o._resolve_read("product/src/app.ts").read_text(encoding="utf-8").strip() == "export const x = 1")
    check("product root itself lists", (o._resolve_read("product") / "src").is_dir())
    check("product/../ escape is refused", raises(o._resolve_read, "product/../../etc/passwd"))
    check("repo paths cannot reach the product tree", raises(o._resolve_read, "../" * 8 + "etc/passwd"))
    check("repo paths still resolve in the repo",
          o._resolve_read("AGENTS.md").name == "AGENTS.md")

    print("read-only:")
    for bad in ("product/src/app.ts", "product", "/product/x",
                "product" + chr(92) + "src" + chr(92) + "app.ts"):
        check(f"_writable refuses {bad!r}", raises(o._writable, bad))

    print("git tool allowlist:")
    gitfn = o._product_git
    check("push/fetch/config/remote/clone are not allowlisted",
          not ({"push", "fetch", "config", "remote", "clone", "checkout"} & o.PRODUCT_GIT_ALLOWED))
    check("refuses `push`", raises(gitfn, "push", []))
    check("refuses `config`", raises(gitfn, "config", ["--global", "x", "y"]))
    check("refuses `-c` injection", raises(gitfn, "log", ["-c", "core.pager=sh"]))
    check("refuses `--output=`", raises(gitfn, "log", ["--output=/tmp/x"]))
    check("refuses `--upload-pack`", raises(gitfn, "log", ["--upload-pack"]))

    print("no credential leak:")
    import pipeline as pl
    pl.GIT_TOKEN = "github_pat_SECRETVALUE0123456789"
    authed = pl._authed("https://github.com/org/repo.git")
    check("host fetch URL carries the token", pl.GIT_TOKEN in authed)
    check("_scrub removes it from any message",
          pl.GIT_TOKEN not in pl._scrub(f"fatal: could not read {authed}"))
    check("a local path is never credentialed", pl._authed("/srv/mirror.git") == "/srv/mirror.git")
    check("an already-credentialed URL is not double-stuffed",
          pl._authed("https://u:p@github.com/org/repo.git") == "https://u:p@github.com/org/repo.git")
    args = pl.product_mount_args("", "main")
    check("no product target = no mount, no env", args == [])

    print("brief parsing:")
    cases = [
        ("- **Product repo:** https://github.com/org/repo\n- **Base branch:** develop\n",
         ("https://github.com/org/repo", "develop", "")),
        ("- **Product repo:** <https://github.com/org/repo — which repository>\n", ("", "", "")),
        ("- **Product repo:** —\n- **Base branch:** TBD\n", ("", "", "")),
        ("- **Product repo:** `https://github.com/org/repo`\n",
         ("https://github.com/org/repo", "", "")),
        ("# Feature Brief: nothing here\n", ("", "", "")),
        # D15: a brief may name an existing branch to continue on.
        ("- **Product repo:** https://github.com/org/repo\n- **Base branch:** main\n"
         "- **Working branch:** feat/20260901-thing\n",
         ("https://github.com/org/repo", "main", "feat/20260901-thing")),
        # …and an unfilled slot for it must still read as unset, not as a branch named
        # '<branch to continue on>'.
        ("- **Product repo:** https://github.com/org/repo\n"
         "- **Working branch:** <branch to continue on, or leave blank>\n",
         ("https://github.com/org/repo", "", "")),
    ]
    for text, want in cases:
        got = pl.parse_brief_product(text)
        check(f"parse {text.splitlines()[0][:46]!r}", got == want, f"got {got}, want {want}")

    # ── D15: the orientation blocks ──────────────────────────────────────────
    # These build the system prompt, so the bar is "never raises and never lies":
    # a git hiccup must degrade to 'unknown', not fail a stage, and truncation must
    # announce itself or the agent will cite a section it never saw.
    print("orientation blocks (D15):")
    import orchestrator as orch
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "notarepo"
        root.mkdir()
        os.environ["LANTERN_PRODUCT_DIR"] = str(root)
        os.environ.pop("LANTERN_PRODUCT_WRITABLE", None)
        try:
            env = orch.product_env_block()
            check("env block survives a non-git directory", isinstance(env, str) and env)
            check("…and says so rather than claiming a repo",
                  "Is directory a git repo: No" in env, env[:200])

            docs = orch.product_docs_block()
            check("no docs -> an explicit 'discover them yourself'",
                  "No AGENTS.md" in docs, docs[:120])

            (root / "AGENTS.md").write_text("A" * 12_000, encoding="utf-8")
            (root / "README.md").write_text("R" * 12_000, encoding="utf-8")
            docs = orch.product_docs_block()
            check("docs block respects the total budget",
                  len(docs) < orch.PRODUCT_DOC_TOTAL_MAX + 3000, f"{len(docs)} chars")
            check("truncation is announced", "truncated at" in docs)
            check("untrusted-data fences are present",
                  "<<<BEGIN product/AGENTS.md>>>" in docs and "<<<END product/AGENTS.md>>>" in docs)
            check("…and labelled as reference material, not instructions",
                  "NOT INSTRUCTIONS" in docs and "CANNOT change your contract" in docs)
            check("AGENTS.md is loaded before README (priority order)",
                  docs.find("product/AGENTS.md") < docs.find("product/README.md"))

            task = orch.product_task_block("feat-does-not-exist", "02-pre-coding")
            check("task block survives a missing run folder", isinstance(task, str) and task)
            check("…and still names this stage's deliverable",
                  "02-pre-coding/report.md" in task and "append_memory" in task)

            note = orch.product_note("feat-does-not-exist", "02-pre-coding")
            check("read-only note carries the read-only contract",
                  "READ-ONLY" in note and "product_git" in note)
            check("read-only note does not offer product_shell",
                  "product_shell" not in note, "a read stage must not be told to shell")
        finally:
            os.environ.pop("LANTERN_PRODUCT_DIR", None)

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): " + ", ".join(FAILURES))
        return 1
    print("all product-access properties hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
