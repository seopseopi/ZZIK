"""Reference people, account-link acceptance, and reference-image access."""
from __future__ import annotations

from .. import storage as storage_backend
from ..config import settings
from ..db import get_db
from ..dependencies import auth, ensure_target_member
from ..image_service import inspect_image
from ..media import stored_file
from ..models import AlbumMember, FileCleanup, Person, Photo, now, uid
from ..schemas import PersonPatch
from ..services import drain_cleanup, fail, invalidate_person_reviews, membership, person_dict
from datetime import timedelta
from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

router = APIRouter()


def find_person(db,person_id,user,owner=False):
    p=db.get(Person,person_id)
    if not p: fail(404,'PERSON_NOT_FOUND','인물을 찾을 수 없어요.')
    membership(db,p.album_id,user,owner)
    return p


@router.get('/api/albums/{album_id}/people')
def list_people(album_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    membership(db,album_id,user)
    rows=db.scalars(select(Person).where(Person.album_id==album_id).order_by(Person.created_at)).all()
    return {'items':[person_dict(p) for p in rows],'total':len(rows)}


@router.post('/api/albums/{album_id}/people',status_code=201)
def add_person(album_id:str,name:str=Form(...,min_length=1,max_length=80),file:UploadFile=File(...),user_id:str|None=Form(None),user=Depends(auth),db:DBSession=Depends(get_db)):
    membership(db,album_id,user)
    user_id=user_id or None
    if user_id and user_id!=user.id: membership(db,album_id,user,owner=True)
    ensure_target_member(db,album_id,user_id)
    data=file.file.read(settings.max_upload_bytes+1)
    meta=inspect_image(data,file.content_type)
    from ..analysis import validate_reference, AnalysisError
    try: validate_reference(data,original_hash=meta['sha256'])
    except AnalysisError as exc: fail(422,exc.code,exc.message)
    person=Person(id=uid(),album_id=album_id,name=name.strip(),reference_hash=meta['sha256'],user_id=user.id if user_id==user.id else None,proposed_user_id=user_id if user_id!=user.id else None)
    if not person.name: fail(422,'INVALID_NAME','인물 이름을 입력해 주세요.')
    person.reference_key=f'albums/{album_id}/people/{person.id}.jpg'
    storage=storage_backend.get_storage()
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


@router.patch('/api/people/{person_id}')
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


@router.post('/api/people/{person_id}/accept-link')
def accept_person_link(person_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    person=find_person(db,person_id,user)
    if person.proposed_user_id != user.id: fail(403,'LINK_NOT_PROPOSED','본인에게 제안된 연결만 확인할 수 있어요.')
    if person.user_id: fail(409,'ALREADY_LINKED','이미 연결된 인물이에요.')
    invalidate_person_reviews(db,person.id,'인물의 계정 연결이 변경되었어요.')
    person.user_id=user.id
    person.proposed_user_id=None
    db.commit()
    return person_dict(person)


@router.delete('/api/people/{person_id}')
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


@router.get('/api/people/{person_id}/reference')
def person_reference(person_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    person=find_person(db,person_id,user)
    if not person.reference_key: fail(404,'REFERENCE_NOT_FOUND','기준 사진이 없어요.')
    return stored_file(person.reference_key,inspect_image(storage_backend.get_storage().get(person.reference_key))['mime'])
