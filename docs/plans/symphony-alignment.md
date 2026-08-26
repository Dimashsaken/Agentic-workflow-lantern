# Symphony alignment — keep the control plane, wrap Codex in, add the Slack front-door

**Status: PROPOSAL v2** (2026-08-26) — for Justin + CTO sign-off. Once approved, record
the decision as D13 in `docs/DECISIONS.md`. Research basis: openai/symphony SPEC.md +
Elixir implementation (claims adversarially re-verified against primary sources
2026-08-26), Fredrin (the LinkedIn post), Codex CLI v0.149 docs, hermes-agent, OpenClaw,
and Slack platform docs. v2 incorporates a three-lens adversarial review (architecture,
security, cost/ops) of the v1 draft — the material changes are marked **[v2]**.

## 1. What the CTO actually shared

- **[openai/symphony](https://github.com/openai/symphony)** — Apache-2.0, ~27k stars.
  NOT a product: a **SPEC.md** plus an experimental Elixir reference implementation that
  OpenAI labels *"a low-key engineering preview for testing in trusted environments"* and
  whose own README says *"we recommend implementing your own hardened version based on
  SPEC.md."* It turns an issue tracker (Linear/GitHub/Jira/Asana/GitLab) into the control
  plane: a polling daemon claims tickets, gives each an isolated workspace, and drives
  **Codex CLI in app-server mode** through one prompt template until the PR lands.
  Humans steer via board states (Backlog→Todo→In Progress→Human Review→Merging/Rework).
- **The LinkedIn post** (`lnkd.in/p/gYUBke2g`) resolves to Jae Lee promoting **Fredrin**
  (fredrin.com) — a closed-source commercial kanban desktop app by a solo developer:
  ticket → git worktree → Claude Code/Codex session → PR ("agents never merge"). The
  50-agents / 1,000%-velocity numbers are the vendor's own marketing.

The CTO is right that these are "essentially the same" **concept** as Lantern: ticket in,
isolated autonomous run, PR out, human on the merge. The difference is in the layers.

## 2. Gap analysis — Symphony vs. Lantern, verified

| Dimension | Symphony (verified from SPEC.md) | Lantern today |
|---|---|---|
| State | **In-memory only, no DB** — restart loses retry timers and sessions (open PRs beg for claim leases) | Postgres state machine, durable sessions, kill-recovery **proven on EC2** |
| Isolation | **None mandated** — sandboxing "deferred to implementers"; trusted-environment assumption | One ephemeral Docker sandbox per stage, isolation battery passed (D10/D12) |
| Verification | Trusts the agent; "proof of work" is convention (CI green, review comments, videos) | Mechanical postconditions: report exists + valid artifacts + memory row from THIS execution; host re-checks after the container. The 7-run fabrication saga is why this exists |
| Human gates | Board states; agent mutates ticket state itself via host-side tools | Fail-closed `approvals` rows written only by host-side surfaces (CLI/web) — see §4 C2.0 for the hardening this claim still needs |
| Pipeline shape | **One prompt template**; no roles/stages | 7 role stages + debug lifecycle, role memory, per-role tool matrix |
| Coding execution | **Codex CLI app-server — the mature harness** | Stage 3 = a human with Codex CLI; fleet stages = hand-rolled Agents SDK loops |
| Work intake | Issue tracker = control plane (its best idea) | Brief files + CLI (`pipeline.py run`) — only Justin can start work comfortably |
| Chat surface | None (no Slack anywhere in the spec) | None yet (D8 planned "Slack buttons later") |
| Code quality | 117-function god module, tests on 3/37 modules, circular dep (Elixir Forum static analysis) | Small, tested where it matters (`test_verification.py`) |

**Verdict: do not replace Lantern with Symphony.** Lantern already *is* the "own hardened
implementation" OpenAI tells you to build — with the durability, isolation, and
verification Symphony explicitly punts on. Adopting the Elixir preview would mean giving
up all three and re-learning the fabrication lessons (`role_memory`, artifact validity
checks) that cost us seven runs to earn.

**But Symphony and Fredrin expose three real Lantern gaps:**

1. **We automate everything *except the coding.*** Symphony's entire value is autonomous
   ticket→PR implementation; Lantern's stage 3 is a human. That's the velocity unlock the
   CTO is pointing at.
2. **No Slack front-door.** Every serious agent product (Codex, Devin, Cursor, Claude,
   Copilot, Factory) converges on the same Slack pattern: mention-to-task, thread-per-run,
   approval buttons. Our gates still live in a CLI and a Tailscale-only web UI.
3. **Undersized execution plane.** Concurrency cap 2 on a t3.large — but scaling waits
   until the loop is proven (§4 Phase 0) per the repo's own "scale when it hurts" rule.

## 3. The gateway question: OpenClaw / Hermes — NO for the control path

Both are excellent *personal assistant* gateways; neither should carry Lantern's approvals
or agent traffic:

- **OpenClaw**: 2026 security record is disqualifying for a company pipeline —
  CVE-2026-25253 (CVSS 8.8, one-click gateway takeover even on loopback), SSRF
  CVE-2026-26322, 135k+ unauthenticated gateways found exposed by Wiz, 1,184+ compromised
  ClawHub skills shipping infostealers, banned on Meta's corporate network. Its own docs:
  *"not a hostile multi-tenant security boundary."* Azure OpenAI is not first-party
  (custom endpoint or LiteLLM proxy). Every allowlisted Slack sender would share one
  blast radius with tools that hold our GitHub PAT.
- **Hermes (Nous Research hermes-agent)**: technically impressive (native Codex
  app-server runtime, Slack Socket Mode), but same consumer DNA, huge attack surface,
  and its Codex integration is built around ChatGPT-subscription OAuth — not our Azure
  key. It solves "a personal AI in my chats," not "fail-closed pipeline gates."

The Slack surface Lantern needs is small and must preserve one invariant: **only a
host-side service ever writes `approvals`; agents never touch Slack tokens.** A ~300-line
Bolt (Python) app over the existing Postgres does this. Routing gate approvals through a
third-party agent gateway would re-open the exact hole D8 closed. Revisit OpenClaw/Hermes
only if the org later wants personal assistants — a separate concern from the pipeline.

**[v2]** That invariant is currently a *tool-level convention*, not an enforced boundary:
every sandbox receives the full-privilege DB URL (`pipeline.py` `sandbox_db_url()`), and
the single `lantern` Postgres user owns the whole database — code running inside any
sandbox could write `approvals` with one SQL statement. Harmless-ish while sandboxes run
curated Agents SDK tool loops; fatal once a shell-wielding Codex agent runs there. Fixing
this (C2.0) is a hard prerequisite for Phase 2 and cheap insurance before it.

## 4. Plan of action

Dates assume roughly the current team (one builder + Justin/CTO at gates). Phases are
sequenced by dependency; later dates are planning targets, not commitments — **[v2]**
Phase 0 and Phase 2 were doubled from v1 after review, and Phase 3 is trigger-based.

### Phase 0 — Prove the loop end-to-end (now → ~Sep 8, 2 weeks)

The system has never completed a brief→prod_signoff run. Nothing below matters until it
has. No new scope beyond what's listed.

- [ ] **P0.1** QA sandbox image: bake `tools/qa-recorder` node_modules (stage 4+ was
  explicitly out of image v1). **[v2]** Credential/network design is part of this task,
  not an afterthought: dev-env URL + test credentials enter via the per-stage env
  allowlist (D12 pattern — `/lantern/qa/dev/*` SSM params), the dev environment must be
  reachable from the sandbox network, and **no AWS credentials enter the sandbox** — the
  video lands in the host-mounted run folder and the **dispatcher uploads to S3 after
  postconditions pass**. Acceptance: stage 4 runs in a sandbox; its video reaches S3 via
  the host path.
- [ ] **P0.2** **[v2 — moved to the END of Phase 0, after P0.3 passes]** Resize the box
  to **m5.2xlarge** (8 vCPU / 32 GB, ~$0.38/hr ≈ **$65/wk**) and raise
  **`LANTERN_MAX_CONCURRENCY`** (the real knob — set to 2 in
  `infra/ec2/lantern-orchestrator.service`) toward **~5**, the ceiling the repo's own
  sizing doc supports (sandboxes are provisioned at 1.5 vCPU each; 8–10 would be 150%+
  CPU oversubscription, and the only memory datapoint is browser-*idle*). Re-measure with
  browser-active QA load before going higher. The first-ever full run happens on the
  known-good t3.large at cap 2 — don't add suspects to it.
- [ ] **P0.3** Run one real feature brief through all 7 stages, gates included. File
  every failure as a memory entry. Stage 1 alone took seven attempts to pass honestly;
  budget the same discovery tax for stages 4–7's first sandbox runs. Acceptance:
  `prod_signoff` approved on a real run.
- [ ] **P0.4** **Token ledger**: per-stage-execution token counts (Agents SDK usage
  object) into `stage_executions`, rolled up per run. **[v2]** Scope v1 = fleet stages
  only; the human stage-3 Codex session runs on a developer laptop and its JSONL is out
  of reach until the auto-coding stage exists. Includes a **daily** threshold check that
  posts immediately (email/webhook until Slack exists; Slack from Phase 1) — see §5 for
  thresholds. The weekly digest is reporting; the daily check is the alarm.

### Phase 1 — Slack front-door, core only (~Sep 8 → Sep 15)

One Bolt-Python app, **Socket Mode** (outbound WebSocket — no public endpoint on the
Tailscale-only box), new systemd unit `lantern-slack` beside Mission Control, reading the
same Postgres. **[v2]** Scope cut to the two items that are the actual front-door;
S1.3/S1.4 slide into the Phase 2 window. **[v2]** Verify the workspace's Slack plan
before Sep 8: a Socket-Mode custom app runs even on the free tier (with the ~10-app cap
and 90-day history limit — approvals live in Postgres, so history loss is cosmetic), but
if an upgrade is wanted it's a real budget line, not $0.

- [ ] **S1.1** Run threads: on run creation, post to `#lantern-runs`; every state change
  (`events` table → poll or LISTEN/NOTIFY) is a threaded reply. `thread_ts` ↔ `run_id`
  mapping in a new table. The convergent industry pattern (Codex/Devin/Cursor) verbatim.
- [ ] **S1.2** Gate approvals: pending `approvals` post as Block Kit messages with
  Approve/Reject buttons + payload summary (UX options render their PNGs). `block_actions`
  → server-side allowlist mapping Slack user ID → approver name → write the row with
  `channel='slack'`. Fail-closed unchanged: rejected = failed run, same as CLI/web.
  **[v2]** Slack-session compromise = gate authority, so the two highest-stakes gates —
  `staging_deploy` and `prod_signoff` — stay Mission-Control/CLI-only (Tailscale) until
  the team explicitly decides otherwise; Slack carries `ux_signoff`, `plan_signoff`,
  `code_complete`.
- [ ] **S1.3** *(moved into Phase 2 window)* `@lantern ask <role>` → consult mode (D11),
  reply in-thread; `@lantern run <brief-ref>` → start a run. **[v2]** The server-side
  user allowlist applies to **every** `@lantern` verb, not just `run` — consult mode
  reads the whole repo including unreleased security findings — and the app only
  responds in named channels. Slack workspace membership is not an authorization
  boundary.
- [ ] **S1.4** *(moved into Phase 2 window)* Weekly cost digest to Slack from the token
  ledger + AWS daily spend; the P0.4 daily alarm also posts here.
- Acceptance: one run's gates (the three Slack-carried ones) decided from Slack, with
  `events` showing `channel='slack'` actors.

### Phase 2 — Wrap Codex in: autonomous coding stage (~Sep 15 → Oct 13, 4 weeks)

The Symphony-shaped piece we actually lack. Add a per-run coding mode:
`runs.coding_mode = human | auto` (human remains the default and the only option for
schema-touching or `HITL: required` runs). **[v2]** Two security preconditions (C2.0,
C2.5) now come *before* the first auto run, and the egress work is a parallel track with
its own owner, not a checkbox.

- [ ] **C2.0 [v2 — NEW, hard prerequisite]** Restricted sandbox DB role: create a
  Postgres role for containers with INSERT-only on `role_memory` + the SDK session
  tables and **no privileges on `approvals`/`runs`/`stage_executions`**;
  `sandbox_db_url()` switches to it. This turns "agents have no write path to approvals"
  from convention into an enforced boundary — it also hardens today's stages, so land it
  early in the phase regardless of Codex progress.
- [ ] **C2.1** *De-risk first (timeboxed 2 days)*: verify Codex CLI headless against our
  Azure deployments **from inside a sandbox as uid 1000 with `HOME=/work`** (the
  entrypoint dance has bitten once already). Known open bug: gpt-5.6-family models
  hardcode ChatGPT-backend-only flags and 400 on Azure (openai/codex
  #31870/#31875/#31882); workaround is a custom `model_catalog_json`
  (`use_responses_lite:false`, `multi_agent_version:null`), or pin a `gpt-5.x-codex`
  deployment. **[v2]** If the timebox fails, the fallback — an Agents SDK coding loop —
  is a real build with an explicit 1-week contingency line, not a parenthetical; decide
  at the timebox boundary whether to spend it or wait on the upstream fix.
- [ ] **C2.2** Sandbox image v2: Codex CLI + `codex exec` wiring (`model_provider=azure`,
  `wire_api="responses"`, env-allowlisted Azure key), and the `append_memory`/artifact
  tools exposed to Codex via a thin MCP shim so postconditions hold identically in both
  harnesses. **[v2]** The `.mcp.json` mirror into the sandbox **excludes** the github and
  posthog servers — no PAT-bearing tool enters the coding sandbox.
- [ ] **C2.3** The `03-coding.auto` stage: `codex exec` on the run's `feat/*` branch with
  the task plan from stage 2 as the prompt, `--output-schema` for the self-review report,
  session ID persisted host-side for `exec resume` on retry. **[v2]** Push/PR mechanics —
  the PAT never enters the sandbox: the sandbox's private product-repo clone emits a
  **git bundle into the host-mounted run folder**; after the container exits and
  postconditions pass, the **dispatcher** verifies the bundle only touches the run's
  `feat/*` branch, pushes it as `lantern-bot`, and opens the PR with the evidence pack
  auto-commented (stage reports, QA charter, links). **[v2]** Gate mechanics, stated
  precisely: `code_complete` remains an **approvals row** — the PR link + evidence pack
  is the payload a human approves from Slack/Mission Control; nothing advances off
  GitHub state directly (a host-side PR-review poller writing the row can come later —
  the box has no inbound endpoint for webhooks). **Merge does not move**: per
  PIPELINE.md, stages 4–6 run pre-merge on the branch, and merge stays a human action
  after security/staging — Symphony's "convince a human to merge" lands as our gate on
  our state machine, and (Fredrin's rule) agents never merge. **[v2]** Enumerated
  dispatcher changes so the estimate is honest: `FEATURE_STAGES`' static `human` tuple
  becomes per-run (`coding_mode` branch in claim/advance), a second sandbox entrypoint
  (codex exec vs. orchestrator.py), and a per-stage timeout knob (the global 45-min
  `LANTERN_STAGE_TIMEOUT_MIN` is wrong for a coding stage).
- [ ] **C2.4** Pilot on 3–5 small, well-specified briefs (the verified Symphony-user
  lesson: vague tickets produce mediocre code — pre-coding's task plan is our
  ticket-quality firewall). Compare wall-clock + review burden vs. human runs; record in
  memory. **[v2]** This is 6–10 gated end-to-end runs in a system that will have
  completed ~2 ever — it's the back half of the 4 weeks, and it slips before quality does.
- [ ] **C2.5 [v2 — moved BEFORE the first pilot run]** Egress control is a
  **prerequisite, not a graduation requirement**: `npm install`/`pip install` executes
  registry-supplied code (postinstall scripts of transitive deps) — that *is* D12's
  "untrusted third-party input," even on a trusted repo, and "trusted repos only" was v1
  claiming D12 compliance while violating it. Parallel track, own owner, landing before
  C2.4: per-container network + nftables (or authenticated proxy) allowlisting Azure,
  GitHub, the product repos' registries, and Postgres; plus `--ignore-scripts`/frozen
  lockfile installs where the product stack allows. With C2.0 + the PAT already kept
  host-side, the remaining sandbox blast radius is the Azure key and the run's own
  branch — bounded, and stated plainly.
- Acceptance: an `auto` run goes brief→PR→(human `code_complete`)→stages 4–6→merged by a
  human, with C2.0/C2.5 in force throughout.

### Phase 3 — Board intake + evidence packs (trigger: Phase 2 acceptance; ~2 weeks)

Symphony's genuinely best idea: work intake is a board, not a CLI. **[v2]** Dates are
deliberately unset — this starts when Phase 2's acceptance passes, not on a calendar day.

- [ ] **B3.1** Tracker: **Linear** (team decision, 2026-08-26 — also Symphony's
  canonical tracker, so its board-state conventions and the ecosystem's Linear patterns
  transfer directly). A `Lantern` label + brief template in the issue description →
  `pipeline.py` creates the run, links the Slack thread and Mission Control URL back on
  the issue, and mirrors state transitions as issue comments (Linear GraphQL via a
  host-side `LINEAR_API_KEY`, never inside sandboxes — the Symphony credential-isolation
  rule). Map Linear workflow states to run states the Symphony way:
  Backlog (untouched) → Todo (intake) → In Progress → In Review (gates) → Done. **[v2]** Authorization checks the **label applier**
  (webhook/poll actor) against the same allowlist as S1.3 — and content provenance is
  separate from authorization: an issue authored outside the team is **transcribed by a
  human into the brief template, never passed verbatim** (the issue body becomes every
  downstream agent's root prompt), and externally-authored intake is barred from
  `coding_mode=auto`.
- [ ] **B3.2** Mission Control v2 items that Slack doesn't cover: SSE updates, inline
  video (presigned S3, short TTL, rendered only inside authenticated Mission Control
  pages — **[v2]** raw presigned URLs don't go into PR/issue comments, whose visibility
  may exceed the approver set), deep links Slack⇄MC both ways.
- [ ] **B3.3** Evidence pack standard: every agent PR carries CI status + stage reports +
  gate history + **links to Mission Control** for videos, auto-commented. (Fredrin's
  "real exit codes in the PR" and Symphony's proof-of-work, unified.)
- [ ] **B3.4** Debug lifecycle intake: PostHog signal / user report → `bug-*` issue →
  debug agent run, same board — with the same transcription rule: attacker-authored bug
  text never becomes an agent prompt verbatim.

### Phase 4 — Scale as it hurts (trigger-based)

- Concurrency: beyond ~5 needs measurement with browser-active load, then a bigger box;
  second VM + S3-backed run folders only when one box saturates (the D8/D10 trigger).
- Best-of-N on hard coding tasks (N parallel attempts, judge picks — we already run
  diverge+judge for UX in D9; `codex exec fork` per the v0.148 changelog, to be verified
  in C2.1).
- Durable-execution upgrade (DBOS → Temporal) only if Postgres-machine ops bite.
- Langfuse self-hosted when tracing pain is real (D8 left this open).

## 5. Budget (constraint: ≤ $10k/week; target far under)

| Item | Est. weekly |
|---|---|
| m5.2xlarge (on-demand, always-on, from end of Phase 0) | ~$65 (US regions; +10–25% EU/AP) |
| gp3 100 GB + S3 (videos, 90-day expiry) + egress | ~$15 |
| Slack (verify plan — free tier suffices for Socket Mode; upgrade is a real line if chosen) | $0–TBD |
| **AWS cash total** | **~$80/wk** |
| Azure OpenAI (credits) | Unanchored until P0.4 measures — see below |

**[v2] The honest cost picture.** The Azure token estimate (20–100M tok/day ≈
$60–600/day) is a 10× range with unverified blended pricing (`sol`/`terra` are opaque
deployment labels); no number here is real until the P0.4 ledger measures actual runs —
treat thresholds as provisional and recalibrate after Phase 0. Two separate guardrails,
because there are two different ceilings:

1. **Rate tripwire** (the $10k/wk constraint): **daily** ledger check, provisional
   threshold $1,200/day model spend, posting immediately — not in a weekly digest. The
   known blow-up mode is Symphony-style unattended retries (verified reports of ~$2–3k/day
   at extreme usage); stage timeouts, retry backoff, and `max_turns` are the brakes, the
   daily check is the alarm.
2. **Pool drawdown** (the finite ~$25k credit pool, D7): cumulative alarms at 25% / 50% /
   75% of the pool. At the estimate's high end the pool lasts ~6 weeks — i.e. roughly
   this plan's own calendar — after which "credits, not cash" silently becomes cash.
   **Decision needed from Justin/CTO before the 75% alarm**: post-credit budget line, or
   throttle (auto-coding is the discretionary spend to cut first).

## 6. Risks and honest unknowns

- **Codex-on-Azure model bug** (#31882 open): mitigated by the C2.1 timebox + the
  explicitly-budgeted Agents SDK fallback. Do not commit Phase 2 externally until C2.1
  passes.
- **Human review becomes the bottleneck** — the #1 reported Symphony failure mode, and
  now also the plan's schedule risk: Phases 0 and 2 both contain full gated runs, so
  gate latency governs the calendar. Track gate-latency in Mission Control; if a gate
  median exceeds a day, that's a staffing conversation, not an automation one.
- **Auto-coding quality**: the fabrication lessons say agents fake it when they lack
  capability. Postconditions + PR-as-payload gate + QA-on-video are the containment;
  pilot scope (C2.4) is small on purpose.
- **Slack approval authority = Slack account security**: acknowledged, and why
  `staging_deploy`/`prod_signoff` stay off Slack (S1.2). Revisit with a step-up factor
  if the team wants all gates in Slack.
- **Prompt injection through intake** (B3.1/B3.4): handled by transcription + the
  auto-mode bar for external authors; the coding sandbox additionally can't reach the
  PAT or the approvals table (C2.0/C2.3) and has bounded egress (C2.5).
- **Fredrin**: nothing to adopt beyond validation; closed-source, solo-maintainer,
  wrong trust model for our credentials. Worth a demo for UX ideas at most.
- **Symphony spec drift**: cheap insurance — keep our tracker-intake (B3.1) conceptually
  adapter-shaped so a future Symphony-spec-compatible intake is a refactor, not a rewrite.
- **Open item deferred, stated plainly**: human stage-3 token capture (developer-laptop
  Codex JSONL → ledger) has no mechanism yet; the ledger undercounts until the auto
  stage exists or a laptop-side reporter is built.
