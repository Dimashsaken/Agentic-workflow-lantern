# Post-coding review: continuation-3 outstanding infrastructure

- Agent/author: independent post-coding reviewer.
- Date: 2026-09-11 (Asia/Hong_Kong).
- Run: feat-20260910-agentic-infrastructure.
- Worktree: C:/Users/dimas/.lantern/worktrees/continuation-3.
- Branch: codex/agentic-infrastructure-continuation-3; implementation baseline 09fdb11c18f8a12f8b625d4c2e7ceeebd1deb8e5.
- Status: PASS-WITH-NOTES for the scoped local implementation review. Complete foundation, external transport and staging remain unaccepted.

## Summary

The maintenance child now keeps explicit inherited authority through its actual artifact and Git handoff boundaries, revalidates committed fixes against the frozen scope/policy/image, and leaves publication to the fenced parent. This review found and verified fixes for child handoff, retention indexing/concurrency, and D20 fingerprint defects; allocation retains a documented history-scan debt. The external launcher remains held, so neither local direct-TLS recordings nor dependency metadata is external transport acceptance.

## Work performed and scope

Read the post-coding charter/skills/memory, AGENTS.md, runboard, continuation task plan, original task plan/blast radius and latest coding/QA/security records. Inspected the full diff-versus-main inventory and reviewed the infrastructure delta as a whole, including untracked modules, rather than commit-by-commit. Main resolves to 302112a4465d7ecc9da1568b2f9d1aa7cc8a4d58 at final inventory; the branch already carries unrelated Mission Control differences, which remain outside this delegated infrastructure review and were not edited. No registered story/validation envelope or formal fleet stage pass is inferred from this local run record.

The inspected source covers maintenance parent/child lease checks, cancellation joining, immutable regate, conditional publication, artifact/memory/usage acceptance, maintenance output isolation, retention descriptors/index/legacy compatibility and the QA controller entry. Security owns the candidate image/dependency/TLS/firewall implementation and its separate verdict. This reviewer changed only post-coding evidence and reports, ran disposable local filesystem/Git tests, and used injected SQL for artifact probes; no configured database, external provider, gate, deployment or existing evidence was changed.

## Findings and verified dispositions

| ID | Area | Severity | Tag | Evidence / disposition |
|---|---|---|---|---|
| C3-PC-1 | D20 fingerprint | medium | fix-now - resolved | The initial list named nonexistent vendor_mitmproxy.py. check_pr.py now fingerprints actual vendor_wheel.py, upstream.lock and the controller/publication entry modules. Final D20 generation remains the integrator's required check. |
| C3-PC-2 | Retention lock duration | major | fix-now - resolved | Initial allocation held the global index lock across clone preparation; an unrelated mount failed after 10.016 seconds. Allocation now releases the index lock before the clone body while retaining its execution lock. Independent thread test and final retention suite pass. |
| C3-PC-3 | Legacy index correctness | major | fix-now - resolved | Initial completed index missed later legacy mappings. A later draft absorbed a concurrent legacy mapping into its completeness timestamp without indexing it. Final shared reconcile_legacy_index validates mapping identity, rebuilds ancestor markers, rechecks the directory timestamp, then records completeness. Both late-addition and interleaved-registration negatives now hold. Old-visible mappings and version-2 sentinels preserve refusal by the actual 09fdb11 reader for same-key, wrong-key and ancestor mounts. |
| C3-PC-4 | Immutable maintenance scope | major | fix-now - resolved | Initial post-child acceptance reread current plan scope. run_fix now verifies successful child status and unchanged durable authority/current plan against the captured scope; run_pass carries that captured scope into independent revalidation inside the bound worker. The original captured quality contract, exact merge ancestry and pinned image remain required. |
| C3-PC-5 | Real child artifact acceptance | major | fix-now - resolved | With dispatcher flag 0 the initial insert_artifact inserted without a child fence/metadata; with flag 1 it rejected the intentionally absent RUN lease. It now recognizes inherited STAGE authority independently of that flag, checks the actual stage and fences insertion with child metadata. Independent actual-function probes accept both flags and reject stale children with zero inserts. Child report/gate/handoff paths also use a per-child ContextVar, preserving the earlier handoff. |
| C3-PC-6 | Real child base reference | major | fix-now - resolved | A real clone of the trial checkout lost origin/main, causing normal finalize_coding to reject the handoff. Production clone preparation now pins the observed base SHA as the child's remote-tracking base. Independent production-prepare and actual finalize_coding calls passed against temporary Git repositories, with earlier handoff bytes unchanged. |
| C3-PC-7 | Regression test execution | minor | fix-now - resolved | The new slow-allocation test initially lacked import asyncio. Import corrected; the final complete retention suite passes 21/21. The initial failed log is retained, not relabelled green. |
| C3-PC-8 / BCD-PC-3 | Allocation scalability | medium | debt-ticket - open | Existing local ticket LANTERN-DEBT-EXECUTION-GC is amended below: mount lookup no longer scans history, but compatibility registration deliberately scans retained mappings before accepting its stamp. This is a safe local-pilot tradeoff, not fleet-wide bounded allocation cost. |
| C3-PC-9 | External foundation acceptance | acceptance limit | waived - local scope only | Keeping an unactivated candidate is acceptable for local review; launch_external still raises unconditionally and capture_stage rejects direct_fixture. Actual audited image, effective TLS hooks, native-host positive/denial controls and trusted external target/deployment configuration remain mandatory and are not waived. |

