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
