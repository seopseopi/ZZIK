#!/usr/bin/env python3
"""Offline PostgreSQL + local photo backup; restore only into a new local drill DB."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


class BackupError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise BackupError(code)


def database_url(value, *, admin=False):
    try:
        url = make_url(value)
    except Exception:
        raise BackupError('INVALID_DATABASE_URL') from None
    require(url.get_backend_name() == 'postgresql' and url.host in {'127.0.0.1', 'localhost', '::1'}
            and bool(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,62}', url.database or ''))
            and bool(url.username) and not url.query, 'LOCAL_POSTGRES_REQUIRED')
    if admin:
        require(url.database.endswith('_e2e'), 'LOCAL_E2E_ADMIN_DATABASE_REQUIRED')
    return url.set(drivername='postgresql+psycopg')


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def inventory(root):
    require(root.is_dir() and not root.is_symlink(), 'PHOTO_DIRECTORY_REQUIRED')
    result = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'SYMLINK_NOT_SUPPORTED')
        if path.is_dir():
            continue
        require(path.is_file(), 'SPECIAL_FILE_NOT_SUPPORTED')
        result[path.relative_to(root).as_posix()] = {'sha256': digest(path), 'bytes': path.stat().st_size}
    return result


def copy_photos(source, destination, *, reserved=False):
    # Source inventory rejects symlinks before copy; no archive extraction is used.
    expected = inventory(source)
    shutil.copytree(source, destination, symlinks=True, dirs_exist_ok=reserved)
    for path in [destination, *destination.rglob('*')]:
        require(not path.is_symlink(), 'SYMLINK_NOT_SUPPORTED')
        path.chmod(0o700 if path.is_dir() else 0o600)
    require(inventory(destination) == expected, 'PHOTO_COPY_MISMATCH')
    return expected


def pg_tool(tool, url, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith('PG')}
    env.update(PGHOST=url.host, PGPORT=str(url.port or 5432), PGDATABASE=url.database,
               PGUSER=url.username, PGPASSWORD=url.password or '', PGCONNECT_TIMEOUT='5')
    # Connection secrets never appear in argv or raw child errors in CI output.
    result = subprocess.run([tool, '--no-password', *args], env=env, capture_output=True)
    require(result.returncode == 0, tool.upper() + '_FAILED')


def database_state(url, *, offline=False):
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            if offline:
                active = conn.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                                          "AND pid<>pg_backend_pid() AND (backend_type='client backend' OR backend_type IS NULL)"))
                require(active == 0, 'STOP_ALL_DATABASE_CLIENTS_FIRST')
            major = int(conn.scalar(text('SHOW server_version_num'))) // 10000
            revisions = list(conn.scalars(text('SELECT version_num FROM public.alembic_version ORDER BY version_num')))
            tables = list(conn.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")))
            counts = {name: conn.scalar(text('SELECT count(*) FROM public.' + conn.dialect.identifier_preparer.quote(name)))
                      for name in tables}
            return {'postgres_major': major, 'alembic_revisions': revisions, 'table_counts': counts}
    finally:
        engine.dispose()


def backup(url, storage, destination, *, writes_stopped=False):
    require(writes_stopped, 'WRITES_STOPPED_ACK_REQUIRED')
    storage, destination = Path(storage), Path(destination)
    require(storage.is_dir() and not storage.is_symlink(), 'PHOTO_DIRECTORY_REQUIRED')
    require(not destination.resolve().is_relative_to(storage.resolve()), 'BACKUP_INSIDE_STORAGE')
    require(not destination.exists() and not destination.is_symlink(), 'BACKUP_DESTINATION_EXISTS')
    before_files = inventory(storage)
    before_db = database_state(url, offline=True)
    destination.mkdir(mode=0o700, parents=True)
    # Only manifest.json marks a complete backup; partial files remain inspectable.
    dump = destination / 'database.dump'
    with dump.open('xb'):
        dump.chmod(0o600)
    pg_tool('pg_dump', url, '--format=custom', '--no-owner', '--no-acl', '--file', str(dump))
    files = copy_photos(storage, destination / 'photos')
    require(files == before_files and inventory(storage) == before_files, 'PHOTOS_CHANGED_DURING_BACKUP')
    require(database_state(url, offline=True) == before_db, 'DATABASE_CHANGED_DURING_BACKUP')
    manifest = {'format': 1, 'scope': 'local_postgres_and_photos', 'created_at': datetime.now(timezone.utc).isoformat(),
                'database': before_db, 'dump_sha256': digest(dump), 'photos': files}
    with (destination / 'manifest.json').open('x') as output:
        os.chmod(output.name, 0o600)
        json.dump(manifest, output, ensure_ascii=False, indent=2)
    return manifest


def verify_bundle(bundle):
    bundle = Path(bundle)
    require(bundle.is_dir() and not bundle.is_symlink(), 'BACKUP_DIRECTORY_REQUIRED')
    for name in ('manifest.json', 'database.dump'):
        require((bundle / name).is_file() and not (bundle / name).is_symlink(), 'BACKUP_INCOMPLETE')
    manifest = json.loads((bundle / 'manifest.json').read_text())
    require(manifest.get('format') == 1 and manifest.get('scope') == 'local_postgres_and_photos', 'BACKUP_FORMAT_UNSUPPORTED')
    require(digest(bundle / 'database.dump') == manifest['dump_sha256'], 'DATABASE_CHECKSUM_MISMATCH')
    require(inventory(bundle / 'photos') == manifest['photos'], 'PHOTO_CHECKSUM_MISMATCH')
    return manifest


def create_database(admin):
    name = 'zzik_restore_' + uuid.uuid4().hex + '_e2e'
    engine = create_engine(admin, isolation_level='AUTOCOMMIT')
    try:
        with engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}" TEMPLATE template0'))
    finally:
        engine.dispose()
    return admin.set(database=name)


def drop_database(admin, target):
    # Call only for databases this process successfully created, never user input.
    require(bool(re.fullmatch(r'zzik_restore_[0-9a-f]{32}_e2e', target.database)), 'INVALID_DRILL_DATABASE')
    engine = create_engine(admin, isolation_level='AUTOCOMMIT')
    try:
        with engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{target.database}"'))
    finally:
        engine.dispose()


def restore(admin, bundle, storage):
    manifest = verify_bundle(bundle)  # No DB mutation before complete integrity check.
    storage, bundle = Path(storage), Path(bundle)
    require(not storage.exists() and not storage.is_symlink(), 'RESTORE_STORAGE_MUST_BE_NEW')
    require(not storage.resolve().is_relative_to(bundle.resolve()), 'RESTORE_INSIDE_BACKUP')
    target = create_database(admin)
    copied = False
    try:
        # Preserve target-local ownership/permissions, restore atomically on SQL errors.
        pg_tool('pg_restore', target, '--dbname', target.database, '--single-transaction', '--exit-on-error',
                '--no-owner', '--no-acl', str(bundle / 'database.dump'))
        storage.mkdir(mode=0o700, parents=True)
        copied = True  # Only a directory exclusively created by this restore is cleaned up.
        copy_photos(bundle / 'photos', storage, reserved=True)
        require(database_state(target) == manifest['database'], 'RESTORED_DATABASE_MISMATCH')
        require(inventory(storage) == manifest['photos'], 'RESTORED_PHOTOS_MISMATCH')
    except BaseException:
        drop_database(admin, target)
        if copied and storage.exists():
            shutil.rmtree(storage)
        raise
    return target, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    save = modes.add_parser('backup')
    save.add_argument('--storage', type=Path, required=True)
    save.add_argument('--output', type=Path, required=True)
    save.add_argument('--writes-stopped', action='store_true')
    load = modes.add_parser('restore-drill')
    load.add_argument('--backup', type=Path, required=True)
    load.add_argument('--storage', type=Path, required=True)
    check = modes.add_parser('verify')
    check.add_argument('--backup', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.mode == 'backup':
            url = database_url(os.environ.get('ZZIK_BACKUP_DATABASE_URL', ''))
            result = backup(url, args.storage, args.output, writes_stopped=args.writes_stopped)
            print(json.dumps({'status': 'backup_complete', 'photo_files': len(result['photos'])}))
        elif args.mode == 'restore-drill':
            admin = database_url(os.environ.get('ZZIK_RESTORE_ADMIN_URL', ''), admin=True)
            target, _ = restore(admin, args.backup, args.storage)
            print(json.dumps({'status': 'restored_for_drill', 'database': target.database}))
        else:
            result = verify_bundle(args.backup)
            print(json.dumps({'status': 'integrity_verified', 'photo_files': len(result['photos'])}))
    except Exception as exc:
        print(json.dumps({'status': 'failed', 'code': str(exc) if isinstance(exc, BackupError) else type(exc).__name__}))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
