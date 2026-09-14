# Software-factory alignment — the logic of the reference designs, what Lantern is missing, and the plan

**Status: PROPOSAL v1** (2026-09-08) — written for dimash + Justin. Sources are three
videos watched end to end (frames + captions) on 2026-09-08 via the `/watch` plugin:

| # | Source | What it is |
|---|--------|------------|
| A | Ray Fu, *How to build a software factory with 7 Claude Fable agents* (short, 1:38) | The role split: seven single-purpose agents with hard boundaries and one human approval |
| B | IndyDevDan, *My Super Simple Software Factory (For Agentic Engineers)* (29:52) | The mechanics: AI Developer Workflows = agents **plus code**, deterministic gates, a model stack, observability, a skill that operates the factory |
| C | Boundary (Vaibhav Gupta) + HumanLayer (Dex Horthy), *How to Build a Software Factory for AI Coding Agents* (1:10:45) | The enterprise picture: the four-layer stack, buy-vs-build per layer, the feedback→repro→PR pipeline they run in production, human-time minimisation |

Timestamps below are `A 0:19`, `B 11:22`, `C 25:05`. Where a claim is about Lantern it was
checked against `AGENTS.md`, `workflow/PIPELINE.md`, `docs/DECISIONS.md` and the code.

## 1. The logic the three sources share

Each source is a different altitude on the same design. Read together they reduce to
nine rules.

1. **One agent, one purpose, hard boundaries.** The failure mode named first in A
   (0:01–0:14): one session acting as analyst, architect, back-end, front-end, tester and
   reviewer at once, so a wrong assumption in planning becomes wrong code everywhere.
   The cure is a roster where each agent has one job, its own prompt and its own
   permissions — a read-only researcher, a story writer, a project manager, a back-end
   engineer confined to back-end folders, a front-end engineer confined to front-end
   folders, an end-to-end verifier, a validator (A 0:19–1:18). B says the same thing as
   an operating rule: one agent, one prompt, one purpose (B 21:01).
2. **Research before planning, story before blueprint, validation after everything.**
   A's order is deliberate: map the codebase first so plans use real files and patterns
   (A 0:19–0:31); turn the rough idea into a user story with acceptance criteria and
   edge cases (A 0:31–0:39); only then produce the technical blueprint — data model, API
   shapes, file changes, migrations (A 0:39–0:44); at the end a validator reads the
   original story, the spec and what was built and reports what is missing, insecure,
   quietly skipped, or off-spec (A 1:11–1:18). The human approves the story + plan
   before any engineer runs (A 1:19–1:23, the "waiting for your approval" gate).
3. **Agents propose, code disposes.** B's central claim: agents plus code beats agents
   alone (B 2:29, 13:28). Every agent phase is followed by deterministic checks written
   in code (B 11:22–11:32); agents must emit typed, validated JSON and are re-prompted
   until it validates (B 12:07–12:20); tests, lint, format and type checks run as code
   steps, and only *failures* go back into an agent's context (B 13:51–14:02). C runs the
   same idea as bounded while-loops: fix review-bot findings until mergeable, at most
   three iterations, then hand to a human (C 25:05–25:14).
4. **Right model at the right cost, per phase.** B's stack has a strong thinking model
   on planning and review and a cheap fast model on building (B 9:20–9:26; planner and
   reviewer configs at 18:26–18:39, 22:01). The models B lists are the ones this repo's
   Azure resource is meant to carry — GPT-5.6 Terra and Luna alongside Gemini Flash and
   Kimi K3 (B 1:43–1:49). C's practitioners write most features with Terra or Sol and
   reach for a frontier model only for UI-heavy work (C 5:29, 6:37–6:53). Every agent is
   configured on the same four axes — context, model, prompt, tools (B 18:18–18:26).
