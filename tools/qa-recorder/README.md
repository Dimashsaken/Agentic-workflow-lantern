# qa-recorder — browser QA with video, always on

Every Lantern stage that drives a browser (ui-ux walkthroughs, qa-dev, qa-staging,
debug repros) runs through this harness. The core mechanism is **Playwright's built-in
video recording**: pass `recordVideo` when creating a browser context and every page in
that context is captured to a `.webm` — headless included, so it works on a display-less
EC2 box with zero extra infrastructure. No screen capture, no GPU, no ffmpeg needed for
the standard path.

Three artifact layers, cheapest to richest:

| Artifact | How | Best for |
|----------|-----|----------|
| Video (`.webm`) | `recordVideo` on the context | Humans reviewing a flow (Justin watches instead of attending a demo) |
| Trace (`.zip`) | `context.tracing.start/stop` | Debugging a failure step-by-step (DOM snapshots, network, console) |
| Screenshots | `page.screenshot()` | Inline evidence in reports |

Record video **and** trace on every QA session — video for humans, trace for agents.

## Setup (once per machine)

```bash
cd tools/qa-recorder
npm install
npx playwright install --with-deps chromium
```

(`--with-deps` needs sudo on EC2; see `infra/ec2/README.md`. Add `webkit firefox` for
the qa-staging cross-browser pass.)

## Usage patterns

**1. Scripted scenarios (the default).** The QA agent writes a script per charter
scenario using `record-session.mjs` as the pattern — one browser context per scenario
so each video is short and named. Deterministic, replayable, and failed scenarios
become permanent regression specs.

**2. Exploratory driving.** For free-form sessions the agent drives the browser
interactively (e.g. via Playwright MCP — recent versions have flags for saving
traces/video; check `npx @playwright/mcp@latest --help`). If interactive video isn't
available in your setup, do exploration first, then immediately codify what you found
into a scripted, recorded scenario — the committed artifact is the scripted one.

**3. Full-desktop capture (rare).** Only if you must show something outside the
browser viewport: `xvfb-run` + ffmpeg x11grab on EC2. Not the default; document why if
used.

## Conventions

- **In-stage evidence is automatic (P0.1):** pipeline QA stages don't use this harness
  for recording — the orchestrator launches the agent's browser MCP with recording on,
  videos land in the run's `<stage-dir>/media/`, and the ORCHESTRATOR uploads them to
  the bucket as `<run-id>--<stage>--session-<n>.webm` after the stage passes. Agents
  never upload (sandboxes hold no AWS credentials) and never claim S3 URLs for
  sessions they didn't record.
- This harness's scripted specs are for committed regression tests and local repro
  work. Their videos/traces land in `videos/` and `traces/` (gitignored) — name them
  `<run-id>--<stage>--<scenario>.webm`; anything worth keeping goes into the run
  folder so the orchestrator's upload pass ships it.
- Reports always link videos **with timestamps** ("0:00 login, 0:25 the failing
  submit").
- 1280×720 is the standard size — big enough to read, small enough to upload fast.
- Base URLs and credentials come from env vars (`QA_BASE_URL`, `QA_USER`, `QA_PASS` via
  SSM/.env) — never hardcoded, never in reports.
