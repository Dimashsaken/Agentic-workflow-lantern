# Chat — talking to the fleet from Mission Control

Where developers *talk* to the pipeline. Mission Control's board answers "where is
my feature?"; Chat answers everything you would otherwise walk over to a colleague
for: "why did QA fail?", "what would security say about storing this token?",
"what's blocked right now and what does it cost?". It is the web surface of
**consult mode (D11)** — the same advisory, read-only line, with history, live
activity, and a token ledger attached.

## The two ways to talk (matches D11's two ways to use an agent)

1. **Consult one specialist.** Every fleet role (`agents/<role>/`) and every
   user-created agent is directly addressable: pick it, type, Enter. The agent
   gets its charter/skills/memory as a system prompt, repo read tools, and
   `append_memory` — exactly what `pipeline.py ask <role>` builds, sharing the
   same conversation store, so a thread started in the CLI can continue on the
   web and vice versa (session ids share the `consult:{user}:{agent}:{name}`
   convention).
2. **Ask Lantern.** One orchestrator chat that "does everything": it holds the
   whole pipeline in view (read tools over the repo *plus* three database tools —
   `pipeline_snapshot`, `run_detail`, `spend_summary`) and **pulls specialists in
   as tools** (`ask_specialist(role, question)` runs a one-shot consult of that
   role and returns the answer). You ask one chat; it routes depth to the right
   role. Specialist calls are visible in the transcript and metered into the
   same turn ledger.

Both stay **advisory and read-only** — no write tools, no gate access, no run
mutation. That is D11's deliberate line, and the web changes nothing about it:
work that changes the product or a run goes through a pipeline run, where
verification and gates exist. The chat UI says so on every composer footer
rather than letting anyone discover it by surprise.

## What the references gave us (read 2026-08-31, not remembered)

- **Claude Code** (the interaction model the brief names): a transcript is
  *messages interleaved with tool lines*, not bubbles — each tool call is one
  compact mono line (`⏺ read_file(workflow/RUNBOARD.md)`) with the result
  folded away; Enter sends, Shift+Enter breaks; a working indicator with elapsed
  time and a stop affordance; sessions are resumable and cost is first-class.
  Adopted wholesale — it matches the house rule "prefer information on surfaces
  over boxing everything into cards".
- **Manus**: three panes — past task threads left, the conversation center, and
  the agent's live activity visible in the open rather than as a black box;
  sessions are replayable after the fact. Adopted: the session rail, and
  `chat_turns.trace` persists every tool call so a finished turn replays its
  activity exactly (nothing is only-live).
- **Devin**: one unified progress timeline per step instead of separate
  shell/edit/browser views. Adopted: tool lines live *inside* the turn that
  caused them, in order, one stream.
- **LangGraph agent-chat-ui / assistant-ui**: thread management + tool-call
  visualization + streaming as the baseline anatomy of an agent chat. Confirms
  the shape; nothing else taken (it's a Next.js SPA — Mission Control stays
  server-rendered, no build step).
- **Dust (Agent Builder + Sidekick) / Lindy**: agent creation is a form a
  non-engineer finishes in a minute — name it, say what it's for, instructions
  are *drafted for you* rather than demanded. Adopted: `purpose` is the only
  required field; instructions are optional and composed from a template when
  empty.
- **openai/symphony** (read earlier for the board, `tools/mission-control/mockups/README.md`):
  numbers as `Total` with `In / Out` beneath, `tabular-nums slashed-zero`
  everywhere, live-ness driven by socket state and never faked, empty states
  written as sentences. All kept here.

Lantern's house style wins where they conflict: the design system's own shell
pattern is already "left column = the conversation, right column = the working
surface" with LANTERN/YOU speaker labels — so the chat page is the design
system's conversation pattern, finally used for an actual conversation.

## Where it runs

Same process, same rules as the rest of Mission Control (`docs/MISSION-CONTROL.md`):
FastAPI + server-rendered HTML, no build step, HMAC-cookie auth, nothing served
unauthenticated, reads and writes the same Postgres the pipeline uses. The chat
logic itself lives in **`tools/azure-runner/chat_service.py`** — harness-agnostic,
imported by the web app the way `pipeline.py` already is, so a future Slack
surface (or the CLI) reuses sessions, ledger, and agent construction without
touching the web layer.

