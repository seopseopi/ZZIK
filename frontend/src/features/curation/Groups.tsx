import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { api, patch, post } from "../../api";
import type { Album, FaceGroups } from "../../types";
import { Empty, ErrorBox, Spinner } from "../../ui";

export function Groups({ album }: { album: Album }) {
  const client = useQueryClient();
  const [selected, setSelected] = useState<string[]>([]);
  const data = useQuery({
    queryKey: ["groups", album.id],
    queryFn: () =>
      api<FaceGroups>(
        `/albums/${album.id}/face-groups`,
      ),
  });
  const action = useMutation({
    mutationFn: (task: () => Promise<unknown>) => task(),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["groups", album.id] });
      client.invalidateQueries({ queryKey: ["photos"] });
      setSelected([]);
    },
  });
  const groups = data.data?.items || [];
  return (
    <section className="extension-view">
      <div className="section-heading">
        <div>
          <h2>인물 그룹</h2>
          <p className="muted">
            같은 앨범 안의 얼굴을 묶고, 이름을 직접 확인해 주세요.
          </p>
        </div>
        <button
          className="button primary"
          disabled={action.isPending}
          onClick={() =>
            action.mutate(() => post(`/albums/${album.id}/face-groups/analyze`))
          }
        >
          <Sparkles size={16} />
          인물 그룹 분석
        </button>
      </div>
      {data.data?.message && (
        <div className="panel-note">{data.data.message}</div>
      )}
      {action.error && <ErrorBox error={action.error} />}{" "}
      {data.isPending ? (
        <Spinner />
      ) : data.error ? (
        <ErrorBox error={data.error} />
      ) : groups.length ? (
        <>
          <div className="group-grid">
            {groups.map((g) => (
              <div className="face-group" key={g.id}>
                <label>
                  <input
                    type="checkbox"
                    checked={selected.includes(g.id)}
                    onChange={(e) =>
                      setSelected(
                        e.target.checked
                          ? [...selected, g.id]
                          : selected.filter((id) => id !== g.id),
                      )
                    }
                  />
                  {g.name || "이름 없는 인물"}
                </label>
                <form
                  className="group-name-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    const name = String(
                      new FormData(e.currentTarget).get("name") || "",
                    ).trim();
                    if (name)
                      action.mutate(() =>
                        patch(`/face-groups/${g.id}`, { name }),
                      );
                  }}
                >
                  <label>
                    인물 이름
                    <input
                      name="name"
                      aria-label={`${g.name || "그룹"} 인물 이름`}
                      defaultValue={g.name || ""}
                      required
                      maxLength={80}
                    />
                  </label>
                  <button
                    className="button secondary small"
                    disabled={action.isPending}
                  >
                    이름 저장
                  </button>
                </form>
                <div className="group-faces">
                  {g.faces?.map((f) => (
                    <div key={f.id}>
                      {f.thumbnail_url && (
                        <img src={f.thumbnail_url} alt="그룹의 얼굴" />
                      )}
                      <button
                        className="text-button"
                        onClick={() =>
                          action.mutate(() =>
                            post(`/face-groups/${g.id}/split`, {
                              face_ids: [f.id],
                            }),
                          )
                        }
                      >
                        분리
                      </button>
                    </div>
                  ))}
                </div>
                <label>
                  등록 인물 연결
                  <select
                    value={g.person_id || ""}
                    onChange={(e) =>
                      action.mutate(() =>
                        patch(`/face-groups/${g.id}`, {
                          person_id: e.target.value || null,
                        }),
                      )
                    }
                  >
                    <option value="">연결할 인물 선택</option>
                    {album.people.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            ))}
          </div>
          {selected.length >= 2 && (
            <button
              className="button secondary"
              disabled={action.isPending}
              onClick={() =>
                action.mutate(() =>
                  post("/face-groups/merge", { group_ids: selected }),
                )
              }
            >
              선택한 그룹 합치기
            </button>
          )}
        </>
      ) : (
        <Empty
          title="아직 인물 그룹이 없어요"
          description="등록 없는 자동 그룹은 실제 얼굴 분석 연결이 필요해요. 기준 사진 등록과 샘플 인물 필터는 지금 사용할 수 있어요."
        />
      )}
    </section>
  );
}
