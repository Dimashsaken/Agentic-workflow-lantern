# Stage Report: 03-coding — feat-20260910-agentic-infrastructure

- **Agent/author:** Codex, developer session
- **Date:** 2026-09-10
- **Status:** PASS-WITH-NOTES

## Summary

Implemented the user-authorized infrastructure plan in
`docs/plans/agentic-infrastructure.md` on local branch `codex/agentic-infrastructure`.
This folder records local engineering evidence; it is not a database-registered
fleet execution and does not satisfy or decide a live pipeline gate.

## Work performed

Read the coding charter, skills, memory, runboard, architecture assessment,
decisions, orchestration contract and runtime code. Retained Azure OpenAI, the
Agents SDK and the fixed code-driven stage sequence. Added:

- Execution-bound file capabilities, generated capability documentation, role
  output ownership, protected harness artifacts and scoped design collection.
- A validated read-only Git grammar, protected-file exclusions for search/history,
  safe revision forms, Windows case handling, alias checks and preserved CRLF
  semantics. This filters conventional credential paths; it is not a secret scanner.
- Mandatory automatic-code tests, a quality configuration captured before the
  first model turn, typed gate-result checks, and scope inspection that fails on
  enumeration errors and includes both sides of a rename.
- Evidence paths and line resolution, review locations checked against the
  handoff's commit/diff, host-side checkout verification, and explicit report status.
- Incremental attempt diagnostics, available SDK partial errors/usage, redaction
  and failure classification. A transport retry cannot blindly replay a loop with
  tool calls. Failure cleanup preserves the known usage and closes resources.
- Structured evidence display in Mission Control, verifier controls in the eval
  report, SDK minor-version compatibility bounds, and rollout documentation (D24).

## Findings / results

The initial full configured test command passed. Independent local QA
confirmed three findings in the first implementation: Windows role/run aliases,
implicit Git credential-file reads, and a case-alias validation self-citation.
All were fixed; the unchanged independent reproduction now reports all eight
bypass booleans false. See `../04-qa-dev/adversarial-probes-before.txt`,
`adversarial-probes-after.txt`, `bugs.md` and `report.md`.

A subsequent full run caught a Windows CRLF regression from discarding global Git
configuration. Inspection now carries forward only a validated `core.autocrlf`
scalar. The original scope test and a new isolated global-config regression pass.

Final configured test/lint results are recorded in `local-quality.json` and the
complete `quality-test.log` / `quality-lint.log`. This record is explicitly marked
`fleet_execution: false`; its source hashes identify the tested local snapshot.

Final result: **384 unit tests passed, one Windows symlink test skipped** (385
total), plus passing standalone product-access and coding property scripts.
The configured test command exited 0 in 102.0 seconds. Lint (compileall and the
D20 eval/fingerprint check) exited 0 in 0.9 seconds. `git diff --check` passed.
The integrator reran QA's unchanged reproduction against the final source:
`local-probes-final.json` has all eight bypass results false.

| Criterion | Implementation and verification | Local verdict |
|---|---|---|
| AC-1 | `tool_policy.py`, actual SDK ToolContext calls, role/run interleaving, protected artifacts, exports, Windows aliases and hardlinks | Pass; real symlink creation skipped on this Windows host |
| AC-2 | `readonly_git.py`, disposable repositories, normal inspection and refusal cases, broad/history/wildcard secret-path controls, blob and alias cases | Pass |
| AC-3 | `factory.py`, missing/malformed/stale/contradictory gates, policy replacement before/during commands, renamed paths and failed Git enumeration | Pass |
| AC-4 | `evidence.py`, missing/empty/self/cross-run references, invalid lines, immutable review head/diff and Mission Control rendering | Pass |
| AC-5 | `ExecutionJournal`, actual SDK exception interface with injected model/DB boundaries; completed plus partial usage, absent usage, retries and both executors | Pass for tested process-level paths |
| AC-6 | Full configured checks, eval regeneration/fingerprint, independent QA reproduction and this handoff | Pass for local engineering; live gates remain unexecuted |