Model calls use the same Azure OpenAI client, deployment routing
(`LANTERN_MODEL_REASONING`/`_FAST`), and `set_default_openai_api` setup as the
orchestrator. If the Azure env vars are absent, chat pages render with an honest
"model backend not configured" notice instead of crashing the board.

## Backend: three tables, one bus

Schema (`tools/azure-runner/schema.sql`, idempotent like everything else there):

- **`chat_sessions`** — one row per conversation: `id` (the
  `consult:{user}:{agent}:{name}` string, which is *also* the Agents SDK
  session key, so the SDK's `agent_messages` rows and ours can never disagree
  about identity), `agent`, `title` (first message, renamable), `created_by`,
  optional `run_id` scope, `archived`, timestamps.
- **`chat_turns`** — one row per user turn, and the system's memory of *what
  was happening*: `user_text`, `final_text`, `status`
  (`running|done|failed|stopped`), `error`, **`trace`** (jsonb list of tool
  calls / specialist handoffs / notes, in order, with elapsed offsets), and the
  same token-ledger columns as `stage_executions` (`model`, `requests`,
  `input_tokens`, `cached_input_tokens`, `output_tokens`, `total_tokens`).
  Dollars are computed at render time by `est_cost_usd` — stored token counts
  are exact, prices stay provisional, same as the rest of the ledger (P0.4).