5. **Observable, customizable, reusable — or you cannot improve it.** Swim-lane view
   per workflow, compiled system + user prompts, tool calls, and a cost breakdown per
   agent phase (B 1:33–1:57, 11:29–11:35, 20:51–21:01); restart a workflow from its
   session id (B 21:08–21:10). Design for the thousandth run, not the first (B 22:26–
   22:40).
6. **The factory must be operable by an agent, and install itself.** A skill teaches an
   agent the workflows the factory has, how to run one, how to add an ADW, how to set up
   a roster, and a `/install` recipe copies the factory into a new codebase (B 6:41–
   6:47, 24:53–26:19). "If you can teach your agents to do it, why are you doing it by
   hand" (B 26:33).
7. **Four layers, open interfaces, buy or build each one.** C's enterprise stack:
   control plane / orchestration (dispatch, sessions and plans, scheduling, review and
   iteration on code, permissions/audit/spend, compounding engineering — C 40:00–41:07);
   harness (agent, tools, skills, memory, compaction, testing, MCP, auth; inner vs outer
   harness — C 36:23–37:19); dev environment (dependencies, internal services, preview
   environments, identity provisioning — pets or cattle — C 34:02–36:19, 41:43–42:10);
   infrastructure (VMs, containers, isolates, lifecycle, snapshots, warm pools — C 33:47).
   Composition over inheritance: buying one layer must not force buying the ones below
   it (C 56:53–57:23).
8. **Untrusted input never becomes work directly; owned artifacts do.** C's production
   pipeline: user feedback is untrustworthy by definition → check whether it is already
   fixed on nightly → search and de-duplicate → spend your own tokens to build a repro →
   *then* create the issue → classify difficulty with an evaluated agent → fix or plan →
   ping a human shepherd in Slack with repro, fix and PR (C 16:14–19:33). Raw code from
   feedback is never executed (C 31:11–31:24). Every past repro is re-checked on every
   PR, forever, because it is cheap CPU time (C 17:21–17:35). Every change to the factory
   must ship its own metrics, and the team holds an eval set of past issues (C 20:18–
   20:27, 30:33–30:52).
9. **95 % automatic, not 100 %; minimise human time, never remove the human.** A
   fully automatic system is much harder than a 95 % one (C 32:29–32:37); humans hit
   merge (C 25:23–25:33); the whole design pressure is pushing human time down (C
   19:00–19:06) — don't notify a human until the bot is happy (C 25:31), queue fifteen
   prompts and let models argue overnight, then review in the morning (C 11:59–12:19),
   and use a large prototype PR as the spec for re-implementation in ≤3k-line reviewable
   PRs (C 12:27–12:40, 14:55–15:31).

## 2. Gap analysis — reference designs vs Lantern today

