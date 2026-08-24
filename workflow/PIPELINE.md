# The Feature Pipeline

Every feature moves through these stages in order. Stages never run out of order and
never skip; a stage may be marked `WAIVED` in its report only by Justin.

The handoff medium is the **run folder**: `workflow/runs/<run-id>/`. Each stage reads
everything upstream and writes its own `<stage-dir>/report.md` using
`workflow/templates/stage-report.md`. If it's not in the run folder, it didn't happen.

```
brief ──▶ 01 ui-ux ──▶ 02 pre-coding ──▶ 03 coding ──▶ 04 qa-dev ──▶ 05 post-coding ──▶ 06 security ──▶ [staging deploy] ──▶ 07 qa-staging ──▶ [prod]
            ▲ gate:            ▲ gate:                       │ gate:                          ▲ gate:                              ▲ gate:
            pick option        approve schema                no sev-1/2 bugs                  no high-risk findings               Justin sign-off
```

---

## Stage 1 — UI/UX (`ui-ux` agent) → `01-ui-ux/`

**In:** the feature brief.
**Do:** map the user flow; produce 2–3 distinct "paper" options (described + wireframed
in markdown/ASCII/mermaid, or HTML mock); once an option is picked, build a clickable
prototype and record a **walkthrough video** with `tools/qa-recorder`.
**Out:** `options.md`, `prototype/` (code), video link in the report.
**Gate:** Justin or the assigned developer picks an option. `HITL: required`.

## Stage 2 — Pre-coding (`pre-coding` agent) → `02-pre-coding/`

**In:** brief + chosen UX option.
**Do:** blast-radius analysis (files, modules, services touched), schema/migration plan,
code-structure plan, new-package justification, coding-principles callouts, and an
explicit decision: does any part of implementation require human-in-the-loop?
**Out:** `blast-radius.md`, `schema-plan.md`, `task-plan.md` (ordered, sized tasks for
the developer).
**Gate:** schema plan and task plan approved by the developer; schema changes always
`HITL: required`.

## Stage 3 — Coding (assigned developer, primary Claude Code session) → `03-coding/`

**In:** approved task plan.
**Do:** implement on branch `feat/<slug>`, following `agents/coding/skills.md`
(conventions, commit discipline, test-alongside rules). Multi-phase features land as a
sequence of reviewable commits mapped to the task plan.
**Out:** the branch; `report.md` listing commits, deviations from the plan, and known
gaps for QA to probe.
**Gate:** developer declares code-complete; all tasks in the plan checked off or
explicitly deferred.

## Stage 4 — QA in dev (`qa-dev` agent) → `04-qa-dev/`

**In:** code-complete branch running in the dev environment.
**Do:** design a test charter from the brief + coding report (happy paths, edge cases,
regression suspects from `memory.md`); execute it by driving the real UI with
`tools/qa-recorder` (Playwright, **video on**); file each bug with severity, repro
steps, and a video timestamp.
**Out:** `test-charter.md`, `bugs.md`, video links per session.
**Gate:** zero open sev-1/sev-2. Sev-3+ may pass with developer acknowledgement.
Bugs loop back to stage 3; QA re-runs the affected charter items.

## Stage 5 — Post-coding review (`post-coding` agent) → `05-post-coding/`

**In:** QA-passed branch.
**Do:** review the full diff for cleanliness (dead code, duplication, naming,
leftover debug), hidden tech debt (TODO bombs, hardcoded values, missing indexes,
n+1 queries), and **backward compatibility** (API contracts, schema rollback safety,
feature-flag defaults, old-client behaviour).
**Out:** findings list, each tagged `fix-now` / `debt-ticket` / `waived`.
**Gate:** all `fix-now` items resolved.

## Stage 6 — Security & deploy risk (`security` agent) → `06-security/`

**In:** final branch, diff against main.
**Do:** dependency audit of any new packages, secrets scan, authz/authn review of new
endpoints, injection/XSS surface review, migration failure modes, rollback plan review,
deployment blast-radius (what breaks if this deploy is bad?).
**Out:** risk report with severity-ranked findings and a go/no-go recommendation.
**Gate:** no unmitigated high findings. Human deploys to staging.

## Stage 7 — QA in staging (`qa-staging` agent) → `07-qa-staging/`

**In:** feature live on staging.
**Do:** re-run the stage-4 charter against staging plus staging-only checks (real
integrations, data volume, auth flows, cross-browser); **video every session**;
verify PostHog events fire as specced.
**Out:** run results, videos, event-verification checklist.
**Gate:** Justin reviews the videos and report and signs off for production.
`HITL: required`.

---

## Cross-cutting rules

- **Blocked ≠ failed.** A blocked stage writes `Status: BLOCKED` with one precise
  question and stops. It does not improvise around missing decisions.
- **Loops are normal.** QA→coding and security→coding loops stay inside the same run
  folder; append to the existing reports rather than overwriting (`## Round 2` etc.).
- **Every stage feeds memory.** A bug that QA missed in dev but staging caught means
  `qa-dev` appends a memory entry. A security finding that pre-coding should have
  predicted means `pre-coding` appends one. This is how the pipeline gets better.
- **Videos:** any stage that drives a browser records video. Naming:
  `<run-id>--<stage>--<session-n>.webm`, uploaded to the artifact bucket, linked from
  the report with a one-line description of what the video shows.
