# Orchestration — one call from concept to live

`lantern run <brief>` starts a feature run that flows through every pipeline stage,
pausing at human gates for as long as it takes, surviving restarts, and ending with a
signed-off production deploy. This document is the design; the implementation lives
in `tools/azure-runner/` (`pipeline.py` + `schema.sql`). Grounding research:
`docs/research/karpathy-agentic-loops.md` and
`docs/research/durable-pipeline-architecture.md`. Decision record: D8.

## The one sentence of philosophy

Karpathy's law — *"LLMs automate what you can verify"* — means the loop's job is not
to remove humans but to move every stage's output into a form that is verified
mechanically (postconditions, tests, recorded UI runs) or reviewed by a human in
seconds (videos, small diffs, reports). One call *starts* concept→live; the gates are
the autonomy slider's detents, and they stay.

## Two layers of durability, no workflow engine

**Outer layer — a Postgres state machine.** Runs and stage executions are rows; a
single orchestrator daemon (systemd, `Restart=always`) polls every few seconds,
claims runnable work with `FOR UPDATE SKIP LOCKED`, executes one stage, advances.
All state is in Postgres, so a crash, reboot, or week-long gate wait costs nothing —
no process ever waits on a human.

**Inner layer — Agents SDK primitives.** Each stage runs one agent whose
conversation persists via `SQLAlchemySession` (session ID `{run_id}:{stage}`) in the
same Postgres. The two written AGENTS.md postconditions (report on disk, memory row
from this execution via `append_memory`) are enforced mechanically after every agent
stage; the runboard is rendered, not written. (v2: `needs_approval` tools +
serialized `RunState` for mid-stage approvals — schema already has the column.)

**Explicitly rejected for now:** Temporal (operational weight of a cluster + replay
discipline, overkill for one box) and LangGraph (second framework; interrupted nodes
re-run from start anyway). **Upgrade path, in order:** DBOS Transact when hand-rolled
retry semantics hurt (still Postgres-only); Temporal + its official Agents SDK plugin
when we outgrow one machine.

## Control flow

```
 lantern run "brief"          (CLI inserts run + run folder, exits)
        │
        ▼
 [Postgres] runs ─ stage_executions ─ approvals ─ artifacts ─ events
            └ agent_sessions / agent_messages   (SDK-owned, per {run_id}:{stage})
        ▲                                ▲
        │ poll + claim                   │ decision writes
 ┌──────┴────────────────┐      ┌────────┴──────────────────────────┐
 │ orchestrator daemon   │      │ approval front-ends               │
 │  next runnable run    │      │  now:  lantern approve/reject CLI │
 │  run stage agent ─────┼──►   │  next: Slack buttons + GitHub PR  │
 │  verify postconditions│      │        webhook (fail-closed)      │
 │  record artifacts     │      └───────────────────────────────────┘
 │  gate? → approval row + status=waiting_gate   (process holds nothing)
 │  fail? → attempt++/failed + heartbeat sweeper
 └───────────────────────┘
```

## Stages, gates, and who verifies what

| Stage | Type | Verified by | Gate after |
|-------|------|-------------|-----------|
| 00-story.scout (EC2) | agent | postconditions + research.json (every cited path exists) | — |
| 00-story.write (EC2) | agent | postconditions + story.json validates + a human reads story.md | `story_signoff` |
| 01-ui-ux.diverge (EC2) | agent | postconditions + judge scores in report | — |
| 01-ui-ux.design (workstation) | agent | postconditions + human reviews PNGs/video | `ux_signoff` |
| 02-pre-coding | agent | postconditions + typed plan artifacts | `plan_signoff` (schema = always human) |
| 03-coding | **human** (developer + Codex CLI), or the `coding` agent in auto mode | human: tests green, self-review; auto: the product's `lantern.toml` quality commands + the plan's write scope run as code, failures fed back for a bounded number of rounds (D17) | `code_complete` |
| 04-qa-dev | agent | executed, video-recorded charter | — (loops back on sev-1/2) |
| 05-post-coding (+ .validate) | agent | findings table, fix-now resolved; then validation.json — one verdict per acceptance criterion, `pass` required (D17) | — |
| 06-security | agent | go/no-go with evidence | `staging_deploy` (human deploys) |
| 07-qa-staging | agent | staging runs + PostHog event checks | `prod_signoff` |

A rejected gate marks the run `failed` with the decision note; `lantern retry` after
rework re-enters at the same stage (fresh attempt row, same session ID — the agent
keeps its conversation memory).

## Runner affinity (D9)

