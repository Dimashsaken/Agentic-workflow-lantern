# Story — status --json reports the pipeline version

As a script or dashboard reading `pipeline.py status --json`, I want the output to say which pipeline version produced it, so that I can tell old and new shapes apart.

## Acceptance criteria

- **AC-1** The object printed by `pipeline.py status --json` has a top-level key `pipeline_version` whose value equals `PIPELINE_VERSION` in pipeline.py.
- **AC-2** A unit test in tools/azure-runner/test_status_json.py fails when `pipeline_version` is missing or does not equal PIPELINE_VERSION.

## Non-goals

- changing the human-readable status table
- database changes