- **`custom_agents`** — `slug`, `name`, `purpose`, optional `instructions`,
  `model_pref` (`reasoning|fast`), `created_by`, `archived`. Custom agents get
  the consult toolset and `append_memory` under their own slug in `role_memory`
  (table-only — no `agents/<slug>/memory.md` is rendered; their unconsolidated
  rows are embedded into the next session's instructions instead), so a custom
  agent *accumulates judgement* like a fleet role does.

Conversation context (what the model re-reads each turn) stays in the Agents
SDK's own `agent_sessions`/`agent_messages` tables via `SQLAlchemySession` —
deliberately not parsed for display, because the SDK's message shape has
shifted between releases (see `usage_dict`'s defensive posture). The transcript
renders from `chat_turns`, which we own.

**Live activity** is an in-process `TurnBus`: per-session subscriber queues plus
a replay buffer for the active turn. `POST /chat/{sid}/send` starts the turn as
a background task; `GET /chat/{sid}/events` (SSE) replays what you missed, then
streams deltas, tool lines, and the final ledger. Refresh-safe and multi-tab
safe by construction: the page renders history from Postgres, then attaches to
the bus. Subscribers are per-SESSION and outlive turns — a page attached while
the conversation is idle must still hear the next turn (v1 had them per-turn
and went deaf; `test_chat_service.py` pins the regression). Known limit, stated
plainly: the bus is process-local, so Mission Control runs single-process (it
already does — one uvicorn, one systemd unit). Restarts and SSE: uvicorn waits
for open connections *before* it fires the app's shutdown hook, so an open
event stream would pin a restart until systemd's 90s kill — the unit and the
dev launcher therefore run with `--timeout-graceful-shutdown 3`, streams
self-end every 5 minutes (EventSource reconnects; replay rebuilds a live turn),
and the shutdown hook still releases whatever is left. A turn whose process
died is marked `failed («interrupted — mission control restarted mid-turn»)`
on next contact — including when a page reconnects to find nothing running —
rather than pretending to still run.

Every finished turn also lands one `consult` row in `events` (actor
`human:{user}`, `channel: web`, usage attached) — the CLI already does exactly
this, so the audit log sees one stream of consults regardless of surface.

## Frontend: three screens

1. **`/chat` — the hub.** Left rail: every past conversation (yours first,
   grouped Today / Earlier, the team's below — the *past chat history*
   requirement), each row carrying agent, title, age, and spend. Main surface: "Ask Lantern"
   hero card, the specialist gallery (fleet roles + custom agents, one card
   each: caps name, one-line charter description, model routing, memory count),
   and the composer. Pick an agent (or keep Lantern), type, Enter — that's a
   session. No separate "create conversation" step, no empty sessions littering
   history (the session row is created with its first message).
2. **`/chat/{sid}` — the conversation.** Claude-Code-anatomy transcript: `YOU`
   / agent caps labels, streamed text, tool lines with folded results,
   specialist handoffs shown as indented sub-consults, a working footer with
   phase + elapsed time + live tool count + Stop (Esc also stops, as in Claude
   Code; a stopped turn keeps the tokens it already burned), and a per-turn
   ledger line (model · tokens · cached % · est. $ · duration). Composer pinned
   at bottom with the advisory-line status footer ("UI-UX CONSULT · ADVISORY,
   READ-ONLY · $0.32 THIS CHAT" — or "NOTHING BILLED YET", which is the design
   system's own example copy). Sessions scoped to a run (`run_id` set) carry
   the run chip and the agent is pointed at the run folder in its instructions.

   **The reading window is fixed** — the rule the rest of the screen obeys.
   The shell is a frame (`min-height:0` on both columns, or a grid/flex child
   floors at its content height and a long conversation scrolls the whole
   page); the transcript owns the only scrollbar; and the client never scrolls
   on its own. Sending a message anchors that question at the top of the
   viewport and a tail spacer shrinks as the answer fills the space, so a long
   reply grows into a still frame. The view follows the bottom only for a
   reader already parked there; anyone who scrolls up keeps their place and
   gets a "↓ Jump to latest" pill instead. The end-of-turn swap (streamed text
   → server-rendered markdown) holds the turn's screen position across the
   replacement, so nothing jumps when a turn finishes.

   **Thinking is not shown.** Reasoning deltas and reasoning items drive the
   status line (`Thinking → Running read_file → Responding`, with elapsed and
   tool count) and are published with `persist=False` — never streamed into
   the reply, never written into the trace, so a replayed turn cannot leak
   them either. What the agent *did* is still fully on the record.

   **The composer never locks.** Typing during a turn is normal: a message
   sent while the agent works becomes a visible queued chip and goes out by
   itself when the turn ends (409-tolerant, since the bus clears just after
   the final event). `↑`/`↓` walk your own past messages, an unsent draft
   survives a reload (per session, in `localStorage`), a finished reply has a
   `copy` button, and traces longer than six tool calls fold behind a
   "N tool calls" summary instead of burying the answer.
3. **`/agents` — the roster.** Fleet roles (read from `agents/<role>/`, exactly
   what the orchestrator loads) and custom agents side by side with per-agent
   usage (sessions, tokens, est. $, memory entries). "New agent" is the
   Dust-style two-field form: name + what-it's-for; instructions optional
   ("leave empty and Lantern writes them from the purpose"); reasoning/fast
   routing choice. Archiving hides an agent from the gallery without touching
   its history.

Entry points from the rest of Mission Control: every stage card on a run page
gets "Consult ‹role› about this run", and the run header gets "Ask Lantern
about this run" — both open a run-scoped session. `/spend` gains a
"Chat & consults" section off `chat_turns`, so consult spend is visible next to
stage spend instead of hiding in the events log.

## Honesty rules (carried over, not new)

- A turn that crashed before usage arrived shows **unmetered**, never $0.00.
- Verdict-free rendering: the transcript shows what the agent actually did
  (tool lines from the trace), not a summary of it.
- The advisory/read-only line is on-screen at the composer, always.
- Browser roles (`ui-ux`, `qa-dev`, …) consult here **without** their Playwright
  MCP in v1 — the agent card says so ("browser tools: CLI consults only for
  now") instead of silently degrading. `pipeline.py ask -i` remains the path
  when a live browser matters.
- Live-ness is real: the working indicator is driven by the SSE socket, and a
  dead socket says "reconnecting", never a frozen spinner.

## Roadmap

- v1 (now): everything above. `tools/mission-control/test_chat_ux.py` pins the
  reading contract (fixed window, hidden thinking, queue, fold) with stdlib
  unittest — no database, no browser.
- v2: opt-in Playwright MCP for browser-role consults (`LANTERN_CHAT_BROWSER=1`);
  file/image drop into the composer; Slack surface reusing `chat_service`.
- v3: "promote this consult" — draft a brief from a conversation and hand it to
  `pipeline.py run` (the human still starts the run; the gate line does not move).
