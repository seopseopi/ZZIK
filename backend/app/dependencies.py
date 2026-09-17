"""Shared session authentication and album-member validation."""
from __future__ import annotations

from .db import get_db
from .models import AlbumMember
from .services import current_user, fail
from fastapi import Depends, Request
from sqlalchemy.orm import Session as DBSession


def auth(request: Request, db: DBSession = Depends(get_db)):
    return current_user(request,db)[0]


def ensure_target_member(db,album_id,user_id):
    if user_id and not db.get(AlbumMember,(album_id,user_id)): fail(422,'INVALID_MEMBER','이 앨범의 멤버만 연결할 수 있어요.')
