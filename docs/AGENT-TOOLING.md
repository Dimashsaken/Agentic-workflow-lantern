# Agent Runtime, Tools & Connections

This answers three questions precisely: **who is the "brain" of each agent**, **what
each agent is allowed to touch and with what identity**, and **how an agent orients
itself** (branches, prior sessions, project state) at the start of every session.

---

## 1. The runtime stack — Azure OpenAI only (D7)

An agent is two separable things: the **brain** (the LLM — one of the org's Azure
OpenAI deployments, `sol`/`terra`) and the **harness** (the loop that gives the brain
tools, MCP connections, file access, and enforces our conventions).

By decision D7 the brain side is fixed: **every agent runs on Azure OpenAI** (the
startup credits). That rules out Claude Code as a harness (it runs Claude models
only), so the fleet uses the OpenAI-native harnesses:

| Harness | Role in Lantern | Notes |
|---------|-----------------|-------|
| **OpenAI Agents SDK** — `tools/azure-runner/orchestrator.py` | All pipeline stages except coding; the debug lifecycle | One stage per invocation; postconditions enforced in code; MCP + function tools |
| **Codex CLI** (Azure provider config) | Stage 3 coding on developer laptops; `codex exec` for headless repo tasks on EC2 | Reads `AGENTS.md` natively — same contract file as the SDK stages load |

Deployment routing lives in the orchestrator: `LANTERN_MODEL_REASONING` (the stronger
deployment) for judgement-heavy roles, `LANTERN_MODEL_FAST` for volume QA execution.
Swapping which of `sol`/`terra` fills which slot is a one-env-var change.

`AGENTS.md` at the repo root is the canonical contract (the OpenAI-ecosystem
convention); `CLAUDE.md` is just a pointer to it. The `.claude/agents/` wrappers are
**dormant** — kept only because they cost nothing and regenerate the fleet on a
Claude Code harness in minutes if the provider decision ever changes; they are not
part of the running system.

---

## 2. Shared tool layer — MCP servers

`.mcp.json` at the repo root is the **single reference list** of shared servers; each
harness wires them its own way — the Agents SDK attaches them in `orchestrator.py`,
Codex CLI mirrors the needed ones into `~/.codex/config.toml` (`[mcp_servers]`).
Secrets are `${ENV_VAR}` references resolved from SSM — never literal values.

| Server | Used by | Purpose |
|--------|---------|---------|
| `playwright` | ui-ux, qa-dev, qa-staging, debug | Interactive browser driving (scripted runs use `tools/qa-recorder` directly) |
| `github` | pre-coding, coding, qa-*, post-coding, security, debug | Repos, branches, PRs, issues, reviews — as `lantern-bot` (§3) |
| `posthog` | qa-staging, debug | Event verification, error trends, session replays |
| `paper` | ui-ux only | Design files: browse existing designs, create options, export frames |

**Paper is per-developer, never hosted (D10).** Its MCP has no auth of its own: it
answers plain HTTP on `127.0.0.1:29979` and acts as whoever is signed into the desktop
app (verified 2026-08-26). A developer therefore "connects their own account" simply by
running Paper Desktop locally — their laptop runs `pipeline.py daemon --runner
workstation`, reaches the cloud Postgres over Tailscale, and claims only
`01-ui-ux.design` for runs they own (`runs.created_by`). Each developer points
`LANTERN_PAPER_FILE_ID` at an agent-owned file in their own workspace. This removes the
concurrency ceiling a shared design desktop would impose, and needs no GUI VM.

**Original caveat (implemented as runner affinity, D9):** Paper's MCP server attaches to
the **desktop app** (`http://127.0.0.1:29979/mcp`, `LANTERN_PAPER_MCP_URL`), so it is
not available on a headless EC2 box. Stage 1 is therefore split: divergence runs on
EC2; the Paper convergence execution (`01-ui-ux.design`) is claimed only by
`pipeline.py daemon --runner workstation` on the design machine, which preflights the
Paper port before claiming (`tools/azure-runner/README.md`). The agent discovers the
live tool list via `tools/list` at session start — tool names drift and are never
hardcoded. The **handoff contract stays Paper-independent**: ui-ux exports chosen
frames as PNGs + `handoff.json` into `01-ui-ux/` and links the Paper file URL, so no
downstream agent ever needs Paper access.

**Endpoint hygiene:** remote MCP URLs (GitHub, PostHog) drift — when first wiring a
box, verify against the providers' current MCP docs rather than trusting the values
in `.mcp.json` blindly, and update the file if they've moved.

---

## 3. GitHub identity — how agents act as collaborators

Agents never use a human's credentials. One machine identity, tightly scoped:

