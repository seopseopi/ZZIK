import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, RotateCcw, Trash2 } from 'lucide-react';
import { api, post, timeLabel } from './api';
import type { Album, Photo, PhotoList, User } from './types';
import { Empty, ErrorBox, Modal, Spinner } from './ui';

export function canManagePhoto(photo: Photo, album: Album, user: User) {
  return photo.uploader_id === user.id || album.members.some(member => member.id === user.id && member.role === 'owner');
}

export async function refreshPhotoLists(client: QueryClient) {
  await Promise.all(['photos', 'trash', 'albums', 'album', 'board', 'recommendations', 'notifications', 'groups', 'analysis-status']
    .map(key => client.invalidateQueries({queryKey: [key]})));
}

export function MoveToTrashButton({photo, album, user, onMoved, notify}: {
  photo: Photo; album: Album; user: User; onMoved: (id: string) => void; notify: (message: string) => void;
}) {
  const client = useQueryClient();
  const action = useMutation({
    mutationFn: () => post(`/photos/${photo.id}/trash`),
    onSuccess: async () => {
      onMoved(photo.id);
      await refreshPhotoLists(client);
      notify('사진을 휴지통으로 이동했어요. 휴지통에서 복원할 수 있어요.');
    },
    onError: error => notify(error.message),
  });
  if (!canManagePhoto(photo, album, user)) return null;
  return <button className="button subtle full small trash-move" disabled={action.isPending} onClick={() => action.mutate()}>
    <Trash2 size={15}/>{action.isPending ? '이동 중…' : '휴지통으로 이동'}
  </button>;
}

export default function Trash({album, user, notify}: {album: Album; user: User; notify: (message: string) => void}) {
  const client = useQueryClient();
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState('');
  const [preview, setPreview] = useState<Photo | null>(null);
  useEffect(() => { const timer = setTimeout(() => { setSearch(query); setPage(1); }, 350); return () => clearTimeout(timer); }, [query]);
  const params = new URLSearchParams({trashed: 'true', page: String(page), page_size: '24', q: search});
  const photos = useQuery({queryKey: ['trash', album.id, params.toString()], queryFn: () => api<PhotoList>(`/albums/${album.id}/photos?${params}`), refetchInterval: 5000});
  const pages = Math.max(1, Math.ceil((photos.data?.total || 0) / 24));
  useEffect(() => { if (photos.data && page > pages) setPage(pages); }, [photos.data, page, pages]);
  const restore = useMutation({
    mutationFn: (photo: Photo) => post(`/photos/${photo.id}/restore`),
    onSuccess: async () => { setPreview(null); await refreshPhotoLists(client); notify('사진을 원래 앨범으로 복원했어요.'); },
  });
  return <section className="extension-view trash-view">
    <div className="section-heading"><div><h2><Trash2 size={23}/>휴지통 <span className="trash-count">{photos.data?.total || 0}장</span></h2>
      <p className="muted">{album.name}에서 버린 사진이에요. 원본과 보정 기록은 보관되며, 사진을 올린 멤버와 앨범 소유자가 복원할 수 있어요.</p>
    </div></div>
    <label className="trash-search">휴지통 사진 검색<input type="search" aria-label="휴지통 사진 검색" value={query} onChange={event => setQuery(event.target.value)} placeholder="사진 이름, 사람, 태그 검색"/></label>
    {restore.error && <ErrorBox error={restore.error}/>}
    {photos.isPending ? <Spinner label="휴지통 불러오는 중"/> : photos.error ? <ErrorBox error={photos.error} retry={() => photos.refetch()}/> : photos.data.items.length ?
      <div className="trash-grid">{photos.data.items.map(photo => <article className="trash-card" key={photo.id}>
        <button className="trash-preview" aria-label={`${photo.filename} 크게 보기`} onClick={() => {setPreview(photo); restore.reset();}}><img src={photo.thumbnail_url} alt={photo.filename}/></button>
        <div className="trash-card-info"><strong title={photo.filename}>{photo.filename}</strong><small>{photo.trashed_at ? `${timeLabel(photo.trashed_at)} 이동` : '휴지통에 보관 중'}</small>
          {canManagePhoto(photo, album, user) && <button className="button secondary small" aria-label={`${photo.filename} 복원`} disabled={restore.isPending} onClick={() => restore.mutate(photo)}><RotateCcw size={15}/>{restore.isPending && restore.variables?.id === photo.id ? '복원 중…' : '복원'}</button>}
        </div>
      </article>)}</div> : <Empty title={search ? '검색한 사진이 없어요' : '휴지통이 비어 있어요'} description={search ? '다른 이름이나 태그로 검색해 보세요.' : '사진을 휴지통으로 이동하면 여기에서 확인하고 복원할 수 있어요.'}/>}
    {pages > 1 && <div className="pagination"><button className="icon-button" aria-label="이전 페이지" disabled={page === 1} onClick={() => setPage(page - 1)}><ChevronLeft size={18}/></button><span>{page} / {pages}</span><button className="icon-button" aria-label="다음 페이지" disabled={page >= pages} onClick={() => setPage(page + 1)}><ChevronRight size={18}/></button></div>}
    {preview && <Modal title={preview.filename} onClose={() => setPreview(null)}><img className="trash-full-image" src={preview.display_url} alt={preview.filename}/><p className="muted">휴지통에 보관 중인 사진이에요. 복원하면 보정과 함께 고르기를 계속할 수 있어요.</p></Modal>}
  </section>;
}
