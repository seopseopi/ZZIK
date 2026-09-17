export const isBrowserDemo = import.meta.env.MODE === "demo";
let csrfToken = '';
export class ApiError extends Error { code: string; status: number; constructor(message:string, code:string, status:number) {super(message); this.code=code; this.status=status;} }
export async function api<T = unknown>(path:string, options:RequestInit = {}):Promise<T> {
  const headers = new Headers(options.headers);
  if(options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  if(options.method && !['GET','HEAD'].includes(options.method)) headers.set('X-CSRF-Token', csrfToken);
  let response:Response;
  try { response = isBrowserDemo ? await (await import('./demo/api')).demoRequest(path, options) : await fetch(`/api${path}`, {credentials:'include', ...options, headers}); }
  catch(error) {if((error as Error).name==='AbortError') throw error; throw new ApiError('서버와 연결하지 못했어요. 네트워크 연결을 확인해 주세요.', 'network_error', 0);}
  if(!response.ok) { const data=await response.json().catch(()=>({})); throw new ApiError(data.message || data.detail?.message || (typeof data.detail==='string' ? data.detail : '요청을 처리하지 못했어요.'),data.code||'request_failed',response.status); }
  if(response.status===204) return undefined as T;
  if(response.headers.get('content-type')?.includes('image/')) return await response.blob() as T;
  const data = await response.json(); if(data.csrf_token) csrfToken=data.csrf_token; return data;
}
export const post = <T=unknown>(path:string,data?:unknown) => api<T>(path,{method:'POST',body:data instanceof FormData ? data : data===undefined ? undefined : JSON.stringify(data)});
export const patch = <T=unknown>(path:string,data:unknown) => api<T>(path,{method:'PATCH',body:JSON.stringify(data)});
export const remove = (path:string) => api(path,{method:'DELETE'});
export function dateLabel(value?:string|null) { if(!value) return '촬영 정보 없음'; return new Date(value).toLocaleDateString('ko-KR',{year:'numeric',month:'long',day:'numeric'}); }
export function timeLabel(value:string) { return new Date(value).toLocaleString('ko-KR',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}); }
export function downloadPhoto(id:string, version?:string|null) { if(isBrowserDemo){void import('./demo/images').then(module=>module.downloadDemoPhoto(id,version ?? undefined)).catch(error=>alert((error as Error).message));return;} const a=document.createElement('a');a.href=`/api/photos/${id}/download${version?`?version_id=${version}`:''}`;a.download='';document.body.appendChild(a);a.click();a.remove(); }
