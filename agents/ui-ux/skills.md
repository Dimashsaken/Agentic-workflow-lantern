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
- One artboard per surviving option, side by side; `rename_nodes` to the axis names.
- `write_html` grounded **only** in `design/design-system.md` tokens/components; off-
  token values are defects. All frames this run creates are yours; nothing else is.

### 3C. Critique loop (≤3 iterations per option)

`get_screenshot` → **layout pass** → fix → re-screenshot → **style pass** → fix,
per `design/critique-checklist.md` (the passes stay separate). Log iterations used
per option; stop at 3 and note unresolved items in `options.md`.

### 3D. Present for the gate

- `options.md`: per option — axis name, screens, trade-offs, judge score; end with a
  recommendation and the single strongest argument against it.
- Export every option's frames as **2x PNGs** into `01-ui-ux/`; get the Paper file
  URL for humans.
- Write `01-ui-ux/handoff.json` — the orchestrator builds the ux_signoff gate
  payload from it, so Mission Control can show the PNGs side by side:

```json
{
  "paper_url": "https://…",
  "recommended": "<axis-name>",
  "options": [{"name": "<axis>", "pngs": ["workflow/runs/<run-id>/01-ui-ux/<axis>@2x.png"],
               "status": "presented"}],
  "video": null,
  "metrics": {"divergence_generated": 8, "critique_iterations": {"<axis>": 2},
              "paper_calls_estimate": 0}
}
```

### 3E. After the gate

Approval of the recommended option needs nothing more — the package (§4) must
already exist for it. If the human wants a different option, the gate comes back
rejected with a note naming it: on retry (same session memory), build §4 for that
option, mark the others' artboards `[rejected] <axis>`, keep them on canvas with one
PNG each, update `handoff.json` statuses (`chosen` / `rejected`).

## 4. The handoff package (recommended/chosen option) → `01-ui-ux/`

1. **2x PNGs of every frame** — the acceptance references the coding agent will
   screenshot-diff against.
2. **`get_jsx` per frame** → `jsx/<frame>.jsx` — structural source of truth, a
   starting point, NOT production code.
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

- Re-read (`get_selection` / `get_node_info`) before writing any frame a human may
  have touched since you last saw it.
- Never `delete_nodes` outside frames created this run.
- Call `finish_working_on_nodes` when done with a frame.
- Long sessions degrade: one run per MCP connection; reconnect rather than push on.

## 6. Session end

Report per template, including the divergence scores, critique-iteration counts, and
unresolved checklist items. Memory: append any pattern decision (chosen or rejected +
why) and any critique item that kept recurring — recurring items graduate into
`design/critique-checklist.md`.
