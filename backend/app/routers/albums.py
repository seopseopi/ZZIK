"""Album membership, invitation, settings, and deletion endpoints."""
from __future__ import annotations

from .. import responses as out

import secrets
from ..config import settings
from ..db import get_db
from ..dependencies import auth
from ..models import Album, AlbumMember, ApprovalTarget, FaceGroup, FileCleanup, Notification, Person, Photo, Version
from ..photo_operations import queue_all_photo_files
from ..schemas import AlbumCreate, AlbumPatch, Join
from ..services import album_dict, drain_cleanup, fail, invalidate_photo_reviews, membership, notify_after_commit
from fastapi import APIRouter, Depends
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session as DBSession
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

router = APIRouter()


def timezone_name(name):
    try: ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError): fail(422,'INVALID_TIMEZONE','올바른 시간대를 선택해 주세요.')
    return name


@router.get('/api/albums', response_model=out.PageResponse[out.AlbumResponse], response_model_exclude_unset=True)
def albums(user=Depends(auth),db:DBSession=Depends(get_db)):
    rows=db.scalars(select(Album).join(AlbumMember).where(AlbumMember.user_id==user.id).order_by(Album.created_at.desc())).all()
    return {'items':[album_dict(db,a) for a in rows],'total':len(rows),'page':1,'page_size':len(rows)}


@router.post('/api/albums',status_code=201, response_model=out.AlbumResponse, response_model_exclude_unset=True)
def create_album(body:AlbumCreate,user=Depends(auth),db:DBSession=Depends(get_db)):
    a=Album(name=body.name.strip(),description=body.description,timezone=timezone_name(body.timezone),owner_id=user.id,invite_code=secrets.token_urlsafe(12))
    if not a.name: fail(422,'INVALID_NAME','앨범 이름을 입력해 주세요.')
    db.add(a)
    db.flush()
    db.add(AlbumMember(album_id=a.id,user_id=user.id,role='owner'))
    db.commit()
    return album_dict(db,a)


@router.post('/api/albums/join', response_model=out.AlbumResponse, response_model_exclude_unset=True)
def join_album(body:Join,user=Depends(auth),db:DBSession=Depends(get_db)):
    code=body.code.strip().rstrip('/').split('/')[-1]
    a=db.scalar(select(Album).where(Album.invite_code==code).with_for_update())
    if not a: fail(404,'INVALID_INVITE','유효한 초대코드를 입력해 주세요.')
    if not db.get(AlbumMember,(a.id,user.id)):
        db.add(AlbumMember(album_id=a.id,user_id=user.id))
        db.commit()
        notify_after_commit(a.id,user.id,'member_joined',f'{user.name} 님이 앨범에 참여했어요.')
    return album_dict(db,a)


@router.get('/api/albums/{album_id}', response_model=out.AlbumResponse, response_model_exclude_unset=True)
def album_detail(album_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    return album_dict(db,membership(db,album_id,user))


@router.patch('/api/albums/{album_id}', response_model=out.AlbumResponse, response_model_exclude_unset=True)
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


@router.post('/api/albums/{album_id}/invite', response_model=out.InviteResponse, response_model_exclude_unset=True)
def rotate_invite(album_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    a=membership(db,album_id,user,owner=True,exclusive=True)
    a.invite_code=secrets.token_urlsafe(12)
    db.commit()
    return {'invite_code':a.invite_code}


@router.delete('/api/albums/{album_id}', response_model=out.OkResponse, response_model_exclude_unset=True)
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


@router.delete('/api/albums/{album_id}/members/{user_id}', response_model=out.OkResponse, response_model_exclude_unset=True)
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
