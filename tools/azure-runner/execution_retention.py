"""Controller-owned checkout retirement. Evidence retention remains indefinite.

Allocation, every Docker launch and retirement share a per-execution OS lock.
Unknown or interrupted allocation descriptors are inventory-only. Retirement
never infers process quiescence from a PID or from a missing Docker label.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time
from uuid import uuid4


class RetentionHeld(RuntimeError):
    pass


def authority_root():
    return Path(os.environ.get('LANTERN_RETENTION_AUTHORITY', str(Path.home() / '.lantern/retention')))


def key(execution_key):
    if not isinstance(execution_key, str) or not execution_key:
        raise RetentionHeld('missing execution identity')
    return hashlib.sha256(execution_key.encode()).hexdigest()


def safe_path(path, root, *, existing=True):
    root, path = Path(root).absolute(), Path(path).absolute()
    if path == root or not path.is_relative_to(root) or root == Path(root.anchor):
        raise RetentionHeld('path is outside the dedicated checkout root')
    # Inspect all ancestors, including above the supplied root, before resolving.
    for candidate in [*reversed(path.parents), path]:
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            if candidate == path and not existing:
                break
            raise RetentionHeld('missing path ancestor') from None
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise RetentionHeld('links and reparse points are forbidden')
    if path.resolve() != path or root.resolve() != root:
        raise RetentionHeld('noncanonical path')
    return path


def path_key(path):
    return hashlib.sha256(os.path.normcase(str(Path(path).absolute())).encode()).hexdigest()


def identity(path):
    st = Path(path).stat()
    return [st.st_dev, st.st_ino]


def atomic_json(path, value):
    tmp = path.with_name('.' + uuid4().hex + '.tmp')
    with tmp.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


@contextmanager
def locked(execution_key, authority=None, timeout=10):
    root = Path(authority or authority_root()).absolute()
    root.mkdir(parents=True, exist_ok=True)
    name = key(execution_key)
    for folder in ('locks-v2', 'records-v2', 'paths-v2'):
        (root/folder).mkdir(exist_ok=True)
        safe_path(root/folder, root)
    # One permanent pathname shared with legacy readers, even when they refuse
    # the v2 sentinel. Selecting a path by existence can split a live OS lock.
    lockpath = root / (name + '.lock')
    lockpath = safe_path(lockpath, root, existing=lockpath.exists())
    with lockpath.open('a+b') as lock:
        if os.fstat(lock.fileno()).st_size == 0:
            lock.write(b'0')
            lock.flush()
        start = time.monotonic()
        while True:
            try:
                if os.name == 'nt':
                    import msvcrt
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() - start >= timeout:
                    raise RetentionHeld('checkout lifecycle lock is busy') from None
                time.sleep(.02)
        try:
            descriptor = root/'records-v2'/(name+'.json')
            if not descriptor.exists() and (root/(name+'.json')).exists():
                descriptor = root/(name+'.json')
            descriptor = safe_path(descriptor, root, existing=descriptor.exists())
            yield descriptor
        finally:
            if os.name == 'nt':
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def _index_ancestors(auth, path):
    # Monotone markers: tombstones and legacy holds are never pruned. A marker
    # means at least one registered descendant, regardless of its current state.
    for ancestor in Path(path).absolute().parents:
        marker = auth / ('ancestor-' + path_key(ancestor) + '.json')
        if not marker.exists():
            atomic_json(marker, {'version': 1, 'path': str(ancestor)})


def reconcile_legacy_index(auth, index):
    stamp = auth.stat().st_mtime_ns
    for mapping in auth.glob('path-*.json'):
        if not re.fullmatch(r'path-[a-f0-9]{64}\.json', mapping.name):
            continue
        owned = json.loads(mapping.read_text())
        if mapping.name != 'path-' + path_key(owned['path']) + '.json':
            raise RetentionHeld('ownership mapping is inconsistent')
        _index_ancestors(index, owned['path'])
    if auth.stat().st_mtime_ns != stamp:
        raise RetentionHeld('legacy registry changed while rebuilding index')
    atomic_json(index/'complete.json', {'version': 2, 'legacy_mtime_ns': stamp})


@contextmanager
def path_index(authority):
    """One locked legacy rebuild; subsequent lookups scale with path depth only.

    Publish completeness last. A crash leaves conservative markers and forces a
    rebuild; allocation and mount checks share this lock so neither misses a path.
    """
    auth = Path(authority).absolute()
    with locked('retention:path-index:v1', auth):
        index = auth/'paths-v2'
        complete = index/'complete.json'
        stamp = json.loads(complete.read_text()) if complete.exists() else None
        # Legacy writers and permanent compatibility locks allocate in auth.
        # Registration reconciles that growth; steady mounts reuse existing locks.
        legacy_stamp = auth.stat().st_mtime_ns
        if stamp is None or stamp.get('legacy_mtime_ns') != legacy_stamp:
            reconcile_legacy_index(auth, index)
        elif stamp.get('version') != 2:
            raise RetentionHeld('unknown ownership index')
        yield index


@contextmanager
def allocation(path, root, execution_key, run_id, *, authority=None):
    root = Path(root).absolute()
    root.mkdir(parents=True, exist_ok=True)
    path = safe_path(path, root, existing=False)
    auth = Path(authority or authority_root()).absolute()
    if auth.is_relative_to(root) or root.is_relative_to(auth):
        raise RetentionHeld('retirement authority overlaps checkout root')
    with locked(execution_key, auth) as location:
        with path_index(auth) as index:
            if location.exists() or path.exists():
                raise RetentionHeld('checkout identity cannot be reused')
            record = {'version': 1, 'execution_key': execution_key, 'run_id': run_id,
                      'root': str(root), 'path': str(path), 'state': 'allocating',
                      'created_at': time.time(), 'docker_only': True}
            atomic_json(location, record)
            mapping = index / ('path-' + path_key(path) + '.json')
            if mapping.exists() or (auth/mapping.name).exists():
                raise RetentionHeld('checkout path already has an ownership record')
            _index_ancestors(index, path)
            atomic_json(mapping, {'execution_key': execution_key, 'path': str(path)})
            quarantine = root / ('.retired-' + key(execution_key))
            _index_ancestors(index, quarantine)
            atomic_json(index / ('path-' + path_key(quarantine) + '.json'), {'execution_key': execution_key, 'path': str(quarantine)})
            # Old readers still see immutable ownership. A v2 sentinel makes an
            # old same-key launch/retirement refuse, rather than assume legacy.
            for owned in (path, quarantine):
                atomic_json(auth/('path-'+path_key(owned)+'.json'), {'execution_key':execution_key,'path':str(owned)})
            atomic_json(auth/(key(execution_key)+'.json'), {'version':2,'protocol':'retention-v2-sentinel'})
            # Compatibility writes share the legacy directory with older
            # allocators. Reconcile it before accepting the new stamp; taking
            # just a timestamp here could absorb a concurrent legacy addition.
            reconcile_legacy_index(auth, index)
        # A slow clone holds only its own execution lock, never the path index.
        yield
        safe_path(path, root)
        record.update(state='ready', identity=identity(path))
        atomic_json(location, record)


def read(location):
    if location.stat().st_size > 64000:
        raise RetentionHeld('oversized descriptor')
    record = json.loads(location.read_text())
    if not isinstance(record, dict) or record.get('version') != 1:
        raise RetentionHeld('unknown descriptor')
    return record


@contextmanager
def worker_mount(path, execution_key, authority=None):
    """Unknown legacy roots cannot be retired; registered roots honor tombstones."""
    auth = Path(authority or authority_root()).absolute()
    mount_path = Path(path).absolute()
    with locked(execution_key, authority) as location, path_index(auth) as index:
        if (index / ('ancestor-' + path_key(mount_path) + '.json')).exists():
            raise RetentionHeld('ancestor mount would expose a registered checkout')
        for candidate in (mount_path, *mount_path.parents):
            for directory in (index, auth):
                mapping = directory / ('path-' + path_key(candidate) + '.json')
                if mapping.exists():
                    ownership = json.loads(mapping.read_text())
                    if ownership.get('execution_key') != execution_key:
                        raise RetentionHeld('checkout path belongs to a different execution')
        if location.exists():
            record = read(location)
            original = Path(record['path']).absolute()
            quarantine = Path(record['root']) / ('.retired-' + key(execution_key))
            if mount_path.is_relative_to(original) or mount_path.is_relative_to(quarantine):
                if record.get('state') != 'ready':
                    raise RetentionHeld('checkout is allocating or irreversibly retired')
                safe_path(path, record['root'])
                if record['execution_key'] != execution_key or identity(original) != record['identity']:
                    raise RetentionHeld('checkout identity changed')
        yield


def docker_mounts():
    ids = subprocess.run(['docker', 'ps', '-aq', '--no-trunc'], capture_output=True,
                         text=True, timeout=30, check=True).stdout.split()
    if any(not re.fullmatch('[a-f0-9]{64}', value) for value in ids):
        raise RetentionHeld('unrecognized container identity')
    mounts = []
    for container in ids:
        value = json.loads(subprocess.run(['docker', 'inspect', container], capture_output=True,
                                         text=True, timeout=30, check=True).stdout)
        if len(value) != 1 or value[0].get('Id') != container:
            raise RetentionHeld('container inventory changed')
        for mount in value[0].get('Mounts', []):
            if mount.get('Type') == 'bind':
                source = mount.get('Source')
                if not isinstance(source, str) or not source:
                    raise RetentionHeld('unknown bind mount source')
                # Desktop rewrites host paths into VM paths. Without a verified
                # mapping a negative overlap result would be an invented proof.
                if os.name == 'nt' and source.startswith('/'):
                    raise RetentionHeld('Docker Desktop mount mapping is not verified')
                mounts.append({'container': container, 'source': source})
    return mounts


async def database_check(conn, record, min_age_days=7):
    """Server time and authoritative terminal state, never a caller-supplied age."""
    row = await conn.fetchrow("SELECT *, clock_timestamp() AS server_now FROM stage_executions WHERE idempotency_key=$1 FOR UPDATE", record['execution_key'])
    if (not row or row['run_id'] != record['run_id'] or row['status'] not in {'succeeded', 'failed', 'skipped'}
            or row['lease_owner'] is not None or row['finished_at'] is None
            or (row['server_now']-row['finished_at']).total_seconds() < min_age_days*86400):
        raise RetentionHeld('execution is unknown, active, or inside retention period')
    if await conn.fetchval("SELECT EXISTS(SELECT 1 FROM execution_effects WHERE run_id=$1 AND status<>'confirmed')", record['run_id']):
        raise RetentionHeld('run has unreconciled external effects')
    # Source needed by a recorded verifier remains pinned indefinitely for now.
    output = row['output']
    if isinstance(output, str):
        output = json.loads(output)
    if output or row['error']:
        raise RetentionHeld('evidence or recovery diagnostics pin this checkout')


def inspect_tree(target):
    size = 0
    for directory, dirs, files in os.walk(target, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            st = path.lstat()
            if stat.S_ISLNK(st.st_mode) or getattr(st, 'st_file_attributes', 0) & 0x400:
                raise RetentionHeld('checkout contains a link or reparse point')
            if stat.S_ISREG(st.st_mode):
                if st.st_nlink != 1:
                    raise RetentionHeld('checkout contains multiply linked files')
                size += st.st_size
    return size


async def retire(conn, execution_key, *, apply=False, authority=None, inspect_mounts=docker_mounts,
                 min_age_days=7):
    if not isinstance(min_age_days, (int, float)) or not 0 <= min_age_days <= 36500:
        raise ValueError('invalid retention age')
    with locked(execution_key, authority) as location:
        if not location.exists():
            raise RetentionHeld('legacy checkout has no descriptor')
        record = read(location)
        if record['execution_key'] != execution_key or record.get('state') not in {'ready', 'retired', 'quarantined', 'deleted'}:
            raise RetentionHeld('unknown or incomplete allocation')
        if record['state'] == 'deleted':
            if apply:
                await audit(conn, record)
            return {'state': 'deleted', 'bytes': record.get('bytes', 0)}
        if record.get('docker_only') is not True:
            raise RetentionHeld('local process quiescence is unknown')
        async with conn.transaction():
            await conn.fetchrow('SELECT id FROM runs WHERE id=$1 FOR UPDATE', record['run_id'])
            await database_check(conn, record, min_age_days)
            original = Path(record['path'])
            target = original
            quarantine = Path(record['root']) / ('.retired-' + key(execution_key))
            if record['state'] in {'retired', 'quarantined'} and not original.exists():
                if record['state'] == 'quarantined' and not quarantine.exists():
                    if apply:
                        record['state'] = 'deleted'
                        atomic_json(location, record)
                        await audit(conn, record)
                    return {'state': 'deleted', 'bytes': record.get('bytes', 0), 'apply': apply}
                target = quarantine
            target = safe_path(target, record['root'])
            if identity(target) != record['identity']:
                raise RetentionHeld('checkout was substituted')
            size = inspect_tree(target)
            for mount in inspect_mounts():
                source = Path(mount['source']).absolute()
                if any(source.is_relative_to(p) or p.is_relative_to(source) for p in (original, quarantine)):
                    raise RetentionHeld('container still references checkout')
            result = {'state': record['state'], 'bytes': size, 'apply': apply, 'path': str(original)}
            if not apply:
                return result
            record.update(state='retired', bytes=size)
            atomic_json(location, record)  # Tombstone precedes the rename, permanently.
            if target == original:
                if quarantine.exists():
                    raise RetentionHeld('quarantine already exists')
                os.rename(original, quarantine)
            safe_path(quarantine, record['root'])
            if identity(quarantine) != record['identity']:
                raise RetentionHeld('quarantine identity changed')
            record['state'] = 'quarantined'
            atomic_json(location, record)
            def writable_retry(fn, path, exc):
                os.chmod(path, stat.S_IWRITE)
                fn(path)
            shutil.rmtree(quarantine, onexc=writable_retry)
            record['state'] = 'deleted'
            atomic_json(location, record)
            await audit(conn, record)
            return {**result, 'state': 'deleted'}


async def audit(conn, record):
    # Retry after a process death/DB rollback without inventing or duplicating a deletion.
    await conn.execute("""INSERT INTO events(run_id,actor,type,data)
      SELECT $1,'orchestrator','checkout_retired',$2::jsonb WHERE NOT EXISTS
      (SELECT 1 FROM events WHERE run_id=$1 AND type='checkout_retired' AND data->>'execution_key'=$3)""",
      record['run_id'], json.dumps({'execution_key': record['execution_key'], 'bytes': record.get('bytes', 0)}), record['execution_key'])


async def inventory(conn, root, *, authority=None, inspect_mounts=docker_mounts):
    """Diagnostic snapshot only: eligibility must be rechecked by retire(apply=True).

    Includes unknown top-level paths and deleted descriptors. Ages come from the
    database clock; filesystem timestamps never authorize retirement.
    """
    root, auth = Path(root).absolute(), Path(authority or authority_root()).absolute()
    records, seen = [], set()
    for location in sorted([*auth.glob('*.json'), *(auth/'records-v2').glob('*.json')]):
        if not re.fullmatch('[a-f0-9]{64}\\.json', location.name):
            continue
        if location.parent == auth and (auth/'records-v2'/location.name).exists():
            continue
        row = {'descriptor': location.name, 'bytes': None, 'age_seconds': None, 'eligible': False}
        try:
            record = read(safe_path(location, auth))
            if Path(record['root']).absolute() != root:
                continue
            original = safe_path(record['path'], root, existing=Path(record['path']).exists())
            quarantine = root/('.retired-'+key(record['execution_key']))
            seen.update((original, quarantine))
            row.update(path=str(original), execution_key=record['execution_key'], state=record['state'])
            target = original if original.exists() else quarantine
            if target.exists():
                row['bytes'] = inspect_tree(safe_path(target, root))
            elif record['state'] == 'deleted':
                row['bytes'] = 0
            age = await conn.fetchval("SELECT EXTRACT(EPOCH FROM (clock_timestamp()-finished_at)) FROM stage_executions WHERE idempotency_key=$1", record['execution_key'])
            row['age_seconds'] = float(age) if age is not None else None
            result = await retire(conn, record['execution_key'], authority=auth, inspect_mounts=inspect_mounts)
            row['eligible'] = result['state'] != 'deleted'
            row['held_reason'] = 'already deleted' if result['state'] == 'deleted' else None
        except Exception as error:
            # Database/provider diagnostics can contain credentials; retain only
            # our own bounded rejection text or the exception class.
            row['held_reason'] = str(error) if isinstance(error, RetentionHeld) else type(error).__name__
        records.append(row)
    if root.exists():
        for path in sorted(root.iterdir()):
            if path in seen:
                continue
            row = {'path': str(path), 'bytes': None, 'age_seconds': None, 'eligible': False,
                   'state': 'unknown', 'held_reason': 'legacy path without an allocation descriptor'}
            try:
                target = safe_path(path, root)
                row['bytes'] = inspect_tree(target) if target.is_dir() else target.stat().st_size
            except (OSError, RetentionHeld) as error:
                row['held_reason'] = str(error) if isinstance(error, RetentionHeld) else type(error).__name__
            records.append(row)
    return {'root': str(root), 'observed_at': time.time(), 'apply': False,
            'known_bytes': sum(r['bytes'] or 0 for r in records), 'entries': records}