- **`lantern-bot`** — a GitHub machine user (upgrade to a GitHub App later if audit
  needs grow) added as a collaborator with **Write** on each product repo. Fine-grained
  PAT stored at SSM `/lantern/github/bot-token`; on EC2 it is loaded into the session
  env and used by both `gh` (`gh auth login --with-token`) and the `github` MCP server.
- **Branch rules (enforced by branch protection, not by trust):**
  - `main` (and `staging` if present): protected — PRs only, ≥1 human review, no
    direct pushes, bot included.
  - Agents may create/push only `feat/*`, `fix/*`, `proto/*` branches.
- **Attribution:** commits by agents are authored `lantern-bot`, prefixed with the
  run ID (existing convention), and carry a trailer `Lantern-Agent: <role>` so
  `git log` shows *which* agent did what. Agent-opened PRs get the label
  `agent:<role>` and link the run folder in the description.
- Humans (developers doing stage 3) commit as themselves, as always.

Setup checklist (once per product repo): invite `lantern-bot` → set branch
protections → create the label set → store the PAT in SSM.

---

## 4. Where the product code lives

Lantern is the **control plane** — product code stays in its own repos. On EC2,
product repos are cloned under `~/work/<repo>`. Every feature brief names the product
repo and base branch; the run folder's reports always state repo + branch so any
session can resume. Each product repo keeps its **own AGENTS.md**, which is
authoritative for that codebase's conventions — Lantern's `agents/coding/skills.md`
explicitly yields to it.

---

## 5. Orientation protocol — how an agent "knows everything"

Every session, after the standard role reads (charter → skills → memory), an agent
orients in this order. This is cheap (a minute) and non-negotiable:

1. **`workflow/RUNBOARD.md`** — the live index of runs: what's in flight, at which
   stage, blocked on what. Answers "what happened recently" without archaeology.
2. **The active run folder** — brief + every upstream report. The run folder is the
   session history; nothing relevant is allowed to exist only in a chat log (D4).
3. **The product repo's git state.** Fleet stages get the run's product repo checked
   out **read-only** under the `product/` path prefix (`read_file('product/src/app.ts')`,
   `list_dir('product/src')`) plus the **`product_git`** tool — real git, read-only
   subcommands only, no shell:
   `product_git('log', ['--oneline','-20'])` for recent history, `product_git('branch',
   ['-a'])`, `product_git('log', ['--all','--grep','<run-id>'])` for work already done
   for this run, and `product_git('grep', ['-n','<symbol>'])` to trace consumers.
   The checkout is a throwaway clone of a **host-side mirror**: no credentials, no push
   path, nothing written there survives the container. Stage 3 (coding) is where product
   code is written, in the developer's own session.
   If a stage reports `product/` missing, the run has no product target — that is a
   BLOCKED report asking for `pipeline.py set-product`, never a guess at paths.
4. **The product repo's AGENTS.md** — its conventions, commands, test invocations
   (`read_file('product/AGENTS.md')`).
5. **Role-relevant externals** — open agent PRs (`gh pr list --label agent:<role>`),
   and for qa-staging/debug: current PostHog error state.

Session-end postconditions (see AGENTS.md): stage report on disk, and a memory entry
recorded via the `append_memory` tool. The runboard is **rendered from the pipeline
database** — agents read it during orientation but never write it.

---

## 6. Per-agent connection matrix

| Agent | MCP / CLIs | Credentials (SSM) | May write to |
|-------|-----------|-------------------|--------------|
| ui-ux | `paper` (workstation only), `playwright`, qa-recorder | — | run folder, `proto/*` branches |
| pre-coding | `github`, git (read), product repo clone | github bot token | run folder only |
| coding (developer) | developer's own gh/git + product tooling | human's own | `feat/*`, `fix/*` |
| qa-dev | `playwright` (video-recording, orchestrator-configured), qa-recorder, `github` (read + PR comments) | github, `/lantern/qa/dev/*` (as `QA_*`) | run folder, PR comments, regression specs on the feature branch |
| post-coding | git diff, `github` (PR review comments) | github | run folder, PR comments |
| security | git, `npm audit`, `github` (read), WebSearch for advisories | github | run folder only (vuln details follow charter confidentiality) |
| qa-staging | `playwright` (video-recording, orchestrator-configured), qa-recorder, `posthog`, `github` (read) | github, posthog, `/lantern/qa/staging/*` (as `QA_*`) | run folder, PR comments |
| debug | `posthog`, CloudWatch logs (read), git, `github`, qa-recorder | github, posthog | bug run folder, `fix/*` (trivial fixes only, per charter) |

Rule of thumb behind the matrix: **review-type agents get read + comment, never
push**; only ui-ux (prototypes), qa-dev (regression specs), and debug (trivial fixes)
touch branches, and only their own prefixes.
