"""Health probes and public runtime configuration."""
from __future__ import annotations

from .. import responses as out

from ..config import settings
from ..db import get_db
from ..models import User
from ..services import fail
from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session as DBSession

router = APIRouter()


@router.get('/health/live', response_model=out.LiveResponse, response_model_exclude_unset=True)
@router.get('/api/health/live', response_model=out.LiveResponse, response_model_exclude_unset=True)
def live(): return {'status':'ok'}


@router.get('/health/ready', response_model=out.ReadyResponse, response_model_exclude_unset=True)
@router.get('/api/health/ready', response_model=out.ReadyResponse, response_model_exclude_unset=True)
def ready(db: DBSession = Depends(get_db)):
    try:
        db.execute(text('SELECT 1'))
        db.execute(select(User.id).limit(1))
    except Exception: fail(503,'DATABASE_NOT_READY','데이터베이스를 준비하고 있어요.')
    return {'status':'ready','database':'ok'}


@router.get('/api/config', response_model=out.ConfigResponse, response_model_exclude_unset=True)
def config():
    return {'face_provider':settings.face_analysis_provider,'storage_backend':settings.storage_backend,
            'demo_enabled':settings.demo_enabled,'max_upload_bytes':settings.max_upload_bytes,
            'grouping_available':settings.face_analysis_provider=='rekognition'}
