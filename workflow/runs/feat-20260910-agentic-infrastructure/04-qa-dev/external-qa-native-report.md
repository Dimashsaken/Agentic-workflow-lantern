# Native external QA transport acceptance — 2026-09-11

- **Author:** qa-dev independent execution; parent integration after task continuation
- **Run:** feat-20260910-agentic-infrastructure
- **Branch:** codex/external-qa-acceptance
- **Status:** PASS-WITH-NOTES for native network and packaged gateway controls;
  BLOCKED for trusted product deployment recording acceptance

## Executed result

On the existing Ubuntu 24.04 fleet host (`7.0.0-1012-aws`), the final candidate pair
passed **14/14 calibrated network denials**, **2/2 permitted paths**, exact local
Docker/container/cgroup/netns identity checks, rule readback and wrong-execution
refusal. Four independent AF_PACKET observers saw **23/13/6/20 packets** with the
restrictions absent, then **0/0/0/0 forbidden packets** with them installed. Socket
observers recorded zero additional forbidden application bytes.

- Gateway: `sha256:05b1729428c8cdcfb099758f81d916afb94550eae48fad72e4c075e151d0b378`
- Recorder: `sha256:bbf5ea982390470ce5d0331ac07fc004906ac1e896df5ebe2d84e7e6ff8d59fd`
- Native recorder base: `sha256:7dbf7f4d1ad88d25023412a3258c9fcad806e9c2730a360bddb1498030cfa76b`
- Final SSM execution: `a89dd8c0-7818-4fd5-bf21-ee52fea98bc2`, success

The recorder base differs from the prior workstation recorder. The native pair
was built and tested independently; no acceptance was transferred between tags.
The base's pre-existing tag was not changed. A separately downloaded, hash-checked
buildx package was extracted under the owned temporary build directory because
the host lacked the plugin; no host package installation or fleet restart occurred.

The actual native gateway image also passed **24/24 loopback TLS/session tests**
and the installed zlib ordinary API/terminal-error test. These cover both TLS
legs, request identity/framing denials, fresh CA rejection across sessions and
closing existing connections on gateway death/policy expiry. The image test runs
with networking disabled and a synthetic upstream CA confined to its disposable
container. It is separate from the native firewall socket probes.

## Denial coverage and limitations

The charter covers alternate/direct TCP, UDP DNS, QUIC-shaped UDP, IPv6, a
simulated link-local metadata destination, an owned listener in the host namespace,
another execution, and actual Docker embedded DNS. Each blocked path has a working
permissive control. It never sends test data to real cloud metadata or unrelated
host services. These are packet/socket restrictions, not proof of complete
application-level HTTPS or browser behavior across a deployed product.

The harness starts controller-owned idle processes in the exact candidate images
and then installs restrictions before sending probes. It does not launch the
production recorder or mint a capture receipt. `external_transport_verified` and
`trusted_deployment_verified` remain false in the machine result.

## Cleanup and review fix

The final run stopped all 12 owned observers and removed its four containers and
two networks. Evidence remains at
`/tmp/lantern-external-qa-054d0a998dd8-fbn5od5x`. No fleet service or host-wide
firewall policy changed. The initial tcpdump-based observer encountered a snap
SSM/AppArmor signal restriction; it was replaced by bounded Python observers and
its exact owned resources were separately cleaned before rerunning.

Post-coding found that an early cleanup error could skip remaining resources.
Cleanup now attempts every independently tracked resource, uses bounded process
termination, aggregates failures and retains an unsuccessful result if any cleanup
is uncertain. **Three native cleanup regression tests** and the independent
reviewer's injected-failure probes pass.

## Evidence

- `external-qa-native-final.json` and `external-qa-native-final-invocation.json`
- `external-qa-native-baseline-result.json`, `external-qa-native-baseline-observers.json`
- `external-qa-native-build-source.json`, `external-qa-native-build-hashes.json`
- `external-qa-native-tls-invocation.json`: 24 TLS tests plus installed zlib test
- `external-qa-native-cleanup-tests-invocation.json`, `external-qa-native-unit.log`
- Native build logs remain in `/tmp/lantern-external-qa-build-998ab62c`; their
  hashes and lengths are recorded without exporting unverified full logs.

## Remaining acceptance

An approved HTTPS target, its controller-owned revision descriptor and scoped
credential references are still absent. The production launcher remains held.
Complete the combined owned-launcher/recorder, lease/cancellation/expiry/death,
deployment-drift and sealed-video receipt charter against that target before
claiming full external QA acceptance. No new browser/video claim is made here.

The actual append_memory receipt is `../03-coding/external-qa-memory.json`, QA row
69; existing runs, executions and approvals remained unchanged.
