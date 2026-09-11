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


## Increment 2 independent defensive review — 2026-09-10

Review target: uncommitted increment 2 relative to `7f01faad1c9cfbef886026906f9a3e8631632a74` on `codex/agentic-infrastructure`. This appendix supersedes neither the historical evidence nor human gates. **Recommendation: NO-GO for staging.** Local remediation and verification can continue. The source is still changing; fixes below require a supplemental verification before closing findings.

Read security charter, skills, memory, AGENTS.md, runboard, continuation plan, next-increment blast radius/schema/task plans and prior post-coding/security reports. Reviewed the entire runtime delta, including new worker/routing, lease/runtime, durable-diagnostics, evidence-manifest and trusted-authority modules; factory, pipeline, builders, review, orchestrator, read-only Git, schema, eval fingerprint and Mission Control changes. No new HTTP route or authorization handler was added. New drawer values pass through HTML escaping. `git diff HEAD --name-only -- '*lock*' '*requirements*' '*package.json'` returned no dependency or lockfile changes for this increment. The earlier image inventory/reproducibility condition still applies; this is not a fresh advisory scan of all installed dependencies.

### Findings at this review cutoff

| ID | Severity / status | Evidence | Concrete mitigation |
|---|---|---|---|
| S2-1 | **High — reproduced; remediation in progress** | `factory.run_quality_gate`, `trusted_evidence.seal_gate` and `evidence_manifest.capture_product_state` capture source before/after commands while the same product mount is writable. Independent actual local subprocess probe committed `value.txt=ORIGINAL_FAIL`; the command wrote `TEST_PASS`, asserted against that value, then restored the file. Result: `gate_passed=true`, provenance `verified`, restored value `ORIGINAL_FAIL`, and `check_quality_gate=[]`. This probe used the existing adapter fixture with injected worker identity/routing, not Docker/Azure/Postgres. It demonstrates a source-identity gap, separately from semantic coverage. | Execute quality commands on a separately constructed committed-only snapshot, inaccessible to the original worker and mounted read-only. Do not copy product Git hooks/config or ignored executable inputs. Verify exact tested bytes, image and command observations. Add positive and modify-test-restore negative controls in actual Docker. Fail explicitly for unsupported writable-source builds; never silently fall back. |
| S2-2 | **Medium — open** | `orchestrator.make_append_memory` opens its own asyncpg connection, inserts into `role_memory` and renders it without checking a bound lease. A tool already in flight can finish after expiry and make stale learning available to future prompts. Existing stage completion fencing does not guard this insertion. The approved boundary discussion explicitly includes memory acceptance. | In lease mode, require the matching execution/run binding and fence the insertion transaction with the stage lease. Stale or absent ownership must fail; retain legacy manual behavior only when honestly outside leased execution. Add expired-owner negative control and normal append control. |
| S2-3 | **Medium — open** | `pipeline.publish_coding_branch` keys intent by run/head and hashes run/head/branch, while `_publish_coding_branch` resolves repo/base separately afterward. Target repo/base is absent from the intent. A repointed run can reuse a confirmed result for a different target or publish against a target different from its recorded intent. | Capture canonical repo/base/work/head once, include them in the effect request, and use that same captured target for publication. Reject mismatches. Keep uncertain effects held until actual provider state is inspected. |
| S2-4 | **Medium operational boundary — partly mitigated** | Initial review found shared process-global product environment across concurrent host stages and `product_checkout` reusing `checkouts/<run_id>`. The integrator added `INPROCESS_STAGE_LOCK` around the complete stage scope/setup/cleanup at `pipeline.py:521-529`; independently checked this source mitigation. Host stages now serialize, preventing that same-process environment race. Reusing the same checkout path still complicates retries if an old worker survives cleanup failure. | Keep serialization until product context is fully request scoped. Use execution-specific checkout paths and prove retry cannot mount/delete another attempt's tree. Do not describe host builders as concurrently isolated merely because their database connections and leases are separate. |
| S2-5 | **Medium rollout incompleteness — open** | Strict worker networking is intentionally `none`; external QA and Paper are held. Lease mode disables automatic babysitting. Publication uses a thread whose in-flight Git/API effects cannot be revoked by task cancellation. The manifest library can validate video records, but this does not establish execution-bound trusted capture for every normal QA path. | Retain explicit opt-in limits. Complete reviewed egress/target access, fenced babysitting and provider-specific reconciliation before enabling the full production pipeline. Bind normal recorder sessions and accepted media to executions; inspect recorded QA against the final source. Never call a local ledger exercise exactly-once GitHub publication proof. |

No host escape, credential exfiltration or approval bypass was demonstrated by this reviewer. Docker daemon and the configured image remain trusted infrastructure; absence of those exploit observations is not proof against arbitrary kernel/container vulnerabilities.

### Independently executed checks and inspected live records

Independently ran `test_execution_runtime.py`: **28 tests passed in 4.298 seconds**; `test_tool_execution.py`: **11 tests passed in 0.049 seconds**, using Python 3.12.10. These injected/local controls are not live database or Docker validation. The source-substitution probe above used a real local subprocess and disposable Git repository; its output was observed directly in this review. No external service mutation or approval decision was made.

Inspected supplied records without repeating their Azure calls:

