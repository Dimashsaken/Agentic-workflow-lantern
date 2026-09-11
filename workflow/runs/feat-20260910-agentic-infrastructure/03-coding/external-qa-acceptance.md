# External QA acceptance continuation — feat-20260910-agentic-infrastructure

- **Agent/author:** Codex, manual engineering; independent QA, post-coding and security reviews
- **Date:** 2026-09-11
- **Branch:** `codex/external-qa-acceptance`, based on `1f94626`
- **Status:** BLOCKED for full external acceptance; implemented candidate changes pass local checks

## Summary

Added a narrowly scoped zlib package mitigation, continuous recording supervision,
and an actual native Linux Docker/network acceptance harness. The production
launcher remains held: socket/TLS fixtures do not establish a registered capture
against an approved deployed product. The configured QA target, trusted deployment
descriptor and scoped credential references are missing.

## Work performed

The gateway builds Debian's hash-pinned zlib source into a locally versioned
`zlib1g` package (`1:1.3.dfsg+really1.3.1-1+b1+lantern1`). A failed gzip writer cannot
be revived by `gzclearerr`, and `gzclose` cannot retry compression after the error.
This intentionally requires closing/reopening a failed writer. It preserves the
exported symbols and versions, ordinary gzip roundtrips and upstream tests; it is
a conservative local mitigation, not an upstream release or a version-based
false-positive waiver. Build tools stay in a separate builder stage. Debian slim's
documentation exclusion is overridden for the precise mitigation provenance file.

The recorder controller now checks policy, lease and optional owned transport
health continuously while capture runs. A failed or timed-out check terminates
the attempt and joins cleanup before a receipt can be sealed. Periodic database
checks join before the final check reuses the connection. The acceptance check is
pure and separate from allocation, removing the double-launch preparation hazard;
this does not implement or activate a production Docker launcher.

The native acceptance harness uses the existing `lantern-fleet` Ubuntu host through
AWS Systems Manager. The old documented SSH address and the current AWS-reported
address timed out on port 22; SSM was online. Only uniquely owned temporary test
resources were used. The harness exercises `LinuxNamespaceFirewall`, its exact
local daemon/container/cgroup/namespace binding and rule readback, with positive
calibration and independent packet/socket observations. Review found and fixed
cleanup that stopped after its first error; every remaining owned resource is now
attempted and uncertainty keeps the overall result failed.

## Findings and results

1. **C4-S1 mitigation implemented and independently reviewed.** Final local image
   is `sha256:46a63fb17ffe9a0df0fa68239315388b13b856983161a0da54f62f653ee73034`.
   The installed library hash matches its build provenance. All 24 actual packaged
   TLS/session tests pass, including rejection of a prior session CA and closure
   of active connections on gateway death/policy expiry. Retain the distro CVE
   record separately from the local mitigation; complete-image audit disposition
   is recorded separately below when available.
2. **Configured checks pass.** `external-qa-final-quality.json` records 655 cases,
   12 platform-dependent skips, green lint and unchanged source during checks.
   Three additional native cleanup regressions pass. The earlier
   `external-qa-quality.json` intentionally remains failed because the native
   harness changed concurrently, although its test/lint commands passed.
3. **Native acceptance is distinct from deployment acceptance.** The final native
   candidate pair passes 14 calibrated denials, two allowed flows and complete
   cleanup. Exact native image identities and the 24 packaged TLS/session controls
   are recorded in the QA report.
4. **External deployment remains unavailable.** Read-only parameter discovery
   returned no `/lantern/qa/` references, and the local configuration contains no
   `LANTERN_QA_` entries. No app-reported or checkout SHA was substituted for a
   trusted controller deployment observation.
5. **Fresh audit transport.** Automatic approval review rejected Docker Scout
   because it may export private image metadata. The offline alternative downloads
   only a public vulnerability database and scans a local image archive with
   networking disabled. Failed/truncated database transfers are retained and
   never treated as a successful scan or accepted despite a hash mismatch.
   The completed native offline audit reports 176 gateway findings (3 critical,
   51 high) and 191 recorder findings (1 critical, 10 high). These raw scanner
   counts are untriaged. Automatic approval review rejected retrieval of package
   versions and vulnerability IDs; explicit user approval is pending. Full reports
   remain at the exact native path recorded in
   `../06-security/external-qa-offline-audit-status.json`. Do not infer that the
   prior smaller Scout result and this scan have equivalent coverage or that the
   local zlib mitigation closes these additional findings.

## Artifacts

- `external-qa-image-build*.log`: original and provenance-corrected builds
- `external-qa-final-quality.json`, `external-qa-final-test.log`, `external-qa-final-lint.log`
- `../06-security/external-qa-image-inventory.json`: immutable image, source hashes,
  actual installed zlib hash, 87 OS packages and 43 Python distributions
- `../06-security/external-qa-zlib-api.json` and `external-qa-image-tls-final.json`
- `../04-qa-dev/external-qa-native-*`: native source, images, calibration, counters,
  cleanup, host observations and scope
- `../05-post-coding/external-qa-review.md`
- `../06-security/external-qa-mitigation-review.md`
- `external-qa-memory.json`: actual memory-tool receipts, rows 68–71

## Handoff and confidence map

- The local zlib mitigation changes write-error recovery semantics. Preserve the
  package/library binding and ordinary API checks when replacing it with an
  upstream or distro fix; do not interpret scanner custom-version behavior as
  absence of the original advisory.
- Native packet denial, loopback TLS and controller unit tests are separate
  evidence. An owned Docker launcher/watchdog and real deployment-bound recorder
  path still need combined acceptance, including startup, partial allocation,
  cancellation/lease loss and cleanup failure against the designated target.
- A native recorder built from the host's existing sandbox has a different base
  from the old workstation recorder. Evaluate the exact final image pair; do not
  transfer acceptance between tags or fixture bases.

The full final deployment charter still includes real browser recording and
sealed receipt verification for normal completion, gateway death, lease loss,
cancellation, policy expiry, fresh CA per attempt, deployment drift, swapped or
modified media and cleanup uncertainty. This change does not claim those combined
tests ran against a trusted product deployment. Human pipeline gates are unchanged.

## Open question

Can the user authorize retrieval of the completed audit's package/version/CVE
details and provide the approved HTTPS deployment, controller-owned revision
descriptor and scoped credential references for final recording acceptance?

## Durable memory

The actual `append_memory` tool inserted coding, QA, post-coding and security
learnings as manual-engineering records. Existing run/execution/approval counts and
the approval snapshot remained unchanged. Rendered role memory was written by the
tool, not edited by hand.
