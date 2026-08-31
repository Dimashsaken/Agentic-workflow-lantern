# First full run — the P0.3 playbook

Written 2026-08-31, after the vacuous-gate cleanup. This is the exact path from today's
state to the thing the repo has never done: one brief carried through all seven stages to
`prod_signoff`. The section at the bottom is a **prompt to paste into a fresh session**
run *with* dimash — it needs answers only a human has.

## State as of 2026-08-31

Everything below is verified on the box, not assumed:

- `ux_signoff` is approved on both active runs (`feat-20260825-candidate-compare`,
  `feat-20260825-role-health`); decisions rendered in each run's `gate-decisions.md`.
- Both stage-2 executions returned `Status: BLOCKED` (no product target). The
  `plan_signoff` gates they opened — pre-5f3f653 code let a BLOCKED stage open its
  gate — were **rejected as vacuous on 2026-08-31** (`claude-for-dimash`); both runs
  now sit honestly `failed` at `02-pre-coding`, resume path in the rejection note.
- The product-repo wiring (P0.3 pass of 2026-08-27) is in place and proven:
  `runs.product_repo`, `pipeline.py set-product`, host bare mirror, read-only
  `product/` mount, `product_git` tool, `test_product_access.py` all-green.
- The sandbox image was rebuilt 2026-08-31 with the 5f3f653 entrypoint
  `safe.directory` fix baked in; `prove_isolation.sh` and `prove_video.sh` both pass.
- Local `main`, `origin/main`, and the box checkout are at parity (Mission Control v2
  worktree merged and pushed 2026-08-31).
- The daemon runs post-fix code (restarted 2026-08-29, after the last deploy).

## The two inputs only a human has

1. **The product repository URL + base branch.** Nothing in this repo, on the box, or
   in SSM names it, and the token at `/lantern/github/bot-token` is currently
   **Dimashsaken's personal PAT**, whose accessible repo list contains no product repo
   (checked 2026-08-31 via the GitHub API). So this needs both the answer *and* access:
   either grant that token read access to the product repo, or put a real `lantern-bot`
   token in the parameter (AGENT-TOOLING §identity says agents act as `lantern-bot` —
   today's reality differs; fix the parameter when convenient).
2. **A dev environment of that product for stage 4**: a base URL reachable **from the
   docker bridge network** (not localhost-only, not Tailscale-only) plus test
   credentials, stored as SecureString at `/lantern/qa/dev/{base_url,user,pass}`.
   `pipeline.py qa-preflight` is the acceptance test — it must print READY from a
   sandbox. The network path is already proven against a public target; only the real
   target is missing.

Also pending for dimash, smaller: confirm the `role-health` acting brief (its header
says "needs Justin's confirmation") or park that run and carry only
`candidate-compare`; assign the developer for stage 3.

## The unblock sequence (once input 1 exists)

On the box (`ssh -i ~/.ssh/lantern.pem ubuntu@54.166.128.138`, then
`cd ~/Agentic-workflow-lantern/tools/azure-runner`):

```bash
.venv/bin/python pipeline.py set-product feat-20260825-candidate-compare \
    --repo <url> --branch <base>       # syncs the mirror + verifies the branch first
.venv/bin/python pipeline.py retry feat-20260825-candidate-compare
journalctl -u lantern-orchestrator -f  # watch the sandbox claim + run stage 2
```

Do **not** retry before `set-product`: the stage will just burn ~$0.50 and fail
BLOCKED again — post-fix, a BLOCKED report fails the stage rather than opening a gate.

## Session prompt — paste into a fresh session with dimash

> Read `AGENTS.md`, `docs/plans/symphony-alignment.md` §4 Phase 0, and
> `docs/plans/first-full-run.md` (state + command sequences are there — trust it, it
> was verified on the box). Goal: **P0.3 — carry `feat-20260825-candidate-compare`
> through the first complete brief→prod_signoff run.** Work interactively with dimash;
> the gates are his to decide, never yours.
>
> First, collect the two human inputs from `first-full-run.md` §"The two inputs":
> the product repo URL + base branch (and token access to it), and the stage-4 dev
> target into SSM `/lantern/qa/dev/*`. Nothing else is blocking.
>
> Then, in order:
> 1. `set-product` + `retry` per the playbook; watch stage 2 run against real product
>    code in a sandbox.
> 2. Read the new `02-pre-coding` report, blast-radius, schema plan, and task plan
>    **with dimash, artifacts open** — a green stage is not evidence, the artifacts
>    are. If the plan is honest and complete he decides `plan_signoff`
>    (`pipeline.py approve <run> plan_signoff --by <his name> --note "..."`). Any
>    schema migration in the plan is `HITL: required`.
> 3. Run `pipeline.py qa-preflight` until it prints READY from the sandbox — before
>    stage 3 finishes, not after.
> 4. Stage 3 is the human+Codex stage: help dimash run the Codex CLI session
>    (`tools/azure-runner/codex-config.example.toml`) on the run's `feat/*` branch,
>    implementing stage 2's task plan. `code_complete` gate when he says so.
> 5. Let stages 4–6 run. Every failure: fix the cause, not the symptom, and file it
>    as role memory — stage 1 took seven attempts to pass honestly; budget the same
>    discovery tax here. Do not tune prompts to make a stage pass.
> 6. Staging deploy is human (gate 3), then stage 7, then `prod_signoff`. When it's
>    approved, update `symphony-alignment.md` P0.3 to DONE and start the P0.2 resize
>    conversation.