- `03-coding/live-leased-isolated.json`: actual Azure/disposable-Postgres scout execution **11** and story execution **12** succeeded, with **49,737** and **167,617** total tokens; `story_signoff` remains pending, `decided_by=null`, and two disposable memory rows exist. These are not a formal engineering-run approval or durable configured-fleet learning.
- `03-coding/live-controller-recovery.json`: actual controller kill after one completed Azure response retains **8,111** known tokens, fsynced partial tool diagnostics and `incomplete=true`. Execution **13** goes from running to failed; no gate opens; exact labelled container `3886407da45f00fa83425caf803d0096318296415f6f49aba5f17fb4c9a0bbfa` is removed. This supports a conservative hold and known-usage lower bound, not replay or external publication recovery.
- `03-coding/isolated-worker-controls.json`: candidate image `sha256:933a9c0899dae9c9d7f73d5bcf76a5298e7eaccea83b17233d4d8d56e3682756`; real shell and MCP transport controls report only product/media mounts, UID 1000, blocked sentinel authority paths and egress, no controller credential sentinels, successful scoped writes, binary Git transport, timeout/background cleanup and read-only product control. SDK MCP browser control is a container-local data URL; its VP8 1280x720 recording is **1.520 seconds**, digest `07e3566acd19ac6252787a013498a8de08cc8cfa2e44fba5d7fe4d6439f9b3e1`. It proves that offline fixture, not deployed target QA.
- `03-coding/live-trusted-evidence.log` records an actual Docker quality command and tamper refusals, with no Azure/database use. It predates closure of S2-1 and cannot establish immutable test-time source on its own.

The records identify source snapshots; later integration fixes require fresh targeted evidence. No measured production-size migration lock duration, staging configuration validation, normal external authenticated QA under strict isolation, or live GitHub reconciliation proof is claimed. Formal fleet inputs and recorded human gates remain absent for this engineering folder.

### Deploy-day checklist for a later human release

- [ ] Resolve S2-1 through S2-3 with independent regression review; document/close S2-4 and S2-5 according to the enabled scope.
- [ ] Freeze release commit and image digest; rerun configured checks/evals and recorded QA after the final runtime changes. Preserve exact source/evidence hashes.
- [ ] Verify target Azure deployments, durable Postgres, scoped QA connectivity and authority/diagnostic filesystem permissions from the candidate environment without logging credentials.
- [ ] Drain all old dispatchers/workers; inventory existing active rows and ambiguous effects. Mixed unfenced/fenced dispatchers are unsupported. Apply only the human-approved additive migration with bounded locks/timeouts and measured row counts.
- [ ] Enable only the tested executor/flags and use a disposable canary that reaches its actual pending human gate. Verify report, memory, known usage, manifest and child/run ownership agree.
- [ ] Stop dispatch on stale acceptance, source mismatch, wrong-target publication or failed worker cleanup. Preserve the effect ledger and diagnostics; reconcile external state before retry. Roll runtime back only after draining; retain additive schema/effect records unless their removal is separately approved.
- [ ] Keep staging deployment, production signoff and merge actions with the human through existing gates. This review decides none of them.

### Memory postcondition

Candidate learning: **2026-09-10: Before/after source hashes cannot establish what a test executed when that source remains writable; use a separate read-only committed snapshot and separately fence every future-authoritative write, including role memory.**

Sent to the integrator for the actual `append_memory` path. Configured durable Postgres at localhost:5432 remains unavailable, and this review has no registered execution to impersonate. No rendered memory edit, fake execution or successful durable append is claimed. This postcondition remains blocked.

Status: BLOCKED


## Supplemental verification of increment 2 fixes — 2026-09-10

Independently read the snapshot construction and verification implementation, then reran the opt-in real Docker regression: `test_trusted_evidence.py FactoryGateHooks.test_real_isolated_worker_quality_gate_and_tamper_controls -v`, with `LANTERN_LIVE_EVIDENCE_TEST=1` and the candidate image. **1 actual Docker test passed in 90.239 seconds.** No Azure or database was used by this test.

**S2-1 is resolved for the tracked-source quality gate.** `trusted_evidence.quality_snapshot` builds a separate committed-only tree, checks blob/tree/commit hashes, writes fresh minimal Git metadata, excludes ignored dependencies and stops the writable preparation worker before running any quality command with a read-only source mount. The original worker cannot access the new source/output directories. `seal_gate` requires this controller-created snapshot, and verification rejects earlier manifests lacking the snapshot record. There is no writable-source fallback.

The independent Docker observation recorded:

- Image `sha256:933a9c0899dae9c9d7f73d5bcf76a5298e7eaccea83b17233d4d8d56e3682756`.
- Tested commit `96d1d540e74d6e6f2ee942db5138cf8ed1b4ea2e`, tree `331abb9014a861416a20f39b17458bff77879fe3`, worktree digest `6ea129319f1d048bf7715354827301c517efd67a24679f4ce4ac17903e683be7`.
- Manifest digest `ea78e4cd3b51eb2a4dfc0a9d638d4b0944f59006eadfae85cdb1328e8821eb65`; harness dirty-source fingerprint `1e7951cafd223789f5f2b4f6bc6c9515053c7ef9e99ad1bec149e8c6dc971b53`.
- Positive command `python source.py` exited zero; ignored helper excluded; manifest/source tampering rejected. The same modify/test/restore command passed against the mutable worker and failed against the snapshot with `OSError: [Errno 30] Read-only file system`; the original source remained intact for the fix loop.

**S2-2 and S2-3 are resolved in the reviewed source.** `make_append_memory` now inserts inside the current child-fenced transaction and verifies run/stage/execution-key identity. Publication intent now includes repo/base/work and passes the expected target to the helper; changed targets stop before starting the publication thread, and a changed handoff head is rejected. This still does not revoke in-flight provider requests or prove live GitHub reconciliation.

**S2-4 is resolved for the supported serialized host executor.** Runtime checkout paths use the full execution-key hash and refuse reuse rather than deleting a previous attempt's mount. The complete host stage is serialized around its remaining process-global environment. Independent `test_recovery_acceptance.py` run: **6 tests passed in 1.020 seconds**; it checks unowned/wrong-key memory refusal and valid insertion, target mismatch before publication, distinct attempt checkouts, stage serialization, child artifact ownership and unsupported leased Docker/babysitter refusal. These are local/injected controls, with real disposable Git checkout operations; they are not live Postgres fence tests.

