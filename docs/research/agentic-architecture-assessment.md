# Lantern's agentic architecture — assessment and plan

**Date:** 2026-09-09 · **Method:** 6-lens code audit + 7-topic external research, each research
topic adversarially fact-checked; the load-bearing code findings re-verified by hand before
inclusion here. Claims sourced from a research agent are marked *(researched)*; claims verified
directly against this repo carry a `file:line`.

---

## 1. What we actually run

### The substrate

| | |
|---|---|
| Agent runtime | **`openai-agents` 0.22.0** (`openai` 3.3.1) — verified in `tools/azure-runner/.venv` |
| API surface | Azure OpenAI **Responses API**, `set_default_openai_client(azure_v1_client())` — [orchestrator.py:1705](../../tools/azure-runner/orchestrator.py) |
| Tracing | **off** — `set_tracing_disabled(True)`, orchestrator.py:1714 (no platform.openai.com key on the Azure credential set) |
| Agent construction | `Agent(name, model, model_settings, instructions, tools, mcp_servers)` — orchestrator.py:1738 |
| Invocation | `Runner.run(agent, input=<one string>, session, max_turns)` — orchestrator.py:1755 |
| Turn budget | `coding` = 400 (`LANTERN_CODING_MAX_TURNS`), **every other role = hardcoded 120** — orchestrator.py:1447 |

### The honest answer to "harness or structure?"

**Both — and the split falls on a clean line:**

> Lantern has real agent structure everywhere the artifact is **code or git**, and is a thin
> harness everywhere the artifact is a **judgement, a picture, or a video**.

That is exactly where a software factory's value lives, which is what makes it worth fixing.

Per lens:

| Lens | Verdict |
|---|---|
| **Agent loop** | Thin harness — deliberately. A stage is literally `results = [await run_turn(kickoff)]` (orchestrator.py:1768). Every loop-shaping feature has been reimplemented in Python outside the SDK. |
| **Control plane** | Real structure. Postgres state machine, gates, approvals, idempotency keys — but missing the mechanisms that make orchestrators survive machines. |
| **Context engineering** | Real structure in *assembly* (ordered, byte-budgeted, provenance-classed, untrusted-input fenced at orchestrator.py:1162), none in *curation* — nothing is ever selected, ranked, summarised or dropped. |
| **Tools / sandbox** | Real structure against **fabrication**, weak against **containment**. Tools are coarse and task-shaped, error messages are written for an agent to act on. Permissions are documented rather than enforced. |
| **Verification** | Real structure where code can decide. Two verdicts are *recomputed from their own inputs* and a disagreeing verdict fails the stage (factory.py:402, factory.py:483) — that is genuinely rare. But the wall is one artifact deep. |
| **Memory** | Real structure on the **write** path (bound tool, execution-keyed postcondition, Postgres as source of truth). Nothing on the **learn** path. |

### Why the loop being thin is *correct*

This is not the weakness. The SDK's own orchestration docs contrast LLM-driven with code-driven
orchestration and recommend code for "speed, cost and performance", listing exactly our patterns
*(researched, high trust)*. The published research agrees: **Agentless** — localize → repair →
validate, with no model-decided control flow — was the top open-source system on SWE-bench Lite at
32.00% and $0.70/issue, and hit 50.80% on Verified, beating the agent scaffolds of its day
(arXiv 2407.01489, FSE 2025). Our D17 rule *"agents propose, code disposes"* is the published
finding, not a hunch. **Keep it and cite it in AGENTS.md.**

The weakness is that having chosen to own the pipeline, we then *also* declined the SDK's
within-stage machinery. We import `Agent`, `Runner`, `function_tool`, `ModelSettings`,
`SQLAlchemySession`, the MCP servers and three `set_default_*` globals — and nothing else.
`output_type`, `input_guardrails`, `output_guardrails`, `hooks`, `RunConfig`, `tool_use_behavior`
and `failure_error_function` have **zero occurrences** outside `.venv`.

