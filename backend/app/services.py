import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from fastapi import Request
from sqlalchemy import select, func
from .config import settings
from .db import SessionLocal
from .models import *

_hasher = PasswordHasher()
def hash_password(password): return _hasher.hash(password)
def verify_password(password, hashed):
    try: return _hasher.verify(hashed, password)
    except (VerifyMismatchError, InvalidHashError): return False

def digest(value): return hashlib.sha256(value.encode()).hexdigest()
class APIError(Exception):
    def __init__(self, status, code, message, details=None):
        self.status, self.code, self.message, self.details = status, code, message, details

def fail(status,code,message,details=None): raise APIError(status,code,message,details)
def utc(value): return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value

def current_user(request, db, csrf=True):
    token = request.cookies.get(settings.session_cookie)
    session = db.get(Session, digest(token)) if token else None
    if not session or utc(session.expires_at) < now(): fail(401,'AUTH_REQUIRED','로그인이 필요해요.')
    if csrf and request.method not in {'GET','HEAD','OPTIONS'}:
        supplied = request.headers.get('X-CSRF-Token', '')
        if not secrets.compare_digest(session.csrf_token, supplied): fail(403,'CSRF_INVALID','요청을 확인할 수 없어요. 새로고침 후 다시 시도해 주세요.')
    return db.get(User,session.user_id), session

def lock_album(db, album_id, exclusive=False):
    """Album → photo → job is the shared API/worker lock order.

    A key-share lock lets ordinary album activity proceed concurrently while
    member removal and album deletion acquire an exclusive lock before changing
    access. Always query fresh after upload staging commits released old locks.
    """
    query=select(Album).where(Album.id==album_id)
    query=query.with_for_update() if exclusive else query.with_for_update(read=True,key_share=True)
    return db.scalar(query.execution_options(populate_existing=True))


def membership(db, album_id, user, owner=False, exclusive=False):
    album=lock_album(db,album_id,exclusive=exclusive)
    member=db.scalar(select(AlbumMember).where(AlbumMember.album_id==album_id,AlbumMember.user_id==user.id)
                     .execution_options(populate_existing=True)) if album else None
    if not album or not member: fail(404,'ALBUM_NOT_FOUND','앨범을 찾을 수 없거나 접근 권한이 없어요.')
    if owner and (member.role!='owner' or album.owner_id!=user.id): fail(403,'OWNER_REQUIRED','앨범 소유자만 할 수 있어요.')
    return album


def get_photo(db, photo_id, user, lock=False, include_trashed=False):
    album_id=db.scalar(select(Photo.album_id).where(Photo.id==photo_id))
    if not album_id: fail(404,'PHOTO_NOT_FOUND','사진을 찾을 수 없어요.')
    membership(db,album_id,user)
    query=select(Photo).where(Photo.id==photo_id)
    if lock: query=query.with_for_update()
    photo=db.scalar(query.execution_options(populate_existing=True))
    if not photo: fail(404,'PHOTO_NOT_FOUND','사진을 찾을 수 없어요.')
    if photo.trashed_at and not include_trashed:
        fail(409,'PHOTO_TRASHED','휴지통에 있는 사진이에요. 복원한 뒤 다시 사용할 수 있어요.')
    return photo

def get_version(db, version_id, user, lock=False):
    v=db.get(Version,version_id)
    if not v: fail(404,'VERSION_NOT_FOUND','보정본을 찾을 수 없어요.')
    p=get_photo(db,v.photo_id,user,lock)
    if lock: db.refresh(v)
    return v,p

def effective_people(db, photo_id):
    return list(db.scalars(select(Person).join(PhotoPerson, PhotoPerson.person_id==Person.id).where(PhotoPerson.photo_id==photo_id,PhotoPerson.excluded==False)).all())

def invalidate_photo_reviews(db, photo, reason):
    for v in db.scalars(select(Version).where(Version.photo_id==photo.id,Version.review_requested==True)):
        v.needs_review=True
        v.review_reason=reason
    photo.final_version_id=None

def invalidate_person_reviews(db, person_id, reason):
    ids=list(db.scalars(select(PhotoPerson.photo_id).where(PhotoPerson.person_id==person_id,PhotoPerson.excluded==False)))
    for p in db.scalars(select(Photo).where(Photo.id.in_(ids)).order_by(Photo.id).with_for_update()):
        invalidate_photo_reviews(db,p,reason)

def user_dict(u): return {'id':u.id,'name':u.name,'email':u.email}
def person_dict(p):
    return {'id':p.id,'name':p.name,'user_id':p.user_id,'proposed_user_id':p.proposed_user_id,'reference_url':f'/api/people/{p.id}/reference' if p.reference_key else None,'link_status':'linked' if p.user_id else 'pending' if p.proposed_user_id else 'unlinked'}

def approval_state(db,v):
    targets=set(db.scalars(select(ApprovalTarget.user_id).where(ApprovalTarget.version_id==v.id)))
    approved=set(db.scalars(select(Approval.user_id).where(Approval.version_id==v.id))) & targets
    consensus=bool(v.review_requested and not v.needs_review and targets and approved==targets)
    return targets,approved,consensus

