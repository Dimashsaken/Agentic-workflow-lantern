// Production drawer renderer fixtures; local QA only, video + trace always on.
import { chromium } from '../../../../tools/qa-recorder/node_modules/playwright/index.mjs';
import assert from 'node:assert/strict';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const root = fileURLToPath(new URL('../../../../', import.meta.url));
const out = path.join(root, 'workflow/runs/feat-20260910-agentic-infrastructure/04-qa-dev');
const media = path.join(out, 'media');
const base = process.env.QA_BASE_URL;
assert(base && ['localhost','127.0.0.1'].includes(new URL(base).hostname));
mkdirSync(media, {recursive:true});
const browser = await chromium.launch();
const results = [];
const evidence = page => page.locator('.dsect').filter({has:page.getByRole('heading', {name:'Execution evidence', exact:true})});
async function record(name, viewport, fn) {
  name += process.env.QA_RECORDING_SUFFIX || '';
  const context = await browser.newContext({viewport, recordVideo:{dir:media,size:{width:1280,height:720}}});
  await context.tracing.start({screenshots:true,snapshots:true});
  const page = await context.newPage();
  const start=Date.now(), result={name,passed:false,events:[],errors:[]};
  const mark = title => result.events.push({seconds:+((Date.now()-start)/1000).toFixed(2),title});
  page.on('pageerror', e=>result.errors.push(e.message));
  try { await fn(page,mark); assert.deepEqual(result.errors,[]); result.passed=true; }
  catch(e) {result.failure=e.message;}
  finally {
    await page.screenshot({path:path.join(media,name+'.png'),fullPage:false});
    await context.tracing.stop({path:path.join(media,name+'.zip')});
    const video=page.video(); await context.close();
    await video.saveAs(path.join(media,name+'.webm')); await video.delete();
    result.video='media/'+name+'.webm'; result.trace='media/'+name+'.zip';
    result.video_sha256=createHash('sha256').update(readFileSync(path.join(media,name+'.webm'))).digest('hex');
    results.push(result);
  }
}
try {
  await record('provenance-fixture-desktop',{width:1280,height:720},async(page,mark)=>{
    for(const name of ['verified','forged-mirror','stale','cross-run']) {
      await page.goto(`${base}/${name}.html`);
      await evidence(page).scrollIntoViewIfNeeded();
      const text=await evidence(page).innerText();
      if(name==='verified') {
        assert.ok(text.includes('Controller verified at completion'));
        for(const value of ['a'.repeat(40),'b'.repeat(40),'sha256:'+'c'.repeat(64),'d'.repeat(64),'AC-10: quality:test, café-🧪-<probe>']) assert.ok(text.includes(value),value);
        assert.equal(await page.locator('probe').count(),0);
      } else {
        assert.ok(text.includes('No verified manifest recorded for this execution'));
        assert.ok(!text.includes('Controller verified at completion'));
      }
      mark(name+': evidence section visible'); await page.waitForTimeout(1000);
    }
    await page.goBack(); assert.ok((await evidence(page).innerText()).includes('No verified manifest'));
    await page.reload(); await evidence(page).scrollIntoViewIfNeeded();
    mark('Back and refresh retain stale receipt refusal'); await page.waitForTimeout(800);
  });
  await record('provenance-fixture-mobile',{width:390,height:844},async(page,mark)=>{
    await page.goto(`${base}/verified.html`); await evidence(page).scrollIntoViewIfNeeded();
    const geometry=await evidence(page).boundingBox();
    assert.ok(geometry.y>=0 && geometry.y+geometry.height<=844,'Entire evidence section visible vertically');
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth);
    assert.ok(overflow<=1,`Page overflows by ${overflow}px`);
    for(const code of await evidence(page).locator('code').all()) {
      const box=await code.boundingBox(); assert.ok(box.x>=0 && box.x+box.width<=391,'Hash visible inside viewport');
    }
    mark('Verified hashes and test links fit mobile viewport'); await page.waitForTimeout(1000);
    await page.locator('.account-menu > summary').click(); await page.getByRole('button',{name:'dark mode',exact:true}).click();
    assert.equal(await page.locator('html').getAttribute('data-theme'),'dark');
    await evidence(page).scrollIntoViewIfNeeded();
    mark('Theme change preserves provenance readability'); await page.waitForTimeout(1000);
  });
} finally {
  await browser.close();
  const source_sha256={};
  for(const p of ['tools/mission-control/drawer.py','tools/mission-control/ui.py','tools/mission-control/app.py','workflow/runs/feat-20260910-agentic-infrastructure/04-qa-dev/local-browser-fixtures.py']) source_sha256[p]=createHash('sha256').update(readFileSync(path.join(root,p))).digest('hex');
  writeFileSync(path.join(out,process.env.QA_RESULTS_FILE||'provenance-browser-results.json'),JSON.stringify({kind:'local_fixture_provenance_renderer',fleet_execution:false,live_dev:false,recorded_at:new Date().toISOString(),source_sha256,results},null,2)+'\n');
}
console.log(JSON.stringify(results.map(({name,passed,failure})=>({name,passed,failure}))));
process.exitCode=results.every(r=>r.passed)?0:1;
