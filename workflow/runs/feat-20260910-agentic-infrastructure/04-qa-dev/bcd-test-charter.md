# Continuation 3 B–D local QA charter

2026-09-11. Written before execution. Local engineering only; no fleet gate.

1. AC-10/11: Record current Mission Control desktop/mobile against the designated disposable database only. Verify legacy/absent provenance, reload/navigation, visible evidence and no application errors or post-login mutations. Compare protected run/approval/execution snapshots before and after.
2. AC-10: Separately record production renderer fixtures: valid controller receipt, forged worker mirror, stale attempt and wrong run; verify narrow-screen hash wrapping and literal Unicode/HTML text. These are synthetic fixtures, never real execution receipts.
3. AC-10a: Start controller Capture objects before a fresh recorded local browser session. Use an explicitly test-only policy and controller-owned descriptor. Seal actual closed video+trace files, fully decode with the production probe, then verify the positive receipt. Test same-size video/trace byte swaps, wrong execution/attempt/fence/recording/revision, deployment drift, failed/missing requirements, unclosed writers and forged writable JSON. Preserve receipt identities and source hashes; do not publish environment URLs or secrets.
4. Exploratory bounded probe: inspect the distinction between the new capture format and legacy UI verification. A local receipt proves byte/identity checks only; it does not prove an accepted container image, TLS gateway, external target revision or fully wired stage capture.

No unrelated UI suite or external launch. If the configured local dev service cannot start, report BLOCKED instead of substituting fixtures for actual-app coverage. Media timestamps will be checked against decoded frames rather than browser wall-clock events.

Execution supplement: the controller's real local direct-TLS fixture recording is tested in `bcd-capture-verification.py`. Its `test_only` receipt must explicitly declare `direct_fixture` and no gateway image. One actual full-decode positive and 12 byte/identity/outcome rejection controls pass; frame 0:00.5 was inspected. Its command trace is redacted JSON, not the normal DOM/network Playwright ZIP. See `bcd-capture-supplement.md` for the exact evidence and remaining external acceptance limits.
