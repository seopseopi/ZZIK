"""Real DB, independent cookie jars, actual file and renderer integration.

TEST_DATABASE_URL must point to a dedicated database whose name ends in _test.
"""
import hashlib
import io
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from backend.app import main, services, worker
from backend.app.config import settings
from backend.app.db import Base, get_db
from backend.app.models import AnalysisJob, Photo, PhotoPerson, Person, Version
from backend.app.storage import LocalStorage


def png(color):
    output=io.BytesIO()
    Image.new('RGB',(120,96),color).save(output,format='PNG')
    return output.getvalue()


@pytest.fixture
def api(tmp_path,monkeypatch):
    url=os.getenv('TEST_DATABASE_URL')
    if not url: pytest.skip('Set TEST_DATABASE_URL to run PostgreSQL API integration tests')
    assert url.rsplit('/',1)[-1].endswith('_test'), 'Refusing destructive integration test setup outside a test database'
    engine=create_engine(url,pool_pre_ping=True)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        tables=', '.join('"'+t.name+'"' for t in Base.metadata.sorted_tables)
        connection.execute(text('TRUNCATE TABLE '+tables+' CASCADE'))
    factory=sessionmaker(engine,expire_on_commit=False)
    def dependency():
        with factory() as db:
            try: yield db
            except Exception:
                db.rollback()
                raise
    main.app.dependency_overrides[get_db]=dependency
    storage=LocalStorage(tmp_path/'files')
    monkeypatch.setattr(worker,'get_storage',lambda:storage)
    import backend.app.storage as storage_module
    monkeypatch.setattr(storage_module,'get_storage',lambda:storage)
    monkeypatch.setattr(worker,'SessionLocal',factory)
    monkeypatch.setattr(services,'SessionLocal',factory)
    monkeypatch.setattr(settings,'storage_backend','local')
    monkeypatch.setattr(settings,'face_analysis_provider','fixture')
    samples={'a':png('red'),'b':png('blue'),'group':png('green'),'landscape':png('white'),'unknown':png('gray'),'failure':png('yellow')}
    box={'left':.1,'top':.1,'width':.2,'height':.3}
    entries={
        'a':{'reference_name':'a','faces':[{'person_name':'a','box':box}]},
        'b':{'reference_name':'b','faces':[{'person_name':'b','box':box}]},
        'group':{'faces':[{'person_name':'a','box':box},{'person_name':'b','box':dict(box,left=.5)}],'tags':['바다']},
        'landscape':{'faces':[]},
        'unknown':{'faces':[{'person_name':'stranger','box':box}]},
    }
    manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps({'fixtures':{hashlib.sha256(samples[k]).hexdigest():v for k,v in entries.items()}}))
    monkeypatch.setattr(settings,'fixture_manifest',str(manifest))
    clients=[]
    for name in ('Alice','Bob','Eve'):
        client=TestClient(main.app)
        response=client.post('/api/auth/register',json={'name':name,'email':name.lower()+'@test.local','password':'StrongPassword123!'})
        assert response.status_code==201,response.text
        client.headers['X-CSRF-Token']=response.json()['csrf_token']
        client.user=response.json()['user']
        clients.append(client)
    owner,member,outsider=clients
    response=owner.post('/api/albums',json={'name':'Test album'})
    assert response.status_code==201,response.text
    album=response.json()
    assert member.post('/api/albums/join',json={'code':album['invite_code']}).status_code==200
    yield owner,member,outsider,album,samples,factory,storage
    for client in clients: client.close()
    main.app.dependency_overrides.clear()
    engine.dispose()


def post_photo(client,album,samples,kind='group',request_id=None):
    response=client.post(f"/api/albums/{album['id']}/photos",data={'request_id':request_id or 'request-'+kind},files={'file':(kind+'.png',samples[kind],'image/png')})
    assert response.status_code==201,response.text
    return response.json()


def register_people(api):
    a,b,_,album,samples,_,_=api
    people=[]
    for client,kind in ((a,'a'),(b,'b')):
        response=client.post(f"/api/albums/{album['id']}/people",data={'name':kind,'user_id':client.user['id']},files={'file':(kind+'.png',samples[kind],'image/png')})
        assert response.status_code==201,response.text
        people.append(response.json())
    return people


def create_version(client,photo,name='edit',**settings):
    response=client.post(f"/api/photos/{photo['id']}/versions",json={'name':name,**settings})
    assert response.status_code==201,response.text
    return response.json()


