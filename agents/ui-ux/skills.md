# Skills — ui-ux

## 1. Session start

Read charter → this file → memory → run folder (brief first). Confirm run ID. If the
brief lacks a success metric or target user, mark BLOCKED with that one question.

Then load the constraint layer: `design/design-system.md` and
`design/critique-checklist.md`. If design-system.md still carries its UNPOPULATED
marker, say so in `options.md` and ground yourself in product screenshots instead —
never generate from taste alone.

## 2. Flow mapping

- Walk the brief as the user: entry point → steps → success. Write it as a numbered
  narrative before any visuals.
- For every step list the non-happy states: empty, loading, error, no-permission,
  slow-network, mobile. A flow without these is not done.
- Check memory for patterns that failed before in similar flows.

## 3. Producing options — divergence, then convergence

Stage 1 runs as two executions with different runners (plan:
`docs/plans/ui-ux-agent-paper.md`). Your assignment says which phase you are in.

### 3A. Divergence (`01-ui-ux.diverge` — EC2, fast model, no Paper)

- Generate **5–10 low-fi HTML skeletons** in `01-ui-ux/divergence/`, each named for
  the **structural axis** it explores (wizard, single-page, inline-edit, split-pane,
  …) — axes differ in *structure*, never in colour. Grayscale, realistic copy.
- **Judge pass:** score every skeleton against the brief (task success, step count
  for the primary task, state coverage, fit with existing product patterns). Keep
  the best 2–3; record all scores and the cut in `report.md` — the losers' names and
  one-line reasons stay, so nobody re-explores a dead axis.

### 3B. Convergence in Paper (`01-ui-ux.design` — design workstation)

- First `tools/list` — **discover the live Paper tool names, never assume them**
  (they drift; docs and third parties disagree on the count).
- **Work only in the agent-owned file (hard rule).** Your assignment names it
  (`LANTERN_PAPER_FILE_ID`); it is already open in the Desktop app. `create_page`
  named after the run ID, `open_file` with that fileId **and** pageId, then build.
  Never create a new file unattended, and never create/edit/restyle/rename/delete
  anything in a file a human made — those are read-only references you may
  `get_tokens` / `get_screenshot` for grounding. Pass `fileId` on **every** call, so
  touching someone else's canvas is structurally impossible.
- Copy the product's tokens into your file once (`get_tokens` on the reference file →
  `create_tokens` in yours) so every write is token-grounded by construction.
- **Mount rule (why the file is fixed):** nodes created in a file that has never been
  rendered do not mount — screenshots/exports return empty ("No DOM element"), and
  `open_file` does NOT switch the visible tab across files, so a brand-new file
  cannot mount without a human click. *Page* switches inside the already-open file
  do mount. Nodes created pre-mount are dead: delete and recreate, never try to
  style them into life. If no agent-owned file is configured, go BLOCKED (§6).
- One artboard per surviving option, side by side; `rename_nodes` to the axis names.
- **Only present what you built this run.** Record the node id `create_artboard`
  returns for each option and present exactly those. Artboards that already existed on
  the page are NOT yours — never adopt, rename, re-label, or export one as your
  option, even if its page is named after this run. If an option has no artboard you
  created, it is not an option: build it or drop it from `options.md`.
- **Never claim an artifact you did not produce.** Every path in `handoff.json` must
  be a file that exists on disk when you finish. Paper's `export` writes to the
  workstation's export folder, so bring each file in yourself: `list_exports()` to see
  what Paper wrote, then `collect_export("<name>@2x.png",
  "workflow/runs/<run-id>/01-ui-ux/<axis>@2x.png")` for each one. There is no
  "artifact collector" that will do this later. The orchestrator checks every claimed
  path and fails the stage if one is missing or empty.
- `write_html` grounded **only** in `design/design-system.md` tokens/components; off-
  token values are defects. All frames this run creates are yours; nothing else is.
- **Keep the product shell on every screen** (design-system.md "Spacing & layout"):
  the 64px icon rail, the caps tab rail with the active tab underlined, the ~400px
  conversation column with Lantern/You and the pinned input, and the caps status
  footer. Dropping any of them is not a design choice — it is a different product.

