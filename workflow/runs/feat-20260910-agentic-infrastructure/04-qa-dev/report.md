# Stage Report: 04-qa-dev — feat-20260910-agentic-infrastructure

- **Agent/author:** qa-dev, independent local audit
- **Date:** 2026-09-10
- **Status:** BLOCKED

## Summary

The local regression audit reproduced three correctness/security findings beyond
the supplied tests, and the exact reproductions pass after fixes. Recorded dev QA
is blocked because no dev target is available.
This report is local engineering evidence, not a database-registered execution or
a fleet gate decision.

## Work performed

Read qa-dev charter, skills and memory; the runboard; local implementation plan and
coding report; recorder README; modified policy, gate, evidence, journal and UI
rendering code. Wrote `test-charter.md` before executing tests. Invoked tests with
the bundled Python runtime and the existing ignored dependency adapter, because
the checked-in virtualenv launcher references an unavailable Python installation.

## Findings / results

The numbered results below describe the initial audit. See Round 2 for the final
local regression result.

1. AC-1/AC-2: supplied capability/Git suite ran 13 tests, 12 passed and one skipped
   because Windows denied symlink creation. Independent probes found QA-1 and QA-2.
2. AC-3: six gate-integrity tests passed, including malformed, missing, stale and
   contradictory gates, missing test policy, and policy replacement attempts.
3. AC-4: 11 evidence tests passed. Independent probe found QA-3: validation can cite
   its own output through a case alias on Windows.
4. AC-5: seven journal tests passed, including partial failure usage, redaction,
   duplicate accounting and safe retry behavior.
5. AC-4: nine Mission Control traceability tests passed, including structured
   evidence paths and hostile HTML characters. This is rendering-unit evidence;
   it does not establish browser behavior.
6. AC-6: parent integrator owns the full suite, eval report and final coding report.
   The coding report was IN-PROGRESS without a confidence map at audit kickoff.
7. No live Azure execution, database lifecycle, container isolation or dev browser
   behavior was verified. Python tests establish local behavior, not OS isolation.

## Artifacts

- `test-charter.md` — written test design and limits.
- `bugs.md` — deterministic findings and affected acceptance criteria.
- `adversarial-probes.py` — independent synthetic reproductions.
- `adversarial-probes-before.txt` — observed bypass booleans.
- `tool-policy-test.txt`, `gate-integrity-test.txt`, `evidence-test.txt`,
  `journal-test.txt`, `traceability-test.txt` — executed local regression logs.
- Videos/traces: zero sessions recorded; no video URLs or timestamps are claimed.

## Handoff notes for the next stage

Do not advance a fleet QA gate from this report. QA-1/QA-2/QA-3 are resolved in the
exact local reproduction plus adjacent suites. Security-relevant findings were
reported to the parent integrator immediately; further exploit exploration stopped.

## Open questions

Which configured dev environment should receive the recorded browser QA run?

## Memory candidates

2026-09-10: Test both canonical and case-varied protected paths on Windows because
case-sensitive string checks can authorize the same file under a different name.
For Git read policies, probe default multi-file reads and wildcards as well as
explicit filenames, because operand validation alone does not exclude secret
content from a command's implicit scope.

These are candidates only. No `append_memory` tool is exposed to this local
non-registered session, so no database memory entry or rendered-memory edit is
claimed.

## Round 2 — regression after fixes, 2026-09-10

The integrator changed path comparisons, excluded protected files from Git content
views, constrained revision operands, and rejected worktree file aliases. I ran
the unchanged independent reproduction script: all eight bypass booleans changed
from true to false. The checks used only disposable synthetic repositories.

| Executed suite | Tests | Result | Evidence |
|---|---:|---|---|
| Tool policy and Git | 18 | 17 passed; one symlink privilege skip | `tool-policy-retest.txt` |
| Evidence resolution | 11 | Passed | `evidence-retest.txt` |
| Gate integrity | 6 | Passed | `gate-integrity-retest.txt` |
| Execution journal | 7 | Passed | `journal-retest.txt` |
| Mission Control traceability | 9 | Passed | `traceability-retest.txt` |

