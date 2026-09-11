# Narrow QA recorder candidate

The Dockerfile derives from an explicitly supplied reviewed sandbox image and
adds `libnss3-tools`. It installs the public per-execution CA only into an ephemeral
container home, keeps Chromium certificate checks enabled, and records a narrow
controller plan. It never mounts the controller authority directory or CA key.

The continuation-3 local image was built as
`sha256:a743cef23a8d1049392135d806aeab9be3ffb3e65559616ae5a66dea5c52172f`.
An actual internal-network HTTPS fixture passed four browser commands, a full
video decode and controller receipt verification. This image has not passed
external gateway/network acceptance or a complete OS/browser dependency audit.

The trace is redacted command-outcome JSON; it contains no raw request values,
headers, cookies, selectors or fill arguments. It cannot be opened as a Playwright
trace ZIP. Video may show page content, so the controller must still choose safe
test data. The recorded fixture used a masked password field and a disposable
sentinel; the sentinel was absent from the stored trace and stdout.

External launch remains held in `qa_transport.py`. See the run's
`03-coding/bcd-capture-proof.json` and independent QA/security supplements for
actual-media evidence and its limits.
