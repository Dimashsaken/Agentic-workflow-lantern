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

Runs as **two executions with different runners** (D9, `docs/plans/ui-ux-agent-paper.md`):

- `01-ui-ux.diverge` (EC2, fast model): map the user flow, generate 5–10 low-fi HTML
  skeletons on named structural axes into `divergence/`, judge-score them against the
  brief, keep the best 2–3.
- `01-ui-ux.design` (design workstation, Paper MCP): converge the survivors into Paper
  artboards grounded in `design/design-system.md`, run the screenshot-critique loop
  (≤3 iterations per option, layout pass separate from style pass per
  `design/critique-checklist.md`), export 2x PNGs, write `handoff.json`.

**In:** the feature brief + the design constraint layer (`design/`).
**Out:** `options.md`, `divergence/`, per-option 2x PNGs, `handoff.json` (feeds the
gate payload), and — for the recommended/chosen option — the full handoff package:
`flow-spec.md`, `jsx/` per frame, Paper file URL, walkthrough video (Paper MP4 export,
or a `prototype/` recording via `tools/qa-recorder` when interaction matters).
**Gate:** Justin or the assigned developer picks an option in Mission Control, which
shows the Paper URL + option PNGs side by side. Picking a non-recommended option =
reject with a note naming it; `retry` re-enters the stage (same session memory) to
package that option and mark the rest `[rejected]`. `HITL: required`.

## Stage 2 — Pre-coding (`pre-coding` agent) → `02-pre-coding/`

**In:** brief + chosen UX option.
**Do:** blast-radius analysis (files, modules, services touched), schema/migration plan,
code-structure plan, new-package justification, coding-principles callouts, and an
explicit decision: does any part of implementation require human-in-the-loop?
**Out:** `blast-radius.md`, `schema-plan.md`, `task-plan.md` (ordered, sized tasks for
the developer).
**Gate:** schema plan and task plan approved by the developer; schema changes always
`HITL: required`.

## Stage 3 — Coding (assigned developer, or the `coding` agent in auto mode) → `03-coding/`

**In:** approved task plan.
**Do:** implement on the run's branch, following `agents/coding/skills.md`
(conventions, commit discipline, test-alongside rules). Multi-phase features land as a
sequence of reviewable commits mapped to the task plan.
**Two modes, chosen per run (D14)** — `- **Coding mode:**` in the brief,
`pipeline.py run --coding-mode`, or `pipeline.py set-coding-mode`:
- `human` (default) — the assigned developer implements the plan in their own coding
  session on their own machine; the gate opens immediately and the developer approves
  it when the branch is code-complete.
- `auto` — the fleet's `coding` agent implements the plan in a sandbox on a WRITABLE
  clone of the product repo (branch `feat/<date>-<slug>`, `fix/…` for bug runs), with a
  shell for builds and tests, committing per task as the bot identity. It cannot push:
  the harness bundles the committed branch into the run folder, and the HOST verifies
  the bundle, pushes the branch and opens the pull request. That PR is the
  `code_complete` payload a human reviews in Mission Control. Agents never merge.
**Out:** the branch; `report.md` listing commits, deviations from the plan, and known
gaps for QA to probe; in auto mode also `handoff.json` + `branch.bundle` (the evidence)
and `pr.md` (where it went).
**Gate:** code-complete declared — by the developer, or by a human reviewing the agent's
PR; all tasks in the plan checked off or explicitly deferred.

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
- **Videos:** any stage that drives a browser records video automatically — the
  browser MCP launches with recording on and files land in `<stage-dir>/media/`.
  After the stage passes its postconditions the orchestrator uploads the attempt's
  videos to the artifact bucket as `<run-id>--<stage>--session-<n>.webm` (recording
  order) under an `attempt-<k>/` prefix — retries never overwrite earlier footage —
  and writes `media-manifest.json` beside the report; QA stages fail without a video
  from the current attempt. Reports link the deterministic bucket URL with a
  one-line description of what the video shows.
