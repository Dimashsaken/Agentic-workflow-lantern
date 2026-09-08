# Five parallel sessions — finishing the software factory (D18–D22)

**Status:** prompts, 2026-09-08. Each prompt below is meant to be pasted into its own
Claude Code session, all five at once. They close the gaps left open by D17
(`docs/plans/software-factory-alignment.md` §4, phases D–G) and add the factory's face.

## Step 0 — before you start any of them

1. **Commit the current working tree** (D16 + D17). Every session must branch from a
   commit that contains `tools/azure-runner/factory.py` and `PIPELINE_VERSION = "3"`.
2. Decide the story gate that is waiting: `feat-20260908-status-facts` at `story_signoff`
   (approve, reject, or ignore — it does not block the sessions).
3. Paste each prompt into a separate session started at the repo root. Each session
   creates its own worktree and branch (the prompt says how), so they cannot trample
   each other's checkouts.

## Rules every session follows (each prompt points here)

1. **Worktree + branch:** `git worktree add ../lantern-<slug> -b feat/factory-<slug> main`
   and work only there. Do not commit to `main`, do not push; leave the branch committed
   for the owner to merge with GitHub Desktop.
2. **Read first:** `AGENTS.md`, `docs/plans/software-factory-alignment.md` (§1 rules, §4
   phases), `docs/DECISIONS.md` D14–D17, `tools/azure-runner/README.md`,
   `tools/azure-runner/factory.py`, `workflow/PIPELINE.md`, and the tests nearest your work.
3. **Invariants you may not break:** Azure OpenAI only (D7); agents never write
   approvals and never merge (D6, gate integrity); the run folder is the only handoff
   channel (D4); every deliverable is checked for presence AND validity, never trusted
   from a report; typed JSON envelopes beside markdown; memory only through
   `append_memory`; second executions in a shared stage dir append to `report.md` and the
   last `Status:` line counts; a Windows laptop (Git Bash, in-process) and the Linux
   sandbox both run everything; keep each file's existing line endings.
4. **Tests:** stdlib `unittest` files runnable as `.venv/Scripts/python test_x.py` — no
   pytest, no network, no database unless the file says so (like `test_verification.py`).
   Every behaviour you add gets a test. Before finishing run every
   `tools/azure-runner/test_*.py` and `tools/mission-control/test_*.py`, then this repo's
   own gate — the commands in `lantern.toml` with `LANTERN_PYTHON` pointing at
   `tools/azure-runner/.venv/Scripts/python`.
5. **Decision record:** append your assigned decision (D18–D22) to `docs/DECISIONS.md` in
   the house style: dated, *why* over *what*, and what you deliberately did not do.
   Update `AGENTS.md`, `workflow/PIPELINE.md`, READMEs only in the sections you own.
   New roles start from `agents/_template/` (three files, seed memory, the render marker).
6. **Shared files:** edit only at the anchors listed in your prompt, with a few-line hook
   that calls into your own new module; never reformat, reorder, or "tidy" shared files.
   `ROLE_FOR_STAGE` additions go at the END of the dict with a `# D<n>` comment;
   argparse subparsers go at the END of the subparser block with a `# D<n>` comment.
7. **Real model calls** (gpt-5.6-sol via `.env`, cents each) are allowed to *prove* a
   flow at the end; unit tests must never need one.
8. **Report back** in your final message: branch name, tests run and their results, the
   decision number, the exact shared-file lines you touched, what is left.

## Ownership map

