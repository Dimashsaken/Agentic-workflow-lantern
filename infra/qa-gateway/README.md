# Disabled gateway candidate

External launch remains an unconditional hold in `qa_transport.launch_external`.
This candidate is not staging approval or proof of host network containment.

The released mitmproxy 12.2.3 pins cryptography, h2, msgpack and tornado below
available advisory fixes. `upstream.lock` pins the official unchanged wheel;
`vendor_wheel.py` checks its SHA-256 and creates `12.2.3+lantern1`, changing only
Version and four exact dependency requirements plus the required dist-info path
and RECORD hashes. Every runtime member is copied unchanged. The generated wheel
is reproducible, independently hash-pinned in `requirements.lock`, and its full
metadata change/provenance is saved inside the image. This is a local modified
candidate, not an upstream release. `pip check` is mandatory at image build; no
resolver conflicts are suppressed. `--no-deps` is used only to download the
hash-pinned original wheel before transformation, never for installation.

The runtime base is the inspected official Python 3.12.14 slim-trixie Linux amd64
manifest, pinned in the Dockerfile. A complete-image audit of the earlier sandbox
base found unrelated Node/npm/browser dependencies with advisories, so the gateway
now carries only Python, required system libraries/CA roots, and the gateway lock.
`build-tools.lock` pins the build installer in both Python environments. After
hash-checked installation and `pip check`, the complete installer and ensurepip
bootstrap are removed from the runtime image: their vendored libraries are not
needed by this gateway, and even the latest installer still carried advisories.
Dependency changes require rebuilding the candidate image.
The sandbox and recorder images are unchanged. A base digest change requires a new
image inventory, audit and actual TLS regression run.

```
docker build -f infra/qa-gateway/Dockerfile -t lantern-qa-gateway-candidate .
```

`test_policy.py` and `test_vendor_wheel.py` are hermetic checks. For actual image
hook validation, mount `test_image.py` read-only into a new throwaway container,
run it with `/opt/gateway/bin/python`, and use `--network=none`. That test uses
loopback TLS and a temporary fixture CA appended to the container's own public
trust bundle; its gateway subprocess runs as UID/GID 1000 with the real entrypoint.
It does not alter host trust or the built image. Discard the test container after
its result; do not retain its temporary CA private keys in artifacts.

A successful image test does not certify a deployed gateway transport. Native
Linux host namespace rules and independent positive/forbidden endpoint packet
observations remain separate acceptance requirements. Inventory and audit the
actual base/runtime OS packages and image identities before any human activation.
