import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownToLine,
  CheckCheck,
  MapPin,
  Plus,
  Settings2,
  SlidersHorizontal,
  Sparkles,
  X,
} from "lucide-react";
import { dateLabel, downloadPhoto, patch, post } from "../../api";
import type { Album, Photo } from "../../types";
import { Avatar } from "../../ui";

export function PhotoInfo({
  photo,
  album,
  onClose,
  onEdit,
  notify,
}: {
  photo: Photo;
  album: Album;
  onClose: () => void;
  onEdit: () => void;
  notify: (message: string) => void;
}) {
  const client = useQueryClient();
  const [note, setNote] = useState(photo.note || "");
  const [saving, setSaving] = useState(false);
  async function update(data: unknown) {
    setSaving(true);
    try {
      await patch(`/photos/${photo.id}`, data);
      client.invalidateQueries({ queryKey: ["photos"] });
      notify("사진 정보를 저장했어요.");
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <aside className="photo-info">
      <header>
        <h3>사진 정보</h3>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label="사진 정보 닫기"
        >
          <X size={17} />
        </button>
      </header>
      <button
        className="info-image"
        onClick={onEdit}
        aria-label="사진 크게 보고 보정하기"
      >
        <img src={photo.display_url} alt={photo.filename} />
        <span>
          <Settings2 size={15} /> 크게 보고 보정하기
        </span>
      </button>
      <h4>{photo.filename}</h4>
      <p className="info-date">
        {photo.captured_at
          ? dateLabel(photo.captured_at)
          : "촬영 시각 정보 없음"}
      </p>
      <p className="info-location">
        <MapPin size={13} />
        {photo.location_name ||
          (photo.latitude != null
            ? `${photo.latitude.toFixed(4)}, ${photo.longitude?.toFixed(4)}`
            : "위치 정보 없음")}
      </p>
      <div className="info-section">
        <h5>
          함께 나온 사람 <span>{photo.people.length}</span>
        </h5>
        <div className="info-people">
          {photo.people.map((p) => (
            <div key={p.id}>
              <Avatar
                name={p.name}
                url={album.people.find((a) => a.id === p.id)?.reference_url}
                size={39}
              />
              <small>{p.name}</small>
            </div>
          ))}
          <button
            className="add-person-small"
            onClick={onEdit}
            aria-label="등장 인물 수정"
          >
            <Plus size={16} />
          </button>
        </div>
        {photo.unknown_faces > 0 && (
          <p className="small-text muted">
            이름을 확인할 얼굴 {photo.unknown_faces}명
          </p>
        )}
      </div>
      <div className="info-section">
        <h5>태그</h5>
        <div className="tags">
          {photo.tags.length ? (
            photo.tags.map((t) => <span key={t}>#{t}</span>)
          ) : (
            <small className="muted">태그 없음</small>
          )}
        </div>
      </div>
      <div className="info-section">
        <h5>사진 용도</h5>
        <select
          aria-label="사진 용도"
          value={photo.purpose || "undecided"}
          onChange={(e) => update({ purpose: e.target.value })}
        >
          <option value="undecided">아직 정하지 않았어요</option>
          <option value="share">함께 공유</option>
          <option value="print">인화할 사진</option>
          <option value="keep">추억으로 보관</option>
          <option value="exclude">게시 제외</option>
        </select>
        {photo.purpose === "exclude" && (
          <small className="muted">
            분류용 표시예요. 앨범 멤버에게는 계속 보여요.
          </small>
        )}
      </div>
      <label className="info-section note-label">
        <h5>메모</h5>
        <textarea
          aria-label="사진 메모"
          placeholder="메모 입력"
          value={note}
          maxLength={4000}
          onChange={(e) => setNote(e.target.value)}
        />
      </label>
      {note !== (photo.note || "") && (
        <button
          className="button secondary full small"
          disabled={saving}
          onClick={() => update({ note })}
        >
          메모 저장
        </button>
      )}
      <div className="photo-analysis-note">
        {photo.analysis_mode === "fixture" ||
        photo.analysis_provider === "fixture" ? (
          <>
            <Sparkles size={13} /> 샘플 분석 결과
          </>
        ) : (
          <>
            <CheckCheck size={13} />{" "}
            {photo.analysis_status === "completed"
              ? "인물 분류 완료"
              : "분석 상태 확인"}
          </>
        )}
      </div>
      {photo.analysis_error && (
        <p className="small-text text-error">
          {photo.analysis_error.replace(/^[A-Z_]+:\s*/, "")}
        </p>
      )}
      {photo.analysis_status === "failed" && (
        <button
          className="button secondary full small"
          onClick={async () => {
            try {
              await post(`/photos/${photo.id}/reanalyze`);
              client.invalidateQueries({ queryKey: ["photos"] });
              notify("다시 분석을 요청했어요.");
            } catch (e) {
              notify((e as Error).message);
            }
          }}
        >
          분석 다시 시도
        </button>
      )}
      <button className="button primary full" onClick={onEdit}>
        <SlidersHorizontal size={16} />
        보정하고 함께 고르기
      </button>
      <button
        className="button subtle full small"
        onClick={() => downloadPhoto(photo.id)}
      >
        <ArrowDownToLine size={15} />
        원본 다운로드
      </button>
    </aside>
  );
}