Every stage carries a `runner` (`ec2` | `workstation`); one daemon per runner claims
only its own stages (`current_stage = ANY(...)` in the claim query), so runners never
contend. The design workstation runs `pipeline.py daemon --runner workstation` for the
Paper-bound `01-ui-ux.design` execution; it preflights Paper Desktop's MCP port at
startup (fails fast with instructions) and every tick (holds claims while Paper is
closed — no mid-run failures). Daemons heartbeat into the `runners` table; Mission
Control renders "needs the design workstation" on runs waiting for an offline runner —
the silent-stall failure mode made visible. Stage keys with a phase suffix
(`01-ui-ux.diverge`/`.design`) share one run-folder dir, so the D4 handoff contract is
unchanged.

## Gate integrity rules (fail closed)

- The `approvals` row is the only source of truth; Slack/GitHub are front-ends
  writing into it. Approver allowlist enforced server-side; actor + timestamp + note
  always recorded; webhook signatures verified.
- Agents have no code path that writes approvals. The code-review gate will be a
  GitHub PR with branch protection — an agent literally cannot self-merge.

## Failure modes engineered against (from the research)

1. **Resume-time drift** — every run stamps `pipeline_version`; stage rows stamp
   `run_state_version`; on mismatch, re-run the stage from its input artifact.
2. **Replayed side effects** — idempotency key per stage-attempt; check-before-acting
   on external mutations; intent recorded in `events` first.
3. **Fail-open gates** — see rules above.
4. **Cross-stage cascade** (MAST: 42% spec / 21% verification failures) — stage
   inputs/outputs are typed JSONB validated at the boundary; QA stays an independent
   execute-and-verify stage, never trusting the coder's self-report.
5. **Zombie runs** — `heartbeat_at` + sweeper requeues/fails stale stages;
   `lantern status` lists every non-terminal run; gate SLAs re-notify.

## The execution plane — sandbox per stage (D10)

The control plane above says *what runs next*. This says *where it runs*, and it is
what makes the system safe for ~5 developers at once.

```
                 one always-on AWS VM running Docker
 [Postgres] <--- dispatcher (claims via SKIP LOCKED, schedules; never executes)
      ^              |  docker run --rm  (one per stage execution)
      |              +--> [ sandbox ] /work + product-repo clone @ run branch
      |              +--> [ sandbox ]   own browser, scoped short-lived creds
      |              +--> [ sandbox ]   cpu/mem caps, wall-clock timeout, egress allowlist
      |                                  dies at the end - no residue between runs
      |
      +---- developer laptops: `daemon --runner workstation`
            claims ONLY 01-ui-ux.design for runs that developer owns,
            talks to *their own* Paper Desktop on 127.0.0.1:29979
```

**Why a container per execution rather than N daemons on a shared box.** Concurrency is
not the hard part — `FOR UPDATE SKIP LOCKED` already lets many workers claim safely.
Isolation is. Without a per-run filesystem, two stages share one working tree and one
product-repo clone and corrupt each other's checkouts. The container also gives the
blast-radius controls a review agent should never need but must have: no long-lived
credentials, a timeout, and an egress allowlist.

**Prerequisite before enabling N>1 — DONE 2026-08-26 (session 1).** The old memory
check (`memory_now == memory_before` on a shared file) was unsound under concurrency:
another run's append to the same role's `memory.md` satisfied it, so a stage that
wrote nothing passed. Now role memory lives in the `role_memory` table, agents write
it only through the `append_memory` tool (bound to the stage execution's key), and
the postcondition is "this execution inserted a row" — which no other run can
satisfy. `RUNBOARD.md` and `memory.md` are rendered views of Postgres; the agent
write tools reject direct edits to them. Proof: `tools/azure-runner/test_verification.py`
shows the old check passing a do-nothing stage and the new one failing it.

**Paper is deliberately not in the cloud.** Its MCP answers plain HTTP on localhost with
no auth of its own — it inherits whoever is signed into the desktop app. So the design
stage runs on the developer's own machine against their own account, routed by
`runs.created_by`. Five developers, five Paper seats, no shared desktop and no ceiling.

## Operating it

```bash
# once
python pipeline.py init-db
# per feature (this is "the one call")
python pipeline.py run workflow/briefs/bulk-export.md
# service (EC2) — LANTERN_EXECUTOR=docker makes it a dispatcher: one sandbox
# container per stage, N concurrent (infra/ec2/README.md "The execution plane")
python pipeline.py daemon
# humans
python pipeline.py status
python pipeline.py approve feat-20260825-bulk-export ux_signoff --by justin --note "option B"
python pipeline.py retry feat-20260825-bulk-export
# the loop as code (D17): a failed validation / QA round goes back to the builder
python pipeline.py rework feat-20260825-bulk-export --to 03-coding --by justin --note "AC-2 off-spec"
# rendered views (also refresh automatically on every state change / stage start)
python pipeline.py runboard
python pipeline.py render-memory [--role ui-ux]
# one-time backfill of a file-era run into the DB
python pipeline.py import-run feat-20260825-role-health --gate ux_signoff
```

Postgres setup + the systemd unit: `infra/ec2/README.md`.
