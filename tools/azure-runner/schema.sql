-- Lantern orchestration schema (design: docs/ORCHESTRATION.md).
-- The Agents SDK creates its own agent_sessions/agent_messages tables separately.

CREATE TABLE IF NOT EXISTS runs (
    id               text PRIMARY KEY,          -- 'feat-20260825-bulk-export'
    brief            text NOT NULL,
    pipeline_version text NOT NULL,
    status           text NOT NULL DEFAULT 'running',  -- running|executing|waiting_gate|failed|done|cancelled
                                                       -- ('executing' = claimed by a daemon slot; requeued to
                                                       --  'running' on daemon restart if the process died)
    current_stage    text NOT NULL,
    created_by       text NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    completed_at     timestamptz
);

CREATE TABLE IF NOT EXISTS stage_executions (
    id                bigserial PRIMARY KEY,
    run_id            text NOT NULL REFERENCES runs(id),
    stage             text NOT NULL,
    runner            text NOT NULL DEFAULT 'ec2',     -- which daemon executed it: ec2|workstation
    attempt           int  NOT NULL DEFAULT 1,
    status            text NOT NULL DEFAULT 'running', -- pending|running|waiting_gate|succeeded|failed|skipped
    input             jsonb,
    output            jsonb,                            -- inter-stage artifact contract
    run_state         jsonb,                            -- serialized Agents SDK RunState (v2)
    run_state_version text,
    error             text,
    error_class       text,                             -- retryable | terminal
    idempotency_key   text UNIQUE,
    heartbeat_at      timestamptz,
    -- token ledger (P0.4): filled by the executor after the agent run; the ONLY
    -- basis for spend reporting and the daily alarm (`pipeline.py usage[-check]`)
    model               text,
    requests            int,
    input_tokens        bigint,
    cached_input_tokens bigint,
    output_tokens       bigint,
    total_tokens        bigint,
    started_at        timestamptz NOT NULL DEFAULT now(),
    finished_at       timestamptz
);
CREATE INDEX IF NOT EXISTS idx_stage_exec_run ON stage_executions(run_id, stage);
CREATE INDEX IF NOT EXISTS idx_stage_exec_started ON stage_executions(started_at);

-- Execution ownership/effects: additive recovery migration, approved local plan.
-- Activate only after draining old dispatchers; no mixed-version worker rollout.
ALTER TABLE runs
  ADD COLUMN IF NOT EXISTS lease_owner text,
  ADD COLUMN IF NOT EXISTS lease_expires_at timestamptz,
  ADD COLUMN IF NOT EXISTS lease_fence bigint NOT NULL DEFAULT 0;
ALTER TABLE stage_executions
  ADD COLUMN IF NOT EXISTS lease_owner text,
  ADD COLUMN IF NOT EXISTS lease_expires_at timestamptz,
  ADD COLUMN IF NOT EXISTS lease_fence bigint NOT NULL DEFAULT 0;