Total: 51 unit tests, 50 passed and one skipped. The standalone
`tools/azure-runner/test_product_access.py` property script also passed all its
checks (`product-access-script-retest.txt`). An initial unittest discovery attempt
against that script ran zero tests and is preserved in `product-access-retest.txt`;
the successful direct invocation supplies the actual verification.

Commands used the same bundled Python runtime, with `PYTHONPATH` pointing to the
ignored dependency adapter. Unit suites used `-m unittest discover -s <suite-dir>
-p <test-file> -v`; the standalone script and `adversarial-probes.py` were invoked
directly. `adversarial-probes-before.txt` and `adversarial-probes-after.txt` retain
both outcomes. `retest-source-hashes.json` identifies the audited source snapshot
after the reruns; this remains an uncommitted working-tree audit.

No open finding remains from these local reproductions. The coding report was
still IN-PROGRESS during the retest, so this audit makes no claim about later
changes or the integrator's final full-suite results. The independent security
review did not execute because its platform risk check failed, per the parent
integrator; no security signoff is claimed. No real dev browser, Azure, database,
deployment or OS isolation check ran. No videos or traces were recorded.

Status: BLOCKED

## Round 3 — continuation baseline, 2026-09-10

Reviewed the completed coding confidence map and continuation plan. HEAD remained
`90e4fb6feef464ef97aa56ccc451ca082b802165`; `continuation-regression-results.json`
identifies the tested source hashes and confirms those files did not change during
these tests. This is a local engineering audit, not a registered stage execution.

### Executed local regression

| Suite | Count | Result | Log |
|---|---:|---|---|
| Tool policy / Git | 19 | 18 passed, one Windows symlink privilege skip | `continuation-test_tool_policy.txt` |
| Evidence resolution | 11 | Passed | `continuation-test_evidence.txt` |
| Gate integrity | 8 | Passed | `continuation-test_gate_integrity.txt` |
| Execution journal | 12 | Passed | `continuation-test_execution_journal.txt` |
| Mission Control traceability | 9 | Passed | `continuation-test_traceability.txt` |

Total: **59 tests, 58 passed and one skipped**. The unchanged independent
`adversarial-probes.py` returned false for all eight bypass booleans
(`continuation-probes.txt`). No new product finding was observed. An initial probe
invocation failed to import `evidence` because the runner directory was absent
from PYTHONPATH; the successful invocation included it. This is a harness setup
error, not a tested product behavior.

Repeatable runner: `continuation-regressions.py`, using bundled Python 3.12.14 and
the existing ignored dependency shim. Each subprocess command is unittest
discovery for the named suite. Actual exit codes and source hashes are in
`continuation-regression-results.json`. No database/model/container boundary is
exercised by these results.

### Recorded local renderer regression

Both process environment and the environment populated through the normal
azure-runner dotenv loader lack `QA_BASE_URL`, `QA_USER`, `QA_PASS`,
`LANTERN_QA_DEV_BASE_URL`, `LANTERN_QA_DEV_USER`, `LANTERN_QA_DEV_PASS`, and
`LANTERN_WEB_USERS`. Therefore authenticated dev QA could not begin.

Separately, `local-browser-fixtures.py` served disposable synthetic envelopes
through the production traceability renderer, validation table, CSS and JavaScript.
Every page explicitly says it is a local renderer fixture. No run, execution,
approval, memory or other database row was created. The fixture has no auth flow
or gate controls; it does not exercise the real application routes or DB.
The loopback server was stopped after recording. Google Fonts were omitted for
deterministic fallback-font rendering without remote requests.

`tools/qa-recorder/agent-infrastructure-evidence.mjs` follows the recorder's
video-and-trace context pattern. Chromium/Playwright 1.62.1 exercised structured
file/line references, literal HTML-shaped text, Unicode, long paths, legacy prose,
empty story, refresh/back, validation-table rendering and theme switching.
The final mobile check verifies horizontal scroll can reveal the reference
without the sticky AC column covering it. Screenshots were visually inspected.
No uncaught browser error occurred. Long matrix paths remain visually truncated
with the full reference in the title attribute; this does not prove mobile
tooltip accessibility or full authenticated application usability.

