# Feature Brief: status --json reports the pipeline version

- **Product repo:** C:/Users/dimas/OneDrive/Documents/GitHub/Agentic-workflow-lantern/.claude/worktrees/lantern-factory-review-agent-58430b
- **Base branch:** claude/lantern-factory-review-agent-58430b
- **Working branch:**
- **Coding mode:** auto

## Problem

`pipeline.py status --json` is what scripts and Mission Control's checks read, and it does
not say which pipeline version produced it. When the shape changes (v2 → v3 added stages),
a consumer cannot tell whether it is looking at old or new output.

## Desired outcome

The JSON status object carries `pipeline_version` (the runner's `PIPELINE_VERSION`) at the
top level, and a unit test proves it.

## Scope

- `status_payload()` in `tools/azure-runner/pipeline.py` adds the field.
- `tools/azure-runner/test_status_json.py` asserts it.

## Non-goals

- No change to the human-readable `status` table.
- No new columns, no database changes.

## Must-haves

1. `pipeline.py status --json` output has a top-level `pipeline_version` string equal to `PIPELINE_VERSION`.
2. A test in `test_status_json.py` fails if the field is missing or wrong.
