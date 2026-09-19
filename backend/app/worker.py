"""Durable database worker with bounded retry, heartbeat leases, and fenced writes.

Run: python -m backend.app.worker [--once]
"""
from __future__ import annotations

import argparse
import logging
import signal
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import OperationalError
from .analysis import AnalysisError, analyze
from .config import settings
from .db import SessionLocal
from .image_service import ImageError, quality_metrics
from .models import AnalysisJob, AnalysisRun, Photo, PhotoPerson, Person, now
from .services import invalidate_photo_reviews, drain_cleanup, lock_album
from .storage import get_storage

logger = logging.getLogger(__name__)


def claim_job() -> tuple[str, str] | None:
    """A compare-and-swap is portable to SQLite; PostgreSQL workers never share a lease."""
    current = now()
    cutoff = current - timedelta(seconds=settings.worker_lease_seconds)
    eligible = or_(and_(AnalysisJob.status == 'pending', AnalysisJob.available_at <= current),
                   and_(AnalysisJob.status == 'processing', AnalysisJob.locked_at < cutoff))
    active_photo = AnalysisJob.photo_id.in_(select(Photo.id).where(Photo.trashed_at.is_(None)))
    with SessionLocal() as db:
        candidates = db.execute(select(AnalysisJob.id, AnalysisJob.attempts, AnalysisJob.photo_id)
                                .join(Photo, Photo.id == AnalysisJob.photo_id)
                                .where(eligible, Photo.trashed_at.is_(None)).order_by(AnalysisJob.available_at).limit(30)).all()
        for job_id, attempts, photo_id in candidates:
            if attempts >= settings.worker_max_attempts:
                changed = db.execute(update(AnalysisJob).where(AnalysisJob.id == job_id, eligible, active_photo)
                                     .values(status='failed', error='WORKER_LEASE_EXHAUSTED: 작업 실행 횟수를 초과했어요.',
                                             locked_by=None, locked_at=None, finished_at=current)).rowcount
                db.commit()
                if changed:
                    with SessionLocal() as photo_db:
                        album_id = photo_db.scalar(select(Photo.album_id).where(Photo.id == photo_id))
                        if album_id and lock_album(photo_db, album_id, exclusive=True):
                            photo = photo_db.scalar(select(Photo).where(Photo.id == photo_id).with_for_update())
                            job = photo_db.scalar(select(AnalysisJob).where(AnalysisJob.id == job_id).with_for_update()
                                                  .execution_options(populate_existing=True))
                            if job and job.status == 'failed' and photo:
                                photo.analysis_status, photo.analysis_error = 'failed', job.error
                                photo_db.commit()
                continue
            token = str(uuid.uuid4())
            changed = db.execute(update(AnalysisJob).where(AnalysisJob.id == job_id, eligible, active_photo, AnalysisJob.attempts == attempts)
                                 .values(status='processing', attempts=attempts + 1, locked_at=current,
                                         locked_by=token, error=None, finished_at=None)).rowcount
            db.commit()
            if changed:
                return job_id, token
    return None


def heartbeat(job_id, token, stop):
    interval = max(.25, min(20, settings.worker_lease_seconds / 3))
    while not stop.wait(interval):
        try:
            with SessionLocal() as db:
                changed = db.execute(update(AnalysisJob).where(AnalysisJob.id == job_id, AnalysisJob.locked_by == token,
                                                               AnalysisJob.status == 'processing').values(locked_at=now())).rowcount
                db.commit()
                if not changed:
                    return
        except Exception:
            logger.exception('Lease heartbeat failed; fenced completion will check ownership')


def _owns(job, token):
    return job is not None and job.status == 'processing' and job.locked_by == token


def _load_input(job_id, token):
    with SessionLocal() as db:
        job = db.get(AnalysisJob, job_id)
        if not _owns(job, token):
            return None
        photo = db.get(Photo, job.photo_id)
        if not photo:
            return None
        data = get_storage().get(photo.original_key)
        references = [{'id': person.id, 'name': person.name, 'data': get_storage().get(person.reference_key)}
                      for person in db.scalars(select(Person).where(Person.album_id == photo.album_id,
                                                                   Person.reference_key.is_not(None)))]
        inputs = (photo.id, photo.album_id, photo.original_hash, data, references, photo.latitude, photo.longitude)
        db.rollback()
        if not lock_album(db, inputs[1], exclusive=True):
            return None
        photo = db.scalar(select(Photo).where(Photo.id == inputs[0]).with_for_update())
        job = db.scalar(select(AnalysisJob).where(AnalysisJob.id == job_id).with_for_update().execution_options(populate_existing=True))
        if not photo or not _owns(job, token):
            return None
        photo.analysis_status, photo.analysis_error = "processing", None
        photo.analysis_provider = settings.face_analysis_provider
        photo.analysis_mode = "sample" if settings.face_analysis_provider == "fixture" else "live"
        db.commit()
        return inputs


