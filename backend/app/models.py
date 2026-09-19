import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, UniqueConstraint, Integer, Float, Boolean, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def uid(): return str(uuid.uuid4())
def now(): return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Session(Base):
    __tablename__ = 'sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class Album(Base):
    __tablename__ = 'albums'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default='')
    timezone: Mapped[str] = mapped_column(String(80), default='Asia/Seoul')
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    invite_code: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class AlbumMember(Base):
    __tablename__ = 'album_members'
    album_id: Mapped[str] = mapped_column(ForeignKey('albums.id', ondelete='CASCADE'), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), default='member')
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Person(Base):
    __tablename__ = 'people'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    album_id: Mapped[str] = mapped_column(ForeignKey('albums.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(80))
    user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    proposed_user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    reference_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Photo(Base):
    __tablename__ = 'photos'
    __table_args__ = (UniqueConstraint('album_id','uploader_id','request_id', name='uq_photo_upload_request'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    album_id: Mapped[str] = mapped_column(ForeignKey('albums.id', ondelete='CASCADE'), index=True)
    uploader_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    request_id: Mapped[str] = mapped_column(String(100))
    filename: Mapped[str] = mapped_column(String(255))
    original_key: Mapped[str] = mapped_column(Text)
    thumbnail_key: Mapped[str] = mapped_column(Text)
    display_key: Mapped[str] = mapped_column(Text)
    original_hash: Mapped[str] = mapped_column(String(64))
    mime: Mapped[str] = mapped_column(String(40))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    byte_size: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    captured_at: Mapped[str | None] = mapped_column(String(80), nullable=True)
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    capture_timezone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    analysis_status: Mapped[str] = mapped_column(String(20), default='pending', index=True)
    analysis_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    analysis_mode: Mapped[str | None] = mapped_column(String(40), nullable=True)
    analysis_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    faces: Mapped[list] = mapped_column(JSON, default=list)
    face_count: Mapped[int] = mapped_column(Integer, default=0)
    unknown_faces: Mapped[int] = mapped_column(Integer, default=0)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    quality: Mapped[dict] = mapped_column(JSON, default=dict)
    purpose: Mapped[str] = mapped_column(String(40), default='undecided')
    note: Mapped[str] = mapped_column(Text, default='')
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    final_version_id: Mapped[str | None] = mapped_column(ForeignKey('versions.id', ondelete='SET NULL', use_alter=True, name='fk_photo_final_version'), nullable=True)

class PhotoPerson(Base):
    __tablename__ = 'photo_people'
    photo_id: Mapped[str] = mapped_column(ForeignKey('photos.id', ondelete='CASCADE'), primary_key=True)
    person_id: Mapped[str] = mapped_column(ForeignKey('people.id', ondelete='CASCADE'), primary_key=True)
    source: Mapped[str] = mapped_column(String(20), default='auto')
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)

class AnalysisJob(Base):
    __tablename__ = 'analysis_jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    photo_id: Mapped[str] = mapped_column(ForeignKey('photos.id', ondelete='CASCADE'), unique=True)
    status: Mapped[str] = mapped_column(String(20), default='pending', index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class AnalysisRun(Base):
    __tablename__ = 'analysis_runs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    photo_id: Mapped[str] = mapped_column(ForeignKey('photos.id', ondelete='CASCADE'), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    mode: Mapped[str] = mapped_column(String(40))
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    calls: Mapped[int] = mapped_column(Integer, default=0)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Version(Base):
    __tablename__ = 'versions'
    __table_args__ = (UniqueConstraint('photo_id','number',name='uq_version_photo_number'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    photo_id: Mapped[str] = mapped_column(ForeignKey('photos.id', ondelete='CASCADE'), index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey('versions.id', ondelete='SET NULL'), nullable=True)
    author_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    number: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(120))
    brightness: Mapped[float] = mapped_column(Float, default=1.0)
    saturation: Mapped[float] = mapped_column(Float, default=1.0)
    renderer_version: Mapped[str] = mapped_column(String(40), default='pillow-v1')
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    review_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_person_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class ApprovalTarget(Base):
    __tablename__ = 'approval_targets'
    version_id: Mapped[str] = mapped_column(ForeignKey('versions.id', ondelete='CASCADE'), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)

class Approval(Base):
    __tablename__ = 'approvals'
    version_id: Mapped[str] = mapped_column(ForeignKey('versions.id', ondelete='CASCADE'), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Comment(Base):
    __tablename__ = 'comments'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    version_id: Mapped[str] = mapped_column(ForeignKey('versions.id', ondelete='CASCADE'), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    body: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(30), default='comment')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Notification(Base):
    __tablename__ = 'notifications'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    album_id: Mapped[str] = mapped_column(ForeignKey('albums.id', ondelete='CASCADE'))
    photo_id: Mapped[str | None] = mapped_column(ForeignKey('photos.id', ondelete='CASCADE'), nullable=True)
    version_id: Mapped[str | None] = mapped_column(ForeignKey('versions.id', ondelete='CASCADE'), nullable=True)
    kind: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class FaceGroup(Base):
    __tablename__ = 'face_groups'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    album_id: Mapped[str] = mapped_column(ForeignKey('albums.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(80), default='이름 없는 인물')
    person_id: Mapped[str | None] = mapped_column(ForeignKey('people.id', ondelete='SET NULL'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class GroupFace(Base):
    __tablename__ = 'group_faces'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    group_id: Mapped[str] = mapped_column(ForeignKey('face_groups.id', ondelete='CASCADE'), index=True)
    photo_id: Mapped[str] = mapped_column(ForeignKey('photos.id', ondelete='CASCADE'), index=True)
    external_face_id: Mapped[str] = mapped_column(String(255), unique=True)
    box: Mapped[dict] = mapped_column(JSON, default=dict)
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)

class FileCleanup(Base):
    __tablename__ = 'file_cleanup'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    key: Mapped[str] = mapped_column(Text)
    not_before: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
