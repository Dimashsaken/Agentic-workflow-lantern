# relay-model — drive a stage with a brain you control

An OpenAI-compatible **stand-in endpoint** for the harness. Every model request the
Agents SDK makes is written to a directory and answered from a terminal (or by another
agent) with `relay_brain.py`; the harness — tool policy, envelopes, quality gate,
postconditions, publication, gates — runs exactly as it does against Azure, because
nothing in it changes but the base URL.

Use it to validate the pipeline's mechanics without a provider, to debug a stage prompt
turn by turn without spending credits, or to demonstrate what a stage does. It is **not
a model provider** (D7: every fleet brain is an Azure OpenAI deployment); a run driven
through it says so in its reports.

```bash
# 1. serve
tools/azure-runner/.venv/bin/python tools/relay-model/relay_server.py --dir ~/.lantern/relay --port 4141

# 2. point the harness at it (in the daemon's environment)
export AZURE_OPENAI_ENDPOINT=http://127.0.0.1:4141 AZURE_OPENAI_API_KEY=relay \
       LANTERN_OPENAI_API=chat_completions LANTERN_MODEL_REASONING=relay-brain \
       LANTERN_MODEL_TIMEOUT_S=3600 LANTERN_MODEL_RETRIES=0

# 3. answer requests
python tools/relay-model/relay_brain.py --dir ~/.lantern/relay wait          # prints what the stage sees
python tools/relay-model/relay_brain.py --dir ~/.lantern/relay reply 1 \
    --call read_file '{"path": "workflow/runs/<run>/brief.md"}'
python tools/relay-model/relay_brain.py --dir ~/.lantern/relay reply 7 --text "Report written; append_memory called."
```

`chat_completions` is required (the relay does not implement the Responses API), which
means image tool outputs are not carried — fine for every stage except a Paper vision
critique loop.

Written 2026-09-11 while validating the harness in a sandbox that had no Azure
credentials. It was exercised only as an endpoint (health, request capture); no
pipeline run has been driven through it yet — the first person to do so should note
the turn counts per stage in this README.
