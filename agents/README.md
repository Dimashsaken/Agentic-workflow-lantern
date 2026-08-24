# Agent Roles

Each role is a folder with exactly three files. These files are **harness-agnostic**:
the same knowledge powers an Agents SDK orchestrator stage on EC2, a Codex CLI
session, or any future harness — the harness just loads them (decision D1; this
invariant is what made the D7 provider pivot cheap).

| File         | What it is                              | Who edits it                          |
|--------------|------------------------------------------|---------------------------------------|
| `charter.md` | Mission, scope, inputs/outputs, gates    | Humans, deliberately and rarely       |
| `skills.md`  | Procedures: how this role does its work  | Humans + agents via reviewed commits  |
| `memory.md`  | Dated judgement from past runs           | The agent, append-only, every session |

## Current roster

- `ui-ux` — flow options, prototype, walkthrough video (pipeline stage 1)
- `pre-coding` — blast radius, schema plan, task plan (stage 2)
- `coding` — implementation conventions for the developer's primary session (stage 3)
- `qa-dev` — exploratory + scripted QA in dev, video on (stage 4)
- `post-coding` — cleanliness, tech debt, backward compatibility (stage 5)
- `security` — vulnerabilities and deploy risk (stage 6)
- `qa-staging` — staging QA, video on, PostHog event verification (stage 7)
- `debug` — owns the bug lifecycle end to end (`workflow/DEBUG-LIFECYCLE.md`)

## Adding a role (the roster is designed to scale to ~20)

1. Copy `agents/_template/` to `agents/<new-role>/` and fill in all three files.
2. Register the role in the orchestrator's stage map
   (`tools/azure-runner/orchestrator.py`: `ROLE_FOR_STAGE`, plus `BROWSER_ROLES` /
   `FAST_ROLES` if applicable).
3. Update the roster above, the pipeline table in `AGENTS.md`, and
   `workflow/PIPELINE.md` if the role is a pipeline stage — same commit.
   (`.claude/agents/` wrappers are dormant — only touch them if reviving the Claude
   Code harness, see DECISIONS D7.)

Candidate future roles: performance, accessibility, data/analytics, docs, i18n,
cost-optimization, incident-response, release-notes.
