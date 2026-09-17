"""Analysis status, retry requests, and similar-photo recommendations."""
from __future__ import annotations

from ..config import settings
from ..db import get_db
from ..dependencies import auth
from ..image_service import similar_groups
from ..models import AnalysisJob, AnalysisRun, Photo
from ..photo_operations import queue_failed_analysis
from ..services import fail, get_photo, membership, photo_dict
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

router = APIRouter()


@router.post('/api/photos/{photo_id}/reanalyze')
def reanalyze(photo_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    p=get_photo(db,photo_id,user,lock=True)
    if p.analysis_status!='failed': fail(409,'ANALYSIS_NOT_FAILED','분석에 실패한 사진만 다시 분석할 수 있어요.')
    if not queue_failed_analysis(db,p): fail(409,'ANALYSIS_ALREADY_QUEUED','이미 분석을 다시 진행하고 있어요.')
    db.commit()
    return photo_dict(db,p)


@router.get('/api/albums/{album_id}/analysis-status')
def album_analysis_status(album_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    membership(db,album_id,user)
    stats={status:0 for status in ['pending','processing','completed','failed']}
    stats.update(dict(db.execute(select(Photo.analysis_status,func.count()).where(Photo.album_id==album_id)
                                 .group_by(Photo.analysis_status)).all()))
    # These are accumulated run totals, not unique photo counts or wall-clock duration.
    recorded_runs,calls,elapsed_ms=db.execute(select(func.count(AnalysisRun.id),func.coalesce(func.sum(AnalysisRun.calls),0),
        func.coalesce(func.sum(AnalysisRun.elapsed_ms),0)).join(Photo,Photo.id==AnalysisRun.photo_id)
        .where(Photo.album_id==album_id)).one()
    failures=db.execute(select(Photo.id,Photo.filename,Photo.analysis_error).where(Photo.album_id==album_id,Photo.analysis_status=='failed')
                        .order_by(Photo.created_at.desc(),Photo.id).limit(20)).all()
    oldest_pending_at=db.scalar(select(func.min(AnalysisJob.available_at)).join(Photo,Photo.id==AnalysisJob.photo_id)
                                .where(Photo.album_id==album_id,AnalysisJob.status=='pending'))
    return {'provider':settings.face_analysis_provider,'mode':'sample' if settings.face_analysis_provider=='fixture' else 'live',
            'stats':stats,'total':sum(stats.values()),'recorded_runs':recorded_runs,'calls':calls,'elapsed_ms':elapsed_ms,
            'failures':[{'photo_id':photo_id,'filename':filename,'error':error} for photo_id,filename,error in failures],
            'oldest_pending_at':oldest_pending_at}


@router.post('/api/albums/{album_id}/reanalyze-failed')
def reanalyze_album_failures(album_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    membership(db,album_id,user)
    photos=db.scalars(select(Photo).where(Photo.album_id==album_id,Photo.analysis_status=='failed')
                      .order_by(Photo.id).with_for_update().execution_options(populate_existing=True)).all()
    queued=sum(queue_failed_analysis(db,photo) for photo in photos)
    db.commit()
    return {'queued':queued}


@router.get('/api/albums/{album_id}/recommendations')
def recommendations(album_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    membership(db,album_id,user)
    photos=db.scalars(select(Photo).where(Photo.album_id==album_id).order_by(Photo.captured_at,Photo.id)).all()
    rows=[dict(photo_dict(db,p),sha256=p.original_hash,faces=p.faces) for p in photos]
    groups=similar_groups(rows)
    for group in groups:
        for photo in group['photos']: photo.pop('sha256',None)
    return {'groups':groups,'method':'동일한 전처리의 유사 사진 안에서 흔들림·노출·눈 감음을 비교해요. 촬영 시간이 없으면 같은 원본만 묶어요.'}
