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

CREATE TABLE IF NOT EXISTS approvals (
    id                 bigserial PRIMARY KEY,
    run_id             text NOT NULL REFERENCES runs(id),
    stage_execution_id bigint REFERENCES stage_executions(id),
    gate               text NOT NULL,   -- ux_signoff|plan_signoff|code_complete|staging_deploy|prod_signoff
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
