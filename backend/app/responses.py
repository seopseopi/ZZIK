"""Public response contracts. Nullable values remain present; optional fields stay omitted."""
from datetime import datetime
from typing import Generic, TypeVar
from pydantic import BaseModel, ConfigDict, JsonValue, field_serializer


class ResponseModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

    @field_serializer('*', check_fields=False)
    def serialize_dates(self, value):
        # Match the existing jsonable_encoder representation (including UTC offset).
        return value.isoformat() if isinstance(value, datetime) else value


class AuthorResponse(ResponseModel):
    id: str
    name: str


class UserResponse(AuthorResponse):
    email: str


class MemberResponse(UserResponse):
    role: str


class SessionResponse(ResponseModel):
    user: UserResponse
    csrf_token: str


class OkResponse(ResponseModel):
    ok: bool


class PersonResponse(ResponseModel):
    id: str
    name: str
    user_id: str | None
    proposed_user_id: str | None
    reference_url: str | None
    link_status: str
    source: str | None = None


class AlbumResponse(ResponseModel):
    id: str
    name: str
    description: str
    timezone: str
    owner_id: str
    invite_code: str
    photo_count: int
    member_count: int
    cover_url: str | None
    created_at: datetime
    members: list[MemberResponse]
    people: list[PersonResponse]


class ApprovalTargetResponse(ResponseModel):
    user_id: str
    name: str
    approved: bool


class CommentResponse(ResponseModel):
    id: str
    author: AuthorResponse
    body: str
    kind: str
    created_at: datetime


class VersionResponse(ResponseModel):
    id: str
    photo_id: str
    number: int
    name: str
    parent_id: str | None
    author: AuthorResponse
    created_at: datetime
    brightness: float
    saturation: float
    renderer_version: str
    preview_url: str
    review_requested: bool
    needs_review: bool
    review_reason: str | None
    targets: list[ApprovalTargetResponse]
    approval_count: int
    target_count: int
    consensus: bool
    is_final: bool
    comments: list[CommentResponse]


class PhotoResponse(ResponseModel):
    id: str
    album_id: str
    uploader_id: str
    filename: str
    thumbnail_url: str
    display_url: str
    original_url: str
    width: int
    height: int
    created_at: datetime
    captured_at: str | None
    capture_timezone: str | None
    latitude: float | None
    longitude: float | None
    location_name: str | None
    analysis_status: str
    analysis_error: str | None
    analysis_provider: str | None
    analysis_mode: str | None
    analysis_metadata: dict[str, JsonValue]
    face_count: int
    unknown_faces: int
    people: list[PersonResponse]
    tags: list[str]
    purpose: str
    selected: bool
    note: str
    final_version_id: str | None
    board_status: str
    quality: dict[str, JsonValue]


class PhotoDetailResponse(PhotoResponse):
    faces: list[dict[str, JsonValue]]
    versions: list[VersionResponse]


class RecommendationPhotoResponse(PhotoResponse):
    faces: list[dict[str, JsonValue]]


T = TypeVar('T')
class ItemsResponse(ResponseModel, Generic[T]):
    items: list[T]
    total: int


class PageResponse(ItemsResponse[T], Generic[T]):
    page: int
    page_size: int


class AnalysisStats(ResponseModel):
    pending: int
    processing: int
    completed: int
    failed: int


class PhotoListResponse(PageResponse[PhotoResponse]):
    stats: AnalysisStats


class AnalysisFailure(ResponseModel):
    photo_id: str
    filename: str
    error: str | None


class AnalysisStatusResponse(ResponseModel):
    provider: str
    mode: str
    stats: AnalysisStats
    total: int
    recorded_runs: int
    calls: int
    elapsed_ms: int
    failures: list[AnalysisFailure]
    oldest_pending_at: datetime | None


class QueuedResponse(ResponseModel):
    queued: int


class InviteResponse(ResponseModel):
    invite_code: str


class RecommendationGroup(ResponseModel):
    id: str
    photos: list[RecommendationPhotoResponse]
    recommended_ids: list[str]
    reasons: dict[str, list[str]]


class RecommendationsResponse(ResponseModel):
    groups: list[RecommendationGroup]
    method: str


class BoardResponse(ResponseModel):
    selection: list[PhotoResponse]
    editing: list[PhotoResponse]
    review: list[PhotoResponse]
    final: list[PhotoResponse]


class NotificationResponse(ResponseModel):
    id: str
    album_id: str
    photo_id: str | None
    version_id: str | None
    kind: str
    message: str
    read: bool
    created_at: datetime


class GroupFaceResponse(ResponseModel):
    id: str
    photo_id: str
    box: dict[str, float]
    similarity: float | None
    thumbnail_url: str


class FaceGroupResponse(ResponseModel):
    id: str
    name: str | None
    person_id: str | None
    album_id: str
    face_count: int
    faces: list[GroupFaceResponse]


class FaceGroupsResponse(ItemsResponse[FaceGroupResponse]):
    available: bool
    mode: str
    message: str | None


class LiveResponse(ResponseModel):
    status: str


class ReadyResponse(LiveResponse):
    database: str


class ConfigResponse(ResponseModel):
    face_provider: str
    storage_backend: str
    demo_enabled: bool
    max_upload_bytes: int
    grouping_available: bool


class ErrorResponse(ResponseModel):
    code: str
    message: str
    details: JsonValue = None
