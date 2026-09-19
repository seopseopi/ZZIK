"""Exercise the trash lifecycle with a real temporary SQLite DB and local files."""
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from backend.app import main, services, worker
from backend.app.db import Base, get_db
from backend.app.models import FileCleanup, Photo
from backend.app.storage import LocalStorage


@pytest.fixture
def trash_api(tmp_path, monkeypatch):
    engine = create_engine(f'sqlite:///{tmp_path / "trash-test.db"}', connect_args={'check_same_thread': False})
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    def dependency():
        with factory() as db:
            yield db
    main.app.dependency_overrides[get_db] = dependency
    storage = LocalStorage(tmp_path / 'photos')
    monkeypatch.setattr(main, 'get_storage', lambda: storage)
    monkeypatch.setattr(services, 'SessionLocal', factory)
    monkeypatch.setattr(worker, 'SessionLocal', factory)
    clients = []
    try:
        for name in ('owner', 'member', 'outsider'):
            client = TestClient(main.app)
            response = client.post('/api/auth/register', json={'name': name, 'email': f'{name}@trash.test', 'password': 'TrashTest123!'})
            assert response.status_code == 201, response.text
            client.headers['X-CSRF-Token'] = response.json()['csrf_token']
            clients.append(client)
        owner, member, outsider = clients
        album = owner.post('/api/albums', json={'name': 'Trash test'}).json()
        assert member.post('/api/albums/join', json={'code': album['invite_code']}).status_code == 200
        image = io.BytesIO()
        Image.new('RGB', (32, 24), 'red').save(image, format='PNG')
        response = owner.post(f'/api/albums/{album["id"]}/photos', data={'request_id': 'trash-photo'}, files={'file': ('trash.png', image.getvalue(), 'image/png')})
        assert response.status_code == 201, response.text
        yield owner, member, outsider, album, response.json(), factory, storage
    finally:
        for client in clients:
            client.close()
        main.app.dependency_overrides.clear()
        engine.dispose()


def test_trash_hides_photo_preserves_files_and_versions_and_restores(trash_api):
    owner, _, _, album, photo, factory, storage = trash_api
    path = f'/api/photos/{photo["id"]}'
    listing = f'/api/albums/{album["id"]}/photos'
    response = owner.post(path + '/versions', json={'name': 'Saved edit', 'brightness': 1.1, 'saturation': 1})
    assert response.status_code == 201, response.text
    version_id = response.json()['id']
    original = owner.get(path + '/file?kind=original').content
    result = owner.post(path + '/trash')
    assert result.status_code == 200, result.text
    assert result.json()['trashed_at']
    # Retrying the request keeps the original trash timestamp.
    assert owner.post(path + '/trash').json()['trashed_at'] == result.json()['trashed_at']
    assert owner.get(listing).json()['total'] == 0
    assert owner.get(listing + '?trashed=true').json()['items'][0]['id'] == photo['id']
    assert owner.get(f'/api/albums/{album["id"]}').json()['photo_count'] == 0
    assert owner.get(f'/api/albums/{album["id"]}').json()['cover_url'] is None
    assert not any(owner.get(f'/api/albums/{album["id"]}/board').json().values())
    assert owner.get(f'/api/albums/{album["id"]}/analysis-status').json()['total'] == 0
    assert owner.get(path + '/file?kind=original').content == original
    assert owner.patch(path, json={'note': 'must not change'}).status_code == 409
    with factory() as db:
        assert db.get(Photo, photo['id']) is not None
        assert db.scalar(select(FileCleanup)) is None
    assert owner.post(path + '/restore').status_code == 200
    assert owner.post(path + '/restore').status_code == 200
    assert owner.get(listing).json()['total'] == 1
    assert owner.get(listing + '?trashed=true').json()['total'] == 0
    assert owner.get(path).json()['versions'][0]['id'] == version_id
    assert owner.get(path + '/file?kind=original').content == original


def test_trash_and_restore_require_uploader_or_owner_and_keep_album_scope(trash_api):
    owner, member, outsider, album, photo, _, _ = trash_api
    path = f'/api/photos/{photo["id"]}'
    assert member.post(path + '/trash').status_code == 403
    assert outsider.post(path + '/trash').status_code == 404
    assert owner.post(path + '/trash').status_code == 200
    assert member.post(path + '/restore').status_code == 403
    assert outsider.post(path + '/restore').status_code == 404
    assert outsider.get(f'/api/albums/{album["id"]}/photos?trashed=true').status_code == 404
    assert member.get(f'/api/albums/{album["id"]}/photos?trashed=true').json()['total'] == 1
    other = owner.post('/api/albums', json={'name': 'Other album'}).json()
    assert owner.get(f'/api/albums/{other["id"]}/photos?trashed=true').json()['total'] == 0


def test_worker_does_not_claim_trashed_photos_until_restored(trash_api):
    owner, _, _, _, photo, _, _ = trash_api
    path = f'/api/photos/{photo["id"]}'
    assert owner.post(path + '/trash').status_code == 200
    assert worker.claim_job() is None
    assert owner.post(path + '/restore').status_code == 200
    assert worker.claim_job() is not None


def test_worker_rechecks_trash_when_claiming_a_previously_selected_candidate(trash_api):
    _, _, _, _, photo, factory, _ = trash_api
    engine = factory.kw['bind']
    @event.listens_for(engine, 'before_cursor_execute')
    def trash_before_claim(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith('UPDATE analysis_jobs'):
            cursor.execute('UPDATE photos SET trashed_at = CURRENT_TIMESTAMP WHERE id = ?', (photo['id'],))
    try:
        assert worker.claim_job() is None
    finally:
        event.remove(engine, 'before_cursor_execute', trash_before_claim)
