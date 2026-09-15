# azure-runner — the fleet runtime (Azure OpenAI only)

Single model provider by decision (D7): **Azure OpenAI** — the org's startup credits.
Two harnesses, both OpenAI-native, both loading the same `agents/<role>/` knowledge
and `AGENTS.md` contract:

| Harness | Runs | Where |
|---------|------|-------|
| **OpenAI Agents SDK** (`orchestrator.py`) | pipeline stages 1–2, 4–7 + debug lifecycle | EC2 (workstation for Paper-dependent ui-ux work) |
| **Codex CLI** (`codex-config.example.toml`) | stage 3 coding | developer laptops; `codex exec` on EC2 for headless repo tasks |

## Env-var contract (never commit values — see `.env.example`)

```
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
AZURE_OPENAI_API_KEY=<from SSM>
AZURE_OPENAI_API_VERSION=<current GA version>

# Model stack (D16/D26) — three tiers, each one Azure deployment of a GPT-5.6 size.
# Only REASONING is required: CODING falls back to FAST, FAST to REASONING. A tier may
# only name a deployment that exists (`smoke_test.py <name>`), see "Model stack" below.
LANTERN_MODEL_REASONING=gpt-5.6-sol     # judgement: research, scoping, planning, review, validation, security, debug, ui-ux design
LANTERN_MODEL_CODING=gpt-5.6-terra      # building: stage-3 builders, integrator, review fixes (auto mode)
LANTERN_MODEL_FAST=gpt-5.6-luna         # labour: QA charter execution, ui-ux divergence
LANTERN_TIER_OVERRIDES=                 # experiments: "<stage-key|role>=<tier>,…" e.g. qa-dev=coding
# Reasoning effort per tier (minimal|low|medium|high|xhigh, or 'default' to send none).
# Defaults are token-max: reasoning=high, coding=high, fast=medium.
LANTERN_EFFORT_REASONING=high
LANTERN_EFFORT_CODING=high
LANTERN_EFFORT_FAST=medium
LANTERN_EFFORT_CHAT=            # optional override for interactive consults (Chat tab, `ask`)
# Per-deployment rates so the ledger prices each tier at its own rate (.env.example has
# the 2026-09-14 numbers: sol 4/0.40/20 promo, terra 2/0.20/12, luna 0.20/0.02/1.20).
LANTERN_PRICE_JSON=

# Runner affinity (docs/plans/ui-ux-agent-paper.md):
LANTERN_RUNNER=ec2                               # 'workstation' on the design machine
LANTERN_PAPER_MCP_URL=http://127.0.0.1:29979/mcp # Paper Desktop's local MCP endpoint

# Execution plane (D10/D12 — EC2 dispatcher only; laptops keep the inprocess default):
LANTERN_EXECUTOR=inprocess          # 'docker' = one sandbox container per stage
LANTERN_MAX_CONCURRENCY=            # default 3 under docker, 1 inprocess
LANTERN_STAGE_TIMEOUT_MIN=45
LANTERN_FIX_ROUNDS=3                # D17: quality-gate fix rounds before a red coding stage fails
LANTERN_BUILDER_PARALLELISM=2       # D18: scoped builders at once; capped by MAX_CONCURRENCY
                                    #   (and by 1 in-process, where executions share env)
LANTERN_REVIEW_ROUNDS=2             # D19: review-bot rounds before a human sees code_complete (0 = off)
LANTERN_MODEL_RETRIES=3             # D23: retries on a throttled/transport model failure (0 = off)
LANTERN_MAX_TURNS=                  # D23: fleet-wide turn ceiling; per role LANTERN_MAX_TURNS_<ROLE>
                                    #   (defaults: coding 400, every other role 120)
LANTERN_BABYSIT_MINUTES=30          # D19: merge-babysitter cadence for approved, unmerged branches
LANTERN_SMALL_FIX_MAX_LINES=60      # D20: a trivial/small bug fix above this many changed lines is re-classified large
LANTERN_DEDUP_THRESHOLD=0.45        # D20: similarity at/above which a past run is a dedup candidate
LANTERN_DEFAULT_SHEPHERD=           # D20: the human pinged at fix-ready when `bug --shepherd` was not given
LANTERN_BUG_CODING_MODE=human       # D20: default coding mode for bug runs
LANTERN_SANDBOX_CPUS=1.5
LANTERN_SANDBOX_MEMORY=2500m
LANTERN_SANDBOX_IMAGE=lantern-sandbox
LANTERN_SANDBOX_DATABASE_URL=       # DB URL as containers see it (default: host.docker.internal)
LANTERN_PLAYWRIGHT_MCP=             # MCP launch cmd; the sandbox image pins its own
LANTERN_DESIGN_MODE_DEFAULT=paper   # D25: stage-1 convergence when a brief says nothing — 'html' on a box without Paper
LANTERN_MODEL_TIMEOUT_S=600         # per-request model timeout (raise for long reasoning turns)

# QA stages (P0.1 — dispatcher host env; containers see uniform QA_BASE_URL/QA_USER/QA_PASS):
LANTERN_QA_DEV_BASE_URL=            # + LANTERN_QA_DEV_USER / LANTERN_QA_DEV_PASS   (SSM /lantern/qa/dev/*)
LANTERN_QA_STAGING_BASE_URL=        # + LANTERN_QA_STAGING_USER / LANTERN_QA_STAGING_PASS
LANTERN_ARTIFACT_BUCKET=            # S3 bucket name; unset = media stays local (dev)

# Product repository (P0.3 — the code the run implements; per-run target overrides these):
LANTERN_PRODUCT_REPO=               # fallback default when a brief/run names none
LANTERN_PRODUCT_BRANCH=main         # fallback default base branch
LANTERN_WORKSPACE_ROOTS=            # dirs the repo picker may scan (D15) - a
                                    # boundary: unset offers nothing, not everything
LANTERN_CODING_BRANCH_PREFIXES=feat,fix,proto   # what agents may push to (D6)
LANTERN_PRODUCT_MIRROR_DIR=         # host mirror cache (default ~/.lantern/product-mirrors)
GITHUB_LANTERN_BOT_TOKEN=           # HOST-ONLY: authenticates the mirror fetch. Never
                                    #   allowlisted into a sandbox, never written into
                                    #   the mirror config that gets mounted.

# Token ledger + spend tripwires (P0.4 — `pipeline.py usage` / `usage-check`):
LANTERN_PRICE_IN_PER_M=4            # $/1M input tokens — PROVISIONAL until Azure
LANTERN_PRICE_CACHED_IN_PER_M=1     #   invoice lines confirm the deployment rates
LANTERN_PRICE_OUT_PER_M=20
LANTERN_DAILY_SPEND_ALARM_USD=500   # rate tripwire (raised from 50 on 2026-09-11: full auto-mode runs on real products)
LANTERN_CREDIT_POOL_USD=25000       # pool tripwire: alarms at 25/50/75% drawn
LANTERN_POOL_SPENT_OFFSET_USD=0     # est. credits burned before the ledger existed
LANTERN_ALARM_WEBHOOK=              # Slack-compatible webhook; unset = journal only
```