| Session | Owns outright | Shared-file hooks (anchor) | Decision |
|---------|---------------|----------------------------|----------|
| 1 builders | `tools/azure-runner/builders.py`, `test_builders.py`; in `orchestrator.py` the functions `finalize_coding`, `check_coding_handoff`, `coding_branch_name`, `coding_work_contract`; in `factory.py` `write_scope`/`check_write_scope`; `agents/coding/skills.md` §7–8; `agents/pre-coding/skills.md` §5 | `pipeline.py` `step_run`: the line `await execute(conn, run_id, stage, runner)` inside the auto-coding branch; the three `ROLE_FOR_STAGE[...]`/`.get(...)` lookups (route through a new `role_for_stage()` helper) | D18 |
| 2 review + merge | `tools/azure-runner/review.py`, `test_review.py`, `agents/reviewer/*` | `pipeline.py` `step_run`: the line `extra = await publish_coding_branch(conn, run_id)`; `pipeline.py` argparse: `babysit`; `ROLE_FOR_STAGE`: `03-coding.review`, `03-coding.fix` | D19 |
| 3 feedback + evals | `tools/azure-runner/intake.py`, `test_intake.py`, `tools/evals/**`, `workflow/DEBUG-LIFECYCLE.md`, `workflow/briefs/_BUG-TEMPLATE.md`, `agents/debug/*` | `pipeline.py` argparse: `bug`, `evals`; `ROLE_FOR_STAGE`: debug sub-phases; `lantern.toml` lint line | D20 |
| 4 agentic access | `tools/azure-runner/chat_service.py` (tools section), `tools/mission-control/chat.py`, `tools/slack-bridge/**`, `docs/CHAT.md`, `infra/ec2/lantern-slack-bridge.service` | `pipeline.py`: new `init-product` command + argparse | D21 |
| 5 Mission Control v3 | `tools/mission-control/app.py`, `ui.py`, `static/**`, its `test_*.py`, `docs/MISSION-CONTROL.md` | `orchestrator.py` and `pipeline.py`: one two-line hook each right after `result = results[-1]`; `factory.py`: append `write_trace()` at the end | D22 |

Merges: sessions 1 and 2 both touch `step_run`, on different lines; sessions 2 and 3 both
append to `ROLE_FOR_STAGE`; sessions 2, 3 and 4 all append argparse parsers. Those are
adjacent-line conflicts, trivial to resolve — resolve them by keeping both sides.

---

## Prompt 1 — Parallel scoped builders (D18)

