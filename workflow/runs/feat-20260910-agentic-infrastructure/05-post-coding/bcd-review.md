# Post-coding review: continuation-3 B/C/D local increment

- Agent/author: independent post-coding reviewer.
- Date: 2026-09-11 (Asia/Hong_Kong).
- Run: feat-20260910-agentic-infrastructure.
- Branch/worktree: codex/agentic-infrastructure-continuation-3; C:/Users/dimas/.lantern/worktrees/continuation-3.
- Baseline: main and HEAD both 80babd0f3c90294f4d13f8b28e47dc1a9a2cdab3 at review. Reviewed the full working diff versus main, including the newly added untracked runtime/image files, not individual commits.
- Status: PASS-WITH-NOTES for the scoped local increment. This is not complete foundation acceptance, a registered stage pass, or deployment approval.

## Summary

The scoped implementation preserves an opt-in maintenance path, dry-run retention and an unconditionally held external QA launcher. One pilot-configuration routing issue was corrected by the integrator and independently verified in the updated diff. Retention debt and real external capture acceptance remain open; security owns its separate race and dependency findings.

## Findings

| ID | Area | Severity | Tag | Evidence and disposition |
|---|---|---|---|---|
| BCD-PC-1 | Maintenance pilot flag routing | major | fix-now - resolved | review.babysit_run originally selected maintenance only through execution_runtime.enabled(). Enabling LANTERN_FENCED_BABYSIT alone could fall through to legacy behavior. Updated routing selects maintenance when either the lease runtime or fenced pilot is enabled. Independent in-memory call with FENCED_BABYSIT=1 and EXECUTION_LEASES=0 returned fenced, called maintenance once and called legacy product lookup zero times. No provider/DB operation occurred. |
| BCD-PC-2 | Retention coverage | medium | debt-ticket - open | Existing local ticket LANTERN-DEBT-EXECUTION-GC remains open. maintenance_runtime.run_pass retains review.trial_merge temporary clones, but those paths do not receive execution_retention.allocation descriptors. Retirement correctly holds unknown paths, so neither successful nor conflicting maintenance clones become cleanup candidates. The current retention API is not fleet-wide cleanup acceptance. |
| BCD-PC-3 | Retention launch overhead | medium | debt-ticket - open | Extend LANTERN-DEBT-EXECUTION-GC: worker_mount scans and parses every persistent path-*.json mapping on every Docker launch to reject ancestor mounts. Allocation keeps both original/quarantine mappings permanently. Launch I/O therefore grows with total historical attempts even after checkout deletion. Scope a bounded path registry/index while preserving ancestor rejection and irreversible tombstones; do not remove the protective check as an optimization. |
| BCD-PC-4 | Candidate capture and compatibility scope | acceptance limit | waived - scope only | launch_external always raises TransportHeld. The candidate receipt is a separate qa_capture version 2 format; existing quality manifests/display are unchanged. Current browser evidence exercises the baseline UI, not this receipt's end-to-end persistence/display. Keeping candidate files locally with no activation is acceptable; actual HTTPS capture, firewall/image acceptance and dependency remediation are not waived. |

No unresolved fix-now finding from this post-coding pass. No fix-now was downgraded to a waiver.

## Independent checks

Executed from this isolated worktree with the existing Python 3.12 virtual environment:

- test_maintenance_runtime: 14 discovered, 7 passed and 7 disposable-PostgreSQL tests skipped (0.134 s).
- test_execution_retention: 15 passed (0.625 s), including a real second-process OS lock and temporary-directory retirement crash retries. Database eligibility is mocked in this suite.
- test_qa_provenance: 7 passed (0.024 s); synthetic media and injected decoder, not actual TLS/video proof.
- test_qa_transport: 6 passed (0.001 s); pure policy and held-launch controls, not packet containment proof.
- Independent pilot flag routing probe: fenced_calls=1, legacy_calls=0.
- git diff --check passed; line-ending conversion warnings only.

The integrator is running the complete configured policy after source changes. Earlier bcd-increment-quality.json records a failed full test run and must not be described as final green evidence. This review does not supersede that final check or security's retest.

