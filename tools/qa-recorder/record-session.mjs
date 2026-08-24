// Minimal recorded-session pattern. QA agents copy this per scenario:
// one context = one scenario = one short, named video + trace.
//
//   node record-session.mjs <baseUrl> <scenario-name>
//
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';

const [, , baseUrl = process.env.QA_BASE_URL ?? 'http://localhost:3000', name = 'session'] =
  process.argv;

mkdirSync('videos', { recursive: true });
mkdirSync('traces', { recursive: true });

const browser = await chromium.launch(); // headless by default — video still records
const context = await browser.newContext({
  recordVideo: { dir: 'videos/', size: { width: 1280, height: 720 } },
  viewport: { width: 1280, height: 720 },
});
await context.tracing.start({ screenshots: true, snapshots: true });

const page = await context.newPage();
await page.goto(baseUrl);

// ── scenario steps go here ─────────────────────────────────────────────
// await page.getByRole('button', { name: 'Sign in' }).click();
// await expect-style assertions belong in @playwright/test specs; this
// pattern is for agent-driven walkthroughs and repros.
// ───────────────────────────────────────────────────────────────────────

const video = page.video();
await context.tracing.stop({ path: `traces/${name}.zip` });
await context.close(); // finalizes the .webm
console.log(`video: ${await video.path()}`);
console.log(`trace: traces/${name}.zip`);
await browser.close();