Additional stage-file hardening was reviewed: policy-approved product/media reads, writes, appends and directory listing now run inside the worker through an isolated Python helper using directory descriptors, `O_NOFOLLOW`, nonblocking opens and regular single-link-file checks. Reads/output are bounded. Independent `test_tool_execution.py` run after these additions: **15 tests passed in 0.034 seconds**. Supplied `isolated-worker-controls.json` includes actual Docker post-policy file/directory substitution refusals and an unchanged synthetic controller sentinel; this reviewer inspected the implementation and unit controls, without repeating that separate live race fixture.

Final local-pilot recommendation remains pending the in-progress output-collection review: model/MCP writers must be gone before bundle export and media reads, and planted links must be refused before any host-side upload. S2-5 and the staging prerequisites remain open. **Staging recommendation remains NO-GO.** Durable memory append remains blocked as previously recorded; no append or approval is claimed.

Status: BLOCKED


## Final bounded local-pilot verdict — 2026-09-10

**GO with conditions for the limited local pilot; NO-GO for staging.** No confirmed unmitigated high finding remains in the reviewed strict host-executor scope. S2-1 through S2-4 are closed as described above. S2-5, durable configured-memory completion and the target-environment release prerequisites remain open. This is an independent engineering recommendation, not a fleet stage signoff or human approval.

The final output-collection boundary was independently checked in source. After the last SDK/fix-loop turn, the controller cleans MCP and stops the original worker before finalization/export/postconditions. A separate, never-started worker object permits only controller-issued ephemeral inspection commands; each command is removed before its result is consumed. Final cleanup removes that worker before upload. Media collection uses the exact execution output root for strict stages, confines every candidate, refuses nonregular/multiple-link files and stages upload bytes in a private controller directory. Upload metadata records execution key and content digest. No actual S3 upload was performed; this is source and local regression verification. No live GitHub publication was performed.

The source hash reader now uses bounded, nonblocking regular-file reads; product policy reads have a 1 MB limit and source hashing a 64 MB per-file limit. Invalid/special/linked files fail closed. Quality snapshot capture retains its committed-object hash checks. Stage tools use the separately tested worker descriptor path. These checks support the stated isolation boundary; they do not certify arbitrary container escape resistance or semantic test coverage.

Final independent regression runs: **8 recovery-acceptance tests passed in 0.766 seconds**, and **17 execution-journal tests passed in 5.004 seconds**. The journal suite includes writer shutdown before postconditions/media; recovery controls cover attempt scoping, linked-media refusal and bounded source inputs. An earlier run of the new media test reported an exception-type mismatch: the implementation correctly refused a hard link with `PermissionError`, while the test expected `ValueError`. The assertion was corrected and the complete eight-test rerun passed. `git diff --check` passed. These local controls are distinct from the independent 90.239-second Docker snapshot proof above.

Conditions for the local pilot:

1. Use the reviewed strict host executor, the tested image digest and disposable database/product runs. Keep worker network disabled; Azure remains on the controller. Do not enable untested external publication, S3 upload, external QA/Paper or leased babysitting as part of this recommendation.
2. Keep host-stage serialization and unique attempt checkouts; stop and investigate any worker cleanup failure. Retention/garbage collection must avoid live mounts and remains a tracked operational task before sustained operation.
3. Complete the integrator's final full gate/eval and current-source Azure smoke before calling the increment complete. Those checks were in progress at this cutoff; this report does not predeclare their results. Re-review changes to the boundaries listed below.
4. Preserve every human gate. Before staging, close S2-5 and the deployment checklist, verify target configuration and migration behavior, finish recorded target QA and independent validation, and obtain the actual required human decisions.

Reviewed boundary source hashes at this cutoff:

| File | SHA-256 |
|---|---|
| `tools/azure-runner/pipeline.py` | `e9bfd71be2f12b8235ac650e822f1b98e5614c30571a6fb282997cae53db5bda` |
| `tools/azure-runner/orchestrator.py` | `4e474f99d4c34dd9b35bea8c6dc26b51ce59db3325358e407043c37937223ee0` |
| `tools/azure-runner/tool_execution.py` | `69fb952682dfece9e5d7aa09abb95bdbed0af42f9199ab9d3ca59c865a2fa33b` |
| `tools/azure-runner/isolated_tools.py` | `ee731cdb276d01ec3fac2646059ef9c6a394398a4906a0f5f401e30454f54970` |
| `tools/azure-runner/factory.py` | `d850780e3d03ec1ec41c8a619ba40632cd3afb4a14b5574cc41ee08129133cb8` |
| `tools/azure-runner/trusted_evidence.py` | `8f71f3b7dc12ed1ef124314e82f13c7c96dbacd0ce5bc26a941f8241647d16bc` |
| `tools/azure-runner/evidence_manifest.py` | `fe535050b67586a064cd068a34ad56b637d60b0a7cac551c7f12c38415a3fc11` |

Memory candidate remains the dated learning above. The actual durable `append_memory` insertion is still blocked by the configured database; rendered memory was not edited and no success is claimed.

Status: BLOCKED (formal stage / staging); bounded local pilot GO with conditions

## Continuation 3 defensive architecture pre-review — 2026-09-10

- **Agent/author:** security, independent reviewer
- **Scope:** continuation-3 contracts B–D; initial working branch `codex/agentic-infrastructure`, HEAD `4dec57a`, preserved concurrent publication/QA changes and unrelated `.codex/`.
- **Recommendation:** GO with conditions for continuing the previously authorized bounded local pilot; **NO-GO for staging**. This pre-review supplies constraints, not a human architecture approval or a completed implementation review.

Read the role charter/skills/memory, AGENTS, runboard, execution-isolation and continuation documents, upstream coding/QA/post-coding/security evidence, and all continuation-3 planning artifacts. The concrete B–D proposal is suitable for implementation after the pending human decision, subject to the constraints below. At this cutoff the dependent maintenance, external QA gateway/capture and retirement implementations do not exist; their acceptance cannot be inferred from this plan.

