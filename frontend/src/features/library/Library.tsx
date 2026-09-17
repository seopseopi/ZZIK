import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownToLine,
  ArrowRight,
  Check,
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Grid2X2,
  Plus,
  Settings2,
  SlidersHorizontal,
  Sparkles,
  Users,
} from "lucide-react";
import { api, isBrowserDemo, patch } from "../../api";
import type { Album, PhotoList, User } from "../../types";
import { Avatar, Empty, ErrorBox, Spinner } from "../../ui";
import { SearchField } from "../library/SearchField";
import { PhotoInfo } from "../library/PhotoInfo";
import type { View } from "../../navigation";

export function Library({
  album,
  user,
  view,
  onUpload,
  onPeople,
  onEdit,
  onAnalysis,
  onView,
  notify,
  lastDeletedPhotoId,
  query,
  onQuery,
  sample,
}: {
  query: string;
  onQuery: (value: string) => void;
  sample: boolean;
  album: Album;
  user: User;
  view: View;
  onUpload: () => void;
  onPeople: () => void;
  onEdit: (id: string) => void;
  onAnalysis: () => void;
  lastDeletedPhotoId: string | null;
  onView: (view: View) => void;
  notify: (text: string) => void;
}) {
  const client = useQueryClient();
  const [people, setPeople] = useState<string[]>([]);
  const [match, setMatch] = useState("all");
  const [filter, setFilter] = useState("all");
  const [tag, setTag] = useState("");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState(view === "recent" ? "newest" : "oldest");
  const [date, setDate] = useState("");
  const [page, setPage] = useState(1);
  const [compact, setCompact] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [focused, setFocused] = useState<string | null>(null);
  const [detailHidden, setDetailHidden] = useState(
    () => window.matchMedia("(max-width: 960px)").matches,
  );
  useEffect(() => {
    if (!lastDeletedPhotoId) return;
    setSelected((old) => {
      const next = new Set(old);
      next.delete(lastDeletedPhotoId);
      return next;
    });
    setFocused((old) => (old === lastDeletedPhotoId ? null : old));
  }, [lastDeletedPhotoId]);
  useEffect(() => {
    const timer = setTimeout(() => setSearch(query), 350);
    return () => clearTimeout(timer);
  }, [query]);
  useEffect(() => {
    setPage(1);
  }, [people, match, filter, tag, search, sort, date]);
  const params = new URLSearchParams({
    page: String(page),
    page_size: "24",
    filter,
    mine: String(view === "mine"),
    people: people.join(","),
    match,
    tag,
    q: search,
    sort,
    date,
  });
  const photos = useQuery({
    queryKey: ["photos", album.id, params.toString(), view],
    queryFn: () => api<PhotoList>(`/albums/${album.id}/photos?${params}`),
    refetchInterval: 4000,
  });
  const items = photos.data?.items || [];
  const active = items.find((p) => p.id === focused) || items[0];
  const personTitle =
    people.length === 1
      ? `${album.people.find((p) => p.id === people[0])?.name}가 나온 사진`
      : people.length > 1
        ? "함께 담긴 사진"
        : view === "mine"
          ? `${user.name}님이 나온 사진`
          : view === "recent"
            ? "최근 업로드"
            : "모든 사진";
  function toggle(id: string) {
    setSelected((old) => {
      const next = new Set(old);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }
  async function saveSelection() {
    try {
      await Promise.all(
        [...selected].map((id) => patch(`/photos/${id}`, { selected: true })),
      );
      client.invalidateQueries({ queryKey: ["photos"] });
      client.invalidateQueries({ queryKey: ["board"] });
      setSelected(new Set());
      onView("board");
      notify("함께 고를 사진을 모아두었어요.");
    } catch (e) {
      notify((e as Error).message);
    }
  }
  const total = photos.data?.total || 0;
  const stats = photos.data?.stats;
  return (
    <div
      className={`library-layout ${detailHidden || !active ? "without-detail" : ""}`}
    >
      <section className="library-main">
        <div className="people-strip">
          <button
            className={`person-filter all-people ${!people.length && view !== "mine" ? "active" : ""}`}
            onClick={() => setPeople([])}
          >
            <span className="all-avatar">
              <Users size={26} />
            </span>
            <span>전체</span>
          </button>
          {album.people.map((p) => (
            <button
              key={p.id}
              className={`person-filter ${people.includes(p.id) || (!people.length && view === "mine" && p.user_id === user.id) ? "active" : ""}`}
              onClick={() =>
                setPeople((old) =>
                  old.includes(p.id)
                    ? old.filter((id) => id !== p.id)
                    : advanced
                      ? [...old, p.id]
                      : [p.id],
                )
              }
            >
              <Avatar name={p.name} url={p.reference_url} size={58} />
              <span>{p.name}</span>
              {p.user_id === user.id && <i>나</i>}
            </button>
          ))}
          <button className="person-filter add-person" onClick={onPeople}>
            <span className="all-avatar">
              <Plus size={22} />
            </span>
            <span>인물 관리</span>
          </button>
          <button
            className="analysis-indicator as-button"
            aria-label="사진 정리 현황"
            onClick={onAnalysis}
          >
            {stats && stats.pending + stats.processing > 0 ? (
              <>
                <i className="working" /> {stats.pending + stats.processing}장
                정리 중
              </>
            ) : stats?.failed ? (
              <>
                <i className="failed" /> {stats.failed}장 확인 필요
              </>
            ) : (
              <>
                <i /> 사진 정리 완료
              </>
            )}
            <small>{sample ? "샘플 분석" : "인물 분석"}</small>
          </button>
        </div>
        <div className="library-heading">
          <div>
            <h2>
              {personTitle}
              <span>{total}장</span>
            </h2>
          </div>
          <div className="library-tools">
            <button
              className="icon-button"
              aria-label="추천 후보"
              onClick={() => onView("recommendations")}
            >
              <Sparkles size={17} />
            </button>
            <button
              className="icon-button compact-analysis"
              aria-label="사진 정리 현황"
              onClick={onAnalysis}
            >
              <Clock3 size={18} />
              {sample && <small>샘플</small>}
            </button>
            <button
              className="icon-button"
              aria-label="상세 검색 조건"
              aria-expanded={advanced}
              onClick={() => setAdvanced(!advanced)}
            >
              <SlidersHorizontal size={19} />
            </button>
          </div>
        </div>
        <div className="filters">
          <div className="filter-pills">
            {[
              ["all", "전체"],
              ["solo", "혼자"],
              ["group", "함께"],
            ].map(([id, label]) => (
              <button
                key={id}
                className={filter === id ? "active" : ""}
                onClick={() => setFilter(id)}
              >
                {label}
              </button>
            ))}
            <span className="filter-divider" />
            {["바다", "카페", "음식"].map((t) => (
              <button
                className={tag === t ? "tag-filter tag-active" : "tag-filter"}
                key={t}
                onClick={() => setTag(tag === t ? "" : t)}
              >
                {t}
              </button>
            ))}
          </div>
          <div className="sort-controls">
            <select
              aria-label="사진 정렬"
              value={sort}
              onChange={(e) => setSort(e.target.value)}
            >
              <option value="newest">최신순</option>
              <option value="oldest">오래된순</option>
              <option value="captured">촬영일순</option>
            </select>
            <button
              className={`icon-button grid-toggle ${compact ? "active" : ""}`}
              aria-label="사진 격자 크기 변경"
              onClick={() => setCompact(!compact)}
            >
              <Grid2X2 size={18} />
            </button>
          </div>
        </div>

        {advanced && (
          <div className="advanced-filters">
            <SearchField
              value={query}
              onChange={onQuery}
              className="mobile-search"
            />
            <label className="mobile-filter">
              정렬
              <select
                aria-label="사진 정렬"
                value={sort}
                onChange={(e) => setSort(e.target.value)}
              >
                <option value="newest">최신순</option>
                <option value="oldest">오래된순</option>
                <option value="captured">촬영일순</option>
              </select>
            </label>
            <label className="mobile-filter">
              태그
              <input
                aria-label="태그 필터"
                placeholder="바다, 카페 등"
                value={tag}
                onChange={(e) => setTag(e.target.value)}
              />
            </label>
            <label>
              분류
              <select
                aria-label="사진 분류"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              >
                <option value="all">모든 사진</option>
                <option value="solo">1인 사진</option>
                <option value="group">2인 이상</option>
                <option value="no_faces">얼굴 미검출</option>
                <option value="review">확인 필요</option>
                <option value="final">최종본</option>
              </select>
            </label>
            <label>
              인물 조합
              <select value={match} onChange={(e) => setMatch(e.target.value)}>
                <option value="all">선택한 사람 모두 포함</option>
                <option value="any">선택한 사람 중 누구든</option>
              </select>
            </label>
            <label>
              촬영일
              <input
                aria-label="촬영일"
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
            </label>
            <button className="text-button" onClick={() => onView("groups")}>
              자동 인물 그룹
              <ArrowRight size={14} />
            </button>
            <small>이름·태그·촬영일로 검색합니다.</small>
          </div>
        )}
        {photos.isPending ? (
          <Spinner />
        ) : photos.error ? (
          <ErrorBox error={photos.error} retry={() => photos.refetch()} />
        ) : items.length ? (
          <div className={`photo-grid ${compact ? "compact" : ""}`}>
            {items.map((photo, index) => (
              <article
                key={photo.id}
                className={`photo-card ${selected.has(photo.id) ? "selected" : ""} ${focused === photo.id ? "focused" : ""}`}
              >
                <button
                  className="photo-open"
                  aria-label={`${photo.filename} 사진 정보`}
                  onClick={() => {
                    if (window.matchMedia("(max-width:700px)").matches) {
                      onEdit(photo.id);
                      return;
                    }
                    setFocused(photo.id);
                    setDetailHidden(false);
                  }}
                  onDoubleClick={() => onEdit(photo.id)}
                >
                  <img
                    src={photo.thumbnail_url}
                    alt={
                      photo.people.length
                        ? `${photo.people.map((p) => p.name).join(", ")} · ${photo.tags.join(", ")}`
                        : photo.filename
                    }
                    loading={index < 8 ? "eager" : "lazy"}
                  />
                </button>
                <label className="photo-select">
                  <input
                    type="checkbox"
                    aria-label={`${photo.filename} 선택`}
                    checked={selected.has(photo.id)}
                    onChange={() => toggle(photo.id)}
                  />
                  <span>{selected.has(photo.id) && <Check size={13} />}</span>
                </label>
                <span className="photo-person-count">
                  <Users size={12} />
                  {photo.analysis_status === "completed"
                    ? `${photo.face_count}명`
                    : photo.analysis_status === "failed"
                      ? "확인 필요"
                      : "분석 중"}
                </span>
                {photo.final_version_id && (
                  <span className="photo-status">
                    <CheckCheck size={12} />
                    최종본
                  </span>
                )}
                <button
                  className="photo-edit-shortcut"
                  aria-label={`${photo.filename} 보정하기`}
                  onClick={() => onEdit(photo.id)}
                >
                  <Settings2 size={14} />
                </button>
              </article>
            ))}
          </div>
        ) : (
          <Empty
            title="조건에 맞는 사진이 없어요"
            description="필터를 바꾸거나 사진을 추가하세요."
            action={
              <button className="button secondary" onClick={onUpload}>
                <Plus size={16} />
                사진 올리기
              </button>
            }
          />
        )}
        {total > 24 && (
          <div className="pagination">
            <button
              className="icon-button"
              aria-label="이전 페이지"
              disabled={page === 1}
              onClick={() => setPage(page - 1)}
            >
              <ChevronLeft size={18} />
            </button>
            <span>
              {page} / {Math.ceil(total / 24)}
            </span>
            <button
              className="icon-button"
              aria-label="다음 페이지"
              disabled={page * 24 >= total}
              onClick={() => setPage(page + 1)}
            >
              <ChevronRight size={18} />
            </button>
          </div>
        )}
        {items.length > 0 && (
          <div className="grid-footnote">
            <span>{total}장</span>
            <button
              className="text-button"
              onClick={() =>
                setSelected(
                  selected.size ? new Set() : new Set(items.map((p) => p.id)),
                )
              }
            >
              {selected.size ? "선택 해제" : "현재 페이지 모두 선택"}
            </button>
          </div>
        )}
      </section>
      {!detailHidden && active && (
        <PhotoInfo
          key={active.id}
          photo={active}
          album={album}
          onClose={() => setDetailHidden(true)}
          onEdit={() => onEdit(active.id)}
          notify={notify}
        />
      )}
      {!!selected.size && (
        <div className="selection-bar">
          <strong>
            {selected.size}장 <span>선택</span>
          </strong>
          <button
            className="text-button"
            onClick={() => setSelected(new Set())}
          >
            선택 해제
          </button>
          <span className="selection-divider" />
          <button className="button secondary" onClick={saveSelection}>
            <Users size={17} />
            함께 고르기
          </button>
          <a
            className="button primary"
            href={`/api/albums/${album.id}/download?photo_ids=${[...selected].join(",")}`}
            onClick={
              isBrowserDemo
                ? (e) => {
                    e.preventDefault();
                    void import("../../demo/images")
                      .then((module) => module.downloadDemoZip([...selected]))
                      .catch((error) => notify((error as Error).message));
                  }
                : undefined
            }
            download
          >
            <ArrowDownToLine size={17} />
            <span>원본 다운로드</span>
          </a>
        </div>
      )}
    </div>
  );
}