def version_dict(db,v,photo=None):
    p=photo or db.get(Photo,v.photo_id)
    targets,approved,consensus=approval_state(db,v)
    author=db.get(User,v.author_id)
    target_users=db.scalars(select(User).where(User.id.in_(targets)).order_by(User.name)).all()
    comments=[]
    for c in db.scalars(select(Comment).where(Comment.version_id==v.id).order_by(Comment.created_at)):
        u=db.get(User,c.author_id)
        comments.append({'id':c.id,'author':{'id':u.id,'name':u.name},'body':c.body,'kind':c.kind,'created_at':c.created_at})
    return {'id':v.id,'photo_id':v.photo_id,'number':v.number,'name':v.name,'parent_id':v.parent_id,'author':{'id':author.id,'name':author.name},'created_at':v.created_at,'brightness':v.brightness,'saturation':v.saturation,'renderer_version':v.renderer_version,'preview_url':f'/api/versions/{v.id}/file?preview=true','review_requested':v.review_requested,'needs_review':v.needs_review,'review_reason':v.review_reason,'targets':[{'user_id':u.id,'name':u.name,'approved':u.id in approved} for u in target_users],'approval_count':len(approved),'target_count':len(targets),'consensus':consensus,'is_final':p.final_version_id==v.id,'comments':comments}

def board_status(db,p):
    if p.final_version_id: return 'final'
    if db.scalar(select(Version.id).where(Version.photo_id==p.id,Version.review_requested==True,Version.needs_review==False).limit(1)): return 'review'
    if db.scalar(select(Version.id).where(Version.photo_id==p.id).limit(1)): return 'editing'
    return 'selection'

def photo_dict(db,p,detail=False):
    links=db.execute(select(Person,PhotoPerson.source).join(PhotoPerson,PhotoPerson.person_id==Person.id).where(PhotoPerson.photo_id==p.id,PhotoPerson.excluded==False)).all()
    result={'id':p.id,'album_id':p.album_id,'uploader_id':p.uploader_id,'filename':p.filename,'thumbnail_url':f'/api/photos/{p.id}/file?kind=thumbnail','display_url':f'/api/photos/{p.id}/file?kind=display','original_url':f'/api/photos/{p.id}/file?kind=original','width':p.width,'height':p.height,'created_at':p.created_at,'captured_at':p.captured_at,'capture_timezone':p.capture_timezone,'latitude':p.latitude,'longitude':p.longitude,'location_name':p.location_name,'analysis_status':p.analysis_status,'analysis_error':p.analysis_error,'analysis_provider':p.analysis_provider,'analysis_mode':p.analysis_mode,'analysis_metadata':p.analysis_metadata,'face_count':p.face_count,'unknown_faces':p.unknown_faces,'people':[dict(person_dict(person),source=source) for person,source in links],'tags':p.tags,'purpose':p.purpose,'selected':p.selected,'note':p.note,'final_version_id':p.final_version_id,'board_status':board_status(db,p),'quality':p.quality}
    result['trashed_at'] = utc(p.trashed_at)
    if detail:
        result['faces']=p.faces
        result['versions']=[version_dict(db,v,p) for v in db.scalars(select(Version).where(Version.photo_id==p.id).order_by(Version.number.desc()))]
    return result

def album_dict(db,a):
    members=db.execute(select(User,AlbumMember.role).join(AlbumMember,AlbumMember.user_id==User.id).where(AlbumMember.album_id==a.id).order_by(AlbumMember.joined_at)).all()
    cover=db.scalar(select(Photo.id).where(Photo.album_id==a.id,Photo.trashed_at.is_(None)).order_by(Photo.face_count.desc(),Photo.created_at).limit(1))
    count=db.scalar(select(func.count()).select_from(Photo).where(Photo.album_id==a.id,Photo.trashed_at.is_(None)))
    return {'id':a.id,'name':a.name,'description':a.description,'timezone':a.timezone,'owner_id':a.owner_id,'invite_code':a.invite_code,'photo_count':count,'member_count':len(members),'cover_url':f'/api/photos/{cover}/file?kind=display' if cover else None,'created_at':a.created_at,'members':[dict(user_dict(u),role=role) for u,role in members],'people':[person_dict(p) for p in db.scalars(select(Person).where(Person.album_id==a.id).order_by(Person.created_at))]}

def notify_after_commit(album_id,actor_id,kind,message,photo_id=None,version_id=None,target_ids=None):
    # Notifications use a separate transaction: failure cannot undo the user's saved edit.
    import logging
    try:
        with SessionLocal() as db:
            ids=target_ids if target_ids is not None else db.scalars(select(AlbumMember.user_id).where(AlbumMember.album_id==album_id)).all()
            for user_id in set(ids)-{actor_id}:
                db.add(Notification(user_id=user_id,album_id=album_id,photo_id=photo_id,version_id=version_id,kind=kind,message=message))
            db.commit()
    except Exception:
        logging.getLogger(__name__).exception('Notification delivery failed after successful save')

def queue_photo_files(db,p):
    for key in (p.original_key,p.thumbnail_key,p.display_key): db.add(FileCleanup(key=key))

def drain_cleanup():
    from .storage import get_storage
    import logging
    try:
        with SessionLocal() as db:
            for row in db.scalars(select(FileCleanup).where(FileCleanup.not_before <= now()).limit(200).with_for_update(skip_locked=True)):
                try:
                    if row.key.startswith('rekognition-'):
                        from .grouping import cleanup_external
                        cleanup_external(row.key)
                    else:
                        get_storage().delete(row.key)
                    db.delete(row)
                except Exception:
                    logging.getLogger(__name__).exception('File cleanup will retry')
            db.commit()
    except Exception: logging.getLogger(__name__).exception('Cleanup deferred')