### 3B-html. Convergence without Paper (`01-ui-ux.design`, design mode `html` — D25)

When the run's design mode is `html` (the brief's `- **Design mode:** html`, or
`pipeline.py set-design-mode <run> html`), this execution runs on the **ec2 runner
with the `playwright` browser and no Paper tools** — for teams and runs without a
design workstation. Same inputs (the divergence survivors and their scores), same
critique loop, same gate; only the medium changes:

- Converge each surviving option into **one self-contained HTML prototype** at
  `01-ui-ux/prototype/<axis>.html`: inline CSS only, every value traceable to
  `design/design-system.md` tokens, realistic copy, every state the flow needs
  (empty / loading / error / permission) on the same page or in clearly labelled
  panels, ~1440px wide. No external fonts, scripts or images.
- Open it with `browser_navigate` on its `file://` URL (the run folder's absolute
  path is in your prompt) and critique from `browser_take_screenshot` exactly as §3C
  describes — layout pass, style pass, ≤3 iterations, every pass logged in
  `critique-log.md`. Fix by rewriting the HTML with `write_file`, then reload.
- The final screenshot of each option IS its handoff PNG: call
  `browser_take_screenshot` with `filename: "<axis>@2x.png"` and `fullPage: true`.
  The browser runs at device scale 2 and writes into `01-ui-ux/media/`, so
  `handoff.json` cites `workflow/runs/<run-id>/01-ui-ux/media/<axis>@2x.png`.
- `handoff.json` (§3D) carries `"design_mode": "html"`, `"paper_url": null`, and per
  option `"prototype": "workflow/runs/<run-id>/01-ui-ux/prototype/<axis>.html"`.
  There is **no `jsx/`** in this mode — the prototype file is the structural handoff
  the coding agent rebuilds from, and the orchestrator checks it exists and is real.
- Everything else in §3D and §4 still applies: `options.md`, `flow-spec.md` for the
  recommended option, the critique log, the design-system version.

### 3C. Critique loop (≤3 iterations per option) — and prove it ran

`get_screenshot` renders only the app's **active page**: before your first
screenshot, call `open_file(<file id>, pageId=<your run page>)` to make your page
active — a screenshot of a node on an inactive page silently returns empty, not an
error (observed 2026-08-31). If screenshots return empty even for the active page,
the Desktop app's capture path is degraded: go BLOCKED and ask for a Paper Desktop
restart — do not substitute exports or memory for critique evidence.

`get_screenshot` → **layout pass** → fix → re-screenshot → **style pass** → fix,
per `design/critique-checklist.md` (the passes stay separate). Stop at 3 and note
unresolved items in `options.md`.

**Write `01-ui-ux/critique-log.md` as you go** — one short block per option per pass:
what the screenshot showed, which checklist item failed, what you changed, and the
verdict after re-screenshotting. A pass that found nothing says so explicitly and
names the two items you checked hardest. This file is the only evidence the loop
actually happened; `metrics.critique_iterations` is a claim, and the orchestrator
fails the stage without the log. If you cannot see a screenshot, say that in the log
and go BLOCKED — never report a pass you could not perform.

The defect this loop misses most often is the **empty bottom third** (both of the
first two agent runs shipped it). Before you call an option done, look at the bottom
of every column and apply the empty-bottom test in the checklist.

### 3D. Present for the gate

- `options.md`: per option — axis name, screens, trade-offs, judge score; end with a
  recommendation and the single strongest argument against it.
- Export every option's frames as **2x PNGs** into `01-ui-ux/`; get the Paper file
  URL for humans.
- JSX for **every presented option** — not only the recommended one, since the
  gate-picker may choose any. Call
  `collect_jsx(<node id>, "workflow/runs/<run-id>/01-ui-ux/jsx/<axis>.jsx")` per
  option: the host calls Paper's `get_jsx` itself and writes the full output
  (typically 7–15 KB) verbatim to disk. **Never call `get_jsx` yourself for the
  handoff and never write a jsx file with `write_file`** — output copied through
  your context gets truncated (attempt 5 of feat-20260831 handed off ~1.5 KB
  summaries of 7–9 KB artboards), and the orchestrator now hash-checks every jsx
  file against what collect_jsx wrote, so a hand-written or edited file fails the
  stage. Unlike `get_screenshot` (§3C), `get_jsx` is not capture-session-limited —
  it works from any MCP session (verified 2026-08-31), so collect_jsx never needs a
  Desktop restart.
