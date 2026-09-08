# Stage Report: 00-story.scout — feat-20260908-status-facts

- **Agent/author:** researcher
- **Date:** 2026-09-08
- **Status:** PASS-WITH-NOTES

## Summary

Mapped the existing two-query status flow, stored branch/version facts, clock-based age precedents, tests, documentation, and current consumers. The riskiest finding is that `tools/azure-runner/pipeline.py` still stamps pipeline version `2` and begins its feature stage list at stage 1, so projecting the stored field alone cannot establish the brief's v2/v3 distinction. The primary exemplar is `tools/azure-runner/pipeline.py`, with its contract pinned by `tools/azure-runner/test_status_json.py`.

## Work performed

- Read the feature brief twice and traced `status` from argparse dispatch through `cmd_status()`, its two database reads, `status_payload()`, JSON serialization, and the separate human renderer.
- Opened and mapped the run/approval schema, branch-resolution semantics, pipeline-version stamping, focused status tests, and the adjacent README contract.
- Searched for callers and consumers of `cmd_status`, `status_payload`, `status --json`, branch fields, pipeline version, gate timestamps, and age calculations.
- Opened the current chat snapshot and Mission Control gate-age implementation/tests to verify existing print-time clock and nonnegative elapsed-time behavior.
- Checked all branches for prior commits for this run; none exist.
- Produced the typed research envelope and re-read it after writing. No product code was changed and no tests were executed in this read-only phase.

## Findings / results

1. **[medium] Pipeline-version provenance:** the target checkout stores and exposes pipeline-version infrastructure, but currently stamps `PIPELINE_VERSION = "2"` and has no stage-0 entry in its feature stage list. This is the highest-risk dependency for the stated v2/v3 consumer goal.
2. **[medium] Time-dependent payload:** `age_seconds` adds wall-clock behavior to a shaper whose tests currently compare repeated direct calls. Existing Mission Control tests establish clamping future timestamps to zero, but the status tests do not yet carry a clock seam or age boundary cases.
3. **[low] Contained blast radius:** status has one CLI dispatch, two reads, one focused test module, and one adjacent documentation paragraph. No code caller of the status payload was found; chat and Mission Control use independent database snapshots.
4. **[fact] No schema work:** all requested source columns already exist with the requested storage types and nullability.
5. **[fact] Working-branch semantics:** a null stored `product_working_branch` means derive the effective branch from the run id; it does not mean the run has no work branch.

## Artifacts

- `research.md` — cited narrative map of the status flow, adjacent patterns, consumers, risks, conventions, and likely files.
- `research.json` — typed research envelope for the story writer and downstream stages.
- `report.md` — this execution summary and handoff.

## Handoff notes for the next stage

Start with the medium pipeline-version provenance finding before turning the brief into acceptance criteria: the requested output field and the mechanism that stamps v3 are separate facts in the current checkout. Preserve the brief's distinction between nullable stored `product_working_branch` and any derived effective branch, and make the nonnegative, print-time nature of gate age explicit enough to test without weakening the byte-identical human-output contract.

## Open questions (BLOCKED status must have exactly one)

None.

## Memory candidates

- 2026-09-08: In Lantern, `product_working_branch = NULL` means “derive the effective branch from the run id,” not “there is no work branch”; research and machine-contract reviews must distinguish stored provenance from resolved runtime behavior because D15 preserves null for older and fresh-branch runs.


## Story phase

- **Agent/author:** story
- **Date:** 2026-09-08
- **Status:** BLOCKED

### Summary

Drafted **Status JSON carries branch and version facts** with six numbered, externally checkable acceptance criteria and matching Markdown/JSON artifacts. The contract covers nullable stored branch facts, pipeline-version output, nonnegative print-time gate age, valid JSON, unchanged human output, the two-read invariant, and documentation. Story signoff is blocked because the requested v2/v3 distinction is not achievable by projection alone while the inspected checkout still stamps new runs as version `2`.

### Work performed

- Read the brief and both research artifacts, confirmed the scout did not block, and used its verified map rather than repeating product research.
- Converted every desired outcome and must-have into six criteria with focused null, empty-result, future-time, sub-second, populated-output, and query-count edge cases.
- Preserved the brief's non-goals and sharpened them to exclude consumer changes, effective-branch derivation, schema work, extra reads, dependencies, and non-ASCII output.
- Wrote and re-read `story.md` and `story.json`; the typed envelope has unique sequential IDs `AC-1` through `AC-6`, non-empty criterion text, list-valued edge cases/non-goals, and one open question.

