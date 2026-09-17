import { Images, Plus } from "lucide-react";
import type { Album, User } from "../../types";
import { Avatar, Empty } from "../../ui";

export function AlbumHome({
  albums,
  user,
  onOpen,
  onCreate,
  onJoin,
}: {
  albums: Album[];
  user: User;
  onOpen: (id: string) => void;
  onCreate: () => void;
  onJoin: () => void;
}) {
  return (
    <div className="album-home">
      <div className="home-heading">
        <h1>
          {user.name}님의 앨범 <span>{albums.length}</span>
        </h1>
        <div>
          <button className="button secondary" onClick={onJoin}>
            초대코드로 참여하기
          </button>
          <button className="button primary home-create" onClick={onCreate}>
            <Plus size={18} />
            <span>새 앨범 만들기</span>
          </button>
        </div>
      </div>
      <div className="album-cards">
        {albums.map((a) => (
          <button
            className="album-card"
            key={a.id}
            onClick={() => onOpen(a.id)}
          >
            {a.cover_url ? (
              <img src={a.cover_url} alt="" />
            ) : (
              <div className="album-placeholder">
                <Images size={48} />
              </div>
            )}
            <div className="album-card-gradient" />
            <div className="album-card-info">
              <h2>{a.name}</h2>
              <div className="album-card-bottom">
                <div className="member-stack">
                  {(a.members || []).slice(0, 4).map((m) => (
                    <Avatar
                      key={m.id}
                      name={m.name}
                      url={
                        a.people?.find((p) => p.user_id === m.id)?.reference_url
                      }
                      size={28}
                    />
                  ))}
                </div>
                <span>
                  {a.member_count}명 · {a.photo_count}장의 사진
                </span>
              </div>
            </div>
          </button>
        ))}
      </div>
      {!albums.length && (
        <Empty
          title="아직 앨범이 없습니다"
          description="새 앨범을 만들거나 초대코드로 참여하세요."
        />
      )}
      <button
        className="mobile-create-album"
        aria-label="새 앨범 만들기"
        onClick={onCreate}
      >
        <Plus size={30} />
      </button>
    </div>
  );
}
