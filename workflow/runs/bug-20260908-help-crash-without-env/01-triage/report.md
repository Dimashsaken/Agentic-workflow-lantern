# Stage Report: 01-triage — bug-20260908-help-crash-without-env

- **Agent/author:** debug
- **Date:** 2026-09-08
- **Status:** PASS

## Summary

The untrusted report was checked against the base branch and visible history without executing it. The affected help path is not fixed, is assessed sev-3 and small, and has no dedup candidates. The next stage should turn the clean-environment CLI path into a deterministic subprocess regression.

## Work performed

- Read the bug brief, hash-marked untrusted feedback, and `intake/dedup.json`; the intake directory was not modified.
- Checked the current/base revision, working-tree status, run-specific commits, visible branches, and history for `tools/azure-runner/pipeline.py` and `tools/azure-runner/orchestrator.py`.
- Opened both affected modules and inspected `azure_v1_client`, `main`, local-only dispatch, parser construction, and bug-command registration.
- Inspected `product/lantern.toml`, `product/tools/azure-runner/test_model_stack.py`, `product/tools/azure-runner/test_intake.py`, and the tracked runner-test inventory for existing CLI-help coverage.
- Opened commits `0c210604d08aff230d65d1cd55ec647d9d8728eb`, `65c09ba6c82bd6dc7b0764f736a53d04ff1335c0`, and `3cc17e79d68b4792de301f6a70d95a07ed4c3a24` while checking introduction and possible fixes.

## Findings / results

1. **sev-3 / open:** normal CLI dispatch constructs the Azure client before argparse can process help, while client construction requires endpoint and API-key variables by direct lookup.
2. **Scope:** fresh or otherwise unconfigured checkouts are affected on normal commands; `repos` and `evals` have explicit early dispatch and are exceptions. No telemetry was available to quantify users or occurrences.
3. **History:** the ordering dates to commit `65c09ba6c82bd6dc7b0764f736a53d04ff1335c0` (2026-08-25) and remains at base HEAD `0c210604d08aff230d65d1cd55ec647d9d8728eb`; no existing fix was found.
4. **Dedup:** `intake/dedup.json` supplied zero candidates, so both duplicate arrays are correctly empty.
5. **Classification:** small — one implementation module plus regression coverage, expected at no more than 60 changed lines and without schema/API/dependency changes.
6. **Coverage gap:** the current quality gate does not exercise the CLI help path with Azure variables absent.

## Artifacts

- `workflow/runs/bug-20260908-help-crash-without-env/01-triage/triage.md` — human-readable owned triage facts and scope.
- `workflow/runs/bug-20260908-help-crash-without-env/01-triage/triage.json` — typed triage envelope.
- `workflow/runs/bug-20260908-help-crash-without-env/01-triage/report.md` — this stage report.

## Handoff notes for the next stage

Start with `triage.json`. Build the regression from product source and test conventions, not from the raw report; isolate environment and local dotenv discovery so the failing assertion specifically proves help is gated by eager Azure-client setup. Do not broaden the expected failure to the two local-only commands without checking their separate early-dispatch semantics.

## Open questions (BLOCKED status must have exactly one)

None.

## Memory candidates

- 2026-09-08: CLI help and parser-error paths should be tested with external-service credentials removed, because eager client construction can turn a local diagnostic path into a credential traceback before argparse runs.