```text
You are session 1 of 5 parallel sessions finishing Lantern's software factory. First read
docs/plans/software-factory-parallel-prompts.md (rules + ownership map; you own the
"1 builders" row and may only touch the shared anchors listed there), then AGENTS.md,
docs/plans/software-factory-alignment.md, docs/DECISIONS.md D14–D17, and
tools/azure-runner/factory.py, orchestrator.py (finalize_coding, check_coding_handoff,
coding_work_contract), pipeline.py (step_run, run_agent_stage, run_agent_stage_docker,
_publish_branch), test_coding_stage.py, test_factory.py. Work in your own worktree:
git worktree add ../lantern-builders -b feat/factory-builders main.

GOAL — Ray Fu's back-end/front-end engineers: in auto coding mode, stage 3 fans out into
N builders that run in parallel, each confined to its own write scope, merged by the host,
integrated once, then the single code_complete gate as today. Without builders in the
plan, behaviour is byte-for-byte today's single builder.

BUILD:
1. plan.json (factory.ENVELOPES "02-pre-coding") gains an optional `builders` list:
   [{name, write_scope: [globs], tasks: [task ids], criteria: [AC ids]}]. Validate in
   factory._check_plan: names unique and branch-safe ([a-z0-9-]), every task id assigned
   to exactly one builder, no glob listed under two builders. Update
   agents/pre-coding/skills.md §5: when to split (independent surfaces: api vs ui vs
   docs/tests), when not to (one surface, shared files), and the JSON example.
2. tools/azure-runner/builders.py: `run_coding(conn, run_id, stage, runner, execute)` —
   if the plan has no builders, `await execute(conn, run_id, stage, runner)` unchanged.
   Otherwise, for each builder run an execution with stage key `03-coding.<name>` (role
   coding) in batches of LANTERN_BUILDER_PARALLELISM (default 2, never above
   LANTERN_MAX_CONCURRENCY), each on its own branch `<run work branch>--<name>` (must stay
   inside CODING_BRANCH_PREFIXES), env LANTERN_BUILDER=<name>. Then `merge(run_id)` on
   the host: land each builder bundle in the mirror, create/reset the run's work branch
   from the base, `git merge --no-ff` each builder branch in plan order; a conflict fails
   the stage with the conflicting files and the rework hint. Then one integrator
   execution `03-coding.integrate` (role coding, scope = union of scopes, task = "make
   the merged branch green") which runs the normal factory.coding_turns gate loop;
   finalize as today so _publish_branch sees exactly one handoff for the run branch.
3. Builder awareness in the code you own: factory.write_scope(run_id) returns the
   builder's scope when LANTERN_BUILDER is set (fall back to the plan scope);
   coding_work_contract + factory.coding_gate_note tell the builder its name, tasks,
   criteria and scope; finalize_coding/check_coding_handoff write and verify per-builder
   handoffs under 03-coding/builders/<name>/ (handoff.json + branch.bundle) and the
   integrator's handoff at 03-coding/ as today; add role_for_stage(stage) in
   orchestrator.py that maps any "03-coding.<x>" to coding, and route the three
   ROLE_FOR_STAGE lookups through it.
4. The code_complete payload (`extra`) gains `builders: [{name, branch, commits,
   files_changed}]` — Mission Control (session 5) renders it; you do not touch app.py.
5. Docs: workflow/PIPELINE.md stage 3, AGENTS.md pipeline table row 3, azure-runner
   README ("Parallel builders"), agents/coding/skills.md §7 (you may be one builder of N;
   what the merge and the integrator expect), D18 in docs/DECISIONS.md.

TESTS (tools/azure-runner/test_builders.py, real git like test_coding_stage.py, no DB, no
model): plan validation (good, duplicate task, overlapping glob); branch naming inside the
D6 namespace; two non-overlapping builder bundles merged into one run branch; a conflict
(same file from two builders) fails with the file list; LANTERN_BUILDER scope resolution;
per-builder handoff dirs; batches respect the parallelism cap (fake execute).

DONE WHEN: all existing suites + yours pass, this repo's lantern.toml gate is green, D18
is written, and one real proof if feasible: a dogfood brief whose plan has two builders
(api + docs) runs stage 3 in-process on gpt-5.6-sol and ends at code_complete with two
builder handoffs and one merged branch (use the follow pattern in
docs/plans/software-factory-alignment.md / pipeline.py run --follow).
```

## Prompt 2 — Review loop and merge babysitter (D19)

