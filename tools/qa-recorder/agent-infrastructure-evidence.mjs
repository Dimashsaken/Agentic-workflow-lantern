// Local renderer regression, following record-session.mjs: video + trace always.
// Requires the separate local-browser-fixtures.py server and QA_BASE_URL.
// This is explicitly NOT a live dev stage or pipeline execution.
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../../', import.meta.url));
const output = path.join(root, 'workflow/runs/feat-20260910-agentic-infrastructure/04-qa-dev');
const media = path.join(output, 'media');
const base = process.env.QA_BASE_URL;
assert(base, 'QA_BASE_URL is required');
assert(['127.0.0.1', 'localhost'].includes(new URL(base).hostname), 'Only loopback fixtures permitted');
mkdirSync(media, { recursive: true });
const browser = await chromium.launch();
const results = [];

async function session(name, viewport, run) {
  name += process.env.QA_RECORDING_SUFFIX || '';
  const context = await browser.newContext({ viewport, recordVideo: { dir: media, size: { width: 1280, height: 720 } } });
  await context.tracing.start({ screenshots: true, snapshots: true });
  const page = await context.newPage();
  const started = Date.now();
  const events = [];
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const mark = title => events.push({ seconds: +( (Date.now() - started) / 1000).toFixed(2), title });
  const result = { name, viewport, passed: false, events, errors };
  try {
    await run(page, mark);
    assert.deepEqual(errors, [], 'No uncaught browser errors');
    result.passed = true;
  } catch (error) {
    result.failure = error.message;
  } finally {
    const video = page.video();
    await context.tracing.stop({ path: path.join(media, `${name}.zip`) });
    await context.close();
    await video.saveAs(path.join(media, `${name}.webm`));
    await video.delete();
    result.video = `media/${name}.webm`;
    result.trace = `media/${name}.zip`;
    result.video_sha256 = createHash('sha256').update(readFileSync(path.join(media, `${name}.webm`))).digest('hex');
    results.push(result);
  }
}

try {
  await session('local-renderer-desktop', { width: 1280, height: 720 }, async (page, mark) => {
    await page.goto(`${base}/structured.html`);
    await page.getByText('Local renderer fixture', { exact: true }).waitFor();
    mark('Structured evidence, HTML-shaped text and Unicode visible');
    assert.equal(await page.locator('.matrix .d').filter({ hasText: 'product/app.py:12' }).count(), 1);
    assert.equal(await page.locator('.matrix .d').filter({ hasText: '04-qa-dev/<result>&\'".txt:2' }).count(), 1);
    assert.equal(await page.locator('.matrix .d').filter({ hasText: 'café-🧪.txt:7' }).count(), 1);
    assert.equal(await page.locator('result').count(), 0);
    await page.locator('.mwrap').evaluate(el => { el.scrollLeft = el.scrollWidth; });
    await page.waitForTimeout(900);
    assert.ok((await page.locator('.matrix .d').last().getAttribute('title')).includes('long-reference-'));
    await page.reload();
    mark('Refresh preserves structured references');
    await page.getByRole('link', { name: 'legacy', exact: true }).click();
    assert.ok((await page.locator('.matrix').innerText()).includes('Legacy prose: <result> remains literal.'));
    mark('Legacy prose and back navigation');
    await page.waitForTimeout(800);
    await page.goBack();
    await page.getByRole('link', { name: 'empty', exact: true }).click();
    assert.ok((await page.locator('main').innerText()).includes('No story yet.'));
    mark('Empty story is explicit');
    await page.waitForTimeout(800);
    await page.getByRole('link', { name: 'validation', exact: true }).click();
    assert.ok((await page.locator('.vtbl').innerText()).includes('product/app.py:12'));
    assert.equal(await page.locator('result').count(), 0);
    mark('Gate validation renderer structured references');
    await page.waitForTimeout(800);
    await page.screenshot({ path: path.join(media, 'local-renderer-validation.png') });
    await page.getByRole('button', { name: 'dark mode', exact: true }).click();
    assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');
    mark('Exploratory theme switch');
    await page.waitForTimeout(600);
  });
  await session('local-renderer-mobile', { width: 390, height: 844 }, async (page, mark) => {
    await page.goto(`${base}/structured.html`);
    mark('Mobile layout and horizontal matrix scroll');
    const size = await page.locator('.mwrap').evaluate(el => ({ client: el.clientWidth, scroll: el.scrollWidth }));
    assert.ok(size.scroll > size.client, 'Matrix scrolls on narrow view');
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    assert.ok(overflow <= 1, `Page overflows by ${overflow}px`);
    await page.waitForTimeout(1000);
    await page.locator('.mwrap').evaluate(el => {
      const cells = el.querySelectorAll('tr:nth-child(2) > td');
      el.scrollLeft = cells[5].offsetLeft - cells[0].offsetWidth;
    });
    assert.ok(await page.locator('.matrix .d').filter({ hasText: 'product/app.py:12' }).isVisible());
    const reference = await page.locator('.matrix .d').filter({ hasText: 'product/app.py:12' }).boundingBox();
    const sticky = await page.locator('.matrix td.ac').boundingBox();
    assert.ok(reference.x >= sticky.x + sticky.width - 1, 'Sticky criterion does not obscure evidence');
    mark('Evidence column reachable after horizontal scroll');
    await page.waitForTimeout(1000);
    await page.screenshot({ path: path.join(media, 'local-renderer-mobile.png') });
  });
} finally {
  await browser.close();
  const source_sha256 = {};
  for (const relative of ['tools/mission-control/ui.py', 'tools/mission-control/traceability.py', 'tools/mission-control/app.py']) {
    source_sha256[relative] = createHash('sha256').update(readFileSync(path.join(root, relative))).digest('hex');
  }
  writeFileSync(path.join(output, 'local-browser-results.json'), JSON.stringify({
    kind: 'local_fixture_renderer_regression', fleet_execution: false, live_dev: false,
    recorded_at: new Date().toISOString(), source_sha256, results,
  }, null, 2) + '\n');
}
console.log(JSON.stringify(results.map(({ name, passed, failure }) => ({ name, passed, failure }))));
process.exitCode = results.every(r => r.passed) ? 0 : 1;