def test_two_users_full_flow_permissions_and_original_preservation(api):
    a,b,e,album,samples,factory,storage=api
    people=register_people(api)
    photo=post_photo(a,album,samples)
    another=post_photo(b,album,samples,'landscape')
    assert photo['analysis_status']=='pending'
    assert worker.process_one() and worker.process_one()
    assert not worker.process_one()
    photo=a.get('/api/photos/'+photo['id']).json()
    assert photo['analysis_status']=='completed' and photo['analysis_mode']=='sample'
    assert {p['id'] for p in photo['people']}=={p['id'] for p in people}
    for client in (a,b):
        result=client.get(f"/api/albums/{album['id']}/photos",params={'filter':'mine'}).json()
        assert [p['id'] for p in result['items']]==[photo['id']]
    base=f"/api/photos/{photo['id']}"
    for path in (base,base+'/file',base+'/download',f"/api/albums/{album['id']}/board"):
        assert e.get(path).status_code==404
    assert e.post(base+'/versions',json={'name':'intrusion'}).status_code==404
    assert e.post(base+'/preview',json={}).status_code==404
    assert e.put(base+'/people',json={'person_ids':[]}).status_code==404
    original=a.get(base+'/download').content
    assert hashlib.sha256(original).digest()==hashlib.sha256(samples['group']).digest()
    v1=create_version(a,photo,'warm',brightness=1.2,saturation=.6)
    review=a.post(f"/api/versions/{v1['id']}/request-review",json={'confirmed':True})
    assert review.status_code==200,review.text
    assert review.json()['target_count']==2 and review.json()['approval_count']==0
    assert e.post(f"/api/versions/{v1['id']}/approval").status_code==404
    assert a.post(f"/api/versions/{v1['id']}/approval").json()['approval_count']==1
    assert a.post(f"/api/versions/{v1['id']}/approval").json()['approval_count']==1
    assert b.post(f"/api/versions/{v1['id']}/approval").json()['consensus']
    assert a.post(f"/api/versions/{v1['id']}/final").json()['is_final']
    v2=create_version(b,photo,'alternative',parent_id=v1['id'],brightness=.7,saturation=1.4)
    assert v2['approval_count']==0 and not v2['review_requested']
    persisted=b.get(base).json()
    assert persisted['final_version_id']==v1['id'] and persisted['versions'][1]['approval_count']==2
    preview=a.post(base+'/preview',json={'brightness':1.2,'saturation':.6})
    export=b.get(base+'/download',params={'version_id':v1['id']})
    assert preview.status_code==export.status_code==200
    assert preview.content==export.content # source smaller than preview cap; same renderer and encoding
    assert Image.open(io.BytesIO(export.content)).size==(120,96)
    assert a.get(base+'/download').content==original
    assert a.get(f"/api/photos/{another['id']}/download",params={'version_id':v1['id']}).status_code==422
    comment=b.post(f"/api/versions/{v1['id']}/comments",json={'body':'조금 더 밝게 부탁해요.','kind':'change_request'})
    assert comment.status_code==201 and comment.json()['comments'][0]['author']['id']==b.user['id']
    assert a.get('/api/notifications').json()['total']>=1
    downloaded=a.get(f"/api/albums/{album['id']}/download",params={'photo_ids':photo['id']+','+another['id']})
    assert downloaded.status_code==200
    with ZipFile(io.BytesIO(downloaded.content)) as archive:
        assert len(archive.namelist())==2
        assert set(archive.read(n) for n in archive.namelist())=={samples['group'],samples['landscape']}
    assert b.delete(f"/api/versions/{v1['id']}/approval").json()['is_final'] is False
    assert a.get(base).json()['final_version_id'] is None
    # Fresh independent app connection still reads persisted data.
    fresh=TestClient(main.app)
    signed=fresh.post('/api/auth/login',json={'email':'alice@test.local','password':'StrongPassword123!'})
    assert signed.status_code==200
    assert len(fresh.get(base).json()['versions'])==2
    fresh.close()


