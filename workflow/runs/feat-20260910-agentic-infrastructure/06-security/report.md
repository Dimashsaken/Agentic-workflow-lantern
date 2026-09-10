# Stage Report: 06-security — feat-20260910-agentic-infrastructure

- **Agent/author:** independent security reviewer, local engineering review
- **Date:** 2026-09-10
- **Status:** BLOCKED for formal stage completion; provisional defensive review completed
- **Recommendation:** **NO-GO for staging** pending the validation and release conditions below.

## Summary

Reviewed the infrastructure branch and current lifecycle corrections without finding a confirmed feature-introduced critical/high vulnerability. The code improves file capabilities, Git inspection, gate validation and failure diagnostics, but this review does not certify the proposed isolation/recovery implementation or a deployed environment. Continue local development and verification; this report neither authorizes deployment nor constitutes a fleet signoff.

## Work performed

Read the security charter, skills and memory in order, runboard, AGENTS.md, continuation and original implementation plans, D23/D24, architecture assessment, orchestration/capability contracts, coding/QA records, the proposed blast-radius/schema/task plan and independent post-coding report/criterion assessment. Reviewed the branch diff from `main` through `90e4fb6`, concentrating on every changed runtime boundary: tool_policy, readonly_git, evidence, factory, orchestrator, pipeline, review, Mission Control evidence rendering and eval enforcement; also examined their tests, role instructions and dependency delta. The subsequent working-tree lifecycle corrections were independently reviewed after the post-coding reviewer implemented them. Exact reviewed runtime hashes are in `source-snapshot.json`; later edits require a supplemental review.

Only the requirement `openai-agents[sqlalchemy]>=0.22` changes, to `>=0.22,<0.23`. `git diff main -- '*lock*' '*requirements*' '*package.json'` has no lockfile or package.json delta. No new package, package name, install script or committed transitive lock change was introduced. This is not an audit of an as-yet unbuilt image's resolved dependencies.

