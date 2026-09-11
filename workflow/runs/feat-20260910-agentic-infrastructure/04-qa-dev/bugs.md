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

## Round 5 — execution provenance UI

No new product bug found in the executed fixture scope. Matching controller
provenance renders; forged gate mirrors and stale/cross-run receipts do not acquire
verified status. All 12 drawer controls and final desktop/mobile recordings pass.
Initial mobile screenshot returned to the header after clicking theme; the recorder
now scrolls the evidence section back into view. This was a recording limitation,
not a product failure. All initial and final media remain linked in report.md.

Actual authenticated desktop/mobile sessions also pass on executions 11/12.
Their unverified-manifest labels remain visible and honest beside succeeded stage
and valid-envelope badges. Before/after snapshots retain pending approval 4 and
unchanged execution/run state. No product bug, gate decision or deployment was
introduced. Verified-receipt display remains explicitly fixture-tested because
these real story stages did not produce a coding manifest.

## Round 6 — continuation 3 UI regression

No new product defect found in four recorded contexts and 32 scoped Python tests.
Matching/forged/stale/cross-run renderer controls pass; actual application
executions 16/17 remain honestly unverified, and approval 6 remains pending.

Evidence limitation QA-E6: recorder event seconds use a wall timer, while video
capture starts later; actual desktop/mobile events can exceed video duration.
This is a recorder timestamp limitation, not an application failure. Round 6's
report uses decoded, visually checked video offsets for all four recordings;
raw wall-event data remains preserved and explicitly labelled. See desktop
actual video at 0:07, mobile actual at 0:13.5, fixture desktop at 0:02.8, fixture
mobile at 0:01.8. Deployment-bound recording receipt acceptance remains separate;
these local videos cannot satisfy that unfinished foundation gate.

## Continuation 3 outstanding-foundation QA — 2026-09-11 preparation

No new product defect is claimed before execution. Environment blocker QA-C3-E1: installed Docker CLI cannot open the Linux-engine API pipe at initial readiness inspection. Reproduction: query Docker server information using the existing CLI. Expected: the designated local Docker engine responds. Actual: named pipe absent. No browser ran, so no video/timestamp exists for this environment failure. Security owns engine startup. This is not a sev-1/sev-2 product finding and does not pass the QA gate.

New execution findings and their actual recordings will be appended below. Prior closed findings and retained evidence remain unchanged.

### QA-C3-E1 update — 2026-09-11

The security agent reports Docker Desktop startup is blocked by a host runtime socket error before the Linux engine becomes available. No actual candidate-image browser capture can run. This remains an environment prerequisite, not a product bug or an acceptance waiver. The exact independent SQL probes in `c3-qa-controller-sql.json` passed 16/16 and found no new sev-1/sev-2 product finding in their limited executed scope. Recorder callbacks were injected; no video or live behavior is claimed by those tests.

### QA-C3-E2 — disposable launcher pipe wait, resolved in QA harness

The fresh PostgreSQL server became ready, but the QA Python launcher continued waiting for daemon-inherited stdout/stderr handles. Reproduction is `pg_ctl start` beneath `subprocess.run(capture_output=True)` on this Windows runtime. The helper was changed to DEVNULL plus the owned PostgreSQL log; only the identified QA launcher processes were terminated, and setup resumed against the verified fresh data directory. The configured cluster was not involved. This was a test-harness issue, not a runtime product defect; it has no browser/video evidence.

### Actual recorder retest — 2026-09-11

QA-C3-E1 is resolved for the tested local engine: four actual recorder sessions now pass their intended positive/negative outcomes. No new sev-1/sev-2 product issue was found. C3-Q2's failed assertion, C3-Q3's injected deployment drift and C3-Q4's actual lost execution fence are intentional denial controls, not bugs. Their exact video links/timestamps and evidence distinctions are in the latest report table; each correctly produces no controller seal or durable receipt. No previous evidence was removed, no unchanged UI proof was repeated, and external gateway/foundation acceptance remains separate.
