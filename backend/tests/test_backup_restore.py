"""Guards that prevent an invalid backup from reaching a restore target."""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from scripts import backup_local as recovery


@pytest.mark.parametrize('value', [
    '', 'sqlite:///app.db', 'postgresql://user:pw@remote/zzik_e2e',
    'postgresql://user:pw@localhost/zzik_e2e?host=remote',
    'postgresql://localhost/zzik_e2e',
    'postgresql://user:pw@localhost/dbname=other%20host=remote',
])
def test_remote_or_ambiguous_database_rejected(value):
    with pytest.raises(recovery.BackupError):
        recovery.database_url(value)


def test_admin_requires_explicit_test_database():
    with pytest.raises(recovery.BackupError, match='LOCAL_E2E_ADMIN_DATABASE_REQUIRED'):
        recovery.database_url('postgresql://user:pw@localhost/production', admin=True)


def bundle(tmp_path):
    root = tmp_path / 'backup'
    root.mkdir()
    (root / 'database.dump').write_bytes(b'custom dump')
    (root / 'photos').mkdir()
    (root / 'photos/original.jpg').write_bytes(b'original')
    (root / 'manifest.json').write_text(json.dumps({
        'format': 1, 'scope': 'local_postgres_and_photos',
        'database': {}, 'dump_sha256': recovery.digest(root / 'database.dump'),
        'photos': recovery.inventory(root / 'photos'),
    }))
    return root


@pytest.mark.parametrize('change,code', [
    ('dump', 'DATABASE_CHECKSUM_MISMATCH'), ('photo', 'PHOTO_CHECKSUM_MISMATCH'),
    ('missing_photo', 'PHOTO_CHECKSUM_MISMATCH'), ('extra_photo', 'PHOTO_CHECKSUM_MISMATCH'),
    ('incomplete', 'BACKUP_INCOMPLETE'), ('symlink', 'SYMLINK_NOT_SUPPORTED'),
])
def test_corrupt_backup_never_creates_database(tmp_path, monkeypatch, change, code):
    root = bundle(tmp_path)
    if change == 'dump': (root / 'database.dump').write_bytes(b'broken')
    if change == 'photo': (root / 'photos/original.jpg').write_bytes(b'broken')
    if change == 'missing_photo': (root / 'photos/original.jpg').unlink()
    if change == 'extra_photo': (root / 'photos/unexpected.jpg').write_bytes(b'extra')
    if change == 'incomplete': (root / 'manifest.json').unlink()
    if change == 'symlink': (root / 'photos/link').symlink_to(root / 'database.dump')
    create = Mock()
    monkeypatch.setattr(recovery, 'create_database', create)
    with pytest.raises(recovery.BackupError, match=code):
        recovery.restore(None, root, tmp_path / 'restored')
    create.assert_not_called()


def test_restore_preserves_existing_storage(tmp_path, monkeypatch):
    root = bundle(tmp_path)
    destination = tmp_path / 'existing'
    destination.mkdir()
    marker = destination / 'keep.jpg'
    marker.write_bytes(b'keep')
    create = Mock()
    monkeypatch.setattr(recovery, 'create_database', create)
    with pytest.raises(recovery.BackupError, match='RESTORE_STORAGE_MUST_BE_NEW'):
        recovery.restore(None, root, destination)
    create.assert_not_called()
    assert marker.read_bytes() == b'keep'


@pytest.mark.parametrize('case,code', [
    ('running', 'WRITES_STOPPED_ACK_REQUIRED'), ('nested', 'BACKUP_INSIDE_STORAGE'),
    ('existing', 'BACKUP_DESTINATION_EXISTS'),
])
def test_invalid_backup_never_contacts_database(tmp_path, monkeypatch, case, code):
    storage = tmp_path / 'photos'
    storage.mkdir()
    output = storage / 'backup' if case == 'nested' else tmp_path / 'backup'
    if case == 'existing': output.mkdir()
    state = Mock()
    monkeypatch.setattr(recovery, 'database_state', state)
    with pytest.raises(recovery.BackupError, match=code):
        recovery.backup(None, storage, output, writes_stopped=case != 'running')
    state.assert_not_called()


