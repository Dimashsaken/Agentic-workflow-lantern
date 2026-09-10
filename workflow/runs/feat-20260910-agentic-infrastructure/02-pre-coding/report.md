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
