# Security supplement: dependency mitigation and recorder watchdog

- Agent: security, independent bounded review
- Date: 2026-09-11
- Run: feat-20260910-agentic-infrastructure
- Branch: codex/external-qa-acceptance; HEAD 1f94626cb88b5ea91ff781c90da1f490861ff37b plus the scoped working-tree changes below
- Recommendation: **GO with conditions for the disabled local candidate. NO-GO for external activation or staging.**

## Scope and result

Read the security charter, skills and memory, AGENTS.md, RUNBOARD, continuation blast radius/schema plan, upstream post-coding and security reports. Reviewed the complete uncommitted changes to `infra/qa-gateway/build_zlib.py`, `test_zlib.py`, `Dockerfile`, and `tools/azure-runner/qa_execution.py`, `qa_transport.py`, `test_qa_execution.py`. There is no lockfile delta in this increment. The broader branch, native acceptance driver and existing image dependency locks retain their prior independent review requirements.

No new high-severity defect was found in this scope. The two zlib guards implement a conservative terminal-error policy; the watchdog joins cleanup before a result can be sealed. This source review and successful build are not, by themselves, closure of C4-S1 or native-host acceptance.

## Severity-ranked findings and conditions

| ID | Severity / disposition | Evidence | Concrete mitigation or closure requirement |
|---|---|---|---|
| EQA-S1 | High inherited package acceptance condition; mitigation reviewed, complete dependency acceptance pending | C4-S1 remains recorded in `continuation4-security-review.md`. Debian still marks trixie's source version vulnerable and unfixed. The new build, installed API test and gateway controls establish the intended local mitigation, not a distro fix. | Retain the advisory; complete the installed-library digest binding and fresh unsuppressed whole-image audit before closing complete dependency acceptance. Do not equate a changed package version or missing scanner match with a fixed CVE. |
| EQA-S2 | High if activated prematurely; contained | `qa_transport.py:102` always raises; `launch_external` invokes that check before allocation. `qa_execution.py:102` rechecks acceptance, and the fleet rejects fixture mode. | Preserve the hold until actual native Linux daemon/container/netns binding, allowed and denied traffic counters, cross-execution trust separation and controller lifecycle acceptance on the final image pair pass. Keep human deployment gates. This review cannot close those requirements. |
| EQA-S3 | Medium compatibility condition, explicit and acceptable for the disabled candidate | `build_zlib.py:27` stops `gzclearerr` from resetting any failed writer, not only I/O failures. `gz_comp` also refuses a pre-existing error. This changes recovery semantics while retaining exported symbols. | Document close/reopen as mandatory after a writer error. Retain ordinary compression, read behavior and installed consumer tests. Call the check exported-symbol/version parity rather than universal ABI or behavioral compatibility. A local fork needs a future replacement/review when the distro releases a fix. |
| EQA-S4 | Low reproducibility debt | `Dockerfile:4` installs the compiler, make, libc headers and binutils from the current signed Debian repository without exact versions. The source and base digest are pinned; the complete build toolchain is not. | Freeze and use the tested final image digest and preserve its build/provenance log. For reproducible rebuilding, pin a Debian snapshot/toolchain inventory and re-review any resulting image change. Build tools remain confined to the builder stage. |

