"""Non-destructive edits, version history, approvals, and final selection."""
from __future__ import annotations

from .. import storage as storage_backend
from ..db import get_db
from ..dependencies import auth, ensure_target_member
from ..image_service import render_image
from ..media import version_file_response
from ..models import Approval, ApprovalTarget, Version
from ..schemas import RenderSettings, ReviewRequest, VersionCreate
from ..services import approval_state, effective_people, fail, get_photo, get_version, notify_after_commit, version_dict
from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

router = APIRouter()


@router.get('/api/photos/{photo_id}/versions')
def versions(photo_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    p=get_photo(db,photo_id,user)
    rows=db.scalars(select(Version).where(Version.photo_id==p.id).order_by(Version.number.desc())).all()
    return {'items':[version_dict(db,v,p) for v in rows],'total':len(rows)}


@router.post('/api/photos/{photo_id}/versions',status_code=201)
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


@router.post('/api/photos/{photo_id}/preview')
def preview(photo_id:str,body:RenderSettings,user=Depends(auth),db:DBSession=Depends(get_db)):
    p=get_photo(db,photo_id,user)
    data=render_image(storage_backend.get_storage().get(p.original_key),body.brightness,body.saturation,max_size=1600)
    return Response(data,media_type='image/jpeg')


@router.get('/api/versions/{version_id}/file')
def version_file(version_id:str,download:bool=False,preview:bool=False,user=Depends(auth),db:DBSession=Depends(get_db)):
    v,p=get_version(db,version_id,user)
    return version_file_response(p,v,download,preview)


@router.post('/api/versions/{version_id}/request-review')
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


@router.post('/api/versions/{version_id}/approval')
def approve(version_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    v,p=get_version(db,version_id,user,lock=True)
    targets,_,_=approval_state(db,v)
    if not v.review_requested or v.needs_review: fail(409,'REVIEW_NOT_ACTIVE','승인 요청을 확인하거나 새 보정본에서 다시 승인해 주세요.')
    if user.id not in targets: fail(403,'NOT_APPROVAL_TARGET','이 보정본의 승인 대상만 승인할 수 있어요.')
    if not db.get(Approval,(v.id,user.id)): db.add(Approval(version_id=v.id,user_id=user.id))
    db.commit()
    return version_dict(db,v,p)


@router.delete('/api/versions/{version_id}/approval')
def revoke_approval(version_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    v,p=get_version(db,version_id,user,lock=True)
    approval=db.get(Approval,(v.id,user.id))
    if approval: db.delete(approval)
    db.flush()
    if p.final_version_id==v.id and not approval_state(db,v)[2]: p.final_version_id=None
    db.commit()
    return version_dict(db,v,p)


@router.post('/api/versions/{version_id}/final')
def set_final(version_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    v,p=get_version(db,version_id,user,lock=True)
    if not approval_state(db,v)[2]: fail(409,'CONSENSUS_REQUIRED','모든 승인 대상의 확인을 받은 보정본만 최종본으로 선택할 수 있어요.')
    p.final_version_id=v.id
    db.commit()
    notify_after_commit(p.album_id,user.id,'final_selected',f'{user.name} 님이 최종본을 선택했어요.',p.id,v.id)
    return version_dict(db,v,p)
