"""Produce a transparent, reproducible dependency-only mitmproxy candidate wheel.

Upstream 12.2.3 caps dependencies below available security fixes. This is NOT an
upstream release: +lantern1 identifies the local metadata patch. Runtime package
members are copied byte-for-byte. Both hashes and every metadata replacement are
recorded; pip checks the complete hashed lock and dependency consistency later.
"""
import argparse
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile

UPSTREAM_SHA256 = 'df75ccd15ccb39ab55ce9dd4130312270e8ba208eb927a7cbe50cb52678ec722'
OLD = 'mitmproxy-12.2.3.dist-info/'
NEW = 'mitmproxy-12.2.3+lantern1.dist-info/'
CHANGES = {
    'Version: 12.2.3': 'Version: 12.2.3+lantern1',
    'Requires-Dist: cryptography<=48.1,>=42.0': 'Requires-Dist: cryptography==50.0.1',
    'Requires-Dist: h2<=4.3.0,>=4.3.0': 'Requires-Dist: h2==4.4.1',
    'Requires-Dist: msgpack<=1.1.2,>=1.0.0': 'Requires-Dist: msgpack==1.2.2',
    'Requires-Dist: tornado<=6.5.5,>=6.5.0': 'Requires-Dist: tornado==6.5.8',
}


def patch(source, output):
    raw = Path(source).read_bytes()
    if hashlib.sha256(raw).hexdigest() != UPSTREAM_SHA256:
        raise ValueError('unreviewed upstream wheel')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
        if len(files) != len(archive.namelist()):
            raise ValueError('duplicate wheel members')
    metadata = files[OLD + 'METADATA'].decode()
    for before, after in CHANGES.items():
        if metadata.splitlines().count(before) != 1:
            raise ValueError('upstream metadata differs: ' + before)
        metadata = metadata.replace(before + '\n', after + '\n')
    files[OLD + 'METADATA'] = metadata.encode()
    files.pop(OLD + 'RECORD')
    files = {(NEW + name[len(OLD):] if name.startswith(OLD) else name): data
             for name, data in files.items()}
    record = io.StringIO(newline='')
    writer = csv.writer(record, lineterminator='\n')
    for name, data in sorted(files.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()
        writer.writerow((name, 'sha256=' + digest, len(data)))
    writer.writerow((NEW + 'RECORD', '', ''))
    files[NEW + 'RECORD'] = record.getvalue().encode()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(files.items()):
            item = zipfile.ZipInfo(name, date_time=(2026, 9, 11, 0, 0, 0))
            item.create_system = 3
            item.external_attr = 0o100644 << 16
            archive.writestr(item, data)
    result = {'upstream_sha256': UPSTREAM_SHA256,
              'candidate_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
              'version': '12.2.3+lantern1', 'runtime_members_changed': 0,
              'changes': CHANGES, 'members': len(files)}
    print(json.dumps(result, sort_keys=True, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source')
    parser.add_argument('output')
    args = parser.parse_args()
    patch(args.source, args.output)
