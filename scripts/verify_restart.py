"""Explicit smoke check across actual API/worker process restart; touches only its own album."""
import argparse
import hashlib
import json
import os
import time
from pathlib import Path
import httpx

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('phase',choices=['setup','verify'])
parser.add_argument('--base-url',default='http://127.0.0.1:8000')
parser.add_argument('--state-file',type=Path,default=root/'data/restart-check.json')
args=parser.parse_args()
state_path=args.state_file
client=httpx.Client(base_url=args.base_url,timeout=30)

def call(method,path,**kwargs):
    response=client.request(method,'/api'+path,**kwargs)
    response.raise_for_status()
    return response

if args.phase=='setup':
    if state_path.exists():raise SystemExit('Existing restart check state found; verify it before starting another.')
    session=call('POST','/auth/login',json={'email':'jisu@moacut.local','password':'MoacutDemo123!'}).json()
    client.headers['X-CSRF-Token']=session['csrf_token']
    album=call('POST','/albums',json={'name':'[검증] 프로세스 재시작 영속성'}).json()
    original=(root/'frontend/public/demo/sample-no-face.jpg').read_bytes()
    photo=call('POST',f"/albums/{album['id']}/photos",files={'file':('restart.jpg',original,'image/jpeg')},data={'request_id':'restart-check'}).json()
    state={'album_id':album['id'],'photo_id':photo['id'],'cookies':dict(client.cookies),'csrf':session['csrf_token'],'hash':hashlib.sha256(original).hexdigest()}
    state_path.parent.mkdir(exist_ok=True)
    state_path.write_text(json.dumps(state));os.chmod(state_path,0o600)
    for _ in range(60):
        data=call('GET',f"/photos/{photo['id']}").json()
        if data['analysis_status']=='completed':break
        if data['analysis_status']=='failed':raise RuntimeError(data['analysis_error'])
        time.sleep(.25)
    assert data['analysis_status']=='completed'
    version=call('POST',f"/photos/{photo['id']}/versions",json={'name':'재시작 후 유지될 보정본','brightness':1.13,'saturation':.82}).json()
    call('POST',f"/versions/{version['id']}/request-review",json={'confirmed':True})
    call('POST',f"/versions/{version['id']}/approval")
    call('POST',f"/versions/{version['id']}/final")
    rendered=call('GET',f"/versions/{version['id']}/file",params={'download':'true'}).content
    state['rendered_hash']=hashlib.sha256(rendered).hexdigest()
    state['version_id']=version['id'];state_path.write_text(json.dumps(state))
    print('SETUP PASSED: album, original, edited version, approval, final and session saved. Restart API and worker, then run verify.')
else:
    state=json.loads(state_path.read_text());client.cookies.update(state['cookies']);client.headers['X-CSRF-Token']=state['csrf']
    try:
        call('GET','/auth/me')
        album=call('GET',f"/albums/{state['album_id']}").json();assert album['photo_count']==1
        photo=call('GET',f"/photos/{state['photo_id']}").json()
        version=next(v for v in photo['versions'] if v['id']==state['version_id'])
        assert photo['final_version_id']==state['version_id']
        assert version['consensus'] and version['approval_count']==1 and version['target_count']==1
        assert version['brightness']==1.13 and version['saturation']==.82
        original=call('GET',f"/photos/{photo['id']}/download").content
        assert hashlib.sha256(original).hexdigest()==state['hash']
        rendered=call('GET',f"/versions/{version['id']}/file",params={'download':'true'}).content
        assert hashlib.sha256(rendered).hexdigest()==state['rendered_hash']
        print('PERSISTENCE PASSED: session, album, original/rendered bytes, settings, approval and final remain intact.')
    finally:
        call('DELETE',f"/albums/{state['album_id']}")
        state_path.unlink()
        print('Temporary verification album removed.')
client.close()
