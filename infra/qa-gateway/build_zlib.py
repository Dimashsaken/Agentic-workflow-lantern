"""Build a locally versioned Debian zlib package with terminal gzip write errors.

This is a conservative mitigation, not an upstream CVE fix. A failed gzip writer
must be closed and reopened. In particular gzclearerr cannot revive a writer
whose compressor may retain a borrowed caller buffer after failed I/O.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request

SOURCE_URL = 'https://deb.debian.org/debian/pool/main/z/zlib/zlib_1.3.dfsg+really1.3.1.orig.tar.gz'
SOURCE_SHA256 = '60dd315c07f616887caa029408308a018ace66e3d142726a97db164b3b8f69fb'
BASE_VERSION = '1:1.3.dfsg+really1.3.1-1+b1'
VERSION = BASE_VERSION + '+lantern1'


def patch_source(root):
    changes = {
        'gzlib.c': (
            '    /* clear error and end-of-file */',
            '    /* Lantern: failed writers cannot safely reuse borrowed input. */\n'
            '    if (state->mode == GZ_WRITE && state->err != Z_OK)\n'
            '        return;\n\n'
            '    /* clear error and end-of-file */'),
        'gzwrite.c': (
            '    /* allocate memory if this is the first time through */',
            '    /* Lantern: also prevent gzclose_w from retrying failed input. */\n'
            '    if (state->err != Z_OK)\n'
            '        return -1;\n\n'
            '    /* allocate memory if this is the first time through */'),
    }
    hashes = {}
    for name, (old, new) in changes.items():
        path = root / name
        text = path.read_text()
        if name == 'gzwrite.c':
            start = text.index('local int gz_comp(')
            end = text.index('\n/* Compress len zeros', start)
            body = text[start:end]
            if body.count(old) != 1 or 'Lantern:' in body:
                raise ValueError('unexpected gz_comp source')
            changed = text[:start] + body.replace(old, new) + text[end:]
        else:
            if text.count(old) != 1 or 'Lantern:' in text:
                raise ValueError('unexpected gzclearerr source')
            changed = text.replace(old, new)
        hashes[name] = {'before': hashlib.sha256(text.encode()).hexdigest(),
                        'after': hashlib.sha256(changed.encode()).hexdigest()}
        path.write_text(changed)
    return hashes


def run(*args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()


def main():
    if run('dpkg-query', '-W', '-f=${Version}', 'zlib1g') != BASE_VERSION:
        raise RuntimeError('unreviewed base zlib package')
    work = Path('/build/zlib')
    work.mkdir(parents=True)
    archive = work / 'source.tar.gz'
    with urllib.request.urlopen(SOURCE_URL, timeout=120) as response:
        archive.write_bytes(response.read())
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise RuntimeError('zlib source hash mismatch')
    with tarfile.open(archive) as source:
        source.extractall(work, filter='data')
    root, = [p for p in work.iterdir() if p.is_dir()]
    hashes = patch_source(root)
    env = {**os.environ, 'CFLAGS': '-O2 -fPIC -fstack-protector-strong -D_FORTIFY_SOURCE=2',
           'LDFLAGS': '-Wl,-z,relro,-z,now', 'SOURCE_DATE_EPOCH': '1720000000'}
    subprocess.run(['./configure', '--shared', '--prefix=/usr'], cwd=root, env=env, check=True)
    subprocess.run(['make', '-j2'], cwd=root, env=env, check=True)
    subprocess.run(['make', 'test'], cwd=root, env=env, check=True)
    library = root / 'libz.so.1.3.1'
    original = Path('/usr/lib/x86_64-linux-gnu/libz.so.1.3.1')
    def symbols(path):
        return sorted(line.split()[-1] for line in run('nm', '-D', '--defined-only', str(path)).splitlines())
    if symbols(library) != symbols(original):
        raise RuntimeError('zlib exported ABI differs')
    subprocess.run(['python3.12', '/build/test_zlib.py', str(library)], check=True)
    package = work / 'package'
    package.mkdir()
    for name in run('dpkg-query', '-L', 'zlib1g').splitlines():
        path = Path(name)
        if path == Path('/'):
            continue
        target = package / path.relative_to('/')
        if path.is_symlink():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(os.readlink(path))
        elif path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    shutil.copy2(library, package / original.relative_to('/'))
    metadata = package / 'DEBIAN'
    metadata.mkdir()
    # Preserve original package relationships; honestly identify the local fork.
    control = run('dpkg-query', '-s', 'zlib1g').splitlines()
    control = [line for line in control if not line.startswith(('Status:', 'Installed-Size:', 'Version:', 'Source:'))]
    control[:0] = ['Version: ' + VERSION, 'Source: zlib (' + VERSION + ')']
    (metadata / 'control').write_text('\n'.join(control) + '\n')
    (metadata / 'triggers').write_text('activate-noawait ldconfig\n')
    provenance = {'source_url': SOURCE_URL, 'source_sha256': SOURCE_SHA256,
                  'base_package': BASE_VERSION, 'package': VERSION, 'patches': hashes,
                  'library_sha256': hashlib.sha256(library.read_bytes()).hexdigest(),
                  'exported_abi_unchanged': True, 'compiler': run('gcc', '--version').splitlines()[0],
                  'mitigation': 'gzip write I/O errors are terminal; close and reopen required'}
    doc = package / 'usr/share/doc/zlib1g/lantern-mitigation.json'
    doc.write_text(json.dumps(provenance, indent=2) + '\n')
    (metadata / 'md5sums').write_text(''.join(
        hashlib.md5(p.read_bytes()).hexdigest() + '  ' + str(p.relative_to(package)) + '\n'
        for p in sorted(package.rglob('*')) if p.is_file() and not p.is_symlink() and metadata not in p.parents))
    Path('/out').mkdir(exist_ok=True)
    subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(package), '/out/zlib1g-lantern.deb'], check=True)
    Path('/out/zlib-provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')


if __name__ == '__main__':
    main()
