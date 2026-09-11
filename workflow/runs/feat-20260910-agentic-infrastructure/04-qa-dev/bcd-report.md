# Continuation 3 B–D local QA — 2026-09-11

Author: qa-dev. Status: PASS-WITH-NOTES for the executed local UI scope. This is local engineering evidence, not a registered fleet QA execution, gate decision or staging acceptance.

The committed Mission Control UI at `80babd0` passes four recorded contexts: real authenticated application desktop/mobile and separately labelled synthetic receipt fixtures desktop/mobile. Current infrastructure modules were copied alongside that UI into temporary harnesses. Concurrent UI edits from another task were preserved and excluded from this infrastructure acceptance. The controller-capture API has seven passing injected unit tests; real HTTPS capture acceptance is separately pending.

## Executed checks

- AC-10/11 actual app: preserved disposable run `feat-20260910-live-inprocess-ln2`, executions 16/17, correctly shows absent provenance. Anonymous access requires login; refresh, return navigation and visible mobile evidence pass. No JavaScript errors, HTTP errors or attempted post-login mutations. Parent injected environment-only target/credentials and invoked QA's wrapper; QA independently inspected results and media. Only the designated disposable database was used.
- Protected run/approval/execution snapshots before and after have identical SHA-256 `94f5e1a3b1e74b11cfc28ad27d1234134a96a886ca81f241f475ffb80257d8a1`. No approval or stage was changed. Application startup is not claimed to be entirely read-only.
- AC-10 fixture renderer: valid controller receipt renders hashes and requirements; forged writable mirror, stale attempt and wrong run remain unverified. Unicode/HTML text stays literal. Mobile hash wrapping, theme change, back and refresh pass. No fixture rows were inserted into any database.
- AC-10a API unit suite: `bcd-capture-unit.log` records 7 tests in 0.025 seconds, all pass. This uses mocked video decoding and synthetic receipt inputs; no real-image or deployment claim follows from it.
- All eight generated WebMs fully decode using the production ffprobe/ffmpeg probe. Four current-tree exploratory contexts were retained but excluded; four baseline contexts supply the scoped UI verdict. Trace recording starts after login. Videos/traces remain local; no remote upload is claimed.

## Recorded evidence

Offsets below were checked against decoded frames. Browser JSON event times are wall-clock offsets and differ from video offsets.

| Scope | Video / trace | Verified video time | Duration |
|---|---|---|---|
| Actual baseline desktop | [video](media/provenance-actual-desktop-bcd-baseline.webm) / [trace](media/provenance-actual-desktop-bcd-baseline.zip) | 0:24 — execution 16 absent provenance | 57.16 s |
| Actual baseline mobile | [video](media/provenance-actual-mobile-bcd-baseline.webm) / [trace](media/provenance-actual-mobile-bcd-baseline.zip) | 0:28 — execution 17 absent provenance | 42.28 s |
| Fixture baseline desktop | [video](media/provenance-fixture-desktop-bcd-baseline.webm) / [trace](media/provenance-fixture-desktop-bcd-baseline.zip) | 0:02.8 — invalid receipt refusal | 7.04 s |
| Fixture baseline mobile | [video](media/provenance-fixture-mobile-bcd-baseline.webm) / [trace](media/provenance-fixture-mobile-bcd-baseline.zip) | 0:01 — positive hashes; 0:02.1 — dark theme | 4.12 s |
| Excluded concurrent UI desktop | [video](media/provenance-fixture-desktop-bcd.webm) / [trace](media/provenance-fixture-desktop-bcd.zip) | 0:01 — exploratory fixture | 7.12 s |
| Excluded concurrent UI mobile | [video](media/provenance-fixture-mobile-bcd.webm) / [trace](media/provenance-fixture-mobile-bcd.zip) | 0:01 — layout before hidden-control timeout | 33.08 s |
| Excluded adapted-test desktop | [video](media/provenance-fixture-desktop-bcd-r2.webm) / [trace](media/provenance-fixture-desktop-bcd-r2.zip) | 0:01 — exploratory fixture | 7.08 s |
| Excluded adapted-test mobile | [video](media/provenance-fixture-mobile-bcd-r2.webm) / [trace](media/provenance-fixture-mobile-bcd-r2.zip) | 0:01 — layout; account-menu adaptation subsequently passes | 4.16 s |

Evidence: `bcd-baseline-live-results.json`, `bcd-baseline-fixture-results.json`, `bcd-live-before.json`, `bcd-live-after.json`, `bcd-video-decode.json`. Decoded frame images accompany the media. Baseline fixture source hashes were corrected from the legacy recorder's current-checkout hash collection to the actual `git show 80babd0` bytes served; the JSON records this correction explicitly. Real-app snapshot hashes already describe the baseline temporary runtime.

## Limits and handoff

No new product bug was found in the executed UI scope. `bcd-bugs.md` documents the stale selector in excluded concurrent UI and the remaining capture acceptance limit. Existing v1 manifest display does not establish rendering or persistence of the new QA capture format. No HTTPS origin was invented for the HTTP recordings. External TLS gateway containment, real deployment revision and fully wired stage capture remain unaccepted; staging remains NO-GO. Independent actual-receipt verification is prepared in `bcd-capture-verification.py` and requires the controller's real expected identity/deployment and closed media.

## Durable memory

Sent to the integration owner for the actual append_memory tool: “2026-09-11: Freeze UI sources in the temporary QA runtime when unrelated UI edits share the checkout; otherwise an infrastructure regression script can test a different navigation contract and misattribute failures.” No append_memory tool is exposed in this QA session; no new insertion or direct rendered-memory edit is claimed here.

