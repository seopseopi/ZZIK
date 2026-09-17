import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  Check,
  ChevronLeft,
  Clock3,
  FolderHeart,
  Image,
  Images,
  LogOut,
  Plus,
  Settings2,
  Users,
} from "lucide-react";
import { api, ApiError, dateLabel, post } from "./api";
import type { Album, List, Session, Config, Notice } from "./types";
import { Avatar, Empty, ErrorBox, Logo, Modal, Spinner } from "./ui";
import Upload from "./Upload";
import People from "./People";
import Editor from "./Editor";
import AlbumSettings from "./AlbumSettings";
import AnalysisStatus from "./AnalysisStatus";
import { Login } from "./features/auth/Login";
import { AlbumHome } from "./features/albums/AlbumHome";
import { AlbumForm } from "./features/albums/AlbumForms";
import { JoinForm } from "./features/albums/AlbumForms";
import { Invite } from "./features/albums/AlbumForms";
import { SearchField } from "./features/library/SearchField";
import { Library } from "./features/library/Library";
import { Board } from "./features/collaboration/Board";
import { Recommendations } from "./features/curation/Recommendations";
import { Groups } from "./features/curation/Groups";
import type { View } from "./navigation";

import "./styles.css";

const navItems: { id: View; label: string; icon: typeof Images }[] = [
  { id: "albums", label: "전체 앨범", icon: FolderHeart },
  { id: "all", label: "모든 사진", icon: Images },
  { id: "mine", label: "내 사진", icon: Image },
  { id: "board", label: "함께 고르기", icon: Users },
  { id: "recent", label: "최근 업로드", icon: Clock3 },
];
export default function App() {
  const client = useQueryClient();
  const session = useQuery({
    queryKey: ["session"],
    queryFn: () => api<Session>("/auth/me"),
    retry: false,
  });
  const config = useQuery({
    queryKey: ["config"],
    queryFn: () => api<Config>("/config"),
  });
  const [albumId, setAlbumId] = useState<string>(
    () => localStorage.getItem("moacut-album") || "",
  );
  const [view, setView] = useState<View>(() =>
    window.matchMedia("(max-width:700px)").matches ? "albums" : "all",
  );
  const [photoQuery, setPhotoQuery] = useState("");
  const [modal, setModal] = useState<
    | "create"
    | "join"
    | "upload"
    | "people"
    | "invite"
    | "notifications"
    | "settings"
    | "analysis"
    | null
  >(null);
  const [editor, setEditor] = useState<string | null>(null);
  const [lastDeletedPhotoId, setLastDeletedPhotoId] = useState<string | null>(
    null,
  );
  const [toast, setToast] = useState("");
  const albums = useQuery({
    queryKey: ["albums"],
    queryFn: () => api<List<Album>>("/albums"),
    enabled: !!session.data,
  });
  const album = useQuery({
    queryKey: ["album", albumId],
    queryFn: () => api<Album>(`/albums/${albumId}`),
    enabled: !!session.data && !!albumId,
  });
  const notices = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api<{ items: Notice[]; total: number }>("/notifications"),
    enabled: !!session.data,
    refetchInterval: 20000,
  });
  useEffect(() => {
    if (albums.data && !albums.data.items.some((a) => a.id === albumId)) {
      setAlbumId(albums.data.items[0]?.id || "");
      if (!albums.data.items.length) setView("albums");
    }
  }, [albums.data, albumId]);
  useEffect(() => {
    if (albumId) localStorage.setItem("moacut-album", albumId);
  }, [albumId]);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 4000);
    return () => clearTimeout(timer);
  }, [toast]);
  function openAlbum(id: string, next: View = "all") {
    setPhotoQuery("");
    setAlbumId(id);
    setView(next);
  }
  function acceptAlbum(created: Album) {
    client.setQueryData<List<Album>>(["albums"], (old) => ({
      items: [
        created,
        ...(old?.items || []).filter((a) => a.id !== created.id),
      ],
      total:
        (old?.total || 0) +
        (old?.items.some((a) => a.id === created.id) ? 0 : 1),
      page: 1,
      page_size: 100,
    }));
    setModal(null);
    openAlbum(created.id);
    client.invalidateQueries({ queryKey: ["albums"] });
  }
  function leaveAlbum(id: string) {
    setModal(null);
    setEditor(null);
    setView("albums");
    setAlbumId("");
    localStorage.removeItem("moacut-album");
    client.setQueryData<List<Album>>(["albums"], (old) =>
      old
        ? {
            ...old,
            items: old.items.filter((a) => a.id !== id),
            total: Math.max(0, old.total - 1),
          }
        : old,
    );
    client.removeQueries({ queryKey: ["album", id] });
    client.removeQueries({ queryKey: ["photos", id] });
    client.removeQueries({ queryKey: ["board", id] });
    client.removeQueries({ queryKey: ["analysis-status", id] });
    client.invalidateQueries({ queryKey: ["albums"] });
    client.invalidateQueries({ queryKey: ["notifications"] });
    setToast("앨범 목록으로 돌아왔어요.");
  }
  async function logout() {
    try {
      await post("/auth/logout");
      client.clear();
      setAlbumId("");
      localStorage.removeItem("moacut-album");
      session.refetch();
    } catch (e) {
      setToast((e as Error).message);
    }
  }
  if (session.isPending)
    return (
      <div className="boot">
        <Logo />
        <Spinner />
      </div>
    );
  if (
    session.error &&
    (!(session.error instanceof ApiError) || session.error.status !== 401)
  )
    return (
      <div className="boot">
        <Logo />
        <ErrorBox error={session.error} retry={() => session.refetch()} />
      </div>
    );
  if (!session.data)
    return (
      <Login
        demoEnabled={!!config.data?.demo_enabled}
        onLogin={() => client.invalidateQueries({ queryKey: ["session"] })}
      />
    );
  const user = session.data.user;
  const current = album.data;
  return (
    <div className={`app-shell view-${view}`}>
      <aside className="sidebar">
        <a
          className="brand-link"
          href="#albums"
          onClick={(e) => {
            e.preventDefault();
            setView("albums");
          }}
          aria-label="찍 전체 앨범"
        >
          <Logo />
        </a>
        <nav aria-label="주 메뉴">
          {navItems.map((n) => (
            <button
              key={n.id}
              className={`nav-item ${view === n.id ? "active" : ""}`}
              onClick={() => setView(n.id)}
            >
              <n.icon size={19} />
              {n.label}
              {n.id === "all" && current && (
                <span className="nav-count">{current.photo_count}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-section-title">
          <span>여행 앨범</span>
          <button
            className="icon-button"
            onClick={() => setModal("create")}
            aria-label="새 앨범 만들기"
          >
            <Plus size={17} />
          </button>
        </div>
        <div className="album-nav">
          {albums.data?.items.map((a) => (
            <button
              key={a.id}
              className={albumId === a.id && view !== "albums" ? "active" : ""}
              onClick={() => openAlbum(a.id)}
            >
              {a.cover_url ? (
                <img src={a.cover_url} alt="" />
              ) : (
                <span className="mini-cover">
                  <Images size={18} />
                </span>
              )}
              <span>
                <strong>{a.name}</strong>
                <small>사진 {a.photo_count}장</small>
              </span>
            </button>
          ))}
        </div>
        <button className="join-link" onClick={() => setModal("join")}>
          <Plus size={15} /> 초대코드로 참여하기
        </button>
        <div className="sidebar-bottom">
          <div className="account">
            <Avatar
              name={user.name}
              url={
                current?.people.find((p) => p.user_id === user.id)
                  ?.reference_url
              }
              size={30}
            />
            <strong>{user.name}</strong>
            <button
              className="icon-button notification-button"
              onClick={() => setModal("notifications")}
              aria-label="알림"
            >
              <Bell size={17} />
              {notices.data?.items.some((n) => !n.read) && <i />}
            </button>
            <button
              className="icon-button"
              aria-label="로그아웃"
              onClick={logout}
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <main className="workspace">
        {view === "albums" && (
          <header className="topbar">
            <div className="mobile-brand">
              <Logo />
            </div>
            <span className="desktop-page-name">전체 앨범</span>
            <div className="topbar-right">
              <button
                className="icon-button notification-button"
                onClick={() => setModal("notifications")}
                aria-label="알림"
              >
                <Bell size={20} />
                {notices.data?.items.some((n) => !n.read) && <i />}
              </button>
              <button
                className="icon-button"
                onClick={logout}
                aria-label="로그아웃"
              >
                <LogOut size={19} />
              </button>
            </div>
          </header>
        )}
        {albums.error ? (
          <ErrorBox error={albums.error} retry={() => albums.refetch()} />
        ) : albums.isPending ? (
          <Spinner label="앨범 불러오는 중" />
        ) : view === "albums" ? (
          <AlbumHome
            albums={albums.data?.items || []}
            user={user}
            onOpen={openAlbum}
            onCreate={() => setModal("create")}
            onJoin={() => setModal("join")}
          />
        ) : album.isPending ? (
          <Spinner />
        ) : album.error ? (
          <ErrorBox error={album.error} retry={() => album.refetch()} />
        ) : current ? (
          <>
            <header className="album-header">
              <div className="album-identity">
                <button
                  className="mobile-back icon-button"
                  aria-label="앨범 목록으로"
                  onClick={() => setView("albums")}
                >
                  <ChevronLeft size={25} />
                </button>
                <div>
                  <div className="breadcrumb">
                    <button onClick={() => setView("albums")}>내 앨범</button>
                    <span>/</span>
                    <span>{current.name}</span>
                  </div>
                  <div className="album-title-row">
                    <h1>{current.name}</h1>
                    <span className="header-meta">
                      사진 {current.photo_count}장 · 멤버 {current.member_count}
                      명
                    </span>
                  </div>
                </div>
              </div>
              <div className="header-actions">
                {!["board", "recommendations", "groups"].includes(view) && (
                  <SearchField
                    value={photoQuery}
                    onChange={setPhotoQuery}
                    className="header-search"
                  />
                )}
                <button
                  className="button primary"
                  onClick={() => setModal("upload")}
                  aria-label="사진 올리기"
                >
                  <Plus size={18} />
                  <span>사진 올리기</span>
                </button>
                <button
                  className="button secondary invite-trigger"
                  onClick={() => setModal("invite")}
                  aria-label="초대하기"
                >
                  <Users size={17} />
                  <span>초대하기</span>
                </button>
                <button
                  className="icon-button album-settings-trigger"
                  aria-label="앨범 설정"
                  onClick={() => setModal("settings")}
                >
                  <Settings2 size={19} />
                </button>
              </div>
              <div className="album-members">
                <button
                  className="member-stack"
                  aria-label="멤버와 인물 관리"
                  onClick={() => setModal("people")}
                >
                  {current.members.slice(0, 4).map((m) => (
                    <Avatar
                      key={m.id}
                      name={m.name}
                      url={
                        current.people.find((p) => p.user_id === m.id)
                          ?.reference_url
                      }
                      size={34}
                    />
                  ))}
                </button>
                <button
                  className="icon-button add-member"
                  aria-label="인물 관리 열기"
                  onClick={() => setModal("people")}
                >
                  <Plus size={18} />
                </button>
              </div>
            </header>
            {view === "board" ? (
              <Board album={current} onOpen={setEditor} />
            ) : view === "recommendations" ? (
              <Recommendations album={current} onOpen={setEditor} />
            ) : view === "groups" ? (
              <Groups album={current} />
            ) : (
              <Library
                key={`${current.id}-${view}`}
                query={photoQuery}
                onQuery={setPhotoQuery}
                sample={config.data?.face_provider === "fixture"}
                album={current}
                user={user}
                view={view}
                onUpload={() => setModal("upload")}
                onPeople={() => setModal("people")}
                onEdit={setEditor}
                lastDeletedPhotoId={lastDeletedPhotoId}
                onAnalysis={() => setModal("analysis")}
                onView={setView}
                notify={setToast}
              />
            )}
          </>
        ) : (
          <Empty
            title="앨범이 없습니다"
            description="새 앨범을 만들거나 초대코드로 참여하세요."
            action={
              <button
                className="button primary"
                onClick={() => setModal("create")}
              >
                앨범 만들기
              </button>
            }
          />
        )}
      </main>
      <nav className="mobile-nav" aria-label="모바일 메뉴">
        {navItems
          .filter((n) => ["albums", "mine", "board"].includes(n.id))
          .map((n) => (
            <button
              key={n.id}
              className={view === n.id ? "active" : ""}
              onClick={() => setView(n.id)}
            >
              <n.icon size={22} />
              {n.label}
            </button>
          ))}
      </nav>
      {modal === "create" && (
        <AlbumForm onClose={() => setModal(null)} onCreated={acceptAlbum} />
      )}
      {modal === "join" && (
        <JoinForm onClose={() => setModal(null)} onJoined={acceptAlbum} />
      )}
      {modal === "upload" && current && (
        <Upload albumId={current.id} onClose={() => setModal(null)} />
      )}
      {modal === "people" && current && (
        <People album={current} user={user} onClose={() => setModal(null)} />
      )}
      {modal === "invite" && current && (
        <Invite album={current} onClose={() => setModal(null)} />
      )}
      {modal === "settings" && current && (
        <AlbumSettings
          key={current.id}
          album={current}
          user={user}
          onClose={() => setModal(null)}
          onExit={leaveAlbum}
        />
      )}
      {modal === "analysis" && current && (
        <AnalysisStatus
          album={current}
          onClose={() => setModal(null)}
          onPhoto={(id) => {
            setModal(null);
            setEditor(id);
          }}
        />
      )}
      {modal === "notifications" && (
        <Modal title="알림" onClose={() => setModal(null)}>
          {notices.error ? (
            <ErrorBox error={notices.error} />
          ) : notices.data?.items.length ? (
            <div className="notice-list">
              {notices.data.items.map((n) => (
                <button
                  key={n.id}
                  className={n.read ? "" : "unread"}
                  onClick={async () => {
                    try {
                      await post(`/notifications/${n.id}/read`);
                      client.invalidateQueries({ queryKey: ["notifications"] });
                      openAlbum(n.album_id);
                      setModal(null);
                      if (n.photo_id) setEditor(n.photo_id);
                    } catch (e) {
                      setToast((e as Error).message);
                    }
                  }}
                >
                  <Bell size={18} />
                  <span>
                    {n.message}
                    <small>{dateLabel(n.created_at)}</small>
                  </span>
                  {!n.read && <i />}
                </button>
              ))}
            </div>
          ) : (
            <Empty
              title="아직 새로운 소식이 없어요"
              description="보정본과 확인 요청 소식을 여기에서 볼 수 있어요."
            />
          )}
        </Modal>
      )}
      {editor && current && (
        <Editor
          key={editor}
          photoId={editor}
          album={current}
          user={user}
          onClose={() => setEditor(null)}
          onDeleted={(id) => {
            setLastDeletedPhotoId(id);
            setToast("사진과 관련 기록을 삭제했어요.");
          }}
          onChanged={() => {
            client.invalidateQueries({ queryKey: ["photos"] });
            client.invalidateQueries({ queryKey: ["board"] });
            client.invalidateQueries({ queryKey: ["album"] });
          }}
        />
      )}
      {toast && (
        <div className="toast" role="status">
          <Check size={17} />
          {toast}
        </div>
      )}
    </div>
  );
}
