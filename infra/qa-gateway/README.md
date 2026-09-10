# Unaccepted gateway candidate

This directory is a continuation-3 implementation candidate, not a deployable
external-QA boundary. `qa_transport.launch_external` always refuses activation.

The exact Linux/Python 3.12 wheel lock contains 43 packages. Independent PyPI
metadata review confirmed the selected wheel hashes but found reported advisories
in cryptography 48.0.1, h2 4.3.0, msgpack 1.1.2 and tornado 6.5.5. The selected
mitmproxy constraints prevent treating a blind dependency upgrade as compatible.
Reachability is not established by a package match; neither is safety established
by disabling an individual protocol. The audit and limitations are preserved at
`workflow/runs/feat-20260910-agentic-infrastructure/06-security/continuation3-dependency-review.json`.

The initial build failed on a package download timeout. A retry was stopped after
the audit; no successful gateway image identity or image acceptance is claimed.
Before activation, resolve and review dependencies, build and inspect the actual
image, validate effective options/event hooks and pass the network acceptance
charter, including zero upstream bytes for rejected decrypted requests. A real
host firewall adapter must deny direct DNS/TCP/UDP, metadata and cross-execution
traffic. Proxy environment variables cannot establish these properties.

The local direct-TLS recorder fixture used no gateway and is explicitly marked
test-only. Its successful recording does not reduce these acceptance requirements.