- Write `01-ui-ux/handoff.json` — the orchestrator builds the ux_signoff gate
  payload from it, so Mission Control can show the PNGs side by side:

```json
{
  "design_mode": "paper",
  "paper_url": "https://…",
  "recommended": "<axis-name>",
  "options": [{"name": "<axis>", "pngs": ["workflow/runs/<run-id>/01-ui-ux/<axis>@2x.png"],
               "status": "presented"}],
  "video": null,
  "metrics": {"divergence_generated": 8, "critique_iterations": {"<axis>": 2},
              "paper_calls_estimate": 0}
}
```

In design mode `html` (§3B-html): `"design_mode": "html"`, `"paper_url": null`, each
option adds `"prototype": "workflow/runs/<run-id>/01-ui-ux/prototype/<axis>.html"` and
its PNGs live under `01-ui-ux/media/`.

### 3E. After the gate

Approval of the recommended option needs nothing more — the package (§4) must
already exist for it. If the human wants a different option, the gate comes back
rejected with a note naming it: on retry (same session memory), build §4 for that
option, mark the others' artboards `[rejected] <axis>`, keep them on canvas with one
PNG each, update `handoff.json` statuses (`chosen` / `rejected`).

## 4. The handoff package (recommended/chosen option) → `01-ui-ux/`

0. **Before you write anything, re-read your own output.** Screenshot each frame one
   last time and check: product shell intact (rail, tab rail, conversation column,
   status footer)? bottom third of every column carrying content? every colour and
   size traceable to `design/design-system.md`? Fix, then package.
1. **2x PNGs of every frame** — the acceptance references the coding agent will
   screenshot-diff against.
2. **`collect_jsx(<node id>, ".../jsx/<frame>.jsx")` per frame** — structural source
   of truth, a starting point, NOT production code. The host writes the full
   `get_jsx` output verbatim; the coding agent reads this file to rebuild the screen
   and cannot open Paper. A node id, a URL, or a summary is NOT a handoff — and
   neither is JSX you copied through your own context: the orchestrator rejects any
   jsx file that does not hash-match what collect_jsx wrote (§3D).
3. The `design/design-system.md` version used (copy the file in, or record its git
   hash in the report).
4. `flow-spec.md` — screens, transitions, all states (empty/loading/error), exact
   copy.
5. Paper file/artboard URL in `options.md` + `handoff.json`.
6. **Walkthrough video:** try Paper's MP4 export first; if the flow needs real
   interaction to be judged, build a throwaway prototype in `01-ui-ux/prototype/`
   (fake data, realistic copy) and record with `tools/qa-recorder` — slow, deliberate
   actions, error state included. Upload, link in the report with a shot list.

## 5. Canvas etiquette (multiplayer safety)

- **Never write into a human's file.** The agent-owned file named in your assignment
  is the only place you create, edit, or delete. Human files are read-only references
  you may read for grounding (§3B).
- Re-read (`get_selection` / `get_node_info`) before writing any frame a human may
  have touched since you last saw it.
- Never `delete_nodes` outside frames created this run.
- Call `finish_working_on_nodes` when done with a frame.
- Long sessions degrade: one run per MCP connection; reconnect rather than push on.

## 6. Session end — including when you are BLOCKED

Report per template, including the divergence scores, critique-iteration counts, and
unresolved checklist items. Memory (via the `append_memory` tool): record any pattern
decision (chosen or rejected + why) and any critique item that kept recurring —
recurring items graduate into `design/critique-checklist.md`.

**Blocking is not an exit from the contract.** If you stop early, you still write
both: the report with `Status: BLOCKED` and exactly one precise question, and the
memory entry (what blocked you and why — that is a durable learning). The runboard
renders itself from the pipeline database — you never write it. A blocked stage that
writes nothing leaves the next session with no idea what happened, and the
orchestrator will fail the stage anyway.
