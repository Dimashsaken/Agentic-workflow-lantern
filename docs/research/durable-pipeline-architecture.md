# Durable multi-agent pipeline — research brief (2026-08-25)

Grounds `docs/ORCHESTRATION.md`. Constraint set: Azure OpenAI GPT deployments,
OpenAI Agents SDK (Python), one EC2 host, Postgres, human gates that wait days.

## Findings

**1. Agents SDK persistence is production-usable.** `SQLAlchemySession` persists
conversation history to Postgres (`agent_sessions` + `agent_messages` tables,
`from_url(session_id, url=..., create_tables=True)`); resuming = same session ID.
Human-in-the-loop is first-class: tools can declare `needs_approval`, a paused run
serializes completely via `RunState.to_json()` (docs mandate storing a version marker
alongside), and `Runner.run(agent, state)` resumes after `state.approve(...)`.
Current: openai-agents 0.22.0 (Aug 2026). Tracing defaults to OpenAI's dashboard
(needs an OpenAI key we don't have) — disable via `set_tracing_disabled(True)` or
route to self-hosted Langfuse with `add_trace_processor`.
Docs: <https://openai.github.io/openai-agents-python/sessions/>,
<https://openai.github.io/openai-agents-python/human_in_the_loop/>

**2. Durable execution, three tiers.** (a) **Temporal** + official
`temporalio.contrib.openai_agents` plugin — real replay-based durability, but you run
a Temporal cluster and learn its determinism discipline; overkill for one box.
(b) **DBOS Transact** — durable execution as a library, Postgres-only infra,
`DBOS.recv()` blocks durably for days (natural human gate); the middle path.
(c) **Plain Postgres state machine** — runs/stage_executions tables + a systemd
daemon polling with `FOR UPDATE SKIP LOCKED`; the ecosystem keeps re-converging on
this (pg-workflows, Microsoft pg_durable), you own retries/idempotency.
LangGraph's PostgresSaver was rejected: second framework, and interrupted nodes
re-run from the start anyway. ZenML's checklist for the outer layer: never hold a
process hostage for a 19-hour approval; never lose completed expensive work; never
lose pending-approval state on crash.
<https://github.com/dbos-inc/dbos-transact-py>,
<https://github.com/temporalio/sdk-python/blob/main/temporalio/contrib/openai_agents/README.md>,
<https://www.zenml.io/blog/openai-agents-sdk-durable-runtime>

**3. Human gates: the DB row is the gate.** An `approvals` row
(pending→approved/rejected, decided_by, decided_at) is the auditable source of truth;
Slack Block Kit buttons and GitHub PR required-reviews are just two front-ends that
write into it. Security lesson from the wild (hermes-agent issue #36848): an approval
handler that doesn't verify *who* clicked fails open — enforce an approver allowlist
server-side, verify Slack signing secrets / GitHub webhook HMACs, and let agents
never write their own approval rows. Branch protection means an agent literally
cannot self-merge.

**4. Schema pattern that recurs everywhere:** one row per workflow instance + one row
per step attempt (input/output JSONB, retry count, error class retryable|terminal) +
an append-only event log + heartbeat for stall detection. The SDK's two conversation
tables stay separate from orchestration tables.

**5. "AI dev team" lessons.** The MAST study (arXiv 2503.13657, 1,600+ annotated
traces): **42% of multi-agent failures are specification failures, 37% coordination,
21% weak verification.** MetaGPT's rigid SOPs cut spec failures but *increased*
verification failures; ChatDev's test-heavy approach did the reverse — you need both
structured stage contracts AND independent verification. OpenHands' winning pattern
is execute-and-verify loops (run the code, check, iterate), not suggest-only.
GPT-Pilot's trajectory (full autonomy → human checkpoints per task) is itself the
lesson.

## Top 5 failure modes to design against

1. **Resume-time drift** — prompts/SDK change while a run waits at a gate; stamp
   `pipeline_version` + `run_state_version` per row; on mismatch re-run the stage
   from its input artifact instead of resuming.
2. **Non-idempotent side effects replayed** — crash between `git push` and the
   checkpoint commit; idempotency key per stage-attempt, check-before-acting on every
   external mutation, record intent in `events` first.
3. **Fail-open approval gates** — verify actor allowlist + webhook signatures;
   decision, actor, timestamp always recorded; agents can't approve anything.
4. **Cross-stage error cascade** — typed artifact contracts validated at stage
   boundaries (fail fast, never let the next agent "interpret"), plus independent QA.
5. **Silent stalls / zombie runs** — heartbeats + a sweeper for stale stages, gate
   SLAs with escalating re-notification, a `status` command and daily digest so
   "waiting" is always visible.