The upstream [0.22.0 release](https://github.com/openai/openai-agents-python/releases/tag/v0.22.0) and [package provenance](https://pypi.org/project/openai-agents/0.22.0/) identify the expected official package. The project's [security page](https://github.com/openai/openai-agents-python/security) returned no published advisories when checked. This does not establish that every transitive dependency is free of vulnerabilities or that a new image resolves the same packages as the local environment. No package installation or upgrade was performed by this reviewer.

Independently executed `tools/azure-runner/.venv/Scripts/python.exe -m unittest discover -q -s tools/azure-runner -p test_execution_journal.py`: **14 tests passed**, Python **3.12.10**, 4.788 seconds. See `lifecycle-review-test.log`. These are local tests using injected SDK/database failures, not live Azure, Docker or Postgres validation. No service exploit, external-target test, approval, deployment, commit or production access was performed. The earlier session's rejected security invocation was not a review; this newly authorized defensive review executed normally and did not bypass a tool rejection.

## Findings / results

No confirmed new critical/high security vulnerability was found. The following are severity-ranked release risks and design conditions, not claims that unimplemented future controls already exist.

| ID | Severity | Evidence | Concrete mitigation / closure condition |
|---|---|---|---|
| S-1 | High deploy risk — open validation gate | The changed postcondition contract rejects missing gates at `tools/azure-runner/factory.py:862`; Docker performs a second check at `tools/azure-runner/pipeline.py:747`. An actual sandbox-image result and target-environment credential/config inventory were unavailable at this review cutoff. `05-post-coding/report.md` also requires a final integrated source check. | Build and identify the exact image digest; validate both executors on disposable Postgres against the same source, including successful completion, failure usage, cleanup, stale/malformed gate refusal and Linux path cases. Publish the final integrated source hashes, quality/eval result and completed QA report. Roll host/image forward together. Do not use local unit passes as a substitute. |
| S-2 | Medium assurance limitation — explicit scope boundary | `tool_policy.py:65`, `:125` checks file paths; `factory.py:888` checks typed gate results; `evidence.py:33` checks reference existence/lines. These checks do not independently attest process isolation, the tested revision, or evidence provenance. The original plan and D24 explicitly bound their claims. | Retain these limited claims for the current increment. Implement the reviewed controller/worker and execution-manifest plan only after its required approval, and prove refusals through actual shell/MCP boundaries plus positive normal-operation controls. A typed worker record or content hash alone must not become host authority. |
| S-3 | Medium release reproducibility risk — open image inventory | `requirements.txt:1` now prevents a minor SDK jump, but it still permits patch/transitive resolution drift. `infra/sandbox/Dockerfile` resolves Python dependencies at image build; no updated lockfile captures the deployment resolution. | Capture installed package versions, provenance/advisory results and the image digest from the actual candidate image. Verify the tested SDK behavior on that image; promote that artifact rather than rebuilding it during deployment. Any dependency update gets its own reviewed inventory. |
| S-4 | Low operational limitation — durable memory pending | No execution-bound `append_memory` tool is exposed in this local review. The integrator reports that the configured fleet Postgres endpoint refuses connections; disposable integration memory rows do not satisfy this review's durable-memory requirement. | Append the dated learning below through the actual memory path using an honest manual identity when the configured database is reachable; retain insertion evidence. Do not create fake stage rows or hand-edit rendered memory. |

The lifecycle fixes close the independently reported setup/teardown defects: `pipeline.py:517` includes setup inside the journal/cleanup boundary; `:603` places postconditions inside failure recording; `:613` preserves the original failure if ledger persistence fails; `:625` awaits all cleanup outcomes before success. The container runner's `orchestrator.py:1798` and `:1887` similarly cover partial setup and connection cleanup. The independent 14-test rerun passed against the source snapshot. These changes preserve failure semantics and do not add a schema mutation or approval path.

The only changed Mission Control output is evidence formatting in `app.py:549` and `traceability.py:189`; rendered values still pass through HTML escaping. There is no new HTTP route, ID parameter or authorization handler in this delta. The existing human approval mechanisms and Azure provider selection are unchanged by these corrections.

## Architecture pre-review of the proposed next increment

The proposed `02-pre-coding` package has the right separation of authority and receives **conditional architectural support**, not implementation approval or a staging GO:

1. The controller must own immutable harness code, Azure/session/database access, gate results and publication. Product commands and shell-capable MCP tools need a distinct worker boundary with no controller credentials, authority mounts, Docker socket or host process access. Treat worker files, stdout and JSON as untrusted input. File-tool policy is not OS isolation.
2. Record a tested immutable revision/tree and refuse publication or evidence acceptance if code changes after testing. Broker requests must be bound to the current execution and fence, with allowlisted operations, confined paths and bounded output/resource sizes. Default-deny egress needs enforcement, not just proxy environment variables.
3. Lease fencing must cover run advancement, each parallel child/review execution, memory/artifact acceptance and external publication. Check ownership/fence/expiry transactionally. Use server time. On loss, stop accepting outputs and reconcile any publication already in flight.
4. An effect ledger is not a promise of exactly-once external execution. Stable operation keys must bind request content; uncertain provider outcomes require reconciliation or a human hold. Do not replay arbitrary MCP side effects or pending human decisions after restart.
5. Evidence should bind execution, test identifiers, source revision, artifact digest and recorder identity through trusted capture. Legacy files remain explicitly unverified. Test wrong execution, stale revision, substituted media and absent manifest alongside valid evidence; line existence remains a separate weaker check.
6. Drain old workers before lease activation. Preserve the effect ledger during a runtime rollback; removing it discards recovery evidence. The proposed schema is not applied or approved by this review.

These are preconditions for the future security review; implementation and live proof remain outstanding. No unrelated unpatched production-vulnerability details are recorded here.

## Evidence and review limits

The integrator's `03-coding/live-inprocess-2.json` records real Azure scout/story execution on disposable Postgres, ending at pending `story_signoff` with no decision actor. Its source hashes and execution/usage rows were inspected as supplied evidence; this reviewer did not repeat that live sequence. This proves that recorded sequence only. The integrator separately reported a live max-turns failure retaining usage; that report is not treated here as independently verified final-image evidence.

At cutoff, Docker image construction was still in progress and Windows entrypoint line endings were under investigation. No actual sandbox result, Linux containment proof, crash/restart/fencing proof or final provenance implementation was available. Formal story/approved-plan/handoff and registered security execution inputs are absent for this engineering folder. The local review cannot turn it into a completed fleet stage.

## Deploy-day checklist

- [ ] Record the release commit, immutable image digest, dependency inventory and full quality/eval result; resolve S-1/S-3 and re-review any later runtime changes.
- [ ] Confirm staging configuration and scoped credentials through a redacted inventory; verify Azure deployment access and Postgres connectivity from the candidate controller environment.
- [ ] Run disposable positive/negative executor and evidence controls against the candidate image; complete recorded QA and review its exact source/target identity.
- [ ] Obtain the required human plan/schema and staging decisions through the normal mechanisms. This report supplies none of them.
- [ ] Drain dispatchers/workers before coordinated host/image rollout. For future lease changes, apply only the approved measured additive migration and reconcile any existing in-flight effects before enabling new dispatch.
- [ ] Start with one disposable canary run and confirm report, memory, usage and host gate checks agree; verify it stops at the next real human gate.
- [ ] Stop dispatch immediately if a stale/contradictory gate is accepted, a stale worker can mutate authority, credentials appear in diagnostics, or code/revision evidence diverges. Preserve redacted diagnostics and effect records, then revert to the last verified host/image pair after reconciling active work. Never restore an old unfenced dispatcher over in-flight leased work.

## Open question

Which final release commit and successful candidate-image validation record should the supplemental staging review assess?

## Memory candidate

2026-09-10: Treat process exit, immutable tested revision and controller-owned records as separate evidence checks; typed worker artifacts alone cannot establish execution provenance.

Sent to the integrator for the actual append path. No insertion or rendered-memory edit is claimed; durable append remains blocked as S-4.

Status: BLOCKED

## Supplemental review — final executor/image corrections, 2026-09-10

Independently reviewed the additional working-tree changes after the initial snapshot:

- `infra/sandbox/Dockerfile:75` removes carriage returns at line ends from the copied entrypoint before applying executable permissions. The command operates on one fixed image path, accepts no caller-supplied shell expression, adds no dependency and leaves the existing privilege transition unchanged. The integrator reports the prior actual image failed on `bash\r`; the corrected image identifier is `sha256:933a9c0899dae9c9d7f73d5bcf76a5298e7eaccea83b17233d4d8d56e3682756`, also recorded in `03-coding/docker-isolation-controls.json`.
- `pipeline.py:518`, `:567`, `:620` and `orchestrator.py:1800`, `:1821`, `:1886` initialize and capture `selected_model` once. Cleanup/usage emission no longer performs a fresh model configuration lookup that could replace an earlier MCP setup failure. `record_usage` accepts a missing model; it does not invent usage. The amended negative control in `test_execution_journal.py:94` makes model lookup raise while asserting that the original MCP failure, connection close and cleanup survive.
- `pipeline.py:82` forwards the host's generic `LANTERN_MAX_TURNS` through the existing container environment allowlist. It uses the existing integer parsing/limit behavior at `orchestrator.py:1506`; it grants no new tool, credential, approval or publication authority.

No new security finding in these changes. Independently reran the updated journal suite: **14 tests passed in 3.410 seconds**, Python 3.12.10; `lifecycle-supplemental-test.log` records this local result. Updated reviewed source hashes are in `supplemental-source-snapshot.json`; the initial snapshot remains intact for its earlier evidence.

Inspected the newly supplied integration artifacts, without repeating their live calls:

- `03-coding/live-docker-1.json`: real Azure/Docker scout execution **7** and story execution **8** succeeded with **78,494** and **58,342** total tokens respectively. The run remains `waiting_gate / 00-story.write`; `story_signoff` is pending with no deciding actor.
- `03-coding/live-docker-partial.json`: the expected `MaxTurnsExceeded` at two turns failed execution **9** and retained **17,022** known tokens in both the failure trace and execution record. No gate opened. The artifact's `passed: true` means the negative-control expectation passed, not that the stage succeeded.
- `03-coding/live-docker-killed.json`: kill delivered; execution **10** and run failed, all usage counters remain null, and no gate opened. This confirms failure/unknown-usage handling for that kill; it is not renewal, fencing, recovery or safe replay proof.
- `03-coding/linux-tool-policy.log`, `linux-gate-integrity.log`, `linux-evidence.log`, and `linux-execution-journal-final.log` record **19 + 8 + 11 + 14 = 52** passing Linux controls. These are unit controls run in the candidate container, distinct from the live Azure stage records. `docker-isolation-controls.json` records separate clone/cleanup checks and explicitly sets `os_containment_claim: false`.
- The final `04-qa-dev/report.md` records authenticated local dev QA against the disposable database, including login redirect, actual execution drawers and a pending traceability matrix. Its before/after records preserve approval state. Later structured validation rendering still uses fixtures; there was no registered QA stage or staging deployment.

S-1 is **partially resolved**: candidate-container startup, live success/turn-limit/kill outcomes and Linux controls now have concrete evidence, and authenticated local dev QA is complete for its stated scope. Final integrated quality/eval results, source-to-release identity and staging environment inventory still need closure. The live JSON records do not themselves contain an image digest; release evidence must retain the link between their execution setup, reviewed source and promoted image. S-2/S-3 and the durable-memory condition remain unchanged; the proposed architecture/schema still awaits its required human approval.

Recommendation remains **NO-GO for staging**. This supplement approves no plan, schema, gate or deployment, and does not claim that the future isolation/recovery/provenance work has been implemented.

Status: BLOCKED
