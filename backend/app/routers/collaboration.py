"""Version comments, album board, and member notifications."""
from __future__ import annotations

from ..db import get_db
from ..dependencies import auth
from ..models import AlbumMember, Comment, Notification, Photo
from ..schemas import CommentCreate
from ..services import fail, get_version, membership, notify_after_commit, photo_dict, version_dict
from fastapi import APIRouter, Depends
from sqlalchemy import and_, select
from sqlalchemy.orm import Session as DBSession

router = APIRouter()


@router.post('/api/versions/{version_id}/comments',status_code=201)
def add_comment(version_id:str,body:CommentCreate,user=Depends(auth),db:DBSession=Depends(get_db)):
    v,p=get_version(db,version_id,user)
    text_body=body.body.strip()
    if not text_body: fail(422,'EMPTY_COMMENT','댓글을 입력해 주세요.')
    db.add(Comment(version_id=v.id,author_id=user.id,body=text_body,kind=body.kind))
    db.commit()
    notify_after_commit(p.album_id,user.id,body.kind,f'{user.name} 님이 '+('수정을 요청했어요.' if body.kind=='change_request' else '댓글을 남겼어요.'),p.id,v.id)
    return version_dict(db,v,p)


@router.get('/api/albums/{album_id}/board')
def board(album_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    membership(db,album_id,user)
    result={status:[] for status in ['selection','editing','review','final']}
    for p in db.scalars(select(Photo).where(Photo.album_id==album_id).order_by(Photo.created_at.desc())):
        item=photo_dict(db,p)
        result[item['board_status']].append(item)
    return result


@router.get('/api/notifications')
def notifications(user=Depends(auth),db:DBSession=Depends(get_db)):
    rows=db.scalars(select(Notification).join(AlbumMember,and_(AlbumMember.album_id==Notification.album_id,AlbumMember.user_id==user.id)).where(Notification.user_id==user.id).order_by(Notification.created_at.desc()).limit(200)).all()
    items=[{key:getattr(n,key) for key in ['id','album_id','photo_id','version_id','kind','message','read','created_at']} for n in rows]
    return {'items':items,'total':len(items)}


@router.post('/api/notifications/{notification_id}/read')
def read_notification(notification_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    n=db.get(Notification,notification_id)
    if not n or n.user_id!=user.id: fail(404,'NOTIFICATION_NOT_FOUND','알림을 찾을 수 없어요.')
    membership(db,n.album_id,user)
    n.read=True
    db.commit()
    return {'ok':True}
