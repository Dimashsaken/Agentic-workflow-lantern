// Actual Mission Control + disposable Postgres. No fixture responses or gate writes.
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../../', import.meta.url));
const out = path.join(root, 'workflow/runs/feat-20260910-agentic-infrastructure/04-qa-dev');
const media = path.join(out, 'media');
const { QA_BASE_URL: base, QA_USER: user, QA_PASS: password, QA_RUN_ID: run } = process.env;
assert(base && user && password && run, 'QA environment must be populated');
assert(['127.0.0.1', 'localhost'].includes(new URL(base).hostname), 'Disposable loopback service required');
const snapshot = JSON.parse(readFileSync(path.join(out, 'live-browser-before.json')));
assert.equal(snapshot.run.id, run);
const browser = await chromium.launch();
mkdirSync(media, { recursive: true });
const results = [];
let auth;
const mobileOnly = process.env.QA_RECORDING_MODE === 'mobile';

async function session(name, viewport, body, reuseAuth = false) {
  name += process.env.QA_RECORDING_SUFFIX || '';
  const ctx = await browser.newContext({ viewport, ...(reuseAuth ? { storageState: auth } : {}), recordVideo: { dir: media, size: { width: 1280, height: 720 } } });
  const page = await ctx.newPage();
  const started = Date.now();
  const result = { name, passed: false, events: [], errors: [], blocked_mutations: [], http_errors: [] };
  const mark = title => result.events.push({ seconds: +((Date.now() - started) / 1000).toFixed(2), title });
  page.on('pageerror', error => result.errors.push(error.message));
  page.on('response', response => { if (response.url().startsWith(base) && response.status() >= 400) result.http_errors.push({ path: new URL(response.url()).pathname, status: response.status() }); });
  let tracing = false;
  try {
    if (!reuseAuth) {
      await page.goto(`${base}/run/${run}/trace`);
      assert.equal(new URL(page.url()).pathname, '/login');
      mark('Anonymous evidence request redirects to login');
      await page.locator('input[name=username]').fill(user);
      await page.locator('input[name=password]').fill(password);
      await page.getByRole('button', { name: 'Sign in', exact: true }).click();
      await page.waitForURL(url => url.pathname === '/');
      mark('Authenticated through actual application login');
      auth = await ctx.storageState();
    }
    // Never capture the login POST/cookie setup in traces or serialize auth to disk.
    await ctx.tracing.start({ screenshots: true, snapshots: true });
    tracing = true;
    await ctx.route('**/*', async route => {
      const request = route.request();
      if (request.url().startsWith(base) && !['GET', 'HEAD'].includes(request.method())) {
        result.blocked_mutations.push({ method: request.method(), path: new URL(request.url()).pathname });
        await route.abort();
      } else await route.continue();
    });
    await body(page, mark);
    assert.deepEqual(result.errors, []);
    assert.deepEqual(result.http_errors, []);
    assert.deepEqual(result.blocked_mutations, []);
    result.passed = true;
  } catch (error) { result.failure = error.message; }
  finally {
    if (tracing) await ctx.tracing.stop({ path: path.join(media, `${name}.zip`) });
    const video = page.video();
    await ctx.close();
    await video.saveAs(path.join(media, `${name}.webm`));
    await video.delete();
    result.video = `media/${name}.webm`;
    result.trace = tracing ? `media/${name}.zip` : null;
    result.video_sha256 = createHash('sha256').update(readFileSync(path.join(media, `${name}.webm`))).digest('hex');
    results.push(result);
  }
}

try {
  if (!mobileOnly) await session('local-dev-authenticated-desktop', { width: 1280, height: 720 }, async (page, mark) => {
    await page.goto(`${base}/run/${run}`);
    await page.locator('a[data-drawer]').first().waitFor();
    assert.equal(await page.locator('a[data-drawer]').count(), snapshot.executions.length);
    mark('Real run lanes and pending story evidence');
    await page.waitForTimeout(900);
    await page.goto(`${base}/run/${run}/trace`);
    assert.equal(await page.locator('.matrix tr').count(), 3);
    assert.equal(await page.locator('.matrix td.ac').first().innerText(), 'AC-1');
    assert.ok((await page.locator('.msum').innerText()).includes('2 pending'));
    assert.equal(await page.locator('.matrix .chip.ok').count(), 0);
    mark('Real story criteria; later stages explicitly pending');
    await page.waitForTimeout(1000);
    await page.reload();
    assert.equal(await page.locator('.matrix tr').count(), 3);
    await page.screenshot({ path: path.join(media, 'local-dev-authenticated-matrix.png') });
    for (const execution of snapshot.executions) {
      await page.goto(`${base}/run/${run}/exec/${execution.id}`);
      assert.ok((await page.locator('h2').first().innerText()).includes(execution.stage));
      await page.getByText('Show the prompt the agent ran with', { exact: true }).click();
      assert.ok((await page.locator('pre.prompt').first().innerText()).length > 100);
      mark(`${execution.stage}: real compiled prompt and execution diagnostics`);
      await page.waitForTimeout(700);
      await page.getByText('Show the prompt the agent ran with', { exact: true }).click();
      await page.getByRole('heading', { name: /Tool calls/ }).scrollIntoViewIfNeeded();
      assert.ok(await page.locator('.tcalls tbody tr, .tcalls tr').count() > 1);
      mark(`${execution.stage}: real tool-call evidence`);
      await page.waitForTimeout(800);
      await page.getByRole('heading', { name: /Memory appended/ }).scrollIntoViewIfNeeded();
      mark(`${execution.stage}: execution-linked memory`);
      await page.waitForTimeout(600);
    }
    await page.screenshot({ path: path.join(media, 'local-dev-authenticated-drawer.png') });
    await page.goto(`${base}/run/${run}`);
    mark('Returned to unchanged pending story run');
    await page.waitForTimeout(700);
  });
  if (auth || mobileOnly) await session('local-dev-authenticated-mobile', { width: 390, height: 844 }, async (page, mark) => {
    await page.goto(`${base}/run/${run}/trace`);
    assert.equal(await page.locator('.matrix tr').count(), 3);
    mark('Authenticated mobile matrix from real story');
    await page.locator('.mwrap').scrollIntoViewIfNeeded();
    await page.waitForTimeout(800);
    await page.locator('.mwrap').evaluate(el => { el.scrollLeft = el.scrollWidth; });
    assert.ok((await page.locator('.matrix').innerText()).toLowerCase().includes('pending'));
    const pending = await page.locator('.matrix tr:nth-child(2) td:last-child .chip').boundingBox();
    assert.ok(pending.y >= 0 && pending.y + pending.height <= 844, 'Pending row verdict is in recorded viewport');
    mark('Later-stage pending columns remain reachable');
    await page.waitForTimeout(800);
    await page.screenshot({ path: path.join(media, 'local-dev-authenticated-mobile.png') });
  }, Boolean(auth));
} finally {
  await browser.close();
  writeFileSync(path.join(out, process.env.QA_RESULTS_FILE || 'live-browser-results.json'), JSON.stringify({
    kind: 'authenticated_local_dev_integration', fleet_qa_execution: false,
    actual_application: true, database: 'disposable_postgres', run_id: run,
    recorded_at: new Date().toISOString(), source_sha256: snapshot.source_sha256,
    trace_starts_after_login: true, results,
  }, null, 2) + '\n');
}
console.log(JSON.stringify(results.map(({ name, passed, failure }) => ({ name, passed, failure }))));
process.exitCode = results.every(r => r.passed) ? 0 : 1;
