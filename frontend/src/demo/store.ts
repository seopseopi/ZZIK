import type { Album, Notice, Photo, User, Version } from '../types';
import fixtures from './fixtures.json';

export const demoUsers: User[] = ['지수', '민지', '서연', '유진'].map((name, i) => ({
  id: ['jisu', 'minji', 'seoyeon', 'yujin'][i], name, email: `${['jisu', 'minji', 'seoyeon', 'yujin'][i]}@moacut.local`,
}));
export type DemoState = { userId: string | null; albums: Album[]; photos: Photo[]; notices: Notice[] };
export const asset = (name: string) => `${import.meta.env.BASE_URL}demo/${name}`;
export const now = () => new Date().toISOString();
export const uid = () => crypto.randomUUID();
export const photoDefaults = {
  captured_at: null, capture_timezone: null, latitude: null, longitude: null, location_name: null,
  analysis_error: null, analysis_metadata: {}, quality: {}, final_version_id: null, note: '', purpose: 'undecided',
};
function normalizeState(state: DemoState): DemoState {
  const person = (p: Album['people'][number]) => ({...p, user_id: p.user_id ?? null, proposed_user_id: p.proposed_user_id ?? null,
    reference_url: p.reference_url ?? null, link_status: p.user_id ? 'linked' : p.proposed_user_id ? 'pending' : 'unlinked'});
  state.albums = state.albums.map(a => ({...a, owner_id: a.owner_id ?? a.members.find(m => m.role === 'owner')?.id ?? '',
    cover_url: a.cover_url ?? null, people: a.people.map(person)}));
  state.photos = state.photos.map(p => ({...photoDefaults, ...p, final_version_id: p.final_version_id ?? null,
    people: p.people.map(person), versions: p.versions?.map(v => ({...v, parent_id: v.parent_id ?? null, review_reason: v.review_reason ?? null}))}));
  state.notices = state.notices.map(n => ({...n, photo_id: n.photo_id ?? null, version_id: n.version_id ?? null, kind: n.kind ?? 'comment'}));
  return state;
}
export function initialState(): DemoState {
  const albums: Album[] = ['제주 여행', '부산 주말', '우리의 작은 순간'].map((name, i) => ({
    id: `demo-album-${i + 1}`, owner_id: 'jisu', cover_url: null, name, description: '팀원과 둘러보는 체험용 앨범', timezone: 'Asia/Seoul',
    photo_count: 0, member_count: 4, invite_code: `ZZIK-DEMO-${i + 1}`, created_at: '2026-09-15T00:00:00Z',
    members: demoUsers.map(user => ({ ...user, role: user.id === 'jisu' ? 'owner' : 'member' })),
    people: demoUsers.map(user => ({ id: `person-${i}-${user.id}`, name: user.name, user_id: user.id, proposed_user_id: null, reference_url: asset(`avatar-${user.id}.jpg`), link_status: 'linked' })),
  }));
  const photos = albums.flatMap((album, index) => {
    const numbers = index === 0 ? fixtures.map(p => p.number) : index === 1 ? [11, 5, 9, 12] : [8, 10, 4];
    return numbers.map((number, order): Photo => {
      const sample = fixtures.find(p => p.number === number)!;
      const url = asset(`photo-${String(number).padStart(2, '0')}.jpg`);
      return { ...photoDefaults, id: `${album.id}-photo-${number}`, album_id: album.id, uploader_id: 'jisu', filename: `JEJU_${String(number).padStart(4, '0')}.jpg`,
        thumbnail_url: url, display_url: url, original_url: url, width: sample.width, height: sample.height,
        created_at: new Date(Date.UTC(2026, 8, 15, order)).toISOString(), analysis_status: 'completed', analysis_provider: 'fixture', analysis_mode: 'fixture',
        face_count: sample.people.length, unknown_faces: 0, people: album.people.filter(p => sample.people.includes(p.name)), tags: sample.tags,
        selected: index === 0 && [3, 5, 8].includes(number), board_status: 'unselected', note: '', purpose: 'undecided', versions: [],
      };
    });
  });
  return { userId: 'jisu', albums, photos, notices: [] };
}
const database = new Promise<IDBDatabase>((resolve, reject) => {
  const request = indexedDB.open('zzik-browser-demo-v1', 1);
  request.onupgradeneeded = () => request.result.createObjectStore('state');
  request.onsuccess = () => resolve(request.result);
  request.onerror = () => reject(new Error('브라우저 저장 공간을 열지 못했어요. 일반 브라우저에서 다시 열어 주세요.'));
});
let statePromise: Promise<DemoState> = database.then(db => new Promise((resolve, reject) => {
  const request = db.transaction('state').objectStore('state').get('current');
  request.onsuccess = () => resolve(normalizeState(request.result || initialState()));
  request.onerror = () => reject(request.error);
}));
let writes: Promise<unknown> = Promise.resolve();
export async function readState() { await writes; return structuredClone(await statePromise); }
export function updateState<T>(action: (draft: DemoState) => T | Promise<T>): Promise<T> {
  const work = writes.then(async () => {
    const draft = structuredClone(await statePromise);
    const result = await action(draft);
    const db = await database;
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction('state', 'readwrite');
      tx.objectStore('state').put(draft, 'current');
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(new Error('브라우저 저장 공간이 부족해요. 체험을 초기화하거나 사진을 줄여 주세요.'));
      tx.onabort = () => reject(new Error('저장하지 못했어요. 브라우저 저장 공간을 확인해 주세요.'));
    });
    statePromise = Promise.resolve(draft);
    return structuredClone(result);
  });
  writes = work.catch(() => undefined);
  return work;
}
export function versionStatus(version: Version) {
  version.approval_count = version.targets.filter(t => t.approved).length;
  version.target_count = version.targets.length;
  version.consensus = version.review_requested && !version.needs_review && version.target_count > 0 && version.approval_count === version.target_count;
  return version;
}