The official [Debian tracker](https://security-tracker.debian.org/tracker/CVE-2026-85091) was checked during this review. Its current distro finding remains authoritative evidence of an open advisory; this supplement makes no false-positive waiver or exploit-reachability claim.

## Package construction and error semantics

The builder checks the installed baseline version, downloads one fixed Debian source URL over HTTPS, verifies SHA-256 before extraction, and uses the data extraction filter. Exact patch anchors reject unexpected source layout. It invokes fixed subprocess argument lists, compiles with stack protection, fortification and RELRO/NOW, runs upstream tests, compares all defined dynamic symbol names including version suffixes, and runs the ordinary API check before packaging. The replacement preserves the package's files/symlinks and relationship fields, uses a visible `+lantern1` version, adds ldconfig activation, regenerates package checksums and includes patch/library provenance. Only the resulting package crosses into the runtime stage.

The source changes do not alter public types or signatures. The build log retains SONAME `libz.so.1`. Export comparison plus the small guard-only source delta is useful compatibility evidence, but does not independently compare every ELF ABI property or establish every Debian build configuration choice.

Inspection of the versioned upstream [gzip writer](https://raw.githubusercontent.com/madler/zlib/v1.3.1/gzwrite.c) and [gzip state/error handling](https://raw.githubusercontent.com/madler/zlib/v1.3.1/gzlib.c) supports the mitigation: public writer entry points reject existing errors; preserving that state prevents revival, and the added internal compression guard stops close from retrying failed input. Close still releases the compressor, buffers, path and descriptor. The tests use an ordinary gzip roundtrip and `/dev/full`; the unpatched baseline inspects reset only and exits without further operations on the failed handle. No exploit code or corruption test was developed or run.

## Watchdog ownership and independent checks

`monitored_recording` checks before launch, periodically during work and again before accepting completion. A completed failing monitor takes precedence over a recorder result. It cancels and joins the monitor before reusing the database connection. Cleanup first requests task cancellation, then invokes the process-owning stop callback before joining tasks. Shielded quiescence survives repeated controller cancellation; cleanup errors prevent receipt sealing. `capture_stage` allocates only once and owns outer cleanup for preparation failures, requiring idempotent stop.

The five-second check timeout is an asyncio cancellation deadline, not proof of OS process termination. The future adapter must implement responsive check cancellation and confirmed, idempotent process shutdown. Failed allocation must also clean up any partially allocated resources before it raises, since no adapter object has yet returned. These are acceptance requirements for the still-absent production adapter, not a claim that the controller alone can kill an arbitrary process.

Independent test command: installed Python 3.12 venv, `python -m unittest test_qa_execution test_qa_transport -v`: **20/20 passed**. This covers policy expiry, lease loss, gateway death, check timeout, cleanup failure, launch failure, result validation and the activation hold. An additional ordinary API probe cancelled the entire monitored recording twice while cleanup was active: stop completed exactly once and no live child asyncio task remained. Both acceptance/allocation entry points still rejected a caller-supplied accepted claim. These used injected callbacks, not real gateway death, native networking or a live lease service.

Supplied `../03-coding/external-qa-image-build.log` was inspected rather than independently rebuilt. It records baseline error reset, patched terminal-error behavior, upstream static/shared/64-bit tests, package installation, dependency hash enforcement and pip check. It exports manifest list `sha256:420eba6337f5c86fe99eebfee9c228a542972025c5fa05a37d7b16db51288a74`, platform manifest `sha256:3e6d8bb8634b6ae9de5e66931db3d96efc589393e79c2dbc343bafb9985196fc` and config `sha256:cf81686a40dcfe37a6c93f300613e99d518e14aac657baf33aa6e2883298b47b`. Final installed-image results remain separately required.

## Reviewed file SHA-256

| File | SHA-256 |
|---|---|
| infra/qa-gateway/build_zlib.py | 46301c522465e599681215c3efc9a6c79088d4d2a222fc5627e60f0f2238cdd2 |
| infra/qa-gateway/test_zlib.py | 181797d477e04dea8310055f9207dadaa3b2bf90caf783b5469433bd06447186 |
| infra/qa-gateway/Dockerfile | b08c72d47eb3f87901b6058fa2096a14f38dcfc9065d9ac30351dea79ff29289 |
| tools/azure-runner/qa_execution.py | e0aa59ff67979b6d19b528a0db4418517ae359f174de500d9707d0fec9208460 |
| tools/azure-runner/qa_transport.py | efc591c26affa5a492bdc7bae4bd02dc90f2c35adefd14d58f71babbc49b85a0 |
| tools/azure-runner/test_qa_execution.py | e5c06843e5b05cf0794bc0eae1a4194a7d5883de7b8bc47110a4179f05dd78f3 |

## Deploy-day checklist

The Dockerfile hash above includes the reviewed follow-up that explicitly retains `/usr/share/doc/zlib1g/lantern-mitigation.json` through dpkg's slim-image documentation filter and asserts that it is nonempty. The preceding build digest predates that rebuild. Final supplied [build log](../03-coding/external-qa-image-build-final.log) records manifest list `sha256:9521f9ace86b7ff946b3ca4561029079b03575184f9fcf86cac3d1fd446d24b9`, platform manifest `sha256:d63e13f6d17200cbcc60ec1ff3386616a67e31e645286b09b1f4ae21d7b0bb5e` and config `sha256:053b421e9882bf7a2ff895fc9bbf4950ad9f0ab03279b429682d3f517e68f1fd`.

Supplied [final gateway test result](external-qa-image-tls-final.json) records **24/24 packaged loopback TLS controls passed**, including previous-session CA rejection, gateway death and policy expiry. [Installed API result](external-qa-zlib-api.json) passes the ordinary roundtrip and terminal-error check. [Installed provenance](external-qa-zlib-installed.json) retains the expected source/patch identities and local package version, with library hash `ddb09e9720925b71d2946e265c4d4b0f1c55dce3dd7f5bb2cec2fa8d1a067997`. At this cutoff that field comes from provenance, not a separately reported installed-file hash; final inventory must compare the actual binary digest and bind the evidence to the immutable image. The results were inspected, not independently re-executed by this reviewer. No native-host acceptance is inferred.

Fresh whole-image scan results were unavailable at this cutoff. The first offline-scanner database download failed with unexpected EOF, retained in [external-qa-trivy-db.log](external-qa-trivy-db.log). The integrator is pursuing the replacement scan. The earlier Scout findings remain preserved; no clean final image or completed dependency acceptance is asserted. The bounded source/API mitigation is reviewed, while full dependency and external foundation acceptance remain open.

1. Keep external launch held while completing EQA-S1 and EQA-S2. Preserve the full advisory record and local-fork provenance.
2. Pin the tested image pair and exact source revision; run final configured tests/evals and obtain required post-coding/QA handoffs.
3. Before any authorized activation, prove policy expiry, lease loss, gateway death and repeated cancellation against actual processes; require zero receipt acceptance on uncertainty and independently confirm process cleanup.
4. Apply only a later explicit human deployment gate. Monitor unexpected writer errors, failed cleanup and policy/transport health loss. On any such failure hold the attempt, stop new QA dispatch, drain/fence workers and preserve evidence/lease records; rollback must not replace the held path with an unaccepted transport.

## Memory handoff

No `append_memory` tool is exposed in this reviewer session. The integrator owns the actual bound insertion and report aggregation; no insertion or rendered-memory edit is claimed. Candidate learning: **2026-09-11: Exported-symbol parity does not preserve documented error recovery semantics; a local library mitigation must state its terminal-error behavior and retain the distro advisory until a reviewed disposition is tied to the tested installed image.**

Status: PASS-WITH-NOTES for the disabled local candidate; external activation and staging NO-GO.
