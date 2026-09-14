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

<!-- ENTRIES BELOW ARE RENDERED FROM THE role_memory TABLE — do not edit here; agents use append_memory, humans consolidate upward and re-run `pipeline.py render-memory` -->

- 2026-08-26 [feat-20260825-role-health · 01-ui-ux.diverge] 2026-08-26 (feat-20260825-role-health): For operational-health screens, a dedicated “diagnosis before evidence” judge criterion prevents familiar metric grids from winning on completeness even though they increase interpretation time.
- 2026-08-31 [feat-20260831-gate-latency · 01-ui-ux.diverge] 2026-08-31 (feat-20260831-gate-latency): For operational latency, judge whether a structure exposes age + threshold + cohort median + sample count in one glance; threshold-only treatments create urgency without revealing whether the bottleneck is systemic, while medians without local age hide which gate needs action.
- 2026-08-31 [feat-20260831-gate-latency · 01-ui-ux.design] 2026-08-31 (feat-20260831-gate-latency): For gate-latency boards, a row-local stale treatment plus a compact median and sample count preserves operational scan speed while distinguishing an isolated old gate from a systemic staffing problem; a threshold-only visualization overstates policy and consumes valuable board space.
- 2026-08-31 [feat-20260831-gate-latency · 01-ui-ux.design] 2026-08-31 (feat-20260831-gate-latency attempt 2): A Paper page can accept node writes while remaining visually unmounted; because successful writes do not prove screenshot/export readiness, verify get_screenshot immediately after the first small section before investing in full convergence.
- 2026-08-31 [feat-20260831-gate-latency · 01-ui-ux.design] 2026-08-31 (feat-20260831-gate-latency attempt 3): After a Paper mount failure, retry by screenshotting the existing artboards before creating more pages or nodes; if the renderer still returns no image, further canvas mutation only creates dead debris and cannot satisfy critique evidence.
- 2026-08-31 [feat-20260831-gate-latency · 01-ui-ux.design] 2026-08-31 (feat-20260831-gate-latency attempt 4): Explicitly activating the run page distinguishes page-scope failures from a degraded Paper capture process; if get_screenshot remains empty on the confirmed active page, restart Paper Desktop instead of mutating or exporting unreviewed artboards.
- 2026-08-31 [feat-20260831-gate-latency · 01-ui-ux.design] 2026-08-31 (feat-20260831-gate-latency attempt 5): After Paper Desktop capture recovers, re-review every frame rather than trusting prior node structure; screenshots exposed inherited black text in cards and metric rows that metadata alone did not reveal, and explicit text-token binding fixed it.
- 2026-09-11 [feat-20260911-tender-onboarding · 01-ui-ux.diverge] 2026-09-11 (feat-20260911-tender-onboarding): For onboarding an automated support channel, score structures on how directly they demonstrate “saved business facts become a visible customer reply”; this rejects superficially fast sandbox-first flows that let the seller hit an unconfigured dead end and mistake missing setup for product failure.
- 2026-09-11 [feat-20260911-tender-onboarding · 01-ui-ux.design] 2026-09-11 (feat-20260911-tender-onboarding): A desktop onboarding split pane is only a viable mobile option when it becomes an explicit Edit facts / Preview switch at 360px; merely stacking both full panes creates a very long teach–test loop and weakens the visible relationship between saved facts and the customer reply.
- 2026-09-11 [feat-20260911-tender-catalog-orders · 01-ui-ux.diverge] 2026-09-11 (feat-20260911-tender-catalog-orders): For automated order-taking UX, score whether the structure keeps the seller’s next valid status action beside the exact customer-notification consequence; status dashboards can look complete while hiding the transactional failure that determines whether fulfilment actually advanced.
- 2026-09-11 [feat-20260911-tender-catalog-orders · 01-ui-ux.diverge] 2026-09-11 (feat-20260911-tender-catalog-orders attempt 2): A measurable first-run completion target can legitimately reverse a divergence cut: once success required two catalog saves, a Sandbox order, seller confirmation, and a status query in under five minutes, the guided sequence beat the previously stronger repeat-use queue because it exposes cross-area wayfinding rather than optimizing only the final status action.
- 2026-09-11 [feat-20260911-tender-catalog-orders · 01-ui-ux.design] 2026-09-11 (feat-20260911-tender-catalog-orders, HTML convergence): A first-run commerce guide should collapse after the seller proves the full catalog → Sandbox order → seller confirmation → customer status loop, because the explicit sequence improves time-to-first-order but becomes permanent friction if it displaces durable Catalog/Orders navigation on return visits.
- 2026-09-12 [feat-20260911-tender-escalations · 01-ui-ux.diverge] 2026-09-12 (feat-20260911-tender-escalations): For escalation UX, judge whether the structure keeps customer silence, owner-notification proof, the live reply action, and hand-back status causally adjacent; workflows that emphasize system events or abstract lanes can look operationally complete while obscuring whether the customer has actually reached a person.
- 2026-09-12 [feat-20260911-tender-escalations · 01-ui-ux.design] 2026-09-12 (feat-20260911-tender-escalations, HTML convergence): For single-owner escalation handling, the repeat-use Inbox should keep trigger reason, assistant-paused proof, transcript, owner reply, and hand-back in one split-pane scan path; owner-phone context is better represented there as a compact delivery status because a permanent mirrored phone pane improves demos but slows daily triage.