| ID | Severity / status | Evidence | Required mitigation / verification |
|---|---|---|---|
| S3-P1 | High, required implementation constraint | `02-pre-coding/continuation-3-task-plan.md`, B, proposes a maintenance lease independent of the stage-dispatch lease. A separate acquisition check without shared dispatcher/rework exclusion would still permit two owners. | Serialize all three paths under the same run-row lock, bind the latest applicable human decision and publication target, and revalidate before each authoritative write. Do not change run status/stage/approval to obtain maintenance authority. Test both CLI and daemon, superseded approval, competing owner and expired child with real disposable PostgreSQL. |
| S3-P2 | High, required implementation constraint | The same plan, C, proposes an internal browser network and a CONNECT gateway. A tunnel destination allowlist alone does not inspect encrypted HTTP Host; on shared infrastructure the tunnel endpoint can serve another logical origin. | Specify the enforced boundary explicitly. Validate/pin DNS answers per connection, reject private/reserved and alternative-address forms, constrain TLS destinations or document narrower IP-level trust, prevent worker direct egress, and cover redirects, subresources, service workers and cross-execution traffic. Prove direct sockets, DNS rebinding and shared-endpoint behavior on the actual image. Browser request hooks alone do not provide containment. |
| S3-P3 | High, required implementation constraint | The same plan, D, correctly identifies delayed worker launch as a race after a terminal-row/mount inspection. Prior debt LANTERN-DEBT-EXECUTION-GC does not by itself define an exclusion protocol. | Require the same controller-owned OS lock around allocation/launch/mount and retirement, an irreversible tombstone, complete relevant Docker mount inspection rather than labels alone, and same-filesystem identity-checked quarantine. Hold on unknown owner, DB/Docker failure or linked/aliased paths. Exercise simultaneous launch/deletion and interrupted quarantine only inside owned temporary roots. |
| S3-P4 | Medium, acceptance incomplete | The same plan, C/D, distinguishes a checkout SHA from deployment identity, recorder ownership from a filename, and evidence retention from disposable checkout cleanup. Current upstream reports explicitly lack full normal external QA capture provenance. | Obtain trusted deployment observations at recording start/end, controller-created recording identity, sealed media and observed requirement results. Preserve positive and negative verifier controls. Retain evidence indefinitely by default; no media deletion without separate policy and verified durable retrieval. |

These are pre-implementation hazards with proposed mitigations, not claims of reproduced exploitable production defects. No external mutation, migration, gate decision, deployment or destructive cleanup was performed by this reviewer.

### Evidence and memory update

`03-coding/configured-postgres-restored.json` records the existing configured PostgreSQL 16.9 database `lantern`, existing data directory `C:/Users/dimas/.lantern/pgdata`, unchanged 12 runs / 23 executions / 8 approvals, and five actual `append_memory` insertions. Security's previously pending learning is row **51**, execution key `manual:feat-20260910-agentic-infrastructure:security:pending-95f74faa9e13`. This is supplied configured-database evidence, not a restoration independently repeated by this reviewer, and not production certification. It closes the old durable-memory connectivity condition. No new cluster, DDL, fake stage or approval was introduced.

New memory candidate sent to the integrator for the actual tool: “2026-09-10: A cleanup eligibility check is not a concurrency boundary; worker allocation, launch and retirement must share an exclusion lock and irreversible tombstone, because a delayed start can mount a path after cleanup has inspected it.” The rendered memory file was not edited.

### Deploy-day checklist

- [ ] Obtain the pending local B–D architecture decision before dependent implementation; record it honestly without manufacturing fleet approval rows.
- [ ] Complete publication observation/fencing review and B–D implementation with the independent controls above. Preserve human approval and merge ownership.
- [ ] Freeze reviewed source/image identity; run configured quality checks/evals and recorded browser QA at that snapshot.
- [ ] Establish actual target GitHub/deployment/network evidence and image/dependency/configuration inventory; distinguish all simulations and disposable integrations.
- [ ] Drain dispatchers/workers before any human-approved live migration or activation; inventory uncertain effects, recovery holds and retained source/evidence first.
- [ ] Stop activation on stale write acceptance, wrong-target publication, failed isolation or cleanup. Preserve ledger/diagnostics and reconcile provider state before retry or rollback.
- [ ] Keep staging and production human gates pending until the full acceptance and release prerequisites are met.

**Open question:** Do you approve the schema-free local contracts B–D in `02-pre-coding/continuation-3-task-plan.md`, preserving the existing live rollout and evidence-deletion gates?

Status: BLOCKED (pending B–D architecture decision and incomplete foundation/staging acceptance)

## Continuation 3 publication security verification — 2026-09-10

**GO with conditions for the bounded local pilot; NO-GO for staging.** The reviewed publication increment now fails closed on stale or conflicting observed state. No confirmed unmitigated high finding remains in this bounded scope. It does not complete the continuation: split-effect repair, fenced maintenance, external QA capture and retention remain outstanding, with B–D awaiting the explicit local architecture decision.

Reviewed the complete current publication/runtime delta from `a64c229`, the entire new `github_publication.py`, lease helpers and tests, additive configured test command, and eval fingerprint change. The legacy PR helper no longer emits retry comments or labels; unconditional force-push fallback is removed. There are no dependency manifest or lockfile changes in this continuation, so no new package advisory/install-script assessment is applicable. This is not a fresh advisory audit of the existing image or installed packages.

### Severity-ranked findings and dispositions

