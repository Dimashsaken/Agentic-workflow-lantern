# Agent Roles

Each role is a folder with exactly three files. These files are **harness-agnostic**:
the same knowledge powers a Claude Code subagent, a headless EC2 session, or an Azure
OpenAI-driven runner — the harness wrapper just loads them.

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
2. Add a wrapper at `.claude/agents/<new-role>.md` (copy an existing one; change only
   the frontmatter and the role folder path).
3. Update the roster above, the pipeline table in `CLAUDE.md`, and
   `workflow/PIPELINE.md` if the role is a pipeline stage — same commit.

Candidate future roles: performance, accessibility, data/analytics, docs, i18n,
cost-optimization, incident-response, release-notes.
