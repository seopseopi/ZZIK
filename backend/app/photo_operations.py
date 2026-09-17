"""Transactional upload staging, file cleanup, and failed-analysis requeue."""
from __future__ import annotations

from . import storage as storage_backend
from .image_service import inspect_image, prepare_image, render_cache_key, thumbnail_image
from .models import AnalysisJob, FileCleanup, GroupFace, Photo, Version, now, uid
from .services import drain_cleanup, fail, membership, queue_photo_files
from datetime import timedelta
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


def queue_all_photo_files(db,p):
    queue_photo_files(db,p)
    for face in db.scalars(select(GroupFace).where(GroupFace.photo_id==p.id)):
        db.add(FileCleanup(key=f'rekognition-face:{p.album_id}:{face.external_face_id}'))
    for v in db.scalars(select(Version).where(Version.photo_id==p.id)):
        for size in (None,1600): db.add(FileCleanup(key=render_cache_key(p.original_hash,v.brightness,v.saturation,size)))


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
    storage=storage_backend.get_storage()
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