### Model stack

The runner reasons about three **tiers** (`tier_for()` in `orchestrator.py` is the only
place routing policy lives) and each tier names one Azure deployment. The deployments
are the three sizes of OpenAI's GPT-5.6 family as Azure sells them (Foundry catalog,
version 2026-07-09) — not org labels, and the order is **sol > terra > luna**:

| Tier | Deployment | Size | Azure rate, $/1M tokens (in / cached / out) | Runs |
|---|---|---|---|---|
| `reasoning` | `gpt-5.6-sol` | frontier — "the most advanced reasoning" | 5 / 0.50 / 30; promo **4 / 0.40 / 20** 2026-09-01 → 11-30 | research, story, ui-ux design, pre-coding, review bot, post-coding, validator, security, debug, consults |
| `coding` | `gpt-5.6-terra` | mid — "balanced … competitive with GPT-5.5 at a lower cost" | 2 / 0.20 / 12 | stage-3 auto mode: builders, integrator, review fixes |
| `fast` | `gpt-5.6-luna` | cheap — "the fastest and most affordable" | 0.20 / 0.02 / 1.20 | QA charter execution (dev, staging, regression), ui-ux divergence |

Sol plans and reviews, terra builds, luna does the volume work — the planner-strong /
builder-mid / labour-cheap split of the software-factory reference designs, with the
survey in `docs/plans/software-factory-alignment.md` §6 and the decision in
`docs/DECISIONS.md` D26. The execution-by-execution table is in `workflow/PIPELINE.md`
("Which model runs which execution"). `LANTERN_TIER_OVERRIDES` re-tiers one execution
or role for an experiment (`qa-dev=coding` runs dev QA on terra); `LANTERN_PRICE_JSON`
carries the three rates so the ledger prices each tier at its own rate (`.env.example`).
The human-mode coding session (Codex CLI on the developer's laptop) is the builder
tier too: `codex-config.example.toml` names terra.

**The fleet's resource is `lantern-agentic-foundry`** (endpoint
`https://lantern-agentic-foundry.openai.azure.com/openai/v1`), which has carried all
three deployments since 2026-09-14 — `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, all
Standard; `smoke_test.py` prints the three tiers `[OK]` against it and the laptop `.env`
is split, and so are SSM `/lantern/dotenv` and the box `.env` (2026-09-14). The older
resource, `lantern-prod-agent`, was retired on 2026-09-15: its only deployment
(`gpt-5.6-sol`) was deleted through the legacy data-plane API
(`DELETE /openai/deployments/<name>?api-version=2023-03-15-preview` with the resource
key — the same API lists a resource's deployments, which `models.list()` does not), so
its key reaches no model any more; deleting the empty resource itself is a portal step.
Rolling the split out to a box:

1. In SSM `/lantern/dotenv` and the box `.env`, set `AZURE_OPENAI_ENDPOINT` to the new
   resource's `/openai/v1` endpoint and `AZURE_OPENAI_API_KEY` to its key (the portal
   shows both next to the project), then `LANTERN_MODEL_CODING=gpt-5.6-terra`,
   `LANTERN_MODEL_FAST=gpt-5.6-luna` and `LANTERN_PRICE_JSON` (values in `.env.example`).
   Flipping only the tier vars while the endpoint still names `lantern-prod-agent` fails
   every coding and QA execution with `DeploymentNotFound`.
2. `.venv/bin/python smoke_test.py` on the box must print the three tiers `[OK]` (it
   exits 1 otherwise) before the restart.
3. Restart the daemon and Mission Control (`sudo systemctl restart lantern-orchestrator
   lantern-mission-control` when no stage is executing — `infra/ec2/tender-playbook.sh
   deploy` does that check).

A tier may only name a deployment the configured resource has: the fallback chain
covers unset vars, not missing deployments, and a wrong name fails its stages —
loudly, which is the intended failure mode.

## The pipeline runner (the "one call")

`pipeline.py` is the durable concept→live loop (design: `docs/ORCHESTRATION.md`):
a Postgres state machine drives all stages in order, pauses at human gates
(`approvals` rows) for as long as needed, and survives restarts. Conversations
persist per `{run_id}:{stage}` via the Agents SDK's `SQLAlchemySession` in the same
Postgres (`LANTERN_DATABASE_URL`).

```bash
python pipeline.py init-db                      # once
python pipeline.py run workflow/briefs/x.md     # the one call
python pipeline.py daemon                       # service loop (systemd on EC2)
python pipeline.py step <run-id>                # one stage of one run in the foreground (laptops, debugging)
python pipeline.py status | approve | reject | retry
python pipeline.py rework <run-id> --to 03-coding --by <you> --note "…"   # the loop as code (D17)
python pipeline.py babysit [<run-id>] [--force]   # keep an approved branch mergeable until a human merges (D19)
python pipeline.py runboard | render-memory     # re-render the Postgres-backed views
python pipeline.py import-run <run-id>          # backfill a file-era run into the DB
python pipeline.py set-product | set-coding-mode   # per-run product repo + how stage 3 runs (D14)
python pipeline.py set-design-mode <run-id> paper|html   # how stage 1 converges: Paper workstation or HTML on ec2 (D25)
python pipeline.py usage [--days 7]             # token ledger: per-day + per-run est. spend
python pipeline.py usage-check                  # spend tripwires (hourly systemd timer on EC2)
python pipeline.py qa-target qa-dev --base-url URL --user U   # write a QA stage's target into .env (password generated, never printed)
python pipeline.py qa-preflight [--stage qa-dev]  # can the host AND a sandbox reach that target?
python pipeline.py bug "<text>"|<file> [--source user|posthog|slack] [--shepherd X] [--coding-mode auto]  # a bug run at 01-triage (D20)
python pipeline.py evals build | run --suite <name> [--live] | report   # the factory's evals (tools/evals/, D20)
```

For scripts, `python pipeline.py status --json` prints one JSON object with `runs`
and `pending_gates` arrays; plain `python pipeline.py status` keeps the human-readable
table.

Every stage execution records its token usage on its `stage_executions` row (P0.4):
the Agents SDK usage object in-process, or the container's `LANTERN_USAGE` stdout
line (validated — it shares stdout with agent text) parsed by the dispatcher — a
host-side write either way, so the ledger keeps working when sandboxes lose direct
table access. Executions that crash before reporting stay unmetered; `usage` prints
the count. QA stages (04/07, debug regression) must leave a fresh, non-empty `.webm`
from the current attempt (the orchestrator launches the browser MCP with the
checked-in `saveVideo` config — recording is automatic in every executor); the check
lives in `check_postconditions`, so container, host re-check, and in-process runs
all enforce it. After postconditions pass, the **host** uploads the attempt's videos
to `s3://$LANTERN_ARTIFACT_BUCKET/lantern/<run-id>/<stage>/attempt-<k>/` under the
PIPELINE.md `session-<n>` naming (AWS creds never enter a sandbox; retries never
overwrite earlier attempts' footage), regenerates `media-manifest.json` from the
artifacts table, and deletes the local files.

## Connecting a codebase — and letting the pipeline code in it (D14)

A run works on ONE product repository, the way a developer's coding agent works in one
checkout. Point the run at it and the fleet does the rest:

There are three ways to point a run at a codebase, and they resolve in this order:
**CLI flag → the brief's own field → the box default**.

```markdown
# in the brief (workflow/briefs/<slug>.md)
- **Product repo:** https://github.com/org/repo     # or an on-box path: /home/ubuntu/work/repo
- **Base branch:** main                             # what work branches FROM, what the PR targets
- **Working branch:**                               # blank = a fresh feat/<date>-<slug> for this run
- **Coding mode:** auto                             # human (default) | auto
```

```bash
# or on the command line
python pipeline.py repos                             # git repos THIS host can offer
python pipeline.py run workflow/briefs/x.md --product-repo https://github.com/org/repo --coding-mode auto
python pipeline.py set-product <run-id> --repo <url-or-path> --branch main   # an existing run
python pipeline.py set-product <run-id> --repo <url-or-path> --branch main \
                   --working-branch feat/20260901-thing                      # continue a branch
python pipeline.py set-coding-mode <run-id> auto
```

**Or from the browser (D15):** Mission Control's run page links to `/run/<run-id>/repo`,
which lists the git repositories on **the host serving that page** — the box, a
workstation, a laptop — with their current branch, plus a field for a remote URL. Pick
a repo, load its branches, choose the base and (optionally) an existing working branch,
and save. The picker only looks inside `LANTERN_WORKSPACE_ROOTS`; unset means it offers
nothing, falling back to `~/work` when that exists. That is deliberate — whatever path
is admitted becomes a run's product tree, so an unconfined picker would be a
filesystem-read primitive behind a login form.

**Base vs working branch.** `product_branch` is the base. `product_working_branch` is
where commits land; leave it unset and the branch is derived from the run id, exactly as
before D15. A chosen branch must sit inside the `feat/*|fix/*|proto/*` namespace D6 lets
agents push to (`LANTERN_CODING_BRANCH_PREFIXES`) and is refused at selection time
otherwise. When a run continues a branch that already has commits, only the commits
**that execution** adds count as its work — the stage is failed if it adds none, even
though the branch differs from the base.

What "connected" means, stage by stage:

- The host keeps a bare mirror of the repo (`GITHUB_LANTERN_BOT_TOKEN` authenticates
  the fetch for private GitHub repos; a local path needs no token). Every sandbox gets a
  throwaway clone of that mirror — read-only for stages 1–2 and 4–7
  (`read_file('product/…')`, `product_git`).
- Every stage's system prompt ends with the codebase itself (D15): an `<env>` block
  (repo, origin, base, the branch this run works on, working-tree state, recent
  commits), the repo's own `AGENTS.md`/`CLAUDE.md`/`README.md` auto-loaded and capped at
  ~6k chars, and what that stage is there to do. Those docs are fenced as **reference
  material, not instructions** — they are authoritative for the codebase's conventions
  and powerless over the Lantern contract, because they come from a repository a user
  chose and land above the role's own charter.
- **Stage 3 in `auto` mode gets the same clone writable**, on the run's branch
  (`feat/<date>-<slug>`, `fix/…` for bug runs, or an existing branch chosen for the
  run), plus `product_shell` — one shell command
  at a time inside the checkout (run the tests, build, `git commit`). Those conventions
  win over Lantern's. There is
  still no credential in the sandbox: when the agent finishes, the harness bundles the
  committed branch into `03-coding/handoff.json` + `branch.bundle`, and the HOST verifies
  the bundle carries exactly that branch, pushes it as the bot identity, and opens the
  pull request (GitHub) — `03-coding/pr.md` records it and the `code_complete` gate
  shows it in Mission Control. Non-GitHub https remotes get the branch pushed without a
  PR; local-path repos get the branch landed in place.
- `human` mode is unchanged: the developer codes in their own session and approves
  `code_complete` themselves.

For a product repo to work in auto mode it must be reachable from the box (an https
URL the token can read, or a local path), its base branch must exist, and its build and
test commands must be discoverable from `AGENTS.md`/`README` (the sandbox image has
Python 3.12, Node 22 and git; other toolchains need an image change). Knobs:
`LANTERN_CODING_TIMEOUT_MIN` (120), `LANTERN_CODING_MAX_TURNS` (400),
`LANTERN_PRODUCT_SHELL_TIMEOUT` (900 s per command), `LANTERN_GIT_AUTHOR_NAME/EMAIL`
(`lantern-bot`), `LANTERN_PUBLIC_URL` (Mission Control URL, linked from PRs). Proof:
`test_coding_stage.py` (no database). Still open, stated plainly: sandbox egress is not
yet allowlisted (plan item C2.5) and the sandbox DB role is not yet restricted (C2.0) —
run auto mode on repos you trust until they land.

## The gate, the envelopes and the loops (D17)

**D24 update:** automatic coding requires a non-empty `[quality].test` command
before its first model turn. Missing policy or gate artifacts are errors, including
on older sandbox images; upgrade host and sandbox together. The harness captures
`lantern.toml` before the build and refuses changes during that execution. Land
quality-policy changes separately through human review, then start a fresh run.
An exit-zero command only proves that configured command succeeded: product owners
still need meaningful tests and independent QA.

Validation `evidence` accepts `{path, line?}` lists (or compact `path:line` strings),
with explanation in `reason`; references must resolve. Existing prose-only validation
envelopes must be regenerated if their stage is retried. Historical artifacts stay
readable in Mission Control. See `docs/AGENT-CAPABILITIES.md` for current tool grants.

`factory.py` holds the software-factory mechanics — pure functions, no SDK, tested by
`test_factory.py`:

- **Quality gate.** A product repo declares its checks in `lantern.toml`:

  ```toml
  [quality]
  test = "npm test -- --runInBand"
  lint = "npm run lint"
  typecheck = "npx tsc --noEmit"
  timeout_s = 900
  ```

  After the coding agent's turn (auto mode) the commands run from the product root
  through bash, plus a **write-scope** check against `02-pre-coding/plan.json`. The
  result is written to `03-coding/gate.json` + `gate.md`; failures (only) go back to the
  agent for `LANTERN_FIX_ROUNDS` rounds; still red = the stage fails, and the handoff is
  refused if a commit leaves the scope. `$LANTERN_PYTHON` in a command is the harness
  interpreter — this repo's own `lantern.toml` uses it to run its test suites when the
  product under a run is Lantern itself.
- **Envelopes.** `00-story/research.json`, `00-story/story.json`,
  `02-pre-coding/plan.json`, `05-post-coding/validation.json` are validated as
  postconditions (shapes in the role skills; `factory.ENVELOPES`). A plan must map every
  story criterion to a task or defer it with a reason; a validation must give every
  criterion exactly one evidenced verdict and a verdict that matches the statuses.
- **Rework.** `pipeline.py rework <run-id> --to 02-pre-coding|03-coding|04-qa-dev` sends a
  failed or waiting run backwards: pending approvals expire, the decision is recorded in
  `gate-decisions.md`, the daemon re-runs from there with the same session memory.

## Parallel builders (D18)

`builders.py` turns stage 3 into several confined agents when — and only when — the
approved `02-pre-coding/plan.json` says so:

```json
"builders": [
  {"name": "api",  "write_scope": ["src/api/**", "tests/api/**"], "tasks": [1, 2], "criteria": ["AC-1"]},
  {"name": "docs", "write_scope": ["docs/**"],                    "tasks": [3],    "criteria": ["AC-4"]}
]
```

With no `builders` key, `run_coding` is one `execute` call and stage 3 is byte-for-byte
what D14/D17 built. With one, per run:

| step | what runs | where |
|------|-----------|-------|
| fan out | `03-coding.<name>` per builder, `LANTERN_BUILDER_PARALLELISM` at a time | branch `<run branch>--<name>`, scope = that builder's globs, `03-coding/builders/<name>/` |
| merge | the **host** verifies each bundle, lands it in the mirror, resets the run branch to the shared start point and `git merge --no-ff`s each builder in plan order | `03-coding/builders.json` + `builders.md` |
| integrate | `03-coding.integrate`, scope = the union, task = "make the merged branch green", normal gate + fix loop | the run branch; its handoff is the stage's handoff |

Then the single `code_complete` gate, whose payload gains
`builders: [{name, branch, commits, files_changed}]`.

- `LANTERN_BUILDER_PARALLELISM` (default 2) is capped by the executor's own concurrency
  and is **1 in-process on purpose**: the in-process path configures each execution
  through `os.environ`, which two concurrent executions in one process would overwrite
  for each other. Real parallelism needs `LANTERN_EXECUTOR=docker`.
- `LANTERN_BUILDER=<name>` is what makes an execution a builder: `factory.write_scope`
  narrows to that builder's globs, and its report, gate, handoff and bundle move under
  `03-coding/builders/<name>/` — parallel builders cannot share one `report.md` without
  racing on its last `Status:` line.
- Branches stay inside `CODING_BRANCH_PREFIXES` (D6) because the suffix is appended to a
  branch that already does.
- **A merge conflict fails the stage** with the conflicting files and points at
  `pipeline.py rework <run-id> --to 02-pre-coding`. Two builders touching one file means
  the split was wrong; resolving it with a model would hide a planning defect. Note the
  plan check compares glob *strings*, so `src/**` and `src/api/**` pass it and conflict
  here — write scopes that are genuinely disjoint.
- The host's own checks stay presence-AND-validity: every builder's bundle must carry
  exactly its branch, its commits must be inside its scope, and every builder head must
  be an **ancestor** of the branch about to be pushed, so a merge that silently dropped
  one cannot reach the PR. Proof: `test_builders.py` (real git, no database, no model).
## Review rounds and the merge babysitter (D19)

`review.py` adds the two things Boundary's factory does around a pull request, both
tested by `test_review.py` (fakes + real git, no database, no network):

- **Review loop.** Right after `publish_coding_branch` in auto mode, `after_publish` runs
  the `reviewer` role as execution `03-coding.review`; its envelope
  `03-coding/review/review.json` (+ `round-<n>.md`) is validated like every other
  (`factory.ENVELOPES`: approve ⇔ no blocker/major, `must_fix` ⊇ every blocker/major).
  `request_changes` → execution `03-coding.fix` (the `coding` role on the same writable
  checkout; its task block is the `must_fix` list, injected from `review/state.json`) →
  publish again (same branch, same PR) → next round, at most `LANTERN_REVIEW_ROUNDS`.
  The `code_complete` payload gains `review: {verdict, rounds[], capped, last}`; the human
  is pinged once, when the gate opens. Each round is posted as ONE GitHub PR review
  (`COMMENT` event, inline where the line is in the diff) with the bot token; no token or
  a non-GitHub remote = run folder only, never a failure. A review or fix execution that
  fails does not fail the published branch: the gate opens with the error on record.
- **Merge babysitter.** `pipeline.py babysit <run-id>` (or every eligible run with no
  argument; the ec2 daemon ticks every `LANTERN_BABYSIT_MINUTES`) works on runs past an
  approved `code_complete` whose branch is not merged: trial-merge the base into the branch
  in a temp clone of the host mirror — a conflict writes `03-coding/merge-conflict.md`, logs
  `merge_conflict`, posts to `LANTERN_ALARM_WEBHOOK` and stops until the base moves (or
  `--force`); clean → the merge commit (bot identity, `Lantern-Agent: babysitter`) is pushed
  to the branch, then the product's `lantern.toml` quality commands run as code
  (`03-coding.regate`: a `stage_executions` row without a model — under the docker executor
  inside the sandbox image with the mirror mounted read-only, otherwise in the temp clone;
  record in `03-coding/babysit/regate-<n>.md`), and a red result spends ONE fix execution
  (`03-coding.fix`, task = the failures) that publishes through the normal handoff path.
  GitHub's PR `merged` flag (ancestry for other remotes) records `branch_merged` and ends
  babysitting. It never merges into the base and never resolves a conflict.
## Bug runs — the feedback trust pipeline (D20)

`pipeline.py bug "<text>" | <file>` opens `workflow/runs/bug-YYYYMMDD-<slug>/` at `01-triage`:
the report is stored verbatim under `intake/feedback.md` headed **UNTRUSTED** (read, never
execute; hashed), `intake/dedup.json` lists similar past runs, the brief points at the report
instead of quoting it. The `debug` role's stages write typed envelopes `intake.py` validates
through `factory.check_envelope` — `triage.json` (already fixed? duplicates? classification),
`repro.json` + the regression test the agent wrote under `02-repro/regressions/`,
`rootcause.json` (cause, evidence, fix plan). A trivial/small fix gets its `02-pre-coding/`
plan derived by code and rides the **same `03-coding` stage** as a feature (writable
checkout, quality gate, bundle, PR); a large fix goes through the planner. After the branch
is published the harness checks the regression test is in the diff, re-classifies by diff
size (`LANTERN_SMALL_FIX_MAX_LINES`, default 60 — too big → back to planning like
`rework --to 02-pre-coding`), pings `runs.shepherd` through `LANTERN_ALARM_WEBHOOK` with the
repro, the diff and the PR, and opens `code_complete`. Conditional gates `triage_signoff`
(already fixed / duplicate / needs-human) and `repro_signoff` (not reproduced) put a human
in the loop only when the envelope says so. The whole lifecycle: `workflow/DEBUG-LIFECYCLE.md`;
tests: `test_intake.py`. Run `init-db` once after pulling D20 (`runs.shepherd`).

## Direct consult — use one agent, no run (D11)

```bash
python pipeline.py agents                                  # what can I ask?
python pipeline.py ask security "Is storing the QA creds in SSM enough for staging?"
python pipeline.py ask security "what about rotation?"     # continues the same conversation
python pipeline.py ask ui-ux "critique this flow idea" -i  # live loop; empty line ends
python pipeline.py ask qa-dev "..." --session bulk-export  # named parallel thread
python pipeline.py ask qa-dev "..." --new                  # forget the thread, start over
```

The role's charter/skills/memory load into the system prompt, the agent can read the
whole repo (and browser roles get the Playwright MCP — `--no-browser` to skip), and
conversation state persists in Postgres per `{you}:{role}:{session}`. Consults are
advisory and read-only by design; producing or changing artifacts is pipeline-run work.

The same consults run in the browser: **`chat_service.py`** powers Mission
Control's Chat tab (docs/CHAT.md, D13) — same session store (a CLI thread whose
`{you}:{role}:{session}` matches continues on the web), plus the `lantern`
orchestrator chat (DB tools + `ask_specialist`, and the write tools below),
user-created custom
agents (`custom_agents` table), a per-turn token ledger (`chat_turns`), and live
SSE streaming. `test_chat_service.py` covers the turn lifecycle with a faked
model loop — no Azure credentials needed.

