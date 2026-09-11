# Native Linux acceptance charter — 2026-09-11

Scope: AC-7a real LinuxNamespaceFirewall/Docker identity and packet containment. This socket-fixture harness does not establish browser TLS, deployment, or live activation acceptance.

1. Pin local container image IDs, record native kernel/cgroups/netns, and keep recorder/gateway on one owned internal private network.
2. Calibrate every forbidden endpoint permissively: TCP, DNS/UDP, QUIC/UDP, IPv6, simulated metadata, an owned host listener and a separate peer container. Real Docker embedded DNS must resolve before installing rules.
3. Install production LinuxNamespaceFirewall. Both recorder-to-proxy and gateway-to-pinned-endpoint positive requests must still pass.
4. Repeat every forbidden probe. Independently owned socket logs must show no additional bytes and destination packet captures must contain zero forbidden packets. DNS must now fail before Docker DNAT.
5. Reject wrong execution binding, remove exact owned containers/networks, retain observer artifacts. Never modify fleet services, host firewall policy, checkout, or production deployment.

No browser is launched by this network-only test; no video evidence is claimed. Full gateway lifecycle/recording remains separately required. Host and images are supplied by the authorized environment, not read as credentials or target URLs from repository files.
