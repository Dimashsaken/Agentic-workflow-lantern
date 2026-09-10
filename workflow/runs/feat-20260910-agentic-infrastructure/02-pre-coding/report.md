# Stage Report: 02-pre-coding — feat-20260910-agentic-infrastructure

- **Agent/author:** pre-coding, independent local planning consult
- **Date:** 2026-09-10
- **Status:** BLOCKED

## Summary

Prepared a concrete next-increment approval package for isolation, renewable leases,
restart recovery and execution-linked evidence. Overall risk is high; the riskiest
change is separating gate/publication authority from product-executing processes.
Implementation needs the proposed plan and recovery schema approved first.

## Work performed

Read the role charter, skills and memory, AGENTS.md, runboard, continuation plan,
prior coding/QA records, architecture plan/assessment, D23/D24 and orchestration
contract. Inspected actual dispatcher, sandbox entrypoint/image, gate, evidence,
journal, builder/review and schema consumers plus relevant tests.
The actual checkout is the target explicitly named by the user; no target was
guessed. This local record has no product mount, approved story, research envelope,
UX outputs or gate decisions, so this package does not claim a completed registered
pre-coding stage or a machine-validated story-to-plan mapping.

## Findings / results

1. High: writable harness copy and shared controller/worker privilege remain
   separate from existing file-tool policy; real containment needs an OS boundary.
2. High: startup requeues all executing runs for the runner; renewal/fencing must
   cover run advancement and child executions, including reviews and babysitting.
3. High: external publication is not made exactly-once by a lease; persist intent,
   reconcile target state and hold uncertain outcomes.
4. Medium: existing artifact JSON metadata can store provenance without a new
   manifest table; historical records remain explicitly unverified.
5. HITL: required for architecture/task plan and recovery schema; independent
   security pre-review applies to credential/data-access boundaries.

## Artifacts

- `blast-radius.md` — inspected paths, consumers, risks and authority boundary.
- `schema-plan.md` — additive lease/effect proposal, forward/rollback and rollout.
- `task-plan.md` — proposed AC-7 through AC-12 and ordered bounded increments.
- `plan-proposal.json` — typed proposal, explicitly unapproved and not a fleet envelope pass.

## Handoff notes for the next stage

Continue already-authorized baseline verification and fixes while the plan is
reviewed. After plan approval, isolation and manifest work can proceed independently
of schema approval; recovery tasks cannot. No migration, runtime implementation,
approval, deployment or commit was performed by this planning consult.

## Open questions

Do you approve this proposed task plan and the additive lease/effect schema in
`schema-plan.md` for the next infrastructure increment?

## Memory candidates

Candidate, pending actual append tool: 2026-09-10: Plan execution fencing at both
run-dispatch and child-execution boundaries because parallel builders and review
attempts can outlive a dispatcher; fencing only stage completion leaves stale run
advancement and publication possible.

No append_memory tool is exposed in this consult. The parent session is investigating
database access and can append with an honest manual identity; no database-backed
memory insertion or rendered-memory change is claimed here.

Status: BLOCKED

## Continuation 3 architecture refinement — 2026-09-10

- **Agent/author:** pre-coding role, local planning consult
- **Status:** BLOCKED

### Summary

Prepared a schema-free plan for the remaining foundation work at baseline
`a64c229`, preserving the user's explicit target and existing local authorization.
Overall risk is high; the riskiest element is permitting external browser traffic
without exposing controller authority or other executions. Existing publication
completion can proceed while the human reviews the new maintenance, transport
and retention contracts.

### Work performed

Read role charter/skills/memory, AGENTS, runboard, isolation and continuation docs,
existing pre-coding plans, latest coding/QA/post-coding/security reports and the
actual ownership/publication/babysitter/evidence/checkout code and tests. The run
folder still has no registered story/research/UX/gate package; the explicitly
named local checkout supplies the product target, and the new JSON is a proposal
rather than a machine-approved fleet plan. No production implementation or DDL
was changed by this planning agent.

### Findings / results

1. High: publication combines branch and PR success; reconciling must bind exact
   GitHub repository/base/head and distinguish partial success. Complete existing
   task 9 with conditional ref updates and observed effects, never blind replay.
2. High / HITL: required: dedicated maintenance ownership must leave pipeline
   status and human decisions unchanged, cover direct CLI and scheduled calls,
   and fence its regate/fix/publication children.
3. High / HITL: required: a per-execution allowlisted QA gateway and trusted
   recorder/deployment observations need security pre-review before dependent
   implementation. Browser request interception alone is not containment.
4. High / HITL: required: retention needs shared worker-launch/cleanup exclusion,
   terminal ownership and verified mount absence before retirement. The initial
   default deletes only eligible disposable checkouts; evidence remains retained.
5. Schema: no new DDL, package or migration is proposed. Application of the prior
   lease schema to a live database still requires its existing human approval.

### Artifacts

- `continuation-3-task-plan.md` — contracts A–D, bounded tasks, controls and decision.
- `continuation-3-blast-radius.md` — opened paths, consumers and exact module ownership.
- `continuation-3-schema-plan.md` — existing storage, compatibility and rollback.
- `continuation-3-plan-proposal.json` — typed proposal with local AC-7–AC-12 mapping;
  not a replacement for the absent approved story/registered envelope.

### Handoff notes

The parent restored the existing configured PostgreSQL cluster non-destructively
and invoked the actual `append_memory` SDK tool with honest manual identities.
`../03-coding/configured-postgres-restored.json` records PostgreSQL 16.9 using the
existing data directory, unchanged 12 runs / 23 executions / 8 approvals and five
new role-memory rows. This planner read that evidence; it is supplied integration
evidence, not a second independently performed database restoration. No empty
cluster, migration, fake fleet execution or approval was created.

The sole runtime coder owns `github_publication.py`, `test_github_publication.py`,
pipeline publication sections and effect helpers. Dependent B–D implementation
waits for the exact local architecture decision and defensive security pre-review.
Do not postpone already authorized independent fixes or turn this local plan into
a staging approval. Context/output experiments remain behind foundation acceptance.

### Memory

Actual tool insertion completed by the parent: pre-coding row **52**, manual key
`manual:feat-20260910-agentic-infrastructure:pre-coding:pending-b31116864f6c`.
Learning: “2026-09-10: Model maintenance leases separately from stage-dispatch
leases when maintenance runs after approval, because reusing an executing-run
predicate can require changing pending-gate state and silently grant pipeline
authority.” No rendered memory file was hand-edited.

### Open question

Do you approve the schema-free local contracts B–D in
`continuation-3-task-plan.md` for dedicated fenced babysitting, an allowlisted QA
gateway with deployment-bound recording receipts, and lock-protected checkout
retirement, while preserving all live rollout and human approval gates?

Status: BLOCKED