Role memory consolidation (roughly monthly): merge the rendered rows below the marker
in `agents/<role>/memory.md` up into the hand-written base, then mark them done and
re-render:

```sql
UPDATE role_memory SET consolidated = true WHERE role = '<role>' AND created_at < '<date>';
```

## Operating the factory from chat and Slack (D21)

The `lantern` orchestrator has five write tools — `start_run`, `set_product`,
`rework`, `retry`, `decide_gate` — so a developer can run the factory from the chat
that already shows them what is blocked. Fleet roles do not: D11's read-only line still
holds for every specialist.

They are `pipeline.py`'s own commands behind `PipelineExecutor`, never a second copy of
the logic, and three of them are two-step. The tool returns a **decision card** and does
nothing; the human types the exact phrase it names; the server looks for that phrase in
**the human's own most recent message** and only then acts. The tools are built per turn
over that turn's text (`make_write_tools(publish, by, user_text, …)`), so a model cannot
confirm itself and yesterday's confirmation cannot authorise today's approval. `retry`
and `set_product` are reversible and act at once. Every action carries the signed-in
human's identity into `events` (`human:<user>`, `channel: web-chat`) — never the agent's.
Proof: `test_chat_tools.py` (30 checks, no database, no model).

**Slack** (`tools/slack-bridge/`, its own README + systemd unit) is the same thing over
Socket Mode: `@lantern <idea>` opens a run and a thread, gates post into that thread with
Approve/Reject buttons, and a click writes through `cmd_decide` as `slack:<user id>` —
only for `LANTERN_SLACK_APPROVERS`, never for `staging_deploy` or `prod_signoff`.

