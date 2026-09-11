# Post-coding review: disabled external QA candidate

- Agent: post-coding, independent bounded review
- Date: 2026-09-11
- Run: feat-20260910-agentic-infrastructure
- Branch: codex/external-qa-acceptance; HEAD `1f94626cb88b5ea91ff781c90da1f490861ff37b` plus working-tree changes
- Baseline: main `302112a4465d7ecc9da1568b2f9d1aa7cc8a4d58`
- Status: PASS-WITH-NOTES for this scoped local source review; external activation and staging remain unaccepted.

## Summary

The watchdog joins process cleanup and the monitor before accepting a recording or reusing its database connection. One native acceptance cleanup defect was found, corrected by its owner, and independently verified. Package semantics and evidence limits remain explicit; this report does not certify a final image pair, deployed target, or pipeline gate.

## Work performed

Read role charter, skills, memory, runboard, original and continuation task-plan/blast-radius material, upstream review and QA/security evidence. Used the full diff-versus-main inventory and the complete current external QA modules, including untracked source, rather than a commit-by-commit review. The existing maintenance, retention and unrelated Mission Control branch changes retain their earlier review records; this bounded delegation does not repeat or expand their verdicts.

Inspected `qa_execution.py`, `qa_transport.py`, `qa_network.py`, `qa_native_acceptance.py`, associated controller tests, gateway Dockerfile, local zlib builder/API test, image TLS harness, dependency documentation and D20 inventory. This reviewer edited only this report and the stage report. No exploit/corruption test, host networking mutation, database write, image build, deployment or approval was performed by this reviewer.

## Findings and verified dispositions

| ID | Area | Severity | Tag | Evidence / disposition |
|---|---|---|---|---|
| EQA-PC-1 | Native acceptance cleanup | medium | fix-now — resolved | Initial `Resources.cleanup` aborted all later cleanup if one observer termination or container inspection failed. Updated code independently attempts every tracked observer/container/network, bounds TERM/KILL waits, aggregates failures, and makes `execute` fail when cleanup is incomplete. Independent injected failure probe verified continuation, timeout escalation and failed result; inspected updated source below. |
| EQA-PC-2 | Local library recovery semantics | compatibility limit | waived — disabled local candidate scope | Writer errors become terminal, including errors beyond failed I/O; callers must close/reopen. README and package provenance identify this behavior and the local fork. Exported symbol/version parity is evidence about the export surface, not universal behavioral compatibility. No compatibility waiver for a future live deployment is granted. |
| EQA-PC-3 | Acceptance evidence cutoff | acceptance limit | waived — local source review only | Earlier native result uses one socket-fixture image for both roles and 12 calibrated denials. It explicitly sets external transport/deployment verification false. Final candidate-pair native run, complete audit and trusted target configuration remain integration/QA/security requirements; none is waived as an activation prerequisite. |
| EQA-PC-4 | Rebuild provenance | reproducibility limit | waived — immutable local candidate only | Source archive/base digest and patch anchors are pinned; builder apt tool versions are not. Use the tested immutable image identity and retain provenance. Rebuilding at a later time requires fresh inventory/audit/testing; this report does not claim byte-reproducible toolchain builds. |

All fix-now resolutions were verified in updated source. No fix-now was downgraded to waived. No new debt ticket was opened; inherited allocation debt remains in the preceding review.

## Independent verification

With the existing Python 3.12 venv, `python -m unittest test_qa_execution test_qa_transport test_qa_network -v` passed **28/28**, 0.890 seconds. The sandbox could not launch its underlying Python executable; the approved retry ran the same ordinary unit command. These tests use injected boundaries and do not prove live SQL or OS containment.

Three additional ordinary probes passed, without writing runtime source:

1. An active periodic check held a simulated exclusive connection through delayed cancellation cleanup; final check entered only after it released, and stop ran once.
2. Failed authority monitoring rejected a recording result and joined cleanup.
3. The first observer raised PermissionError and the first container inspection failed; other owned resources were still cleaned, a timed-out observer received KILL, and aggregate cleanup remained incomplete.

The supplied configured run `../03-coding/external-qa-quality.json` had test/lint exit zero (655 cases, 12 skips), but its source-stability field and overall pass were false. It is not a frozen-source pass. The integration owner must retain that result and supply the final rerun after all source changes stop.

Inspected supplied gateway TLS results (24 controls), build/API/provenance results and earlier native socket-fixture evidence. They remain supplied evidence, not independent reruns. The native report's positive paths and destination observers establish its stated fixture scope only; it has no browser video, application deployment identity, or final-pair claim. The security supplement owns dependency advisory disposition and final installed-image binding.

## Compatibility and handoff

`check_external_acceptance` is pure and unconditionally held; `launch_external` checks it before allocating. The fleet rejects direct fixture mode, and the explicit local test entry remains the only available capture exception. Optional capture configuration remains off when absent; no schema or public event shape changes occur in this bounded increment.

The monitor checks policy and lease before launch, periodically, and before acceptance. Its periodic database transaction finishes before transport I/O; successful completion cancels and joins the periodic task before the final check uses the same connection. Existing lease heartbeats use their separate connection. Cleanup stops real processes through the adapter callback before joining a launcher that may await process exit; shielding survives repeated controller cancellation and cleanup failure prevents sealing. The five-second asyncio check timeout still requires a cancellation-responsive adapter, and its stop callback must confirm process termination. The absent production adapter must clean partial allocations before throwing and support idempotent stop.

The zlib package uses the fixed source hash, conservative guarded patch anchors, distinct package version, retained provenance, regenerated package checksums and ldconfig activation. Its documented terminal-error contract is deliberate. Preserve the distro advisory and tested installed-binary digest; a local version string or scanner miss is not a fix verdict. Keep gateway and recorder identities distinct from tags and from socket-fixture images.

Before claiming external acceptance, finish the final immutable-pair run, installed library digest/audit binding, actual-process failure lifecycle checks, trusted deployment mapping and applicable human gates. This local review does not approve staging or production.

## Reviewed source identities

| File | SHA-256 |
|---|---|
| tools/azure-runner/qa_execution.py | e0aa59ff67979b6d19b528a0db4418517ae359f174de500d9707d0fec9208460 |
| tools/azure-runner/qa_transport.py | efc591c26affa5a492bdc7bae4bd02dc90f2c35adefd14d58f71babbc49b85a0 |
| tools/azure-runner/qa_network.py | 6c4f864905ed98a0f3df84c02b81faa1705859d5b30c494f54b43e98b38e0216 |
| tools/azure-runner/qa_native_acceptance.py | 0cd01f82c63c669d4541223d7a6f5de1c006bafca1638822314a1628b401d2cc |
| infra/qa-gateway/build_zlib.py | 46301c522465e599681215c3efc9a6c79088d4d2a222fc5627e60f0f2238cdd2 |
| infra/qa-gateway/Dockerfile | b08c72d47eb3f87901b6058fa2096a14f38dcfc9065d9ac30351dea79ff29289 |

## Memory handoff

The parent owns the actual bound append_memory operation; no rendered-memory edit or completed insertion is claimed here. Learning supplied: **2026-09-11: A cleanup loop must attempt every independently owned resource after one stop/inspect failure and keep the result failed on uncertainty; otherwise a diagnostic harness can report its original error while leaving unrelated observers and containers alive. Join periodic database checks before a final check reuses their connection.**

Status: PASS-WITH-NOTES for the bounded disabled candidate source review; external activation and staging remain unaccepted.
