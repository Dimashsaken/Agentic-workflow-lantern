"""Read-only installed image inventory, with networking disabled for inspection."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parents[1] / '06-security'
docker, image = sys.argv[1:3]


def command(*args):
    return subprocess.check_output([docker, *args], text=True)


identity = json.loads(command('image', 'inspect', image))[0]
image = identity['Id']
script = '''import hashlib, importlib.metadata, json, pathlib, subprocess, zlib
p=pathlib.Path('/usr/share/doc/zlib1g/lantern-mitigation.json')
provenance=json.loads(p.read_text())
actual=hashlib.sha256(pathlib.Path('/usr/lib/x86_64-linux-gnu/libz.so.1.3.1').read_bytes()).hexdigest()
assert actual == provenance['library_sha256']
print(json.dumps({'zlib_runtime':zlib.ZLIB_RUNTIME_VERSION,'provenance':provenance,
 'installed_library_sha256':actual,'installed_matches_provenance':True,
 'os_packages':subprocess.check_output(['dpkg-query','-W','-f=${Package}\\t${Version}\\n'],text=True).splitlines(),
 'python_packages':sorted((d.metadata['Name'],d.version) for d in importlib.metadata.distributions())}))
'''
installed = json.loads(command('run', '--rm', '--network', 'none', '--entrypoint',
                               '/opt/gateway/bin/python', image, '-c', script))
sources = list((ROOT/'infra/qa-gateway').glob('*.py')) + list((ROOT/'infra/qa-gateway').glob('*.lock'))
sources += [ROOT/'infra/qa-gateway/Dockerfile', ROOT/'tools/azure-runner/qa_transport.py']
result = {'image': image, 'created': identity['Created'], 'layers': identity['RootFS']['Layers'],
          'network_during_inspection': 'none', 'installed': installed,
          'source_sha256': {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
(OUT/'external-qa-image-inventory.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'image':image, 'installed_library_matches_provenance':True,
                  'os_packages':len(installed['os_packages']), 'python_packages':len(installed['python_packages'])}))