The first desktop script used the pre-hydration button name `theme`; the UI changes
it to `dark mode`. Its final click timed out. The recorder was corrected, with the
failed recording preserved. After the first green rerun, screenshot inspection
justified strengthening the mobile assertion to check actual geometry, because
`isVisible()` alone does not prove a sticky column leaves text unobscured.
The final rerun passed both sessions.

| Session | Video / trace | Timeline from session start | Result |
|---|---|---|---|
| 1, initial desktop | [video](media/local-renderer-desktop.webm) / [trace](media/local-renderer-desktop.zip) | 0:00.42 structured; 0:01.66 legacy/back; 0:02.59 empty; 0:03.47 validation; ~0:04–0:34 locator wait | Recorder locator failed |
| 2, initial mobile | [video](media/local-renderer-mobile.webm) / [trace](media/local-renderer-mobile.zip) | 0:00.09 mobile; 0:01.17 evidence scroll | Passed limited assertion |
| 3, desktop retest | [video](media/local-renderer-desktop-retest.webm) / [trace](media/local-renderer-desktop-retest.zip) | 0:00.30 structured; 0:01.43 legacy; 0:02.35 empty; 0:03.21 validation; 0:04.12 theme | Passed |
| 4, mobile retest | [video](media/local-renderer-mobile-retest.webm) / [trace](media/local-renderer-mobile-retest.zip) | 0:00.09 mobile; 0:01.18 evidence scroll | Passed limited assertion |
| 5, final desktop | [video](media/local-renderer-desktop-verified.webm) / [trace](media/local-renderer-desktop-verified.zip) | 0:00.11 structured; 0:01.10 refresh; 0:01.19 legacy/back; 0:02.10 empty; 0:02.98 validation; 0:03.86 theme | Passed |
| 6, final mobile | [video](media/local-renderer-mobile-verified.webm) / [trace](media/local-renderer-mobile-verified.zip) | 0:00.07 mobile; 0:01.15 unobscured evidence after scroll | Passed |

These are **six local fixture sessions, zero configured dev sessions**. Videos and
traces are gitignored local files, not uploaded stage artifacts. No S3 location,
execution ID or provenance signature is claimed. `local-browser-results-initial.json`,
`local-browser-results-retest.json` and `local-browser-results.json` contain exact
step timings, browser errors, video SHA-256 hashes and production source hashes.
Final screenshots: `media/local-renderer-validation.png` and
`media/local-renderer-mobile.png`.

### Handoff and memory

QA-1, QA-2 and QA-3 remain resolved for their reproduced local behaviors. No open
sev-1/sev-2 product finding was discovered in this continuation. This report must
not advance a fleet QA gate: authenticated dev browser testing and live backend
integration are unverified. The parent integrator owns separate Azure/Postgres/
Docker results and independent review reports.

No `append_memory` tool is exposed to this non-registered local session; no memory
write or rendered-memory edit was made. Durable candidate for the actual tool:
"2026-09-10: Browser visibility assertions do not prove evidence is readable under
sticky columns. Check element geometry and inspect the recorded narrow viewport,
because a horizontally scrolled table can cover text that Playwright considers
visible." The parent's memory append, if any, must be evidenced separately.

Open question: Which environment-provided dev URL and QA login should receive the
authenticated recorded QA run?

Status: BLOCKED

## Round 4 — authenticated local dev integration, 2026-09-10

The parent integrator supplied an isolated harness containing an actual run after
real Azure researcher/story executions against disposable Postgres. This enabled
the previously blocked authenticated browser check. This round uses the actual
Mission Control application, database queries and on-disk execution artifacts;
it does not use the Round 3 renderer fixture server or injected HTTP responses.

Tested target: disposable run `feat-20260910-live-inprocess-2`, in the ignored
`tools/azure-runner/.venv/live-inprocess-2/harness` checkout. Its Mission Control
source hashes are recorded in `live-browser-before.json`; the four rendered
modules match baseline 90e4fb6. The local URL and credentials were supplied only
through process environment. The app launched with a hidden process, temporary
auth and a fresh signing secret. It was stopped after every recording invocation;
temporary auth variables were cleared and no reusable credential file was created.

### Results

