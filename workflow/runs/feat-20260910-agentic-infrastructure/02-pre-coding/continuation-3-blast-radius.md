# Continuation 3 blast radius

Date: 2026-09-10. Observed branch `codex/agentic-infrastructure`, HEAD `a64c229`;
initial working tree contains only unrelated untracked `.codex/`, preserved.
Overall risk: **high**. The riskiest element is granting network access to a
browser worker while keeping controller credentials and other execution data
outside its reach. Maintenance publication and retention have separate races.

This remains the local engineering record explicitly targeted by the user. The
folder has no registered brief, story/research envelopes, UX stage or gate decisions;
the product is the explicitly named Lantern checkout, not a guessed product mount.
No artifact here pretends to be a registered fleet signoff. Existing local
authorization is recorded in `03-coding/report.md`, under “Next increment
authorization”; it permits the earlier concrete implementation/disposable-schema
plan, not a live migration or deployment.

## Opened existing paths and consumers

| Path | Action | Reason / consumers | Risk |
|---|---|---|---|
| `tools/azure-runner/pipeline.py` | modify | Publication CLI, dispatcher, media upload, checkout creation and daemon babysitter scheduling share the affected helpers | high |
| `tools/azure-runner/review.py` | modify | Manual and daemon babysitter paths, review/fix publication, regate, PR comments and transient clones | high |
| `tools/azure-runner/execution_leases.py` | modify | Effect intent and reconciliation currently store only request hashes; maintenance cannot satisfy the executing-run predicate | high |
| `tools/azure-runner/execution_runtime.py` | modify | Existing run/child scopes and finalization must stay distinct from maintenance ownership | high |
| `tools/azure-runner/isolated_tools.py` | modify | Worker launch, exact-label cleanup, network policy and launch/retention exclusion | high |
| `tools/azure-runner/evidence_manifest.py` | modify | Video identity validation, artifact hashes and requirement links; trusted gate and QA receipt consumers | high |
| `tools/azure-runner/trusted_evidence.py` | modify | Authority directory and immutable snapshot pattern to reuse for QA receipts and retention pins | high |
| `tools/azure-runner/orchestrator.py` | modify | Browser MCP construction and execution-bound tool/capture registration | high |
| `tools/azure-runner/schema.sql` | read | Existing JSON and lease fields suffice; do not modify without a new schema decision | high |
| `tools/azure-runner/test_execution_leases.py` | modify | Renewal and identity controls; supplement injected tests with real PostgreSQL concurrency | medium |
| `tools/azure-runner/test_review.py` | modify | Real temporary Git behavior, bounded fixes, human approval and direct CLI controls | medium |
| `tools/azure-runner/test_evidence_manifest.py` | modify | Valid and forged capture receipts; wrong identity/revision/outcome controls | medium |
| `tools/azure-runner/test_recovery_acceptance.py` | modify | Replace unsupported-babysitter assertion only when equivalent stronger controls pass; preserve leased legacy-Docker refusal | high |
| `tools/mission-control/traceability.py` | read / modify if QA receipt is shown here | Existing requirements view must not infer coverage from prose or artifact presence | medium |
| `tools/mission-control/test_traceability.py` | read / modify with view | Fixture coverage remains distinct from actual authenticated recorded QA | low |
| `tools/qa-recorder/README.md` | modify | Explain scripted versus stage MCP capture and new provenance limits | low |
| `tools/evals/check_pr.py` | modify | Include any new policy/receipt/ownership module in D20 fingerprint | medium |
| `docs/EXECUTION-ISOLATION.md` | modify | Update supported transport, maintenance, cleanup and rollback only after verified implementation | medium |
| `docs/DECISIONS.md` | modify after approval | Record accepted boundary refinement without rewriting historical decisions | medium |
| `agents/coding/skills.md` | read | Preserve bounded tasks, defaults-off behavior and explicit deviation recording | low |

Existing path statements above refer to files actually opened in this planning
session. New files below are proposed creations, not claims about existing code:

| Proposed new path | Ownership / purpose |
|---|---|
| `tools/azure-runner/github_publication.py` | Sole runtime coder: GitHub observation parsing and effect orchestration, plus pipeline publication sections and execution_leases effect helpers |
| `tools/azure-runner/maintenance_runtime.py` | Runtime owner: maintenance lease eligibility, fencing and expiration |
| `tools/azure-runner/qa_transport.py` | Runtime owner: per-execution gateway policy and lifecycle |
| `tools/azure-runner/qa_provenance.py` | Runtime owner: controller capture/deployment observations and receipt validation |
| `tools/azure-runner/execution_retention.py` | Runtime owner: root inventory, exclusion locks, retirement and dry-run/apply |
| `tools/azure-runner/test_github_publication.py`, `test_maintenance_runtime.py`, `test_qa_transport.py`, `test_qa_provenance.py`, `test_execution_retention.py` | Same owner as implementation; adversarial behavior tests |

The runtime owner may retain helpers in existing files if that is simpler; any
different extraction must be recorded before implementation. Shared pipeline,
review, ownership and evidence files make parallel builders inappropriate here.
Independent QA and security/review roles should inspect a stable snapshot.

## Findings that affect sequencing

1. `_open_or_find_pr` selects the first open head match without complete base,
   repository and revision validation; retry also posts a comment. Read-only
   reconciliation must never produce a retry comment or label mutation.
2. `_publish_branch` falls back to unconditional force after a rejected push.
   Exact expected-old-head conditional publication is required to protect a
   concurrently changed branch. A database fence cannot revoke a request in flight.
3. The aggregate effect can be confirmed while PR creation failed. Branch and PR
   observations need separate outcomes so a later PR repair cannot replay push.
4. Babysitter eligibility is checked by the batch query, but the explicit run
   command reaches `babysit_run` directly. Both entry points need the same latest
   human-decision check. Reusing a historical approved row is insufficient after
   rework or a newer pending/rejected decision.
5. Current stage media upload identifies an attempt and digest but does not prove
   a controller-owned recording session or deployed code identity. File mtime and
   filename are not capture identity. Deleting a video after upload also requires
   remote digest/readback verification before it can satisfy retention policy.
6. Attempt-unique checkouts correctly refuse reuse but accumulate. A terminal DB
   row plus a Docker inspection is necessary but insufficient unless worker launch
   and retirement participate in the same lock and retirement protocol.

No new dependency is proposed: use Python stdlib, existing asyncpg, existing
Playwright/Docker/image tooling and current SDK bounds. Any added image/package
dependency needs developer signoff before installation. Principles most exposed:
keep authority checks simple, keep new modes off by default, and test observed
behavior rather than a worker-authored claim.
