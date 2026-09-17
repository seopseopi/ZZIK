import { useQuery } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { api } from "../../api";
import type { Album, Recommendations as RecommendationsResponse } from "../../types";
import { Empty, ErrorBox, Spinner } from "../../ui";

export function Recommendations({
  album,
  onOpen,
}: {
  album: Album;
  onOpen: (id: string) => void;
}) {
  const data = useQuery({
    queryKey: ["recommendations", album.id],
    queryFn: () =>
      api<RecommendationsResponse>(`/albums/${album.id}/recommendations`),
  });
  return (
    <section className="extension-view">
      <h2>
        <Sparkles size={23} />
        추천 후보
      </h2>
      <p className="muted">비슷한 사진의 선명도와 노출을 비교합니다.</p>
      {data.isPending ? (
        <Spinner />
      ) : data.error ? (
        <ErrorBox error={data.error} />
      ) : data.data?.groups.length ? (
        data.data.groups.map((group, i) => (
          <div className="recommendation-group" key={group.id}>
            <h3>함께 비교할 순간 {i + 1}</h3>
            <div className="recommendation-grid">
              {group.photos.map((p) => (
                <button key={p.id} onClick={() => onOpen(p.id)}>
                  <img src={p.thumbnail_url} alt={p.filename} />
                  <strong>{p.filename}</strong>
                  {group.recommended_ids.includes(p.id) && (
                    <span className="badge">
                      <Sparkles size={13} />
                      {group.reasons[p.id]?.join(" · ") || "비교 추천"}
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>
        ))
      ) : (
        <Empty
          title="아직 함께 비교할 사진이 없어요"
          description="촬영 시각과 이미지가 충분히 비슷한 사진이 모이면 추천 후보를 보여드려요."
        />
      )}
    </section>
  );
}
