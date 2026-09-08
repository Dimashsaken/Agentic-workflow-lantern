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