def test_failed_dump_has_no_completion_manifest(tmp_path, monkeypatch):
    storage = tmp_path / 'photos'
    storage.mkdir()
    monkeypatch.setattr(recovery, 'database_state', lambda *_a, **_k: {})
    monkeypatch.setattr(recovery, 'pg_tool', Mock(side_effect=recovery.BackupError('PG_DUMP_FAILED')))
    with pytest.raises(recovery.BackupError, match='PG_DUMP_FAILED'):
        recovery.backup(None, storage, tmp_path / 'backup', writes_stopped=True)
    assert not (tmp_path / 'backup/manifest.json').exists()


def test_restore_sql_failure_removes_only_created_database(tmp_path, monkeypatch):
    root = bundle(tmp_path)
    target = recovery.database_url('postgresql://user:pw@localhost/zzik_restore_test_e2e')
    monkeypatch.setattr(recovery, 'create_database', lambda _: target)
    monkeypatch.setattr(recovery, 'pg_tool', Mock(side_effect=recovery.BackupError('PG_RESTORE_FAILED')))
    drop = Mock()
    monkeypatch.setattr(recovery, 'drop_database', drop)
    with pytest.raises(recovery.BackupError, match='PG_RESTORE_FAILED'):
        recovery.restore('admin', root, tmp_path / 'restored')
    drop.assert_called_once_with('admin', target)
    assert not (tmp_path / 'restored').exists()


def test_directory_created_during_restore_is_not_deleted(tmp_path, monkeypatch):
    root = bundle(tmp_path)
    target = recovery.database_url('postgresql://user:pw@localhost/zzik_restore_test_e2e')
    destination = tmp_path / 'restored'
    monkeypatch.setattr(recovery, 'create_database', lambda _: target)
    def restore_db(*_args):
        destination.mkdir()
        (destination / 'keep').write_text('concurrent user data')
    monkeypatch.setattr(recovery, 'pg_tool', restore_db)
    drop = Mock()
    monkeypatch.setattr(recovery, 'drop_database', drop)
    with pytest.raises(FileExistsError):
        recovery.restore('admin', root, destination)
    drop.assert_called_once_with('admin', target)
    assert (destination / 'keep').read_text() == 'concurrent user data'


def test_file_copy_failure_cleans_its_partial_restore(tmp_path, monkeypatch):
    root = bundle(tmp_path)
    target = recovery.database_url('postgresql://user:pw@localhost/zzik_restore_test_e2e')
    destination = tmp_path / 'restored'
    monkeypatch.setattr(recovery, 'create_database', lambda _: target)
    monkeypatch.setattr(recovery, 'pg_tool', Mock())
    def failed_copy(_source, output, **_kwargs):
        (output / 'partial').write_text('partial')
        raise recovery.BackupError('PHOTO_COPY_MISMATCH')
    monkeypatch.setattr(recovery, 'copy_photos', failed_copy)
    drop = Mock()
    monkeypatch.setattr(recovery, 'drop_database', drop)
    with pytest.raises(recovery.BackupError, match='PHOTO_COPY_MISMATCH'):
        recovery.restore('admin', root, destination)
    drop.assert_called_once_with('admin', target)
    assert not destination.exists()


def test_pg_tools_keep_credentials_out_of_argv_and_clear_inherited_options(monkeypatch):
    url = recovery.database_url('postgresql://user:secret@localhost/zzik_e2e')
    monkeypatch.setenv('PGOPTIONS', '-csearch_path=other')
    run = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(recovery.subprocess, 'run', run)
    recovery.pg_tool('pg_dump', url, '--format=custom')
    args, kwargs = run.call_args
    assert 'secret' not in ' '.join(args[0])
    assert kwargs['env']['PGPASSWORD'] == 'secret'
    assert 'PGOPTIONS' not in kwargs['env']
    assert kwargs['capture_output']


def test_copy_hashes_and_private_permissions(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'original.jpg').write_bytes(b'image')
    target = tmp_path / 'target'
    files = recovery.copy_photos(source, target)
    assert files == recovery.inventory(source) == recovery.inventory(target)
    assert target.stat().st_mode & 0o777 == 0o700
    assert (target / 'original.jpg').stat().st_mode & 0o777 == 0o600
