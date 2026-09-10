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
