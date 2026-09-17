import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Images, Users } from "lucide-react";
import { api } from "../../api";
import type { Album, Board as BoardResponse } from "../../types";
import { ErrorBox, Spinner } from "../../ui";

export function Board({
  album,
  onOpen,
}: {
  album: Album;
  onOpen: (id: string) => void;
}) {
  const board = useQuery({
    queryKey: ["board", album.id],
    queryFn: () => api<BoardResponse>(`/albums/${album.id}/board`),
    refetchInterval: 5000,
  });
  const columns = [
    ["selection", "사진 선택"],
    ["editing", "보정 중"],
    ["review", "확인 대기"],
    ["final", "최종본"],
  ] as const;
  return (
    <section className="extension-view">
      <div className="section-heading">
        <div>
          <h2>함께 고르기</h2>
        </div>
        <span className="badge">
          <Users size={14} />
          {album.member_count}명과 함께
        </span>
      </div>
      {board.isPending ? (
        <Spinner />
      ) : board.error ? (
        <ErrorBox error={board.error} retry={() => board.refetch()} />
      ) : (
        <div className="board-columns">
          {columns.map(([key, title]) => (
            <section key={key} className={`board-column ${key}`}>
              <h3>
                <i />
                {title}
                <span>{board.data?.[key]?.length || 0}</span>
              </h3>
              {board.data?.[key]?.map((p) => (
                <button
                  key={p.id}
                  className="board-card"
                  onClick={() => onOpen(p.id)}
                >
                  <img src={p.thumbnail_url} alt={p.filename} />
                  <span>
                    <strong>{p.filename}</strong>
                    <small>
                      {p.people.map((v) => v.name).join(" · ") || "인물 미지정"}
                    </small>
                    <ArrowRight size={15} />
                  </span>
                </button>
              ))}
              {!board.data?.[key]?.length && (
                <div className="board-empty">
                  <Images size={24} />
                  <span>아직 사진이 없어요</span>
                </div>
              )}
            </section>
          ))}
        </div>
      )}
    </section>
  );
}
