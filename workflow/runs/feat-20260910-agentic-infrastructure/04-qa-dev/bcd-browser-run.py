"""Local QA wrapper; environment-only targets/credentials, no gate mutations."""
import importlib.util
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request
from urllib.parse import urlsplit

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
BASELINE = '80babd0'


def baseline_ui(target):
    paths = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', BASELINE, 'tools/mission-control'], cwd=ROOT, text=True).splitlines()
    for path in paths:
        dest = target/path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(subprocess.check_output(['git', 'show', f'{BASELINE}:{path}'], cwd=ROOT))


def main():
    mode = sys.argv[1]
    assert mode in ('live', 'fixture')
    target = urlsplit(os.environ['QA_BASE_URL'])
    assert target.scheme == 'http' and target.hostname in {'127.0.0.1', 'localhost'}
    suffix = os.environ.get('QA_BCD_SUFFIX', '-bcd')
    os.environ.update(QA_RECORDING_SUFFIX=suffix, QA_RESULTS_FILE=f'{suffix.lstrip("-")}-{mode}-results.json')
    assert not (OUT/os.environ['QA_RESULTS_FILE']).exists(), 'Existing evidence attempt'
    if mode == 'live':
        db = urlsplit(os.environ['LANTERN_DATABASE_URL'].replace('+asyncpg', ''))
        assert db.hostname in {'127.0.0.1', 'localhost'} and db.port == 55432 and db.path == '/lantern_validation'
        os.environ.update(QA_BEFORE_FILE='bcd-live-before.json', QA_AFTER_FILE='bcd-live-after.json', QA_RECORDING_MODE='provenance')
        spec = importlib.util.spec_from_file_location('prior_live', OUT/'run-provenance-live.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        original_snapshot = module.snapshot
        async def snapshot(target, runtime, before=None):
            if before is None:
                baseline_ui(runtime)
            return await original_snapshot(target, runtime, before)
        module.snapshot = snapshot
        module.main()
        return
    with tempfile.TemporaryDirectory(prefix='lantern-bcd-ui-') as temp, tempfile.TemporaryFile(mode='w+', encoding='utf-8') as log:
        runtime = Path(temp)
        baseline_ui(runtime)
        for source in (ROOT/'tools/azure-runner').glob('*.py'):
            dest = runtime/'tools/azure-runner'/source.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
        fixture = runtime/OUT.relative_to(ROOT)/'local-browser-fixtures.py'
        fixture.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(OUT/'local-browser-fixtures.py', fixture)
        child = subprocess.Popen([sys.executable, str(fixture)], stdout=log, stderr=log,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            for _ in range(40):
                if child.poll() is not None:
                    raise RuntimeError('Fixture service unavailable')
                try:
                    with urllib.request.urlopen(os.environ['QA_BASE_URL']+'/verified.html', timeout=2) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(.25)
            else:
                raise RuntimeError('Fixture service unavailable')
            subprocess.run([os.environ['QA_NODE'], str(ROOT/'tools/qa-recorder/agent-infrastructure-provenance.mjs')], check=True)
            result_path = OUT/os.environ['QA_RESULTS_FILE']
            result = json.loads(result_path.read_text(encoding='utf-8'))
            result['ui_revision'] = BASELINE
            for name in ('app.py', 'ui.py', 'drawer.py'):
                key = 'tools/mission-control/'+name
                result['source_sha256'][key] = hashlib.sha256((runtime/key).read_bytes()).hexdigest()
            result_path.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        finally:
            child.terminate()
            child.wait(timeout=15)


if __name__ == '__main__':
    main()
