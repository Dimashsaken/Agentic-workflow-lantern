"""Create/stop a fresh temporary local test cluster, never the configured cluster."""
import asyncio
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile

import asyncpg

OUT = Path(__file__).resolve().parent


def run(argv):
    result = subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True, timeout=90,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError('owned PostgreSQL operation failed; inspect temporary local log')
    return result


async def start():
    binary = Path(os.environ['QA_PROOF_PG_BIN'])
    port = int(os.environ['QA_PROOF_PG_PORT'])
    if port == 5432:
        raise RuntimeError('configured default port is forbidden')
    sock = socket.socket()
    try:
        sock.bind(('127.0.0.1',port))
    finally:
        sock.close()
    root = Path(tempfile.mkdtemp(prefix='lantern-c3-qa-postgres-')).resolve()
    data, password = root/'data', root/'password'
    password.write_text(secrets.token_urlsafe(32))
    run([str(binary/'initdb.exe'),'-D',str(data),'-U','lantern','--pwfile',str(password),
         '--auth-host=scram-sha-256','--auth-local=scram-sha-256','--encoding=UTF8','--no-locale'])
    run([str(binary/'pg_ctl.exe'),'-D',str(data),'-l',str(root/'postgres.log'),'-o',
         f'-h 127.0.0.1 -p {port}','-w','start'])
    # The DSN is only in this process environment, not in evidence output.
    os.environ['QA_PROOF_ADMIN_DSN'] = f'postgresql://lantern:{password.read_text()}@127.0.0.1:{port}/postgres'
    conn = await asyncpg.connect(os.environ['QA_PROOF_ADMIN_DSN'])
    try:
        await conn.execute('CREATE DATABASE lantern_validation')
    finally:
        await conn.close()
    state = dict(root=str(root), data=str(data), password_file=str(password), binary=str(binary), port=port)
    (root/'state.json').write_text(json.dumps(state))
    (OUT/'c3-disposable-db-readiness.json').write_text(json.dumps(dict(
        kind='fresh_disposable_postgres_readiness',passed=True,configured_cluster_touched=False,
        schema_applied=False,database_count_before_test_schema=0,bind_scope='loopback-only',
        existing_disposable_listener=False,new_cluster=True),indent=2)+'\n')
    print(json.dumps(dict(state_file=str(root/'state.json'),password_file=str(password),running=True)))


def stop(state_path):
    state = json.loads(Path(state_path).read_text())
    root = Path(state['root']).resolve()
    data = Path(state['data']).resolve()
    if not root.name.startswith('lantern-c3-qa-postgres-') or data != root/'data' or state['port'] == 5432:
        raise RuntimeError('refusing unknown cluster state')
    run([str(Path(state['binary'])/'pg_ctl.exe'),'-D',str(data),'-m','fast','-w','stop'])
    # Preserve the owned data/logs; no evidence or pre-existing files are removed.
    print(json.dumps(dict(stopped=True,retained=True)))


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == 'stop':
        stop(sys.argv[2])
    else:
        asyncio.run(start())