```bash
python pipeline.py init-product /path/to/product-repo      # install the gate (D21)
python pipeline.py init-product /path/to/repo --dry-run    # show what it would write
```

`init-product` detects the stack from the files that are there — `package.json` →
`npm test` (plus `npm run lint` / `npx tsc --noEmit` / `npm run build` where the repo
shows evidence), `pyproject.toml`/`setup.py` → `pytest -q` (+ ruff/mypy if configured),
`go.mod` → `go test ./...`, `Cargo.toml` → `cargo test` — writes `lantern.toml` from
`workflow/templates/lantern.toml` with those commands, appends a short "built by the
Lantern software factory" block to the product's `AGENTS.md` (created if absent, existing
text never rewritten, the block marked so a second run is a no-op), and prints how to
point a run at the repo. An existing `lantern.toml` is kept unless `--force`: that file
is the product's gate and the team may have tuned it. Proof: `test_init_product.py`.

### Runner affinity — the design workstation daemon

Paper's MCP server is desktop-bound, so stage 1 is split (D9): `01-ui-ux.diverge`
runs on EC2 with `LANTERN_MODEL_FAST`; `01-ui-ux.design` (Paper convergence) is
claimed only by a daemon started with `--runner workstation`. Setup on the design
machine (once):

1. Install Paper Desktop, sign in, open the team file `Lantern` (its MCP server
   listens on `http://127.0.0.1:29979/mcp` while the file is open).
