# Mission Control

Mission Control opens on the work that needs attention. The primary navigation is
**Work**, **Reviews**, and **Chat**. Agents, factory configuration, and costs are in
**Workspace**; theme, keyboard help, and sign-out are under the user's name.

- **Work** `/`: a single searchable list, with reviews and blocked work first.
  Active, Needs review, Completed, and All work filters retain the search query.
  Search matches the run name, repository, owner, and current activity. `/runs`
  opens the same view with all history selected. Each row keeps a compact stage
  path, current position, and current agent activity visible.
- **Reviews** `/gates`: compact summaries, oldest first. Open a review to see the
  full artifact and decision form. Recent decisions and review timing are folded
  below the queue. Existing `#gate-<id>` links reveal the matching evidence.
- **Run** `/run/<id>`: an always-visible lifecycle connects the brief to staging
  QA, with the current stage, human handoff, and next step. Click a stage to inspect
  its agents, attempts, and evidence. Parallel builders remain separate. A return
  from QA appears as a rework arrow with its reason; previous-cycle evidence is
  retained without marking downstream stages complete. Bug runs show their debug
  lifecycle, including conditional planning. Repository and branch stay visible;
  full execution lanes, reports, and audit history open on demand.
- **Chat** `/chat`: describe the work to Lantern. Specialist selection is optional,
  and links from a run preserve the chosen role and run context. On phones,
  conversation history is available from the Conversations disclosure.

The full execution trace, acceptance-criterion matrix, catalog, and cost views remain
available. Decisions still use the authenticated server routes and the existing human
confirmation rules. The work list itself has no approval shortcuts: it takes the
reviewer to the evidence.

The interface is server-rendered Python with native HTML forms and disclosures,
shared CSS, and small JavaScript enhancements. No frontend build step or dependency
was added. Light is the default; dark is a per-browser preference. `j`/`k` move through
visible work or executions, Enter opens, `a`/`r` act on a focused review, `t` opens the
criterion matrix, `d` changes theme, and `?` opens keyboard help. Typing or opening a
disclosure pauses automatic refresh so it cannot discard the reader's context.

Implementation: `tools/mission-control/worklist.py`, `app.py`, `ui.py`, `chat.py`,
`lanes.py`, `lifecycle.py`. Tests: `python -m unittest discover -s tools/mission-control -p 'test_*.py'`.

