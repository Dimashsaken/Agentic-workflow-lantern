"""Own one local fixture child; record it and always stop that exact child."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request
from urllib.parse import urlsplit


def main():
    out = Path(__file__).resolve().parent
    root = out.parents[3]
    target = urlsplit(os.environ['QA_BASE_URL'])
    assert target.scheme == 'http' and target.hostname in {'localhost', '127.0.0.1'}
    os.environ.update(QA_RECORDING_SUFFIX='-continuation3', QA_RESULTS_FILE='continuation3-fixture-results.json')
    assert not (out / os.environ['QA_RESULTS_FILE']).exists(), 'Evidence already exists'
    with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as log:
        child = subprocess.Popen([sys.executable, str(out / 'local-browser-fixtures.py')],
                                 stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            for _ in range(40):
                if child.poll() is not None:
                    raise RuntimeError('Fixture child exited')
                try:
                    with urllib.request.urlopen(os.environ['QA_BASE_URL'] + '/verified.html', timeout=2) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(.25)
            else:
                raise RuntimeError('Fixture readiness failed')
            subprocess.run([os.environ['QA_NODE'], str(root / 'tools/qa-recorder/agent-infrastructure-provenance.mjs')], check=True)
        finally:
            child.terminate()
            child.wait(timeout=15)
    print('Fixture recordings complete; owned fixture child stopped')


if __name__ == '__main__':
    main()
