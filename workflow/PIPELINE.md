# The Feature Pipeline

Every feature moves through these stages in order. Stages never run out of order and
never skip; a stage may be marked `WAIVED` in its report only by Justin.

The handoff medium is the **run folder**: `workflow/runs/<run-id>/`. Each stage reads
everything upstream and writes its own `<stage-dir>/report.md` using
`workflow/templates/stage-report.md`. If it's not in the run folder, it didn't happen.

```
brief ──▶ 00 story ──▶ 01 ui-ux ──▶ 02 pre-coding ──▶ 03 coding ──▶ 04 qa-dev ──▶ 05 post-coding + validate ──▶ 06 security ──▶ [staging deploy] ──▶ 07 qa-staging ──▶ [prod]
            ▲ gate:      ▲ gate:       ▲ gate:            ▲ code gate:    │ gate:            ▲ a verdict per criterion       ▲ gate:                                 ▲ gate:
            approve      pick option   approve schema     tests green +   no sev-1/2 bugs    (fail → rework to 03)           no high-risk findings                   Justin sign-off
            criteria                                      write scope
```

---

## Stage 0 — Research & story (`researcher` → `story` agents) → `00-story/`

Two executions in one stage dir (D17). Ray Fu's agents 1 and 2: map the code before
anyone plans against it, then write the contract everything else is checked against.

- `00-story.scout` (EC2, `researcher`, reasoning tier): read-only. Opens the code the
  feature will touch and writes `research.md` + `research.json` — patterns to imitate
  (exemplar paths), similar features to reuse, risks with severity, conventions, likely
  files. **Every path cited must exist in the checkout** (the harness verifies).
- `00-story.write` (EC2, `story`, reasoning tier): reads the brief + research and writes
  `story.md` + `story.json` — one user story, acceptance criteria `AC-1…AC-n` (each one
  observable, one behaviour, with edge cases), non-goals. Appends its section to the
  scout's `report.md`.

**In:** the feature brief + the product repo (read-only).
**Out:** `research.md`, `research.json`, `story.md`, `story.json`, `report.md`.
**Gate:** `story_signoff` — Justin or the assigned developer approves the criteria in
Mission Control (the story renders inline). Reject with a note → `retry` re-enters the
story execution with the same session memory. `HITL: required`.

## Stage 1 — UI/UX (`ui-ux` agent) → `01-ui-ux/`

Runs as **two executions with different runners** (D9, `docs/plans/ui-ux-agent-paper.md`):

- `01-ui-ux.diverge` (EC2, fast model): map the user flow, generate 5–10 low-fi HTML
  skeletons on named structural axes into `divergence/`, judge-score them against the
  brief, keep the best 2–3.
- `01-ui-ux.design` (design workstation, Paper MCP): converge the survivors into Paper
  artboards grounded in `design/design-system.md`, run the screenshot-critique loop
  (≤3 iterations per option, layout pass separate from style pass per
  `design/critique-checklist.md`), export 2x PNGs, write `handoff.json`.
  **Design mode `html` (D25):** the same execution runs on the ec2 runner with the
  browser instead of Paper — the survivors become self-contained HTML prototypes under
  `01-ui-ux/prototype/`, critiqued from browser screenshots, whose final 2x screenshots
  are the option PNGs; `handoff.json` says `design_mode: html` and names each prototype
  instead of `jsx/`. Chosen per run: `- **Design mode:**` in the brief,
  `pipeline.py run --design-mode`, or `pipeline.py set-design-mode <run-id> html` for a
  run parked at the design stage without a workstation. Default stays `paper`.

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
the developer), `plan.json` (D17: tasks → acceptance criteria, `write_scope` globs the
builder may change, `schema_changes`, `hitl_required`, `deferred_criteria` with reasons —
every story criterion is planned or explicitly deferred).
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
  **The gate runs as code (D17):** after the agent's turn the product's `lantern.toml`
  `[quality]` commands (test / lint / typecheck / build) run from the product root, plus
  a check that every changed path is inside the plan's `write_scope`. Failures — only
  failures — go back to the agent for at most `LANTERN_FIX_ROUNDS` rounds (default 3);
  still red = the stage fails and nothing is handed off. `gate.json` + `gate.md` in the
  stage dir are the record; the handoff itself is refused if a commit leaves the scope.

  **Parallel scoped builders (D18) — only when the plan asks for them.** If the approved
  `plan.json` carries a `builders` list (`[{name, write_scope, tasks, criteria}]`, see
  `agents/pre-coding/skills.md` §5a), stage 3 fans out:

  1. one execution per builder, `03-coding.<name>`, `LANTERN_BUILDER_PARALLELISM` at a
     time (default 2, never above the executor's own concurrency — 1 in-process, where
     executions share one process env). Each runs on its own branch
     `<run branch>--<name>` from a single shared start point, confined to its own
     `write_scope`, with its own quality gate and fix loop, writing
     `03-coding/builders/<name>/` (report, gate, handoff, bundle). Builders cannot see
     each other's branches: they build against the contract the plan wrote down.
  2. the **host** merges: it verifies each builder's bundle, lands it in the mirror,
     resets the run's branch to the start point and `git merge --no-ff`s each builder in
     plan order. A conflict fails the stage with the conflicting file list and sends the
     run back to planning — two builders sharing a file means the split was wrong.
     `03-coding/builders.json` + `builders.md` are the record.
  3. one **integrator** execution, `03-coding.integrate`, on the merged branch with the
     union of the scopes and one task: make it green. It runs the normal gate + fix loop
     and its handoff is the stage's handoff, so `03-coding/` still carries exactly one
     branch for the host to push. Then the single `code_complete` gate as always, with
     the builder list in its payload.

  Without a `builders` list none of this happens and stage 3 is one builder, unchanged.
  **Then the review bot (D19):** once the host has published the branch, the `reviewer`
  runs as `03-coding.review` — correctness, missing tests, plan conformance, security
  smells (flagged for `security`, never decided) — and writes `03-coding/review/round-<n>.md`
  + `review.json` (validated: approve ⇔ no blocker/major; `must_fix` ⊇ every blocker/major).
  `request_changes` → a fix execution `03-coding.fix` (the `coding` role, writable, same
  branch, the `must_fix` list as its task) → the branch is published again (same PR) →
  the next round. At most `LANTERN_REVIEW_ROUNDS` reviews (default 2); approve, the cap,
  or a failed execution all end the loop, and only then is a human pinged. Each round is
  also posted as one PR review from the bot identity when the host has a token.
