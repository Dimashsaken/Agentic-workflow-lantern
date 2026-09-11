# Architecture Decisions

Read before changing the design. Append-dated; never rewrite old entries — supersede them.

## D1 — 2026-08-24 — Agent knowledge is harness-agnostic files

Each role is `charter.md` + `skills.md` + `memory.md` under `agents/<role>/`. Claude
Code subagents (`.claude/agents/`) are thin wrappers that load these; the Azure runner
loads the same files into its system prompt. **Why:** the fleet spans two model
providers and three execution surfaces (laptop, EC2 interactive, EC2 headless);
duplicating role knowledge per harness would drift immediately. **Consequence:**
wrappers must stay thin — role content added to a wrapper instead of the role folder
is a bug.

## D2 — 2026-08-24 — Provider matrix: Foundry for Claude Code, Azure OpenAI for the runner *(amended by D7)*

Verified against official docs (claude-code third-party integrations, 2026-08):

| Need | Provider | Why |
|------|----------|-----|
| Claude Code sessions/subagents | Claude via **Microsoft Foundry** (`CLAUDE_CODE_USE_FOUNDRY=1`) | Claude Code runs Claude models only (Anthropic API / Bedrock / Vertex / Foundry). Foundry bills CCUs on the Azure invoice and decrements MACC → uses the org's Azure credits. |
| GPT-driven stages (browser QA execution etc.) | **Azure OpenAI** deployments via `tools/azure-runner` | Uses the same Azure credits; an Azure OpenAI key cannot power Claude Code. |

