"""Album-scoped face-group analysis, linking, merging, and splitting."""
from __future__ import annotations

from ..config import settings
from ..db import get_db
from ..dependencies import auth
from ..models import AnalysisJob, FaceGroup, GroupFace, Person, Photo, now
from ..schemas import GroupMerge, GroupPatch, GroupSplit
from ..services import fail, membership
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

router = APIRouter()


def group_dict(db,g):
    faces=db.scalars(select(GroupFace).where(GroupFace.group_id==g.id).order_by(GroupFace.id)).all()
    return {'id':g.id,'name':g.name,'person_id':g.person_id,'album_id':g.album_id,'face_count':len(faces),
            'faces':[{'id':f.id,'photo_id':f.photo_id,'box':f.box,'similarity':f.similarity,'thumbnail_url':f'/api/photos/{f.photo_id}/file?kind=thumbnail'} for f in faces]}


def get_group(db,group_id,user):
    g=db.get(FaceGroup,group_id)
    if not g: fail(404,'GROUP_NOT_FOUND','인물 그룹을 찾을 수 없어요.')
    membership(db,g.album_id,user)
    return g


@router.get('/api/albums/{album_id}/face-groups')
def face_groups(album_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    membership(db,album_id,user)
    groups=db.scalars(select(FaceGroup).where(FaceGroup.album_id==album_id).order_by(FaceGroup.created_at)).all()
    return {'items':[group_dict(db,g) for g in groups],'total':len(groups),'available':settings.face_analysis_provider=='rekognition',
            'mode':settings.face_analysis_provider,'message':None if settings.face_analysis_provider=='rekognition' else '등록 없는 자동 인물 그룹은 AWS Rekognition 연결이 필요해요. 샘플 모드는 기준 인물 매칭만 제공해요.'}


@router.post('/api/albums/{album_id}/face-groups/analyze')
def analyze_face_groups(album_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    membership(db,album_id,user)
    if settings.face_analysis_provider!='rekognition': fail(409,'GROUPING_UNAVAILABLE','자동 인물 그룹은 실제 Rekognition 연결 후 사용할 수 있어요.')
    grouped=select(GroupFace.photo_id)
    photos=db.scalars(select(Photo).where(Photo.album_id==album_id,Photo.id.not_in(grouped)).order_by(Photo.id).with_for_update()).all()
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
    from ..grouping import sync_group_people
    photo_ids=set(db.scalars(select(GroupFace.photo_id).where(GroupFace.group_id==g.id)))
    g.person_id=person_id
    sync_group_people(db,photo_ids,force_review=True)


@router.patch('/api/face-groups/{group_id}')
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


@router.post('/api/face-groups/merge')
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


@router.post('/api/face-groups/{group_id}/split',status_code=201)
def split_group(group_id:str,body:GroupSplit,user=Depends(auth),db:DBSession=Depends(get_db)):
    g=get_group(db,group_id,user)
    faces=db.scalars(select(GroupFace).where(GroupFace.group_id==g.id)).all()
    selected=set(body.face_ids)
    if not selected.issubset({f.id for f in faces}) or len(selected)==len(faces): fail(422,'INVALID_SPLIT','기존 그룹에 남길 얼굴과 분리할 얼굴을 나누어 선택해 주세요.')
    new=FaceGroup(album_id=g.album_id,name='새 인물 그룹')
    db.add(new)
    db.flush()
    for face in faces:
        if face.id in selected: face.group_id=new.id
    from ..grouping import sync_group_people
    sync_group_people(db,{face.photo_id for face in faces},force_review=True)
    db.commit()
    return group_dict(db,new)
