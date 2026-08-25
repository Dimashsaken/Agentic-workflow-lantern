# Plan — the UI/UX agent on Paper (paper.design) MCP

> **Status (2026-08-25):** the repo side of Phases 1–3 is implemented (decision D9) —
> the loop is encoded in `agents/ui-ux/skills.md`, the constraint layer is scaffolded
> in `design/` (design-system.md is a marked template until extracted from the product
> repo), and runner affinity is live in `tools/azure-runner` (`01-ui-ux.diverge` on
> EC2 / `01-ui-ux.design` behind `daemon --runner workstation`, Paper preflight,
> `handoff.json` → the ux_signoff payload rendered as side-by-side PNGs in Mission
> Control). Still outstanding: Phase 0 (Justin's workstation + Paper Pro setup),
> populating `design/design-system.md`, the first real run through `ux_signoff`
> (Phase 1/2 done-when criteria), and reviewing Phase 4 metrics once runs exist.

How Lantern's `ui-ux` agent (pipeline stage 1) becomes a real design agent working
inside the team's Paper workspace. Grounded in `docs/research/design-agents.md` —
every design choice below traces to a verified finding or a reported failure mode.

## The two facts that shape everything

1. **Paper's MCP is desktop-bound**: served by the running Desktop app at
   `http://127.0.0.1:29979/mcp` with a file open — no headless/remote mode. So the
   Paper half of stage 1 runs on a **design workstation** (Justin's or a designer's
   machine, Paper Desktop open on the Lantern team file), not on EC2. Files
   cloud-sync, so workstation edits land in the shared workspace.
2. **Paper has no shipped component/token system yet** (roadmap). The pipeline must
   supply its own constraint layer — a checked-in design-system context file — or
   the agent produces generic, taste-free output (the #1 reported failure mode).

## The loop (per feature run)

```
brief ──► A. divergence (cheap, EC2, no Paper):
              5–10 low-fi HTML skeletons w/ LANTERN_MODEL_FAST,
              self-score vs brief, keep best 2–3 — each on a NAMED axis
              (e.g. wizard vs single-page vs inline-edit)
      ──► B. convergence (workstation, Paper MCP):
              create_artboard + write_html per option, side by side;
              rename_nodes to the axis names; ground every write in
              design/design-system.md
      ──► C. critique loop (≤3 iterations per option):
              get_screenshot → layout critique pass → style critique pass
              (separated, per METAL) → update_styles / write_html
      ──► D. present: options.md + exported PNGs + Paper link
              ──► HUMAN GATE ux_signoff (pick an option in Mission Control)
      ──► E. handoff package for the chosen option (see below);
              losers renamed “[rejected] …”, kept on canvas + 1 PNG each
```

## The handoff artifact set (machine-readable-first)

Written to `workflow/runs/<run-id>/01-ui-ux/`:

1. `export` **PNGs at 2x** of every chosen frame — acceptance references the coding
   agent later screenshot-diffs its build against (the Lovable pattern);
2. **`get_jsx` output per frame** — structural source of truth (a starting point,
   NOT production code: Paper JSX reflects canvas structure, not app architecture);
3. the **design-system context file** version used for grounding;
4. `flow-spec.md` — screens, transitions, states (empty/loading/error), copy;
5. the **Paper file/artboard URL** for humans + `[rejected]` option PNGs;
6. walkthrough video: try Paper's **MP4 export** first; fall back to the existing
   qa-recorder prototype recording if motion/interaction needs showing.

## Canvas etiquette (multiplayer safety)

Re-read (`get_selection`/`get_node_info`) before writing any frame a human may have
touched; never `delete_nodes` outside frames created this run; call
`finish_working_on_nodes` when done; restart the MCP connection per run (long
sessions degrade); **discover the tool list via `tools/list` at session start** and
never assume names (docs say ~21, third parties say 24, Paper ships near-daily).

## Phases

**Phase 0 — prerequisites (Justin, ~30 min)**
Paper **Pro** ($16/mo — free tier's 100 tool calls/week is roughly one run); create
the team file `Lantern`; install Paper Desktop on the design workstation; connect an
agent session (`claude mcp add paper --transport http http://127.0.0.1:29979/mcp` or
the Codex equivalent) and verify `tools/list` answers.
*Done when:* an agent session lists Paper tools and can create a scratch artboard.

**Phase 1 — skills + manual-in-the-loop runs**
Rewrite `agents/ui-ux/skills.md` §3–4 to encode the loop above (divergence axes,
critique checklist, artifact set, etiquette). Run stage 1 for one real brief from
the workstation interactively. *Done when:* one feature reaches `ux_signoff` with
the full artifact set and Justin decides from Mission Control.

**Phase 2 — the constraint layer**
Build `design/design-system.md` (+ extracted tokens/tailwind config from the product
repo — the `code-to-design` flow) and `design/critique-checklist.md` (hierarchy,
spacing rhythm, contrast, states). The agent loads both before any generation.
*Done when:* two options generated with/without the context file are visibly
distinguishable in fidelity to the product's look.

**Phase 3 — pipeline integration (workstation runner)**
Add runner affinity to the orchestrator: stage rows carry `runner` (`ec2` |
`workstation`); a small `pipeline.py daemon --runner workstation` on the design
machine claims only ui-ux stages, with a preflight that fails fast ("open Paper
Desktop on the Lantern file") instead of mid-run. Stage A (divergence) stays on EC2;
the workstation runner picks up from B. Artifacts auto-register; the `ux_signoff`
payload in Mission Control links the Paper URL + PNGs side by side.
*Done when:* `lantern run` reaches ux_signoff with zero manual steps while the
workstation daemon is online.

**Phase 4 — quality loops + measurement**
Add the judge pass (score options vs brief before presenting), cap and log critique
iterations, and track per-run: MCP calls used, iterations per option, gate decision
time, and how often the human picks the agent's recommended option — the metric that
tells us whether the agent's taste is improving. Feed misses into
`agents/ui-ux/memory.md` per the memory protocol.

## Risks

| Risk | Mitigation |
|---|---|
| Tool names drift (near-daily releases) | runtime `tools/list` discovery; pin nothing |
| Workstation offline ⇒ stage stalls | runner preflight + Mission Control shows the run as waiting with "needs the design workstation" note |
| Agent clobbers human canvas edits | etiquette rules above; agent-created frames only |
| Generic output | Phase 2 constraint layer is mandatory before Phase 3 |
| MCP call budget | Pro plan + divergence happens outside Paper |
