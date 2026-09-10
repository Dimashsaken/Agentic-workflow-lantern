# Skills — reviewer

## 1. Session start

Standard reads, then the round context at the end of your prompt ("This review
round"): which round this is, how many are allowed, and what earlier rounds asked for.
Build the ledger before judging:

1. `03-coding/handoff.json` → `base_sha`, `head_sha`, `commits` (oldest first),
   `files_changed`. This is the exact range you review; nothing outside it.
2. `02-pre-coding/plan.json` + `task-plan.md` → the tasks, their criteria, the
   `write_scope`. `00-story/story.json` → the criteria and their `edge_cases`.
3. `03-coding/gate.md` → what the product's own commands said (green by construction
   when you run; a red gate means the loop is broken — BLOCK).
4. `03-coding/report.md` → the coding report's `## Deviations` and confidence map;
   start reading the diff where confidence is lowest.
5. Not the first round? `03-coding/review/round-<n-1>.md` + `review.json` → what you
   asked for; the fix execution's `## Fix — round <n-1>` section in `report.md` → what
   it says it changed. Verify each earlier must-fix in the new diff; carry forward any
   that is not actually resolved, same id.

Then the code: `product_git('diff', ['<base_sha>..<head_sha>', '--stat'])`, then
`product_git('diff', ['<base_sha>..<head_sha>', '--', '<path>'])` per file, and
`read_file('product/<path>')` for the surrounding code the diff does not show. The
checkout is on the run's branch — confirm with the `<env>` block; if `HEAD` is not
`head_sha`, BLOCK.

## 2. Review passes (in this order)

1. **Correctness** — read each changed function end to end. For every criterion the
   task claims, ask: what input breaks it? Check the story's `edge_cases` explicitly.
   Follow every new call into its callee; follow every error path to where it lands.
2. **Tests** — for every behaviour change, find the test that would fail without it.
   No such test → `major` ("missing test for …") with the test you would write as the
   suggestion. Tests that only assert the code ran are not tests.
3. **Plan conformance** — every plan task present or declared deferred; nothing
   undeclared. Compare `files_changed` with the `write_scope` and the blast radius.
4. **Security smells** — injection (SQL, shell, path), auth checks on new endpoints,
   secrets in code or logs, unbounded lists or uploads, unsafe deserialisation.
   `major`, summary starts with `security:`. Never decide the deploy — flag.
5. **Style that hides bugs** — only misleading names, dead branches, copy-paste drift.

Severity: `blocker` = wrong behaviour a user or the next stage will hit, or a
security smell on an auth/data path; `major` = a bug on an edge case, a missing test,
undeclared scope, any other security smell; `minor` = a real but contained defect;
`nit` = a suggestion. Be specific: `file`, `line` (the line in the NEW file), one
sentence, and the smallest fix.

## 3. Verdict

Computed, not chosen: `approve` when there is no blocker and no major; otherwise
`request_changes`, and `must_fix` lists every blocker and major (minors may join it
when they are cheap and adjacent). The harness rejects a verdict that disagrees with
the severities. Approving with open nits is normal — list them, they are for the
human. Do not request changes for taste.

## 4. Write the envelope

`03-coding/review/round-<n>.md` — the review a human reads: the verdict in the first
line, then the findings table (`id | severity | file:line | summary | suggestion`),
then what you checked and found sound (one line per pass). `03-coding/review/review.json`:

```json
{
  "kind": "review",
  "run_id": "feat-20260908-saved-items",
  "round": 1,
  "verdict": "request_changes",
  "findings": [
    {"id": "R-1", "severity": "major", "file": "src/api/saved.py", "line": 41,
     "summary": "save_item inserts twice on a double click — no unique constraint and no check (AC-1 edge case)",
     "suggestion": "SELECT before INSERT inside the transaction, or a unique index on (user_id, item_id) and catch the violation"},
    {"id": "R-2", "severity": "major", "file": "tests/test_saved.py", "line": null,
     "summary": "missing test: nothing exercises unsave (AC-3)",
     "suggestion": "test_unsave_removes_within_one_second using the fake clock in tests/conftest.py"},
    {"id": "R-3", "severity": "nit", "file": "src/ui/saved.tsx", "line": 12,
     "summary": "`itms` is the only abbreviation in the file", "suggestion": "rename to items"}
  ],
  "must_fix": ["R-1", "R-2"]
}
```

Rules the harness enforces: `round` is a positive integer and `round-<n>.md` exists;
ids unique; `severity` in blocker/major/minor/nit; `summary` non-empty; a blocker or
major carries a `suggestion`; `must_fix` ⊆ finding ids and ⊇ every blocker/major;
`verdict` = `approve` ⇔ no blocker/major. Then append `## Review — round <n>` to
`03-coding/report.md` with its own `- **Status:**` line (PASS for either verdict — a
request_changes is your job done, not a blocked stage) and the one-line verdict.

File findings must resolve inside the handoff's diff. A line must exist in that
file at `head_sha`, and the checkout must be at `head_sha`. For a deleted file use
`line: null`. For missing work whose file is not in the diff, use `file: ""` and
`line: null`, and name the expected file in the summary. This verifies location;
it does not establish that the reviewer found every defect.

## 5. Session end

Report section as above; `append_memory` with the defect class this product's builds
keep producing (so the story writer and the coding role tighten next time), or an
explicit "nothing durable learned". Never edit the branch, never comment on GitHub
yourself — the host posts your findings as one PR review from the bot identity.
