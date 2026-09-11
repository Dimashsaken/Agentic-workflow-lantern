"""Download only Trivy's public OCI vulnerability database; no image input."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parents[1] / '06-security'
CACHE = ROOT / '.venv/external-qa-scan/cache/db'
CACHE.mkdir(parents=True, exist_ok=True)
registry = 'https://ghcr.io'
token = json.load(urllib.request.urlopen(registry + '/token?scope=repository:aquasecurity/trivy-db:pull', timeout=60))['token']
request = urllib.request.Request(registry + '/v2/aquasecurity/trivy-db/manifests/2',
    headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.oci.image.manifest.v1+json'})
with urllib.request.urlopen(request, timeout=60) as response:
    encoded = response.read()
    manifest = json.loads(encoded)
layer, = manifest['layers']
expected = layer['digest'].removeprefix('sha256:')
archive = CACHE.parent / 'trivy-db.tar.gz'
hash_value = hashlib.sha256()
url = registry + '/v2/aquasecurity/trivy-db/blobs/' + layer['digest']
offset = archive.stat().st_size if archive.exists() else 0
if offset > layer['size'] or (offset != layer['size'] and offset % (4*1024*1024)):
    raise RuntimeError('partial public database does not end on a checked range')
if offset:
    hash_value.update(archive.read_bytes())

def fetch(start):
        end = min(layer['size'], start+4*1024*1024)-1
        for attempt in range(3):
            request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token,
                'Range':f'bytes={start}-{end}'})
            with urllib.request.urlopen(request, timeout=120) as response:
                if response.status != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{layer["size"]}':
                    raise RuntimeError('public registry did not honor bounded database range')
                chunk = response.read(end-start+2)
            if len(chunk) == end-start+1:
                break
        else:
            raise RuntimeError('public database range was truncated repeatedly')
        return chunk

print(json.dumps({'public_database_bytes':layer['size'], 'resume_at':offset}),flush=True)
with archive.open('ab') as output, ThreadPoolExecutor(max_workers=4) as pool:
    for chunk in pool.map(fetch, range(offset, layer['size'], 4*1024*1024)):
        output.write(chunk)
        output.flush()
        hash_value.update(chunk)
if hash_value.hexdigest() != expected or archive.stat().st_size != layer['size']:
    raise RuntimeError('public database layer does not match registry digest')
with tarfile.open(archive) as source:
    if set(source.getnames()) != {'trivy.db', 'metadata.json'}:
        raise RuntimeError('unexpected vulnerability database archive')
    source.extractall(CACHE, filter='data')
record = {'source': registry + '/aquasecurity/trivy-db:2',
          'manifest_sha256':hashlib.sha256(encoded).hexdigest(), 'layer_sha256':expected,
          'bytes':layer['size'], 'metadata':json.loads((CACHE/'metadata.json').read_text()),
          'private_image_accessed':False}
(OUT/'external-qa-trivy-db-provenance.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