| ID | Severity / disposition | Evidence | Mitigation and verified result |
|---|---|---|---|
| S3-1 | High, fixed before acceptance | Initial draft recorded branch/PR artifacts before the post-provider target/handoff recheck. Final `pipeline.py:1097` and `:1104` place target validation, effect acceptance and artifact/event writes in the same fenced transaction; `_publish_coding_branch` defers strict recording. | Regression `test_handoff_changes_during_provider_call_emit_no_authoritative_artifacts` passes: a changed handoff after provider work prevents effect confirmation and every publication artifact/event write, and preserves uncertainty. |
| S3-2 | High, fixed before acceptance | Initial draft reused publication output after `review.after_publish` without fresh observation. Final `pipeline.py:1373` re-observes repository/base/head/PR after review; final parent-fenced gate transaction rechecks current target/handoff. | Regression `test_gate_reobserves_after_review_and_holds_changed_provider` passes: provider movement during review opens no gate. This is a timestamped observation plus conditional branch update, not an atomic transaction spanning PostgreSQL and GitHub. |
| S3-3 | Medium, fixed for v2 intents | Initial draft bound names/head only and omitted durable expected-old/base/repository identities. Final `github_publication.py:58`, `:96`, `:161`; `execution_leases.py:207`, `:216`; `pipeline.py:1076` persist a v2 request before mutation, bind immutable repository ID/base SHA/expected old remote SHA, and hold legacy intents. | Independent controls reject repository replacement, moved base, mismatched PR repository/base, changed expected old head and destination changes. CAS pushes the immutable commit SHA with exact expected remote ref and no unconditional fallback. Duplicate effects perform reads only. Each response is capped at 4 MiB and pagination at 20 pages. |
| S3-4 | Medium, open acceptance limitation | `pipeline.py:1073` still uses one aggregate `publish-v2` effect. `github_publication.py:151` holds absent or partial effects; a push completed without a PR is not automatically repaired. This is narrower than continuation-3 contract A's split effect proposal. | Keep partial/legacy effects explicitly held and inspect provider state; do not delete/reset intent records to force a retry. Complete separately journaled branch and PR effects plus safe partial-repair/operator flow and integration controls before claiming full AC-9a or broader publication recovery acceptance. |
| S3-5 | Medium, open rollout limitation | B–D are plans, not implementations; current strict transport remains offline, leased babysitting remains held, and checkout retention debt persists. Recorded UI positive provenance is fixture evidence rather than a normal external deployment-bound recorder receipt. | Preserve the existing local-pilot restrictions and apply S3-P1–P4 after architecture approval. Finish real target validation, image/config inventory and human release gates before staging. Context/output experiments remain behind foundation acceptance. |

The destination/ref parser permits only explicit GitHub HTTPS destinations and separate `feat/`, `fix/` or `proto/` branch names. Observations reject malformed/conflicting data, pagination exhaustion, duplicate or closed PRs, mismatched head/base repositories, canonical URL mismatch and branch/PR disagreement. Every mutation checks current ownership/target; acceptance checks again. An API call already in flight cannot be revoked by a database lease, so loss of ownership or inconclusive observations must continue to hold. No exactly-once external effect guarantee is claimed.

### Independent checks at the reviewed cutoff

Executed using local Python 3.12.10:

- `python tools/azure-runner/test_github_publication.py`: **21 passed in 1.035 seconds**. Provider calls are mocked; the CAS test uses actual disposable local Git repositories and proves both concurrent update and unexpected creation refusal.
- `python tools/azure-runner/test_execution_runtime.py`: **33 passed in 2.743 seconds**, including both acceptance-order regressions above. Database/provider boundaries are injected.
- `python tools/azure-runner/test_recovery_acceptance.py`: **8 passed in 0.516 seconds**; existing memory/source/checkout/media/unsupported-mode controls remain intact.
- `python tools/azure-runner/test_execution_leases.py`: **8 passed in 0.113 seconds**, injected lease controls.
- Additional independent v2 fresh-publication/duplicate probe: prepared canonical request, observed exactly one mocked push and one mocked POST, then re-observed using GET only. Passed; no network or remote mutation.
- `git diff --check`: passed. The configured gate adds the publication suite and preserves every prior test/lint command and timeout. `github_publication.py` is included in D20 fingerprint inputs; the parent owns final full-gate/eval evidence.

An initial `publication-postgres-proof.json` was inspected: it records real disposable PostgreSQL and an actual killed subprocess, with simulated durable-file GitHub responses and unchanged approval data. Its hashes predate v2 finalization; it must be superseded by the integration owner's final-source rerun before serving as v2 acceptance. This reviewer did not repeat PostgreSQL, Azure, Docker, S3 or live GitHub operations in this round. Actual read-only GitHub observation, if supplied separately, is not publication/interrupt recovery proof.

Reviewed source SHA-256:

| File | SHA-256 |
|---|---|
| `tools/azure-runner/github_publication.py` | `2374ac01e3f862102eb77514011c53974bd28f23820335a27af6e6d75cdfdeb8` |
| `tools/azure-runner/pipeline.py` | `2713cbdfd8449c02e79e2b9783bece1154e8f6ccafa66beefc8c3ec7d5629284` |
| `tools/azure-runner/execution_leases.py` | `8693d056fd6daa506808bef6425ea9727fa09d40be30eddbb2bc4ac1c4825afd` |
| `tools/azure-runner/test_github_publication.py` | `ee7eebe937a833c9ce26735945e6daeb7c474031e0f0b2074ec15a180be7a2c6` |
| `tools/azure-runner/test_execution_runtime.py` | `10aa3e3dadfcf7295939d0e7c702ca7ba71e205b16b033ab4a6182aae67bca42` |

### Durable learning and release conditions

The new cleanup learning above was inserted through actual `append_memory`, configured database row **54**, key `manual:feat-20260910-agentic-infrastructure:security:pending-56e281d3530d`; receipt `03-coding/continuation3-memory.json` preserves unchanged run/execution/approval counts and approval snapshot, no migration and no new cluster. The parent performed this actual tool invocation with an honest manual identity. The previous pending row **51** and this row complete the security memory requirements; no rendered view was hand-edited by this reviewer.

The earlier deploy-day checklist remains mandatory. In addition, freeze the final v2 source/evals and rerun the disposable PostgreSQL proof; retain v1/aggregate ambiguous effects during code rollback; do not enable external publication or remove ledger records merely to escape a hold. Keep the existing offline pilot restrictions, staging NO-GO, and all human merge/approval/deployment ownership. This engineering review is not a registered fleet stage signoff.

**Open question:** Do you approve the schema-free local contracts B–D in `02-pre-coding/continuation-3-task-plan.md`, preserving existing live rollout and evidence-deletion gates?