Inspected the supplied maintenance integration driver and log: 14 tests passed in 24.431 s. That driver uses real disposable PostgreSQL, local Git and Docker for the green path, with simulated GitHub GET observations/local conditional push; it is not live GitHub proof. The reviewer did not rerun database integration or modify any database. Baseline browser results and limitations remain in ../04-qa-dev/bcd-report.md.

## Intent, compatibility and handoff

B uses the existing schema and binds a dedicated stage execution to the decision, run position and target. Existing legacy configuration stays on its prior path; enabling the fenced pilot selects the new path even when dispatcher leasing is disabled. Red regates return an explicit held-fix result. Renewal/completion use the maintenance lease and do not approve a gate or advance the run. The run-row locking changes cover dispatch, retry/rework and decision mutation; security independently owns adversarial concurrency verification.

D registers fresh isolated product checkouts and makes worker launch share the lifecycle lock. Unknown/legacy/allocating descriptors and Windows Docker mount mapping uncertainty hold. Evidence remains retained indefinitely; nonempty execution output/error pins its checkout. SQL eligibility uses existing execution/run/effect indexes and server time; no new schema or production EXPLAIN was executed. No automatic cleanup command is connected in this increment.

C includes separate gateway/recorder candidates, frozen destination policy and controller receipt helpers. The baseline sandbox and controller SDK requirements are unchanged. The recorder's trace is a redacted JSON command trace rather than a raw Playwright network trace. No concrete candidate image was accepted here, no HTTPS deployment identity was observed and no activation was performed. Dependency details belong to ../06-security/continuation3-dependency-review.json and the security report.

## Local debt ticket amendment: LANTERN-DEBT-EXECUTION-GC

Owner: runtime maintainer. Priority: before sustained opt-in fleet operation. Existing ticket is defined in report.md. Extend its acceptance to maintenance temporary-clone allocation/inventory, safe retirement after all thread/container quiescence, and bounded launch lookup cost across 0/1/10,000 retained descriptors including deleted tombstones. Preserve indefinite evidence retention and legacy holds. This local ticket amendment creates no external issue and performs no deletion.

## Durable memory candidate

2026-09-11: Test optional safety flags independently of neighboring runtime flags; an operator enabling a protected pilot must reach that protected entry point even when the older dispatcher mode remains configured. Retention inventories must include temporary maintenance clones and permanent descriptor growth, because deleting checkout bytes alone does not bound lifecycle overhead.

Sent to the integrator for the actual append_memory tool. No rendered role-memory file was hand-edited; this reviewer does not claim an insertion.

## Reviewed source identities

| Source | SHA-256 |
|---|---|
| `tools/azure-runner/maintenance_runtime.py` | `cf90f135d9be0c56f8035ef4b57cdd3414b993feca51189ee6ac7abc8b08a7d4` |
| `tools/azure-runner/execution_retention.py` | `f2769e93281105d9f02438d630fecd663595bae26a26a1fd0ac2d6bba5ec67e0` |
| `tools/azure-runner/isolated_tools.py` | `4ee69d3689f7e8b6f1a726a55e612a1d7a39077679cdbd5c08df0ea135e90b2b` |
| `tools/azure-runner/execution_leases.py` | `1bded3709f104939c096c4abac91c8e9f7f2d0e7b211abee351bdd38a3ca2daa` |
| `tools/azure-runner/pipeline.py` | `6339ee18be5361d0c053b23e0c841a7b52228195425e60618987c041c94f4d9c` |
| `tools/azure-runner/review.py` | `a5ced67b4aed1d806756c243754862f8b2016707793137fe61132881701ab763` |
| `tools/azure-runner/qa_provenance.py` | `55f8f35314c1e0b0fb82aa35044ded80ec7b097d3f34ca5f31396f1e0e9d58b2` |
| `tools/azure-runner/qa_transport.py` | `b8a81b6f3a29ce6804fdd677e5bec94cc495c5f93d46d03a2871765f96370aee` |
| `tools/azure-runner/qa_recorder_worker.py` | `37ab3957fac008fedda4c04fcd4b44c6ba527be22f6f07c0f3634c7e7ae6251b` |
| `infra/qa-gateway/policy.py` | `9a5b68718bd46986bc337ab10ce848dd0e90595262e9ffb35e3f95212a19fc44` |
| `infra/qa-gateway/entrypoint.py` | `a2c7122d8a30b52cb190acac9f1f23bd10b0ee32a96fd056e79f4f818b114d4f` |
| `infra/qa-gateway/requirements.lock` | `a0b35cf9b1427d9492f78fa88c4959a63c372bb563711e60692e9f74bc934b35` |
| `infra/qa-gateway/Dockerfile` | `38c3733e7bde0bb83238813f1a145816692248e853ae4360aa7970d05926311b` |
| `infra/qa-recorder/Dockerfile` | `feb16b5fc1c0a375bcf5e730259e9d852892ba8855905241ca7073d013029ee0` |


