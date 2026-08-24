# azure-runner — running stages on Azure OpenAI (GPT) deployments

**The constraint this exists for:** Claude Code runs Claude models only — an Azure
OpenAI key cannot power it. But the org's Azure credits can still fund the fleet two
ways:

1. **Claude Code via Microsoft Foundry** (Claude models on Azure, bills against Azure
   credits/MACC) — preferred for the reasoning-heavy stages. Setup:
   `infra/ec2/README.md`.
2. **GPT deployments via this runner** — for stages where an Azure OpenAI model drives
   tools directly (browser QA execution, batch checks, video walkthrough sessions).

Full decision record: `docs/DECISIONS.md` (D2).

## Env-var contract (never commit values — see `.env.example`)

```
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
AZURE_OPENAI_API_KEY=<from SSM>
AZURE_OPENAI_API_VERSION=<current preview/GA version>
AZURE_OPENAI_DEPLOYMENT=<deployment name, e.g. sol or terra>
```

Deployment names (`sol`, `terra`, …) are org-internal Azure *deployment* labels — the
runner treats them as opaque. Any deployment with solid tool/function calling works.

## How a runner session works

The knowledge layer is harness-agnostic, so a runner session is just:

1. Load `agents/<role>/charter.md` + `skills.md` + `memory.md` into the system prompt,
   plus `CLAUDE.md`'s "one rule that matters" section.
2. Give the model tools: browser control (Playwright), file read/write scoped to the
   run folder + its own `memory.md`, shell if the role needs it.
3. Loop until the stage report is written; enforce the report + memory-append
   postconditions in the harness (don't trust the model to remember).

## Harness options (pick one when the first GPT-driven stage is built)

- **OpenAI Agents SDK** (JS or Python) — first-party agent loop; wrap Playwright
  actions as tools; supports Azure OpenAI clients. Best default.
- **Playwright MCP + any MCP-capable client** — reuses the same browser tooling the
  Claude Code agents use.
- **browser-use** (Python) — highest-level "agent clicks around the app" library,
  works with Azure OpenAI via its LangChain client. Fastest to demo, least control.

Whichever harness: video recording is a property of the **browser context**
(`tools/qa-recorder`), not of the model — every option above records the same way.