Status: BLOCKED (full continuation / staging); bounded local pilot GO with conditions

### Final narrow hardening and evidence supplement — 2026-09-10

Independently verified the final PR parser refinement: nested repository IDs require exact integer type, and an open PR with a non-null `merged_at` is rejected as contradictory. The complete publication suite now passes **22 tests in 1.036 seconds**; this supersedes the earlier 21-test cutoff. The matching final module hash is `eea9c811e2d8db858b2174eb6608ee02b569d45151914331a2e95e97a9ec6a12`, and test hash is `5de4e58f8157aaf4b92845674694e769564acdbc09dee176a71b027598d30c5a`. Pipeline and lease source hashes remain unchanged from the table above.

Also reviewed `review._post_review_for`: lease mode now keeps the bot review in the run folder and returns before any provider review API call, because this side effect has no reconciled intent yet. Local review execution and human approval ownership remain intact. Independent `test_review.py` ran **36 passing tests in 12.204 seconds** with the established Windows test environment (`C:/Program Files/Git/bin` prepended to PATH, UTF-8 enabled). A prior plain-Windows-shell invocation failed two existing POSIX `test -f` fixture cases; both passed in the established Git Bash environment without code changes. Review source hash: `3d99e488fd1c5c4f90c4e8a0dc74a3b0f54fe638d8f07b1267a872bf6526a12b`; review test hash: `c42287d9697495584fd7672e5dd9c07d65a68ef1f7ed061dfab828b4423c4f7a`.

The integration owner reran `publication-postgres-proof.json` at these exact final module/pipeline/lease hashes: all **six controls pass**, database `lantern_publication_proof_b9910d8fd59c`, 12 simulated provider GETs, unchanged validation approval snapshot. This supersedes the stale proof limitation above. It remains actual disposable PostgreSQL and subprocess death with a simulated durable-file GitHub boundary, not live publication.

Inspected `github-readonly-validation.json`: actual configured bot credential receives repository/base GET 200, intended branch GET 404 and pull-request-list GET **403** (`Resource not accessible by personal access token`). The observer correctly holds; **zero provider mutations** occurred. This is actual read-only negative validation and identifies a real credential/target prerequisite for a future authorized publication test. It is not positive live GitHub publication, duplicate-effect, or recovery proof, and no credential scope was changed.

Recommendation unchanged: **GO with conditions for the bounded local pilot; NO-GO for staging**. S3-4/S3-5 and S3-P1–P4 remain open as described. The parent owns the final full configured gate/evals and frozen-source Docker rerun; their outcomes must be reported from their actual evidence. No additional high security defect was found at this final scoped cutoff.

**Open question:** Do you approve the schema-free local contracts B–D in `02-pre-coding/continuation-3-task-plan.md`, preserving existing live rollout and evidence-deletion gates?

Status: BLOCKED (full continuation / staging); bounded local pilot GO with conditions

## V3 split publication defensive review — 2026-09-11 (Asia/Hong_Kong)

**GO with conditions for the bounded local pilot; NO-GO for staging.** Reviewed the complete runtime/test diff after `da8a9ad`, including `github_publication.publish_split`, the pipeline parent/child intent callbacks and the supplied actual-process-kill PostgreSQL proof. No new unmitigated high or critical finding was identified. This supplement closes S3-4 for fresh v3 branch-only recovery within the stated evidence limits; it does not enable external publication, maintenance, transport or cleanup, and it grants no approval.

### Findings and disposition

| ID | Severity / status | Evidence | Mitigation / verified behavior |
|---|---|---|---|
| S3-4 | Medium, resolved for new v3 requests | `github_publication.py:216` journals branch and PR actions separately. `pipeline.py:1159` persists each action under the current target/handoff and lease before invoking its provider write; `:1166` rechecks before receipt acceptance. | A completed branch with no PR action permits one fresh PR action. An existing unresolved branch or PR intent never authorizes replay when its desired external result is absent. Actual disposable PostgreSQL and two killed controllers demonstrate one simulated branch write and one simulated PR write in each recovered scenario. |
| S3-6 | Medium, retained compatibility hold | `pipeline.py:1084` refuses any v1/v2 parent intent before creating v3; v3's absence-of-child inference is valid only for its own persist-before-action protocol. The historical formats cannot prove that a missing PR child means no POST was started. | Keep v1/v2 effects held for explicit inspection. Never delete, rename or reset old effects to force v3 migration. Unit controls cover intended, uncertain and confirmed v2 holds. This safe compatibility restriction is not transparent legacy recovery. |
| S3-5 / S3-P1–P4 | Medium acceptance limits / high design constraints, unchanged | B–D remain proposed and unimplemented; the actual bot token's PR-list check returned 403; full external execution-linked QA and retention acceptance remain incomplete. | Preserve offline pilot limits, pending architecture approval, human gate/merge ownership and staging NO-GO. No live GitHub mutation or context/output experiment is authorized by this review. |

The parent canonical request remains bound to run, repository identity, base revision, branch, head and expected prior remote revision. Action requests add the branch/PR discriminator and retain the request hash. Branch updates use immutable-SHA conditional ref updates. A new owner can reconcile an old child's observed result; it cannot reissue an old child's ambiguous action. The missing-child condition is checked transactionally by `begin_effect`, so a racing owner that wins the intent prevents the other caller's POST. Parent receipt acceptance and the final pre-gate reobservation retain the previous target/fence controls. No approval rows or merge actions are introduced.

### Independently executed controls

