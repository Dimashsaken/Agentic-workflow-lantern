# Local QA findings — feat-20260910-agentic-infrastructure

Date: 2026-09-10. Findings concern the local working tree, not a deployed fleet.
Reproductions use disposable synthetic repositories and no real credentials.
All true values in `adversarial-probes-before.txt` indicate a bypass reproduced by
`adversarial-probes.py`. No videos were recorded: dev QA is blocked before browser
execution, so no video timestamps exist. These are local code-level findings.

## QA-1 — sev-2 — Windows path case aliases bypass execution output boundaries

Status: RESOLVED IN LOCAL RETEST. Criteria: AC-1. First seen: uncommitted working tree on
`codex/agentic-infrastructure`, 2026-09-10.

Reproduce on Windows with `adversarial-probes.py`: create a coding policy and a real
`03-coding/review/review.json`, then ask `StageAccess.write` for
`03-coding/REVIEW/review.json`. The returned target is the same protected file.
Likewise, post-coding can obtain `05-post-coding/VALIDATION.JSON`, and a read of
`WORKFLOW/RUNS/other-run/report.md` reaches another run.

Expected: reject protected role artifacts and cross-run reads regardless of
filesystem case aliases. Actual: case-sensitive string guards pass, while Windows
resolves the target to the protected file. The repro calls the policy and verifies
file identity without corrupting any real artifacts.

Evidence: `adversarial-probes-before.txt`, lines 3–5. Video: none; local-only repro.
Developer/security flag sent to the parent integrator immediately after reproduction.

## QA-2 — sev-2 — Git inspection exposes tracked credential files

Status: RESOLVED IN LOCAL RETEST. Criteria: AC-1, AC-2. First seen: uncommitted working tree on
`codex/agentic-infrastructure`, 2026-09-10.

Reproduce with `adversarial-probes.py`: initialize a temporary repository, commit an
`app.py` plus a `.env` containing only the script's synthetic marker. Invoke the
actual `orchestrator._product_git` body with `show HEAD`, `grep -n <marker>`,
`grep -e <marker> .env`, and `show HEAD -- *env`.

Expected: the Git tool observes its documented credential-file boundary. Actual:
all four return the synthetic protected content. The option grammar rejects an
explicit `show HEAD:.env` but does not confine implicit multi-file reads, wildcard
pathspecs, or all positional operands in grep.

Evidence: `adversarial-probes-before.txt`, lines 7–10. Video: none; local-only repro.
Security-relevant exploration stopped and the parent integrator was notified.

## QA-3 — sev-2 — Windows evidence case alias admits validation self-citation

Status: RESOLVED IN LOCAL RETEST. Criterion: AC-4. First seen: uncommitted working tree on
`codex/agentic-infrastructure`, 2026-09-10.

Reproduce with `adversarial-probes.py`: create a nonempty
`05-post-coding/validation.json` and resolve a line-1 reference to
`05-post-coding/VALIDATION.JSON` against the same run on Windows.

Expected: reject self-citation. Actual: `validation_problems` returns an empty list
because the self-citation guard compares the supplied filename case-sensitively.

Evidence: `adversarial-probes-before.txt`, line 6. Video: none; local-only repro.

## Environment blocker

No dev server was running at kickoff and no dev/QA base URL is present in the
current process environment. The browser QA gate remains unexecuted. Do not count
local Python/HTML assertions as recorded dev UI evidence.

## Round 2 — exact reproduction after fixes

On 2026-09-10 the integrator supplied fixes and requested a regression rerun.
The unchanged `adversarial-probes.py` now returns false for all eight bypass
booleans. QA-1 is resolved by lines 3–5, QA-3 by line 6, and QA-2 by lines 7–10
of `adversarial-probes-after.txt`. The adjacent tool-policy and evidence suites
also pass; details and remaining skips are in the report.

No open finding remains from the executed local probes. Resolution here covers
the reproduced behaviors only, not a security signoff or a fleet QA pass. The
attempted independent security review did not execute because of a platform risk
check, as reported by the parent integrator. Browser QA remains unexecuted; no
videos or timestamps are claimed.

## Round 3 — continuation baseline and local renderer checks

On 2026-09-10, all eight unchanged bypass reproductions remained false in
`continuation-probes.txt`. Adjacent regression: 59 tests, 58 passed and one Windows
symlink privilege skip. No new product bug was found in the local renderer browser
checks; final desktop and mobile recordings pass. Videos, timestamps and trace
links for all six local sessions are in Round 3 of `report.md`.

The first desktop recording failed only because the test requested a button named
`theme` after the application had changed its accessible name to `dark mode`.
The recorder now targets the hydrated label and verifies the theme changed.
An additional mobile assertion checks reference geometry against the sticky AC
column, avoiding a false positive from visibility alone. Neither change modifies
the product. Earlier failed and superseded recordings remain available.

The authenticated dev QA blocker remains: both process environment and the normal
dotenv-backed environment have no dev base URL or QA login configured. No live
application session, Azure call, database lifecycle or container-isolation result
is claimed by this QA audit. The local fixture server was stopped after recording.

## Round 4 — actual authenticated local application

The environment blocker was resolved for a supplied disposable local app and DB.
Recorded browser sessions read actual Azure-produced researcher/story artifacts for
`feat-20260910-live-inprocess-2`; no fixture execution or validation row was added.
Final desktop and mobile recordings pass. Before/after Postgres snapshots prove
approval 1 remains pending story_signoff and the run remains waiting_gate.
See Round 4 of `report.md` for all five actual-app video/trace links and timestamps.

No new product bug was found. One mobile test failed because it expected lowercase
text while CSS transforms the label to uppercase. A later visual review strengthened
the test again to bring the matrix inside the recorded viewport; text assertions
alone had passed below the fold. Both are corrected recorder limitations, with
earlier recordings preserved. The final screenshot visibly shows pending columns.

No registered QA stage or gate approval is claimed. Real downstream structured
validation content remains untested because the real run correctly waits for human
story approval; the earlier fixture coverage is kept separate.