Lifecycle references: [Super Simple Software Factory](https://github.com/disler/super-simple-software-factory)
uses compact phase indicators and a selectable session trace; [Last Light](https://lastlight.dev/)
shows workflow stages and review loops. Lantern adapts those interaction patterns
to its existing fixed pipeline, without adding a workflow editor or copying code.
Stage position comes from the run, attempts from executions, and rework reasons
from recorded events. Missing execution evidence is labeled, not inferred as success.
The work list uses the latest execution snapshot; the run page shows full attempts
and the most recent rework among its latest 100 audit events. Both retain the
existing 30-second refresh behavior; they are not a live agent stream.

## Earlier design and evidence

The following describes the v3 implementation before the September 11 simplification.
Its evidence, accounting, and gate-integrity rules remain applicable; the screen
arrangement above supersedes the older Inbox + Board presentation.

## Mission Control v3 — the software factory's face

Where developers *see* the factory. Design principle (from
`docs/research/karpathy-agentic-loops.md`): the human's job in an agentic loop is
**verification**, so the UI is a verification surface first and a dashboard second —
"make the generation-verification loop go as fast as possible."

v3 (D22) adds the two bars the reference designs set
(`docs/plans/software-factory-alignment.md` §1 rule 5, §2 row 10):

- **IndyDevDan's dashboard** — sessions as swim lanes, the compiled prompt, per-phase
  cost, restart from here. That is the run page, the execution drawer, and `/cost`.
- **HumanLayer's workspace** — one glance = what runs, what needs me, what it cost;
  one click = act. That is Home: the Inbox above the Board, every gate card leading
  with the artifact being decided, Approve/Reject on the card.

## Where it runs

`tools/mission-control/app.py` — FastAPI + server-rendered HTML (no build step, no
JS framework), served from the same host as the orchestrator (port 8080, its own
systemd unit `lantern-mission-control.service`). It reads the same Postgres the
pipeline writes and the same run folders the agents write, so there is no second
source of truth. Expose it via Tailscale (recommended) or a security-group-allowlisted
IP plus the built-in login — never open to the internet.

Modules: `ui.py` (tokens, CSS, the page shell, the vanilla-JS layer), `lanes.py`
(the swim-lane model), `drawer.py` (one execution, end to end), `traceability.py`
(the matrix), `catalog.py` (the factory catalog), `cost.py` (aggregation and
tripwires), `chat.py` (the chat surface, docs/CHAT.md), `workspace.py` (the repo
picker's boundary).

## What each page answers

| Page | The question it answers |
|------|-------------------------|
| **Home** `/` | *What needs me, and what is the factory doing?* The **Inbox** lists every pending gate oldest first, each card opening with the artifact under decision and carrying Approve/Reject. Below it the gate-latency ledger, then the **Board** — runs as tickets in five workflow columns (Queued · Running · Blocked · Review · Done) with the 8-stage pipeline as a rail on each card. |
| **Run** `/run/<id>` | *What ran, in what order, for how much?* **Swim lanes**: one lane per stage execution key in the order they started, each attempt a bar sized by duration, gate diamonds between lanes, per-lane tier / tokens / estimated cost. Below: the stage folders (reports, artifacts, videos, consults) and the audit log. |
| **Execution drawer** `/run/<id>/exec/<n>` | *What did this execution actually do?* The compiled system prompt and kickoff, the tool-call timeline, the report, the typed envelope with its validation result, the quality gate, the memory rows it appended, its ledger — and the loop actions, retry and rework-to. |
| **Traceability** `/run/<id>/trace` | *Is the contract kept?* Story criteria × plan tasks × coding commits × QA charter sections × validation verdicts, as a matrix of status chips. |
| **Factory** `/factory` | *What is this factory made of?* Roles with their missions and tiers, the fixed pipeline and its gates, the model stack with its fallback chain resolved, each product's `lantern.toml` quality commands, eval numbers, and the builders a plan declares. Read-only, from files and the environment. |
| **Cost** `/cost` | *What did it cost, and are we near a limit?* Per run, per day, per model, plus both tripwires with what has already fired. |
| **Gates** `/gates` | The same gate cards as the Inbox, plus the decided history. |
| **Runs** `/runs` | Every run as a flight strip, open above closed. |
| **Chat** `/chat` · **Agents** `/agents` | Consult mode on the web (docs/CHAT.md, D13). |

`/spend` redirects to `/cost`.

## The keyboard map

Every action also has a link or a button — the keys only shorten the path, and nothing
client-side can decide a gate.

| Key | Does |
|-----|------|
| `j` / `k` (or ↓ / ↑) | move between gate cards, run rows, execution bars |
| `Enter` | open what is focused (the run, or the execution drawer) |
| `a` | approve the focused gate — asks first, and says so when the report is BLOCKED |
| `r` | reject the focused gate; prompts for the note, which is required |
| `o` | open the focused row as a full page |
| `t` | the traceability matrix of the run you are on |
| `h` | home |
| `d` | dark mode on / off (white is the default) |
| `Esc` | close the drawer, drop focus |
| `?` | show this map in the corner |

Typing in a field disables the single-key shortcuts; `Esc` leaves the field.

## One style: white

Every page is white, on every machine, whatever the operating system prefers. The
palette lives once on the bare `:root`; surfaces are white and the hairline does the
separating, with the raised tones kept for hover, controls and the "needs you" tint.
Form fields — the login, a gate's decision note, the repo picker, the drawer's rework
select, the chat composer, the new-agent form — share one rule, so a field looks the
same wherever it appears.

**The operating system is deliberately not consulted.** A gate gets discussed in a
screenshot, a review and a call; if the palette followed each reader's OS, the same
page would look different to each of them. Dark remains available as a per-browser
opt-in (`d`, or the top-bar button) for anyone who wants it, stored in `localStorage`
and applied by a tiny inline script before first paint. The dark ladder is the design
system's original palette (tokens contentHash 288d9538), kept intact under
`:root[data-theme=dark]`.

## On a phone

One column below 820px: the board's five columns stack, the swim lanes fold each lane
into a block (stage, tier, bar, cost), the drawer becomes a full-width sheet, the top
bar wraps its nav onto a second line. Wide content — tables, prompts, tool output —
scrolls inside its own container; the page itself never scrolls sideways.

## The trace file — what the drawer reads

`tools/azure-runner/factory.py` writes `<run>/<stage-dir>/trace/<execution-key>.json`
after the agent's last turn, from both executors (`orchestrator.main` and
`pipeline.run_agent_stage` call it with one two-line hook each, right after
`result = results[-1]`).

```json
{
  "kind": "trace", "run_id": "…", "stage": "00-story.scout",
  "execution_key": "…:00-story.scout:2", "written_at": "…",
  "instructions": "the compiled system prompt, redacted",
  "instructions_chars": 25917,
  "kickoff": "the first user turn",
  "turns":      [{"turn": 1, "usage": {…}, "final_output": "…", "items": 71}],
  "tool_calls": [{"order": 1, "turn": 1, "name": "read_file",
                  "args": "…", "args_chars": 41,
                  "output": "…", "output_chars": 2629, "seconds": null}],
  "usage": {"requests": 9, "input_tokens": 126694, "…": 0},
  "redaction": {"qa_target_dropped": false, "secret_values_known": 5}
}
```

Rules it obeys:

- **It never fails a stage.** A trace is observability, not a postcondition: every
  error inside `write_trace` becomes one line on stderr.
- **It never carries a secret.** Redaction happens *before* the file exists: the whole
  `# QA target` section (the environment's test login) is dropped, credential-shaped
  text is masked (`password: …`, `Bearer …`, `SOME_TOKEN=…`, `scheme://user:pass@host`,
  known key shapes), and the values of secret-looking environment variables are
  scrubbed wherever they appear. A value that is an ordinary short lowercase word is
  deliberately *not* scrubbed wherever it appears — the local database password is
  literally `lantern`, and blanket-masking it rewrote every `lantern.toml` path in a
  trace as `[redacted].toml`; such a value is still masked where it reads as a
  credential. Proof: `tools/azure-runner/test_trace.py`.
- **It is truncated, and says so.** Arguments keep 600 characters, tool output 1500,
  each turn's final output 4000; the drawer prints how much was cut.
- **Filenames are Windows-safe.** Execution keys carry colons, so the filename
  replaces every character outside `[A-Za-z0-9._-]`.

Executions from before D22 have no trace, and the drawer says so plainly rather than
showing an empty panel.

## Honesty rules (carried over, not new)

- **Presence AND validity.** A gate card renders the artifact it is deciding, and says
  when a named artifact is missing — a PNG the handoff names but the run folder no
  longer holds is stated in words, not served as a broken image.
- **A report's own verdict outranks the database.** A stage execution can be
  `succeeded` while its report's last `Status:` line says `BLOCKED`; that disagreement
  is shown on the card, and approving asks again.
- **Unmetered is never $0.00.** An execution that crashed before its usage line has no
  token counts; every ledger view counts it separately and says real spend is higher.
- **Bars are ordered, not scaled to a clock.** A lane's bars sit in the order the
  executions started, and their fill is the duration against the run's longest
  execution. Two builders that truly ran in parallel therefore appear in adjacent
  columns, not stacked — the exact start and finish times are in the bar's tooltip and
  in the drawer.
- **The matrix traces by identifier only.** A commit or charter section counts for a
  criterion when it names the `AC-n` id or a plan task mapped to it. Prose similarity
  would be a guess dressed as evidence; untraced commits and orphan charter sections
  are listed under the matrix instead.

## Gate integrity in the UI

**Nothing is served unauthenticated** — every page redirects to a login screen;
sessions are HMAC-signed cookies (7-day TTL, key from `LANTERN_WEB_SECRET`, falling
back to a hash of `LANTERN_WEB_USERS`). Decisions write the `approvals` row with
actor + timestamp + note (`channel='web'`) — the same fail-closed contract as the CLI
(D8), and the same event names, so one audit stream covers both surfaces. No users
configured → nobody can log in at all. Agents have no route here.

The drawer's **retry** and **rework-to** are the only other writes, and they call the
pipeline's own primitives with the web user as the actor: retry re-queues a *failed*
run at its current stage, rework sends a failed or waiting run back to an earlier
`REWORK_TARGETS` stage through `pipeline.cmd_rework`. Approvals are never decided
there.

## Roadmap

- v1: Inbox, Board, Run timeline, polling refresh. **Done.**
- v2: Chat + Agents, SSE streaming, chat spend in the ledger. **Done.**
- v3 (now): Inbox-first home with artifact-led gate cards, swim lanes, the execution
  drawer over the trace file, the traceability matrix, the factory catalog, the cost
  page, light mode, the keyboard map, phone layout. **Done.**
- v4: per-tool-call timings (needs a streamed run, not the final result); SSE on the
  run page so a live execution's lane grows without a reload; inline `<video>` playback
  via presigned S3 URLs; a brief-composer form; the debug lifecycle's own lane table
  once `pipeline.py bug` lands (D20).
