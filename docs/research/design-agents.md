# Design agents — research brief (2026-08-25)

How teams build agents that do UI/UX design work; grounds
`docs/plans/ui-ux-agent-paper.md`. Sources verified 2026-08-25; unverified items flagged.

## Paper (paper.design) MCP — verified facts

- Canvas is **real HTML/CSS on DOM nodes** — why LLMs manipulate it with high fidelity.
- MCP server is served by the **Desktop app** at `http://127.0.0.1:29979/mcp`, auto-starts
  with a file open. **No headless/remote option is documented** — the session is bound to
  one machine's open file (files cloud-sync to the team workspace, so edits do land).
  Desktop ships for macOS/Windows/Linux. (<https://paper.design/docs/mcp>)
- Tool surface (~21 per docs; third parties claim 24 — **discover via `tools/list` at
  runtime, never hardcode**): reads `get_basic_info/get_selection/get_node_info/
  get_children/get_tree_summary/get_screenshot/get_jsx/get_computed_styles/...`;
  writes `create_artboard/write_html/set_text_content/rename_nodes/duplicate_nodes/
  move_nodes/update_styles/delete_nodes`; plus `export` (**PNG/JPG/SVG/MP4**, 2x/1080p)
  and `finish_working_on_nodes`.
- Operational limits reported: long MCP sessions degrade (restart per run); free tier
  100 tool calls/week vs **1M/week on Pro ($16/mo)**.
- Components-with-props, themes/tokens, Tailwind/shadcn kits: **roadmap, not shipped** —
  the pipeline must supply its own design-system constraint layer.
- Working bidirectional loop confirmed in the field: `write_html` → human tweak →
  `get_jsx` → React/Tailwind. (<https://medium.com/@tahirbalarabe2/bidirectional-design-to-code-via-paper-and-claude-code-mcp-a749a5a4ad5b>)

## Figma MCP (the mature comparison)

Remote hosted MCP (no desktop needed — contrast with Paper); read-only design context +
**Code Connect** maps generated code onto the team's real components; since Mar 2026
write access (`use_figma`, `generate_figma_design`) with "self-healing loops" — agent
screenshots its own output and iterates. Lesson: bind tokens/components first; coverage
of leaf primitives cascades. (<https://help.figma.com/hc/en-us/articles/32132100833559>,
<https://www.figma.com/blog/the-figma-canvas-is-now-open-to-agents/>)

## Product architectures (v0, Lovable, Magic Patterns, Figma Make)

Common shape: **N divergent options → human pick → grounded convergence → live preview
→ agent self-verification → export.** v0's pick-from-3 + headless API
(<https://www.infoq.com/news/2026/08/vercel-v0-api/>); Lovable's QA loop drives the real
preview and verifies with screenshots across breakpoints; Magic Patterns' Design System
Agent generates only against ingested real components/tokens; Make kits package library
+ usage guidelines as generation constraints.

## Quality patterns (research-backed)

- **Vision self-critique on rendered output is standard**: Design2Code render-and-revise;
  ReLook (MLLM critic on rendered pages); METAL — *separate layout-critique from
  style-critique* for better self-correction. (<https://arxiv.org/pdf/2412.16829>)
- **Divergence cheap, convergence expensive**: ~10 fast low-fi variants → human picks
  1-2 → strong model implements only those (Superdesign pattern,
  <https://www.superdesign.dev/blog/ai-wireframe-generator>).
- **Agents have no taste by default** — quality comes from constraints: a design-system
  context file, aesthetic heuristics, concrete references
  (<https://github.com/superdesigndev/superdesign>).
- **Handoff = machine-readable-first**: tokens + structured code (JSX) + flow spec;
  screenshots as *acceptance references* for the coding agent's own visual diff.

## Reported failure modes

Hallucinated MCP tool names · degrading long sessions · generic output without
design-system context · too-similar variants stakeholders can't compare · agents
clobbering human edits on a multiplayer canvas.

**Unverified (check before building on):** exact live tool count/names; any Paper
Web/remote MCP (all evidence: none); auth beyond localhost; component/token ship date.