The labelled verifier controls accept zero of 14 invalid records and reject zero
of one valid record. Both an always-accepting and an always-rejecting verifier are
detected by the eval tests. The frozen plan score remains 1.00 on only two plans;
there are no scored validator-vs-QA examples. These numbers do not establish live
model performance or production false-acceptance rates.

## Artifacts

- `docs/plans/agentic-infrastructure.md` — acceptance criteria and ordered plan.
- `docs/DECISIONS.md` D24 — implementation, trust boundary and rollout decision.
- `docs/AGENT-CAPABILITIES.md` — generated policy inventory.
- `tools/evals/REPORT.md` — frozen metrics and verifier controls.
- `validate-local.py` — repeatable local configured-check runner.
- `local-quality.json`, `quality-test.log`, `quality-lint.log` — final check evidence.
- `local-probes-final.json` — the unchanged QA reproductions on the final source.
- `../04-qa-dev/` — independent local audit, findings and exact retest evidence.

## Deviations

The checked-in local virtualenv launcher references a missing Python installation.
Local tests use the bundled Python 3.12 runtime with the existing virtualenv's
packages loaded through a local, ignored `sitecustomize.py`.

Verification used bundled Python 3.12.14, installed `openai-agents` 0.22.0 and Git
for Windows. The SDK tool invocation and exception interfaces were checked against
the installed SDK. No dependency download, database migration or live model call
was required. One symlink test needs Windows privileges unavailable in this session.

The requested security subagent failed before conducting its review: the platform
risk check flagged the request for possible cybersecurity risk. No independent
security report or signoff is claimed. The QA agent completed a local regression
audit; its recorded dev-browser gate is BLOCKED because no real dev environment
was exercised. Neither status is converted into a pipeline approval.

## Handoff notes for the next stage

Deploy the host code and sandbox image together only after the normal review and
deployment gates. Old coding gate records without policy hashes no longer pass
new execution checks. Products need a meaningful `quality.test` configured before
automatic coding. Update quality policy in a separate reviewed change; do not
weaken it during a build/fix execution. New validation executions require resolvable
references; old prose artifacts remain readable in Mission Control.

This change is a tool boundary, not OS isolation or signed gate attestation. A
coding shell, an unrestricted MCP server, shared-user filesystem access, database
credentials and arbitrary secret content remain separate trust boundaries. File
and Git reference resolution does not prove test coverage or video provenance.
Hard process death before SDK return can still lose telemetry. Early setup
failures and full crash recovery need broader lifecycle work.

Recommended next implementation sequence:

1. Immutable harness mounts and authoritative host-side gate records, scoped
   credentials and constrained egress; verify on the actual execution image.
2. Renewable stage leases with fencing, restart recovery and streamed diagnostics;
   verify kill/restart and duplicate-effect scenarios against disposable Postgres.
3. Execution-stamped evidence manifests and requirement-to-test links, followed by
   live Azure and recorded dev-browser acceptance runs.
4. Context-budget management and SDK structured outputs using the resulting live
   evaluation corpus. Keep the deterministic stage graph and human gates.

No branch was published, no PR opened, no human approval written and no deployment
performed. The pre-existing untracked `.codex/` directory was left untouched.

## Open questions

No answer is needed to review the local implementation. Live rollout still needs
the normal environment, recorded QA and human gates described above.

## Memory candidates

Candidate durable learning: When restricting an existing command interface, test
normal behavior alongside refusals and preserve benign repository semantics;
otherwise a permission fix can turn valid work into a false gate failure.

The configured role-memory database timed out on a bounded read-only availability
check both inside and outside the sandbox. No `append_memory` insertion was made,
and the rendered memory file was not edited. This local engineering report is not
presented as satisfying the fleet's database-backed memory postcondition.

## Commit and continuation handoff — 2026-09-10

The user explicitly requested committing the completed files and a prompt for the
unfinished work. The tested source hashes still match `local-quality.json`; the
eval fingerprint was checked again. The commit includes implementation, tests,
evals and local evidence, plus `docs/plans/agentic-infrastructure-continuation.md`.
It excludes the pre-existing `.codex/` directory. No push, deployment or pipeline
approval is part of this commit handoff. Database-backed memory recording remains
unavailable as documented above and is included in the continuation prompt.

Status: PASS-WITH-NOTES
