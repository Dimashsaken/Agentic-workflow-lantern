"""Run local engineering UI QA; refuse any non-designated disposable database."""
import importlib.util
import os
from pathlib import Path
from urllib.parse import urlsplit


def main():
    target = urlsplit(os.environ['LANTERN_DATABASE_URL'].replace('+asyncpg', ''))
    if target.hostname not in {'127.0.0.1', 'localhost'} or target.port != 55432 or target.path != '/lantern_validation':
        raise SystemExit('Refusing database outside the designated disposable validation endpoint')
    out = Path(__file__).resolve().parent
    os.environ.update(QA_BEFORE_FILE='continuation3-live-before.json',
                      QA_AFTER_FILE='continuation3-live-after.json',
                      QA_RESULTS_FILE='continuation3-live-results.json',
                      QA_RECORDING_SUFFIX='-continuation3', QA_RECORDING_MODE='provenance')
    for name in ('QA_BEFORE_FILE', 'QA_AFTER_FILE', 'QA_RESULTS_FILE'):
        if (out / os.environ[name]).exists():
            raise SystemExit('Refusing to overwrite a prior evidence attempt')
    spec = importlib.util.spec_from_file_location('prior_launcher', out / 'run-provenance-live.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()


if __name__ == '__main__':
    main()
