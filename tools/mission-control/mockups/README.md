# Mission Control v2 — board mockups

Three static directions for the Board, built on **real rows copied from the box**
(`54.166.128.138`, `lantern` DB, read at **2026-08-27 12:45 UTC**). Nothing here is
invented data. Open them from this folder — they share `tokens.css`.

| | File | Screenshots |
|-|------|-------------|
| **A** | `board-a-stage-lanes.html` | `shots/a-1440.png` · `shots/a-1920.png` |
| **B** | `board-b-obligation.html` | `shots/b-1440.png` · `shots/b-1920.png` |
| **C** | `board-c-flight-strips.html` | `shots/c-1440.png` · `shots/c-1920.png` |

---

## 1. What the references actually are (read, not remembered)

### openai/symphony — its dashboard is *not* a board

I read the real source: `elixir/priv/static/dashboard.css` (471 lines),
`lib/symphony_elixir_web/live/dashboard_live.ex` (446), `presenter.ex`, `router.ex`.

The brief assumed Symphony's dashboard is a dense dark ops board. **It isn't.** It is:

- **Light mode.** `--page:#f7f7f8`, `--ink:#202123`, `--accent:#10a37f` (OpenAI green),
  a radial green wash behind the body, `backdrop-filter: blur(18px)` glass cards,
  28px hero radius, 22–24px card radii, `--shadow-lg: 0 20px 50px rgba(15,23,42,.08)`.
- **Not a kanban.** One hero card, a 5-up metric grid, then **three data tables** —
  *Running sessions*, *Blocked sessions*, *Retry queue* — plus a `<pre>` dump of the
  rate-limit snapshot. There are no columns and nothing moves.

The "board is the control plane" idea in Symphony lives in the **external tracker**
(Linear/GitHub board states: Backlog → Todo → In Progress → Human Review → Merging),
not in this dashboard. So Symphony cannot be the reference for how Lantern's board
*looks*. What it does give us, and what I took:

- **Triage by obligation, not by stage.** Three tables split by what a human owes:
  running (watch), blocked (act), retrying (wait).
- **Row anatomy for a live agent session:** identifier → state badge → session →
  runtime/turns → *last event* (human message on top, raw event name + timestamp
  underneath) → tokens as `Total` with `In / Out` beneath.
- **Live vs Offline** driven purely by socket state (`.phx-connected` toggles which
  badge displays) — never a fake "live".
- **Empty states written as sentences:** "No active sessions." / "No issues are
  currently backing off."
- `font-variant-numeric: tabular-nums slashed-zero` on every number. Adopted.
- API shape confirmed: `GET /`, `GET /api/v1/state`, `POST /api/v1/refresh`,
  `GET /api/v1/:issue_identifier`, and every table row deep-links to its JSON.

### Fredrin — the kanban interaction model

Columns are **BACKLOG · RUNNING · BLOCKED · REVIEW · COMPLETED**, each with a count in
the header. A ticket card carries: mono ticket ID (`WEBS-9QDM4LJR`), title, relative
time ("3h ago"), agent/board association, priority. Branch → PR → CI flow back onto the
card. Same conclusion as Symphony: **columns are obligation states, not pipeline
stages.** Borrowed the model; no branding or trade dress taken.

### Lantern's house style wins where they conflict

Everything visual comes from `design/design-system.md` (contentHash `288d9538`) and the
realized screens in `workflow/runs/feat-20260825-*/01-ui-ux/*.png`. All three mockups
use only listed literals. Two deliberate calls, both flagged below rather than silently
taken.

---

## 2. The three directions

### A — Stage lanes (`board-a-stage-lanes.html`)

Seven columns, one per pipeline stage, edge to edge. Today's model, rebuilt dense.
Reading is left→right through the pipeline exactly as the pipeline runs.

- **For:** the only direction where "where is this run?" is answered by *position*.
  Lane headers carry the actor (`🤖 agent · ec2` / `👤 human · Codex CLI`).
- **Against:** with 2 open runs, **5 of 7 lanes are empty** — visible in the shot. It
  only earns the screen when the fleet is busy. Cards at ~187px force the run ID to
  wrap to two lines, and there is no room for the token ledger without truncating it.

### B — Obligation lanes + narrator (`board-b-obligation.html`)

The house shell kept intact: Lantern narrates in the left ~400px column, the working
surface is on the right. Four lanes by **who owes the next move** — NEEDS YOU · AGENTS
WORKING · STUCK · CLOSED. Stage becomes a rail on the card.

- **For:** best "what needs me?" read of the three, and the only one that keeps the
  house shell's conversation column and first-person voice. The narration does real
  work — it says *why* both runs are stuck and what it would cost to fix.
- **Against:** the narrator eats 28% of a 1440px screen, and three of four lanes are
  one paragraph tall with ~700px of dead space beneath them. Columns are the wrong
  container for a set this uneven.

### C — Flight strips (`board-c-flight-strips.html`) ← **my recommendation**

One run, one row. Grouped by obligation with section headers (NEEDS YOU 2 · AGENTS
WORKING 0 · STUCK 0 · CLOSED 8), the seven stages compressed to a rail inside each row,
and columns for verdict / waiting-on / elapsed / model / tokens / est. $.

- **For:** this is Symphony's proven IA in Lantern's house style. It is the only one of
  the three that still reads at forty runs — rows grow down, columns don't grow across.
  Every row carries the full ledger without truncation. Empty groups collapse to one
  honest line instead of a dead column. Scans cleanly at both 1440 and 1920.