## Narrow supplement: direct fixture receipt and diagnostic inventory - 2026-09-11

Inspected the new common transport validator at construction, sealing, verification and persistence. A direct_fixture receipt must be test_only=true and must have no gateway image; gateway mode still requires both immutable image identities. Unknown or contradictory transport contracts hold. Persistence now compares the receipt's attempt and execution key with the authoritative stage_executions row inside the fenced transaction, in addition to the lease run/execution/fence checks. No new post-coding fix-now finding.

The transport_mode field is now required in this still-unactivated candidate version-2 format, so earlier experimental receipts without it are refused. Existing legacy quality manifests and UI contracts are unchanged. This is acceptable within the local candidate scope; do not relabel an old receipt as proof for the newer transport contract.

Inspected bcd-capture-proof.py and its supplied result JSON: an actual recorder image captured a local direct TLS fixture using ephemeral NSS trust, without ignoring TLS errors, and produced a fully decoded 1-second VP8 video plus a redacted JSON command trace. The driver persists/verifies its controller receipt in a disposable PostgreSQL database and checks wrong attempt/key and stale-writer refusal. Reported Docker/database resources were removed. This reviewer inspected the driver/results and did not independently rerun the Docker/database proof; QA/security independently cover its evidence. The result explicitly has external_transport_verified=false and gateway_accepted=false. This updates the earlier 'no concrete candidate image accepted' wording only for the direct recorder fixture; it does not accept the gateway, host firewall, external transport or production deployment identity.

execution_retention.inventory is a diagnostic snapshot: it lists descriptor-owned and unknown top-level paths with known byte totals, database-clock ages where available, eligibility and held reasons. It only calls retire with its default apply=false; eligibility must be rechecked before any later deletion. Deleted descriptors report zero retained bytes. No automatic cleanup is connected. The maintenance temporary-clone and all-history lookup debts BCD-PC-2/3 remain open.

Independent focused reruns from the isolated worktree: 16 retention tests passed in 0.665 seconds and 9 provenance tests passed in 0.034 seconds; git diff --check passed. Retirement tests use owned temporary directories and mocked database eligibility. No original database, external service, approval or runtime file was changed by this reviewer.

Memory: the existing pending candidate remains applicable; no additional durable learning beyond that entry was identified in this narrow supplement. Integrator owns the actual append_memory path.

Updated inspected source/artifact identities (these identify the reviewed files, not a reconstructed image build):

| Source/artifact | SHA-256 |
|---|---|
| `tools/azure-runner/qa_provenance.py` | `251b6585978ea307c0c5c57b7585d20a8f0419113584c3ea1ef2ccd46b905cc1` |
| `tools/azure-runner/execution_retention.py` | `bbd1c071c2644d89a52406fa8dc40149392c91cfae2dda86ca8b1b1d42813f12` |
| `tools/azure-runner/test_qa_provenance.py` | `715921bf3fc5cc7f8588128a2dd4c2d448eb64e086cadb0d7adcb42dd73dfdc4` |
| `tools/azure-runner/test_execution_retention.py` | `e3a2692083beb621058ce8526475bc6d1ab4f38f0cb71616339fb7bcc4966f42` |
| `workflow/runs/feat-20260910-agentic-infrastructure/03-coding/bcd-capture-proof.py` | `c6b444318bb02b6f841e964c2f598b9bc27892c24a5f3823d2e64caa9426fc4a` |
| `workflow/runs/feat-20260910-agentic-infrastructure/03-coding/bcd-capture-proof.json` | `7978719f15a44c24d5d0ce3832f9d1911112c560b20b41352160949a51bb6cba` |

Status: PASS-WITH-NOTES (narrow local supplement); external QA activation remains unaccepted.