def reverse_geocode(latitude, longitude):
    if latitude is None or longitude is None:
        return {}
    if not settings.geocoding_url:
        return {"status": "not_configured", "notice": "좌표는 보존되며 장소명 연결은 설정되지 않았어요."}
    try:
        import httpx
        response = httpx.get(settings.geocoding_url,
                             params={"lat": latitude, "lon": longitude, "format": "jsonv2"},
                             headers={"User-Agent": settings.geocoding_user_agent}, timeout=10)
        response.raise_for_status()
        name = response.json().get("display_name")
        return {"status": "completed", "name": str(name)[:255] if name else None}
    except Exception:
        # Location failure does not erase a successful face analysis or GPS.
        logger.warning("Reverse geocoding unavailable")
        return {"status": "failed", "notice": "장소명 조회에 실패했지만 촬영 좌표는 보존했어요."}


def _apply_result(db, photo, result):
    before = set(db.scalars(select(PhotoPerson.person_id).where(PhotoPerson.photo_id == photo.id, PhotoPerson.excluded == False)))
    allowed = set(db.scalars(select(Person.id).where(Person.album_id == photo.album_id)))
    faces = [dict(face, person_id=face['person_id'] if face.get('person_id') in allowed else None)
             for face in result['faces']]
    matched = {face['person_id'] for face in faces if face['person_id']}
    existing = {link.person_id: link for link in db.scalars(select(PhotoPerson).where(PhotoPerson.photo_id == photo.id))}
    for person_id, link in existing.items():
        if link.source == 'auto' and not link.excluded and person_id not in matched:
            db.delete(link)
    for person_id in matched:
        # Manual exclusions/additions always win over later analysis.
        if person_id not in existing:
            db.add(PhotoPerson(photo_id=photo.id, person_id=person_id, source='auto', excluded=False))
    db.flush()
    after = set(db.scalars(select(PhotoPerson.person_id).where(PhotoPerson.photo_id == photo.id, PhotoPerson.excluded == False)))
    if before != after:
        invalidate_photo_reviews(db, photo, '등장 인물 분석이 변경되어 다시 확인이 필요해요.')
    photo.faces = faces
    photo.face_count = len(faces)
    photo.unknown_faces = sum(face['person_id'] is None for face in faces)
    photo.tags = result['tags']
    photo.analysis_provider, photo.analysis_mode = result['provider'], result['mode']
    metadata = dict(photo.analysis_metadata or {})
    metadata.update(result.get('metadata', {}))
    metadata.update(model=result['model'], calls=result['calls'], elapsed_ms=result['elapsed_ms'],
                    analyzed_at=now().isoformat())
    photo.analysis_metadata = metadata


