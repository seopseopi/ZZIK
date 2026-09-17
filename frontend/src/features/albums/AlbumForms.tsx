import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ArrowRight, Check, Copy } from "lucide-react";
import { isBrowserDemo, post } from "../../api";
import type { Album } from "../../types";
import { ErrorBox, Modal } from "../../ui";

export function AlbumForm({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (album: Album) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const action = useMutation({
    mutationFn: () =>
      post<Album>("/albums", { name, description, timezone: "Asia/Seoul" }),
    onSuccess: onCreated,
  });
  return (
    <Modal title="새 앨범 만들기" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          action.mutate();
        }}
      >
        <label>
          앨범 이름
          <input
            required
            maxLength={120}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="예: 우리들의 제주 여행"
          />
        </label>
        <label>
          앨범 소개
          <textarea
            maxLength={2000}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="앨범 소개 (선택)"
          />
        </label>
        {action.error && <ErrorBox error={action.error} />}
        <button
          className="button primary full"
          disabled={action.isPending || !name.trim()}
        >
          앨범 만들기
          <ArrowRight size={16} />
        </button>
      </form>
    </Modal>
  );
}

export function JoinForm({
  onClose,
  onJoined,
}: {
  onClose: () => void;
  onJoined: (album: Album) => void;
}) {
  const [code, setCode] = useState("");
  const action = useMutation({
    mutationFn: () => post<Album>("/albums/join", { code: code.trim() }),
    onSuccess: onJoined,
  });
  return (
    <Modal title="초대코드로 참여하기" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          action.mutate();
        }}
      >
        <label>
          초대코드
          <input
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="초대코드 붙여넣기"
          />
        </label>
        {action.error && <ErrorBox error={action.error} />}
        <button
          className="button primary full"
          disabled={action.isPending || !code.trim()}
        >
          앨범 참여하기
        </button>
      </form>
    </Modal>
  );
}

export function Invite({
  album,
  onClose,
}: {
  album: Album;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  return (
    <Modal title="멤버 초대" onClose={onClose}>
      <h3 className="center">{album.name}</h3>
      <p className="center muted">
        {isBrowserDemo
          ? "체험 코드는 같은 브라우저에서 인물을 바꿔 사용할 수 있어요."
          : "로그인 후 ‘초대코드로 참여하기’에서 입력하세요."}
      </p>
      <div className="invite-code">
        <code>{album.invite_code}</code>
        <button
          className="icon-button"
          aria-label="초대코드 복사"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(album.invite_code);
              setCopied(true);
            } catch {
              setError(
                new Error(
                  "복사하지 못했어요. 위 코드를 직접 선택해 복사해 주세요.",
                ),
              );
            }
          }}
        >
          {copied ? <Check size={19} /> : <Copy size={19} />}
        </button>
      </div>
      {copied && (
        <p className="center text-green" role="status">
          초대코드를 복사했어요.
        </p>
      )}
      {error && <ErrorBox error={error} />}
    </Modal>
  );
}