### Findings / results

1. **[contract]** Six criteria cover all requested JSON facts and protect the existing machine-readable and byte-identical human-readable behavior.
2. **[edge semantics]** A null stored `product_working_branch` remains JSON `null`; deriving an effective branch is deliberately outside this payload.
3. **[blocking contradiction]** The brief's consumer outcome requires distinct v2/v3 provenance, but research found that the inspected run-creation path still stamps version `2`; the stated status-only scope does not resolve that provenance gap.
4. **[HITL]** Story approval is required after the scope question below is answered and, if necessary, the criteria are revised.

### Artifacts

- `story.md` — approver-readable user story, six criteria, edge cases, non-goals, and the blocking question.
- `story.json` — typed twin consumed by downstream stages.
- `report.md` — combined scout and story-phase handoff.

### Handoff notes for the next stage

Do not advance to story signoff until the pipeline-version producer scope is decided. If version-3 stamping is included, revise the story so the producer behavior is explicitly testable; if projection-only scope is confirmed, retain AC-1's requirement to report the stored version faithfully and record that the broader v2/v3 discrimination outcome is deferred.

### Open questions (BLOCKED status must have exactly one)

Should this feature also update run creation to stamp `pipeline_version` as `"3"` (and include any stage-0 definition needed to make that version truthful), or is success limited to exposing the existing stored value even though the inspected checkout stamps new runs as `"2"`?

### Memory candidates

- 2026-09-08: When a machine-readable status field is meant to distinguish pipeline generations, verify that run creation stamps distinct version values; exposing a stored field alone cannot satisfy the user outcome if every new run still receives the old version.


## Story phase — attempt 2

- **Agent/author:** story
- **Date:** 2026-09-08
- **Status:** PASS

### Summary

Revised **Status JSON carries branch and version facts** into a four-criterion contract aligned exactly with the brief's four must-haves. The newly recorded decision resolves the prior blocker by limiting this feature to exposing stored `pipeline_version` values and assigning version stamping to separate D17 work. The story is ready for human `story_signoff`.

### Work performed

- Re-read the updated brief, including its decision that version-3 and stage-0 stamping are outside this story.
- Replaced the prior six-criterion draft with four observable criteria covering per-run branch/version facts, per-gate print-time age, byte-identical human output, and the existing two-read database boundary.
- Kept valid JSON and empty collections as edge behavior under the relevant machine-output criteria rather than adding requirements beyond the four must-haves.
- Made version stamping, consumer changes, effective-branch derivation, filtering, pagination, schema work, new dependencies, and non-ASCII output explicit non-goals.
- Removed the resolved open question, wrote matching `story.md` and `story.json`, and re-read both artifacts to verify sequential unique IDs `AC-1` through `AC-4`, non-empty text, list-valued fields, and an empty `open_questions` list.

### Findings / results

1. **[contract]** Four acceptance criteria map one-to-one to the brief's four must-haves and are directly falsifiable at the CLI or database-read boundary.
2. **[scope]** `pipeline_version` must be returned exactly as stored; changing what run creation stamps, including version `3` or stage-0 work, is explicitly excluded.
3. **[edge semantics]** Stored nullable branch facts remain nullable in JSON, future gate timestamps cannot yield negative ages, and empty run/gate collections remain valid JSON arrays.
4. **[HITL]** Standard human story approval remains required; there are no unresolved story questions.

### Artifacts

- `story.md` — approver-readable user story with four criteria, focused edge cases, non-goals, and no open questions.
- `story.json` — validated-shape typed twin for downstream stages.
- `report.md` — prior scout/attempt-1 history plus this superseding story-phase result.

### Handoff notes for the next stage

Treat the stored `pipeline_version` projection and the separate producer-side version-stamping work as distinct. Preserve the nullable stored `product_working_branch` value rather than substituting the effective derived branch, and make gate-age tests deterministic around sub-second and future timestamps.

### Open questions (BLOCKED status must have exactly one)

None.

### Memory candidates

- 2026-09-08: When a brief explicitly separates version stamping from exposing stored version provenance, keep stamping as a non-goal and assess the projection contract against stored values; otherwise a valid consumer-facing increment is incorrectly blocked by an independent producer change.