def test_upload_retry_validation_failure_and_manual_exclusions(api):
    a,b,_,album,samples,factory,storage=api
    people=register_people(api)
    photo=post_photo(a,album,samples)
    assert post_photo(a,album,samples)['id']==photo['id']
    conflict=a.post(f"/api/albums/{album['id']}/photos",data={'request_id':'request-group'},files={'file':('other.png',samples['landscape'],'image/png')})
    assert conflict.status_code==409
    bad=a.post(f"/api/albums/{album['id']}/photos",data={'request_id':'invalid-1'},files={'file':('fake.png',b'not an image','image/png')})
    assert bad.status_code==422 and bad.json()['code']=='INVALID_IMAGE'
    badmime=a.post(f"/api/albums/{album['id']}/photos",data={'request_id':'invalid-2'},files={'file':('fake.jpg',samples['group'],'image/jpeg')})
    assert badmime.status_code==422 and badmime.json()['code']=='IMAGE_MIME_MISMATCH'
    assert worker.process_one()
    url='/api/photos/'+photo['id']
    change=a.put(url+'/people',json={'person_ids':[people[0]['id']]})
    assert change.status_code==200
    assert a.post(url+'/reanalyze').status_code==409
    # Force a failed state as an external failure would; retry must retain explicit exclusions.
    with factory() as db:
        p=db.get(Photo,photo['id']);p.analysis_status='failed'
        job=db.scalar(select(AnalysisJob).where(AnalysisJob.photo_id==p.id));job.status='failed'
        db.commit()
    assert a.post(url+'/reanalyze').status_code==200
    assert worker.process_one()
    assert [p['id'] for p in a.get(url).json()['people']]==[people[0]['id']]
    with factory() as db:
        assert db.get(PhotoPerson,(photo['id'],people[1]['id'])).excluded
    failed=post_photo(b,album,samples,'failure')
    assert worker.process_one()
    result=b.get('/api/photos/'+failed['id']).json()
    assert result['analysis_status']=='failed' and '실제 분석 연결 필요' in result['analysis_error']
    assert b.get('/api/photos/'+failed['id']+'/download').content==samples['failure']
    unknown=post_photo(a,album,samples,'unknown')
    assert worker.process_one()
    assert a.get('/api/photos/'+unknown['id']).json()['unknown_faces']==1
    assert a.get(f"/api/albums/{album['id']}/photos",params={'filter':'review'}).json()['total']==2


def test_person_links_consensus_invalidation_and_no_face_reviewer(api):
    a,b,e,album,samples,factory,storage=api
    people=register_people(api)
    assert b.patch('/api/people/'+people[0]['id'],json={'user_id':b.user['id']}).status_code==403
    assert b.post('/api/people/'+people[0]['id']+'/accept-link').status_code==403
    photo=post_photo(a,album,samples)
    assert worker.process_one()
    version=create_version(a,photo)
    url='/api/versions/'+version['id']
    assert a.post(url+'/request-review',json={'confirmed':False}).status_code==422
    assert a.post(url+'/request-review',json={'confirmed':True}).status_code==200
    a.post(url+'/approval');b.post(url+'/approval');a.post(url+'/final')
    changed=a.put('/api/photos/'+photo['id']+'/people',json={'person_ids':[people[0]['id']]})
    assert changed.json()['final_version_id'] is None and changed.json()['versions'][0]['needs_review']
    assert a.post(url+'/approval').status_code==409
    assert a.post(url+'/request-review',json={'confirmed':True}).status_code==409
    new=create_version(a,photo,parent_id=version['id'])
    new_url='/api/versions/'+new['id']
    assert a.post(new_url+'/request-review',json={'confirmed':True}).json()['target_count']==1
    assert b.post(new_url+'/approval').status_code==403
    assert a.post(new_url+'/approval').json()['consensus']
    assert a.post(new_url+'/final').json()['is_final']
    assert a.patch('/api/people/'+people[0]['id'],json={'user_id':None}).status_code==200
    assert a.get('/api/photos/'+photo['id']).json()['final_version_id'] is None
    assert a.patch('/api/people/'+people[0]['id'],json={'user_id':b.user['id']}).json()['link_status']=='pending'
    assert b.post('/api/people/'+people[0]['id']+'/accept-link').json()['user_id']==b.user['id']
    landscape=post_photo(b,album,samples,'landscape')
    assert worker.process_one()
    lv=create_version(a,landscape)
    targets=a.post('/api/versions/'+lv['id']+'/request-review',json={'confirmed':True}).json()['targets']
    assert [t['user_id'] for t in targets]==[b.user['id']]
    assert a.post('/api/versions/'+lv['id']+'/approval').status_code==403
    assert b.post('/api/versions/'+lv['id']+'/approval').json()['consensus']
    assert a.post('/api/versions/'+lv['id']+'/final').json()['is_final']
    assert b.delete(f"/api/albums/{album['id']}/members/{b.user['id']}").status_code==200
    assert a.get('/api/photos/'+landscape['id']).json()['final_version_id'] is None
    assert b.get('/api/photos/'+landscape['id']).status_code==404