```text
You are session 2 of 5 parallel sessions finishing Lantern's software factory. First read
docs/plans/software-factory-parallel-prompts.md (rules + ownership map; you own the
"2 review + merge" row and may only touch the shared anchors listed there), then AGENTS.md,
docs/plans/software-factory-alignment.md (§1 rules 3 and 9, §4 phase E), docs/DECISIONS.md
D6, D14–D17, tools/azure-runner/pipeline.py (step_run, _publish_branch, _open_or_find_pr,
publish_coding_branch, cmd_rework), orchestrator.py (check_postconditions,
build_instructions), factory.py, agents/post-coding/*, agents/coding/skills.md. Worktree:
git worktree add ../lantern-review -b feat/factory-review main.

GOAL — Boundary's rule "do not notify a human until the review bot is happy, at most
three rounds, then a human", and their agentic merge queue: after a human approves, keep
the branch mergeable until a human merges. Humans still merge; agents never do.

BUILD:
1. Role `reviewer` (agents/reviewer/charter.md, skills.md, memory.md from _template):
   reads story.json, plan.json, the branch diff (read-only checkout on the run branch,
   D15), gate.md, and the coding report; reviews for correctness, missing tests, plan
   conformance, and security smells (flag for `security`, do not decide); style only
   where it hides a bug. Output per round: 03-coding/review/round-<n>.md and
   review.json {kind:"review", run_id, round, verdict: approve|request_changes,
   findings:[{id, severity: blocker|major|minor|nit, file, line, summary, suggestion}],
   must_fix:[ids]} — register it in factory.ENVELOPES under stage key "03-coding.review"
   and validate it (ids unique, must_fix ⊆ findings, verdict approve ⇔ no blocker/major).
2. tools/azure-runner/review.py: `after_publish(conn, run_id, payload)` called from
   step_run right after publish_coding_branch: loop up to LANTERN_REVIEW_ROUNDS (default
   2): run execution "03-coding.review" (role reviewer); if approve → stop; else run a
   fix execution "03-coding.fix" (role coding, writable, continuing the run branch, the
   must_fix list injected as its task block, factory.coding_turns gate as usual), publish
   again (same branch, PR updated), next round. When rounds run out with
   request_changes, open code_complete anyway with the last review attached — the human
   decides; either way the human is only pinged at the end. Add the rounds and verdicts
   to the code_complete payload (session 5 renders it).
3. PR review comments: `post_pr_review(owner, name, pr_number, review)` posts the
   findings as one GitHub PR review (host side, the bot token, D6 allows review-role
   comments); no token → run folder only, never a failure.
4. Merge babysitter: `pipeline.py babysit <run-id>` and a daemon tick for runs that are
   past an approved code_complete and not yet merged: merge origin/<base> into the run
   branch in the mirror; clean → run the product's lantern.toml gate in a sandbox
   execution "03-coding.regate" (red → one fix execution as above) → push; conflict →
   write 03-coding/merge-conflict.md, log an event, post to LANTERN_ALARM_WEBHOOK, stop.
   Detect a merged PR through the GitHub API and record `branch_merged`; cadence
   LANTERN_BABYSIT_MINUTES (default 30). It never merges into the base.
5. Docs: PIPELINE.md stage 3 (review loop, babysitting), AGENTS.md row 3, azure-runner
   README, docs/AGENT-TOOLING.md matrix row for reviewer, D19.

TESTS (tools/azure-runner/test_review.py, no DB, no network, real git where useful):
review envelope validation; the loop with fake executions (approve on round 2 → one fix
execution; never approve → capped, gate opens with the review attached; must_fix reaches
the fix execution's task block); babysitter with real git (base moves ahead → branch
updated and gate re-run via a fake; conflict → stops with the file list); PR review
request body built correctly without network.

Coordination: session 1 changes how stage 3 executes (builders + an integrator) — your
hook runs after publish and must work whether or not builders exist. Add your
ROLE_FOR_STAGE keys at the end of the dict with a `# D19` comment.

