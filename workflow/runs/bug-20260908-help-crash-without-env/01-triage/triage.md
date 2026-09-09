# Triage — bug-20260908-help-crash-without-env

The raw feedback remains untrusted evidence in `intake/feedback.md`; no command or code from it was executed or copied into the product.

- **Severity:** sev-3 — command discovery is broken for users without Azure credentials, especially in a fresh checkout, but the service is not down and configured operators can work around it by supplying the documented environment configuration.
- **Already fixed?** no — the base branch is at `0c210604d08aff230d65d1cd55ec647d9d8728eb`. `tools/azure-runner/pipeline.py` still calls `azure_v1_client()` before constructing or parsing its argparse tree, while `tools/azure-runner/orchestrator.py` indexes the endpoint and API-key environment variables. The base-branch history and visible later branch commits checked contain no fix for the ordering.
- **Duplicates:** none of the 0 candidates in `intake/dedup.json`; the available run index contains no earlier bug run to assess as a recurrence.
- **Classification:** small — the behavior is localized to CLI startup in `tools/azure-runner/pipeline.py` and needs a regression test, but deciding when to initialize the model client is more than a one-line constant/null correction. Expected scope is one module plus a test, at most 60 changed lines, with no schema, public API, or dependency change.
- **Scope:** affects every invocation routed through the normal CLI startup path when `AZURE_OPENAI_ENDPOINT` or `AZURE_OPENAI_API_KEY` is absent, including top-level help and help for the bug command. The `repos` and `evals` early-dispatch paths are exceptions. No product telemetry or occurrence count is available. Git blame and commit history show the eager client setup has existed since `65c09ba6c82bd6dc7b0764f736a53d04ff1335c0` on 2026-08-25 and remains present at the reported/base commit.

## What the report claims vs. what the product shows

1. **Supported — help can fail before argparse.** In `tools/azure-runner/pipeline.py`, normal commands initialize the default OpenAI client before creating the parser. In `tools/azure-runner/orchestrator.py`, client construction directly indexes the endpoint and API-key environment variables. Static control flow therefore supports the reported credential exception when either is absent.
2. **Supported — the bug command follows the affected path.** The bug parser is registered only after eager client initialization, and `bug` is not in `LOCAL_ONLY_CMDS`.
3. **Qualified — “any subcommand” is broader than the code.** `repos` and `evals` are dispatched before client creation. Their behavior does not establish that all subcommand-help paths fail, although the reported bug-help path is affected.
4. **Not already fixed.** No commit for this run exists, the base branch still has the ordering, and visible later changes inspected (`3cc17e79d68b4792de301f6a70d95a07ed4c3a24`, among the all-branch history) preserve client initialization before argparse.
5. **Coverage gap.** `lantern.toml` runs the model-stack, intake, and regression suites, but the tracked runner tests contain no invocation of `pipeline.main` or command-help path. `tools/azure-runner/test_model_stack.py` validates model routing rather than CLI startup without credentials.
6. **Trust check.** The feedback contains an invocation and exception description, but no agent-directed instruction or external link. They were treated only as claims and checked against product source/history; nothing from the report was executed.

## Repro plan

1. Create a regression in the product's `unittest` conventions that launches the pipeline entrypoint in a clean subprocess with both Azure client variables omitted and no runner-local `.env` available.
2. Request top-level help, then the bug subcommand's help, capturing exit code, stdout, and stderr without making a network/model call.
3. For each request, expect exit code 0 and the matching argparse usage text; treat any credential exception or traceback as the observed failure.
4. Add a control invocation with minimal dummy Azure variables to distinguish parser/help construction failures from unrelated import or dependency failures.