CREATE TABLE IF NOT EXISTS execution_effects (
  operation_key text PRIMARY KEY,
  run_id text NOT NULL REFERENCES runs(id),
  stage_execution_id bigint NOT NULL REFERENCES stage_executions(id),
  lease_fence bigint NOT NULL,
  kind text NOT NULL,
  request_sha256 text NOT NULL,
  status text NOT NULL CHECK (status IN ('intended', 'confirmed', 'uncertain')),
  external_ref text,
  result jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_runs_active_lease
  ON runs(lease_expires_at) WHERE status = 'executing';
CREATE INDEX IF NOT EXISTS idx_stage_active_lease
  ON stage_executions(lease_expires_at) WHERE status = 'running';
CREATE INDEX IF NOT EXISTS idx_execution_effects_run
  ON execution_effects(run_id, created_at);

CREATE TABLE IF NOT EXISTS approvals (
    id                 bigserial PRIMARY KEY,
    run_id             text NOT NULL REFERENCES runs(id),
    stage_execution_id bigint REFERENCES stage_executions(id),
    gate               text NOT NULL,   -- story_signoff|ux_signoff|plan_signoff|code_complete|staging_deploy|prod_signoff
    status             text NOT NULL DEFAULT 'pending', -- pending|approved|rejected|expired
    payload            jsonb,                            -- what the human is approving (links, videos)
    channel            text,                             -- cli|slack|github
    external_ref       text,                             -- slack ts / PR URL
    requested_at       timestamptz NOT NULL DEFAULT now(),
    decided_at         timestamptz,
    decided_by         text,
    decision_note      text
);
CREATE INDEX IF NOT EXISTS idx_approvals_pending ON approvals(run_id) WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS artifacts (
    id         bigserial PRIMARY KEY,
    run_id     text NOT NULL REFERENCES runs(id),
    stage      text NOT NULL,
    kind       text NOT NULL,   -- report|plan|prototype|diff|qa_video|checklist|design_png|design_handoff|paper_file|flow_spec
    uri        text NOT NULL,   -- repo-relative path or S3 URL
    sha256     text,
    metadata   jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS events (           -- append-only audit log
    id     bigserial PRIMARY KEY,
    run_id text,
    actor  text NOT NULL,                     -- 'orchestrator'|'agent:<role>'|'human:<name>'
    type   text NOT NULL,                     -- run_created|stage_started|stage_succeeded|...
    data   jsonb,
    at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, at);

CREATE TABLE IF NOT EXISTS runners (          -- daemon heartbeats (runner affinity)
    name      text PRIMARY KEY,               -- 'ec2' | 'workstation'
    last_seen timestamptz NOT NULL DEFAULT now(),
    details   jsonb
);

-- Role memory lives here, not in agents/<role>/memory.md (session 1, D10 prerequisite).
-- The file is a RENDERED VIEW of this table; the postcondition is "this stage execution
-- inserted at least one row", keyed by execution_key — sound under concurrency, unlike
-- the old file-diff check which another run's append could satisfy.
-- No FK on run_id: manual/legacy entries may predate any runs row.
CREATE TABLE IF NOT EXISTS role_memory (
    id            bigserial PRIMARY KEY,
    role          text NOT NULL,
    run_id        text,
    stage         text,
    execution_key text,                       -- '{run_id}:{stage}:{attempt}' | 'manual:...'
    entry         text NOT NULL,
    consolidated  boolean NOT NULL DEFAULT false,  -- true once merged into the file's base section
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_role_memory_role ON role_memory(role, created_at);
CREATE INDEX IF NOT EXISTS idx_role_memory_exec ON role_memory(execution_key);

-- idempotent upgrades for databases created before these columns existed
ALTER TABLE stage_executions ADD COLUMN IF NOT EXISTS runner text NOT NULL DEFAULT 'ec2';
ALTER TABLE stage_executions ADD COLUMN IF NOT EXISTS model text;
ALTER TABLE stage_executions ADD COLUMN IF NOT EXISTS requests int;
ALTER TABLE stage_executions ADD COLUMN IF NOT EXISTS input_tokens bigint;
ALTER TABLE stage_executions ADD COLUMN IF NOT EXISTS cached_input_tokens bigint;
ALTER TABLE stage_executions ADD COLUMN IF NOT EXISTS output_tokens bigint;
ALTER TABLE stage_executions ADD COLUMN IF NOT EXISTS total_tokens bigint;

-- The product repo this run implements (P0.3). Per-run, not per-daemon: a run
-- records what it was pointed at, and every stage's sandbox gets that repo
-- read-only. NULL = unset, and stage 2+ blocks asking for it rather than guessing.
ALTER TABLE runs ADD COLUMN IF NOT EXISTS product_repo text;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS product_branch text;
-- D15: product_branch is the BASE branch. product_working_branch is the branch work
-- actually lands on — NULL means "derive it from the run id" (coding_branch()), which
-- is every run created before D15 and every run that wants a fresh branch. Kept as a
-- separate nullable column so pre-D15 runs resolve to exactly what they resolve to
-- today and a rolling restart needs no coordination.
ALTER TABLE runs ADD COLUMN IF NOT EXISTS product_working_branch text;
-- How stage 3 runs for this run (D14): 'human' = the developer's own session and the
-- gate opens immediately (the original contract); 'auto' = the fleet's coding agent
-- implements the approved plan in a sandbox, the host pushes the branch as the bot
-- identity and opens the PR that becomes the code_complete gate's payload.
ALTER TABLE runs ADD COLUMN IF NOT EXISTS coding_mode text NOT NULL DEFAULT 'human';
-- D21: the Slack thread that follows this run. thread_ts is Slack's message timestamp
-- and doubles as the correlation key — gate cards, state relays and button clicks all
-- land in the one thread the run opened. NULL = the run was never started from Slack
-- (nothing about a run depends on these; the bridge is a front-end, not the truth).
ALTER TABLE runs ADD COLUMN IF NOT EXISTS slack_channel text;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS slack_thread_ts text;
-- D20: the human a bug run pings when its fix is ready (repro + diff + PR link). NULL = the
-- LANTERN_DEFAULT_SHEPHERD value at ping time. Feature runs leave it NULL.
ALTER TABLE runs ADD COLUMN IF NOT EXISTS shepherd text;

-- ── Chat surface (docs/CHAT.md, D13): web consults with history and a ledger ──
-- chat_sessions.id doubles as the Agents SDK session key ('consult:{user}:{agent}:{name}'),
-- so the SDK's agent_sessions/agent_messages rows and ours can never disagree on identity,
-- and a thread started with `pipeline.py ask` can continue on the web.

CREATE TABLE IF NOT EXISTS chat_sessions (
    id          text PRIMARY KEY,             -- 'consult:{user}:{agent}:{name}'
    agent       text NOT NULL,                -- fleet role, custom agent slug, or 'lantern'
    title       text,                         -- first message by default; renamable
    created_by  text NOT NULL,
    run_id      text,                         -- optional run scope (no FK: runs may be imported later)
    archived    boolean NOT NULL DEFAULT false,
    created_at  timestamptz NOT NULL DEFAULT now(),
    last_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_last ON chat_sessions(last_at DESC);

-- One row per user turn: the transcript, the activity trace ("what was happening"),
-- and the same token-ledger columns as stage_executions (P0.4 — dollars are always
-- computed at render time from exact token counts; NULL tokens = unmetered, never $0).
CREATE TABLE IF NOT EXISTS chat_turns (
    id          bigserial PRIMARY KEY,
    session_id  text NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    asked_by    text NOT NULL,
    user_text   text NOT NULL,
    final_text  text,
    status      text NOT NULL DEFAULT 'running',  -- running|done|failed|stopped
    error       text,
    trace       jsonb,                            -- ordered tool calls / specialist handoffs / notes
    model               text,
    requests            int,
    input_tokens        bigint,
    cached_input_tokens bigint,
    output_tokens       bigint,
    total_tokens        bigint,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);
CREATE INDEX IF NOT EXISTS idx_chat_turns_session ON chat_turns(session_id, id);
CREATE INDEX IF NOT EXISTS idx_chat_turns_started ON chat_turns(started_at);

-- User-created consult agents (Dust-style: purpose is the only required field;
-- instructions are composed from it when empty). They learn through role_memory
-- under their slug — table-only, no agents/<slug>/memory.md is rendered.
CREATE TABLE IF NOT EXISTS custom_agents (
    slug        text PRIMARY KEY,
    name        text NOT NULL,
    purpose     text NOT NULL,                -- one line: what this agent is for
    instructions text,                        -- optional; template-composed when empty
    model_pref  text NOT NULL DEFAULT 'reasoning',  -- reasoning|fast
    created_by  text NOT NULL,
    archived    boolean NOT NULL DEFAULT false,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