| # | Dimension | Reference designs | Lantern today (verified) | Gap |
|---|-----------|-------------------|--------------------------|-----|
| 1 | Role boundaries and write scopes | Back-end and front-end builders with folder-scoped write permission, in parallel (A 0:46–1:02) | One `coding` agent per run in auto mode with a writable whole checkout (D14); sandbox per stage, never pushes | **Medium.** No path-scoped write permissions, no parallel builders |
| 2 | Research before planning | Read-only researcher maps patterns, similar features, risks first (A 0:19–0:31); B's scout ADW (B 4:44–6:02) | `pre-coding` reads the product through a read-only mount plus the D15 `<env>` block, then writes blast radius | **Low–medium.** Research is folded into planning; no reusable scout artifact for the story or the builders |
| 3 | Story with acceptance criteria | Story writer produces the user story, acceptance criteria and edge cases; everything downstream validates against it (A 0:31–0:39, 1:02–1:18) | The brief template (problem, outcome, scope, non-goals) is written by Justin; no acceptance-criteria artifact exists in a run | **High.** Nothing downstream has a contract to be validated against |
| 4 | Requirements validator | Reads story + spec + build; reports missing / insecure / skipped / off-spec (A 1:11–1:18) | `post-coding` checks cleanliness, debt, backward-compat; `security` checks risk; nobody checks the feature against the requirements | **Medium–high** |
| 5 | End-to-end tests as durable evidence | Verifier writes E2E flow tests per acceptance criterion; repros re-run on every PR forever (A 1:02–1:09, C 17:21) | `qa-dev`/`qa-staging` drive the real UI with video evidence (stronger for humans) but leave no test code in the product repo | **Medium.** Evidence is not executable or cumulative |
| 6 | Deterministic gates between phases | Code validates each agent output; typed JSON envelopes; tests/lint/typecheck run as code (B 11:22–14:02) | Mechanical postconditions on presence + validity of reports, artifacts, memory rows, videos (proven under concurrency); product tests/lint run only if the coding agent chooses to | **High for auto coding.** Prerequisite for a cheap coding tier |
| 7 | Bounded fix loops, human fallback | Verifier failures go back to the builder; max N iterations then a human (B 9:11–9:16, C 25:05–25:14) | QA→coding loops exist per run folder; no automatic bounded loop; `code_complete` reaches a human immediately | **Medium** |
| 8 | Review bot and merge automation | Fix review-bot findings until green; agentic merge queue keeps the branch mergeable after human approval; humans merge (C 24:59–26:21) | PR is the payload, human approves, agents never merge (D14) — keep that; no bot review pass, no merge babysitter | **Medium** |
| 9 | Model stack | Strong planner/reviewer, cheap builder, per-agent config on context/model/prompt/tools (B 9:20, 18:18) | Two env tiers, both pointing at `gpt-5.6-sol`; no reasoning-effort setting anywhere | **Closed at the config level today (D16).** Blocked on Azure deployments for the actual split |
| 10 | Observability and cost | Swim lanes, compiled prompts, per-phase cost, restart by session id (B 1:33–2:41, 21:08) | Mission Control timeline, per-stage token ledger, per-turn traces in chat, retry with the same session | **Near parity.** Missing: the compiled prompt per stage execution in the UI |
| 11 | Agentic access and self-install | A skill lets an agent run, extend and install the factory (B 24:53–26:19) | `lantern` chat agent has read-only DB tools (D13); starting runs, choosing repos and approving gates are CLI/web only; `AGENTS.md` is the install surface | **Medium** |
| 12 | Feedback trust pipeline | Already-fixed check → dedup → owned repro → issue → evaluated classification → shepherd (C 16:14–21:08) | `DEBUG-LIFECYCLE.md`: triage → repro → root cause → fix → regression → postmortem, owned by `debug` | **Medium.** Missing dedup, already-fixed check, classification evals, the cumulative regression suite, the never-run-raw-feedback rule |
| 13 | Evals of the factory itself | Every PR to the factory pushes metrics; issue database doubles as an eval set (C 20:18–20:27, 30:33) | Proof tests for mechanics (verification, coding stage, isolation, video) — none for output quality | **Medium–high under token-max:** infinite tokens with no measure of what they buy |
| 14 | Four-layer stack | Control plane / harness / dev env / infra, each buy-or-build behind open interfaces (C 22:10–42:10) | Control plane strong (Postgres state machine + Mission Control + gates); harness is a hand-rolled Agents SDK loop, Codex swap deferred (D14); dev env = one sandbox image (Py 3.12 + Node 22 + git) on one t3.large, cap 2; infra = Docker on EC2 | **Medium.** Dev-environment layer is the thin one: preview environments, identity provisioning, toolchains, cattle sandboxes |
| 15 | Human gates | 95 % automatic; humans on merge and hard cases (C 32:29) | Four named HITL gates, `HITL: required` escalation, blocked ≠ failed | **Parity — keep** |
| 16 | Human-time minimisation | Overnight prompt queues, argue-it-out loops, slop-PR-as-spec, ≤3k-line PRs (C 11:59–15:31) | Gates wait synchronously; no prompt queue; no PR-splitting step | **Low–medium**, after Phase B |
| 17 | Intake: scheduling, webhooks, chat | Dispatcher listens to Linear, Slack, GitHub; cron; a DB behind it (C 28:49–29:41, 40:20) | Daemon claim loop; Slack front door planned (Symphony plan Phase 1); no cron or webhook intake | **Medium** |
| 18 | Multi-repo coordination | Coordination repo / simulated monorepo (C 46:14–48:04) | One product repo per run (D15) | **Low** for now |