1. Actual unauthenticated traceability requests redirected to login. UI login
   succeeded. Desktop run lanes displayed both real successful executions.
2. The real story matrix displayed AC-1 and AC-2, **zero complete and two pending**,
   with later-stage columns marked not yet. Refresh preserved those facts. No
   validation envelope was fabricated to populate the matrix: structured validation
   reference rendering remains covered only by Round 3 fixtures until that real
   downstream stage has run through its human gates.
3. Actual execution drawers for IDs **2** (`00-story.scout`) and **3**
   (`00-story.write`) displayed compiled prompts, tool calls, typed envelope
   validation and execution-linked memory. The test expanded prompts, scrolled
   tool-call and memory sections and returned to the pending run.
4. The final authenticated mobile recording scrolls the real matrix into the
   viewport and horizontally to later-stage columns. Geometry asserts the pending
   verdict lies inside the recorded viewport. Final desktop and mobile screenshots
   were visually inspected. No uncaught browser error or application HTTP error
   occurred.
5. `live-browser-state.py` used read-only Postgres transactions before and after
   browser work. Run status/stage/update timestamp, execution identities/statuses/
   token counts, approval decision fields and source hashes were identical.
   The run remains **waiting_gate / 00-story.write**; approval **1** remains
   **story_signoff / pending**, with null decision timestamp, actor and note.
   `live-browser-before.json` / `live-browser-after.json` retain the final pair;
   `live-browser-before-initial.json` / `live-browser-after-initial.json` retain
   the first pair. No gate, retry, rework or chat action was invoked. After login,
   the recorder allowed only GET/HEAD requests to the app; zero blocked mutation
   attempts were observed. Normal application startup hooks ran against the
   disposable database; this is not a claim that app startup makes no DB writes.

The first mobile script incorrectly compared lowercase text to CSS-uppercased
`PENDING`; it failed while desktop passed. Only the recorder assertion changed.
The rerun passed both checks. Screenshot review then revealed the mobile table was
below the recorded viewport despite its DOM assertions passing. A final mobile-only
session added scroll-into-view and a viewport geometry assertion. That passed and
its screenshot visibly shows the pending columns. Earlier recordings are retained
as superseded test-harness evidence, not product bugs.

### Videos and traces

Video includes login with a masked password field. Tracing begins after login to
avoid recording the login credential payload. Traces remain local; the temporary
signing secret is discarded when the server stops. No media was uploaded or given
a fleet execution identity. Times are offsets from session start.

| Session | Video / trace | Timeline | Result |
|---|---|---|---|
| 7, actual desktop | [video](media/local-dev-authenticated-desktop.webm) / [trace](media/local-dev-authenticated-desktop.zip) | 0:02.16 login redirect; 0:02.73 authenticated; 0:03.66 lanes; 0:05.22 matrix; 0:07.57 scout prompt; 0:08.36 tool calls; 0:09.19 memory; 0:10.76 story prompt; 0:11.56 tool calls; 0:12.39 memory; 0:13.59 pending run | Passed |
| 8, initial actual mobile | [video](media/local-dev-authenticated-mobile.webm) / [trace](media/local-dev-authenticated-mobile.zip) | 0:01.78 matrix loaded; ~0:02.6 case-sensitive assertion | Recorder assertion failed |
| 9, actual desktop retest | [video](media/local-dev-authenticated-desktop-retest.webm) / [trace](media/local-dev-authenticated-desktop-retest.zip) | 0:01.72 login redirect; 0:02.24 authenticated; 0:03.05 lanes; 0:04.55 matrix; 0:06.83 scout prompt; 0:07.63 tool calls; 0:08.46 memory; 0:09.69 story prompt; 0:10.46 tool calls; 0:11.29 memory; 0:13.02 pending run | Passed |
| 10, actual mobile retest | [video](media/local-dev-authenticated-mobile-retest.webm) / [trace](media/local-dev-authenticated-mobile-retest.zip) | 0:01.73 matrix loaded; 0:02.56 horizontal scroll while table below viewport | DOM assertions passed; visual coverage superseded |
| 11, final actual mobile | [video](media/local-dev-authenticated-mobile-verified.webm) / [trace](media/local-dev-authenticated-mobile-verified.zip) | 0:02.39 login redirect; 0:03.05 authenticated; 0:03.82 real matrix; 0:04.68 visible pending columns | Passed, visually verified |