2. `pip install -r requirements.txt`; copy `.env.example` → `.env` with
   `LANTERN_RUNNER=workstation` and a `LANTERN_DATABASE_URL` that reaches the EC2
   Postgres (Tailscale recommended) plus the Azure OpenAI vars.
3. Run `python pipeline.py daemon --runner workstation`.

The daemon preflights Paper at startup (exits with instructions if the Desktop app
isn't up) and re-checks every tick — it never claims a stage it would fail mid-run.
Daemons heartbeat into the `runners` table; Mission Control uses that to show
"needs the design workstation" instead of a silent stall when the daemon is offline.

## The stage orchestrator

`orchestrator.py` runs **one stage of one run** per invocation (used directly for
manual/debug work; `pipeline.py` reuses its internals) — deterministic pipeline
control stays in code/humans, the model only gets autonomy *inside* a stage:

```bash
python orchestrator.py feat-20260824-bulk-export 04-qa-dev
```

What it does:

1. Renders the role's `memory.md` fresh from the `role_memory` table, then builds the
   system prompt: `AGENTS.md` core rules + the role's `charter.md` + `skills.md` +
   `memory.md` + the run/stage assignment.
2. Creates an Agents SDK `Agent` on the role's routed deployment, with tools:
   file read/write scoped to the repo (rejects the rendered views RUNBOARD.md and
   memory.md), `append_memory` bound to this execution, the Playwright MCP server for
   browser roles, and shell access only where the role's charter needs it.
3. Runs the loop, then **enforces the two written postconditions** (stage report
   exists + claimed artifacts are real, memory row inserted by THIS execution) —
   failing loudly if the model skipped one. Sound under concurrent runs:
   `test_verification.py` is the proof.

**Requires Postgres** (`LANTERN_DATABASE_URL` + `pipeline.py init-db` once) even for
one-off stage runs — role memory lives in the database. `pip install -r requirements.txt`.

### Local dev Postgres on Windows (no admin, no service)

Portable binaries from EDB, kept outside the OneDrive-synced repo:

```powershell
# once: download + extract https://get.enterprisedb.com/postgresql/postgresql-16.9-1-windows-x64-binaries.zip
#       to %USERPROFILE%\.lantern\pgsql, then:
& "$env:USERPROFILE\.lantern\pgsql\bin\initdb" -U lantern -A trust -E UTF8 -D "$env:USERPROFILE\.lantern\pgdata"
& "$env:USERPROFILE\.lantern\pgsql\bin\pg_ctl" -D "$env:USERPROFILE\.lantern\pgdata" -l "$env:USERPROFILE\.lantern\pg.log" start
& "$env:USERPROFILE\.lantern\pgsql\bin\createdb" -U lantern -h localhost lantern
# every reboot: just the pg_ctl ... start line
```

The default `LANTERN_DATABASE_URL` (`postgresql+asyncpg://lantern:lantern@localhost:5432/lantern`)
matches this setup as-is.

## Codex CLI for developers (stage 3)

Copy `codex-config.example.toml` into `~/.codex/config.toml`, fill in the resource
name, and export `AZURE_OPENAI_API_KEY`. Codex reads the product repo's `AGENTS.md`
natively; Lantern's coding conventions (`agents/coding/skills.md`) apply as before.
Check Codex's docs for the current `api-version` value when setting up.

## MCP wiring

The shared server list lives in `.mcp.json` (repo root) as the single reference.
- Agents SDK: servers are attached in `orchestrator.py` (stdio/HTTP per server).
- Codex CLI: mirror the needed servers into `~/.codex/config.toml` (`[mcp_servers]`).

Video recording stays harness-independent: it's a property of the Playwright browser
context (`tools/qa-recorder`), so QA videos work identically under every option above.

## Experimental isolated controller and execution leases

The opt-in controller/worker, authority, lease and recovery contract is in
[docs/EXECUTION-ISOLATION.md](../../docs/EXECUTION-ISOLATION.md). Read its unsupported
paths and rollback limits before enabling any experimental flag. Live and injected
evidence are separately labelled in the infrastructure engineering run.
