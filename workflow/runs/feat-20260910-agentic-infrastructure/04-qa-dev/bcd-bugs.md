# Continuation 3 B–D QA findings

2026-09-11. No new product defect demonstrated in the executed baseline UI scope.

## QA-BCD-1 — stale fixture navigation selector, resolved in test scope

Severity: 4, test harness only. First run accidentally used concurrently edited Mission Control UI; theme moved inside the account menu. Existing script requested the hidden `dark mode` button and timed out. Positive receipt/layout assertions had passed. Reproduction: run the prior provenance fixture script against those concurrent UI files on mobile; expected visible old top-level theme button, actual button is in a closed account menu.

[Initial video](media/provenance-fixture-mobile-bcd.webm), 0:01 shows readable evidence before the selector timeout. [Adapted test video](media/provenance-fixture-mobile-bcd-r2.webm), 0:01 shows the same layout; the adapted script opens the account menu and completes. Neither recording accepts unrelated UI work. The authoritative infrastructure rerun exports baseline UI `80babd0` into a temporary harness; its unchanged original script passes on desktop and mobile. No runtime/UI source was modified by QA.

## QA-BCD-2 — external capture acceptance remains separate

Acceptance limitation, no new bug severity assigned. Seven injected capture unit cases pass, but those mocked video probes cannot prove real recorder image identity, TLS destination confinement, deployment identity or a live fleet receipt. Ordinary HTTP application videos are intentionally not sealed under a synthetic HTTPS descriptor. The candidate external launcher remains held pending actual-image/firewall acceptance. A positive local HTTPS capture and independent receipt negatives must be recorded separately when available.

2026-09-11 supplement: actual direct TLS fixture capture now independently passes one full-decode positive and 12 rejection controls; see [capture supplement](bcd-capture-supplement.md), [video](media/bcd-tls-d13a2182c62d440394ce9f6ac302cfeb/d13a2182c62d440394ce9f6ac302cfeb.webm) at 0:00.5. Local media sealing is covered. Gateway/external denial controls and production stage wiring remain unaccepted. The accompanying redacted command trace is not a replayable Playwright trace; that diagnostic limitation is explicitly documented.