- `python tools/azure-runner/test_github_publication.py`: **30 passed in 1.786 seconds**. Includes both crash boundaries, an existing uncertain action with absent provider result, missing-child race, stale owner and legacy-version refusal. Provider effects are mocked; existing CAS controls use actual disposable local Git repositories.
- `python tools/azure-runner/test_execution_runtime.py`: **36 passed in 4.785 seconds**. Includes actual threaded callback dispatch with injected target/fence refusal before intent creation, plus the retained artifact and gate acceptance-order controls.
- `python tools/azure-runner/test_execution_leases.py`: **8 passed in 0.188 seconds**; `test_recovery_acceptance.py`: **8 passed in 0.888 seconds**. These are local/injected checks, not live database evidence.
- Additional independent injected control: lose the lease immediately after the PR intent is persisted and before the POST. The old caller emits **zero POSTs**; a new caller sees the existing intended PR and remains held with **zero POSTs**. This verifies the conservative gap between a recorded intent and a provider call.
- `git diff --check`: passed. No DDL, dependency or lockfile change is present in this narrow increment. The parent owns refreshed configured checks/eval output after the final source snapshot.

Inspected `03-coding/publication-split-postgres-proof.py` and its JSON rather than rerunning them. The proof creates and removes an explicitly disposable PostgreSQL database, uses the production split algorithm and lease operations, and actually kills two subprocess controllers after durable simulated branch/PR writes but before receipts. Both scenarios retain exactly **one branch write and one PR write**, reconcile child effects to confirmed, refuse stale ownership, and preserve the existing validation approval snapshot; no fixture approvals are created. Git/GitHub operations in this proof are durable local-file simulations. It does not execute the full pipeline callback stack, perform live GitHub writes, establish provider request quiescence, or change the configured database. The JSON hashes match this review cutoff.

| Reviewed file | SHA-256 |
|---|---|
| `tools/azure-runner/github_publication.py` | `d0b0b0d41cdfd74abc924361849a62f03e02abbc31ea8599a9c35816f314704e` |
| `tools/azure-runner/pipeline.py` | `a564fadefd812a855fe197f44d82680982b958ee45c3597782bfa9e874db75bf` |
| `tools/azure-runner/execution_leases.py` | `8693d056fd6daa506808bef6425ea9727fa09d40be30eddbb2bc4ac1c4825afd` |
| `tools/azure-runner/test_github_publication.py` | `2c098027a34bd8f66a347c67e8d5e42af934e73a1e5b580b8e137448d8d9d9d2` |
| `tools/azure-runner/test_execution_runtime.py` | `8eedaf800092eaa0fe736b163b421cea2db885f7e1ba4eb3255edb72108eb21c` |

### Deploy-day additions and memory

The prior deploy-day checklist still applies. Before a later human activation: inventory all v1/v2 and v3 parent/child effects; preserve them during rollback; never downgrade an uncertain v3 action to the legacy publisher; verify final-source configured tests/evals and the exact target credentials; stop on any stale acceptance, changed destination, missing effect binding or unexplained duplicate write. A held intended action may have been persisted before any call, but absence of its result is deliberately not treated as proof that replay is safe.

The actual security `append_memory` postcondition remains satisfied by configured row **54**, as documented above; this is a continued review of the same engineering work, not a new fleet execution. No rendered memory edit or new insert is claimed. All runtime edits were made by the implementation owner; this reviewer changed only this report.

**Open question:** Do you approve the schema-free local contracts B–D in `02-pre-coding/continuation-3-task-plan.md`, preserving existing live rollout and evidence-deletion gates?

Status: BLOCKED (full continuation / staging); bounded local pilot GO with conditions

## Continuation 3 B–D implementation pre-review — 2026-09-11

**GO with conditions for local implementation; NO-GO for staging or external-mode activation.** The user's current continuation-3 instruction authorizes implementing the concrete local B–D contracts, as recorded by the integration owner. The older unanswered local implementation question is superseded; no fleet gate, live migration, publication, deployment or evidence-deletion approval is inferred.

See [continuation3-bcd-prereview.md](continuation3-bcd-prereview.md) for the severity-ranked constraints, file evidence, concrete mitigations, source/API review limits and deploy-day checklist. This is a design pre-review at `80babd0`, not acceptance of concurrently written implementation. The required boundaries are shared maintenance/dispatch/rework exclusion, separately fenced maintenance publication, enforceable host egress plus per-request TLS destination checks, isolated ephemeral CA trust, controller-owned sealed capture, and shared launch/retirement OS locks with irreversible tombstones. All require the plan's actual integration and negative controls before activation.

No dependency/lockfile/image diff exists in the reviewed continuation baseline through this cutoff. New gateway packages and images still require exact inventory and audit. No tests or external effects were executed by this pre-review. A dated gateway authorization learning was sent to the integration owner for actual `append_memory`; no tool is exposed in this reviewer session and no new durable insertion or rendered memory edit is claimed here.

Status: PASS-WITH-NOTES (local design pre-review); staging and external-mode activation NO-GO pending implementation evidence.

## Final continuation-3 B/D security disposition — 2026-09-11

**GO with conditions for the bounded local B/D pilot only. C is unaccepted and NO-GO for activation; staging remains NO-GO.** Full findings, concrete mitigations, evidence limits and deploy-day checklist are in [continuation3-bcd-prereview.md](continuation3-bcd-prereview.md), section “Final bounded B/D retest and disabled C review”. No confirmed unmitigated high finding remains in that reviewed B/D scope. Final configured checks/evals and post-coding review remain integration conditions, not results assumed by this report.

Review artifacts now live only in `C:/Users/dimas/.lantern/worktrees/continuation-3`, branch `codex/agentic-infrastructure-continuation-3`. [continuation3-final-review-snapshot.json](continuation3-final-review-snapshot.json) binds the runtime/image/lock review to exact file hashes. This review excludes unrelated concurrent Mission Control changes.

Closed findings cover exact merge ancestry, repeated-cancellation worker joining, path/key and quarantine retirement ownership, post-deletion audit recovery, and both direct/scheduled claim exclusion. An additional actual two-connection PostgreSQL probe exposed stale NOT EXISTS evaluation after a lock wait; the final helper acquires the run lock before reading child conflicts in a new statement, and its regression passes. Current-provider reobservation and site-local IPv6 denial were also verified. Independent worktree checks: 15 retirement tests, 6 added adversarial probes, 6 transport unit tests and 7 capture unit tests passed. Earlier independent SQL/Git/Docker maintenance run passed 13/13; the integrator's separately supplied final run records 14/14 and retains its original path/provenance.

