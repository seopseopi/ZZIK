"""ZZIK's authenticated, persistent API. All photo mutations lock the photo row."""
from __future__ import annotations

import logging
import secrets
from datetime import timedelta
from pathlib import Path
from typing import Literal
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, File, Form, Query, Request, Response, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import and_, delete, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from .config import settings
from .db import get_db
from .image_service import ImageError, inspect_image, prepare_image, render_cache_key, render_image, similar_groups, thumbnail_image
from .models import *
from .schemas import *
from .services import *
from .storage import get_storage

log = logging.getLogger(__name__)
app = FastAPI(title='ZZIK API', version='1.0.0')
origins = [s.strip() for s in settings.allowed_origins.split(',') if s.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True,
                   allow_methods=['GET','POST','PATCH','PUT','DELETE','OPTIONS'], allow_headers=['Content-Type','X-CSRF-Token'])


@app.middleware('http')
async def request_safety(request: Request, call_next):
    if request.method not in {'GET','HEAD','OPTIONS'} and request.headers.get('origin') and request.headers['origin'] not in origins:
        return JSONResponse({'code':'ORIGIN_NOT_ALLOWED','message':'허용되지 않은 사이트의 요청이에요.'},status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    if request.url.path.startswith('/api'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.exception_handler(APIError)
async def api_error(_, exc):
    result = {'code':exc.code,'message':exc.message}
    if exc.details is not None: result['details'] = exc.details
    return JSONResponse(jsonable_encoder(result), status_code=exc.status)


@app.exception_handler(ImageError)
async def image_error(_, exc):
    return JSONResponse({'code':exc.code,'message':exc.message},status_code=422)


@app.exception_handler(RequestValidationError)
async def validation_error(_, exc):
    return JSONResponse({'code':'INVALID_REQUEST','message':'입력값을 확인해 주세요.','details':jsonable_encoder(exc.errors(),custom_encoder={ValueError:str})},status_code=422)


@app.exception_handler(Exception)
async def unexpected_error(_, exc):
    log.exception('Request failed',exc_info=exc)
    return JSONResponse({'code':'INTERNAL_ERROR','message':'처리하지 못했어요. 잠시 후 다시 시도해 주세요.'},status_code=500)


def auth(request: Request, db: DBSession = Depends(get_db)):
    return current_user(request,db)[0]


def timezone_name(name):
    try: ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError): fail(422,'INVALID_TIMEZONE','올바른 시간대를 선택해 주세요.')
    return name


def login_session(db, user, request, response):
    previous = request.cookies.get(settings.session_cookie)
    if previous:
        db.execute(delete(Session).where(Session.token_hash==digest(previous)))
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(Session(token_hash=digest(token),user_id=user.id,csrf_token=csrf,expires_at=now()+timedelta(days=settings.session_days)))
    db.commit()
    response.set_cookie(settings.session_cookie,token,max_age=settings.session_days*86400,httponly=True,
                        secure=settings.cookie_secure,samesite='lax',path='/')
    return {'user':user_dict(user),'csrf_token':csrf}


@app.get('/health/live')
@app.get('/api/health/live')
def live(): return {'status':'ok'}


@app.get('/health/ready')
@app.get('/api/health/ready')
def ready(db: DBSession = Depends(get_db)):
    try:
        db.execute(text('SELECT 1'))
        db.execute(select(User.id).limit(1))
    except Exception: fail(503,'DATABASE_NOT_READY','데이터베이스를 준비하고 있어요.')
    return {'status':'ready','database':'ok'}


@app.get('/api/config')
def config():
    return {'face_provider':settings.face_analysis_provider,'storage_backend':settings.storage_backend,
            'demo_enabled':settings.demo_enabled,'max_upload_bytes':settings.max_upload_bytes,
            'grouping_available':settings.face_analysis_provider=='rekognition'}


@app.post('/api/auth/register',status_code=201)
def register(body:Register,request:Request,response:Response,db:DBSession=Depends(get_db)):
    user = User(name=body.name,email=body.email,password_hash=hash_password(body.password))
    db.add(user)
    try: db.flush()
    except IntegrityError:
        db.rollback()
        fail(409,'EMAIL_EXISTS','이미 가입한 이메일이에요.')
    return login_session(db,user,request,response)


@app.post('/api/auth/login')
def login(body:Login,request:Request,response:Response,db:DBSession=Depends(get_db)):
    user = db.scalar(select(User).where(User.email==body.email.strip().lower()))
    if not user or not verify_password(body.password,user.password_hash):
        fail(401,'INVALID_CREDENTIALS','이메일 또는 비밀번호를 확인해 주세요.')
    return login_session(db,user,request,response)


@app.get('/api/auth/me')
def me(request:Request,db:DBSession=Depends(get_db)):
    user, session = current_user(request,db)
    return {'user':user_dict(user),'csrf_token':session.csrf_token}


@app.post('/api/auth/logout')
def logout(request:Request,response:Response,db:DBSession=Depends(get_db)):
    _,session=current_user(request,db)
    db.delete(session)
    db.commit()
    response.delete_cookie(settings.session_cookie,path='/',secure=settings.cookie_secure,httponly=True,samesite='lax')
    return {'ok':True}


@app.get('/api/albums')
def albums(user=Depends(auth),db:DBSession=Depends(get_db)):
    rows=db.scalars(select(Album).join(AlbumMember).where(AlbumMember.user_id==user.id).order_by(Album.created_at.desc())).all()
    return {'items':[album_dict(db,a) for a in rows],'total':len(rows),'page':1,'page_size':len(rows)}


@app.post('/api/albums',status_code=201)
def create_album(body:AlbumCreate,user=Depends(auth),db:DBSession=Depends(get_db)):
    a=Album(name=body.name.strip(),description=body.description,timezone=timezone_name(body.timezone),owner_id=user.id,invite_code=secrets.token_urlsafe(12))
    if not a.name: fail(422,'INVALID_NAME','앨범 이름을 입력해 주세요.')
    db.add(a)
    db.flush()
    db.add(AlbumMember(album_id=a.id,user_id=user.id,role='owner'))
    db.commit()
    return album_dict(db,a)


@app.post('/api/albums/join')
def join_album(body:Join,user=Depends(auth),db:DBSession=Depends(get_db)):
    code=body.code.strip().rstrip('/').split('/')[-1]
    a=db.scalar(select(Album).where(Album.invite_code==code).with_for_update())
    if not a: fail(404,'INVALID_INVITE','유효한 초대코드를 입력해 주세요.')
    if not db.get(AlbumMember,(a.id,user.id)):
        db.add(AlbumMember(album_id=a.id,user_id=user.id))
        db.commit()
        notify_after_commit(a.id,user.id,'member_joined',f'{user.name} 님이 앨범에 참여했어요.')
    return album_dict(db,a)


@app.get('/api/albums/{album_id}')
def album_detail(album_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    return album_dict(db,membership(db,album_id,user))


@app.patch('/api/albums/{album_id}')
def album_patch(album_id:str,body:AlbumPatch,user=Depends(auth),db:DBSession=Depends(get_db)):
    a=membership(db,album_id,user,owner=True,exclusive=True)
    for key,value in body.model_dump(exclude_unset=True).items():
        if value is None: continue
        if key=='timezone': value=timezone_name(value)
        if key=='name':
            value=value.strip()
            if not value: fail(422,'INVALID_NAME','앨범 이름을 입력해 주세요.')
        setattr(a,key,value)
    db.commit()
    return album_dict(db,a)


@app.post('/api/albums/{album_id}/invite')
def rotate_invite(album_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    a=membership(db,album_id,user,owner=True,exclusive=True)
    a.invite_code=secrets.token_urlsafe(12)
    db.commit()
    return {'invite_code':a.invite_code}


def queue_all_photo_files(db,p):
    queue_photo_files(db,p)
    for face in db.scalars(select(GroupFace).where(GroupFace.photo_id==p.id)):
        db.add(FileCleanup(key=f'rekognition-face:{p.album_id}:{face.external_face_id}'))
    for v in db.scalars(select(Version).where(Version.photo_id==p.id)):
        for size in (None,1600): db.add(FileCleanup(key=render_cache_key(p.original_hash,v.brightness,v.saturation,size)))


@app.delete('/api/albums/{album_id}')
def delete_album(album_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    a=membership(db,album_id,user,owner=True,exclusive=True)
    for p in db.scalars(select(Photo).where(Photo.album_id==album_id).order_by(Photo.id).with_for_update()): queue_all_photo_files(db,p)
    for person in db.scalars(select(Person).where(Person.album_id==album_id)):
        if person.reference_key: db.add(FileCleanup(key=person.reference_key))
    if settings.face_analysis_provider=='rekognition' or db.scalar(select(FaceGroup.id).where(FaceGroup.album_id==album_id).limit(1)):
        db.add(FileCleanup(key=f'rekognition-collection:{album_id}'))
    db.delete(a)
    db.commit()
    drain_cleanup()
    return {'ok':True}


@app.delete('/api/albums/{album_id}/members/{user_id}')
def remove_member(album_id:str,user_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    a=membership(db,album_id,user,exclusive=True)
    if user.id != user_id: membership(db,album_id,user,owner=True)
    if user_id==a.owner_id: fail(409,'OWNER_CANNOT_LEAVE','앨범 소유자는 앨범을 삭제할 수 있어요.')
    member=db.get(AlbumMember,(album_id,user_id))
    if not member: fail(404,'MEMBER_NOT_FOUND','멤버를 찾을 수 없어요.')
    # Exclusive album access precedes ordered photo locks, shared by worker publication.
    for p in db.scalars(select(Photo).where(Photo.album_id==album_id).order_by(Photo.id).with_for_update()):
        target=db.scalar(select(Version.id).join(ApprovalTarget).where(Version.photo_id==p.id,ApprovalTarget.user_id==user_id).limit(1))
        if target: invalidate_photo_reviews(db,p,'승인 대상 멤버가 앨범을 떠났어요. 새 보정본에서 다시 확인해 주세요.')
    for person in db.scalars(select(Person).where(Person.album_id==album_id,or_(Person.user_id==user_id,Person.proposed_user_id==user_id))):
        if person.user_id==user_id: person.user_id=None
        if person.proposed_user_id==user_id: person.proposed_user_id=None
    db.execute(delete(Notification).where(Notification.album_id==album_id,Notification.user_id==user_id))
    db.delete(member)
    db.commit()
    return {'ok':True}


def find_person(db,person_id,user,owner=False):
    p=db.get(Person,person_id)
    if not p: fail(404,'PERSON_NOT_FOUND','인물을 찾을 수 없어요.')
    membership(db,p.album_id,user,owner)
    return p


def ensure_target_member(db,album_id,user_id):
    if user_id and not db.get(AlbumMember,(album_id,user_id)): fail(422,'INVALID_MEMBER','이 앨범의 멤버만 연결할 수 있어요.')


@app.get('/api/albums/{album_id}/people')
def list_people(album_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    membership(db,album_id,user)
    rows=db.scalars(select(Person).where(Person.album_id==album_id).order_by(Person.created_at)).all()
    return {'items':[person_dict(p) for p in rows],'total':len(rows)}


@app.post('/api/albums/{album_id}/people',status_code=201)
def add_person(album_id:str,name:str=Form(...,min_length=1,max_length=80),file:UploadFile=File(...),user_id:str|None=Form(None),user=Depends(auth),db:DBSession=Depends(get_db)):
    membership(db,album_id,user)
    user_id=user_id or None
    if user_id and user_id!=user.id: membership(db,album_id,user,owner=True)
    ensure_target_member(db,album_id,user_id)
    data=file.file.read(settings.max_upload_bytes+1)
    meta=inspect_image(data,file.content_type)
    from .analysis import validate_reference, AnalysisError
    try: validate_reference(data,original_hash=meta['sha256'])
    except AnalysisError as exc: fail(422,exc.code,exc.message)
    person=Person(id=uid(),album_id=album_id,name=name.strip(),reference_hash=meta['sha256'],user_id=user.id if user_id==user.id else None,proposed_user_id=user_id if user_id!=user.id else None)
    if not person.name: fail(422,'INVALID_NAME','인물 이름을 입력해 주세요.')
    person.reference_key=f'albums/{album_id}/people/{person.id}.jpg'
    storage=get_storage()
    intent=FileCleanup(id=uid(),key=person.reference_key,not_before=now()+timedelta(hours=1))
    db.add(intent)
    db.commit()
    try:
        storage.put(person.reference_key,data,meta['mime'])
        membership(db,album_id,user)
        ensure_target_member(db,album_id,user_id)
        db.delete(intent)
        db.add(person)
        db.commit()
    except Exception:
        db.rollback()
        pending=db.get(FileCleanup,intent.id)
        if pending: pending.not_before=now()
        db.commit()
        drain_cleanup()
        raise
    return person_dict(person)


@app.patch('/api/people/{person_id}')
def patch_person(person_id:str,body:PersonPatch,user=Depends(auth),db:DBSession=Depends(get_db)):
    person=find_person(db,person_id,user)
    member=db.get(AlbumMember,(person.album_id,user.id))
    if member.role!='owner' and person.user_id!=user.id: fail(403,'PERSON_OWNER_REQUIRED','앨범 소유자 또는 연결된 당사자만 수정할 수 있어요.')
    values=body.model_dump(exclude_unset=True)
    if 'name' in values and values['name'] is not None:
        person.name=values['name'].strip()
        if not person.name: fail(422,'INVALID_NAME','인물 이름을 입력해 주세요.')
    if 'user_id' in values:
        target=values['user_id'] or None
        ensure_target_member(db,person.album_id,target)
        if target != person.user_id:
            if target is not None:
                if member.role!='owner': fail(403,'OWNER_REQUIRED','계정 연결 제안은 앨범 소유자만 할 수 있어요.')
                if person.user_id: fail(409,'ALREADY_LINKED','기존 계정 연결을 먼저 해제해 주세요.')
                person.proposed_user_id=target
            else:
                invalidate_person_reviews(db,person.id,'인물의 계정 연결이 변경되었어요.')
                person.user_id=None
                person.proposed_user_id=None
    db.commit()
    return person_dict(person)


@app.post('/api/people/{person_id}/accept-link')
def accept_person_link(person_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    person=find_person(db,person_id,user)
    if person.proposed_user_id != user.id: fail(403,'LINK_NOT_PROPOSED','본인에게 제안된 연결만 확인할 수 있어요.')
    if person.user_id: fail(409,'ALREADY_LINKED','이미 연결된 인물이에요.')
    invalidate_person_reviews(db,person.id,'인물의 계정 연결이 변경되었어요.')
    person.user_id=user.id
    person.proposed_user_id=None
    db.commit()
    return person_dict(person)


@app.delete('/api/people/{person_id}')
def delete_person(person_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    person=find_person(db,person_id,user)
    if person.user_id!=user.id: membership(db,person.album_id,user,owner=True)
    invalidate_person_reviews(db,person.id,'인물 프로필이 삭제되었어요.')
    if person.reference_key: db.add(FileCleanup(key=person.reference_key))
    # Clear embedded identifiers too; preserve detected boxes as unknown faces.
    for p in db.scalars(select(Photo).where(Photo.album_id==person.album_id).order_by(Photo.id).with_for_update()):
        faces=[dict(face,person_id=None,similarity=None) if face.get('person_id')==person.id else face for face in p.faces]
        if faces!=p.faces:
            p.faces=faces
            p.unknown_faces=sum(not f.get('person_id') for f in faces)
    db.delete(person)
    db.commit()
    drain_cleanup()
    return {'ok':True}


def stored_file(key,mime,filename=None):
    storage=get_storage()
    if settings.storage_backend=='s3': return RedirectResponse(storage.signed_url(key,filename=filename),status_code=307)
    try: data=storage.get(key)
    except FileNotFoundError: fail(404,'FILE_NOT_FOUND','파일을 찾을 수 없어요.')
    headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(filename)} if filename else {}
    return Response(data,media_type=mime,headers=headers)


@app.get('/api/people/{person_id}/reference')
def person_reference(person_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    person=find_person(db,person_id,user)
    if not person.reference_key: fail(404,'REFERENCE_NOT_FOUND','기준 사진이 없어요.')
    return stored_file(person.reference_key,inspect_image(get_storage().get(person.reference_key))['mime'])


def upload_photo(db,album_id,user,data,filename,content_type,request_id):
    membership(db,album_id,user)
    existing=db.scalar(select(Photo).where(Photo.album_id==album_id,Photo.uploader_id==user.id,Photo.request_id==request_id))
    meta=inspect_image(data,content_type)
    if existing:
        if existing.original_hash!=meta['sha256']: fail(409,'UPLOAD_ID_REUSED','다른 파일에는 새 업로드 요청 ID를 사용해 주세요.')
        return existing
    p=Photo(id=uid(),album_id=album_id,uploader_id=user.id,request_id=request_id,filename=Path(filename or 'photo.jpg').name[:255],
            original_hash=meta['sha256'],mime=meta['mime'],width=meta['width'],height=meta['height'],byte_size=len(data),
            captured_at=meta.get('captured_at'),capture_timezone=meta.get('capture_timezone'),latitude=meta.get('latitude'),longitude=meta.get('longitude'))
    prefix=f'albums/{album_id}/photos/{p.id}'
    p.original_key=prefix+'/original'
    p.thumbnail_key=prefix+'/thumbnail.jpg'
    p.display_key=prefix+'/display.jpg'
    blobs=[(p.original_key,data,p.mime),(p.thumbnail_key,thumbnail_image(data),'image/jpeg'),(p.display_key,prepare_image(data),'image/jpeg')]
    storage=get_storage()
    # Persist a delayed cleanup intent before any object write. A process crash
    # leaves only expiring objects; success removes intents with the photo commit.
    intents=[FileCleanup(id=uid(),key=key,not_before=now()+timedelta(hours=1)) for key,_,_ in blobs]
    db.add_all(intents)
    db.commit()
    try:
        for key,blob,mime in blobs:
            storage.put(key,blob,mime)
        membership(db,album_id,user)
        db.add(p)
        db.flush()
        for intent in intents: db.delete(intent)
        db.add(AnalysisJob(photo_id=p.id))
        db.commit()
    except Exception as exc:
        db.rollback()
        for intent in intents:
            pending=db.get(FileCleanup,intent.id)
            if pending: pending.not_before=now()
        db.commit()
        drain_cleanup()
        if isinstance(exc,IntegrityError):
            existing=db.scalar(select(Photo).where(Photo.album_id==album_id,Photo.uploader_id==user.id,Photo.request_id==request_id))
            if existing and existing.original_hash==meta['sha256']: return existing
            if existing: fail(409,'UPLOAD_ID_REUSED','다른 파일에는 새 업로드 요청 ID를 사용해 주세요.')
        raise
    return p


@app.post('/api/albums/{album_id}/photos',status_code=201)
def upload(album_id:str,file:UploadFile=File(...),request_id:str=Form(...,min_length=8,max_length=100),user=Depends(auth),db:DBSession=Depends(get_db)):
    membership(db,album_id,user)
    p=upload_photo(db,album_id,user,file.file.read(settings.max_upload_bytes+1),file.filename,file.content_type,request_id)
    return photo_dict(db,p)


@app.get('/api/albums/{album_id}/photos')
def list_photos(album_id:str,page:int=Query(1,ge=1),page_size:int=Query(40,ge=1,le=100),
                filter:Literal['all','mine','solo','group','no_faces','review','final']='all',people:str='',
                match:Literal['all','any']='all',tag:str='',q:str='',mine:bool=False,sort:Literal['newest','oldest','captured']='newest',date:str='',
                trashed:bool=False,user=Depends(auth),db:DBSession=Depends(get_db)):
    membership(db,album_id,user)
    query=select(Photo).where(Photo.album_id==album_id,Photo.trashed_at.is_not(None) if trashed else Photo.trashed_at.is_(None))
    included=select(PhotoPerson.photo_id).where(PhotoPerson.excluded==False)
    if filter=='mine' or mine:
        ids=select(Person.id).where(Person.album_id==album_id,Person.user_id==user.id)
        query=query.where(Photo.id.in_(included.where(PhotoPerson.person_id.in_(ids))))
    if filter=='solo': query=query.where(Photo.analysis_status=='completed',Photo.face_count==1)
    elif filter=='group': query=query.where(Photo.analysis_status=='completed',Photo.face_count>=2)
    elif filter=='no_faces': query=query.where(Photo.analysis_status=='completed',Photo.face_count==0)
    elif filter=='review': query=query.where(or_(Photo.analysis_status=='failed',and_(Photo.analysis_status=='completed',Photo.unknown_faces>0)))
    elif filter=='final': query=query.where(Photo.final_version_id.is_not(None))
    person_ids=sorted(set(pid for pid in people.split(',') if pid))
    if len(person_ids)>100: fail(422,'TOO_MANY_PEOPLE','인물 필터를 줄여 주세요.')
    if person_ids:
        valid=set(db.scalars(select(Person.id).where(Person.album_id==album_id,Person.id.in_(person_ids))))
        if valid!=set(person_ids): fail(422,'INVALID_PERSON','이 앨범의 인물만 검색할 수 있어요.')
        if match=='all':
            for pid in person_ids: query=query.where(Photo.id.in_(included.where(PhotoPerson.person_id==pid)))
        else: query=query.where(Photo.id.in_(included.where(PhotoPerson.person_id.in_(person_ids))))
    from sqlalchemy.dialects.postgresql import JSONB
    tag_text=Photo.tags.cast(JSONB).cast(Text) if db.bind.dialect.name=='postgresql' else Photo.tags.cast(Text)
    if tag:
        if db.bind.dialect.name=='postgresql': query=query.where(Photo.tags.cast(JSONB).contains([tag]))
        else: query=query.where(tag_text.ilike('%'+tag.replace('%','\\%').replace('_','\\_')+'%'))
    if q:
        term='%'+q.replace('%','\\%').replace('_','\\_')+'%'
        matching_people=select(Person.id).where(Person.album_id==album_id,Person.name.ilike(term))
        query=query.where(or_(Photo.filename.ilike(term),Photo.note.ilike(term),Photo.location_name.ilike(term),tag_text.ilike(term),Photo.id.in_(included.where(PhotoPerson.person_id.in_(matching_people)))))
    if date:
        from datetime import date as Date
        try: Date.fromisoformat(date)
        except ValueError: fail(422,'INVALID_DATE','날짜 형식을 확인해 주세요.')
        query=query.where(Photo.captured_at.startswith(date))
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    order=Photo.created_at.asc() if sort=='oldest' else Photo.captured_at.desc().nulls_last() if sort=='captured' else Photo.created_at.desc()
    if trashed: order=Photo.trashed_at.desc()
    rows=db.scalars(query.order_by(order,Photo.id).offset((page-1)*page_size).limit(page_size)).all()
    stats={status:0 for status in ['pending','processing','completed','failed']}
    stats.update(dict(db.execute(select(Photo.analysis_status,func.count()).where(Photo.album_id==album_id,Photo.trashed_at.is_(None)).group_by(Photo.analysis_status)).all()))
    return {'items':[photo_dict(db,p) for p in rows],'total':total,'page':page,'page_size':page_size,'stats':stats}


@app.get('/api/photos/{photo_id}')
def photo_detail(photo_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    return photo_dict(db,get_photo(db,photo_id,user),detail=True)


@app.patch('/api/photos/{photo_id}')
def patch_photo(photo_id:str,body:PhotoPatch,user=Depends(auth),db:DBSession=Depends(get_db)):
    p=get_photo(db,photo_id,user,lock=True)
    for key,value in body.model_dump(exclude_unset=True).items():
        if value is not None: setattr(p,key,value)
    db.commit()
    return photo_dict(db,p,detail=True)


@app.delete('/api/photos/{photo_id}')
def delete_photo(photo_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    p=get_photo(db,photo_id,user,lock=True)
    if p.uploader_id!=user.id: membership(db,p.album_id,user,owner=True)
    queue_all_photo_files(db,p)
    db.delete(p)
    db.commit()
    drain_cleanup()
    return {'ok':True}


@app.post('/api/photos/{photo_id}/trash')
def trash_photo(photo_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    p=get_photo(db,photo_id,user,lock=True,include_trashed=True)
    if p.uploader_id!=user.id: membership(db,p.album_id,user,owner=True)
    if p.trashed_at is None: p.trashed_at=now()
    db.commit()
    return photo_dict(db,p)


@app.post('/api/photos/{photo_id}/restore')
def restore_photo(photo_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    p=get_photo(db,photo_id,user,lock=True,include_trashed=True)
    if p.uploader_id!=user.id: membership(db,p.album_id,user,owner=True)
    p.trashed_at=None
    db.commit()
    return photo_dict(db,p)


@app.put('/api/photos/{photo_id}/people')
def set_people(photo_id:str,body:PeopleSet,user=Depends(auth),db:DBSession=Depends(get_db)):
    p=get_photo(db,photo_id,user,lock=True)
    wanted=set(body.person_ids)
    valid=set(db.scalars(select(Person.id).where(Person.album_id==p.album_id,Person.id.in_(wanted))))
    if valid!=wanted: fail(422,'INVALID_PERSON','이 앨범의 인물만 연결할 수 있어요.')
    existing={row.person_id:row for row in db.scalars(select(PhotoPerson).where(PhotoPerson.photo_id==p.id))}
    before={pid for pid,row in existing.items() if not row.excluded}
    for pid,row in existing.items():
        row.excluded=pid not in wanted
        row.source='manual'
    for pid in wanted-set(existing): db.add(PhotoPerson(photo_id=p.id,person_id=pid,source='manual',excluded=False))
    if wanted!=before: invalidate_photo_reviews(db,p,'등장 인물이 변경되었어요. 새 보정본에서 승인 대상을 다시 확인해 주세요.')
    db.commit()
    return photo_dict(db,p,detail=True)


def queue_failed_analysis(db, photo):
    """Caller holds album and photo locks; never steal a live worker lease."""
    if photo.analysis_status!='failed': return False
    job=db.scalar(select(AnalysisJob).where(AnalysisJob.photo_id==photo.id).with_for_update()
                  .execution_options(populate_existing=True))
    if job and job.status in {'pending','processing'}: return False
    if not job:
        db.add(AnalysisJob(photo_id=photo.id))
    else:
        job.status='pending'
        job.attempts=0
        job.available_at=now()
        job.locked_at=None
        job.locked_by=None
        job.error=None
        job.finished_at=None
    photo.analysis_status='pending'
    photo.analysis_error=None
    return True


@app.post('/api/photos/{photo_id}/reanalyze')
def reanalyze(photo_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    p=get_photo(db,photo_id,user,lock=True)
    if p.analysis_status!='failed': fail(409,'ANALYSIS_NOT_FAILED','분석에 실패한 사진만 다시 분석할 수 있어요.')
    if not queue_failed_analysis(db,p): fail(409,'ANALYSIS_ALREADY_QUEUED','이미 분석을 다시 진행하고 있어요.')
    db.commit()
    return photo_dict(db,p)


@app.get('/api/albums/{album_id}/analysis-status')
def album_analysis_status(album_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    membership(db,album_id,user)
    stats={status:0 for status in ['pending','processing','completed','failed']}
    stats.update(dict(db.execute(select(Photo.analysis_status,func.count()).where(Photo.album_id==album_id,Photo.trashed_at.is_(None))
                                 .group_by(Photo.analysis_status)).all()))
    # These are accumulated run totals, not unique photo counts or wall-clock duration.
    recorded_runs,calls,elapsed_ms=db.execute(select(func.count(AnalysisRun.id),func.coalesce(func.sum(AnalysisRun.calls),0),
        func.coalesce(func.sum(AnalysisRun.elapsed_ms),0)).join(Photo,Photo.id==AnalysisRun.photo_id)
        .where(Photo.album_id==album_id,Photo.trashed_at.is_(None))).one()
    failures=db.execute(select(Photo.id,Photo.filename,Photo.analysis_error).where(Photo.album_id==album_id,Photo.trashed_at.is_(None),Photo.analysis_status=='failed')
                        .order_by(Photo.created_at.desc(),Photo.id).limit(20)).all()
    oldest_pending_at=db.scalar(select(func.min(AnalysisJob.available_at)).join(Photo,Photo.id==AnalysisJob.photo_id)
                                .where(Photo.album_id==album_id,Photo.trashed_at.is_(None),AnalysisJob.status=='pending'))
    return {'provider':settings.face_analysis_provider,'mode':'sample' if settings.face_analysis_provider=='fixture' else 'live',
            'stats':stats,'total':sum(stats.values()),'recorded_runs':recorded_runs,'calls':calls,'elapsed_ms':elapsed_ms,
            'failures':[{'photo_id':photo_id,'filename':filename,'error':error} for photo_id,filename,error in failures],
            'oldest_pending_at':oldest_pending_at}


@app.post('/api/albums/{album_id}/reanalyze-failed')
def reanalyze_album_failures(album_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    membership(db,album_id,user)
    photos=db.scalars(select(Photo).where(Photo.album_id==album_id,Photo.trashed_at.is_(None),Photo.analysis_status=='failed')
                      .order_by(Photo.id).with_for_update().execution_options(populate_existing=True)).all()
    queued=sum(queue_failed_analysis(db,photo) for photo in photos)
    db.commit()
    return {'queued':queued}


@app.get('/api/photos/{photo_id}/file')
def photo_file(photo_id:str,kind:Literal['original','thumbnail','display']='display',download:bool=False,user=Depends(auth),db:DBSession=Depends(get_db)):
    p=get_photo(db,photo_id,user,include_trashed=True)
    key=getattr(p,kind+'_key')
    return stored_file(key,p.mime if kind=='original' else 'image/jpeg',p.filename if download else None)


@app.get('/api/photos/{photo_id}/download')
def photo_download(photo_id:str,version_id:str|None=None,user=Depends(auth),db:DBSession=Depends(get_db)):
    p=get_photo(db,photo_id,user)
    if version_id:
        v,pv=get_version(db,version_id,user)
        if pv.id!=p.id: fail(422,'VERSION_PHOTO_MISMATCH','이 사진의 보정본을 선택해 주세요.')
        return version_file_response(p,v,download=True)
    return stored_file(p.original_key,p.mime,p.filename)


@app.get('/api/photos/{photo_id}/versions')
def versions(photo_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    p=get_photo(db,photo_id,user)
    rows=db.scalars(select(Version).where(Version.photo_id==p.id).order_by(Version.number.desc())).all()
    return {'items':[version_dict(db,v,p) for v in rows],'total':len(rows)}


@app.post('/api/photos/{photo_id}/versions',status_code=201)
def create_version(photo_id:str,body:VersionCreate,user=Depends(auth),db:DBSession=Depends(get_db)):
    p=get_photo(db,photo_id,user,lock=True)
    if body.parent_id:
        parent=db.get(Version,body.parent_id)
        if not parent or parent.photo_id!=p.id: fail(422,'INVALID_PARENT','같은 사진의 이전 보정본을 선택해 주세요.')
    number=(db.scalar(select(func.max(Version.number)).where(Version.photo_id==p.id)) or 0)+1
    v=Version(photo_id=p.id,author_id=user.id,number=number,**body.model_dump())
    v.name=v.name.strip()
    if not v.name: fail(422,'INVALID_NAME','보정본 이름을 입력해 주세요.')
    db.add(v)
    db.commit()
    notify_after_commit(p.album_id,user.id,'new_version',f'{user.name} 님이 새 보정본을 저장했어요.',p.id,v.id)
    return version_dict(db,v,p)


@app.post('/api/photos/{photo_id}/preview')
def preview(photo_id:str,body:RenderSettings,user=Depends(auth),db:DBSession=Depends(get_db)):
    p=get_photo(db,photo_id,user)
    data=render_image(get_storage().get(p.original_key),body.brightness,body.saturation,max_size=1600)
    return Response(data,media_type='image/jpeg')


def version_file_response(photo,version,download=False,preview=False):
    size=1600 if preview and not download else None
    key=render_cache_key(photo.original_hash,version.brightness,version.saturation,size)
    storage=get_storage()
    if not storage.exists(key): storage.put(key,render_image(storage.get(photo.original_key),version.brightness,version.saturation,max_size=size),'image/jpeg')
    filename=f'{Path(photo.filename).stem}-v{version.number}.jpg' if download else None
    return stored_file(key,'image/jpeg',filename)


@app.get('/api/versions/{version_id}/file')
def version_file(version_id:str,download:bool=False,preview:bool=False,user=Depends(auth),db:DBSession=Depends(get_db)):
    v,p=get_version(db,version_id,user)
    return version_file_response(p,v,download,preview)


@app.post('/api/versions/{version_id}/request-review')
def request_review(version_id:str,body:ReviewRequest,user=Depends(auth),db:DBSession=Depends(get_db)):
    v,p=get_version(db,version_id,user,lock=True)
    if not body.confirmed: fail(422,'TARGETS_NOT_CONFIRMED','등장 인물과 승인 대상을 먼저 확인해 주세요.')
    if v.needs_review: fail(409,'NEW_VERSION_REQUIRED','등장 인물이 바뀌었어요. 새 보정본을 만들어 다시 확인을 요청해 주세요.')
    if v.review_requested: return version_dict(db,v,p)
    people=effective_people(db,p.id)
    if people:
        if any(not person.user_id for person in people): fail(409,'UNLINKED_PEOPLE','등장 인물 모두가 앨범 멤버 계정과 연결되어야 해요.')
        targets={person.user_id for person in people}
    elif p.analysis_status=='completed' and p.face_count==0:
        targets={p.uploader_id}
    else: fail(409,'NO_REVIEW_TARGETS','등장 인물과 연결 계정을 확인해 주세요. 얼굴 없는 사진은 분석 완료 후 업로더가 확인해요.')
    for target in targets: ensure_target_member(db,p.album_id,target)
    v.target_person_ids=sorted(person.id for person in people)
    v.review_requested=True
    for target in targets: db.add(ApprovalTarget(version_id=v.id,user_id=target))
    db.commit()
    notify_after_commit(p.album_id,user.id,'review_requested',f'{user.name} 님이 보정본 확인을 요청했어요.',p.id,v.id,target_ids=targets)
    return version_dict(db,v,p)


@app.post('/api/versions/{version_id}/approval')
def approve(version_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    v,p=get_version(db,version_id,user,lock=True)
    targets,_,_=approval_state(db,v)
    if not v.review_requested or v.needs_review: fail(409,'REVIEW_NOT_ACTIVE','승인 요청을 확인하거나 새 보정본에서 다시 승인해 주세요.')
    if user.id not in targets: fail(403,'NOT_APPROVAL_TARGET','이 보정본의 승인 대상만 승인할 수 있어요.')
    if not db.get(Approval,(v.id,user.id)): db.add(Approval(version_id=v.id,user_id=user.id))
    db.commit()
    return version_dict(db,v,p)


@app.delete('/api/versions/{version_id}/approval')
def revoke_approval(version_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    v,p=get_version(db,version_id,user,lock=True)
    approval=db.get(Approval,(v.id,user.id))
    if approval: db.delete(approval)
    db.flush()
    if p.final_version_id==v.id and not approval_state(db,v)[2]: p.final_version_id=None
    db.commit()
    return version_dict(db,v,p)


@app.post('/api/versions/{version_id}/final')
def set_final(version_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    v,p=get_version(db,version_id,user,lock=True)
    if not approval_state(db,v)[2]: fail(409,'CONSENSUS_REQUIRED','모든 승인 대상의 확인을 받은 보정본만 최종본으로 선택할 수 있어요.')
    p.final_version_id=v.id
    db.commit()
    notify_after_commit(p.album_id,user.id,'final_selected',f'{user.name} 님이 최종본을 선택했어요.',p.id,v.id)
    return version_dict(db,v,p)


@app.post('/api/versions/{version_id}/comments',status_code=201)
def add_comment(version_id:str,body:CommentCreate,user=Depends(auth),db:DBSession=Depends(get_db)):
    v,p=get_version(db,version_id,user)
    text_body=body.body.strip()
    if not text_body: fail(422,'EMPTY_COMMENT','댓글을 입력해 주세요.')
    db.add(Comment(version_id=v.id,author_id=user.id,body=text_body,kind=body.kind))
    db.commit()
    notify_after_commit(p.album_id,user.id,body.kind,f'{user.name} 님이 '+('수정을 요청했어요.' if body.kind=='change_request' else '댓글을 남겼어요.'),p.id,v.id)
    return version_dict(db,v,p)


@app.get('/api/albums/{album_id}/board')
def board(album_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    membership(db,album_id,user)
    result={status:[] for status in ['selection','editing','review','final']}
    for p in db.scalars(select(Photo).where(Photo.album_id==album_id,Photo.trashed_at.is_(None)).order_by(Photo.created_at.desc())):
        item=photo_dict(db,p)
        result[item['board_status']].append(item)
    return result


@app.get('/api/albums/{album_id}/recommendations')
def recommendations(album_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    membership(db,album_id,user)
    photos=db.scalars(select(Photo).where(Photo.album_id==album_id,Photo.trashed_at.is_(None)).order_by(Photo.captured_at,Photo.id)).all()
    rows=[dict(photo_dict(db,p),sha256=p.original_hash,faces=p.faces) for p in photos]
    groups=similar_groups(rows)
    for group in groups:
        for photo in group['photos']: photo.pop('sha256',None)
    return {'groups':groups,'method':'동일한 전처리의 유사 사진 안에서 흔들림·노출·눈 감음을 비교해요. 촬영 시간이 없으면 같은 원본만 묶어요.'}


@app.get('/api/notifications')
def notifications(user=Depends(auth),db:DBSession=Depends(get_db)):
    rows=db.scalars(select(Notification).join(AlbumMember,and_(AlbumMember.album_id==Notification.album_id,AlbumMember.user_id==user.id)).where(Notification.user_id==user.id,or_(Notification.photo_id.is_(None),Notification.photo_id.in_(select(Photo.id).where(Photo.trashed_at.is_(None))))).order_by(Notification.created_at.desc()).limit(200)).all()
    items=[{key:getattr(n,key) for key in ['id','album_id','photo_id','version_id','kind','message','read','created_at']} for n in rows]
    return {'items':items,'total':len(items)}


@app.post('/api/notifications/{notification_id}/read')
def read_notification(notification_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    n=db.get(Notification,notification_id)
    if not n or n.user_id!=user.id: fail(404,'NOTIFICATION_NOT_FOUND','알림을 찾을 수 없어요.')
    membership(db,n.album_id,user)
    n.read=True
    db.commit()
    return {'ok':True}


def group_dict(db,g):
    faces=db.scalars(select(GroupFace).join(Photo,Photo.id==GroupFace.photo_id).where(GroupFace.group_id==g.id,Photo.trashed_at.is_(None)).order_by(GroupFace.id)).all()
    return {'id':g.id,'name':g.name,'person_id':g.person_id,'album_id':g.album_id,'face_count':len(faces),
            'faces':[{'id':f.id,'photo_id':f.photo_id,'box':f.box,'similarity':f.similarity,'thumbnail_url':f'/api/photos/{f.photo_id}/file?kind=thumbnail'} for f in faces]}


def get_group(db,group_id,user):
    g=db.get(FaceGroup,group_id)
    if not g: fail(404,'GROUP_NOT_FOUND','인물 그룹을 찾을 수 없어요.')
    membership(db,g.album_id,user)
    return g


@app.get('/api/albums/{album_id}/face-groups')
def face_groups(album_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    membership(db,album_id,user)
    groups=db.scalars(select(FaceGroup).where(FaceGroup.album_id==album_id).order_by(FaceGroup.created_at)).all()
    return {'items':[group_dict(db,g) for g in groups],'total':len(groups),'available':settings.face_analysis_provider=='rekognition',
            'mode':settings.face_analysis_provider,'message':None if settings.face_analysis_provider=='rekognition' else '등록 없는 자동 인물 그룹은 AWS Rekognition 연결이 필요해요. 샘플 모드는 기준 인물 매칭만 제공해요.'}


@app.post('/api/albums/{album_id}/face-groups/analyze')
def analyze_face_groups(album_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    membership(db,album_id,user)
    if settings.face_analysis_provider!='rekognition': fail(409,'GROUPING_UNAVAILABLE','자동 인물 그룹은 실제 Rekognition 연결 후 사용할 수 있어요.')
    grouped=select(GroupFace.photo_id)
    photos=db.scalars(select(Photo).where(Photo.album_id==album_id,Photo.trashed_at.is_(None),Photo.id.not_in(grouped)).order_by(Photo.id).with_for_update()).all()
    for p in photos:
        p.analysis_metadata=dict(p.analysis_metadata,grouping_requested=True)
        job=db.scalar(select(AnalysisJob).where(AnalysisJob.photo_id==p.id).with_for_update())
        if not job:
            db.add(AnalysisJob(photo_id=p.id))
            p.analysis_status='pending'
        elif job.status not in {'pending','processing'}:
            job.status='pending'
            job.attempts=0
            job.available_at=now()
            job.error=None
            job.locked_at=None
            job.locked_by=None
            job.finished_at=None
            p.analysis_status='pending'
    db.commit()
    return {'queued':len(photos)}


def apply_group_person(db,g,person_id):
    from .grouping import sync_group_people
    photo_ids=set(db.scalars(select(GroupFace.photo_id).where(GroupFace.group_id==g.id)))
    g.person_id=person_id
    sync_group_people(db,photo_ids,force_review=True)


@app.patch('/api/face-groups/{group_id}')
def patch_group(group_id:str,body:GroupPatch,user=Depends(auth),db:DBSession=Depends(get_db)):
    g=get_group(db,group_id,user)
    if body.name is not None:
        g.name=body.name.strip()
        if not g.name: fail(422,'INVALID_NAME','그룹 이름을 입력해 주세요.')
    if 'person_id' in body.model_fields_set:
        if body.person_id:
            p=db.get(Person,body.person_id)
            if not p or p.album_id!=g.album_id: fail(422,'INVALID_PERSON','같은 앨범의 인물을 선택해 주세요.')
        apply_group_person(db,g,body.person_id)
    db.commit()
    return group_dict(db,g)


@app.post('/api/face-groups/merge')
def merge_groups(body:GroupMerge,user=Depends(auth),db:DBSession=Depends(get_db)):
    ids=sorted(set(body.group_ids))
    if len(ids)<2: fail(422,'TWO_GROUPS_REQUIRED','그룹을 2개 이상 선택해 주세요.')
    groups=[get_group(db,gid,user) for gid in ids]
    if len({g.album_id for g in groups})!=1: fail(422,'GROUP_ALBUM_MISMATCH','같은 앨범의 그룹만 합칠 수 있어요.')
    if len({g.person_id for g in groups if g.person_id})>1: fail(409,'GROUP_PERSON_CONFLICT','서로 다른 인물에 연결된 그룹은 연결을 해제한 뒤 합쳐 주세요.')
    target=groups[0]
    person_id=next((g.person_id for g in groups if g.person_id),None)
    for g in groups[1:]:
        for face in db.scalars(select(GroupFace).where(GroupFace.group_id==g.id)): face.group_id=target.id
        db.flush()
        db.delete(g)
    db.flush()
    apply_group_person(db,target,person_id)
    db.commit()
    return group_dict(db,target)


@app.post('/api/face-groups/{group_id}/split',status_code=201)
def split_group(group_id:str,body:GroupSplit,user=Depends(auth),db:DBSession=Depends(get_db)):
    g=get_group(db,group_id,user)
    faces=db.scalars(select(GroupFace).join(Photo,Photo.id==GroupFace.photo_id).where(GroupFace.group_id==g.id,Photo.trashed_at.is_(None))).all()
    selected=set(body.face_ids)
    if not selected.issubset({f.id for f in faces}) or len(selected)==len(faces): fail(422,'INVALID_SPLIT','기존 그룹에 남길 얼굴과 분리할 얼굴을 나누어 선택해 주세요.')
    new=FaceGroup(album_id=g.album_id,name='새 인물 그룹')
    db.add(new)
    db.flush()
    for face in faces:
        if face.id in selected: face.group_id=new.id
    from .grouping import sync_group_people
    sync_group_people(db,{face.photo_id for face in faces},force_review=True)
    db.commit()
    return group_dict(db,new)

@app.get('/api/albums/{album_id}/download')
def album_download(album_id:str,photo_ids:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    """A spooled ZIP keeps a bounded batch of originals out of browser memory."""
    import tempfile
    import zipfile
    from fastapi.responses import StreamingResponse
    membership(db,album_id,user)
    ids=list(dict.fromkeys(pid for pid in photo_ids.split(',') if pid))
    if not 1<=len(ids)<=100: fail(422,'INVALID_DOWNLOAD_SELECTION','1–100장의 사진을 선택해 주세요.')
    photos=db.scalars(select(Photo).where(Photo.album_id==album_id,Photo.trashed_at.is_(None),Photo.id.in_(ids))).all()
    if len(photos)!=len(ids): fail(404,'PHOTO_NOT_FOUND','선택한 사진 중 접근할 수 없는 사진이 있어요.')
    if sum(p.byte_size for p in photos)>512*1024*1024: fail(413,'DOWNLOAD_TOO_LARGE','한 번에 512MB까지 내려받을 수 있어요. 사진을 나누어 선택해 주세요.')
    output=tempfile.SpooledTemporaryFile(max_size=8*1024*1024)
    try:
        with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_STORED) as archive:
            for index,p in enumerate(photos,1):
                archive.writestr(f'{index:03d}-{Path(p.filename).name}',get_storage().get(p.original_key))
        output.seek(0)
    except Exception:
        output.close()
        raise
    def chunks():
        try:
            while chunk:=output.read(128*1024): yield chunk
        finally: output.close()
    return StreamingResponse(chunks(),media_type='application/zip',headers={'Content-Disposition':"attachment; filename*=UTF-8''zzik-originals.zip"})
