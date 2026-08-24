# Agent Runtime, Tools & Connections

This answers three questions precisely: **who is the "brain" of each agent**, **what
each agent is allowed to touch and with what identity**, and **how an agent orients
itself** (branches, prior sessions, project state) at the start of every session.

---

## 1. Brain vs. harness — untangling "GPT brain with Claude agentics"

An agent is two separable things:

- **Brain** — the LLM making decisions (Claude Opus/Sonnet, or a GPT deployment like
  `sol`/`terra`).
- **Harness** — the software that runs the loop around the brain: gives it tools,
  MCP connections, file access, subagents, permissions, and enforces our conventions.
  Claude Code is a harness. The OpenAI Agents SDK is a harness.

The pairing rules are hard constraints, not preferences:

| Brain | Harness | Works? | Azure credits? |
|-------|---------|--------|----------------|
| Claude | Claude Code (backend = Microsoft Foundry) | ✅ everything in this repo works natively | ✅ bills CCUs against MACC |
| GPT (`sol`/`terra`) | OpenAI Agents SDK (`tools/azure-runner`) | ✅ but we build/maintain the loop ourselves | ✅ Azure OpenAI |
| GPT (`sol`/`terra`) | Claude Code | ❌ **does not exist** — Claude Code runs Claude models only | — |

**The recommended shape (recorded as D5 in DECISIONS.md):**

- **Default: Claude brain + Claude Code harness via Foundry** for all pipeline stages.
  Subagents, `.mcp.json`, CLAUDE.md conventions, skills, permissions — all free. Same
  Azure credit pool.
- **GPT (`sol`/`terra`) via the azure-runner** where a second, cheaper, high-volume
  brain earns its keep: executing large QA charters, batch checks, repetitive browser
  runs. Both harnesses speak MCP, so the tool layer below is shared.
- Developers' laptops run Claude Code as themselves for stage 3, exactly as before.

Practical consequence: **stand up the fleet on Foundry first** (one env-var block,
zero harness code — see `infra/ec2/README.md`), and build the azure-runner only when
the first GPT-driven stage is actually scheduled.

---

## 2. Shared tool layer — MCP servers (`.mcp.json` at repo root)

Project-scoped MCP config lives in `.mcp.json` so every Claude Code session in this
repo gets the same connections; the azure-runner points its MCP client at the same
servers. Secrets are `${ENV_VAR}` references resolved from SSM — never literal values.

| Server | Used by | Purpose |
|--------|---------|---------|
| `playwright` | ui-ux, qa-dev, qa-staging, debug | Interactive browser driving (scripted runs use `tools/qa-recorder` directly) |
| `github` | pre-coding, coding, qa-*, post-coding, security, debug | Repos, branches, PRs, issues, reviews — as `lantern-bot` (§3) |
| `posthog` | qa-staging, debug | Event verification, error trends, session replays |
| `paper` | ui-ux only | Design files: browse existing designs, create options, export frames |

**Paper caveat (plan-ahead item):** Paper's MCP server attaches to the **desktop
app**, so it is not available on a headless EC2 box. Two workable setups:
(a) run the ui-ux agent's Paper work in a Claude Code session on a workstation where
Paper is installed (the `paper-desktop` plugin also provides `code-to-design` /
`design-to-code` skills there), or (b) skip Paper on EC2 and let ui-ux produce
HTML/mermaid options. Either way the **handoff contract is Paper-independent**: ui-ux
exports chosen frames as PNGs into `01-ui-ux/` and links the Paper file URL in
`options.md`, so no downstream agent ever needs Paper access.

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
session can resume. Each product repo keeps its **own CLAUDE.md**, which is
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
3. **The product repo's git state** —
   `git fetch --all --prune`, `git branch -r`, `git log --oneline -20` on the base
   branch, and `git log --all --grep=<run-id>` to find every commit already made for
   this run (including by other agents or the developer).
4. **The product repo's CLAUDE.md** — its conventions, commands, test invocations.
5. **Role-relevant externals** — open agent PRs (`gh pr list --label agent:<role>`),
   and for qa-staging/debug: current PostHog error state.

And the session-end postconditions grow by one (now three, see CLAUDE.md): stage
report, memory append, **runboard row update**.

---

## 6. Per-agent connection matrix

| Agent | MCP / CLIs | Credentials (SSM) | May write to |
|-------|-----------|-------------------|--------------|
| ui-ux | `paper` (workstation only), `playwright`, qa-recorder | — | run folder, `proto/*` branches |
| pre-coding | `github`, git (read), product repo clone | github bot token | run folder only |
| coding (developer) | developer's own gh/git + product tooling | human's own | `feat/*`, `fix/*` |
| qa-dev | `playwright`, qa-recorder, `github` (read + PR comments), S3 | github, `/lantern/qa/dev/*` | run folder, PR comments, regression specs on the feature branch |
| post-coding | git diff, `github` (PR review comments) | github | run folder, PR comments |
| security | git, `npm audit`, `github` (read), WebSearch for advisories | github | run folder only (vuln details follow charter confidentiality) |
| qa-staging | `playwright`, qa-recorder, `posthog`, S3, `github` (read) | github, posthog, `/lantern/qa/staging/*` | run folder, PR comments |
| debug | `posthog`, CloudWatch logs (read), git, `github`, qa-recorder | github, posthog | bug run folder, `fix/*` (trivial fixes only, per charter) |

Rule of thumb behind the matrix: **review-type agents get read + comment, never
push**; only ui-ux (prototypes), qa-dev (regression specs), and debug (trivial fixes)
touch branches, and only their own prefixes.