def test_concurrent_approvals_revocation_and_csrf(api):
    a,b,_,album,samples,_,_=api
    register_people(api)
    photo=post_photo(a,album,samples)
    assert worker.process_one()
    version=create_version(a,photo)
    url='/api/versions/'+version['id']
    assert a.post(url+'/request-review',json={'confirmed':True}).status_code==200
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda c:c.post(url+'/approval'),[a,b]))
    assert all(r.status_code==200 for r in results)
    assert a.get('/api/photos/'+photo['id']).json()['versions'][0]['approval_count']==2
    with ThreadPoolExecutor(max_workers=2) as pool:
        final=pool.submit(a.post,url+'/final')
        revoke=pool.submit(b.delete,url+'/approval')
        assert final.result().status_code in (200,409)
        assert revoke.result().status_code==200
    assert a.get('/api/photos/'+photo['id']).json()['final_version_id'] is None
    token=a.headers.pop('X-CSRF-Token')
    assert a.post('/api/albums',json={'name':'csrf'}).status_code==403
    a.headers['X-CSRF-Token']=token
    assert a.post('/api/albums',json={'name':'foreign'},headers={'Origin':'https://evil.example'}).status_code==403
    assert a.post('/api/auth/logout').status_code==200
    assert a.get('/api/albums').status_code==401


def test_filters_cross_album_parent_and_delete_cleanup(api):
    a,b,e,album,samples,factory,storage=api
    people=register_people(api)
    photo=post_photo(a,album,samples)
    one=post_photo(a,album,samples,'a')
    none=post_photo(a,album,samples,'landscape')
    while worker.process_one(): pass
    base=f"/api/albums/{album['id']}/photos"
    ids=','.join(p['id'] for p in people)
    assert a.get(base,params={'people':ids,'match':'all'}).json()['total']==1
    assert a.get(base,params={'people':ids,'match':'any'}).json()['total']==2
    assert a.get(base,params={'filter':'solo'}).json()['total']==1
    assert a.get(base,params={'filter':'solo','mine':True}).json()['total']==1
    assert b.get(base,params={'filter':'solo','mine':True}).json()['total']==0
    assert a.get(base,params={'filter':'group'}).json()['total']==1
    assert a.get(base,params={'filter':'no_faces'}).json()['total']==1
    assert a.get(base,params={'tag':'바다'}).json()['total']==1
    assert a.get(base,params={'page_size':1}).json()['total']==3
    version=create_version(a,photo)
    assert a.post('/api/photos/'+one['id']+'/versions',json={'name':'bad','parent_id':version['id']}).status_code==422
    foreign=e.post('/api/albums',json={'name':'foreign'}).json()
    r=e.post(f"/api/albums/{foreign['id']}/people",data={'name':'eve','user_id':e.user['id']},files={'file':('a.png',samples['a'],'image/png')})
    assert r.status_code==201
    assert a.put('/api/photos/'+photo['id']+'/people',json={'person_ids':[r.json()['id']]}).status_code==422
    assert b.delete('/api/photos/'+photo['id']).status_code==403
    with factory() as db: original_key=db.get(Photo,photo['id']).original_key
    assert storage.exists(original_key)
    assert a.delete('/api/photos/'+photo['id']).status_code==200
    assert not storage.exists(original_key)
    assert a.get('/api/photos/'+photo['id']).status_code==404
    assert a.get(f"/api/albums/{album['id']}/face-groups").json()['available'] is False
    assert a.post(f"/api/albums/{album['id']}/face-groups/analyze").status_code==409