All fix-now resolutions were checked in the updated source. No fix-now was downgraded to a waiver. BCD-PC-2 is closed for descriptor registration: both trial and fix clones are allocated under retention ownership. Registration does not make evidence-pinned clones eligible for deletion.

## Independent verification and supplied integration evidence

- c3-initial-defect-probes.json retains the initial slow-lock, missed legacy mapping, artifact flag and missing-base observations. These are defect evidence, not acceptance results.
- c3-review-probes.py/json: **16/16 independent checks passed**. Includes actual filesystem/thread behavior, the interleaved legacy writer, actual artifact function with injected SQL/fence, production nested clone preparation, real Git merge/commit/bundle plus actual finalize_coding, prior-handoff preservation and actual baseline retention-code refusal. It is not Azure execution or live publication.
- c3-retention-retest-final.log: **21/21 passed in 6.981 seconds**. Includes the 10,000-mapping steady-lookup control, real subprocess lifecycle lock and disposable-root retirement/crash controls. Database eligibility in this suite is injected. c3-retention-retest.log preserves the initial 20-pass/one-test-error run.
- Inspected the integrator's c3-foundation-maintenance-r2.log and driver: **18/18 passed in 116.868 seconds**, using real disposable PostgreSQL, Git, immutable Docker regate and local conditional push. Model decisions and GitHub observations are scripted; the test does not prove an Azure model execution or live GitHub mutation. The separate independent real child-handoff probes above cover paths skipped by its scripted child.
- Inspected QA's real SQL controller probes and new local recorder evidence: the controller captures through execute_capture, persists a positive sealed receipt, and rejects failing requirements, deployment drift and lost ownership. QA records these as explicit test-only direct TLS with actual image-local Playwright/video, not gateway transport. Existing unchanged decoder/UI proofs were not rerun or counted as new acceptance.
- git diff --check passed. Final configured checks and refreshed D20 results belong to the integrator's eventual source/commit cutoff; they are not assumed green by this review.

## Compatibility and handoff

The maintenance pilot remains opt-in. Its children never acquire a dispatcher lease, advance a run or approve a gate; begin_effect rejects child publication, and the parent owns conditional ref publication after independent immutable revalidation. Cancellation joins model/tool work and cleanup before accepting the child; changed approval/target/authority or ambiguous effects hold. No schema migration is introduced by this continuation delta.

Retirement remains dry-run by default with indefinite evidence retention. Current records live under records-v2, while old-visible immutable path mappings and rejecting sentinels prevent an older reader from treating a new checkout as unowned. Existing legacy locks/descriptors remain recognized; uncertain ownership, incomplete allocation, evidence output/error and unverified Docker inspection still hold. Do not erase compatibility mappings, sentinels or evidence to reduce disk usage. Human rollout should drain controllers/workers and preserve the registry/effect ledger during rollback.

QA capture is controller initiated before the stage's model work; it derives durable execution identity, observes the expected deployment at both ends, checks exact command/requirement outcomes, closes writers, fully decodes/hashes media and fences receipt persistence. Direct fixture capture requires an explicit test API argument and cannot be selected by the fleet configuration. The optional fleet setting currently produces a deliberate hold until external adapter acceptance; successful local fixture evidence does not remove that prerequisite. Before future external activation, the adapter must also enforce expiry and gateway-failure shutdown while recording, and avoid duplicate allocating launcher calls between capture_stage and execute_capture.

## Local debt ticket amendment: LANTERN-DEBT-EXECUTION-GC

