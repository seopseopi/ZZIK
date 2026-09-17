import type { Album, Config, Person, Photo, PhotoDetail, Version } from '../types';
import { demoUsers, photoDefaults, initialState, now, readState, uid, updateState, versionStatus } from './store';
import type { DemoState } from './store';
import { dataUrl, imageFile, render } from './images';

type Body = { email?: string; user_id?: string | null; name?: string; description?: string; timezone?: string; code?: string; note?: string; purpose?: string; selected?: boolean; brightness?: number; saturation?: number; parent_id?: string; confirmed?: boolean; person_ids?: string[]; body?: string; kind?: string };
class DemoError extends Error { constructor(message: string, public status = 400) { super(message); } }
const requireValue = <T>(value: T | undefined, message: string): T => { if (!value) throw new DemoError(message, 404); return value; };
const json = (value: unknown) => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });
function stats(photos: Photo[]) { return { completed: photos.filter(p => p.analysis_status === 'completed').length, failed: photos.filter(p => p.analysis_status === 'failed').length, pending: 0, processing: 0 }; }
function albumView(state: DemoState, album: Album): Album {
  const photos = state.photos.filter(p => p.album_id === album.id);
  return { ...album, photo_count: photos.length, member_count: album.members.length, cover_url: photos.find(p => p.face_count > 2)?.thumbnail_url || photos[0]?.thumbnail_url || null };
}
function photoView(photo: Photo): PhotoDetail {
  return { ...photo, faces: photo.faces ?? [], versions: (photo.versions ?? []).map(versionStatus), board_status: photo.final_version_id ? 'final' : photo.versions?.some(v => v.review_requested) ? 'review' : photo.versions?.length ? 'editing' : photo.selected ? 'selection' : 'unselected' };
}
function invalidateReview(photo: Photo) {
  photo.final_version_id = null;
  photo.versions?.forEach(v => { v.is_final = false; if (v.review_requested) v.needs_review = true; versionStatus(v); });
}
function owner(album: Album, userId: string) { if (!album.members.some(m => m.id === userId && m.role === 'owner')) throw new DemoError('앨범 소유자만 변경할 수 있어요.', 403); }
function notify(state: DemoState, photo: Photo, message: string) { state.notices.unshift({id: uid(), message, photo_id: photo.id, album_id: photo.album_id, created_at: now(), read: false, kind: 'comment', version_id: null}); }
function settings(body: Body) {
  const brightness = body.brightness ?? 1, saturation = body.saturation ?? 1;
  if (!Number.isFinite(brightness) || brightness < .25 || brightness > 2 || !Number.isFinite(saturation) || saturation < 0 || saturation > 2) throw new DemoError('보정값의 범위를 확인해 주세요.');
  return { brightness, saturation };
}
async function route(state: DemoState, path: string, method: string, body: Body, form?: FormData): Promise<unknown> {
  const [pathname, search = ''] = path.split('?'), params = new URLSearchParams(search);
  const [, resource, id, action, child] = pathname.split('/');
  if (path === '/config') return {face_provider: 'fixture', storage_backend: 'browser-demo', demo_enabled: true, max_upload_bytes: 8 * 1024 * 1024, grouping_available: false} satisfies Config;
  if (path === '/demo/reset') { Object.assign(state, initialState()); return {ok: true}; }
  if (path === '/demo/switch' || path === '/auth/login') {
    const user = demoUsers.find(u => path === '/demo/switch' ? u.id === body.user_id : u.email === body.email);
    if (!user) throw new DemoError('체험 사이트에서는 상단의 샘플 인물을 선택해 주세요.');
    state.userId = user.id; return {user, csrf_token: 'browser-demo'};
  }
  if (path === '/auth/register') throw new DemoError('체험 사이트는 회원가입 없이 사용합니다. 상단에서 샘플 인물을 선택해 주세요.');
  if (path === '/auth/logout') { state.userId = null; return {ok: true}; }
  const user = demoUsers.find(u => u.id === state.userId);
  if (!user) throw new DemoError('체험할 인물을 선택해 주세요.', 401);
  if (path === '/auth/me') return {user, csrf_token: 'browser-demo'};
  if (resource === 'notifications') {
    if (method === 'POST') { const notice = state.notices.find(n => n.id === id); if (notice) notice.read = true; return {ok: true}; }
    return {items: state.notices, total: state.notices.length};
  }
  if (resource === 'albums') {
    if (id === 'join') {
      const album = requireValue(state.albums.find(a => a.invite_code === body.code?.trim()), '이 브라우저에 있는 체험용 초대코드를 입력해 주세요.');
      if (!album.members.some(m => m.id === user.id)) album.members.push({...user, role: 'member'});
      return albumView(state, album);
    }
    if (!id) {
      if (method === 'POST') {
        if (!body.name?.trim()) throw new DemoError('앨범 이름을 입력해 주세요.');
        const album: Album = { id: uid(), owner_id: user.id, cover_url: null, name: body.name.trim(), description: body.description || '', timezone: body.timezone || 'Asia/Seoul', invite_code: `ZZIK-${uid().slice(0, 8).toUpperCase()}`, created_at: now(), members: [{...user, role: 'owner'}], people: [], photo_count: 0, member_count: 1 };
        state.albums.unshift(album); return albumView(state, album);
      }
      const items = state.albums.filter(a => a.members.some(m => m.id === user.id)).map(a => albumView(state, a));
      return {items, total: items.length, page: 1, page_size: 100};
    }
    const album = requireValue(state.albums.find(a => a.id === id && a.members.some(m => m.id === user.id)), '앨범에 참여한 체험 인물을 선택해 주세요.');
    const photos = state.photos.filter(p => p.album_id === id);
    if (!action) {
      if (method === 'DELETE') { owner(album, user.id); state.albums = state.albums.filter(a => a.id !== id); state.photos = state.photos.filter(p => p.album_id !== id); state.notices = state.notices.filter(n => n.album_id !== id); return {ok: true}; }
      if (method === 'PATCH') { owner(album, user.id); if (!body.name?.trim()) throw new DemoError('앨범 이름을 입력해 주세요.'); Object.assign(album, {name: body.name.trim(), description: body.description, timezone: body.timezone}); }
      return albumView(state, album);
    }
    if (action === 'invite') { owner(album, user.id); album.invite_code = `ZZIK-${uid().slice(0, 8).toUpperCase()}`; return {invite_code: album.invite_code}; }
    if (action === 'members' && method === 'DELETE') {
      if (child !== user.id) owner(album, user.id);
      if (album.members.some(m => m.id === child && m.role === 'owner')) throw new DemoError('소유자는 앨범에서 나갈 수 없어요.');
      album.members = album.members.filter(m => m.id !== child);
      album.people.forEach(p => { if (p.user_id === child) p.user_id = null; });
      photos.forEach(p => { p.people.forEach(person => { if (person.user_id === child) person.user_id = null; }); invalidateReview(p); });
      return {ok: true};
    }
    if (action === 'people' && form) {
      const file = form.get('file'); if (!(file instanceof File)) throw new DemoError('인물 사진을 선택해 주세요.');
      const image = await imageFile(file);
      const person: Person = {id: uid(), user_id: null, proposed_user_id: null, link_status: 'unlinked', name: String(form.get('name') || '새 인물'), reference_url: image.url, source: 'manual'};
      const requestedId = String(form.get('user_id') || '');
      if (requestedId === user.id) person.user_id = user.id;
      else if (requestedId) person.proposed_user_id = requestedId;
      person.link_status = person.user_id ? 'linked' : person.proposed_user_id ? 'pending' : 'unlinked';
      album.people.push(person); return person;
    }
    if (action === 'photos' && method === 'POST' && form) {
      const file = form.get('file'); if (!(file instanceof File)) throw new DemoError('사진을 선택해 주세요.');
      const image = await imageFile(file);
      const photo: Photo = {...photoDefaults, id: uid(), album_id: id, uploader_id: user.id, filename: file.name, thumbnail_url: image.url, display_url: image.url, original_url: image.url, width: image.width, height: image.height, created_at: now(), analysis_status: 'failed', analysis_error: '체험 모드에서는 새 사진을 자동 분석하지 않아요. 사진 정보에서 인물을 직접 지정해 주세요.', analysis_provider: 'fixture', analysis_mode: 'fixture', face_count: 0, unknown_faces: 0, people: [], tags: [], selected: false, board_status: 'unselected', versions: []};
      state.photos.push(photo); return photo;
    }
    if (action === 'photos') {
      const people = (params.get('people') || '').split(',').filter(Boolean), filter = params.get('filter'), query = (params.get('q') || '').toLowerCase();
      let items = photos.filter(photo => {
        if (params.get('mine') === 'true' && !photo.people.some(p => p.user_id === user.id)) return false;
        if (people.length && !(params.get('match') === 'any' ? people.some(id => photo.people.some(p => p.id === id)) : people.every(id => photo.people.some(p => p.id === id)))) return false;
        if (filter === 'solo' && photo.face_count !== 1 || filter === 'group' && photo.face_count < 2 || filter === 'no_faces' && photo.face_count !== 0 || filter === 'review' && photo.analysis_status !== 'failed' || filter === 'final' && !photo.final_version_id) return false;
        if (params.get('tag') && !photo.tags.includes(params.get('tag')!)) return false;
        if (params.get('date') && !photo.captured_at?.startsWith(params.get('date')!)) return false;
        return !query || `${photo.filename} ${photo.people.map(p => p.name).join(' ')} ${photo.tags.join(' ')} ${photo.note || ''}`.toLowerCase().includes(query);
      });
      items = items.sort((a, b) => (params.get('sort') === 'newest' ? -1 : 1) * a.created_at.localeCompare(b.created_at));
      const page = Math.max(1, Number(params.get('page') || 1)), pageSize = 24;
      return {items: items.slice((page - 1) * pageSize, page * pageSize).map(photoView), total: items.length, page, page_size: pageSize, stats: stats(photos)};
    }
    if (action === 'board') return Object.fromEntries(['selection', 'editing', 'review', 'final'].map(key => [key, photos.map(photoView).filter(p => p.board_status === key)]));
    if (action === 'analysis-status') return {provider: 'fixture', mode: 'sample', total: photos.length, recorded_runs: 0, calls: 0, elapsed_ms: 0, stats: stats(photos), oldest_pending_at: null, failures: photos.filter(p => p.analysis_status === 'failed').map(p => ({photo_id: p.id, filename: p.filename, error: p.analysis_error}))};
    if (action === 'recommendations') return {groups: [], method: '체험에서는 자동 추천을 실행하지 않아요.'};
    if (action === 'face-groups' && method === 'GET') return {items: [], total: 0, available: false, mode: 'fixture', message: '체험 사이트는 자동 인물 그룹 분석을 실행하지 않습니다. 인물 필터와 직접 지정은 체험할 수 있어요.'};
    if (action === 'reanalyze-failed' || action === 'face-groups') throw new DemoError('실제 자동 분석은 서버와 AWS 연결이 필요해요. 체험에서는 인물을 직접 지정해 주세요.');
  }
  if (resource === 'photos') {
    const photo = requireValue(state.photos.find(p => p.id === id), '사진을 찾지 못했어요.');
    const album = requireValue(state.albums.find(a => a.id === photo.album_id && a.members.some(m => m.id === user.id)), '앨범 멤버를 선택해 주세요.');
    if (!action) {
      if (method === 'DELETE') { if (photo.uploader_id !== user.id) owner(album, user.id); state.photos = state.photos.filter(p => p.id !== id); state.notices = state.notices.filter(n => n.photo_id !== id); return {ok: true}; }
      if (method === 'PATCH') { for (const key of ['note', 'purpose', 'selected'] as const) if (body[key] !== undefined) Object.assign(photo, {[key]: body[key]}); }
      return photoView(photo);
    }
    if (action === 'people') {
      photo.people = album.people.filter(p => body.person_ids?.includes(p.id)).map(p => ({...p, source: 'manual'}));
      invalidateReview(photo); return photoView(photo);
    }
    if (action === 'preview') { const values = settings(body); return render(photo, values.brightness, values.saturation); }
    if (action === 'versions') {
      if (method === 'GET') return {items: photo.versions ?? [], total: photo.versions?.length ?? 0};
      const values = settings(body);
      const version: Version = { id: uid(), photo_id: id, number: (photo.versions?.length || 0) + 1, name: body.name || '새 보정본', parent_id: body.parent_id ?? null, review_reason: null, author: {id: user.id, name: user.name}, created_at: now(), ...values, renderer_version: 'browser-demo-v1', preview_url: await dataUrl(await render(photo, values.brightness, values.saturation)), review_requested: false, needs_review: false, targets: [], approval_count: 0, target_count: 0, consensus: false, is_final: false, comments: [] };
      (photo.versions ||= []).push(version); return version;
    }
    if (action === 'reanalyze') throw new DemoError('체험 사이트에서는 자동 분석을 실행하지 않아요. 인물을 직접 지정해 주세요.');
  }
  if (resource === 'versions') {
    const photo = requireValue(state.photos.find(p => p.versions?.some(v => v.id === id)), '보정본을 찾지 못했어요.');
    const album = requireValue(state.albums.find(a => a.id === photo.album_id && a.members.some(m => m.id === user.id)), '앨범 멤버를 선택해 주세요.');
    const version = photo.versions!.find(v => v.id === id)!;
    if (action === 'request-review') {
      if (!body.confirmed) throw new DemoError('등장 멤버와 승인 대상을 확인해 주세요.');
      if (version.review_requested) return versionStatus(version);
      if (photo.people.some(p => !p.user_id)) throw new DemoError('등장 인물의 계정을 연결해 주세요.');
      const ids = photo.people.length ? [...new Set(photo.people.map(p => p.user_id!))] : [photo.uploader_id!];
      version.targets = ids.map(id => ({user_id: id, name: album.members.find(m => m.id === id)?.name || '멤버', approved: false}));
      version.review_requested = true; notify(state, photo, `${user.name}님이 보정본 확인을 요청했어요.`);
    } else if (action === 'approval') {
      if (!version.review_requested || version.needs_review) throw new DemoError('승인 대상을 다시 확인해 주세요.');
      const target = requireValue(version.targets.find(t => t.user_id === user.id), '이 보정본의 승인 대상이 아니에요.');
      target.approved = method !== 'DELETE';
      if (!target.approved && version.is_final) { version.is_final = false; photo.final_version_id = null; }
    } else if (action === 'final') {
      if (!versionStatus(version).consensus) throw new DemoError('등장 멤버가 모두 승인해야 해요.');
      photo.versions!.forEach(v => v.is_final = v.id === id); photo.final_version_id = id;
      notify(state, photo, `${version.name}을 최종본으로 골랐어요.`);
    } else if (action === 'comments') {
      if (!body.body?.trim()) throw new DemoError('의견을 입력해 주세요.');
      version.comments.push({id: uid(), author: {id: user.id, name: user.name}, body: body.body.trim(), kind: body.kind || 'comment', created_at: now()});
    } else if (method === 'PATCH' && body.name?.trim()) version.name = body.name.trim();
    else throw new DemoError('체험에서 지원하지 않는 보정 요청입니다.');
    return versionStatus(version);
  }
  if (resource === 'people') {
    const album = requireValue(state.albums.find(a => a.people.some(p => p.id === id) && a.members.some(m => m.id === user.id)), '인물을 찾지 못했어요.');
    const person = album.people.find(p => p.id === id)!;
    if (action === 'accept-link') { if (person.proposed_user_id !== user.id) throw new DemoError('연결 제안을 받은 인물을 선택해 주세요.'); person.user_id = user.id; person.proposed_user_id = null; }
    else {
      owner(album, user.id);
      if (method === 'DELETE') album.people = album.people.filter(p => p.id !== id);
      else if (method === 'PATCH') { if (body.name) person.name = body.name; if (body.user_id === null) { person.user_id = null; person.proposed_user_id = null; } else if (body.user_id) person.proposed_user_id = body.user_id; }
    }
    state.photos.filter(p => p.album_id === album.id && p.people.some(person => person.id === id)).forEach(photo => {
      photo.people = photo.people.flatMap(p => p.id !== id ? [p] : method === 'DELETE' ? [] : [{...person, source: p.source}]); invalidateReview(photo);
    });
    person.link_status = person.user_id ? 'linked' : person.proposed_user_id ? 'pending' : 'unlinked';
    return method === 'DELETE' ? {ok: true} : person;
  }
  throw new DemoError('이 기능은 실제 서버 실행 시 사용할 수 있어요. 체험 안내를 확인해 주세요.', 501);
}
export async function demoRequest(path: string, options: RequestInit = {}): Promise<Response> {
  const method = options.method || 'GET';
  const form = options.body instanceof FormData ? options.body : undefined;
  const body: Body = typeof options.body === 'string' ? JSON.parse(options.body) : {};
  if (options.signal?.aborted) throw new DOMException('Aborted', 'AbortError');
  try {
    const action = (state: DemoState) => route(state, path, method, body, form);
    const result = method === 'GET' || path.endsWith('/preview') ? await action(await readState()) : await updateState(action);
    if (options.signal?.aborted) throw new DOMException('Aborted', 'AbortError');
    return result instanceof Blob ? new Response(result, {headers: {'Content-Type': result.type}}) : json(result);
  } catch (error) {
    if ((error as Error).name === 'AbortError') throw error;
    return new Response(JSON.stringify({message: (error as Error).message, code: 'demo_notice'}), {status: error instanceof DemoError ? error.status : 400, headers: {'Content-Type': 'application/json'}});
  }
}