- **Against:** you lose position-as-stage; you read the rail instead. Less "kanban".

---

## 3. What the real data made the board say

The most valuable thing the redesign does is not layout. Reading the live rows, the
board's headline writes itself, and it is a real problem:

> Both open runs are parked at the same gate and both of their plans came back
> **BLOCKED** — `stage_executions.status = 'succeeded'`, but the stage report's own
> `Status:` line says BLOCKED, with two blockers each (`product_repo` is NULL, and no
> UX choice was ever recorded). The `plan_signoff` gates opened anyway.

That is the vacuous-gate failure mode, live in the database right now. Commit `5f3f653`
fixed the cause this morning; these two gates predate it. **Today's UI cannot show
this** — it renders `succeeded` as a green badge and offers Approve. So:

> **Verdict is a first-class column.** The board reads the stage report's `Status:`
> line, not just the DB status, and shows them when they disagree.

Other things the real rows forced into the design, all visible in the shots:

- **`workstation` has no row in `runners` at all** — never seen, not merely stale. Both
  the "1 / 2 runners" readout and the STUCK lane say so, and STUCK explains what the
  next stage-1 run will do about it.
- **Cost is small and should look small.** $0.58 + $0.40 = **$0.98** against the new
  $50/day tripwire — rendered as "2% of the daily tripwire", not an alarm. Cached share
  (84% / 88%) is the interesting number, so it sits under the token count.
- **Closed runs have no ledger.** Every pre-P0.4 row shows `— unmetered / no ledger`
  rather than `$0.00`, which would be a lie.
- **Retries are the fleet's real story.** 5 failed sandbox attempts on Aug 26, 3
  recovered — with the actual error strings (`sandbox exited 23: dir "/work/lantern/
  tools" failed: Permission denied`, `exited 137`). This fills the bottom third of A
  and C with something a person would actually read.
- **A dead artifact stays dead.** `demo-onboarding`'s only `qa_video` points at
  `example-bucket.s3.amazonaws.com` — shown as "video link points at a dead bucket".

Gate ages are real: both opened 02:06 UTC, **10h 39m** ago. The only two gates ever
actually decided (`ux_signoff` #3 and #4) took **20h 16m**.

---

## 4. Design-system items — proposing, not inventing

Per the house rule, these are proposals for your call, not changes I made to
`design-system.md`:

1. **`ADAM.CG PRO` is not vendored and is licensed.** No font file exists anywhere in
   the repo. The mockups declare `'ADAM.CG PRO', 'Figtree', …` and degrade to Figtree
   caps + `.14em` tracking, which is close but not it. Before ship: license and
   self-host a `.woff2` (Mission Control is Tailscale-only, so no CDN), or formally
   adopt the fallback. Same question for Figtree and JetBrains Mono, which are open but
   also not vendored.
2. **The conversation column is a product pattern, not a shell law.** The house shell
   says every screen is "left column ≈440px = the conversation". Mission Control is an
   ops board, not a conversational product. B keeps it (as *narration*, not chat); A
   and C drop it. If C wins, I'd propose the shell rule be restated as "left column =
   Lantern's voice, present when there is something to say".
3. **Progress uses the night→dawn ramp, not the accent.** A run's position in the
   pipeline is an ordered quantity, so the stage rail is `--night-2` (done) →
   `--dawn-4` (current) → `--surface-3` (not started) → `--danger` (failed). That keeps
   `--accent` scarce for the one real action per screen. Both A and C have exactly one
   amber control ("Open both plan gates"); B has one ("Read the plan, then decide").
4. **Verdicts never go on the ramp.** `BLOCKED` in prose is `--danger`, never
   `--dawn-4` — the ramp is "ordered quantities ONLY, never verdicts". I had this wrong
   in the first pass and fixed it.
5. **No new colors were introduced.** Three near-black chip backgrounds (`#231517`,
   `#3A211E`, `#3A2D18`, `#1B3D28`, `#3A2A1E`, `#2E2A22`) are borders/fills derived
   between listed tokens. If you want these formalized, they should become
   `--danger-soft` / `--accent-border` / etc. in the token file rather than staying
   inline.

---

## 5. Not yet built

These mockups cover **screen 1 only** (the Board), as agreed — I stopped before
implementing so you can pick a direction. Still to design once you choose:

- **Gate inbox.** Note the payloads differ sharply: `ux_signoff` carries a rich handoff
  (3 options with axis text, PNG paths, `recommended`, and a metrics block —
  `divergence_generated: 8`, `divergence_kept: 3`, per-option critique iterations, and
  an honest `png_scale: "1x — 2x export blocked on canvas viewport"`). `plan_signoff`
  carries **only** `{stage, run_folder}` — so that gate must render the plan report
  itself, and the inbox must degrade per gate kind.
- **Run detail** — per-stage verification timeline with attempts and error strings,
  reports as HTML, artifacts/videos, per-stage cost, event log.
- **Spend view** off the ledger, matching `pipeline.py usage` (per-day and per-run, per
  model, cached share; rates $4 / $1 cached / $20 per 1M, all provisional).

Gate integrity is untouched in all three: approvals stay a server-side
`POST /gate/{approval_id}/{decision}` into the `approvals` table, fail-closed, with the
existing allowlist. Nothing in these mockups holds state that could approve anything.
