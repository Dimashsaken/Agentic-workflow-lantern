# Memory — ui-ux

Long-term judgement for this role. Read fully at session start. Append at session end.

Rules: dated entries, concrete, with the *why*; append-only during runs; no secrets or
customer data. Target: under ~200 lines after consolidation.

## Learnings (append-only, newest last)

- 2026-08-24 (seed): Always present the option you'd argue *against* too — Justin
  chooses better from real alternatives than from one design plus strawmen.
- 2026-08-24 (seed): Walkthrough videos replace meetings only if they show error states,
  not just the happy path — reviewers' first question is always "what if it fails?".
- 2026-08-25 (feat-20260825-candidate-compare): Paper MCP — nodes created before the
  file has ever been opened in the app's renderer never mount (screenshots/exports
  return empty / "No DOM element"); `open_file` does NOT switch the visible tab.
  Create the file, ask the human for one click to open it, THEN create artboards.
  Dead pre-mount nodes must be deleted and recreated, not styled into life.
- 2026-08-25 (feat-20260825-candidate-compare): Paper shipped design tokens
  (create_tokens/get_tokens — 35 tools total); recreating the product file's tokens
  in the sandbox file made every write token-grounded by construction. Always pass
  `fileId` on every write call — it makes touching the wrong file structurally
  impossible, which is exactly the multiplayer-safety contract.
- 2026-08-25 (feat-20260825-candidate-compare): judging divergence axes on "does the
  structure enact the product's core promise" (here: weights decide, Lantern argues)
  cleanly split six axes into three keepers and three rejects — better than generic
  usability scoring, which rated the familiar-but-wrong `columns` axis too high.

- 2026-08-26 (feat-20260825-role-health): For operational-health screens, judging whether the structure preserves “diagnosis first, numbers second” rejects generic dashboard grids even when they expose every metric; a compact diagnosis plus progressive evidence better supports between-meeting checks.

- 2026-08-26 (feat-20260825-role-health): A compact diagnosis-first design outperformed a numbers-first dashboard for role health because it converts a degraded signal into one understandable action without requiring chart interpretation; progressive disclosure remains the best alternative for scan-first users.
- 2026-08-26 (feat-20260825-role-health): Paper may resolve unspecified text color to black even inside a token-colored parent; inspect exported JSX or screenshots and explicitly bind important text nodes to `--color-text` before handoff.

- 2026-08-26 (feat-20260825-role-health): In headless Paper convergence, export success is insufficient when repo tools cannot read the workstation Downloads path; verify a binary-copy bridge before declaring the handoff package complete.

- 2026-08-26 (feat-20260825-role-health): When export collection becomes available, re-export from the current mounted Paper page rather than relying on old workstation paths; this verifies freshness and artifact provenance together.

- 2026-08-26 (feat-20260825-role-health): Recreating convergence on a fresh mounted page and immediately collecting new exports is the safest recovery path after stale or empty Paper pages; it preserves provenance and avoids adopting prior-run artboards.

- 2026-08-26 (feat-20260825-role-health): After repeated headless convergence attempts, creating a fresh mounted run page and collecting exports immediately gives the clearest artifact provenance; verify screenshots before exporting so a successful export cannot mask an empty or stale canvas.
- 2026-08-26 (feat-20260825-role-health): Paper virtualises offscreen canvas nodes out
  of the DOM — `export`/`get_screenshot` fail with "No DOM element found" for artboards
  outside the viewport even when the right file and page are visible. This is a SECOND
  mount trap beyond the never-opened-file one: bring the artboards into view (zoom to
  fit) before exporting, and screenshot right after creating while the canvas is still
  centred on the new node.
- 2026-08-26 (feat-20260825-role-health): the empty-bottom test caught a real defect in
  3 of 3 first drafts, including my own — a `flex:1` spacer pushing a footer down is the
  usual culprit. The fix is never "leave it": either the screen is missing content the
  user needs (trait distribution, what-changed, next action) or the frame is taller than
  the design. Check it before declaring any option done.
