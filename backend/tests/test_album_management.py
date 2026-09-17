"""Album owner/member management and analysis operations through a real PostgreSQL DB."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Event

from sqlalchemy import event, func, select

from backend.app import main, worker
from backend.app.routers import albums, photos
from backend.app.models import (
    Album, AlbumMember, AnalysisJob, AnalysisRun, Approval, FileCleanup,
    Notification, Person, Photo, Version, now,
)
from backend.tests.test_api_integration import api, create_version, post_photo, register_people


def row(album, uploader, index, status='failed'):
    return Photo(id=f'management-photo-{index}', album_id=album['id'], uploader_id=uploader.user['id'],
                 request_id=f'management-request-{index}', filename=f'trip-{index:02d}.jpg',
                 original_key=f'private/original-{index}', thumbnail_key=f'private/thumb-{index}', display_key=f'private/display-{index}',
                 original_hash=str(index).zfill(64), mime='image/jpeg', width=100, height=80,
                 analysis_status=status, analysis_error='REAL_ANALYSIS_REQUIRED: 실제 분석 연결 필요' if status=='failed' else None)


def test_album_owner_settings_invite_rotation_and_membership_authority(api):
    owner,member,outsider,album,_,factory,_=api
    base=f"/api/albums/{album['id']}"
    for client,expected in ((member,403),(outsider,404)):
        assert client.patch(base,json={'name':'nope'}).status_code==expected
        assert client.post(base+'/invite').status_code==expected
        assert client.delete(base).status_code==expected
    assert member.delete(base+'/members/'+owner.user['id']).status_code==403
    assert owner.delete(base+'/members/'+owner.user['id']).json()['code']=='OWNER_CANNOT_LEAVE'
    assert owner.patch(base,json={'name':'   '}).status_code==422
    assert owner.patch(base,json={'name':'should roll back','timezone':'Not/AZone'}).status_code==422
    assert owner.get(base).json()['name']==album['name']
    changed=owner.patch(base,json={'name':'  가을 여행  ','description':'같이 고른 순간','timezone':'Asia/Tokyo'})
    assert changed.status_code==200,changed.text
    assert (changed.json()['name'],changed.json()['description'],changed.json()['timezone'])==('가을 여행','같이 고른 순간','Asia/Tokyo')
    rotated=owner.post(base+'/invite')
    assert rotated.status_code==200 and rotated.json()['invite_code']!=album['invite_code']
    assert outsider.post('/api/albums/join',json={'code':album['invite_code']}).status_code==404
    assert outsider.post('/api/albums/join',json={'code':rotated.json()['invite_code']}).status_code==200
    assert owner.get(base).json()['member_count']==3
    assert outsider.patch(base,json={'description':'nope'}).status_code==403
    with factory() as db:
        assert db.get(Album,album['id']).owner_id==owner.user['id']
        assert db.get(AlbumMember,(album['id'],outsider.user['id'])).role=='member'


def test_remove_member_invalidates_only_affected_consensus_and_preserves_originals(api):
    owner,member,_,album,samples,factory,storage=api
    people=register_people(api)
    group=post_photo(owner,album,samples)
    landscape=post_photo(owner,album,samples,'landscape')
    while worker.process_one(): pass
    versions=[]
    for photo in (group,landscape):
        version=create_version(owner,photo)
        base='/api/versions/'+version['id']
        assert owner.post(base+'/request-review',json={'confirmed':True}).status_code==200
        assert owner.post(base+'/approval').status_code==200
        if photo==group: assert member.post(base+'/approval').status_code==200
        assert owner.post(base+'/final').json()['is_final']
        versions.append(version)
    with factory() as db:
        pending=Person(album_id=album['id'],name='연결 대기',proposed_user_id=member.user['id'])
        db.add(pending)
        db.add(Notification(user_id=member.user['id'],album_id=album['id'],kind='review_requested',message='검증용 알림'))
        db.commit()
        pending_id=pending.id
    base=f"/api/albums/{album['id']}"
    assert owner.delete(base+'/members/'+member.user['id']).status_code==200
    assert member.get(base).status_code==404
    assert member.get('/api/photos/'+group['id']+'/download').status_code==404
    assert member.post('/api/versions/'+versions[0]['id']+'/approval').status_code==404
    changed=owner.get('/api/photos/'+group['id']).json()
    assert changed['final_version_id'] is None
    assert changed['versions'][0]['needs_review'] and not changed['versions'][0]['consensus']
    assert owner.get('/api/photos/'+landscape['id']).json()['final_version_id']==versions[1]['id']
    assert owner.get('/api/photos/'+group['id']+'/download').content==samples['group']
    with factory() as db:
        assert db.get(Person,people[1]['id']).user_id is None
        assert db.get(Person,pending_id).proposed_user_id is None
        assert not db.scalars(select(Notification).where(Notification.user_id==member.user['id'],Notification.album_id==album['id'])).all()
        # Historical approvals remain as history but can no longer form consensus.
        assert len(db.scalars(select(Approval).where(Approval.version_id==versions[0]['id'])).all())==2
    # Rejoining does not silently restore the old person link or final selection.
    assert member.post('/api/albums/join',json={'code':album['invite_code']}).status_code==200
    assert member.get('/api/photos/'+group['id']).json()['versions'][0]['needs_review']
    assert owner.delete(base).status_code==200
    assert owner.get(base).status_code==404
    with factory() as db:
        assert db.get(Album,album['id']) is None
        assert not db.scalars(select(Photo).where(Photo.album_id==album['id'])).all()
        assert not db.scalars(select(Version)).all()
        assert not db.scalars(select(FileCleanup)).all()
    assert not list(storage.root.rglob('original'))


def test_analysis_status_is_scoped_bounded_and_counts_recorded_retries(api):
    owner,member,outsider,album,_,factory,_=api
    earlier=now()-timedelta(minutes=12)
    with factory() as db:
        photos=[row(album,owner,index) for index in range(25)]
        photos.extend([row(album,owner,25,'pending'),row(album,owner,26,'processing'),row(album,owner,27,'completed')])
        db.add_all(photos);db.flush()
        db.add(AnalysisJob(photo_id=photos[25].id,status='pending',available_at=earlier))
        db.add(AnalysisJob(photo_id=photos[26].id,status='processing',locked_at=now(),locked_by='active-lease'))
        db.add_all([
            AnalysisRun(photo_id=photos[0].id,provider='rekognition',mode='live',status='failed',calls=2,elapsed_ms=100),
            AnalysisRun(photo_id=photos[0].id,provider='rekognition',mode='live',status='failed',calls=3,elapsed_ms=200),
            AnalysisRun(photo_id=photos[27].id,provider='fixture',mode='sample',status='completed',calls=0,elapsed_ms=50),
        ])
        db.commit()
    foreign=outsider.post('/api/albums',json={'name':'other album'}).json()
    with factory() as db:
        p=row(foreign,outsider,99)
        p.analysis_error='OTHER_ALBUM_ONLY'
        db.add(p);db.flush()
        db.add(AnalysisRun(photo_id=p.id,provider='rekognition',mode='live',status='failed',calls=999,elapsed_ms=99999))
        db.commit()
    path=f"/api/albums/{album['id']}/analysis-status"
    assert outsider.get(path).status_code==404
    response=member.get(path)
    assert response.status_code==200,response.text
    data=response.json()
    assert data['provider']=='fixture' and data['mode']=='sample'
    assert data['stats']=={'pending':1,'processing':1,'completed':1,'failed':25}
    assert data['total']==28
    assert (data['recorded_runs'],data['calls'],data['elapsed_ms'])==(3,5,350)
    assert len(data['failures'])==20
    assert all(item['photo_id']!='management-photo-99' for item in data['failures'])
    assert 'OTHER_ALBUM_ONLY' not in response.text and 'private/' not in response.text
    assert datetime.fromisoformat(data['oldest_pending_at'])==earlier
    empty=owner.post('/api/albums',json={'name':'empty'}).json()
    empty_status=owner.get(f"/api/albums/{empty['id']}/analysis-status").json()
    assert empty_status['total']==empty_status['recorded_runs']==empty_status['calls']==empty_status['elapsed_ms']==0
    assert empty_status['failures']==[] and empty_status['oldest_pending_at'] is None


def test_bulk_retry_is_idempotent_and_keeps_active_leases(api):
    owner,member,outsider,album,_,factory,_=api
    with factory() as db:
        photos=[row(album,owner,index,status) for index,status in enumerate(['failed','failed','failed','pending','processing','completed','failed'])]
        db.add_all(photos);db.flush()
        for index,status in [(0,'failed'),(1,'failed'),(3,'pending'),(4,'processing'),(5,'completed'),(6,'processing')]:
            db.add(AnalysisJob(photo_id=photos[index].id,status=status,attempts=3 if status=='failed' else 1,
                               locked_by='keep-this-lease' if status=='processing' else None,
                               locked_at=now() if status=='processing' else None,error='failed before retry' if status=='failed' else None))
        db.commit()
    path=f"/api/albums/{album['id']}/reanalyze-failed"
    assert outsider.post(path).status_code==404
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda client:client.post(path),[owner,member]))
    assert all(response.status_code==200 for response in results)
    assert sorted(response.json()['queued'] for response in results)==[0,3]
    assert member.post(path).json()=={'queued':0}
    with factory() as db:
        for index in (0,1,2):
            p=db.get(Photo,f'management-photo-{index}')
            job=db.scalar(select(AnalysisJob).where(AnalysisJob.photo_id==p.id))
            assert p.analysis_status==job.status=='pending'
            assert p.analysis_error is None and job.error is None
            assert job.attempts==0 and job.locked_by is None and job.finished_at is None
        assert db.get(Photo,'management-photo-5').analysis_status=='completed'
        for index in (4,6):
            job=db.scalar(select(AnalysisJob).where(AnalysisJob.photo_id==f'management-photo-{index}'))
            assert job.status=='processing' and job.locked_by=='keep-this-lease'
        assert db.scalar(select(func.count()).select_from(AnalysisJob))==7
    # A stale failed photo flag cannot let an individual retry take a worker's lease either.
    assert member.post('/api/photos/management-photo-6/reanalyze').json()['code']=='ANALYSIS_ALREADY_QUEUED'


def test_member_removal_waits_for_authorized_photo_mutation(api,monkeypatch):
    owner,member,_,album,samples,_,_=api
    photo=post_photo(owner,album,samples,'landscape')
    mutation_locked=Event(); release_mutation=Event(); removal_started=Event()
    actual_photo=photos.get_photo
    actual_membership=albums.membership
    def held_photo(db,photo_id,user,lock=False):
        result=actual_photo(db,photo_id,user,lock)
        if user.id==member.user['id'] and lock:
            mutation_locked.set()
            assert release_mutation.wait(10)
        return result
    def observed_membership(db,album_id,user,owner=False,exclusive=False):
        if exclusive: removal_started.set()
        return actual_membership(db,album_id,user,owner,exclusive)
    monkeypatch.setattr(photos,'get_photo',held_photo)
    monkeypatch.setattr(albums,'membership',observed_membership)
    with ThreadPoolExecutor(max_workers=2) as pool:
        mutation=pool.submit(member.patch,'/api/photos/'+photo['id'],json={'note':'saved before leaving'})
        assert mutation_locked.wait(5)
        removal=pool.submit(owner.delete,f"/api/albums/{album['id']}/members/{member.user['id']}")
        try:
            assert removal_started.wait(5)
            assert not removal.done()
        finally: release_mutation.set()
        assert mutation.result(timeout=10).status_code==200
        assert removal.result(timeout=10).status_code==200
    assert member.patch('/api/photos/'+photo['id'],json={'note':'not allowed'}).status_code==404
    assert owner.get('/api/photos/'+photo['id']).json()['note']=='saved before leaving'


def test_album_deletion_waits_for_upload_commit_and_cleans_new_files(api):
    owner,member,_,album,samples,factory,storage=api
    upload_staged=Event();release_upload=Event()
    def before_commit(db):
        if any(isinstance(obj,AnalysisJob) for obj in db.new):
            upload_staged.set()
            assert release_upload.wait(10)
    event.listen(factory.class_,'before_commit',before_commit)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            upload=pool.submit(post_photo,member,album,samples,'landscape')
            assert upload_staged.wait(5)
            deletion=pool.submit(owner.delete,f"/api/albums/{album['id']}")
            release_upload.set()
            assert upload.result(timeout=10)['id']
            assert deletion.result(timeout=10).status_code==200
    finally:
        release_upload.set()
        event.remove(factory.class_,'before_commit',before_commit)
    with factory() as db:
        assert db.get(Album,album['id']) is None
        assert not db.scalars(select(Photo)).all()
        assert not db.scalars(select(FileCleanup)).all()
    assert not list(storage.root.rglob('original'))
    assert not list(storage.root.rglob('thumbnail.jpg'))


def test_deleted_album_rejects_staged_upload_and_worker_publication(api,monkeypatch):
    owner,member,_,album,samples,factory,storage=api
    # A worker holds bytes outside its DB transaction while external analysis runs.
    photo=post_photo(owner,album,samples,'landscape')
    analyzing=Event();release_analysis=Event();original_written=Event();release_storage=Event()
    actual_analyze=worker.analyze;actual_put=storage.put
    def held_analysis(*args,**kwargs):
        result=actual_analyze(*args,**kwargs)
        analyzing.set()
        assert release_analysis.wait(10)
        return result
    def held_put(key,data,content_type='application/octet-stream'):
        result=actual_put(key,data,content_type)
        if key.endswith('/original'):
            original_written.set()
            assert release_storage.wait(10)
        return result
    monkeypatch.setattr(worker,'analyze',held_analysis)
    monkeypatch.setattr(storage,'put',held_put)
    with ThreadPoolExecutor(max_workers=3) as pool:
        analysis=pool.submit(worker.process_one)
        assert analyzing.wait(5)
        upload=pool.submit(member.post,f"/api/albums/{album['id']}/photos",data={'request_id':'upload-after-stage'},
                           files={'file':('new.png',samples['group'],'image/png')})
        assert original_written.wait(5)
        try:
            assert owner.delete(f"/api/albums/{album['id']}").status_code==200
        finally:
            release_storage.set();release_analysis.set()
        assert analysis.result(timeout=10)
        assert upload.result(timeout=10).status_code==404
    with factory() as db:
        assert db.get(Album,album['id']) is None
        assert not db.scalars(select(Photo)).all()
        assert not db.scalars(select(AnalysisJob)).all()
        assert not db.scalars(select(AnalysisRun)).all()
        assert not db.scalars(select(FileCleanup)).all()
    assert not list(storage.root.rglob('original'))