def test_partial_storage_failure_cleanup_and_concurrent_retry(api,monkeypatch):
    from backend.app.models import FileCleanup
    a,b,_,album,samples,factory,storage=api
    real_put=storage.put
    calls=0
    def broken_put(key,data,content_type='application/octet-stream'):
        nonlocal calls
        calls+=1
        if calls==2: raise OSError('simulated disk failure')
        return real_put(key,data,content_type)
    monkeypatch.setattr(storage,'put',broken_put)
    with pytest.raises(OSError):
        a.post(f"/api/albums/{album['id']}/photos",data={'request_id':'retry-partial'},files={'file':('group.png',samples['group'],'image/png')})
    with factory() as db:
        assert not db.scalars(select(Photo)).all()
        assert not db.scalars(select(FileCleanup)).all()
    assert not list(storage.root.rglob('original'))
    monkeypatch.setattr(storage,'put',real_put)
    # Use distinct independent sessions for concurrent same-user network retries.
    retry=TestClient(main.app)
    response=retry.post('/api/auth/login',json={'email':'alice@test.local','password':'StrongPassword123!'})
    retry.headers['X-CSRF-Token']=response.json()['csrf_token']
    with ThreadPoolExecutor(max_workers=2) as pool:
        photos=list(pool.map(lambda client:post_photo(client,album,samples,request_id='retry-partial'),[a,retry]))
    assert photos[0]['id']==photos[1]['id']
    assert a.get(f"/api/albums/{album['id']}/photos").json()['total']==1
    with factory() as db: assert not db.scalars(select(FileCleanup)).all()
    retry.close()


def test_unlinked_review_blocks_and_new_members_do_not_change_snapshot(api):
    a,b,e,album,samples,factory,_=api
    result=a.post(f"/api/albums/{album['id']}/people",data={'name':'unlinked'},files={'file':('a.png',samples['a'],'image/png')})
    assert result.status_code==201
    person=result.json()
    photo=post_photo(a,album,samples,'a')
    assert worker.process_one()
    version=create_version(a,photo)
    url='/api/versions/'+version['id']
    blocked=a.post(url+'/request-review',json={'confirmed':True})
    assert blocked.status_code==409 and blocked.json()['code']=='UNLINKED_PEOPLE'
    assert a.patch('/api/people/'+person['id'],json={'user_id':b.user['id']}).status_code==200
    assert b.post('/api/people/'+person['id']+'/accept-link').status_code==200
    # Before first request, linking may resolve targets on the same version.
    assert a.post(url+'/request-review',json={'confirmed':True}).json()['target_count']==1
    assert e.post('/api/albums/join',json={'code':album['invite_code']}).status_code==200
    assert a.post(url+'/request-review',json={'confirmed':True}).json()['target_count']==1
    assert e.post(url+'/approval').status_code==403
    assert b.post(url+'/approval').json()['consensus']
    assert a.post(url+'/final').json()['is_final']
    # Concurrent saves receive monotonically distinct server version numbers.
    with ThreadPoolExecutor(max_workers=2) as pool:
        versions=list(pool.map(lambda client:create_version(client,photo),[a,b]))
    assert sorted(v['number'] for v in versions)==[2,3]


def test_group_link_merge_split_rechecks_consensus(api):
    from backend.app.models import FaceGroup,GroupFace
    a,b,_,album,samples,factory,_=api
    people=register_people(api)
    first=post_photo(a,album,samples,'landscape')
    second=post_photo(a,album,samples,'landscape','landscape-2')
    while worker.process_one(): pass
    with factory() as db:
        g1=FaceGroup(album_id=album['id'],name='one');g2=FaceGroup(album_id=album['id'],name='two')
        db.add_all([g1,g2]);db.flush()
        f1=GroupFace(group_id=g1.id,photo_id=first['id'],external_face_id='remote-one',box={})
        f2=GroupFace(group_id=g2.id,photo_id=second['id'],external_face_id='remote-two',box={})
        db.add_all([f1,f2]);db.commit()
        ids=g1.id,g2.id,f1.id,f2.id
    assert a.patch('/api/face-groups/'+ids[0],json={'person_id':people[0]['id']}).status_code==200
    assert a.get('/api/photos/'+first['id']).json()['people'][0]['id']==people[0]['id']
    merged=a.post('/api/face-groups/merge',json={'group_ids':list(ids[:2])})
    assert merged.status_code==200,merged.text
    assert merged.json()['face_count']==2
    assert a.get('/api/photos/'+second['id']).json()['people'][0]['id']==people[0]['id']
    version=create_version(a,second)
    url='/api/versions/'+version['id']
    assert a.post(url+'/request-review',json={'confirmed':True}).status_code==200
    assert a.post(url+'/approval').json()['consensus']
    assert a.post(url+'/final').json()['is_final']
    separated=a.post('/api/face-groups/'+merged.json()['id']+'/split',json={'face_ids':[ids[3]]})
    assert separated.status_code==201,separated.text
    photo=a.get('/api/photos/'+second['id']).json()
    assert photo['people']==[] and photo['final_version_id'] is None
    assert photo['versions'][0]['needs_review']