Owner: runtime maintainer. Priority: before sustained fleet allocation. Prior BCD-PC-2 is resolved for maintenance descriptor registration; prior BCD-PC-3 is narrowed to allocation/rebuild cost. The mount lookup is bounded by path depth in steady state and tested with 10,000 retained mappings, but each new compatibility registration reconciles the historical top-level mappings. A future optimization must measure allocation and mount I/O at 0/1/10,000 attempts while preserving old-reader sentinels, late/concurrent legacy-write refusal, filename/path consistency, allocation/retirement lock exclusion and indefinite tombstones/evidence. Do not remove the scan without another verified compatibility protocol. This amendment creates no external issue and authorizes no cleanup.

## Memory

Pending integration-owner insertion through actual append_memory; this reviewer discovered no callable append_memory tool and did not edit the rendered memory file. Candidate supplied: "2026-09-11: A bounded historical-path index must preserve the write protocol across rollback and mixed-version writers; a permanent completeness marker can silently lose ancestor protection after a legacy writer adds a path. Keep registry locks out of slow clone work, and validate final maintenance changes against the inherited scope rather than a reread plan. A scripted repair child can prove parent fencing and immutable regate without proving the real child handoff; exercise its artifact acceptance and required Git refs with dispatcher flags both on and off."

The real durable receipt, final configured checks/evals and security's actual-image/native-host disposition must be attached by the integration owner before the final handoff. This scoped review grants no human approval, deployment, external activation or complete-foundation pass.

Status: PASS-WITH-NOTES (scoped local post-coding review); external foundation and staging remain unaccepted.

## Final lock-identity compatibility supplement - 2026-09-11

| ID | Area | Severity | Tag | Evidence / disposition |
|---|---|---|---|---|
| C3-PC-10 | Permanent lifecycle lock identity | major | fix-now - resolved | Selecting top-level versus locks-v2 by later existence allowed an actual old reader to create a second lock path. A second current holder then entered while the original holder was still live. locked now always uses the single original top-level pathname. c3-lock-compat-retest.json independently proves old09fdb11/current contenders both remain held until the first holder releases, then reacquisition succeeds. |

Final independent affected-suite rerun: **21/21 retention tests passed in 12.199 seconds**, recorded in c3-retention-lock-retest.log. The three additional actual old-reader/current-lock controls pass; their final retention SHA-256 is `2ef0943e49d521461f4a4cef3ff7a4aeb90bf846245f798b702f3f8f52f4e99f`. This hash supersedes the retention entry in c3-final-review-snapshot.json; the other snapshot entries keep their stated cutoff. That earlier snapshot also records an additional independent malformed legacy-mapping hold after shared reconciliation-helper extraction. No Git/Docker/media proof was rerun for this lock-only correction.

The durable learning supplied to the integrator now also notes: "Compatibility metadata can reject an old reader yet still change which OS lock newer readers acquire; keep each execution lock identity permanent." No unresolved fix-now finding remains. Historical allocation/legacy-transition scan debt and external activation prerequisites remain exactly as above.

Status: PASS-WITH-NOTES (final scoped local post-coding review); external foundation and staging remain unaccepted.

## Actual durable-memory receipt - 2026-09-11

The integration owner completed the actual bound append_memory call on the existing configured PostgreSQL database. I inspected [c3-foundation-memory.json](../03-coding/c3-foundation-memory.json): post-coding row **66**, execution key `manual:feat-20260910-agentic-infrastructure:post-coding:pending-639f48d9e2ae`. This resolves the earlier pending memory postcondition; it is manual engineering memory, not a fabricated fleet execution or a direct edit to rendered memory.

The inserted post-coding entry reads: "2026-09-11: A bounded historical-path index must preserve the write protocol across rollback and mixed-version writers; a permanent completeness marker can silently lose ancestor protection after a legacy writer adds a path. Keep registry locks out of slow clone work, and validate final maintenance changes against the inherited scope rather than a reread plan. Compatibility metadata can reject an old reader yet still change which OS lock newer readers acquire; keep each execution lock identity permanent."

Receipt counts preserve runs/executions/approvals at **12/23/8**, with unchanged approval snapshot; role_memory grows 41 to 45 for the four role insertions. No migration or new cluster is recorded. The actual invocation helper also records the scripted-child versus real-handoff learning under coding row64. This reviewer performed no database mutation directly and did not hand-edit agents/post-coding/memory.md.

Status: PASS-WITH-NOTES (final scoped local post-coding review and memory complete); external foundation and staging remain unaccepted.
