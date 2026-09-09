# Regression tests — every past bug, every run (D20)

Each bug run's repro stage writes one test here (`test_<slug>.py` for this repo; a
product repo uses its own framework under the same `lantern/regressions/` path) from the
agent's own understanding of the defect — never from code in the untrusted report. The
fix stage lands it on the fix branch, where it fails before the fix and passes after.

This repo's `lantern.toml [quality] test` command discovers this directory, so every
future coding run re-runs every repro. Delete a test only with the postmortem that
explains why the behaviour it guards no longer exists.