`live-browser-results-initial.json`, `live-browser-results.json` and
`live-browser-mobile-verification.json` preserve exact timings, source hashes,
video SHA-256 hashes, errors and blocked-request lists. The final desktop video
SHA-256 is `8ca252caf836a4eae92667b623288eaea96c14c7d7386df35ca0ef28d29056ab`;
the final mobile SHA-256 is
`9faf4a6116b564243fd9b41943d1c7d64997dc0ec01aaa9edc1b2564b922fb6a`.
Final screenshots are `media/local-dev-authenticated-matrix.png`,
`media/local-dev-authenticated-drawer.png` and
`media/local-dev-authenticated-mobile.png`.

Reproduction scripts: `run-live-browser.ps1`, `live-browser-state.py`, and
`tools/qa-recorder/agent-infrastructure-live.mjs`. Runtime paths, service location,
database URL and target run ID come from environment variables. The launcher
generates process-only login credentials and always stops its service in cleanup.

### Scope, gate and memory

The authenticated local dev blocker is resolved for this supplied disposable
environment. **Five actual-application sessions plus six fixture sessions were
recorded; zero registered 04-qa-dev stage executions were created.** No stage was
advanced, approval written, deployed environment verified or branch committed by
this QA agent. The actual Azure execution results belong to the parent's separate
integration report; this browser round confirms their existing UI/DB artifacts.
No new product finding was discovered. Local engineering QA is PASS-WITH-NOTES;
the report does not decide a fleet QA gate or certify later infrastructure changes.

No open question remains for this completed local scope. Live downstream validation
content awaits its normal approved stage sequence. The actual `append_memory` tool
still is not exposed to this QA session, so no QA memory write or rendered-memory
edit is claimed. Candidate learning: "2026-09-10: Pair browser DOM assertions with
recorded viewport geometry, because a below-fold table can satisfy text assertions
without ever appearing in the review video." Any parent memory write has separate
evidence and must not be inferred from these rendered drawer memory rows.

Status: PASS-WITH-NOTES

## Round 5 — execution provenance UI, 2026-09-10

Independent QA of the continuation's AC-10/AC-11 display contract. This section
is local engineering evidence, not a registered QA execution or gate decision.
The test charter was extended before execution. Production drawer/CSS/renderers
were exercised with explicit synthetic rows through the existing fixture harness;
the fixture labels remain visible and no fixture database rows were inserted.

Matching controller receipt: tested commit/tree, worker image, manifest SHA-256
and requirement-to-test names render. A forged gate.json mirror, stale attempt
receipt and cross-run receipt each retain the explicit no-verified-manifest label.
Refresh/back retain that result. Unicode and HTML-shaped test names remain text.
The mobile check requires the full evidence section and hashes inside the viewport,
then repeats the visible section after a theme switch. All checks pass.

Independent Python controls: `provenance-renderer-tests.py` ran 12 passing tests
(nine existing drawer controls plus cross-run identity, malformed output string
and literal test-link names), recorded in `provenance-renderer-tests.log`.
These fixture/unit passes do not prove controller generation, semantic coverage,
artifact integrity, recovery, or any deployed service's behavior.

| Session | Video / trace | Recorded scenario offsets | Result |
|---|---|---|---|
| 12, initial fixture desktop | [video](media/provenance-fixture-desktop.webm) / [trace](media/provenance-fixture-desktop.zip) | 0:00–0:06 matching/forged/stale/cross-run receipts and refresh | Passed; final recording below repeats it |
| 13, initial fixture mobile | [video](media/provenance-fixture-mobile.webm) / [trace](media/provenance-fixture-mobile.zip) | 0:00–0:03 mobile geometry, theme switch | Passed assertions; final screenshot initially returned to header after theme click |
| 14, final fixture desktop | [video](media/provenance-fixture-desktop-final.webm) / [trace](media/provenance-fixture-desktop-final.zip) | 0:00.14 matching receipt; 0:01.23 forged mirror; 0:02.33 stale receipt; 0:03.42 cross-run; 0:04.56 refresh/back | Passed |
| 15, final fixture mobile | [video](media/provenance-fixture-mobile-final.webm) / [trace](media/provenance-fixture-mobile-final.zip) | 0:00.18 mobile evidence geometry; 0:01.25 evidence scrolled into view after theme switch | Passed, screenshot visually inspected |

