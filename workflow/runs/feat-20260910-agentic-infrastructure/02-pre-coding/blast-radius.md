# Proposed next increment: blast radius

Date: 2026-09-10. Baseline inspected: `90e4fb6`, branch `codex/agentic-infrastructure`.
This is a local engineering proposal, not a registered stage or an approved work order.
The product target is the Lantern checkout explicitly identified in the continuation
request. No `product/` mount, story, research envelope, UX outputs or gate decisions
exist for this local record. The criteria below are proposed additions, not approved
story criteria. Existing AC-1 through AC-6 remain the earlier increment's contract.

Overall risk: **high**. The riskiest element is transferring authority away from
processes that execute product code while preserving every host publication and
human-gate path. A read-only harness alone does not isolate a same-user process's
credentials or prevent product tests from fabricating process stdout.

## Inspected implementation and consumers

Every existing path listed here was opened; paths classify proposed modifications,
not edits made in this planning session.

| Path | Action | Reason and consumers | Risk |
|---|---|---|---|
| `tools/azure-runner/pipeline.py` | modify | Both executors, dispatch, stage rows, host publication, usage, artifact registration, startup recovery | high |
| `tools/azure-runner/orchestrator.py` | modify | Tool construction, product shell, direct database memory/session access, postcondition verification | high |
| `tools/azure-runner/factory.py` | modify | Quality commands and records, journals, typed envelope verification; both executors consume it | high |
| `tools/azure-runner/review.py` | modify | Independent regate container, review/fix execution rows and merge babysitter publication | high |
| `tools/azure-runner/builders.py` | modify | Parallel child executions and integrator; single run lease must not serialize all builders | high |
| `tools/azure-runner/schema.sql` | modify after schema approval | Durable run/execution ownership and publication-intent tracking | high |
| `infra/sandbox/entrypoint.sh` | modify | Currently copies harness to writable `/work/lantern` and shares UID with tools | high |
| `infra/sandbox/Dockerfile` | modify | Trusted controller versus untrusted shell/MCP execution identities and immutable runtime | high |
| `infra/sandbox/prove_isolation.sh` | modify | Current proof checks private workspaces and cleanup, not gate or credential authority | high |
| `infra/sandbox/prove_video.sh` | modify | Capture, decode and execution provenance controls on actual image | medium |
| `tools/azure-runner/evidence.py` | modify | Existing path/line resolution becomes a component of provenance validation | high |
| `tools/azure-runner/tool_policy.py` | modify | Host artifact paths, controller-owned outputs and execution-specific tool requests | high |
| `tools/mission-control/traceability.py` | modify | Requirement/test/execution/revision links and explicit legacy/unverified presentation | medium |
| `tools/azure-runner/test_factory.py` | modify | Gate controls and host command-result validation | medium |
| `tools/azure-runner/test_gate_integrity.py` | modify | Wrong execution/revision and fabricated worker gate refusal | medium |
| `tools/azure-runner/test_execution_journal.py` | modify | Incremental durable events and uncertain usage | medium |
| `tools/azure-runner/test_verification.py` | modify | Real disposable-Postgres lifecycle, ownership and memory checks | high |
| `tools/azure-runner/test_coding_stage.py` | modify | Shell routing, cleanup and publication boundary | high |
| `tools/azure-runner/test_review.py` | modify | Review/regate/babysitter fencing and duplicate effects | high |
| `tools/azure-runner/test_builders.py` | modify | Child lease loss, sibling independence and stale integration refusal | high |
| `tools/azure-runner/test_evidence.py` | modify | Positive and negative provenance controls | medium |
| `tools/mission-control/test_traceability.py` | modify | New and legacy evidence presentation | low |
| `tools/evals/check_pr.py` | modify if new verifier modules introduced | Include every new policy/verifier module in fingerprint | medium |
| `tools/evals/REPORT.md` | regenerate | Required when gate/prompt/policy logic changes | low |
| `lantern.toml` | read | Preserve captured gate policy; any required quality-policy update is separate reviewed work | high |
| `tools/azure-runner/requirements.txt` | read | Existing SDK compatibility interval and dependencies | low |
| `docs/ORCHESTRATION.md` | modify | Recovery guarantees and unsupported replay conditions | medium |
| `docs/DECISIONS.md` | modify | Record approved boundary/recovery design, without renumbering historical proposals | medium |
| `docs/AGENT-CAPABILITIES.md` | regenerate if policy changes | Generated boundary inventory | low |

No runtime file was modified by this planner. No new package is proposed. Reuse
stdlib hashing/JSON/subprocess, existing asyncpg, Docker and the pinned SDK range.
Video decoding may require an image-level ffmpeg package; inventory the actual image
first and obtain developer sign-off for any new dependency before adding it.

## Required structure

Keep a trusted controller that owns Azure/session/database access, immutable harness
code, gate results and run advancement. Product shell and shell-capable MCP servers
execute in a separate untrusted worker container with only product and designated
output volumes. The worker gets no controller database URL, Azure/GitHub credentials,
Docker socket, host PID namespace or authoritative gate-store mount. Controller
tools broker only operations bound to an immutable execution identity. Merely
filtering a subprocess environment is insufficient when a sibling process can read
controller state. Use existing host regate architecture in `review.py` as the
exemplar, but record exits from the process/container boundary, not worker-emitted
JSON markers as proof of success.

Default worker network is disabled. Explicit per-role allowlists need enforced
network policy for approved QA targets or package endpoints; proxy variables alone
are not enforcement. Keep dependencies baked where possible. Do not advertise
in-process execution as OS containment: confine its product/MCP actions to the same
worker boundary or hold automatic coding when that backend is unavailable.

Run ownership covers dispatch and advancement; child ownership covers execution
completion, memory/artifact acceptance, publication and review. The startup blanket
requeue must be replaced only when all mutation consumers enforce the fence.
Unknown external MCP side effects remain high risk and cannot be auto-replayed.

## Validation and principles

Current tests use injected SDK/database boundaries and real temporary Git repositories;
they do not prove actual image containment or crash recovery. Add refusal and normal
operation cases together, then real Docker/Postgres kill/restart cases. Recorded
browser QA must exercise new/legacy evidence rendering, incorrect revision, missing
manifest and stale execution behavior. Preserve external gate waits exactly.

The coding principles most at risk are: handle failures at the boundary, imitate
existing host-side authority patterns, and keep each task independently reviewable.
This touches credential and data-access boundaries: independent defensive security
pre-review is required before approving its architecture, as well as normal final review.