Status: PASS-WITH-NOTES (local baseline UI only; external capture acceptance pending)
## Direct TLS fixture capture supplement — 2026-09-11

Author: qa-dev. Status: PASS-WITH-NOTES for local `direct_fixture` capture verification. This supplements the earlier pending real-media check; gateway/external denial acceptance remains pending.

Independently executed `bcd-capture-verification.py` in the isolated continuation-3 worktree against the integration owner's freshly sealed actual TLS recording. The positive receipt fully decodes and verifies against separately supplied controller identity/deployment. All **12 negative controls** reject: wrong run, execution key, execution ID, attempt, fence, revision and recording ID; same-size altered video and trace bytes; failed/missing requirement outcomes; and a forged receipt in the writable media directory. **13/13 controls pass.** The negatives modify only disposable copies and preserve the original sealed evidence. No runtime source was edited by QA.

The receipt is explicitly `test_only: true`, `transport_mode: direct_fixture`, and has no gateway image. Recorder image is `sha256:a743cef23a8d1049392135d806aeab9be3ffb3e65559616ae5a66dea5c52172f`. Recording ID is `d13a2182c62d440394ce9f6ac302cfeb`; the identity binds local test execution 1, attempt 1, fence 1. Tested `qa_provenance.py` SHA-256 is `4e097e8f3c99cec7a4a466be3c59e68fe6b4ab6c41459fd28a3197088056de8b`. Receipt SHA-256 is `59ef25d03f673431299fc9d7d46bb1c51f6b84a8510864eaac3aeb819baf826b`; complete outcome/hash evidence is in [bcd-capture-verification.json](bcd-capture-verification.json).

The [actual TLS fixture video](media/bcd-tls-d13a2182c62d440394ce9f6ac302cfeb/d13a2182c62d440394ce9f6ac302cfeb.webm) is VP8, 1280×720, exactly 1.0 second and 41,853 bytes. Independently decoded and visually inspected [frame at 0:00.5](media/bcd-tls-d13a2182c62d440394ce9f6ac302cfeb/bcd-frame-0.5.png) shows the fixture heading, password input and “Capture ready” status. Its SHA-256 is `cf2b326a9ee0c5f86f477a5aae460a379258da21c2fefec3beb133b7f78d8e60`. This short frame proves the page was captured; it does not visually demonstrate every command outcome or a production application flow.

The accompanying [redacted command trace](media/bcd-tls-d13a2182c62d440394ce9f6ac302cfeb/d13a2182c62d440394ce9f6ac302cfeb.trace.json) is 305 bytes, SHA-256 `d8787911ef9d88e162f8c9bc06febd9c322e30fde13ddfe246cec406b69305ba`. It contains command IDs, requirement IDs and outcomes, **not a replayable Playwright ZIP with DOM/network snapshots**. The recorder intentionally omits raw traces because those can contain credentials. This is a documented reduction in diagnostic detail, not equivalence to the usual full trace. Requirement IDs AC-1/AC-2 in this test describe fixture actions, not acceptance of the infrastructure run's capability/Git criteria.

Inspected the integration owner's `03-coding/bcd-capture-proof.py` and `.json`: an actual dedicated recorder trusts only its ephemeral NSS CA, leaves certificate errors enabled, runs against a direct local TLS fixture and seals actual closed media. Its separate disposable PostgreSQL test records matching durable output, wrong-attempt/key rejection, stale-writer refusal, unchanged approvals and cleanup. Those database/container actions were executed by the integration owner; QA did not rerun them. The original application UI before/after approval checks remain unchanged. No gateway was in this path, and no host egress, forbidden destination, production deployment or fully wired fleet-stage capture acceptance follows from it.

QA-BCD-2 is narrowed: actual local direct-TLS media sealing and independent tamper/identity controls now pass; external transport and production capture integration remain open. No new product defect was demonstrated. Staging remains NO-GO.

Memory candidate sent for actual append_memory: “2026-09-11: Label redacted recorder command traces separately from replayable Playwright traces, because preventing credential capture removes DOM/network evidence and a one-second video cannot replace that diagnostic detail.” No memory insertion is claimed by this supplement until its actual receipt is available.

Status: PASS-WITH-NOTES (local direct TLS capture only; no gateway/external acceptance)
### Final capture validator retest — 2026-09-11

QA independently reran the same 13 actual-media controls after transport-mode validation was shared across construction, sealing, verification and persistence. **13/13 pass** against final `qa_provenance.py` SHA-256 `251b6585978ea307c0c5c57b7585d20a8f0419113584c3ea1ef2ccd46b905cc1`; `bcd-capture-verification.json` now records this cutoff. The receipt and media are unchanged, so the preceding decoded video/frame evidence remains applicable and no new browser recording is claimed. Acceptance remains test-only `direct_fixture`, with no gateway or external containment certification.

The integration owner completed the actual QA `append_memory` insertion as row **63**, manual key `manual:feat-20260910-agentic-infrastructure:qa-dev:pending-02d0970f1059`, recorded in `03-coding/bcd-memory.json`. QA inspected that receipt: configured runs/executions/approvals remain 12/23/8, the approval snapshot is unchanged, and no migration or new cluster was created. This satisfies the previously pending memory insertion for the supplied redacted-trace learning; it is not a fleet QA execution or a direct edit to rendered memory.

Status: PASS-WITH-NOTES (final local direct TLS capture retest; external acceptance remains open)
