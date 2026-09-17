#!/usr/bin/env python3
"""Create synthetic data, lose its isolated DB/files, and recover from the backup."""
from __future__ import annotations

import json
from contextlib import ExitStack
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.backup_local import backup, create_database, database_url, drop_database, restore
from scripts.run_integration import free_port, interrupted, stop, wait_ready


def main():
    admin = database_url(os.environ.get('ZZIK_E2E_DATABASE_URL', ''), admin=True)
    port = free_port()
    base = f'http://127.0.0.1:{port}'
    logdir = ROOT / 'logs/recovery' / uuid.uuid4().hex
    logdir.mkdir(parents=True, mode=0o700)
    env = dict(os.environ)
    env.update(STORAGE_BACKEND='local', FACE_ANALYSIS_PROVIDER='fixture', DEMO_ENABLED='true',
               COOKIE_SECURE='false', ALLOWED_ORIGINS=base, GEOCODING_URL='',
               FIXTURE_MANIFEST=str(ROOT / 'backend/fixtures/manifest.json'), AWS_EC2_METADATA_DISABLED='true')
    databases, children, handles = [], [], []

    def checked(command):
        with (logdir / 'commands.log').open('ab') as log:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                if process.wait():
                    raise RuntimeError('Recovery command failed; inspect logs/recovery locally.')
            finally:
                stop([process])

    def launch_backend(label):
        for name, command in (
            ('api', [sys.executable, '-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1', '--port', str(port)]),
            ('worker', [sys.executable, '-m', 'backend.app.worker']),
        ):
            handle = (logdir / f'{label}-{name}.log').open('w')
            handles.append(handle)
            children.append(subprocess.Popen(command, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True))
        wait_ready(base + '/api/health/ready', children)

    def halt():
        stop(children)
        children.clear()

    try:
        with tempfile.TemporaryDirectory(prefix='zzik-recovery-') as directory, ExitStack() as services:
            services.callback(halt)
            work = Path(directory)
            source = create_database(admin)
            databases.append(source)
            env.update(DATABASE_URL=source.render_as_string(hide_password=False), STORAGE_ROOT=str(work / 'original'))
            checked([sys.executable, '-m', 'alembic', '-c', 'backend/alembic.ini', 'upgrade', 'head'])
            checked([sys.executable, '-m', 'backend.app.seed'])
            launch_backend('source')
            scenario = [sys.executable, 'scripts/verify_restart.py']
            options = ['--base-url', base, '--state-file', str(work / 'scenario.json')]
            checked([*scenario, 'setup', *options])
            halt()  # Freeze all app/worker writes before pairing DB and file snapshots.
            manifest = backup(source, work / 'original', work / 'backup', writes_stopped=True)
            print('BACKUP PASSED: stopped writers; captured PostgreSQL and local photo checksums.', flush=True)

            # Only generated fixture resources are destroyed; no user-supplied DB is reset.
            drop_database(admin, source)
            databases.remove(source)
            shutil.rmtree(work / 'original')
            print('SOURCE REMOVED: temporary fixture DB and source photos no longer exist.', flush=True)
            started = time.monotonic()
            target, _ = restore(admin, work / 'backup', work / 'restored')
            databases.append(target)
            env.update(DATABASE_URL=target.render_as_string(hide_password=False), STORAGE_ROOT=str(work / 'restored'))
            checked([sys.executable, '-m', 'alembic', '-c', 'backend/alembic.ini', 'check'])
            launch_backend('restored')
            checked([*scenario, 'verify', *options])
            restore_seconds = round(time.monotonic() - started, 2)
            # A fresh upload must pass through the restored API, DB, worker and file store.
            checked([*scenario, 'setup', *options])
            checked([*scenario, 'verify', *options])
            halt()
            print(json.dumps({'status': 'recovery_passed', 'scope': 'local_postgres_and_photos',
                              'source_removed_before_restore': True, 'photo_files': len(manifest['photos']),
                              'tables': len(manifest['database']['table_counts']),
                              'alembic_revisions': manifest['database']['alembic_revisions'],
                              'restore_and_api_verification_seconds': restore_seconds,
                              'session_original_render_approval_final_verified': True,
                              'new_upload_and_worker_verified': True}, ensure_ascii=False), flush=True)
    finally:
        halt()
        for handle in handles:
            handle.close()
        for database in reversed(databases):
            drop_database(admin, database)
    print('RECOVERY CLEANUP PASSED: disposable databases, backup and photo directories removed.')


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, interrupted)
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        # Do not expose connection strings, app responses, sessions or raw SQL errors.
        print(f'Recovery drill failed ({type(exc).__name__}); inspect local logs/recovery.', file=sys.stderr)
        sys.exit(1)
