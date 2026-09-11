"""Narrow one-session recorder candidate. Receipts remain controller-owned.

Input is a controller-mounted plan, output is one recording and trace. No product
checkout, eval operation, shell tool or arbitrary output path is accepted.
External deployment wiring is held in qa_transport.launch_external.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

SCRIPT = r'''
const fs = require('fs');
const {chromium} = require('/opt/lantern/qa-recorder/node_modules/playwright');
const p = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  const browser = await chromium.launch({headless: true,
    args: ['--disable-quic', '--disable-http2'],
    ...(p.proxy ? {proxy: {server: p.proxy}} : {})});
  const context = await browser.newContext({viewport: p.viewport,
    ignoreHTTPSErrors: false, recordVideo: {dir: '/recordings', size: p.viewport}});
  // Persist only redacted command outcomes; raw Playwright traces contain network secrets.
  await context.route('**/*', route => {
    const u = new URL(route.request().url());
    return p.origins.includes(u.origin) ? route.continue() : route.abort();
  });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  const outcomes = [];
  for (const a of p.actions) {
    let passed = false;
    try {
      if (a.kind === 'navigate') await page.goto(a.url, {waitUntil: 'domcontentloaded'});
      else if (a.kind === 'click') await page.locator(a.selector).click();
      else if (a.kind === 'fill') await page.locator(a.selector).fill(a.value);
      else if (a.kind === 'assert_text') {
        const text = await page.locator(a.selector).innerText();
        if (!text.includes(a.text)) throw Error('assertion failed');
      } else throw Error('unsupported action');
      passed = true;
    } catch (_) { /* no request values or credentials in stdout */ }
    outcomes.push({command_id: a.id, requirement: a.requirement, passed});
    if (!passed) break;
  }
  const video = page.video();
  fs.writeFileSync('/recordings/' + p.recording_id + '.trace.json',
    JSON.stringify({recording_id: p.recording_id, events: outcomes}));
  await context.close();
  await video.saveAs('/recordings/' + p.recording_id + '.webm');
  await video.delete();
  await browser.close();
  process.stdout.write(JSON.stringify({recording_id: p.recording_id, outcomes, writers_closed: true})+'\n');
})().catch(() => {process.stderr.write('recorder failed\n');process.exit(1);});
'''


def validate(plan):
    if (not isinstance(plan, dict) or not re.fullmatch('[0-9a-f]{32}', plan.get('recording_id', ''))
            or not isinstance(plan.get('actions'), list) or not 1 <= len(plan['actions']) <= 100
            or not isinstance(plan.get('origins'), list) or not 1 <= len(plan['origins']) <= 32):
        raise ValueError('invalid controller recording plan')
    from qa_transport import canonical_origin
    for origin in plan['origins']:
        canonical_origin(origin)
    if set(plan.get('viewport', {})) != {'width', 'height'} or any(
            type(v) is not int or not 240 <= v <= 2000 for v in plan['viewport'].values()):
        raise ValueError('invalid viewport')
    ids = set()
    for action in plan['actions']:
        if (action.get('kind') not in {'navigate', 'click', 'fill', 'assert_text'}
                or not re.fullmatch('[A-Za-z0-9_-]{1,80}', action.get('id', ''))
                or action['id'] in ids or not re.fullmatch(r'AC-[1-9][0-9]*', action.get('requirement', ''))):
            raise ValueError('invalid recording action')
        ids.add(action['id'])
    return plan


def main():
    plan_path = Path('/plan/recording.json')
    if plan_path.stat().st_size > 64000:
        raise ValueError('oversized recording plan')
    plan = validate(json.loads(plan_path.read_text()))
    # Import only the public per-execution certificate, into this ephemeral HOME.
    home = Path('/home/worker')
    store = home / '.pki/nssdb'
    store.mkdir(parents=True, exist_ok=False)
    subprocess.run(['certutil', '-N', '--empty-password', '-d', 'sql:' + str(store)], check=True, capture_output=True)
    subprocess.run(['certutil', '-A', '-d', 'sql:' + str(store), '-n', 'Lantern session CA',
                    '-t', 'C,,', '-i', '/trust/ca.pem'], check=True, capture_output=True)
    env = {**os.environ, 'HOME': str(home)}
    result = subprocess.run(['node', '-e', SCRIPT], input=json.dumps(plan), text=True,
                            env=env, timeout=1800, capture_output=True)
    if result.returncode:
        raise RuntimeError('recorder failed')
    # Never relay browser stderr or request values to the controller log.
    print(result.stdout.strip())


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('recording held', file=sys.stderr)
        raise SystemExit(1)
