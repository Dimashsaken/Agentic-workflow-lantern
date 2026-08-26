# The next three sessions — foundation and groundwork

Written 2026-08-26, after the first real agent runs. Each section is a **prompt to paste
at the start of a fresh session**. They are ordered by dependency: session 1 makes the
verification trustworthy, session 2 makes it concurrent, session 3 makes it real for
five developers. Do not reorder — session 2's concurrency is unsafe without session 1.

Context every session should load first: `AGENTS.md`, `docs/DECISIONS.md` (D8, D9, D10),
`docs/ORCHESTRATION.md`, and `workflow/RUNBOARD.md`.

---

## Session 1 — Make the pipeline's verification sound

> **Prompt:**
>
> Read `AGENTS.md`, `docs/DECISIONS.md` D10, and `docs/ORCHESTRATION.md` "The execution
> plane". The pipeline's trustworthiness rests on three postconditions, and two of them
> are unsound or will become unsound. Fix that, because everything else is blocked on it.
>
> 1. **Move role memory into Postgres.** Add a `role_memory` table (role, run_id, stage,
>    entry, created_at). Agents append through a new `append_memory` function tool, not
>    by editing `agents/<role>/memory.md`. Change `check_postconditions` from
>    `memory_now == memory_before` — which another concurrent run can satisfy on this
>    run's behalf — to "this stage execution inserted at least one row". Add a
>    consolidation command that renders the markdown file from the table so humans and
>    the system prompt keep reading one file.
> 2. **Stop agents writing `RUNBOARD.md`.** It is derived data Postgres already holds.
>    Render it from the DB (a `pipeline.py runboard` command plus the existing Mission
>    Control board), drop it from the postcondition set, and update `AGENTS.md` so the
>    contract says two written postconditions plus a derived view.
> 3. **Prove both with a test.** Simulate two concurrent executions of the same role and
>    show that the old check passes a stage that wrote nothing while the new one fails
>    it. That test is the artifact that matters — keep it.
>
> Then re-run `orchestrator.py feat-20260825-role-health 01-ui-ux.diverge` and confirm
> the stage still passes end to end. Update D10's "blocking prerequisite" note to say it
> is done, and record what you learned in `agents/ui-ux/memory.md` only if it is durable.
>
> Do not start containerisation in this session.

**Done when:** two concurrent runs of one role cannot satisfy each other's postconditions,
`RUNBOARD.md` is generated rather than hand-edited, and a stage run still passes.

---

## Session 2 — One sandbox per stage execution

> **Prompt:**
>
> Read `docs/DECISIONS.md` D10 and confirm session 1's prerequisite is done (role memory
> in Postgres). Now give each stage execution its own isolated shell, per the CTO's
> requirement: one always-on AWS VM running Docker, one ephemeral container per stage.
>
> 1. **Build the agent sandbox image.** Python + the azure-runner deps + Playwright
>    browsers + `gh`/git. It runs exactly one stage and exits:
>    `python orchestrator.py <run-id> <stage>`.
> 2. **Give it a per-run workspace.** `/work` with a fresh clone of the product repo at
>    the run's branch. The Lantern run folder is mounted or synced from object storage —
>    decide which and write down why. Nothing from one run may be visible to another;
>    the stale-export bug from 2026-08-26 must be structurally impossible.
> 3. **Turn the daemon into a dispatcher.** It claims with the existing
>    `FOR UPDATE SKIP LOCKED` query and then `docker run --rm` instead of executing
>    in-process. Add an explicit concurrency cap (start at 3), a wall-clock timeout per
>    stage, CPU/memory limits, and short-lived scoped credentials rather than a shared
>    `.env` baked into the image.
> 4. **Prove isolation, not just concurrency.** Run three stages at once that all write
>    to the same product repo path and show they do not corrupt each other. Then kill a
>    container mid-stage and show the run recovers on retry with no residue.
>
> Update `infra/ec2/README.md` with the real instance size you settled on and the
> concurrency cap. If you discover the cap needs to be lower than 3 on the current
> instance, say so plainly rather than sizing up silently.

**Done when:** three stages run concurrently in separate containers without touching each
other's filesystem, a killed container leaves no residue, and the cap is documented.

---

## Session 3 — Five developers, and a first complete run

> **Prompt:**
>
> Read `docs/DECISIONS.md` D10 and `docs/AGENT-TOOLING.md` §2. The system now runs
> isolated stages concurrently. Make it genuinely multi-developer, then drive one feature
> all the way through for the first time.
>
> 1. **Per-developer runner identity.** Extend the `runner` concept to
>    `workstation:<dev>` and route `01-ui-ux.design` to the laptop of the developer who
>    owns the run (`runs.created_by`). Update the claim query, the `runners` heartbeat
>    table, and Mission Control's "needs the design workstation" notice so it names the
>    developer instead of being global.
> 2. **Write the workstation setup doc.** What a developer installs (Paper Desktop, their
>    own Paper Pro seat, the venv, Tailscale to reach Postgres), what they set
>    (`LANTERN_RUNNER`, `LANTERN_PAPER_FILE_ID` pointing at an agent-owned file in their
>    own workspace), and the one command they run. Keep it under a page.
> 3. **Scope Mission Control to people.** Gates should surface to the developer who owns
>    the run, with a shared board still visible to everyone. Do not add roles or
>    permissions beyond that yet.
> 4. **Then do the thing the repo has never done: one complete run.** Take
>    `feat-20260825-role-health` from its `ux_signoff` gate through pre-coding, and go as
>    far as the pipeline will honestly carry it. Every stage that fails, fix the cause
>    rather than the symptom — that is how the last six defects were found.
>
> Write a decision record for anything you change about the pipeline's shape, and a short
> honest note in `docs/plans/` about where the first full run actually stopped and why.

**Done when:** two developers can have design stages in flight at once on their own Paper
accounts, and one feature has travelled further than stage 1 with every gate honoured.

---

## What not to do in these three sessions

- **Do not add pipeline stages or roles.** Seven stages and eight roles is already more
  than has been exercised end to end once.
- **Do not build the Slack/GitHub gate front-ends yet.** The `approvals` row plus Mission
  Control is enough until a real run has waited at a real gate.
- **Do not tune agent prompts to make a stage pass.** Every prompt fix in this repo so far
  came from a *demonstrated* failure with evidence on disk. Keep that discipline: find the
  failure first, then fix the cause.
- **Do not trust a green stage without opening its artifacts.** Run 3 on 2026-08-26 exited
  zero while fabricating its entire output. `check_claimed_artifacts` catches that class
  now, but only for what it knows to check.
