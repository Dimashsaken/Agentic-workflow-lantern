# Continuation prompt: agent infrastructure and live verification

Continue Lantern's agent-infrastructure work from the local branch
`codex/agentic-infrastructure` in
`C:\Users\dimas\OneDrive\Documents\GitHub\Agentic-workflow-lantern`.
Inspect the actual branch and working tree before changing anything; preserve
unrelated changes, including the pre-existing untracked `.codex/` directory.

Read AGENTS.md and the applicable role charter, skills and memory in the required
order, then workflow/RUNBOARD.md. Read these handoff documents:

- `docs/plans/agentic-infrastructure.md`
- `docs/DECISIONS.md` D23 and D24
- `docs/research/agentic-architecture-assessment.md` (historical audit, with update)
- `workflow/runs/feat-20260910-agentic-infrastructure/03-coding/report.md`
- `workflow/runs/feat-20260910-agentic-infrastructure/04-qa-dev/report.md`
- `docs/ORCHESTRATION.md` and `docs/AGENT-CAPABILITIES.md`

The completed local implementation binds tool capabilities to executions, validates
Git inspection, fails closed on missing or weakened quality gates, resolves
evidence references, and preserves available failure diagnostics and usage. The
recorded baseline is 384 unit tests passing, one Windows symlink test skipped,
standalone property checks passing, and lint/eval fingerprint passing. Three
independent QA findings were fixed and the exact reproductions retested. Verify
the baseline rather than assuming it still describes the current checkout.

This artifact folder is a local engineering record, not a registered fleet run or
proof of live pipeline approval. Do not fabricate execution rows, signoffs,
recordings, memory writes or test results to make the pipeline appear complete.

Finish outstanding verification first:

1. Diagnose the Python environment, configured Postgres connectivity and Docker
   availability. The old virtualenv launcher pointed at a missing Python install;
   local checks used bundled Python 3.12.14 with installed Agents SDK 0.22.0 through
   an ignored sitecustomize shim. Repair or reproduce the setup without exposing
   credentials or silently upgrading the SDK beyond its compatibility bounds.
   Use a disposable database/product repository for integration tests.
2. Verify both executors against real Postgres and the actual sandbox image. Test
   normal execution, failed turns, partial usage, cleanup, stale/malformed gates,
   role boundaries, and Windows/Linux path behavior where supported. Distinguish
   injected unit tests from live integration evidence.
3. Run a small end-to-end stage sequence on the configured Azure deployment and
   perform recorded dev-browser QA on the changed Mission Control evidence view.
   Use the qa-dev role and the normal stage contracts; stop at real human gates.
4. Obtain independent post-coding/validation and defensive security review through
   permitted review tooling. The previous security subagent was rejected before
   review by the platform's cybersecurity risk check; that is not a completed
   review or a finding about this code. Do not bypass a tool rejection. Record any
   remaining block honestly and use an authorized reviewer when needed.
5. Once the configured database is reachable, record durable learning through the
   actual append_memory tool. The previous session made no insertion because both
   availability checks timed out. Never edit the rendered memory or runboard.

Then develop the next infrastructure increment, with concrete acceptance criteria
and the required plan/schema approvals before dependent changes:

- Separate the agent's writable product from the immutable harness and authoritative
  host-side gate records. Scope database/service credentials and constrain egress.
  Prove that the coding shell and MCP tools cannot modify gate authority; file-tool
  restrictions alone are not OS containment.
- Add renewable execution leases, fencing and explicit restart recovery. Preserve
  diagnostics during process death and define safe SDK resumption or replay rules.
  Prove kill/restart, stale-worker and duplicate-effect behavior on disposable data.
- Tie evidence manifests to execution identity and the tested code revision, with
  requirement-to-test links and positive/negative verifier controls. A file existing
  at a valid line does not establish its truth, test coverage or video provenance.
- After those foundations are verified, evaluate context-budget management and SDK
  structured outputs against a live baseline. Retain Azure OpenAI and the fixed,
  code-driven pipeline rather than introducing a new orchestration framework.

Use independently scoped role agents where the workflow requires them. Implement
and fix findings; do not stop at an assessment. Regenerate evals for prompt/gate
changes, run the configured checks, commit completed increments with the run ID,
and update the report with exact evidence, confidence limits and unresolved work.
Use the existing gate/confirmation mechanisms for any registered run. Prepare a
reviewable rollout package; keep staging/production deployment and merge decisions
with the human. If credentials or an environment are unavailable, continue useful
independent work and ask one precise question only when it blocks the next action.