`provenance-browser-results.json` and `provenance-browser-results-final.json`
contain exact source hashes, video hashes and event times. Final videos fully
decode with ffmpeg: VP8, 1280×720, desktop 7.12 seconds, mobile 4.12 seconds.
The final mobile screenshot is [here](media/provenance-fixture-mobile-final.png).
The fixture service was stopped. The screenshot correction changed only the
recorder, not the product; no new product bug was discovered in this scope.

The QA session has no exposed append_memory tool. No rendered memory file was
edited and no insertion is claimed. Candidate pending the actual memory path:
"2026-09-10: Pair negative provenance tests with a matching controller receipt
and forged writable mirror, because an always-unverified UI can falsely pass
negative checks without ever displaying valid evidence."

### Round 5 actual authenticated application

The integrator supplied credentials through the launcher process environment.
`run-provenance-live.py` copied current source to a separate temporary harness,
copied the existing Azure-produced run artifacts, generated process-only login
credentials, and launched the actual Mission Control application against disposable
Postgres. This was a real authenticated application session with real execution
rows, distinct from the renderer fixture sessions above. No application response
was stubbed and no receipt, approval or execution row was manufactured for QA.

The desktop session verified anonymous access redirects to login, then logged in.
Desktop and mobile opened executions 11 and 12 of
`feat-20260910-live-inprocess-leased-isolated`, scrolled the evidence messages into
the viewport, refreshed, and returned to the run. Both accurately display that no
verified manifest was recorded. The succeeded story envelope and memory display
remain separate from this unverified provenance label. The mobile screenshot was
visually inspected; the label is fully visible.

| Session | Video / trace | Recorded scenario offsets | Result |
|---|---|---|---|
| 16, actual desktop | [video](media/provenance-actual-desktop-leased.webm) / [trace](media/provenance-actual-desktop-leased.zip) | 0:00.73 login redirect; 0:01.97 authenticated; 0:02.93 execution 11; 0:05.66 execution 12; 0:08.60 return to run | Passed |
| 17, actual mobile | [video](media/provenance-actual-mobile-leased.webm) / [trace](media/provenance-actual-mobile-leased.zip) | 0:02.04 execution 11; 0:04.56 execution 12; 0:07.02 return to run | Passed, visually inspected |

`provenance-live-results.json` records exact UI source/video hashes, timestamps,
zero browser errors, zero HTTP errors and zero blocked mutation attempts. Traces
start after login to exclude the credential payload. Video records the masked
password field. Both WebMs fully decode: VP8, 1280×720, desktop 9.36 seconds and
mobile 7.32 seconds. [Mobile evidence screenshot](media/provenance-actual-mobile-12.png).

`provenance-live-before.json` and `provenance-live-after.json` are identical:
executions 11/12 remain succeeded, the run remains waiting_gate at 00-story.write,
and approval 4 remains pending story_signoff with no deciding person or timestamp.
The launcher stopped its service. Normal application startup ran against disposable
data; this does not claim the application's startup has no database writes.

The 20 existing Mission Control route tests also pass, including the execution
trace badge test against factory-generated traces; see `provenance-route-tests.log`.
Total final Python suite evidence in this round is 32 passing tests (12 drawer,
20 routes), not a whole-repository check. An earlier standalone nine-test drawer
run also passed and is included in the 12-test suite rather than counted twice.

No new product bug was found. Six browser contexts were recorded in this round;
four are fixture contexts and two use the actual application. No registered QA
execution, fleet approval, deployment or QA memory insertion is claimed. Positive
verified-provenance display is fixture coverage; these actual story executions
establish the honest absence path only. Runtime manifest generation/tamper checks
and recovery/Azure integration remain the integrator's separately identified
evidence. This round does not certify changed runtime source after its snapshot.

Status: PASS-WITH-NOTES