**Out:** the branch; `report.md` listing commits, deviations from the plan, and known
gaps for QA to probe; in auto mode also `handoff.json` + `branch.bundle` (the evidence)
and `pr.md` (where it went); `review/` with every round's review (D19); with builders,
additionally `builders/<name>/` per builder and `builders.json` + `builders.md` for the
merge.
**Gate:** code-complete declared — by the developer, or by a human reviewing the agent's
PR with the last review attached; all tasks in the plan checked off or explicitly deferred.
**After approval — the merge babysitter (D19):** every `LANTERN_BABYSIT_MINUTES` (30) the
daemon, or `pipeline.py babysit <run-id>`, keeps an approved, unmerged branch mergeable:
a trial merge of the base on the host — a conflict stops with `03-coding/merge-conflict.md`,
an event and an alarm; clean → the merge commit is pushed to the branch, the product's
`lantern.toml` quality commands re-run as code (`03-coding.regate`, no agent turn), and
only a red result spends one fix execution. A merged PR (GitHub API, or git ancestry for
other remotes) records `branch_merged` and ends it. It never merges into the base.

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

**Then `05-post-coding.validate` (`validator` agent, D17):** reads `story.json`,
`plan.json`, the coding handoff + diff, the QA charter / bugs / media manifest and the
review above, and gives every acceptance criterion exactly one verdict — `covered` /
`missing` / `skipped` / `off-spec` / `insecure` — with evidence a human can open.
**Out:** `validation.md`, `validation.json` (verdict computed from the statuses:
`pass` only when everything is covered and `fix_now` is empty); appends its section to
`report.md`. **Gate:** verdict `pass`; `fail` stops the run here with the `fix_now` list —
fix on the branch, then `pipeline.py rework <run-id> --to 03-coding` (auto mode) or
`retry` after the developer pushed the fix.

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
  Mechanically (D17): `pipeline.py rework <run-id> --to 03-coding` sends a failed or
  waiting run back to the builder (same branch, same session memory, fresh attempt);
  inside the coding stage the quality gate feeds failures back for `LANTERN_FIX_ROUNDS`
  rounds before a human sees it, and the review bot's `must_fix` list goes to a fix
  execution for `LANTERN_REVIEW_ROUNDS` rounds before a human sees `code_complete` (D19).
- **Envelopes are the contract (D17).** Stages 0, 2 and 5b write a typed JSON envelope
  beside their markdown (`research.json`, `story.json`, `plan.json`, `validation.json`;
  exact shapes in each role's skills). The orchestrator validates presence AND validity,
  cross-checked against the story, so a claim never stands in for a deliverable. Second
  executions in a shared stage dir (`00-story.write`, `05-post-coding.validate`) append
  their section to the existing `report.md`; the last `Status:` line is the one that
  counts.
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