What Lantern already has that none of the three sources do: durable Postgres state
with kill-recovery, a sandbox per stage with a proven isolation battery, fail-closed
approval rows, and verification that fabricated deliverables cannot pass. That is the
control-plane layer C calls the most underserved (C 39:55–40:03). Keep it.

## 3. What changed on 2026-09-08 (D16)

- **Three-tier model stack** in `tools/azure-runner/orchestrator.py`: `tier_for()` →
  `reasoning | coding | fast`; `LANTERN_MODEL_<TIER>` with fallback `coding → fast →
  reasoning`; `LANTERN_EFFORT_<TIER>` → `ModelSettings(reasoning=Reasoning(effort))`
  on every Agent (stages, `pipeline.py ask`, the Chat tab's specialist calls);
  `LANTERN_EFFORT_CHAT` override for consults. Test: `test_model_stack.py`.
- **Azure fact:** the resource has one deployment, `gpt-5.6-sol`. `gpt-5.6-terra`,
  `gpt-5.6-luna`, `terra`, `luna`, `flash` all return `DeploymentNotFound` (probed with
  `smoke_test.py`). So the split dimash asked for — Terra on research/scoping/planning,
  a Flash-class model on coding — is wired but resolves to `sol` until the deployments
  exist. In an Azure-OpenAI-only fleet (D7) the Flash analogue is `gpt-5.6-luna`.
  **Corrected 2026-09-14 (D26, §6):** sol is the frontier size, terra the mid, luna the
  cheap one — so sol plans and reviews, terra builds, luna labours. Still one deployment
  on that date.
- **Positioning:** README and AGENTS.md present the system as a software factory with
  Lantern as codename. Identifiers stay `lantern`.

### Shipped later the same day (D17) — Phases B and C, minus parallel builders

- **Stage 0** `00-story.scout` (`researcher`) + `00-story.write` (`story`) with the
  `story_signoff` gate; roles in `agents/researcher`, `agents/story`.
- **Typed envelopes** (`factory.ENVELOPES`): `research.json`, `story.json`, `plan.json`,
  `validation.json`, validated as postconditions and cross-checked against the story.
- **Quality gate as code + bounded fix loop** in stage 3 auto mode (`lantern.toml
  [quality]`, `LANTERN_FIX_ROUNDS`, `gate.json`), write scope enforced on the handoff.
- **Validation** `05-post-coding.validate` (`validator`) — a verdict per criterion,
  `fail` stops the run; **rework** `pipeline.py rework <run> --to …` is the loop
  primitive. Tests: `test_factory.py`. Gaps 3, 4, 6, 7 closed; 1 (parallel scoped
  builders) now has its mechanism (write scope) but not its second sandbox.
- **Proven live** on `feat-20260908-status-facts` (stage 0 in-process against sol):
  research passed with path verification; the story writer blocked on a genuine brief
  contradiction, the decision went into the run folder, the retry passed and the
  `story_signoff` gate opened — the design's honest-failure path and its loop both
  exercised on the first real run. Details in `docs/DECISIONS.md` D17.

## 4. Plan of action

Ordered by leverage per rule in §1; each phase names the gaps it closes.

### Phase A — make the model stack real (this week, human actions)

1. In the Foundry portal create deployments `gpt-5.6-terra` (coding) and `gpt-5.6-luna`
   (fast) on `lantern-prod-agent` — sol, already deployed, is the reasoning tier (D26
   corrected the order: sol > terra > luna). Verify: `smoke_test.py gpt-5.6-terra gpt-5.6-luna`.
2. Set `LANTERN_MODEL_CODING=gpt-5.6-terra`, `LANTERN_MODEL_FAST=gpt-5.6-luna` and
   `LANTERN_PRICE_JSON` in SSM `/lantern/dotenv` and the box `.env`, **restart the
   daemon** (it loads `pipeline.py` at start). Phase B landed (D17), so the mid-tier
   builder is behind the quality gate it needs.
3. First experiments, each an env var (`LANTERN_TIER_OVERRIDES`), ten runs before and
   after: `qa-dev=coding,qa-staging=coding` (does QA on terra find more of what the
   validator later flags?) and `researcher=coding` (does a mid-tier scout change the
   plan's quality?). Results go into §6.
4. Token-max knobs already present: raise `LANTERN_DAILY_SPEND_ALARM_USD` (alarm, not a
   block) and `LANTERN_STAGE_TIMEOUT_MIN` if high-effort stages start hitting 45 min.
   Closes gap 9.

### Phase B — agents propose, code disposes (1–2 weeks)

1. **Build gate as code, inside the coding stage's sandbox, after the agent's turn:** run
   the product's test, lint and typecheck commands (read from the product's `AGENTS.md`
   or a `lantern.toml`), attach the result to `handoff.json`, fail the stage on red.
2. **Bounded fix loop:** on red, re-enter the coding session with only the failures
   (never the passing output), at most three attempts, then `BLOCKED` with the failure
   as the one question. Same loop shape for stage-4 bugs → coding.
3. **Typed handoff envelopes:** every stage emits a JSON envelope next to `report.md`
   (schema per stage: task plan, changed files, known gaps, confidence map) validated by
   the orchestrator; `report.md` stays the human view. Closes gaps 6, 7; unblocks A.3.

### Phase C — story, research, validation (2 weeks)

1. **Story writer** as a stage-0 phase (`00-story`, `reasoning` tier): brief → `story.md`
   with numbered acceptance criteria and edge cases; new gate `story_signoff` before
   ui-ux. Ray Fu's agent 2; the contract everything else is checked against.
2. **Researcher** as a read-only phase at the start of stage 2 (`02-pre-coding.scout`,
   `fast` tier): patterns, similar features, risks → `research.md`; the planner cites it.
3. **Validator** as a `05-post-coding.validate` phase (`reasoning` tier): acceptance
   criteria × (diff, QA charter, videos) → coverage table with missing / skipped / off-spec
   / insecure; `fix-now` items feed the Phase B loop.
4. **Acceptance-criterion E2E tests:** `qa-dev` additionally lands Playwright specs in
   the product repo under a `lantern/` test folder, one per criterion, so evidence
   becomes cumulative and runs on every PR. Closes gaps 2, 3, 4, 5.

### Phase D — parallel scoped builders (after C; 2 weeks)

Split stage-3 auto mode into `backend` and `frontend` builders with **path allowlists**
enforced by the host on the bundle (a commit touching a path outside the builder's
scope fails the handoff — same presence-and-validity discipline as D14), running as
two sandboxes on the same branch base and merged by the host. Closes gap 1.

### Phase E — human-time minimisation on the PR (2 weeks)

Review-bot pass before a human sees `code_complete` (a `review` role or an external
bot), bounded fix loop as in B.2, and a merge babysitter that keeps an approved branch
mergeable until a human merges. Slack front door from the Symphony plan carries the
shepherd ping. Closes gaps 8, 16, part of 17.

### Phase F — feedback trust pipeline and factory evals (ongoing)

1. `DEBUG-LIFECYCLE.md` gains: already-fixed-on-latest check, dedup against open runs,
   the rule that feedback-supplied code is never executed, difficulty classification with
   a forced re-classification by diff size, and every repro added to the cumulative suite.
2. **Evals:** a `tools/evals/` set built from past runs — plan quality (pre-coding),
   classification accuracy (debug), validator recall (Phase C) — and the rule from C:
   any PR to this repo that changes an agent's prompt, skills or gates reports its eval
   numbers. Closes gaps 12, 13.

### Phase G — agentic access and the dev-environment layer (trigger-based)

Write tools for the `lantern` chat agent (start run, set-product, approve with
reason), a `/factory` skill that documents the workflows the way B's cookbook does, a
`lantern.toml` install recipe for product repos; per-run preview environments and
identity provisioning in the sandbox layer; warm sandbox pools when the t3.large cap
(2) hurts. Closes gaps 11, 14, 17.

## 5. Decisions needed

1. **Azure deployments** — who creates `gpt-5.6-terra` and `gpt-5.6-luna`, and when. Nothing in
   Phase A works without them. Still open on 2026-09-14: no Azure CLI or management
   credential on the laptop, so it is a portal click by whoever owns the subscription.
2. **Cheap coding tier timing** — *decided 2026-09-14 (D26):* Phase B landed with D17, so
   the builder moves to the mid size (terra) the day it is deployed; the cheapest size
   (luna) builds nothing — B's warning about a cheap builder without code gates
   (B 13:33–13:49) is answered by the gate, and no factory in the §6 survey builds on
   its smallest model.
3. **GitHub repository rename** to `software-factory` — one click on GitHub, then
   `git remote set-url origin …` on every clone and the box's `infra/ec2/bootstrap.sh`
   SSM parameters. Recommended, but a human action.
4. **Pipeline shape** — Phases C and D add phases and two roles; `AGENTS.md` calls the
   pipeline fixed. Adding phases inside existing stage directories keeps every run
   folder and gate intact; adding `00-story` changes the stage table and needs Justin's
   sign-off.
5. **Token-max guardrails** — keep the spend tripwires as alarms and raise them, or
   remove them. Recommend keep-and-raise: the ledger is how Phase F's evals are priced.

## 6. Which model runs which phase — the survey behind D26 (2026-09-14)

Dimash's ask: the state-of-the-art model only for planning, a less expensive one for
the builders, the cheapest for labour — "other software factories are built like
this". Checked against what the systems actually publish; every claim below was read
on the page cited, and "not found" is said where it is so.

### 6.1 The three deployments, verified

`gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` are OpenAI's three GPT-5.6 sizes as
Azure sells them (Foundry catalog, version 2026-07-09; 1.05 M context, 128 K output,
knowledge cutoff February 2026 — learn.microsoft.com, "Foundry Models sold by Azure").
Microsoft's launch post ("GPT-5.6 now available in Microsoft Foundry"): Sol "delivers
the most advanced reasoning capabilities yet, supporting extended reasoning, agentic
workflows, and code-focused scenarios"; Terra "a balanced model for everyday work,
delivering performance competitive with GPT-5.5 at a lower cost"; Luna "the fastest and
most affordable model in the family, making it well suited to high-volume,
latency-sensitive workloads".

| Size | Deployment | $/1M in / cached / out (Azure Standard Global) |
|---|---|---|
| frontier | `gpt-5.6-sol` | 5 / 0.50 / 30 — promo 4 / 0.40 / 20 from 2026-09-01 to 2026-11-30 |
| mid | `gpt-5.6-terra` | 2 / 0.20 / 12 |
| cheap | `gpt-5.6-luna` | 0.20 / 0.02 / 1.20 |

OpenAI's own price list (developers.openai.com/api/docs/pricing) carries the same
numbers; requests above 272 K input tokens bill at roughly double. So the order is
**sol > terra > luna** — the message that started this had terra as the strongest; the
mapping follows its intent with the verified order. On 2026-09-14 `lantern-prod-agent`
still has only `gpt-5.6-sol` deployed (terra / luna: `DeploymentNotFound`).

### 6.2 What each system publishes

| System | Phases it distinguishes | Model class per phase | Where it says so | Confidence |
|---|---|---|---|---|
| openai/symphony | none — one Codex thread per issue | one frontier model at max effort: `codex --config 'model="gpt-5.5"' --config model_reasoning_effort=xhigh` | github.com/openai/symphony — elixir/WORKFLOW.md, SPEC.md | high — *against* tiering |
| Codex CLI (what Symphony wraps) | main agent vs subagents (`default`, `worker`, `explorer`); plan mode | per-subagent `model` / `model_reasoning_effort`; OpenAI: "Use `gpt-5.6-terra` when you want a faster, lower-cost option for lighter subagent work"; `plan_mode_reasoning_effort` for planning; "medium" effort for everyday interactive coding, "high or xhigh … for your hardest tasks" | learn.chatgpt.com/docs/agent-configuration/subagents; …/config-file/config-reference; the GPT-5 Codex prompting guide | high |
| Aider | architect (solve) → editor (format the edits) | strong reasoning model plus a cheaper editor; R1 + Sonnet scored higher than o1 alone at "14X less cost" | aider.chat/2024/09/26/architect.html; aider.chat/2025/01/24/r1-sonnet.html | high |
| Claude Code | plan vs execution; subagents | `opusplan`: "In plan mode: uses opus … In execution mode: automatically switches to sonnet"; subagents carry their own `model`, "routing tasks to faster, cheaper models like Haiku"; since v2.1.198 Explore *inherits* the main model instead of always running on Haiku | code.claude.com/docs/en/model-config; …/sub-agents | high |
| Anthropic guidance | routing; lead + workers | "Routing easy/common questions to smaller, cost-efficient models … and hard/unusual questions to more capable models"; an Opus lead with Sonnet subagents beat a single Opus | anthropic.com/engineering/building-effective-agents; …/multi-agent-research-system | high |
| Cline / Roo Code / Kilo Code | Plan vs Act; per-mode models | Cline: "a stronger reasoning model for planning and a faster model for implementation"; Kilo Auto: Architect / Orchestrator / Plan → Opus, Code / Build / Debug / Explore → Sonnet — "frontier-level thinking where it matters, cost-effective execution where it doesn't"; Cline's telemetry: most users keep the mid model for both modes | docs.cline.bot/core-workflows/plan-and-act; blog.kilo.ai/p/auto-model-picks-the-right-ai-model; cline.ghost.io/plan-act-model-usage-patterns-in-cline | high |
| Cursor | a per-request router; an explore subagent | "Simple work goes to the most price-efficient models, UI updates go to the model with the best taste, and more complex, long-horizon problems go to frontier reasoning models" (30–50 % cheaper); "The explore subagent uses a faster model by default" | cursor.com/blog/router; cursor.com/docs/subagents | high |
| Cognition Devin (Fusion) | lead vs sidekick | the frontier lead makes "the plan, the interpretation of ambiguity, the final review"; the sidekick "explores code, implements changes, runs tests, and reports back"; 35–60 % cheaper; rejects prompt-level routers because task difficulty "reveals itself late" | cognition.com/blog/devin-fusion; …/local-fusion | high |
| Factory Droids | subagent tiers light / medium / heavy; review depth | `explorer` = light, `worker` = medium, each pinnable; **review `deep` (the default) = `gpt-5.6-sol` at `high`**, `shallow` = a cheap model | docs.factory.ai/cli/configuration/mixed-models; github.com/Factory-AI/droid-action | high — frontier on review |
| OpenHands | plan / implement / review; the condenser | "Start with a strong but expensive reasoning model to inspect the repository and write a plan. Switch to [a cheaper model] for the implementation loop. Switch back for final review, test failure analysis, or a risky refactor"; summarisation on an "often cheaper model" | openhands.dev/blog/model-choice-llm-profiles; docs.openhands.dev/sdk/arch/condenser | high |
| GitHub Copilot | none per phase; auto model selection | one user-picked model for the coding agent; auto selection reserves "higher-cost reasoning models for problems that truly need it" | github.blog changelog 2026-04-01; docs.github.com, auto-model-selection | high |
| Google Jules | a plan critic | a separate "Planning Critic" agent (−9.5 % task failures); models come with the plan tier, not the phase | jules.google/docs/changelog | medium |
| Amazon Kiro | none — per-mode model request "Closed as not planned" | one model | github.com/kirodotdev/Kiro/issues/4812 | high (absence) |
| Sourcegraph Amp | main agent vs oracle | Sonnet as the main agent; the oracle is a read-only o3 / GPT-5 subagent "good at reviewing, at debugging, at analyzing", deliberately not over-invoked | ampcode.com/news/oracle; …/gpt-5-oracle | high |
| MetaGPT / ChatDev / AgentCoder | roles, not tiers | one backbone for every role | arxiv 2308.00352, 2307.07924, 2312.13010 | high |
| BudgetMLAgent, RouteLLM, FrugalGPT | cascade / router | cheap by default, escalate on failure: −94 % cost with higher success (BudgetMLAgent); RouteLLM −85 % cost at 95 % of GPT-4 — on chat benchmarks | arxiv 2411.07464; lmsys.org/blog/2024-07-01-routellm; arxiv 2305.05176 | high, chat benchmarks |

Vendor sizing guidance: OpenAI — build with "the most capable model for every task …
then try swapping in smaller models"; Microsoft's effort table — minimal for "bulk
operations, simple transforms", low for "triage, short answers, simple edits", medium
for "moderate coding", high for "complex planning, analysis, multihop reasoning"
(learn.microsoft.com, Foundry "model choice guide"; its model router claims "up to 60 %"
saving at comparable quality). Cost shape: agentic coding spends ~1000× the tokens of
code chat, input tokens dominate (often above 99 %), and "accuracy often peaks at
intermediate cost" (arxiv 2604.22750). Nobody publishes a planning-versus-build split;
every router vendor's saving (Cursor, Devin, Replit, Foundry: 30–65 %) comes from moving
the build / test loop off the frontier model.

### 6.3 Consensus, and where Lantern lands

| Phase | Consensus class | Lantern (D26) |
|---|---|---|
| planning / architecture | frontier, high effort — unanimous | `reasoning` → sol: story, ui-ux design, pre-coding |
| research / scoping | mid; small only for raw search | sol for now — 2.5 min of a 40-min run, and the plan is built on it; `researcher=coding` is experiment 2 |
| code generation | mid — the majority; Symphony and Copilot dissent with one strong model end to end | `coding` → terra, behind the D17 quality gate that makes a cheaper builder safe |
| test / QA loop | mid for running and fixing; frontier for failure analysis | fix loops ride the coding tier (terra); charter execution → luna, and `qa-dev=coding,qa-staging=coding` is experiment 1 |
| code review | split — Factory deep = sol at high, Amp's oracle, Devin's lead for "the final review"; cheap pre-screens elsewhere | `reasoning` → sol: the review bot is the merge gate |
| security | frontier, high — inferred; no system publishes a security-specific choice | `reasoning` → sol |
| cheap labour (search, summarise, classify, bulk generation) | small | `fast` → luna: ui-ux divergence, QA charter runs |
| orchestration / routing | a frontier or mid orchestrator; routing by a small classifier or by stage | consults route by role; routing is by **stage**, never per prompt (Cognition's argument) |

Two honest caveats. The one system closest to Lantern's control plane, Symphony, does
not tier at all; and prompt-level routers are benchmarked on chat, not on multi-step
coding. Tiering by stage with an env-var override for experiments is the conservative
reading of both.