---

## 2. "Pi agents", and how peers actually build

### What you were thinking of

Most likely **[earendil-works/pi](https://github.com/earendil-works/pi)** — Mario Zechner's
MIT-licensed TypeScript agent toolkit, the harness under **OpenClaw** and under
**[withastro/flue](https://github.com/withastro/flue)**, the Astro team's "sandbox agent
framework" and the closest thing in the wild to a Lantern-shaped open-source factory
*(researched; that topic's fact-check came back **medium** trust — treat the star/download
figures as indicative, the architecture as sound)*. Pi ships an `azure-openai-responses`
provider type, so it is not blocked by our Azure constraint.

Not PydanticAI — nobody abbreviates it "pi agents", and it is a Python framework, not a factory.
Not Inflection's Pi.

### The one word that matters

The field converged on **"harness" (control plane) vs "compute" (execution plane)** in roughly the
last twelve months: OpenAI added a harness/compute split with Docker and unix-local sandbox
clients to the SDK we already run; AWS renamed the Strands repo to `harness-sdk`; Microsoft
shipped a "Harness Agent"; PydanticAI v2 split out `pydantic-ai-harness`.

**`orchestrator.py` + `pipeline.py` + `factory.py` is a harness. Sandbox-per-stage is the compute
plane.** We built this before it had a name. Worth adopting the vocabulary in AGENTS.md so future
readers place us correctly — and worth noticing that the frameworks are chasing our architecture,
not the reverse.

### What happened to the role-cast factories

This is the most useful peer data, because it is a *negative* result about our own shape:

| System | What it is | Where it went |
|---|---|---|
| **MetaGPT** | Role cast passing documents ("Code = SOP(Team)"), shared message pool | ~70k stars, but effectively frozen as a factory — latest tagged release **v0.8.2, 2025-03-09** (fact-checker corrected the original claim of v0.8.1/2024). Team moved to a commercial product (MGX, Feb 2025) and to *learned* orchestration (AFlow, **ICLR 2025 oral**) |
| **ChatDev** | CEO/CTO/programmer/tester "virtual software company" waterfall | **2.0 (DevAll), 2026-01-07** demoted the waterfall to a legacy `chatdev1.0` branch, replaced by a drag-and-drop workflow canvas |
| **gpt-engineer** | Fixed prompt chain | **Archived read-only 2026-04-22** |
| **Devika** | Planner + research + code | Dead since Sep 2024. README points at a successor ("Checkout Opcode…") — it does *not* say "Devika is now Opcode" (fact-checker correction) |
| **OpenHands** | **Single loop** over an immutable event stream; CodeActAgent writes bash/Python instead of many JSON tools | Very active, ~87k stars. 53.0% Verified with CodeAct v2.1 + Sonnet; 60.6% → **66.4% with five attempts** and a trained critic |
| **mini-SWE-agent** | ~100 lines, **bash only**, linear append-only history | Officially **supersedes SWE-agent** in its own docs. (The claim "SWE-agent 2.0, 2026-03-13" was **refuted** — SWE-agent's newest release is v1.1.0, 2025-05-22) |
| **openfactory-core** | Deterministic state machine on **Temporal**; tickets in, reviewed PRs out | Tiny (4 stars) but the closest architectural analogue to Lantern that exists publicly |

**Read this correctly.** It is not "Lantern's shape is wrong." What killed those projects is that
*a role cast with no mechanical gate produces plausible documents and unverified code.* Our
differentiator is the gate layer, not the fact that we have a story agent. The corollary is
uncomfortable: **the gates are the product, and section 3 shows several of ours are vacuous.**

Two peer mechanisms worth copying outright, both from `openfactory-core`:
1. **Refuse vacuous green** — a project that declares no test command is *held*, not passed.
2. **Structural reviewer independence** — review is a separate execution, potentially a different
   engine, and merge is policy-gated with human as the default.

---

## 3. What is actually costing us

Ordered by damage. Everything in this section I verified directly.

### 3.1 `product_git` executes arbitrary commands — **critical, fix today**

The tool documented as *"Run one READ-ONLY git command in the product checkout (no shell)"*
(orchestrator.py:734) filters flags against `PRODUCT_GIT_DENY` (orchestrator.py:727), which covers
`-c`, `--exec-path`, `--output`, `--git-dir`, `--work-tree`, `-o`, `--ext-diff` — but **not
`--open-files-in-pager`**. Verified empirically against a non-tty `subprocess.run(capture_output=True)`,
the exact shape `_product_git` uses:

```
git grep --open-files-in-pager="sh -c 'echo PWNED > …/pwned.txt'" -n Lantern -- README.md
→ exit 0, empty stdout, marker file written
```

Every read-only stage holds this tool. **Fix:** add `--open-files-in-pager`, `--pager` and `-P` to
the deny list *and* pass `GIT_PAGER=cat` + `-c core.pager=cat` in the subprocess env (belt and
braces — the deny-list approach is a blocklist on a surface git keeps extending).

### 3.2 The blast radius of a compromised stage is the whole repo — **critical**

- `write_file` → `_writable()` → `_safe()` confines to `REPO` and then denies exactly three paths:
  `workflow/RUNBOARD.md`, `agents/*/memory.md`, the jsx manifest (orchestrator.py:619-633).
  **An agent can write `tools/azure-runner/orchestrator.py`.**
- `read_file` → `_resolve_read()` → `_safe()` confines to `REPO`, which contains
  `tools/azure-runner/.env` — Azure key, GitHub PAT, Postgres DSN, QA password, PostHog key.
- `stage_tools(role, run_id, stage, execution_key, paper)` takes `role` and uses it **only** to
  bind `append_memory` (orchestrator.py:1434). Twelve roles, one toolbelt, differentiated by two
  booleans. The per-role matrix in `docs/AGENT-TOOLING.md` §6 does not exist in code.

### 3.3 The gates are one artifact deep — **critical, and this is the real one**

Every mechanical check verifies the **shape** of a claim, never its **content** — with one
exception (`_paths_exist`, factory.py:163, called from exactly one place: `_check_research`).

| Gate | What it actually enforces |
|---|---|
| QA video | `is_file() and st_size > 0 and st_mtime >= floor` (orchestrator.py:1676). Stale-attempt reuse *is* correctly blocked. But `write_file('…/media/x.webm', 'x')` satisfies it. **The blind-vision-loop class is not closed.** |
| Validation evidence | `_nonempty_str(c.get("evidence"))` (factory.py:386). The last gate on the acceptance-criteria contract cannot distinguish evidence from assertion. |
| Review findings | `file` must be a string, `line` a positive int or null — neither is resolved against the diff. **An empty approve is the cheapest valid review.** |
| Five stages | `01-ui-ux`, `04-qa-dev`, `05-post-coding`, `06-security`, `07-qa-staging` have **no typed envelope at all**. Verification = "report.md exists + one `role_memory` row." |
| `report.md` | Existence only. No size, no content; only the literal word `BLOCKED` fails. |

The two ideas that would fix most of this **are already in the repo, unused as postconditions**:
the `collect_jsx` hash manifest (host-written provenance an agent cannot forge) and the D22
execution trace (a complete record of what tools were actually called).

The external evidence says this is the highest-value area by a distance:
- **ImpossibleBench**: GPT-5 exploited conflicting tests **66–93%** of the time, and *stronger
  models cheat more*; read-only test access was the best-value mitigation (arXiv 2510.20270).
- **"To Run or Not to Run"** (ISSTA 2026): in **81–100%** of failed cases, commercial coding agents
  passed their own agent-executed validation and failed official evaluation. *An agent's own test
  run is not evidence.*
- **Agentless §5.1.3**: of 213 generated reproduction tests that looked valid, only **94** actually
  detected the ground-truth fix — a ~56% false-signal rate.
- **SWE-bench+**: **31.08%** of "passed" patches were suspicious because the tests were too weak.

### 3.4 No lease, no retry, no checkpoint — **major**

- `heartbeat_at` appears in **three `INSERT`s and zero `UPDATE`s** (pipeline.py:511, pipeline.py:646,
  review.py:759). The heartbeat sweeper `docs/ORCHESTRATION.md` describes does not exist.
- There is **no application-level retry or backoff** on any model API failure. A `MaxTurnsExceeded`
  or an Azure 429 propagates through a blanket `except Exception`, marks the run `failed`, and
  waits for a human `pipeline.py retry`. On startup credits with D18 fan-out hitting one
  deployment, throttling is a *content* failure today when it should be a retriable one.
- Crash recovery flips `status='executing'` → `'running'` and **re-executes the entire stage**,
  losing every model turn already paid for. `run_state` / `run_state_version` are dead columns.
- Any exception out of `Runner.run` destroys both the D22 trace and the token ledger for that
  execution — the diagnostics die exactly when you need them.

### 3.5 Memory is an append-only log nobody reads back — **major**

- Retrieval is `read_text()` of the whole `memory.md` (orchestrator.py:495). No selection, no
  ranking, no cap, no expiry, no dedup, no cross-role routing.
- `consolidated` is **read** (`WHERE NOT consolidated`, orchestrator.py:673) and **never written**.
  The consolidation protocol in AGENTS.md has no implementation.
- The postcondition is `count(*) > 0`, and the corpus shows what that buys: `agents/qa-dev/memory.md`
  holds real operational judgement; `agents/ui-ux/memory.md` holds five retry-narration entries from
  a single stage. To the next prompt they are indistinguishable.

### 3.6 Context is 93% invariant — **major**

A measured stage prompt is ~42k chars, of which **~2,800 chars are run-specific** and roughly 20k
are maintainer-facing prose rather than agent-actionable instruction. Meanwhile the skills files
tell most roles to re-read files that are *already inlined*, and traces show they obey. For the
bug-lifecycle stages the task block is vacuous — it contains nothing about the bug.

---

## 4. The plan (D23–D28)

Ordered by payoff per unit of effort. Every step is shippable alone. No new infrastructure.

### D23 — Close the containment holes *(hours)*
`orchestrator.py`
1. `PRODUCT_GIT_DENY += ("--open-files-in-pager", "--pager", "-P")`; set `GIT_PAGER=cat` and
   `-c core.pager=cat` in `_product_git`'s subprocess env.
2. Scope `_writable()` to `workflow/runs/<run-id>/` + the role's own outputs instead of all of
   `REPO`. Keep the three existing named refusals.
3. Deny `read_file` on `**/.env`, `**/*.pem`, `**/id_*`; move the runner's secrets out of the repo
   tree (systemd `EnvironmentFile=` / SSM) so the confinement rule and the secret location stop
   being the same directory.
4. Make `stage_tools` actually branch on `role`, and make `docs/AGENT-TOOLING.md` §6 a table
   generated from that code so the doc can never drift again.

### D24 — Evidence must resolve *(days — the highest-value item here)*
`factory.py`, `orchestrator.py`
1. Call `_paths_exist` (factory.py:163) from **every** envelope checker, not just `_check_research`.
2. `_check_review`: a finding's `file:line` must resolve **inside the diff of the branch under
   review**, or the envelope fails. This kills the empty-approve equilibrium.
3. `_check_validation`: `evidence` must parse as one of `path`, `path:line`, `test-id`, or
   `video-url#t=` **and resolve**. A bare sentence stops counting.
4. QA video: verify the container actually decodes (`ffprobe` duration > 0 and ≥1 video stream)
   and record the hash **host-side**, the way `collect_jsx` already does. Presence is not provenance.
5. Add typed envelopes to the five stages that have none. Field order matters — per Tam et al.
   (EMNLP 2024 Industry), GPT-3.5 dropped **76.6% → 49.3%** on GSM8K under JSON mode because the
   answer key preceded the reason key. Our review and validation envelopes already get this right
   (findings first, verdict computed in Python); copy that shape.

### D25 — Make the verifier prove itself *(days)*
`factory.py`, `tools/evals/`
1. **FAIL_TO_PASS**: run the acceptance tests against the merge-base commit and **refuse** to
   proceed unless they fail there. A test that passes before the feature is not evidence.
2. **No-test-is-a-hold**: if a product's `lantern.toml` declares no runnable test command, or the
   diff touches paths with zero covering tests, stages 04/05 return `HELD`, never `PASS`
   (openfactory's rule).
3. **Tests are read-only to the builder.** `check_write_scope` already exists; extend it so
   acceptance-test paths are in no builder's write scope, and hash the QA charter's tests at
   creation. ImpossibleBench says this is the best-value mitigation available.
4. Add **tokens, wall-clock and estimated Azure cost** to `tools/evals/REPORT.md` and to the
   `check_pr.py` table. Today `REPORT.md` carries quality numbers and no cost numbers — we cannot
   currently tell a quality win from a bill.
5. Score what the factory actually sells: **false-green rate** (gate passed, human rejected) and
   false-red rate. No public benchmark measures this and it is our product.

### D26 — Use the SDK we already pay for *(days)*
`orchestrator.py`, `pipeline.py`
1. `output_type=` on every enveloped stage. Azure's Responses API supports structured outputs;
   since SDK v0.15.0 refusals raise `ModelRefusalError` instead of silently looping. One schema
   trap *(researched)*: Azure rejects `'default'` inside a property definition, so generate strict
   schemas without Pydantic defaults. Keep the Python re-validation — belt and braces, and it is
   what makes the verdict recomputation sound.
2. **Retry and backoff** around `Runner.run`, classifying 429/5xx as retryable and populating the
   `error_class` column that already exists. Wrap it so a failure still writes the trace and the
   token ledger.
3. Wire the dead `run_state` / `run_state_version` columns using `RunState.to_json()` /
   `Runner.run(agent, state)`. This shrinks the unit of replay from *the whole stage* to *the
   turn*, and it is the same SDK with no new dependency.
4. `max_turns_for` from a per-role env var instead of a flat 120; log tool-call count and prompt
   tokens per execution into Postgres and surface both in the Mission Control execution drawer.
5. Turn tracing back on via **OpenTelemetry → Azure Monitor** (`OpenAIAgentsInstrumentor`), which
   is the documented path when there is no platform.openai.com key *(researched)*.

### D27 — Make the fan-out decision mechanical *(days)*
`builders.py`, `factory.py`
1. Refuse to fan out unless the plan's builder scopes are **provably disjoint**; fail the plan
   envelope when two `write_scope` globs overlap (they are currently compared as literal strings).
2. Derive N from a static import/symbol graph over the product repo rather than from an LLM's
   proposal: N = number of independent clusters, clipped to **[1, 4]**. Mark hub files (migrations,
   lockfiles, shared types, root config) unassignable. **N=1 is a first-class outcome, not a
   fallback** — the evidence is consistent that concurrent *writers* is where multi-agent value
   goes negative, while concurrent *readers* is robustly positive.
3. Give the integrator, the reviewer and the validator **clean context**: the merged tree, the
   contracts and the failing gate output — never the builders' transcripts. Cheaper *and* better.
4. Run the gate on the **merged** tree after the integrator, including a whole-repo typecheck — a
   clean `git merge` is the absence of a postcondition, not one.
5. Cheap wins available now: fan out the read-mostly stages (research, post-coding review,
   security, debug hypothesis search) where parallelism is unambiguously positive.

### D28 — Close the learning loop *(days)*
1. Implement consolidation (nothing sets `consolidated = true` today) and cap what gets inlined —
   rank by recency + role + explicit tags, budget it in bytes.
2. Raise the memory postcondition above `count(*) > 0`: reject entries that are pure retry
   narration. `agents/ui-ux/memory.md` is the worked example of the failure mode.
3. Cut the invariant 93%. Move maintainer-facing prose out of the compiled prompt; delete the
   skills instructions telling roles to re-read files already in context. Measure each cut against
   the D20 eval suite — we have the harness, so this is a measurable change, not a taste change.
4. Fill the bug-lifecycle task block, which is currently vacuous.

---

## 5. What not to do

**Do not adopt a second framework at the orchestration layer.** The churn is the observed base
rate, not a hypothetical: AutoGen is in maintenance mode pointing at Microsoft Agent Framework;
LangChain/LangGraph did a 1.0 rewrite; PydanticAI went v1→v2 in nine months and *halved* its
breaking-change window; Atomic Agents changed GitHub orgs. Adding one would cost the D17 invariant
for capabilities we can buy piecemeal.

**Do not migrate to Temporal / Restate / DBOS / Inngest.** We are on the hand-rolled side of every
line that matters: one host, a genuinely fixed state machine, low run volume, and a coarse
expensive unit of work. Three specific reasons:
- **No engine makes `git push` idempotent.** The hardest reliability problem we have — crash
  between push and checkpoint, then a duplicate PR — is hand-written code under every option.
- **Determinism discipline is charged twice** in a system whose prompts change weekly and whose
  runs sit at gates for days. Prompt drift becomes a non-determinism error on replay rather than a
  recoverable condition.
- **A day-long human gate should be a database row, not a suspended process.** Our `approvals`
  table is *better* than an engine primitive here, because Mission Control, Slack and the CLI can
  all query it and it records who decided.
- Also, as of now the Temporal ↔ `openai-agents` integration would require pinning the SDK back
  roughly three minor versions or vendoring the plugin *(researched)*.

**Do not replace stage sequencing with SDK `handoffs`.** The SDK's own orchestration page
recommends code orchestration for exactly our case. `handoffs` would move control flow back into
the model — the thing D17 exists to prevent.

**Do not add a critic-of-the-critic, a debate stage, or multi-round reflection.** Kamoi et al.
(TACL): no prior work demonstrates successful self-correction from prompted-LLM feedback outside
tasks exceptionally suited to it; self-correction works when there is *reliable external feedback*.
This licenses **removal**: any stage whose only feedback is a model reflecting on its own output
should be deleted or converted to take a mechanical signal.

**Do not chase public benchmark numbers.** SWE-bench closed Verified submissions on 2025-11-18 to
academic teams with peer-reviewed publications — an admission that leaderboard entries were not
reproducible science. UTBoost found 345 patches wrongly labelled resolved, flipping 18 Lite and 11
Verified ranks. Our own frozen-run evals on our own repos are the primary signal, not a supplement.

**One thing to reconsider, not reject:** `agents/*/skills.md` + the prompt builders are the
"elaborate scaffolding" that current GPT-5.x guidance says to trim in favour of stating the
destination and the success criteria. Do it one role at a time with D20 measuring the delta.

---

## 6. Two open items

1. **Pin the SDK.** `openai-agents[sqlalchemy]>=0.22` is an unpinned lower bound on a 0.x package
   where the minor carries breaking changes and ships roughly every five days. v0.21.0 alone forced
   `openai>=3.0.0` and an httpx→httpx2 swap. Add an upper bound before the next box rebuild.
2. **Judge reliability is our hardest constraint and we cannot fix it yet.** A genuine cross-family
   jury needs a second model family, and we have one Azure deployment. Until then: strip authorship
   and stage provenance from what the reviewer and validator see, randomise comparison order, and
   report **Cohen's kappa against a human-labelled set** rather than raw agreement — raw agreement
   overstates by 10–41pp depending on benchmark (Norman, Rivera & Hughes, ~541k judgments).
   `validator_agreement` currently compares the validator to QA's `bugs.md`, which is agent-vs-agent,
   not agent-vs-truth.