DONE WHEN: all suites + yours pass, the lantern.toml gate is green, D19 written, and if
feasible one real proof: a dogfood run in auto mode goes through one review round on
gpt-5.6-sol and opens code_complete with review.json attached.
```

## Prompt 3 — Feedback trust pipeline and factory evals (D20)

```text
You are session 3 of 5 parallel sessions finishing Lantern's software factory. First read
docs/plans/software-factory-parallel-prompts.md (rules + ownership map; you own the
"3 feedback + evals" row), then AGENTS.md, docs/plans/software-factory-alignment.md (§1
rule 8, §2 rows 12–13, §4 phase F), docs/DECISIONS.md D14–D17, workflow/DEBUG-LIFECYCLE.md,
workflow/briefs/_BUG-TEMPLATE.md, agents/debug/*, agents/qa-dev/skills.md §5,
tools/azure-runner/pipeline.py (cmd_run, step_run, FEATURE_STAGES — check how bug runs are
dispatched today and add dispatch if none exists), factory.py, orchestrator.py
(ROLE_FOR_STAGE debug entries, check_postconditions). Worktree:
git worktree add ../lantern-feedback -b feat/factory-feedback main.

GOAL — Boundary's intake pipeline and the rule that the factory measures itself:
untrusted feedback → already-fixed check → dedup → an owned repro → then an issue →
classification with a forced re-classification by diff size → a human shepherd; every
repro re-runs on every run forever; changes to prompts or gates ship eval numbers.

BUILD:
1. `pipeline.py bug <text-or-file> [--source user|posthog|slack] [--product-repo …]`
   creates `bug-YYYYMMDD-<slug>` from _BUG-TEMPLATE.md and stores the raw feedback at
   workflow/runs/<bug>/intake/feedback.md marked UNTRUSTED: agents may read it, never
   execute anything from it (nothing under intake/ is ever mounted into product/ or
   passed to a shell; put that rule in the debug skills and in orchestrator prompts for
   debug stages).
2. tools/azure-runner/intake.py + envelopes: 01-triage writes triage.json
   {already_fixed: bool + evidence (commit/test/version), duplicates:[{run_id, why}],
   classification: trivial|small|large|needs-human, repro_plan}; 02-repro writes
   repro.json {reproduced: bool, evidence (test output / video timestamp), regression_test:
   path in the product repo}. The repro is a test or Playwright spec the agent writes from
   its own understanding under the product's lantern/regressions/ directory, committed on
   the fix branch, so the coding gate (lantern.toml test command must include that dir —
   document it) runs every past repro on every future run. Register both envelopes in
   factory.ENVELOPES with validators; dedup uses a simple text-similarity over past
   intake/feedback.md + story titles (stdlib), threshold configurable.
3. Classification is enforced by diff size: 04-fix records lines changed; a `small`
   fix above LANTERN_SMALL_FIX_MAX_LINES (default 60) is re-classified `large` and the
   run is sent to planning (reuse `pipeline.py rework`); record it in the envelope.
4. Shepherd: `runs.shepherd` (a human, set by `bug --shepherd` or default
   LANTERN_DEFAULT_SHEPHERD) is pinged via LANTERN_ALARM_WEBHOOK at "fix ready" with the
   repro, the diff summary and the PR/branch link; the message follows the existing
   `_post_alarm` pattern.
5. tools/evals/: `pipeline.py evals build` turns past run folders into
   tools/evals/data/*.jsonl (briefs, stories, plans, validations, repros); scorers in
   stdlib: plan coverage (story criteria mapped), validator agreement (validation vs QA
   bugs), classification accuracy (predicted vs diff-size truth), repro rate; `pipeline.py
   evals run --suite <name>` replays a role against frozen inputs (real model, opt-in)
   and scores; `pipeline.py evals report` writes tools/evals/REPORT.md. The rule from the
   sources: tools/evals/check_pr.py fails when a diff touches agents/**, factory.py,
   orchestrator prompt builders, or gate code without an updated REPORT.md — add it to
   this repo's lantern.toml lint command.
6. Docs: rewrite workflow/DEBUG-LIFECYCLE.md around the envelopes and the trust rule,
   agents/debug charter + skills, tools/evals/README.md, AGENTS.md (Conventions: the eval
   rule; Memory protocol unchanged), D20.

TESTS (test_intake.py + tools/evals/test_evals.py, no DB, no model): bug run creation and
the UNTRUSTED marker; triage/repro envelope validation; the re-classification rule;
dedup on fixtures (a duplicate found, a near-miss not); scorers on fixture data with
known answers; check_pr.py on fixture diffs (blocks without REPORT.md, passes with it).

DONE WHEN: all suites + yours pass, the lantern.toml gate is green (with your lint
addition), D20 written, and if feasible one real proof: `pipeline.py bug` on a small real
defect in this repo runs triage on gpt-5.6-sol and produces a valid triage.json.
```

## Prompt 4 — Agentic access: run the factory from chat and Slack (D21)

```text
You are session 4 of 5 parallel sessions finishing Lantern's software factory. First read
docs/plans/software-factory-parallel-prompts.md (rules + ownership map; you own the
"4 agentic access" row), then AGENTS.md ("Two ways to use an agent", gates), docs/CHAT.md,
docs/DECISIONS.md D11, D13, D14–D17, docs/plans/symphony-alignment.md §4 Phase 1 (the
Slack front door design) and §3 (why no gateways), tools/azure-runner/chat_service.py
(the lantern orchestrator agent and its read-only tools, custom agents, sessions),
pipeline.py (cmd_run, cmd_decide, cmd_rework, cmd_retry, cmd_set_product, parse_brief_*),
tools/mission-control/chat.py, workflow/briefs/_TEMPLATE.md. Worktree:
git worktree add ../lantern-access -b feat/factory-access main.

GOAL — IndyDevDan's "an agent operates the factory" and Boundary's dispatcher that
listens to Slack: start runs, point them at repos, decide gates as the human, rework and
retry — from the Chat tab and from Slack — fail-closed, and a one-command install of the
factory into a product repo.

BUILD:
1. Write tools for the `lantern` chat agent in chat_service.py: start_run(brief_path or
   brief_markdown, product_repo, base_branch, coding_mode), set_product, rework, retry,
   decide_gate(run_id, gate, approve|reject, note). Rules: every call logs an event with
   the authenticated web user (the session's `by`), never the agent; decide_gate,
   rework and start_run require an explicit confirmation turn — the agent shows a
   decision card, the human types a confirmation, and the SERVER verifies the
   confirmation phrase in the most recent human turn before executing (the model cannot
   self-confirm; a missing confirmation returns guidance, not an action). Reuse the
   pipeline.py functions; do not duplicate their logic.
2. Brief composer: start_run from a rough idea → the agent fills workflow/briefs/<slug>.md
   from the template, asks for missing fields (product repo, coding mode, must-haves),
   validates with parse_brief_product/parse_brief_coding_mode before creating the run.
3. Slack front door, tools/slack-bridge/ (Bolt for Python, Socket Mode, no public URL):
   `@lantern <idea>` opens a run and a thread per run (thread_ts as the correlation key
   stored on the run); gate notifications post to the thread with Approve/Reject Block
   Kit buttons; button handlers ack within 3 s and write approvals through
   pipeline.cmd_decide with by="slack:<user>", allowed only for users in
   LANTERN_SLACK_APPROVERS; every other user gets "not an approver". Rework/retry as slash
   commands. systemd unit in infra/ec2/lantern-slack-bridge.service and a README with the
   Slack app manifest.
4. `pipeline.py init-product <path>`: detects the stack (package.json → npm test,
   pyproject/setup → pytest, go.mod → go test, Cargo.toml → cargo test), writes
   lantern.toml from workflow/templates/lantern.toml with real commands, appends a short
   "built by the Lantern software factory" block to the product's AGENTS.md (create if
   absent, never overwrite existing text), and prints how to point a run at it.
5. Mission Control chat UI (tools/mission-control/chat.py only): render confirmation
   cards and run/gate links; app.py belongs to session 5 — do not edit it.
6. Docs: docs/CHAT.md (write tools, confirmation protocol, identity), tools/slack-bridge/
   README.md, AGENTS.md "Two ways to use an agent" amended (consults can act, with
   confirmation and the human's identity), symphony plan Phase 1 marked done, D21.

TESTS (tools/azure-runner/test_chat_tools.py, tools/slack-bridge/test_bridge.py,
test_init_product.py; no network, fake sessions/clients): confirmation enforced server
side (no phrase → no action; phrase in an older turn → no action); events carry the human
identity; the composer's brief parses; Slack handlers with a fake client (approver
allowed, non-approver refused, ack timing); init-product on fixture repos for each stack.

DONE WHEN: all suites + yours pass, the lantern.toml gate is green, D21 written, and if
feasible one real proof: from the Chat tab, start a dogfood run and approve its
story_signoff with the confirmation flow, on gpt-5.6-sol.
```

## Prompt 5 — Mission Control v3: the factory's face (D22)

```text
You are session 5 of 5 parallel sessions finishing Lantern's software factory; you build
its UI. First read docs/plans/software-factory-parallel-prompts.md (rules + ownership
map; you own the "5 Mission Control v3" row), then docs/MISSION-CONTROL.md, docs/CHAT.md,
tools/mission-control/app.py, ui.py, the test_*.py there (the fake-pool route-test
pattern), tools/azure-runner/pipeline.py (status_payload, render_runboard, cmd_usage,
est_cost_usd), schema.sql (stage_executions ledger columns, approvals, events,
artifacts), factory.py (ENVELOPES, gate.json), and docs/plans/software-factory-alignment.md
§1 rule 5 and §2 row 10 — the usability bar is IndyDevDan's dashboard (sessions as swim
lanes, compiled prompts, per-phase cost, restart from here) and HumanLayer's workspace
(one glance = what runs, what needs me, what it cost; one click = act). Worktree:
git worktree add ../lantern-ui -b feat/factory-ui main. Keep the stack: FastAPI,
server-rendered HTML, a small vanilla-JS layer over the existing SSE pattern, no build
step, light and dark, keyboard-friendly, usable on a phone.

BUILD:
1. Home = Inbox + Board, tightened: each gate card leads with the artifact being decided
   (story.md for story_signoff, option PNGs for ux, task-plan for plan, PR + gate.md +
   review rounds + builders for code_complete, validation table before staging), STALE
   badges as today, keyboard shortcuts (j/k move, a approve, r reject with a note).
2. Run page = swim lanes: one lane per stage execution in time order (scout, story,
   diverge, design, plan, builders, review rounds, QA, review, validate, security,
   staging) with duration, model tier, tokens and estimated cost from the ledger, status
   colour, attempt markers, gate diamonds between lanes; click → execution drawer.
3. Execution drawer: the compiled system prompt and kickoff, the tool-call timeline
   (name, args snippet, result size, seconds), the report rendered, the envelope as
   pretty JSON with its validation result, gate.md when present, the memory entries it
   appended, usage/cost, and actions: retry, rework-to (server-side POSTs calling the
   pipeline.py functions; approvals stay human).
4. Traceability view per run: story criteria × plan tasks × coding commits × QA charter
   sections × validation verdicts as a matrix with status chips — the contract at a glance.
5. Factory catalog page (read-only, from files + env): roles (mission one-liner, tier,
   tools), stages and gates, the model stack (tiers → deployments, effort), each product's
   lantern.toml quality commands, eval numbers if tools/evals/REPORT.md exists, builders if
   the plan declares them.
6. Cost page: per run, per day, per model; tripwire status (reuse cmd_usage logic).
7. Trace capture (the only edits outside mission-control): append
   `write_trace(run_id, stage, execution_key, instructions, kickoff, results)` to the end
   of tools/azure-runner/factory.py — writes <stage-dir>/trace/<execution_key>.json with
   the compiled prompt, the kickoff, tool calls extracted from each result's new_items
   (name, truncated args, truncated output, order), and usage — and call it with one
   two-line hook right after `result = results[-1]` in orchestrator.py main() and in
   pipeline.run_agent_stage. REDACT before writing: drop the "# QA target" section and
   mask anything that looks like a password or token; a trace must never carry a secret.
8. Docs: docs/MISSION-CONTROL.md v3 (what each page answers, the keyboard map, the trace
   file), D22.

TESTS (tools/mission-control/test_*.py in the fake-pool style; tools/azure-runner/
test_trace.py): lane math and ordering from fixture execution rows; the drawer from a
fixture trace; the traceability matrix from fixture envelopes; the catalog from fixture
files; cost aggregation; redaction (a QA password never reaches the trace); every route
renders with an empty database. Then run the app (.claude/launch.json has the
mission-control config; set LANTERN_WEB_USERS locally) and verify each page in the
browser at desktop and phone widths, light and dark; attach screenshots in your report.

DONE WHEN: all suites + yours pass, the lantern.toml gate is green, D22 written, and the
screenshots show every page with real data from the local Postgres (the restored demo
runs plus feat-20260908-status-facts).
```

---

## After these five

What still separates Lantern from the reference factories, on purpose or for later:
the dev-environment layer (per-run preview environments, identity provisioning, warm
sandbox pools — alignment plan Phase G), multi-repo coordination, and model breadth
(D7 keeps the fleet on Azure OpenAI; the sources mix providers). Everything else the
three sources describe will exist: story and research before planning, code gates
between agents, scoped parallel builders, bounded review loops, a merge queue, a trust
pipeline for feedback, evals on the factory, an agent that operates the factory, and a
UI that shows what ran, what it cost, and what needs a human.