def process_claim(job_id: str, token: str) -> bool:
    stop = threading.Event()
    lease_thread = threading.Thread(target=heartbeat, args=(job_id, token, stop), daemon=True)
    lease_thread.start()
    started = time.monotonic()
    result = None
    try:
        inputs = _load_input(job_id, token)
        if inputs is None:
            return False
        photo_id, album_id, original_hash, data, references, latitude, longitude = inputs
        result = analyze(data, references, original_hash, album_id)
        quality = quality_metrics(data)
        location = reverse_geocode(latitude, longitude)
        with SessionLocal() as db:
            # Match API album → photo → job lock order. Exclusive album access is
            # acquired before photos because grouping also serializes at album level.
            # A changed token still fences a worker whose remote call completed late.
            if not lock_album(db, album_id, exclusive=True):
                return False
            photo = db.scalar(select(Photo).where(Photo.id == photo_id).with_for_update())
            job = db.scalar(select(AnalysisJob).where(AnalysisJob.id == job_id).with_for_update())
            if not photo or not _owns(job, token):
                return False
            _apply_result(db, photo, result)
            photo.quality = quality
            if location.get("name"):
                photo.location_name = location["name"]
            if location:
                photo.analysis_metadata = dict(photo.analysis_metadata, geocoding=location)
            if (photo.analysis_metadata or {}).get('grouping_requested'):
                from .grouping import group_photo
                group_result = group_photo(db, photo, data)
                result["calls"] += group_result.get("calls", 0)
                photo.analysis_metadata = dict(photo.analysis_metadata, grouping_requested=False, grouping=group_result, calls=result["calls"])
            else:
                from .grouping import sync_group_people
                sync_group_people(db, [photo.id])
            photo.analysis_metadata = dict(photo.analysis_metadata, elapsed_ms=round((time.monotonic()-started)*1000))
            photo.analysis_status, photo.analysis_error = 'completed', None
            job.status, job.error, job.finished_at = 'completed', None, now()
            job.locked_at, job.locked_by = None, None
            db.add(AnalysisRun(photo_id=photo.id, provider=result['provider'], mode=result['mode'], model=result['model'],
                               status='completed', calls=result['calls'], elapsed_ms=round((time.monotonic()-started)*1000)))
            db.commit()
        return True
    except Exception as exc:
        if isinstance(exc, (AnalysisError, ImageError)):
            error = f'{exc.code}: {exc.message}'
            retryable = getattr(exc, 'retryable', False)
        else:
            logger.exception('Photo analysis failed')
            error = 'ANALYSIS_FAILED: 사진 분석 처리에 실패했어요. 저장 파일과 연결 설정을 확인해 주세요.'
            retryable = isinstance(exc, (OSError, TimeoutError, OperationalError))
        try:
            with SessionLocal() as db:
                snapshot = db.get(AnalysisJob, job_id)
                if not snapshot:
                    return False
                failed_album_id = db.scalar(select(Photo.album_id).where(Photo.id == snapshot.photo_id))
                if not failed_album_id or not lock_album(db, failed_album_id, exclusive=True):
                    return False
                photo = db.scalar(select(Photo).where(Photo.id == snapshot.photo_id).with_for_update())
                job = db.scalar(select(AnalysisJob).where(AnalysisJob.id == job_id).with_for_update().execution_options(populate_existing=True))
                if not photo or not _owns(job, token):
                    return False
                retry = retryable and job.attempts < settings.worker_max_attempts
                job.status = photo.analysis_status = 'pending' if retry else 'failed'
                job.error = photo.analysis_error = error
                job.available_at = now() + timedelta(seconds=min(60, 2 ** job.attempts))
                job.finished_at = None if retry else now()
                job.locked_at, job.locked_by = None, None
                db.add(AnalysisRun(photo_id=photo.id, provider=settings.face_analysis_provider,
                                   mode='sample' if settings.face_analysis_provider == 'fixture' else 'live',
                                   model=result.get('model') if result else None, status='failed',
                                   calls=(result['calls'] if result else 0) + getattr(exc, 'calls', 0),
                                   elapsed_ms=round((time.monotonic() - started) * 1000), error=error))
                db.commit()
        except Exception:
            logger.exception('Failed to record analysis error; lease expiry will recover the job')
        return False
    finally:
        stop.set()
        lease_thread.join(timeout=1)


def process_one() -> bool:
    claim = claim_job()
    if claim is None:
        return False
    process_claim(*claim)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true', help='Drain all currently available jobs and exit')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    shutdown = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: shutdown.set())
    cleanup_lock = threading.Lock()
    last_cleanup = [0.0]
    def loop():
        while not shutdown.is_set():
            if time.monotonic() - last_cleanup[0] >= 30 and cleanup_lock.acquire(blocking=False):
                try:
                    last_cleanup[0] = time.monotonic()
                    drain_cleanup()
                finally:
                    cleanup_lock.release()
            if not process_one():
                if args.once:
                    return
                shutdown.wait(settings.worker_poll_seconds)
    with ThreadPoolExecutor(max_workers=max(1, settings.worker_concurrency)) as pool:
        futures = [pool.submit(loop) for _ in range(max(1, settings.worker_concurrency))]
        for future in futures:
            future.result()
    drain_cleanup()


if __name__ == '__main__':
    main()
