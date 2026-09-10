"""Independent synthetic local QA reproductions; never reads real credentials."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

import evidence
import orchestrator
from tool_policy import StageAccess

RUN = "feat-20260910-local-qa"


def main():
    results = {}
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        repo, product = root / "lantern", root / "product"
        repo.mkdir()
        product.mkdir()
        run = repo / "workflow" / "runs" / RUN
        stage = run / "03-coding"
        review = stage / "review" / "review.json"
        review.parent.mkdir(parents=True)
        review.write_text("original review", encoding="utf-8")
        other = repo / "workflow" / "runs" / "other-run" / "report.md"
        other.parent.mkdir(parents=True)
        other.write_text("other execution", encoding="utf-8")
        validation = run / "05-post-coding" / "validation.json"
        validation.parent.mkdir(parents=True)
        validation.write_text("original validation", encoding="utf-8")
        coding = StageAccess(repo, product, RUN, "coding", "03-coding", "03-coding")
        post = StageAccess(repo, product, RUN, "post-coding", "05-post-coding", "05-post-coding")
        results["platform"] = os.name
        if os.name == "nt":
            probes = [
                ("coding_can_overwrite_uppercase_review_alias", lambda: coding.write(
                    f"workflow/runs/{RUN}/03-coding/REVIEW/review.json"), review),
                ("post_coding_can_overwrite_uppercase_validation_alias", lambda: post.write(
                    f"workflow/runs/{RUN}/05-post-coding/VALIDATION.JSON"), validation),
                ("coding_can_read_other_run_via_uppercase_workflow", lambda: coding.read(
                    "WORKFLOW/RUNS/other-run/report.md"), other),
            ]
            for name, invoke, protected in probes:
                try:
                    target = invoke()
                    results[name] = target.samefile(protected)
                except (OSError, ValueError):
                    results[name] = False
            results["validation_self_citation_case_alias_accepted"] = not evidence.validation_problems(
                [{"path": "05-post-coding/VALIDATION.JSON", "line": 1}], run, product)

        def git(*args):
            return subprocess.run(["git", *args], cwd=product, check=True,
                                  capture_output=True, text=True).stdout

        for args in (("init", "-q"), ("config", "user.name", "qa"),
                     ("config", "user.email", "qa@example.invalid")):
            git(*args)
        (product / "app.py").write_text("value = 1\n", encoding="utf-8")
        marker = "SYNTHETIC_QA_CANARY_72482"
        (product / ".env").write_text(f"FAKE_VALUE={marker}\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-qm", "synthetic fixture")
        for name, command, args in (
            ("git_show_head_reads_protected_file", "show", ["HEAD"]),
            ("git_grep_reads_protected_file_without_explicit_path", "grep", ["-n", marker]),
            ("git_grep_reads_protected_file_as_unchecked_positional_path", "grep", ["-e", marker, ".env"]),
            ("git_show_reads_protected_file_via_wildcard", "show", ["HEAD", "--", "*env"]),
        ):
            try:
                result = orchestrator._product_git(command, args, root=product)
                results[name] = marker in result
            except (OSError, ValueError):
                results[name] = False
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