Model pinning on Foundry is mandatory for fleet machines (alias defaults can lag the
resource's enabled models). Config: `infra/ec2/README.md`.

## D3 — 2026-08-24 — QA video = Playwright `recordVideo`, not screen capture

Videos come from Playwright's context-level `recordVideo` (+ tracing), which works
headless on EC2 with no display, GPU, or ffmpeg. **Why:** zero-infra, per-scenario
files, works identically under every harness because recording is a property of the
browser context, not the model driving it. Full-desktop xvfb+ffmpeg capture is the
documented exception, not the default. **Consequence:** videos are per-context — the
"one context per scenario" convention in `tools/qa-recorder` is load-bearing for
reviewable, short videos.

## D4 — 2026-08-24 — The run folder is the only handoff channel

Stages communicate exclusively through `workflow/runs/<run-id>/` reports. No chat
handoffs, no side channels. **Why:** durable, auditable, resumable by any harness, and
it forces each stage to write for a reader — which is also what makes the pipeline
debuggable when a stage goes wrong. Large binaries (videos) live in S3 and are linked,
keeping git fast.

## D5 — 2026-08-24 — Brain/harness split: Claude Code (Foundry) is the default harness; GPT runs in its own harness *(superseded by D7)*

An agent = brain (LLM) + harness (tool loop). Claude Code is a harness that accepts
only Claude brains; "GPT brain inside Claude Code" does not exist. Therefore:
**default all pipeline stages to Claude brain + Claude Code harness via Foundry**
(zero harness code, native subagents/MCP/CLAUDE.md, same Azure credit pool), and run
GPT deployments (`sol`/`terra`) through the OpenAI Agents SDK in `tools/azure-runner`
only where a high-volume second brain earns its keep (bulk QA execution, batch
checks). Both harnesses consume the same MCP tool layer (`.mcp.json`), so tools are
written once. **Consequence:** build order is Foundry fleet first; azure-runner is
deferred until a GPT-driven stage is actually scheduled. Full explanation:
`docs/AGENT-TOOLING.md` §1.

## D6 — 2026-08-24 — Agents act on GitHub as `lantern-bot`, never as humans

One machine identity (machine user now, GitHub App if audit needs grow) with Write on
product repos; fine-grained PAT in SSM. Branch protection enforces the contract:
`main`/`staging` are PR-only with human review; agents push only `feat/*`, `fix/*`,
`proto/*`. Commits carry the run-ID prefix plus a `Lantern-Agent: <role>` trailer;
agent PRs are labeled `agent:<role>`. **Why:** clean audit trail (git shows which
agent did what), instant revocability, and no agent ever inherits a human's broader
permissions. Details: `docs/AGENT-TOOLING.md` §3.

## D7 — 2026-08-24 — Azure OpenAI is the only model provider; OpenAI-native harnesses

Justin's call: the org's ~$25k Azure OpenAI startup credits make GPT deployments
(`sol`, `terra`) effectively free, so **every agent brain is an Azure OpenAI
deployment** — no Claude models, no Foundry. This supersedes D5's Claude-Code-default
and amends D2 (whose factual matrix still holds: an Azure OpenAI key cannot power
Claude Code — which is exactly why the harness changes too). The runtime becomes:

- **OpenAI Agents SDK** (`tools/azure-runner/orchestrator.py`) runs pipeline stages
  on EC2 — one stage per invocation, postconditions enforced in code.
- **Codex CLI** (Azure provider config) is the developer's stage-3 session and the
  headless repo-task tool; it reads `AGENTS.md` natively.
- **`AGENTS.md` is the canonical contract file** (OpenAI-ecosystem convention);
  `CLAUDE.md` is a pointer. `.claude/agents/` wrappers stay in-tree but dormant —
  free insurance if the provider decision ever reverses.
- Deployment routing: `LANTERN_MODEL_REASONING` / `LANTERN_MODEL_FAST` env vars map
  roles to deployments; swapping is a one-var change.

**Consequence:** D1 (harness-agnostic knowledge) is what made this pivot a one-day
change — that invariant is now load-bearing and must be preserved as roles scale.

## D8 — 2026-08-25 — One-call durable loop: Postgres state machine + Agents SDK sessions

Justin's ask: "idea from concept to live with one call," Karpathy-style agentic
loop, Postgres managing all sessions. Design (full doc: `docs/ORCHESTRATION.md`;
research: `docs/research/`): **two-layer durability with no workflow engine** —
an explicit Postgres state machine (runs / stage_executions / approvals /
artifacts / events, claimed by one systemd daemon with `FOR UPDATE SKIP LOCKED`)
around Agents SDK `SQLAlchemySession` per `{run_id}:{stage}` for conversation
persistence in the same Postgres. Human gates are `approvals` rows (fail-closed;
agents have no write path to them); CLI front-end first, Slack buttons + GitHub
PR webhooks later. Temporal and LangGraph rejected for one-box scale; upgrade
path is DBOS Transact, then Temporal's official Agents SDK plugin. Karpathy
grounding: gates are the autonomy slider's detents — one call *starts*
concept→live but never skips the human at choose/approve/ship
("LLMs automate what you can verify"). Tracing to the OpenAI dashboard is
disabled (Azure-only credentials); self-hosted Langfuse is the future option.

## D9 — 2026-08-25 — Stage 1 splits by runner affinity: divergence on EC2, Paper convergence on a design workstation

Paper's MCP is desktop-bound (no headless mode — `docs/research/design-agents.md`),
and divergence is cheap volume work that shouldn't spend Paper's call budget. So the
pipeline's stage 1 becomes two executions sharing one run-folder dir: `01-ui-ux.diverge`
(EC2, `LANTERN_MODEL_FAST`, 5–10 low-fi skeletons + judge pass) and `01-ui-ux.design`
(design workstation, Paper MCP, convergence + critique loop). Mechanism: stage tuples
carry a `runner`; one daemon per runner (`pipeline.py daemon --runner workstation`)
claims only its stages; the workstation daemon preflights Paper's port at startup and
every tick, and daemons heartbeat into a `runners` table so Mission Control shows
"needs the design workstation" instead of a silent stall. The ui-ux agent writes
`01-ui-ux/handoff.json`; the orchestrator builds the `ux_signoff` payload from it and
Mission Control renders Paper URL + option PNGs side by side. Quality is constrained
by the checked-in design layer (`design/design-system.md` + `design/critique-checklist.md`)
because Paper ships no token/component system yet and unconstrained agents produce
generic output. Full plan + phases: `docs/plans/ui-ux-agent-paper.md`. **Consequence:**
stage keys in the DB are no longer always run-folder dirs — anything joining stages to
folders must go through `STAGE_DIR`/`stage_dir()`.

## D10 — 2026-08-26 — Cloud execution: one Docker host, a sandbox per stage, Paper on the developer's own laptop

CTO requirement: the system runs on cloud, every agent gets an isolated shell, and it
serves ~5 developers concurrently. That requirement invalidates four things in the
pre-D10 design — all verified in code, not assumed:

1. **One stage at a time.** `claim_and_step` takes `LIMIT 1` and executes the stage
   synchronously in-process, so a daemon is a single-slot worker.
2. **All agents share one filesystem.** `REPO` is one checkout and `_safe()` scopes
   every write into it; concurrent stages would share a working tree and a product-repo
   clone, colliding on branch checkout.
3. **Two postconditions mutate shared files, and one becomes _unsound_.** The memory
   check is `memory_now == memory_before`; under concurrency another run's append to the
   same role's `memory.md` satisfies it, so a stage that wrote nothing passes. This is
   verification failure, not just a data race. `RUNBOARD.md` has the same contention and
   is derived data Postgres already holds.
4. **Paper's MCP is desktop-bound** and cannot run in a container at all.

**Decisions.**

- **Host: AWS, one always-on VM running Docker.** Kubernetes is rejected for now — the
  operational weight is unjustified for a system that has not completed one end-to-end
  run. Revisit when queueing actually hurts (the same trigger as D8's upgrade path).
  Staying on AWS keeps `infra/ec2/`, SSM and S3; note the standing tension that model
  spend runs on Azure credits (D7) while compute and storage cost cash on AWS.
- **Isolation: one ephemeral container per stage execution.** Own `/work`, own
  product-repo clone at the run's branch, own browser, scoped short-lived credentials
  (never a shared `.env` baked into the image), CPU/memory caps, wall-clock timeout,
  egress allowlist. Container death also removes the stale-artifact bug class found on
  2026-08-26 — a leftover export cannot survive into another run.
- **Concurrency: N containers, existing claim query.** `FOR UPDATE SKIP LOCKED` already
  supports many claimers. The daemon becomes a *dispatcher* that schedules sandboxes; it
  stops executing stages itself.
- **State plane moves out of the git working tree.** Run artifacts to object storage
  (`artifacts.uri` already holds URIs); `RUNBOARD.md` becomes a rendered view that agents
  never write; `memory.md` becomes appends to a `role_memory` table with a consolidation
  job rendering the file. The memory postcondition becomes "this execution inserted a
  memory row" — sound under concurrency instead of accidentally correct at N=1.
- **Paper is NOT hosted.** Its MCP has no auth of its own: it answers plain HTTP on
  `127.0.0.1:29979` and inherits whoever is signed into the desktop app (verified
  2026-08-26). So each developer runs Paper Desktop locally with their own account, and a
  small `pipeline.py daemon --runner workstation` on their laptop reaches the cloud
  Postgres over Tailscale and claims **only `01-ui-ux.design` for runs they own**
  (`runs.created_by`). Five developers means five laptops and five Paper accounts, so the
  design stage has no concurrency ceiling — and there is no GUI VM or server-side seat
  licensing to buy.

**Consequences.**

- Runner identity gains a per-developer dimension (`workstation:<dev>`), routed by
  `runs.created_by`; Mission Control's "needs the design workstation" notice becomes
  per-developer rather than global.
- Every developer doing design work needs their own Paper Pro seat.
- **The memory postcondition must move into the database before concurrency is switched
  on.** Running N>1 against the file-based check silently disables the verification that
  the whole pipeline's trustworthiness rests on. This is a blocking prerequisite, not a
  cleanup task.

**Addendum 2026-08-26 — the blocking prerequisite is DONE (session 1).** Role memory
lives in the `role_memory` table; agents write it only via the `append_memory` tool,
bound to the stage execution's key, and the postcondition is "this execution inserted
a row". `RUNBOARD.md` and `agents/<role>/memory.md` are rendered views of Postgres
(`pipeline.py runboard` / `render-memory`, auto-refreshed on every state change); the
agent write tools reject direct edits to both. `tools/azure-runner/test_verification.py`
proves the old file-diff check passed a stage that wrote nothing under concurrency and
the new check fails it. Sandboxing (session 2) is now unblocked.

## D11 — 2026-08-26 — Direct consult mode: any agent, on demand, advisory and read-only

Justin's requirement: developers can use any single agent for their own purposes, not
only through the fixed pipeline. `pipeline.py agents` lists the roles;
`pipeline.py ask <role> "<prompt>"` runs one — the role's charter/skills/memory in the
system prompt, repo read tools, the Playwright MCP for browser roles, and the role's
routed deployment. Conversations persist per `{developer}:{role}:{session}` as Agents
SDK sessions in Postgres, so follow-up asks continue the thread (`-i` gives a live
loop, `--new` resets, `--session` names parallel threads). Consults are logged to
`events`.

**The deliberate line: consults are advisory.** No write tools, no run ID, no
postconditions — anything that mutates the product or a run goes through a pipeline
run, where verification and gates exist. This keeps "ask the security agent a
question" cheap while making "sneak work past the pipeline" structurally impossible.
Consult memory entries (optional) carry `consult:` execution keys in `role_memory`.
Revisit the read-only line only with evidence it blocks real usage.

## D12 — 2026-08-26 — Execution-plane mechanics: mounts, claims, credentials (session 2)

Decisions made while implementing D10's sandbox-per-stage, each with the why:

- **Run folders are HOST BIND-MOUNTS, not object-storage sync.** Each container gets
  exactly one mount rw: `workflow/runs/<run-id>` from the host checkout. Why: D4 makes
  the run folder the intra-run handoff channel — stages of one run must see each
  other's outputs immediately and atomically; S3 sync would add an eventual-consistency
  window plus a sync daemon that can fail independently. The host checkout keeps git as
  the audit trail, and `artifacts.uri` already speaks `s3://` for the day multiple VMs
  make object storage necessary (same "upgrade when it hurts" trigger as D8).
- **The Lantern repo enters the container as a read-only mount (`/repo-src`) copied to
  a private `/work/lantern` EXCLUDING `workflow/runs`.** No other run's artifacts exist
  inside a container at all — cross-run visibility is structurally impossible rather
  than discouraged. The copy is why image rebuilds are only needed for dependency
  changes, never for repo edits.
- **Claims mark the run `executing`.** The old single-slot loop was double-claim-safe
  only because it executed synchronously; N slots (or a tick during a long stage) would
  re-claim the same run. Every completion path overwrites the marker; a daemon restart
  requeues its own runner's orphaned `executing` runs (one daemon per runner).
- **Credentials cross as a per-stage env allowlist** (Azure endpoint/key, model
  routing, DB URL rewritten to `host.docker.internal`) — never a `.env` in the image.
  Secrets no current stage needs (GitHub PAT, PostHog) are added to the allowlist
  per-stage when such a stage first exists.
- **The host re-checks postconditions after the container's own check.** A compromised
  or lying sandbox exiting 0 still cannot pass without the report on the host-mounted
  run dir and its memory row in Postgres.
- **Egress allowlisting is DEFERRED, stated plainly.** v1 sandboxes have default bridge
  egress. Doing it honestly needs a per-container network + nftables rules or an
  authenticated proxy; bolting on a half measure now would look like a control without
  being one. It must land before any stage processes untrusted third-party input.
- **Image v1 scope:** stages 1–2 and the review stages (Python + Playwright MCP with
  version-locked browsers). qa stages need `tools/qa-recorder`'s node_modules baked in
  — add when a run first reaches stage 4.

**Addendum 2026-08-26 — sandboxes run as uid 1000, not root.** The first sandboxed
stage wrote root-owned files onto the host-mounted run dir (inside the git working
tree), which the app user then could not manage. The entrypoint now starts as
root ONLY to chown the docker-created root-owned mountpoint parents, then drops
itself to uid 1000 (setpriv) — a straight `--user 1000` start cannot write beside
mountpoints docker pre-creates as root. The image keeps browsers in a world-readable
`/ms-playwright` and `HOME=/work`, so nothing runs as root past the first line.

## D13 — 2026-08-31 — Chat surface: consult mode gets a web face, custom agents, one ledger

The ask: talk to the fleet from the browser the way you talk to Claude Code —
per-stage specialists or one chat that does everything, effortless agent
creation, past-chat history, and a backend where sessions and token spend are
tracked end to end. Design doc: `docs/CHAT.md`. Decisions, each with the why:

- **Chat is consult mode (D11), not a new power.** Web consults get the same
  advisory/read-only toolset, the same `consult:{user}:{agent}:{name}` session
  key (so CLI and web continue each other's threads via the SDK's Postgres
  sessions), and the same `consult` audit events. The gate line does not move:
  nothing in the chat surface can start runs, decide gates, or write files.
- **The "one chat" is an orchestrator agent, not a router.** `lantern` carries
  the AGENTS.md contract plus three read-only database tools
  (`pipeline_snapshot`, `run_detail`, `spend_summary`) and `ask_specialist`,
  which runs a one-shot consult of a fleet role and relays the answer with
  attribution. Specialist usage merges into the parent turn's ledger row
  (`model = 'mixed'` when deployments differ — flat rates price those).
- **Transcript state is ours; model context is the SDK's.** `chat_turns` holds
  what the UI renders (user text, final text, an ordered `trace` of tool calls
  and handoffs, the P0.4 token columns); the Agents SDK's `agent_messages`
  holds what the model re-reads. Deliberate duplication: the SDK's message
  shape has drifted between releases and is never parsed for display.
- **Live activity is an in-process bus + SSE, not a queue service.** Subscribers
  are per-session and outlive turns (v1 had them per-turn — a page attached
  while idle went deaf to the next turn; `test_chat_service.py` pins the fix).
  Replay covers mid-turn attach and reconnect. Process-local on purpose (one
  uvicorn, one box, D8's "upgrade when it hurts"); a turn orphaned by a restart
  is marked failed «interrupted», never left pretending, and shutdown closes
  every stream so restarts can't hang on open SSE connections.
- **Custom agents are rows, not roles.** `custom_agents` (name, purpose,
  optional instructions — composed from the purpose when empty, the Dust move)
  get the consult toolset and learn through `role_memory` under their slug,
  embedded into later instructions (table-only; no `agents/<slug>/` folder is
  rendered). An agent that needs to act in the pipeline still becomes a real
  role via `agents/_template/` — the roster page says exactly that.
- **Browser roles consult without their Playwright MCP in v1**, and the card
  says so, rather than spawning a browser per web turn; `pipeline.py ask -i`
  remains the path when a live browser matters.

## D14 — 2026-09-07 — Auto-coding: stage 3 as a fleet stage that ends in a pull request

The ask: the pipeline must take a concept from brief to a ready pull request on its own,
in any git repository, the way a developer's coding agent works in a checkout. Plan
item C2.3 designed it; this records what was built and the choices made on the way.

- **A per-run mode, not a new stage.** `runs.coding_mode = human | auto` (brief field
  `- **Coding mode:**`, `pipeline.py run --coding-mode`, `set-coding-mode`). `03-coding`
  stays the human stage it was; in `auto` the dispatcher executes the `coding` role for
  it like any agent stage and then opens the same `code_complete` gate. Why: the
  pipeline shape, the run folder layout and every downstream stage stay identical — a
  human-mode run and an auto-mode run differ only in who wrote the commits.
- **Agents SDK loop, not Codex CLI, for the first version.** C2.1's de-risk of Codex on
  Azure was not done (open 400s on gpt-5.6 deployments); the plan's stated fallback — the
  same orchestrator with a writable checkout and a shell tool — is what shipped. Codex
  remains a swap-in for the sandbox entrypoint later: the handoff contract (bundle +
  handoff.json) does not depend on which harness wrote the commits.
- **The sandbox never pushes.** Same clone as every other stage, on the run's branch
  (`feat/<date>-<slug>`), writable; commits carry the bot identity and the
  `Lantern-Agent: coding` trailer. When the turn ends the harness writes a git bundle of
  exactly that branch into the run folder. The HOST — which holds the token — verifies
  the bundle lists one ref, lands it in its mirror, pushes, and opens or reuses the PR.
  Why: D6/D12 — the PAT never enters a sandbox; a lying container can at most produce a
  bundle the host rejects.
- **The PR is the payload; the approvals row is the gate.** Nothing advances off GitHub
  state. A human approves `code_complete` in Mission Control with the PR link, the
  commit list and the coding report in front of them. Merge stays a human act after
  stages 4–6, as PIPELINE.md always said.
- **Presence AND validity, again.** A coding stage with no commits fails; a handoff
  without a verifiable bundle fails; uncommitted leftovers are auto-committed but
  flagged, so a reviewer sees the agent stopped early. Proof:
  `tools/azure-runner/test_coding_stage.py` (real git, no database).
- **Deferred, stated plainly:** C2.0 (restricted sandbox DB role) and C2.5 (egress
  allowlist) are still open — auto mode is for trusted repos until they land; the
  sandbox image carries Python 3.12 + Node 22 + git only, so other toolchains need an
  image change; human-stage token capture is unchanged (unmetered).

## D15 — 2026-09-07 — Codebase connection: a run points at a host-local repo, a base branch, and optionally a branch to continue on

Before this, a run's product target was CLI-only (`pipeline.py run --product-repo`,
`set-product`) and Mission Control showed it read-only. There was no way to see what
repositories a machine actually had, and no way to work on a branch that already
existed — `coding_branch(run_id)` always derived a fresh `feat/<date>-<slug>`. An agent
starting a stage learned an origin, a base branch and one `git log -1` line, then spent
a turn discovering the codebase's own conventions.

- **Discovery is host-relative and root-confined.** The picker lists git repos on the
  filesystem of whichever machine serves Mission Control — the box, a workstation, a
  laptop — because "the repo I am working on" is a property of where the developer is,
  not of where the fleet happens to run. `LANTERN_WORKSPACE_ROOTS` is the entire
  boundary; unset means the picker offers **nothing**, falling back only to `~/work`
  when it exists. Why it matters: a repo picker on a web UI is a filesystem-read
  primitive — whatever path it admits gets cloned by the host, mounted into sandboxes,
  read through `read_file('product/…')` and pasted into a system prompt. `contains()`
  is the single admission point and resolves both sides before comparing, so a symlink
  out of a root is not a bypass. Proof: `tools/mission-control/test_workspace.py`,
  `test_repo_routes.py`.
- **`product_branch` stays the BASE; `product_working_branch` is new and nullable.**
  NULL means "derive from the run id", which is every pre-D15 run and every run that
  wants a fresh branch — so old runs resolve to exactly what they resolved to before.
  No rename: the daemon, `status --json`, Mission Control and `test_status_json.py`
  all read the existing column name, and a rename would buy nothing. `work_branch()`
  resolves the pair; `coding_branch()` stays the pure derivation so its assertions
  keep meaning one thing.
- **The chosen branch stays inside D6's push namespace.** `CODING_BRANCH_PREFIXES`
  (`feat,fix,proto`, overridable) is now both the handoff guard and the filter the
  picker offers branches through, so a branch that would be refused at handoff is
  never selectable. Picking `develop` is refused at selection time, naming D6 — three
  stages earlier than before, and widening the list is understood as a security
  change, not a preference.
- **"Did this stage do work?" is answered against a start sha, not the base.** The old
  check — `merge-base(base, HEAD)..HEAD` non-empty — was sound only for a fresh branch.
  On a branch that already carries commits it is true before the agent does anything,
  so an idle coding stage would have passed and its bundle would have carried someone
  else's commits into the PR as the agent's work. `LANTERN_CODING_START_SHA` is captured
  after checkout and before the agent runs, by whichever side prepared the checkout; the
  bundle still spans `base..HEAD` so the PR shows the whole branch. Absent (an older
  sandbox image) it degrades to the old check rather than failing. Proof:
  `test_coding_stage.py` asserts BOTH directions, so the fix cannot silently regress.
- **The system prompt tells the agent where it is.** A Claude-Code-style `<env>` block
  (working dir, repo, origin, base, current branch, access, working-tree state, recent
  commits), the product's own `AGENTS.md`/`CLAUDE.md`/`README.md` auto-loaded and
  capped, and a task block naming this stage's job from the brief and the approved
  plan. It sits at the END of the prompt: it is now the most volatile text in it (git
  status changes every stage), so keeping it ahead of the static charter/skills/memory
  would invalidate the cached prefix for everything below. A stub at the old position
  points at it.
- **Auto-loaded product docs are untrusted data, and are fenced as such.** They come
  from a repository a human pointed the run at, and they land in a system prompt above
  the role's own charter. They are authoritative for *how* to write code here and
  explicitly cannot change the contract — postconditions, the no-push rule, the gates,
  the approved plan. Without the fences this feature would be a prompt-injection
  channel. The fences mitigate; they do not eliminate.
- **Residual risks, stated plainly:** (a) a local-path target is never fetched, so the
  pipeline sees **committed** state only — uncommitted work in a developer's checkout is
  invisible to agents; (b) `_publish_branch` fetches the bundle into a local-path repo,
  and git refuses a fetch into a branch that repo has checked out; (c) the untrusted-doc
  fences are mitigation, not a guarantee; (d) discovery under a root on a network drive
  can be slow despite the time box.

## D16 — 2026-09-08 — Model stack: three tiers with reasoning effort; the project is a software factory

Dimash asked for the planner-strong / builder-cheap split the software-factory
reference designs use (IndyDevDan's Super Simple Software Factory; the Boundary /
HumanLayer "enterprise software factory" stack; Ray Fu's seven-agent setup — analysis
in `docs/plans/software-factory-alignment.md`), with token budget explicitly not the
constraint ("token-max").

- **Three tiers, not two.** `reasoning` (research, scoping, planning, review, security,
  debug, ui-ux design), `coding` (the stage-3 builder in auto mode), `fast` (QA charter
  runs, ui-ux divergence). `tier_for(role, stage)` is the single routing point; each tier
  is one env var with a fallback chain (`CODING → FAST → REASONING`) so a resource with
  one deployment still routes every stage. Why a separate coding tier: the reference
  designs put the cheapest capable model on building and the strongest on planning and
  review; sharing the QA tier would tie two unrelated cost decisions together.
- **Reasoning effort is configuration, per tier.** `LANTERN_EFFORT_<TIER>` becomes the
  Agent's `ModelSettings(reasoning=Reasoning(effort=…))`; defaults high/high/medium.
  Before this every stage ran at the deployment default. `LANTERN_EFFORT_CHAT` can lower
  it for interactive consults, where latency matters more than depth.
- **Fact that bounds this decision:** on 2026-09-08 `lantern-prod-agent` has exactly one
  deployment, `gpt-5.6-sol`; `gpt-5.6-terra`, `gpt-5.6-luna` and any "flash" name return
  `DeploymentNotFound`. The intended mapping (terra = reasoning, luna = coding/fast) is
  documented in `tools/azure-runner/README.md` and takes effect the moment the
  deployments exist. A cheap coding tier is only safe after the deterministic build gates
  (plan Phase B) — until then the coding tier stays on the strong deployment.
- **Positioning, not a rename of identifiers.** The repo, README and AGENTS.md now
  present the system as a *software factory* with Lantern as the codename. Env vars,
  tables, the bot identity and CLI names stay `lantern` — renaming ~100 identifiers buys
  nothing and would break the box, SSM parameters and every run folder in flight.
  Renaming the GitHub repository is a human, one-click action recorded here if taken.
- **Not changed:** the fixed pipeline shape, the gates, D7 (Azure OpenAI only). The new
  roles and phases the reference designs suggest are proposed in the plan, not adopted
  by this decision.

## D17 — 2026-09-08 — Software-factory logic: story stage, typed envelopes, quality gate as code, validation, rework

Dimash's ask after the three software-factory sources (`docs/plans/software-factory-
alignment.md`): build the architecture the reference designs share, assuming the strong
deployment (Terra) lands later. What shipped, and the shape chosen:

- **A stage 0 with two executions, not a new role bolted onto planning.** `00-story.scout`
  (`researcher`, read-only: patterns, similar features, risks, likely files — every cited
  path verified to exist) then `00-story.write` (`story`: user story + numbered acceptance
  criteria + edge cases + non-goals) behind a new human gate, `story_signoff`. Ray Fu's
  agents 1 and 2. Why a gate here: the criteria are what every later stage is checked
  against; approving them is the cheapest correction point in the whole run.
- **Typed envelopes beside the markdown, validated by code.** `research.json`,
  `story.json`, `plan.json`, `validation.json` (`tools/azure-runner/factory.py`,
  `ENVELOPES`). Presence AND validity, cross-checked: every plan task maps to criteria
  and every criterion is planned or deferred with a reason; every validation verdict
  names evidence and appears exactly once; the verdict is computed from the statuses,
  never chosen. Same lesson as the 2026-08-26 fabrication saga, applied to requirements.
- **The coding gate runs as code (IndyDevDan's "agents plus code").** After the coding
  agent's turn the product's `lantern.toml [quality]` commands and a write-scope check
  (the plan's `write_scope` globs — Ray Fu's folder-confined engineers) run in the
  checkout; only failures go back to the agent, at most `LANTERN_FIX_ROUNDS` (3) times;
  a red gate fails the stage and the handoff refuses out-of-scope commits. `gate.json`
  carries the execution key so a stale green gate cannot pass a later attempt. The same
  helper (`factory.coding_turns`) serves the container and the in-process path. This is
  the prerequisite the D16 note named before a cheap coding tier is safe.
- **Validation as a second execution of stage 5.** `05-post-coding.validate`
  (`validator`) gives every criterion a verdict with evidence after the review and before
  security; `fail` stops the run with a `fix_now` list. Chosen over a new stage so no
  existing run's `current_stage` key changes and the run-folder layout stays intact.
- **Loops as a primitive.** `pipeline.py rework <run> --to 02-pre-coding|03-coding|04-qa-dev`
  sends a failed or waiting run backwards (pending approvals expire, the decision lands
  in `gate-decisions.md`). Before this the only loop was "fail, fix by hand, retry the
  same stage". Boundary's "max iterations then a human" is the fix loop + rework.
- **Second executions append to a shared `report.md`** and the LAST `Status:` line
  counts (`report_blocker`). The alternative — per-execution report files — would have
  changed the postcondition, Mission Control and every template for one convention.
- **Not done, on purpose:** parallel back-end/front-end builders (plan Phase D — write
  scope is the mechanism they will reuse), the review-bot loop and merge babysitter
  (Phase E), the feedback trust pipeline and factory evals (Phase F), agentic access to
  start runs from chat (Phase G). `PIPELINE_VERSION` is now `3`.
- **Proof (live, 2026-09-08, in-process on `gpt-5.6-sol`, product = this repo by local
  path):** run `feat-20260908-status-facts`. `00-story.scout` passed in 280 s (1.09 M
  input tokens, 88 % cached; every cited path verified). `00-story.write` attempt 1 ended
  `BLOCKED` with one question — the brief promised a v2/v3 distinction the inspected
  checkout could not deliver — and the harness failed the stage from the LAST status
  line of the appended report section, opened no gate, and still recorded both roles'
  memory. The answer was written into the run's brief; `retry` → attempt 2 passed in
  108 s with a four-criterion story mapped 1:1 to the brief's must-haves, and
  `story_signoff` opened. A parser bug surfaced on the way (a blank `Working branch:`
  line swallowed the next line) and is fixed with `test_brief_parsing.py`.

## D18 — 2026-09-08 — Parallel scoped builders: stage 3 fans out, the host merges, one gate

Gap 1 of the software-factory alignment plan (Ray Fu's folder-confined back-end and
front-end engineers, plan Phase D) was the last structural difference between Lantern
and the reference designs: D17 built the *mechanism* — a write scope enforced on every
commit — but stage 3 still ran one agent with the whole checkout. This adds the second
sandbox, and nothing else.

- **The plan declares the split, and code checks it is a partition.** `plan.json` gains
  an optional `builders: [{name, write_scope, tasks, criteria}]`. `factory._check_plan`
  refuses names that are not branch-safe, a duplicate name, `integrate` (reserved for
  the host's own execution), a task assigned twice, a task assigned to nobody, a task id
  the plan does not define, and a glob claimed by two builders. Why validate this hard:
  a bad split does not fail at planning time, it fails forty minutes later as a merge
  conflict, and the human sees a coding failure for a planning defect.
- **Optional, and provably inert when absent.** No `builders` key → `builders.run_coding`
  is `await execute(conn, run_id, stage, runner)` and every other function short-circuits
  on the same emptiness. `test_builders.py` asserts the pass-through and the existing
  `test_coding_stage.py` / `test_factory.py` run unchanged, because "byte-for-byte
  today's single builder" is a claim that has to be checked, not asserted.
- **One start point, N branches, `--no-ff` in plan order.** The host creates every
  builder's branch at one commit (the run's branch if it exists — a continued branch,
  D15 — else the base), so each builder's `base..HEAD` is exactly its own work and the
  merge is a clean fan-in. Branches are `<run branch>--<name>`, which stays inside D6's
  pushable namespace because the run's branch already does. `--no-ff` keeps each
  builder's work one readable arc for the reviewer.
- **The host merges; agents never see each other's branches.** A builder cannot fetch,
  read or wait for a sibling — its checkout does not contain them and never will. The
  only thing that crosses is the bundle it writes into the run folder, verified by the
  host before it lands in the mirror, exactly as D14 designed for one builder. That is
  also why the plan must carry the contract between them: with no shared branch, an
  interface not written down is an interface that does not exist.
- **A merge conflict is a planning failure, and is reported as one.** The stage fails
  with the conflicting file list and points at `pipeline.py rework <run-id> --to
  02-pre-coding`. We deliberately did NOT hand conflicts to a model to resolve: two
  builders editing one file means the split was wrong, and a resolved conflict hides
  that. Note the plan check compares glob *strings* — `src/**` and `src/api/**` pass it
  and collide here — so the merge is the second line of defence, not a redundant one.
- **An integrator, because "green apart" is not "green together".** One final execution
  (`03-coding.integrate`, role `coding`) runs on the merged branch with the union of the
  builders' scopes and one task: make it green, through the normal `factory.coding_turns`
  gate loop. Its handoff is the stage's handoff, so `03-coding/` still carries exactly
  one branch and `_publish_branch`, the PR, and the single `code_complete` gate are
  untouched. Its "did this execution do work?" check measures from the PRE-merge start
  point recorded by the merge: an integrator that finds nothing to fix is a success, not
  an idle stage, but a merge that produced nothing still fails.
- **Per-builder run-folder subtrees, for a race, not for tidiness.** `03-coding/builders/
  <name>/` holds each builder's report, gate, handoff and bundle. Sharing one `report.md`
  would race on the last `Status:` line (`report_blocker`) and sharing one `gate.json`
  would race on `execution_key` — the loser failing on the winner's evidence. The
  invariant that second executions append to a shared report still holds for the stage
  dir, where only the integrator writes.
- **The stage key is the identity; the env var is only for the turn.** `LANTERN_BUILDER`
  tells the agent's own execution which builder it is (the write scope and the prompt
  read it), but every *check* derives the builder from the stage key `03-coding.<name>`
  via `factory.builder_of`. The first live run proved why: the in-process executor clears
  the writability env in its `finally`, and the docker host never sets it at all, so
  postconditions that read the environment looked in the stage directory and failed a
  builder that had done everything right — green gate, clean handoff, wrong place to
  look. `test_builders.py` pins the env-free path.
- **Parallelism is capped by the executor, and is 1 in-process on purpose.**
  `LANTERN_BUILDER_PARALLELISM` (default 2) never exceeds `LANTERN_MAX_CONCURRENCY`, and
  is forced to 1 unless `LANTERN_EXECUTOR=docker`: the in-process path configures each
  execution through `os.environ` (product dir, branch, `LANTERN_BUILDER`), which two
  concurrent executions in one process would overwrite for each other. Real parallelism
  is a property of the container executor; a laptop runs the same builders sequentially
  and gets the same branch.
- **One more thing the host verifies before pushing:** every builder head must be an
  ancestor of the handed-off head. A merge that silently dropped a builder would
  otherwise arrive at the PR looking like a complete feature with a third missing.
- **Shared-file surface, kept small:** a new `role_for_stage()` in `orchestrator.py` maps
  any `03-coding.<x>` to the `coding` role (the builder names come from `plan.json` at run
  time, so they cannot be listed in `ROLE_FOR_STAGE`), and the three role lookups route
  through it; the two executors key the coding-stage setup on that role instead of the
  literal stage string and resolve the builder's branch and `LANTERN_BUILDER` through
  `builders.branch_for`/`name_for`; `step_run`'s single `execute` call becomes
  `builders.run_coding(...)`. Everything else is in `builders.py` and `factory.py`.
- **Not done, on purpose:** no automatic splitting — a human-approved plan decides, and
  `agents/pre-coding/skills.md` §5a says when not to (one surface, sequential tasks, a
  shared file, a small feature); no cross-builder communication; no per-builder PRs (one
  branch, one PR, one gate — D14 unchanged); no rebase or conflict resolution; builders
  are not offered to `human` coding mode.
- **Proof (live, 2026-09-08, in-process on `gpt-5.6-sol`):** run `feat-20260908-note-delete`
  against a small product repo, plan split into `api` (`src/**`, `tests/**`, tasks 1–2)
  and `docs` (`docs/**`, task 3). Stage 3 fanned out one at a time (in-process cap),
  both builders' gates went green, the host merged both branches `--no-ff` in plan
  order, the integrator ran on the merged branch and added one cleanup commit, the
  branch published and `code_complete` opened with both builders in its payload. The
  merged branch's own tests pass (2 → 4). Neither builder touched the other's files, and
  the run folder carries `03-coding/builders/{api,docs}/` with a report, gate, handoff
  and bundle each, `builders.json` + `builders.md` for the merge, and the integrator's
  single handoff at `03-coding/`. Three defects surfaced on the way and are fixed with
  tests: the env-vs-stage-key one above; an ancestry check that asked the mirror about a
  commit the mirror does not receive until `_publish_branch` lands the bundle a moment
  later (it now checks only where both commits exist — "I cannot see that commit" is not
  "that commit is wrong"); and a pre-existing `product_checkout` bug where
  `shutil.rmtree(..., ignore_errors=True)` silently failed on read-only git objects, so
  the SECOND execution of a run in one process died with "destination path already
  exists". That last one was latent for any two stages of one run under a single daemon
  tick on Windows; builders just reach it first.
- **Proof (unit):** `test_builders.py` — 36 tests on real git with no database and no model:
  the partition rules, branch naming inside the D6 namespace, two builders' bundles
  merged into one run branch with both heads as ancestors, an add/add conflict failing
  with the file list, `LANTERN_BUILDER` scope resolution (including the integrator's
  union and the fallback), per-builder handoff directories, the host holding a builder to
  ITS scope with no env of its own, batches never exceeding the cap, and the
  no-builders pass-through.

## D21 — 2026-09-08 — Agentic access: the factory is operated from chat and Slack, behind a typed confirmation

The two reference designs agree on the surface Lantern lacked: IndyDevDan's factory is
*operated by an agent* and installs itself into a codebase (B 6:41, 24:53), and
Boundary's dispatcher listens in Slack so the human's part of the loop happens where the
human already is (C). Lantern could see everything and do nothing: the `lantern` chat
knew which gate had been waiting eleven hours and could only answer "run this command
somewhere else". This closes that, without moving the gate line.

- **The orchestrator gets five write tools; specialists get none.** `start_run`,
  `set_product`, `rework`, `retry`, `decide_gate` on the `lantern` agent only. D11's
  read-only rule was never about the *surface* — it was about work sneaking past
  verification. A gate decided in chat still writes the same `approvals` row, still
  renders `gate-decisions.md`, still advances the same state machine. What would break
  the rule is an agent deciding something, and that is what the confirmation prevents.
- **The server verifies the confirmation, in the human's own most recent message.** The
  tool renders a decision card and returns without acting; the human types
  `confirm approve story_signoff on feat-20260908-status-facts`; the next call is checked
  against the text of the turn being served. The mechanism is a closure —
  `run_chat_turn` builds the tools over that turn's `user_text` — so the model has no
  path to the argument `confirmed()` reads. It cannot confirm itself by printing the
  phrase, cannot claim the human said it, and cannot spend an old turn's confirmation:
  the tools are rebuilt every turn. A missing confirmation returns guidance, never an
  action. Why a typed phrase rather than a button: the phrase names the verb AND the
  subject, so it authorises exactly one act on exactly one run, and it survives being
  relayed through any surface that can carry text — which is what made the same
  protocol work unchanged when the Slack bridge arrived.
- **`retry` and `set_product` act on the first call.** They are stage-local and
  reversible. Putting a confirmation on everything is how confirmations stop being read.
- **Reuse, not reimplementation.** `PipelineExecutor` calls `pipeline.py`'s own `cmd_*`
  coroutines and turns their CLI manners (print, `sys.exit("why")`) into a result dict.
  A second copy of the gate logic in the chat layer is exactly how two surfaces start
  disagreeing about what an approval is. It also means a refusal *reads* like the CLI's.
- **Identity is the point of the audit log.** Every action is recorded as the signed-in
  human — `human:dimash` from the web, `human:slack:U…` from Slack, `channel` on the
  event — and never as the agent. The chat and the bridge are surfaces for a person's
  decision; an event that named the agent would make the log useless for the only
  question anyone asks of it.
- **Slack is a bridge, not a gateway.** ~600 lines of Bolt in Socket Mode with its own
  systemd unit, reading the same Postgres: `@lantern <idea>` opens a run and the thread
  that follows it (`runs.slack_thread_ts`), gates post there with Approve/Reject, clicks
  ack inside Slack's 3 s and then write through `cmd_decide`. Two fail-closed allowlists
  (approvers decide gates, operators start and loop runs; unset means nobody), channel
  scoping, and `staging_deploy` / `prod_signoff` refused server-side — a Slack session is
  easier to take over than the Tailscale-only web app, and those two gates put code in
  front of users. The alternative considered and rejected in the symphony plan §3 stays
  rejected: routing approvals through OpenClaw or Hermes would share a blast radius with
  tools holding our PAT.
- **`pipeline.py init-product <path>`** installs the factory into a product repo: detect
  the stack from the files that exist, write `lantern.toml` with real commands, append a
  marked block to the repo's `AGENTS.md`, print how to point a run at it. Two refusals
  are the design: an existing `lantern.toml` is kept unless `--force` (it is the team's
  gate, possibly tuned), and existing `AGENTS.md` text is appended to, never rewritten.
  A repo with no recognised stack gets a `lantern.toml` whose test command fails loudly
  rather than a green gate that proves nothing.
- **The brief composer** turns a rough idea into `workflow/briefs/<slug>.md` from the
  template and validates it with `parse_brief_product` / `parse_brief_coding_mode` — the
  same parsers `pipeline.py run` uses, so a brief that composes is a brief that runs.
  Missing repo or coding mode is a question put to the human, never a default. A brief
  written by hand is never overwritten.
- **Not done, on purpose:** `@lantern ask <role>` (consult mode inside a Slack thread) —
  a consult reads the whole repo including unreleased security findings, and reading a
  long agent answer in a thread is worth little against that; the Chat tab is where
  consults belong. No gate is decidable by an agent under any flag. The Slack bridge is
  dormant until a workspace app exists (a human, one-time action; the manifest is in
  `tools/slack-bridge/README.md`), and nothing else depends on it.
- **Proof (unit):** `test_chat_tools.py` (31 checks — the confirmation matrix, identity on
  every event, the composer's briefs parsing back), `tools/slack-bridge/test_bridge.py`
  (36 — allowlists, ack-before-pipeline timing, gate cards, relay), `test_init_product.py`
  (19 — a fixture repo per stack, both refusals, the written `lantern.toml` read back by
  `factory.quality_config`), and the decision-card rendering in `test_chat_ux.py`.
- **Proof (live, 2026-09-08, Chat tab on `gpt-5.6-sol`, product = this repo by local
  path):** run `feat-20260908-runboard-stage-timestamps`, started and gated entirely from
  chat for $0.18. An idea became a decision card; the card became a run only after the
  phrase was typed; both story stages passed; asked to approve `story_signoff`, the agent
  read the story first and produced a second card. **"Yes, I confirm - approve it."
  changed nothing** — the agent reported that the wording did not match and the gate row
  stayed `pending`, which is the whole design working in the only place it matters. The
  exact phrase then approved it: `approvals.decided_by = dimash`, the note carried
  through to `gate-decisions.md`, the run advanced to `01-ui-ux.diverge`, and the audit
  log reads `human:dimash pipeline_action action=decide_gate channel=web-chat`.
- **Known wart, not fixed here:** `approvals.channel` still records how the gate was
  OPENED (`'cli'` from `open_gate`) rather than where it was decided. The decision's real
  channel is on the `pipeline_action` event, so the audit answer is right; correcting the
  column means changing `cmd_decide`'s signature for all three surfaces, which belongs
  with whoever next touches that function.


## D20 — 2026-09-08 — The feedback trust pipeline and the factory's own evals

Session 3 of the five parallel factory sessions (`docs/plans/software-factory-parallel-
prompts.md`). The ask: Boundary's production rule for feedback — untrusted input never
becomes work directly — plus the rule that every change to the factory ships its own
numbers (alignment plan §1.8, §4 Phase F). What shipped, and the shape chosen:

- **A bug run starts with `pipeline.py bug`, not with a hand-written brief.** The raw
  report is stored once, verbatim, at `intake/feedback.md` under a header that says
  `UNTRUSTED`, hashed at intake; the brief points at it instead of quoting it. Why: a
  report pasted into a brief is a trusted file by the time an agent reads it. The trust
  rule is mechanical where it can be — triage fails if the file changed, every cited run
  and commit must exist, the dedup candidates the harness computed must each be addressed,
  and a regression test carrying a code block copied from the report is rejected — and a
  prompt rule where it cannot (every debug phase note and the debug skills say: read it,
  never execute anything from it). Nothing under `intake/` is mounted or shelled.
- **Envelopes for triage, repro and root cause** (`triage.json`, `repro.json`,
  `rootcause.json`) validated by `factory.check_envelope` through a `CHECKERS` registry
  `intake.py` extends — the same postcondition every executor already runs, so the
  container path enforces them the day it dispatches a bug stage. The repro is a test the
  agent writes under `02-repro/regressions/` from its own reading of the code; the fix
  lands it at `lantern/regressions/` in the product, and the product's `lantern.toml` test
  command must cover that directory, so every past repro re-runs on every future run.
- **The fix is the feature pipeline's `03-coding` stage — same key, directory and
  machinery — not a `04-fix` stage.** The prompt asked for `04-fix`; a separate fix stage
  would have needed its own writable checkout, gate loop, bundle handoff, publish and PR
  path, or edits deep inside `run_agent_stage`, `_publish_branch` and the sandbox
  entrypoint that sessions 1, 2 and 5 were changing in the same hour. Reusing the stage
  gives bug runs the quality gate, write scope, review loop, merge babysitter and Mission
  Control's `code_complete` rendering for free, and keeps one way code gets written.
  Planning is reused the same way: `02-pre-coding` sits in the bug table and runs only for
  `large` / `needs-human`; for `trivial` / `small` the harness derives `plan.json` +
  `task-plan.md` from the root cause's `fix_plan` (task 1 is always the regression test)
  and the run skips the planner. The directory numbers in a bug folder are therefore
  01, 02, 03, (02), 03, 05, 06 — a cost accepted for the reuse.
- **Classification is enforced by the diff.** After the branch is published, insertions +
  deletions above `LANTERN_SMALL_FIX_MAX_LINES` (60) for a `trivial`/`small` bug write a
  `reclassified` record into `triage.json` and send the run back to planning with exactly
  the transition `pipeline.py rework --to 02-pre-coding` makes (approvals expire, the
  decision in `gate-decisions.md`), the branch keeping the work. The agent's original call
  stays on record — that is what the classification eval scores.
- **Gates open from the envelope, not from the table.** `triage_signoff` only when the
  bug is already fixed, a duplicate, or `needs-human`; `repro_signoff` only when not
  reproduced; otherwise the run advances by itself — Boundary's 95 % automatic. The
  shepherd (`runs.shepherd`, `--shepherd` or `LANTERN_DEFAULT_SHEPHERD`) is pinged once,
  at fix-ready, through the existing `_post_alarm` webhook path with the repro, the diff
  summary and the PR or branch link; `code_complete` opens with the same facts.
- **Dispatch for bug runs did not exist** — `step_run`, `advance` and the claim query
  only knew `FEATURE_STAGES`. It is added as five small hooks in `pipeline.py` (import,
  stage-map registration, a table-aware row lookup, a bug-run branch in `step_run` and
  `advance`, a lifecycle-aware ordering in `rework`), one line in
  `orchestrator.check_stage_inputs`, and five phase notes; everything else lives in
  `intake.py`. `runs.shepherd` is the one schema addition (`init-db` once).
- **The factory measures itself.** `tools/evals/`: `evals build` freezes every run folder
  into jsonl; four stdlib scorers — plan coverage, validator ↔ QA agreement,
  classification accuracy against diff size, repro rate; `evals run --suite … --live`
  replays a role on the real model against the same inputs (opt-in, injectable, tested
  with a fake); `evals report` writes `REPORT.md` with a fingerprint of the watched files.
  The rule from the sources runs in this repo's lint gate: `check_pr.py` fails a diff that
  touches `agents/**`, `factory.py`, `intake.py`, the scorers, or the orchestrator's prompt
  builders / gate functions **by name** unless `REPORT.md` changed with it and its
  fingerprint matches — an edited-but-not-regenerated report does not pass. Today the
  report is mostly `n/a` (one story, no plan envelope, no bug run yet); the point is the
  delta from here on.
- **Dedup is deliberately crude:** stemmed token overlap (weighted for error codes) over
  past intake reports, story titles and brief titles, threshold 0.45, one candidate list
  per run. It finds a reworded duplicate and not a different bug in the same feature area
  (`test_intake.py`); it is an input to triage, never a verdict.
- **Not done, stated plainly:** the container executor has not run a bug stage yet (the
  hooks are executor-agnostic, but only the in-process path was exercised); the repro
  stage cannot execute the test it writes (no shell outside auto coding — the coding
  stage proves fail-then-pass); Mission Control renders bug runs with its feature-stage
  board (session 5 owns that); a conditional `security` spot-check for sev-1 / auth /
  payment fixes is a rule in the lifecycle doc, not code; the live eval replay was not run
  against Azure (frozen scoring is tested; the live path with a fake); and Slack intake
  (`--source slack`) is the same function session 4's bridge will call.
- **Proof (live, 2026-09-08, in-process on `gpt-5.6-sol`, product = this repo by local
  path at commit 0c21060):** `pipeline.py bug` on a real defect — `pipeline.py bug --help`
  crashes with `KeyError: 'AZURE_OPENAI_ENDPOINT'` in a checkout without `.env`, because
  `main()` builds the Azure client before argparse runs — created
  `bug-20260908-help-crash-without-env` (no dedup candidates: nothing similar exists) and
  one `step_run` executed `01-triage`: 170 s, 1.08 M input tokens (90 % cached), 8.6 k
  output. `triage.json` validated on the first attempt — sev-3, `small`, not already fixed
  (the agent cited the base sha and the 2026-08-25 commit that introduced the ordering,
  and noted that `repos`/`evals` bypass it), a four-step repro plan the next stage can turn
  into a subprocess test — and `triage.md` states in its second line that nothing from the
  report was executed. Code then advanced the run to `02-repro` without a gate, and the
  memory row landed. The defect itself is left for the lifecycle to fix.
## D19 — 2026-09-08 — Review loop before the human, merge babysitter after: Boundary's rule for a pull request

Session 2 of the five parallel factory sessions (`docs/plans/software-factory-parallel-
prompts.md`), closing alignment-plan Phase E. The rule from the source: "do not notify a
human until the review bot is happy, at most three rounds, then a human", and after the
human approves, "keep the branch mergeable until a human merges". Humans still merge;
agents never do. What was built and the shapes chosen:

- **A `reviewer` role and a typed `review.json`, validated like every other envelope.**
  `03-coding.review` runs the new role on the read-only checkout (already on the run's
  branch, D15) against `story.json`, `plan.json`, the handoff's exact commit range,
  `gate.md` and the coding report; it writes `03-coding/review/round-<n>.md` +
  `review.json` and appends its section to the shared `report.md` (the D17 convention).
  `factory._check_review` computes the verdict from the severities — `approve` ⇔ no
  blocker/major — and requires `must_fix` ⊆ findings and ⊇ every blocker/major. The
  second rule is not in the source; it is what makes the loop converge: a blocker the
  reviewer does not put on the fix list would never be fixed and would eat every round.
  Style is a finding only where it hides a bug; security smells are flagged `major` for
  the `security` role, never decided.
- **The loop runs as code in `review.py`, after publish, bounded by `LANTERN_REVIEW_ROUNDS`
  (2).** A round is one review; `request_changes` runs a fix execution `03-coding.fix` —
  the `coding` role, writable, on the same branch, its task block the `must_fix` list —
  then publishes again (same branch, same PR) and reviews again. The LAST review is never
  followed by an unreviewed fix, so what the human sees is a review of the code that is
  actually on the branch. Approve, the cap, or a failing execution all end the loop and
  the `code_complete` gate opens with `review: {verdict, rounds[], capped, last}` in its
  payload (Mission Control, session 5, renders it). A failed review or fix execution does
  NOT fail the stage: the branch is already published and valid, the failure is on record,
  and re-running a whole coding stage over a broken review would be the wrong loop. Why
  the state travels through `03-coding/review/state.json` rather than env vars: the
  sandbox's prompt builder reads the mounted run dir, so the round number and the fix
  list reach the container the same way every other handoff does (D4).
- **One PR review per round, always a `COMMENT` event.** A bot `APPROVE` could satisfy a
  "one approving review" branch rule and a bot `REQUEST_CHANGES` would have to be dismissed
  by hand after a human overrules it at `code_complete`; the verdict is advisory, so it
  goes in the text. Inline comments where the line is in the diff; a 422 falls back to
  body-only; no token or a non-GitHub remote means the run folder is the only record —
  never a failure (the D14 rule for PR-API refusals, applied again).
- **The merge babysitter is code with one agent turn in reserve.** `pipeline.py babysit`
  and the ec2 daemon's tick (`LANTERN_BABYSIT_MINUTES`, 30) take every auto run past an
  approved `code_complete` whose branch is not merged: a trial merge of the base in a temp
  clone of the host mirror; a conflict writes `03-coding/merge-conflict.md`, logs
  `merge_conflict`, alarms, and waits for the base to move (`--force` retries); a clean
  merge is committed with the bot identity and a `Lantern-Agent: babysitter` trailer,
  pushed, and then the product's quality commands re-run as CODE — `03-coding.regate`, a
  `stage_executions` row without a model (inside the sandbox image under the docker
  executor, in the temp clone otherwise) — and only a red result spends a fix execution.
  Why not an agent execution for the regate: the coding handoff's "did this execution do
  work" rule (D15) fails an execution that commits nothing, and the coding gate's
  write-scope check diffs from the execution's start, which after a merge includes
  everything the base brought in. Both are right for coding and wrong for a regate, so
  the regate does not go through them. GitHub's PR `merged` flag (squash merges leave no
  ancestry) or git ancestry for other remotes records `branch_merged` and ends it.
- **What it deliberately does not do.** It never merges into the base and never resolves
  a conflict; a bot `APPROVE` is never posted; human-mode runs are not babysat (the branch
  is a developer's); a failed fix after a red regate leaves the merge commit on the branch
  — the PR then shows the truth — and alarms rather than reverting. The regate outside
  the docker executor runs the product's commands on the host, the same containment
  D14 already accepts for trusted repos until the egress allowlist lands.
- **One pre-existing bug, found by the first live review round and fixed at its site.**
  `pipeline.product_checkout` re-clones a run's checkout per stage and cleaned the old one
  with `shutil.rmtree(..., ignore_errors=True)`. git writes objects mode 0444, and on
  Windows a read-only file cannot be unlinked, so the tree survived and the next clone died
  with "already exists and is not an empty directory". It had never fired because the
  coding stage was the last in-process stage of a run to touch the checkout; the review
  execution runs right after it. The fix is `review.force_rmtree` (chmod-and-retry, `onexc`
  on 3.12) called from that one line — stage 4+ of any auto run on an in-process runner was
  broken the same way. Regression: `test_review.py::CheckoutReuse`.
- **Shared-file hooks beyond the listed anchors, stated for the merge:** `STAGE_DIR` learns
  the three sub-stages; the two `stage == "03-coding"` writability conditions in
  `run_agent_stage` / `run_agent_stage_docker` also accept `review.WRITABLE_STAGES`
  (session 1's builders need the same widening — keep whichever condition covers both);
  `orchestrator.product_task_block` calls `review.task_block` for the review and fix
  stages; `cmd_daemon` starts the babysit slot. Proof: `test_review.py` (31 tests — the
  envelope, the loop with fakes, PR review bodies, the babysitter on real git).

## D22 — 2026-09-09 — Mission Control v3: the factory's face, and a trace to look at

The factory could run a feature end to end but could not be *watched*. The board
answered "where is my feature"; nothing answered "what did that execution actually
do", "what is this criterion's fate", "what is the factory made of", or "what did
today cost". The two reference bars (`docs/plans/software-factory-alignment.md` §1
rule 5, §2 row 10) are IndyDevDan's dashboard — sessions as swim lanes, compiled
prompts, per-phase cost, restart from here — and HumanLayer's workspace — one glance
= what runs, what needs me, what it cost; one click = act.

- **The artifact leads the gate card, not the report.** Every pending gate opens with
  the thing being decided: `story.md` for `story_signoff`, the option PNGs for
  `ux_signoff`, the plan summary plus `task-plan.md` for `plan_signoff`, the pull
  request plus `gate.md` plus review rounds plus builders for `code_complete`, the
  validation table before `staging_deploy`, the staging videos before `prod_signoff`.
  Before this a reviewer got a stage report and had to know which file to go read. The
  Inbox now sits *above* the board on Home, because "what needs me" outranks "what is
  running". Approve and Reject are one form, so the keyboard can submit it and nothing
  client-side can decide a gate.
- **A run is its executions, not its stages.** The run page is swim lanes keyed by
  *execution key* — `00-story.scout`, `03-coding.api`, `03-coding.review` — so the
  parallel builders of D18 and the review rounds of D19 appear as their own lanes the
  day those sessions land, with no change here. Each attempt is a bar carrying its
  duration, model tier, tokens and estimated cost from the ledger; gate diamonds sit
  between the lanes they gate. Bars are ordered, not scaled to a clock: two builders
  that truly overlapped appear in adjacent columns, and the exact times live in the
  tooltip and the drawer. A run whose current stage is outside the feature pipeline (a
  bug run on the debug lifecycle) shows only what it executed — painting the eight
  feature stages as its road ahead would have been a claim about work it will never do.
- **The execution drawer is the answer to "prove it".** Compiled system prompt,
  kickoff, the tool-call timeline (name, arguments, result size), the report, the typed
  envelope *with its validation result recomputed live*, `gate.md`, the memory rows
  keyed to that execution, the ledger — and the loop actions. Retry and rework-to are
  server-side POSTs onto `pipeline`'s own primitives with the web user as the actor;
  **approvals are never decided there**, which keeps D6's gate integrity in one place.
- **Traces are captured at the source, and redacted before they exist.**
  `factory.write_trace()` writes `<stage-dir>/trace/<execution-key>.json` from both
  executors (one two-line hook each, right after `result = results[-1]`). Two rules:
  it never raises — observability is not a postcondition — and it never carries a
  secret. The `# QA target` section (the environment's test login) is dropped whole,
  credential-shaped text is masked, and the values of secret-looking environment
  variables are scrubbed wherever they appear. **The over-redaction lesson:** the local
  database password is literally `lantern`, and blanket-masking it rewrote every
  `lantern.toml` path in a trace as `[redacted].toml` — fail-safe, and useless. A value
  that is a short all-lowercase word is now left to the keyword and URL patterns, which
  still catch it where it reads as a credential.
- **Traceability is matched by identifier, never by prose.** The matrix rows are the
  story's criteria; a plan task, a commit or a QA charter section counts for a
  criterion when it *names* the `AC-n` id or a task mapped to it. Text similarity would
  be a guess dressed as evidence — the same rule that makes a report a claim and a file
  the evidence. Commits and charter sections that trace to nothing are listed under the
  matrix rather than quietly dropped, and each row's verdict is computed from the
  stages that ran, never chosen.
- **The catalog reads files and environment, not a hand-written page.** Roles come from
  `agents/<role>/charter.md` and `tier_for()`, stages and gates from `FEATURE_STAGES`,
  the model stack from `LANTERN_MODEL_*`/`LANTERN_EFFORT_*` with the fallback chain
  resolved and the *intended* deployment named beside the resolved one, product gates
  from each `lantern.toml`, evals from `tools/evals/REPORT.md` when D20 writes one. It
  cannot drift from the factory because it is derived from it.
- **Light mode, a keyboard map, and a phone layout — because a gate is decided
  wherever the human is.** The light palette mirrors the design system's dark ladder
  with the gold ramp deepened for contrast; the choice follows the OS unless made
  explicitly, applied before first paint. `j/k` move, `a` approves, `r` rejects with a
  required note, `t` opens the matrix, `?` shows the map — every one of them also a
  link or a button, so the keyboard is a shortcut and never the only path.
- **Three defects the real data found, fixed here:** `/runs` crashed with `IndexError`
  the first time a bug run appeared (a stage name with no ` · ` in the display map);
  a gate rejection logged `gate_rejectd`, splitting web rejections from the CLI's
  `gate_rejected` in the audit log; and a handoff naming a PNG the run folder no longer
  holds rendered a broken image instead of saying so.
- **Not done, on purpose:** per-tool-call timings (the SDK's final result carries order
  and payloads, not per-call clocks — that needs a streamed run); SSE on the run page,
  so a live lane still needs the 30-second reload; inline video playback; and the debug
  lifecycle's own lane table, which waits for `pipeline.py bug` (D20) to define it.
- **Proof:** `tools/mission-control/test_lanes.py` (16), `test_drawer.py` (8, over a
  trace written by the real `write_trace`), `test_traceability.py` (8),
  `test_catalog.py` (8), `test_cost.py` (8), `test_routes_v3.py` (18, every route on an
  empty database and every write fail-closed), shared fixtures in `fakes.py`, and
  `tools/azure-runner/test_trace.py` (15, including "a QA password never reaches the
  trace"). Live proof on `gpt-5.6-sol`: run `feat-20260909-trace-proof` executed
  `00-story.scout` (33 tool calls) and `00-story.write` (25) in-process against a
  throwaway product repo; both wrote traces the drawer renders, neither contains any
  configured secret, and the run opened a real `story_signoff` gate. Screenshots of
  every page at 1440 and 390 px, light and dark, in
  `tools/mission-control/screenshots/v3-*.png`.

## D23 — 2026-09-10 — The stage loop survives its own bad rounds and the deployment's 429s

**Context.** An architecture audit (`docs/research/agentic-architecture-assessment.md`)
found the per-stage loop is the thinnest part of the system: one `Runner.run` per stage
with no retry, a flat 120-turn ceiling for twelve roles, and a fix loop that hands off
whatever the LAST round produced. Two of those are cheap to fix and one of them is the
best-evidenced failure mode in the agentic-coding literature.

**Decision.**

- **A red fix round costs a round, not the work.** `coding_turns` snapshots the worktree
  before each gate and, if the loop ends red on a tree that scores worse than one it
  already had, restores the better tree and re-gates it. `gate.json` records
  `restored_from_round` so the handoff, the execution drawer and a human all see which
  round shipped. Motivation is measured, not theoretical: across SWE-agent and OpenHands,
  60–69% of failures reach and edit the *correct* functions and then thrash them, in five
  cases producing a bit-identical gold patch mid-trajectory and destroying it
  (arXiv 2603.24631). Our fix loop has exactly that shape. aider buys the same protection
  by auto-committing every model turn; here the harness takes the snapshot instead, so the
  agent's branch, index and commit messages are untouched.
- **A checkpoint is a temporary-index commit, not `git stash create`.** `stash create`
  silently omits untracked files, which is most of what a builder produces between
  commits. `read-tree HEAD` → `add -A` → `write-tree` → `commit-tree` under
  `GIT_INDEX_FILE` captures the same state including new files, respects `.gitignore`,
  and touches neither the real index nor the worktree nor HEAD. Checkpoints are kept
  under `refs/lantern/<execution>/round-<n>` so a discarded round stays readable.
- **A 429 is transport, not content.** `factory.with_retry` retries transport-shaped
  failures with capped exponential backoff and jitter (`LANTERN_MODEL_RETRIES`, default
  3), wired into both executors' `run_turn`. `classify_error` splits retryable from
  terminal by exception class NAME — never by import, so factory.py keeps its no-SDK rule
  — with a status code outranking the name when the exception carries one.
  `MaxTurnsExceeded` and guardrail tripwires stay terminal: they are results about the
  work, and retrying buys the same answer twice. This matters most under D18, where N
  builders hit one Azure deployment on the same startup credits, so throttling is the
  expected case; before this, one 429 failed the run and a human had to re-run the whole
  stage and pay for every turn again.
- **Turn ceilings are per role.** `LANTERN_MAX_TURNS_<ROLE>` then `LANTERN_MAX_TURNS`,
  falling back to 400 for `coding` (the D14 `LANTERN_CODING_MAX_TURNS` name still works)
  and 120 for everything else. 120 was one number for twelve roles with no relation to
  observed behaviour — traces show a review-shaped stage finishing in ~9–11 model
  requests while a browser-driving QA charter can legitimately need far more.

**Not done here, deliberately.** Context compaction inside a stage, `output_type`
structured outputs, guardrails, and `RunState` gate resumption are all real gaps the same
audit found, but each changes what the model sees or how a stage resumes and none can be
proven on frozen data alone — they need a live run against the Azure deployment. Writing
`error_class` at the failure site is now a one-liner (`factory.classify_error`) and is
still unwired. Delegating stage 3's inner loop to Codex CLI via the SDK's experimental
`codex_tool` remains the strategically better answer than growing our own loop further;
it needs live Azure plumbing to evaluate.

**Proof.** `tools/azure-runner/test_factory.py` 29 → 47 tests: `Retry` (8, including
status-code precedence, terminal classification of `MaxTurnsExceeded`, and the real
backoff maths with injected sleep), `Checkpoints` (6, including "an untracked new file
survives a restore" — the bug `stash create` would have shipped — and ".gitignore is
respected"), `CoherenceCollapse` (3: a worse round is discarded, a better final round
ships unchanged, checkpoints can be switched off). Whole-suite green, `check_pr.py` green
with a regenerated `tools/evals/REPORT.md`.

## D24 — 2026-09-10 — Bind capabilities and verify the evidence behind a green gate

**Context.** The architecture assessment identified a mismatch between the role
charters and runtime authority: file tools could overwrite the harness or another
role's artifacts, a Git subcommand allowlist still admitted write/execute forms,
and a missing quality gate or missing test command could pass. Validation accepted
prose as evidence. A failed SDK turn discarded available trace and usage data.

**Decision.** Keep Azure OpenAI, the Agents SDK and the fixed code-driven pipeline.
Make the existing boundaries enforceable before adding another agent framework.

- File tools capture the run, role, output directory, product root and approved
  file scope at construction. Role outputs, shared report append rules, builder
  subdirectories and host artifacts are checked in code. Design collection uses
  the same policy. Windows case aliases, links, traversal and conventional
  credential filenames are checked before access. `docs/AGENT-CAPABILITIES.md` is
  generated from this policy and checked for drift.
- Read-only Git uses an explicit command/option grammar, disables external
  drivers and pagers, excludes protected filenames from broad searches and
  historical diffs, and rejects anonymous blob reads. File paths follow `--`;
  explicit `show revision:path` remains supported for permitted files.
- Automatic coding requires a configured test before the first model call. The
  initial quality configuration is fixed for the execution; replacing it during
  build/fix/test cannot produce a green gate. Missing, stale, malformed and
  contradictory gate records fail. Scope inspection uses NUL-delimited names,
  checks both sides of renames, and fails if Git cannot enumerate changes.
- Validation references identify existing confined files and valid text lines;
  self-citation fails. Review locations must belong to the handoff's diff and
  commit. Docker host rechecks obtain their own product checkout. These checks
  establish reference resolution, not semantic correctness or recording provenance.
- An execution journal persists completed SDK attempts and available partial
  failure data. Known usage survives later failures; absent usage remains
  explicitly incomplete. Transport retries do not replay a loop that has already
  called tools. Failure records use redacted messages and a retry classification.
- The eval report now includes labelled positive and negative verifier controls.
  Both false acceptance and false rejection are measured; an always-rejecting
  verifier cannot masquerade as success. Frozen scores are not live model scores.

**Validation.** Local SDK wrappers, temporary Git repositories, injected SDK/DB
failures and the repository's complete configured test command. Independent QA
found Windows aliases and implicit Git reads that the initial tests missed; all
three findings were fixed and the exact reproductions retested. Evidence and final
counts live in `workflow/runs/feat-20260910-agentic-infrastructure/03-coding/report.md`
and `04-qa-dev/report.md`.

**Limits and rollout.** This is a tool boundary, not an OS sandbox or cryptographic
gate attestation. Coding shells, MCP capabilities, database credentials, arbitrary
secret content, network egress and same-user filesystem races need separate
containment. Commands remain only as meaningful as their tests and human review.
Hard process kills before an SDK return still need streaming telemetry. No live
Azure run, Docker isolation proof or recorded browser QA is claimed here. Deploy
the host and sandbox image together; old green gates without fingerprints fail,
and new validation executions must replace prose-only citations. No schema change,
deployment or human gate decision is included in this local engineering change.

## D25 — 2026-09-11 — Stage 1 converges without Paper when a run says so (`design mode html`)

Found while carrying the first product feature (`feat-20260911-tender-onboarding`,
the Tender WhatsApp assistant) through the pipeline in a sandbox: **every feature run
stalls at `01-ui-ux.design` until someone with Paper Desktop runs a workstation
daemon.** The runboard on 2026-09-11 showed five runs parked there, one since
2026-08-31. D9's split is right for a team with design seats; it is a silent stop for
everyone else, and "the whole team can use this" cannot depend on one laptop.

**Decision.** A run carries a `design_mode` (`runs.design_mode`, default `paper`):
the brief's `- **Design mode:**`, `pipeline.py run --design-mode`, or
`set-design-mode <run-id>` for a parked run. `paper` is D9 unchanged. `html` makes
the ec2 runner claim `01-ui-ux.design` (the workstation never sees it) and the same
`ui-ux` execution converge the divergence survivors into self-contained HTML
prototypes under `01-ui-ux/prototype/`, critique them from browser screenshots (the
Playwright MCP it already has, launched at device scale 2 into `01-ui-ux/media/`),
and hand off those screenshots as the option PNGs. `handoff.json` declares the mode
and names each prototype; the orchestrator checks the prototypes exist and are real
(≥500 bytes) instead of the `jsx/` provenance it checks in Paper mode. The gate,
the critique log and `flow-spec.md` are unchanged. Skills: `agents/ui-ux/skills.md`
§3B-html.

**Why not make html the default.** Paper artboards are the team's design medium
and the JSX handoff is a better structural source than a prototype page; the
constraint layer (`design/`) was written for it. `html` is the mode for runs and
boxes that have no seat — it must never be the reason a designer stops being in the
loop. Mission Control's "needs the design workstation" warning is therefore only
shown for `paper` runs.

**Also in this change (same session, same cause — proving the pipeline in a sandbox
without credentials):** `pipeline.py` wires the model client after argparse and only
for commands that run an agent turn, so `--help`, `init-db`, `status`, `approve` work
on a box without Azure keys (`bug-20260908-help-crash-without-env`; regression test in
`lantern/regressions/`); a misconfigured model stack raises `ModelStackError` and
fails the stage instead of `sys.exit`ing the daemon with a claim held;
`LANTERN_MODEL_TIMEOUT_S` sets the per-request model timeout; Mission Control imports
on Python 3.11 again (two f-strings needed 3.12); `LANTERN_DAILY_SPEND_ALARM_USD`
defaults to 500; `pipeline.py step <run-id>` executes one stage of one run in the
foreground (a single daemon tick, for laptops and debugging); and `tools/relay-model/`
is a stand-in OpenAI-compatible endpoint that lets a person answer a stage's model
requests by hand — for debugging a prompt or a gate without spending credits.

