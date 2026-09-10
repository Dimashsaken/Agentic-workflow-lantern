# Stage Report: 05-post-coding — feat-20260910-agentic-infrastructure

- **Agent/author:** independent post-coding reviewer; subsequently assigned bounded lifecycle fixes
- **Date:** 2026-09-10
- **Status:** BLOCKED (formal pipeline review); provisional local review completed

## Summary

Reviewed the full implementation diff from main to `90e4fb6`, then verified the bounded executor lifecycle corrections in the updated working-tree diff. Three local findings are resolved with regression evidence. This is a local engineering review, not a registered fleet execution, independent validation signoff, or authorization to advance beyond QA.

## Work performed

Read role charter, skills and memory; AGENTS.md; runboard; implementation and continuation plans; D23/D24; architecture assessment; orchestration/capability contracts; coding and QA reports. Compared policy, Git grammar, quality gates, evidence resolution, execution journal, executors, review integration, Mission Control rendering, role instructions and eval changes against AC-1 through AC-6 in `docs/plans/agentic-infrastructure.md`.

The baseline run has no `00-story/story.json`, approved `02-pre-coding/plan.json`, baseline task-plan/blast-radius documents, or `03-coding/handoff.json`. The continuation plan is not a substitute for those formal artifacts. `validation.md` therefore records a local criterion assessment instead of fabricating a passing typed fleet validation envelope.

Executed independent lifecycle probes using Python 3.12.10, openai-agents 0.22.0 and MCP 2.0.0. The MCP control starts a disposable local stdio server using the actual installed client library; executor setup and failure probes inject database/model boundaries. These probes make no Azure requests and do not exercise Docker or real Postgres. An initial probe attempted the removed `mcp.server.fastmcp` import and failed before connecting; it was corrected to the installed MCP 2.0 low-level server API before the recorded before/after results.

## Findings / results

Line references below identify the corrected working tree; original failure sites are also given against `90e4fb6`.

| ID | Area | Severity | Tag | Evidence and resolution |
|---|---|---|---|---|
| R-1 | Setup resource lifecycle | major | fix-now — resolved | At `90e4fb6`, `pipeline.py:541-563` and `orchestrator.py:1795-1818` perform session/input/MCP setup before the cleanup boundary. `lifecycle-probes-before.txt:5` records writable coding state remaining after rejected inputs; line 10 records zero database closes and MCP cleanups after connect failure. The outer boundary now begins at `pipeline.py:515` / `orchestrator.py:1798`; `lifecycle-probes-after.txt` records null writable/branch state and one database close plus one MCP cleanup. Regression tests: `test_execution_journal.py:44`, `:57`, `:94`. |
| R-2 | Failure masking and cleanup completion | major | fix-now — resolved | At `90e4fb6`, `pipeline.py:608-618` lets failed usage persistence replace a model failure and uses gather without collecting all cleanup outcomes. Updated `pipeline.py:613-637` retains the primary error, awaits all cleanup results, reports cleanup errors safely, and clears all product execution state. `orchestrator.py:1887` likewise awaits cleanup results while preserving the primary execution failure. `test_execution_journal.py:70` proves the MaxTurnsExceeded error and 200 known input tokens survive ledger failure; `:132` proves cleanup failure is journaled and cannot mark success. |
| R-3 | Missing postcondition diagnostics | moderate | fix-now — resolved | At `90e4fb6`, `pipeline.py:622-626` checks finalization/postconditions after the journal exception handler; the trace can describe completed turns without the execution's actual failure. Checks now run inside the journal boundary at `pipeline.py:603-607`. `test_execution_journal.py:82` proves a missing-memory postcondition appears in the trace, preserves 75 known input tokens and never writes succeeded. `:112` verifies the ordinary success path records success only after MCP cleanup. |

All three fix-now resolutions were verified in the updated source diff and the executed tests. No debt-ticket or waiver was created. The suspected task-ownership problem with parallel MCP cleanup was **not reproduced**: the real installed SDK/MCP stdio control passed both sequential and parallel cleanup without captured exit-stack errors. It is not a finding.

`journal-retest.txt:17` records **14 tests passed**: the original seven tests remain and seven lifecycle regressions were added to the already configured suite. `git diff --check` passed after these changes. These bounded checks are not a new complete repository test run; the integrator owns the final full gate, eval regeneration and tested-source snapshot after concurrent work finishes.

## Compatibility and scope

No schema or approval behavior changed in the lifecycle correction. Azure OpenAI and the existing stage graph remain intact. Automatic coding's requirement for configured tests and fingerprinted gates is an intentional compatibility break documented in D24: deploy host and sandbox versions together. Legacy evidence prose remains readable in Mission Control, but new validator executions require resolvable references. Validation of deleted files remains file-level, with a null line, and review lines resolve against the committed handoff revision.

The original acceptance criteria explicitly distinguish file-tool policy from OS containment and resolvable references from truth/provenance. This review does not upgrade either claim. Shell/MCP containment, scoped credentials, renewal/fencing, hard-kill telemetry, execution-linked evidence and live sequence behavior remain subjects of the continuation increment. No finding here certifies those future implementations.

## Artifacts

- `validation.md` — local AC-1 through AC-6 evidence ledger and confidence limits.
- `lifecycle-probes.py` — independent setup and real local MCP cleanup controls.
- `lifecycle-probes-before.txt`, `lifecycle-probes-after.txt` — exact observed results.
- `journal-retest.txt` — 14-test regression log.

## Handoff notes for the next stage

The initial review was independent of the implementation author; the integrator subsequently assigned the three bounded lifecycle corrections to this reviewer. Consequently the corrections have automated regression verification but still need another reviewer's final assessment. Review against the final committed source, final full-suite/eval evidence and completed QA artifacts before any formal stage transition.

The parent integrator is collecting live Azure/Postgres/Docker evidence and the QA role is recording browser behavior. This report does not adopt their in-progress results as completed or independently verified evidence. No commit, merge, deployment, fleet approval or database execution row was created by this reviewer.

## Open questions

Which registered execution and approved intent artifacts should own formal stage-5 verification after the required dev QA completes?

## Memory candidates

2026-09-10: Exercise stage setup and teardown separately from model failures; a finally block beginning after MCP connect cannot clean partially initialized resources, and success must be recorded only after cleanup and usage bookkeeping.

This candidate was sent to the parent integrator for the actual `append_memory` path. This local review has no execution-bound append tool and claims no memory insertion; the rendered role memory was not edited.

Status: BLOCKED