C remains safely blocked by the launcher. Actual host egress/TLS denial proof, candidate image builds/audit, trusted deployment-bound capture and recorder-secret controls are incomplete. The new 43-package lock matches official PyPI wheel hashes, but four pinned packages have reported advisories; [continuation3-dependency-review.json](continuation3-dependency-review.json) records exact versions and references. The recorder was changed from raw Playwright network traces to redacted command-outcome JSON; actual image acceptance remains outstanding. These package findings do not claim demonstrated reachability in an activated service.

The deploy-day checklist requires final-source checks, default-off maintenance, dry-run retention with indefinite evidence, continued hard hold on C, worker drain/fencing and preserved effect ledger on rollback, and every existing human rollout gate. No live provider write, configured-database migration, deployment, existing-evidence deletion or human approval was performed by this reviewer. Actual append_memory remains the integrator's pending final action; its fresh-statement PostgreSQL learning is included in the detailed report, without a fabricated insert or rendered-memory edit.

Status: PASS-WITH-NOTES (bounded local B/D pilot only); C activation and staging NO-GO.

## Fixture-capture and inventory verification supplement — 2026-09-11

**GO with conditions remains limited to local B/D and the explicitly test-only recorder fixture; external C and staging remain NO-GO.** The latest detailed supplement in [continuation3-bcd-prereview.md](continuation3-bcd-prereview.md) reviews strict fixture/gateway mode validation at every receipt boundary, durable attempt/key checks under the fence, and diagnostic-only retention inventory. No new unmitigated high finding was identified. Final source hashes and proof-driver/result hashes are in the updated snapshot.

Supplied evidence now establishes one actual recorder image exercised against a direct local TLS fixture with certificate validation and ephemeral NSS trust. Independently verified media hashes, full video decoding and redacted trace schema are in [continuation3-capture-media-review.json](continuation3-capture-media-review.json). Updated independent checks passed: 9 receipt tests, 16 retention tests and 7 security probes. The actual Docker/PostgreSQL fixture driver was inspected rather than rerun by security; its synthetic deployment identity and direct networking remain clearly test-only. Gateway/firewall negative acceptance and dependency advisory resolution remain open, and the external launcher remains unconditionally held. Previous deploy-day conditions and human gates are unchanged.

Status: PASS-WITH-NOTES (bounded local B/D and explicitly test-only recorder fixture); external C activation and staging NO-GO.


## Continuation-3 outstanding foundation implementation and actual gateway review — 2026-09-11

**GO with conditions for the authorized local implementation and disabled candidate; NO-GO for external gateway activation, complete foundation acceptance or staging.** The previous B-D local permission question is superseded by the current user instruction. No new approval, gate decision or deployment is inferred.

The full severity-ranked findings, source evidence, concrete mitigations, review scope and deploy-day checklist are in [continuation4-security-review.md](continuation4-security-review.md). Reviewed the complete continuation runtime and lockfile delta, including inherited maintenance authority/cancellation/revalidation/publication, retention compatibility/index growth, controller-sealed recording and host namespace restrictions. The gateway's actual core exposed and now fixes ineffective ClientHello denial, replacement-socket pinning, absolute-target normalization and invalid startup options. A deterministic metadata-only local mitmproxy candidate resolves the patched43-package runtime lock without resolver suppression. The minimal pinned image removes unrelated sandbox tooling and the complete unused pip/ensurepip installer.

The frozen final image `sha256:b5f5a8a7d6116711e797f36d532f5050036e1a8b7fe7ebd1c2930edd8dedeb8c` passes **20/20 actual packaged loopback TLS/HTTP controls**. Its complete Scout scan still reports **27 OS advisories:1 high,2 medium,24 low** across12 packages. High CVE-2026-85091 affects the exact Debian zlib package according to Debian's current tracker and has no fixed distro version listed. It is retained as an open blocker, not waived from a conflicting upstream version range. [continuation4-final-image-summary.json](continuation4-final-image-summary.json) records the exact image/source hashes and compact findings; the detailed report links full build, inventory, scan and request-counter evidence.

External launch remains unconditionally disabled. Actual native-host/container identity and packet-denial acceptance, cross-execution CA/lifecycle controls and a trusted external deployment through the real gateway/controller path remain mandatory. Docker namespace and direct-TLS Playwright fixtures are explicitly separate evidence. The exact remaining prerequisites are a reviewed zlib disposition plus an authorized native host and target capable of those positive/denial and lifecycle tests; none is replaced by successful dependency resolution or media decoding. Final configured checks/evals and source-cutoff handoff remain the integrator's responsibility.

The required durable security learning was appended via the actual append_memory tool: row **67**, key `manual:feat-20260910-agentic-infrastructure:security:pending-e48b28231f26`, in [c3-foundation-memory.json](../03-coding/c3-foundation-memory.json). This manual engineering receipt is not a fleet stage pass. No rendered memory edit occurred; configured runs, executions and approvals stayed unchanged, and no migration was applied.

Status: PASS-WITH-NOTES for bounded local implementation; external foundation and staging NO-GO.

Final host-adapter supplement: reviewed and independently passed **8/8** controls for local Unix-socket pinning, exact process cgroup/container binding, rule normalization and refusal of remote-PID collisions. The supplied actual nftables namespace proof passes calibrated positive controls, seven denial checks and zero forbidden observer bytes; it remains separate from native Docker-host/external TLS acceptance. Final reviewed runtime hashes are in [continuation4-runtime-review-snapshot.json](continuation4-runtime-review-snapshot.json). No additional unmitigated high code defect was found in the local maintenance/retention/controller scope. The zlib and external acceptance blockers remain unchanged.

Status: PASS-WITH-NOTES for bounded local implementation; external foundation and staging NO-GO.
