import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, ArrowLeft, ArrowLeftRight, Check, CheckCircle2, ChevronDown, Clock3, Download, History, Info, LoaderCircle, Maximize2, MessageCircle, Minimize2, Palette, RotateCcw, Send, ShieldCheck, SlidersHorizontal, SunMedium, Trash2, Users, X } from 'lucide-react';
import { api, downloadPhoto, patch, post, remove, timeLabel } from './api';
import { Avatar, ErrorBox, Spinner } from './ui';
import type { Album, PhotoDetail, User, Version } from './types';
import './Editor.css';

type EditorProps = { photoId: string; album: Album; user: User; onClose: () => void; onChanged?: () => void; onDeleted?: (photoId: string) => void };
type Tab = 'edit' | 'review' | 'info';
const analysisLabels: Record<string, string> = { pending: '분석 대기 중', processing: '사진 분석 중', completed: '분석 완료', failed: '분석 확인 필요' };

export default function Editor({ photoId, album, user, onClose, onChanged, onDeleted }: EditorProps) {
  const client = useQueryClient();
  const [deleting, setDeleting] = useState(false);
  const deletingRef = useRef(false);
  const query = useQuery({ queryKey: ['photo', photoId], queryFn: ({ signal }) => api<PhotoDetail>(`/photos/${photoId}`, { signal }), enabled: !deleting, refetchInterval: deleting ? false : 5000 });
  const photo = query.data;
  const versions = photo?.versions || [];
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = versions.find(v => v.id === selectedId);
  const [tab, setTab] = useState<Tab>('edit');
  const [brightness, setBrightness] = useState(1);
  const [saturation, setSaturation] = useState(1);
  const [versionName, setVersionName] = useState('');
  const [compare, setCompare] = useState(false);
  const [split, setSplit] = useState(50);
  const [showOriginal, setShowOriginal] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [renderedUrl, setRenderedUrl] = useState<string | null>(null);
  const [rendering, setRendering] = useState(false);
  const [previewError, setPreviewError] = useState<Error | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [comment, setComment] = useState('');
  const [commentKind, setCommentKind] = useState('comment');
  const [editingPeople, setEditingPeople] = useState(false);
  const [peopleIds, setPeopleIds] = useState<string[]>([]);
  const [note, setNote] = useState('');
  const [purpose, setPurpose] = useState('undecided');
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteConfirmed, setDeleteConfirmed] = useState(false);
  const [deleteError, setDeleteError] = useState<Error | null>(null);
  const initializedId = useRef('');
  const dialog = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  const dirty = brightness !== (selected?.brightness ?? 1) || saturation !== (selected?.saturation ?? 1);
  const busyRef = useRef(false);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    dialog.current?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (document.querySelector('.modal-backdrop')) return;
      if (event.key === 'Escape' && !deletingRef.current) closeRef.current();
      if (event.key !== 'Tab') return;
      const nodes = Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),summary,[tabindex="0"]') || []).filter(element => element.getClientRects().length > 0);
      const first = nodes[0], last = nodes[nodes.length - 1];
      if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener('keydown', handleKey);
    return () => { document.body.style.overflow = overflow; document.removeEventListener('keydown', handleKey); previous?.focus(); };
  }, []);

  useEffect(() => {
    if (!photo || initializedId.current === photo.id) return;
    initializedId.current = photo.id;
    setNote(photo.note || '');
    setPurpose(photo.purpose || 'undecided');
    if (photo.final_version_id) {
      const final = photo.versions?.find(v => v.id === photo.final_version_id);
      if (final) { setSelectedId(final.id); setBrightness(final.brightness); setSaturation(final.saturation); }
    }
  }, [photo]);

  // Previews and downloads share the server renderer; superseded requests cannot replace the current image.
  useEffect(() => {
    setRenderedUrl(null);
    setPreviewError(null);
    if (deleting || !photo || !dirty || (brightness === 1 && saturation === 1)) { setRendering(false); return; }
    const controller = new AbortController();
    let objectUrl: string | undefined;
    setRendering(true);
    const timer = window.setTimeout(async () => {
      try {
        const blob = await api<Blob>(`/photos/${photoId}/preview`, { method: 'POST', body: JSON.stringify({ brightness, saturation }), signal: controller.signal });
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob);
        setRenderedUrl(objectUrl);
      } catch (cause) { if (!controller.signal.aborted) setPreviewError(cause as Error); }
      finally { if (!controller.signal.aborted) setRendering(false); }
    }, 300);
    return () => { window.clearTimeout(timer); controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [photoId, !!photo, brightness, saturation, selectedId, dirty, deleting]);

  async function act(task: () => Promise<unknown>, success: string) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true); setError(null); setNotice('');
    try { await task(); await client.invalidateQueries(); onChanged?.(); setNotice(success); }
    catch (cause) { setError(cause as Error); }
    finally { busyRef.current = false; setBusy(false); }
  }

  function chooseVersion(version?: Version) {
    setSelectedId(version?.id || null); setBrightness(version?.brightness ?? 1); setSaturation(version?.saturation ?? 1);
    setVersionName(''); setConfirmed(false); setShowOriginal(false); setNotice(''); setError(null);
  }

  function saveVersion() {
    void act(async () => {
      const saved = await post<Version>(`/photos/${photoId}/versions`, { name: versionName.trim() || `보정본 ${Math.max(0, ...versions.map(v => v.number)) + 1}`, parent_id: selectedId, brightness, saturation });
      setSelectedId(saved.id); setVersionName(''); setConfirmed(false); setTab('review');
    }, '새 보정본을 저장했어요.');
  }

  const resultUrl = photo ? (brightness === 1 && saturation === 1 ? photo.display_url : renderedUrl || selected?.preview_url || photo.display_url) : '';
  const selectedTitle = selected?.name || '원본';
  const personTargets = (photo?.people || []).filter(person => !!person.user_id);
  const missingAccounts = (photo?.people || []).filter(person => !person.user_id);
  const noFaces = photo?.analysis_status === 'completed' && photo.face_count === 0 && photo.people.length === 0;
  const uploader = album.members.find(member => member.id === photo?.uploader_id);
  const targetNames = noFaces ? [uploader?.name || '사진을 올린 멤버'] : Array.from(new Map(personTargets.map(person => [person.user_id, album.members.find(member => member.id === person.user_id)?.name || person.name])).values());
  const canRequestReview = missingAccounts.length === 0 && (noFaces || personTargets.length > 0);
  const myTarget = selected?.targets.find(target => target.user_id === user.id);
  const canDelete = !!photo && (photo.uploader_id === user.id || album.members.some(member => member.id === user.id && member.role === 'owner'));
  const isSample = photo?.analysis_provider === 'fixture' || photo?.analysis_mode === 'fixture' || photo?.analysis_mode === 'sample';
  const analysisMetadata = photo?.analysis_metadata;
  const recordedDuration = typeof analysisMetadata?.elapsed_ms === 'number' && Number.isFinite(analysisMetadata.elapsed_ms) && analysisMetadata.elapsed_ms >= 0 ? analysisMetadata.elapsed_ms : null;
  const recordedCalls = typeof analysisMetadata?.calls === 'number' && Number.isInteger(analysisMetadata.calls) && analysisMetadata.calls >= 0 ? analysisMetadata.calls : null;
  const recordedModel = typeof analysisMetadata?.model === 'string' && analysisMetadata.model.trim() ? analysisMetadata.model : null;
  const recordedDate = typeof analysisMetadata?.analyzed_at === 'string' && !Number.isNaN(new Date(analysisMetadata.analyzed_at).getTime()) ? analysisMetadata.analyzed_at : null;
  const hasAnalysisRecord = recordedDuration !== null || recordedCalls !== null || !!recordedModel || !!recordedDate;

  async function deletePhoto() {
    if (!canDelete || !deleteConfirmed || busyRef.current) return;
    busyRef.current = true; deletingRef.current = true;
    setBusy(true); setDeleting(true); setDeleteError(null);
    try {
      await client.cancelQueries({ queryKey: ['photo', photoId], exact: true });
      await remove(`/photos/${photoId}`);
    } catch (cause) {
      busyRef.current = false; deletingRef.current = false;
      setBusy(false); setDeleting(false); setDeleteError(cause as Error);
      return;
    }
    // Keep the detail query disabled through unmount. Refetching it after deletion would create a ghost 404.
    client.removeQueries({ queryKey: ['photo', photoId], exact: true });
    onClose();
    onDeleted?.(photoId);
    for (const key of ['photos', 'albums', 'album', 'board', 'recommendations', 'notifications', 'groups']) {
      void client.invalidateQueries({ queryKey: [key] });
    }
  }

  return createPortal(<div className="editor-backdrop"><div className={`photo-editor ${expanded ? 'is-expanded' : ''}`} ref={dialog} role="dialog" aria-modal="true" aria-label="사진 보정 및 함께 고르기" tabIndex={-1}>
    <header className="editor-header">
      <button className="editor-icon" onClick={onClose} disabled={deleting} aria-label="사진 상세 닫기"><ArrowLeft size={21}/></button>
      <div className="editor-heading"><span>{album.name}<ChevronDown size={12}/></span><h2>{photo?.filename || '사진 불러오는 중'}</h2></div>
      <strong className="editor-mobile-title">함께 고르기</strong>
      {photo && !deleting && <details className="editor-download"><summary className="editor-button" aria-label="다운로드"><Download size={17}/><span>다운로드</span><ChevronDown size={13}/></summary><div className="editor-download-menu">
        <button onClick={() => downloadPhoto(photo.id)}>원본 다운로드<small>업로드한 원본 파일</small></button>
        {selected && <button onClick={() => downloadPhoto(photo.id, selected.id)}>선택 보정본 다운로드<small>{selected.name} · 저장된 설정</small></button>}
        {photo.final_version_id && <button onClick={() => downloadPhoto(photo.id, photo.final_version_id)}>최종본 다운로드<small>함께 승인한 최종본</small></button>}
      </div></details>}
      <button className="editor-icon editor-close-desktop" onClick={onClose} disabled={deleting} aria-label="닫기"><X size={21}/></button>
    </header>
    {query.isPending ? <Spinner label="사진 불러오는 중"/> : query.error ? <div className="editor-load-error"><ErrorBox error={query.error} retry={() => void query.refetch()}/></div> : photo && <div className="editor-body">
      <main className="editor-canvas">
        <div className="editor-canvas-toolbar"><div><span className="editor-version-badge">{dirty ? '저장 전 미리보기' : selectedTitle}</span>{selected?.is_final && !dirty && <span className="editor-final-badge"><CheckCircle2 size={13}/>최종본</span>}</div><button className="editor-icon" onClick={() => setExpanded(!expanded)} aria-label={expanded ? '편집 패널 보기' : '사진 확대'}>{expanded ? <Minimize2 size={17}/> : <Maximize2 size={17}/>}</button></div>
        <div className={`editor-photo-stage ${compare && !showOriginal ? 'comparing' : ''}`} style={{ aspectRatio: `${photo.width} / ${photo.height}` }}>
          <img src={showOriginal || compare ? photo.display_url : resultUrl} alt={`${photo.filename} ${showOriginal ? '원본' : selectedTitle}`} className="editor-main-image"/>
          {compare && !showOriginal && <><img src={resultUrl} alt="보정 결과 비교" className="editor-compare-image" style={{ clipPath: `inset(0 0 0 ${split}%)` }}/><div className="editor-comparison-line" style={{ left: `${split}%` }}><span><ArrowLeftRight size={19}/></span></div><span className="editor-before-label">원본</span><span className="editor-after-label">{dirty ? '보정 중' : selectedTitle}</span><input className="editor-comparison-input" aria-label="원본과 보정본 비교 위치" type="range" min="0" max="100" value={split} onChange={event => setSplit(Number(event.target.value))}/></>}
          {rendering && <span className="editor-rendering"><LoaderCircle className="spin" size={14}/>보정 미리보기 생성 중</span>}
          {showOriginal && <span className="editor-original-label">원본을 보고 있어요</span>}
        </div>
        <div className="editor-preview-controls">
          <div className="editor-view-toggle"><button aria-label="원본 보기" className={showOriginal || (!selected && !dirty) ? 'active' : ''} aria-pressed={showOriginal || (!selected && !dirty)} onClick={() => { setShowOriginal(true); setCompare(false); }}>원본</button><button aria-label="보정본 보기" className={!showOriginal && (!!selected || dirty) ? 'active' : ''} aria-pressed={!showOriginal && (!!selected || dirty)} disabled={!selected && !dirty} onClick={() => setShowOriginal(false)}>{selected ? `v${selected.number}` : '보정본'}</button></div>
          <button className={`editor-button subtle editor-compare-toggle ${compare ? 'active' : ''}`} aria-label="슬라이더로 비교" aria-pressed={compare} onClick={() => { setCompare(!compare); setShowOriginal(false); }}><ArrowLeftRight size={16}/><span>슬라이더로 비교</span></button><span className="editor-image-size">{photo.width.toLocaleString()} × {photo.height.toLocaleString()}</span>
        </div>
        {previewError && <div className="editor-preview-error"><ErrorBox error={previewError}/></div>}
        <section className="editor-filmstrip" aria-label="사진 보정 이력">
          <div className="editor-filmstrip-title"><span>보정본</span><small>{versions.length}개</small></div>
          <div className="editor-version-list"><button className={`editor-version ${!selectedId ? 'active' : ''}`} aria-pressed={!selectedId} onClick={() => chooseVersion()}><span className="editor-version-thumb"><img src={photo.thumbnail_url} alt="원본 썸네일"/>{!selectedId && <i><Check size={12}/></i>}</span><strong>원본</strong></button>
            {[...versions].sort((a, b) => a.number - b.number).map(version => <button key={version.id} title={`${version.name} · ${version.author.name} · ${timeLabel(version.created_at)} · 밝기 ${Math.round(version.brightness * 100)}% · 채도 ${Math.round(version.saturation * 100)}%`} className={`editor-version ${selectedId === version.id ? 'active' : ''}`} aria-pressed={selectedId === version.id} onClick={() => chooseVersion(version)}><span className="editor-version-thumb"><img src={version.preview_url} alt={`${version.name} 썸네일`} loading="lazy"/>{version.is_final ? <em>최종본</em> : selectedId === version.id && <i><Check size={12}/></i>}</span><strong>{version.name}</strong><small>{version.author.name} · {timeLabel(version.created_at)}</small><small>밝기 {Math.round(version.brightness * 100)}% · 채도 {Math.round(version.saturation * 100)}%</small></button>)}
          </div>
        </section>
        {selected && selected.review_requested && !selected.needs_review && tab !== 'review' && <div className="editor-mobile-review">
          <div className="editor-quick-approvals"><div>{selected.targets.map(target => <span key={target.user_id} className={target.approved ? 'approved' : ''} title={`${target.name} · ${target.approved ? '승인 완료' : '확인 대기'}`}><Avatar name={target.name} url={album.people.find(person => person.user_id === target.user_id)?.reference_url} size={35}/></span>)}</div><span>{selected.approval_count} / {selected.target_count}명 승인</span></div>
          {myTarget && <button className={`editor-button ${myTarget.approved ? '' : 'primary'} full`} disabled={busy || dirty} onClick={() => void act(() => myTarget.approved ? remove(`/versions/${selected.id}/approval`) : post(`/versions/${selected.id}/approval`), myTarget.approved ? '승인을 취소했어요. 최종본이었다면 지정도 해제돼요.' : '이 보정본을 승인했어요.')}><CheckCircle2 size={19}/>{myTarget.approved ? '내 승인 취소' : '이 보정본 승인'}</button>}
          {selected.consensus && !selected.is_final && <button className="editor-button primary full" disabled={busy || dirty} onClick={() => void act(() => post(`/versions/${selected.id}/final`), '이 보정본을 최종본으로 정했어요.')}><ShieldCheck size={18}/>최종본으로 정하기</button>}
          <button className="editor-button full" onClick={() => setTab('review')}>승인 상세 보기</button>
        </div>}
      </main>
      <aside className="editor-panel">

        <nav className="editor-tabs" aria-label="사진 상세 메뉴">{([{ id: 'edit', title: '사진 보정', icon: SlidersHorizontal }, { id: 'review', title: '함께 고르기', icon: Users }, { id: 'info', title: '사진 정보', icon: Info }] as const).map(item => <button key={item.id} className={tab === item.id ? 'active' : ''} aria-pressed={tab === item.id} onClick={() => setTab(item.id)}><item.icon size={16}/>{item.title}</button>)}</nav>
        <div className="editor-panel-scroll">
          {error && <ErrorBox error={error}/>} {notice && <div className="editor-notice" role="status"><CheckCircle2 size={17}/>{notice}</div>}
          {tab === 'edit' && <>
            <div className="editor-section-heading"><h3>보정</h3><button className="editor-text-button" onClick={() => { setBrightness(1); setSaturation(1); }}><RotateCcw size={13}/>초기화</button></div>
            <div className="editor-adjustment"><label htmlFor="photo-brightness"><span><SunMedium size={19}/>밝기</span><output htmlFor="photo-brightness">{Math.round(brightness * 100)}%</output></label><input id="photo-brightness" type="range" min="0.25" max="2" step="0.01" value={brightness} onChange={event => { setBrightness(Number(event.target.value)); setShowOriginal(false); }}/><div className="editor-range-labels"><span>어둡게</span><span>기본 100%</span><span>밝게</span></div></div>
            <div className="editor-adjustment"><label htmlFor="photo-saturation"><span><Palette size={19}/>채도</span><output htmlFor="photo-saturation">{Math.round(saturation * 100)}%</output></label><input id="photo-saturation" type="range" min="0" max="2" step="0.01" value={saturation} onChange={event => { setSaturation(Number(event.target.value)); setShowOriginal(false); }}/><div className="editor-range-labels"><span>차분하게</span><span>기본 100%</span><span>선명하게</span></div></div>
            <div className="editor-base-version"><History size={17}/><div><strong>{selected ? `기준 · ${selected.name}` : '기준 · 원본'}</strong>{selected && <p>{selected.author.name} · {timeLabel(selected.created_at)}</p>}{selected && <small>밝기 {Math.round(selected.brightness * 100)}% · 채도 {Math.round(selected.saturation * 100)}%</small>}</div></div>
            <form className="editor-save-form" onSubmit={event => { event.preventDefault(); saveVersion(); }}><label htmlFor="version-name">새 보정본 이름 <span>선택</span></label><input id="version-name" maxLength={80} value={versionName} onChange={event => setVersionName(event.target.value)} placeholder="보정본 이름"/><button className="editor-button primary full" disabled={busy || rendering} type="submit">{busy ? <LoaderCircle size={17} className="spin"/> : <Check size={17}/>}새 보정본 저장</button></form>
          </>}
          {tab === 'review' && <>
            {!selected ? <div className="editor-review-empty"><h3>저장된 보정본을 선택해 주세요</h3><p>새 보정본을 저장한 뒤 확인을 요청할 수 있어요.</p><button className="editor-button primary full" onClick={() => setTab('edit')}>사진 보정하기</button></div> : <>
              <div className="editor-selected-summary"><h3>{selected.name}</h3><p>{selected.author.name} · {timeLabel(selected.created_at)}</p></div>
              {dirty && <div className="editor-warning"><AlertCircle size={17}/><div>저장하지 않은 변경사항이 있어요. 새 보정본을 저장한 뒤 확인을 요청해 주세요.<button className="editor-text-button" onClick={() => setTab('edit')}>보정 화면으로 돌아가기</button></div></div>}
              {selected.needs_review ? <div className="editor-warning"><AlertCircle size={18}/><div><strong>등장 멤버가 바뀌어 재확인이 필요해요.</strong><p>현재 설정으로 새 보정본을 저장하고 변경된 멤버에게 다시 확인을 요청해 주세요.</p><button className="editor-button full" disabled={busy || rendering} onClick={saveVersion}>새 보정본으로 다시 확인하기</button></div></div> : !selected.review_requested ? <>
                <h3 className="editor-small-heading">승인 대상</h3><p className="editor-help">사진에 실제로 나온 멤버와 아래 승인 대상을 확인해 주세요. 승인은 이 보정본에만 적용돼요.</p>
                <div className="editor-target-preview">{targetNames.length ? targetNames.map(name => <span key={name}><Avatar name={name} size={30}/>{name}</span>) : <p>확인된 승인 대상이 아직 없어요.</p>}</div>
                {noFaces && <p className="editor-help">얼굴이 감지되지 않은 사진은 사진을 올린 멤버가 확인해요.</p>}
                {missingAccounts.length > 0 && <div className="editor-warning"><AlertCircle size={17}/><span>{missingAccounts.map(person => person.name).join(', ')}의 계정 연결이 필요해요. 앨범의 인물 관리에서 연결을 완료해 주세요.</span></div>}
                {(photo.unknown_faces > 0 || !canRequestReview) && <div className="editor-warning"><Info size={17}/><span>{photo.unknown_faces > 0 ? `미확정 얼굴 ${photo.unknown_faces}명은 승인 대상에 자동 포함되지 않아요. ` : ''}사진 정보에서 실제 등장 멤버를 확인해 주세요.</span></div>}
                <button className="editor-text-button" onClick={() => setTab('info')}>등장 멤버 확인·수정</button>
                <label className="editor-confirmation"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)}/><span>사진의 등장 멤버와 승인 대상을 확인했어요.</span></label>
                <button className="editor-button primary full" disabled={busy || dirty || !confirmed || !canRequestReview} onClick={() => void act(() => post(`/versions/${selected.id}/request-review`, { confirmed: true }), '멤버들에게 확인을 요청했어요.')}><Send size={16}/>확인 요청 보내기</button>
              </> : <>
                <div className="editor-consensus-heading"><h3>{selected.consensus ? '합의 완료' : '승인 현황'}</h3><span>{selected.approval_count} / {selected.target_count}명 승인</span></div>
                <div className="editor-progress-track"><span style={{ width: `${selected.target_count ? selected.approval_count / selected.target_count * 100 : 0}%` }}/></div>
                <div className="editor-targets">{selected.targets.map(target => <div key={target.user_id} className={`editor-target-person ${target.approved ? 'approved' : ''}`}><Avatar name={target.name} url={album.people.find(person => person.user_id === target.user_id)?.reference_url} size={35}/><strong>{target.name}{target.user_id === user.id && <small>나</small>}</strong><span className={target.approved ? 'approved' : ''}>{target.approved ? <><CheckCircle2 size={14}/>승인 완료</> : <><Clock3 size={14}/>확인 대기</>}</span></div>)}</div>
                {myTarget && <button className={`editor-button ${myTarget.approved ? '' : 'primary'} full`} disabled={busy || dirty} onClick={() => void act(() => myTarget.approved ? remove(`/versions/${selected.id}/approval`) : post(`/versions/${selected.id}/approval`), myTarget.approved ? '승인을 취소했어요. 최종본이었다면 지정도 해제돼요.' : '이 보정본을 승인했어요.')}><CheckCircle2 size={17}/>{myTarget.approved ? '내 승인 취소' : '이 보정본 승인'}</button>}
                {!myTarget && <p className="editor-help">이 보정본의 승인 대상인 멤버만 승인할 수 있어요.</p>}
                {selected.is_final ? <div className="editor-final-callout"><ShieldCheck size={22}/><div><strong>최종본으로 선택됨</strong><p>승인 대상 모두 확인 완료</p></div></div> : selected.consensus && <button className="editor-button primary full" disabled={busy || dirty} onClick={() => void act(() => post(`/versions/${selected.id}/final`), '이 보정본을 최종본으로 정했어요.')}><ShieldCheck size={17}/>최종본으로 정하기</button>}
              </>}
              <section className="editor-comments"><h3><MessageCircle size={17}/>의견 <span>{selected.comments.length}</span></h3>{selected.comments.length === 0 ? <p className="editor-help">아직 의견이 없어요.</p> : <div className="editor-comment-list">{selected.comments.map(item => <article key={item.id}><Avatar name={item.author.name} size={28}/><div><header><strong>{item.author.name}</strong><time>{timeLabel(item.created_at)}</time></header>{item.kind === 'change_request' && <span className="editor-change-tag">수정 요청</span>}<p>{item.body}</p></div></article>)}</div>}<form onSubmit={event => { event.preventDefault(); void act(async () => { await post(`/versions/${selected.id}/comments`, { body: comment.trim(), kind: commentKind }); setComment(''); }, '이야기를 남겼어요.'); }}><label className="editor-sr-only" htmlFor="version-comment">보정본에 의견 남기기</label><textarea id="version-comment" value={comment} onChange={event => setComment(event.target.value)} placeholder="의견 입력" maxLength={2000} required rows={3}/><div><select aria-label="의견 종류" value={commentKind} onChange={event => setCommentKind(event.target.value)}><option value="comment">의견 남기기</option><option value="change_request">수정 요청하기</option></select><button className="editor-button small" disabled={busy || !comment.trim()} type="submit"><Send size={14}/>등록</button></div></form></section>
            </>}
          </>}
          {tab === 'info' && <>
            <div className="editor-section-heading"><h3>사진 속 사람들</h3><button className="editor-text-button" onClick={() => { setPeopleIds(photo.people.map(person => person.id)); setEditingPeople(!editingPeople); }}>{editingPeople ? '닫기' : '수정'}</button></div>
            {editingPeople ? <div className="editor-people-edit">{album.people.length ? album.people.map(person => <label key={person.id}><input type="checkbox" checked={peopleIds.includes(person.id)} onChange={event => setPeopleIds(current => event.target.checked ? [...current, person.id] : current.filter(id => id !== person.id))}/><Avatar name={person.name} url={person.reference_url} size={32}/><span>{person.name}<small>{person.user_id ? '계정 연결됨' : '계정 미연결'}</small></span></label>) : <p className="editor-help">앨범에서 기준 인물을 먼저 등록해 주세요.</p>}<p className="editor-help">등장 인물을 바꾸면 기존 승인과 최종본을 다시 확인해야 해요.</p><button className="editor-button primary full" disabled={busy} onClick={() => void act(async () => { await api(`/photos/${photoId}/people`, { method: 'PUT', body: JSON.stringify({ person_ids: peopleIds }) }); setEditingPeople(false); setConfirmed(false); }, '등장 인물을 저장했어요.')}>등장 인물 저장</button></div> : <div className="editor-people-display">{photo.people.length ? photo.people.map(person => <span key={person.id}><Avatar name={person.name} url={person.reference_url || album.people.find(p => p.id === person.id)?.reference_url} size={45}/><strong>{person.name}</strong><small>{person.source === 'manual' ? '직접 연결' : person.source === 'auto' ? isSample ? '샘플 분석' : '자동 분석' : '연결 정보'}</small></span>) : <p className="editor-help">확인된 인물이 없어요. 사진에 나온 인물을 직접 연결할 수 있어요.</p>}</div>}
            {photo.people.some(person => person.source === 'manual') && <p className="editor-help">직접 연결한 인물은 재분석 후에도 유지돼요. 얼굴 감지 수와 직접 연결한 인물 수는 다를 수 있어요.</p>}
            <div className="editor-analysis-info"><span className={`editor-status-dot ${photo.analysis_status}`}/><strong>{analysisLabels[photo.analysis_status] || '분석 상태 확인 중'}</strong>{isSample && <span className="editor-sample-label">샘플</span>}</div>
            <p className="editor-help">{photo.analysis_status === 'completed' ? `감지된 얼굴 ${photo.face_count}명 · 미확정 ${photo.unknown_faces}명` : '사진 저장과 인물 분석은 따로 진행돼요.'}</p>
            {photo.analysis_error && <div className="editor-warning"><AlertCircle size={16}/><span>{photo.analysis_error}</span></div>}
            {photo.analysis_status === 'failed' && <button className="editor-button full" disabled={busy} onClick={() => void act(() => post(`/photos/${photoId}/reanalyze`), '다시 분석을 요청했어요.')}><RotateCcw size={15}/>사진 다시 분석하기</button>}
            <details className="editor-analysis-record"><summary><Clock3 size={15}/><span>분석 기록</span><ChevronDown size={14}/></summary>
              {hasAnalysisRecord ? <>
                <p>{isSample ? '등록된 샘플을 처리한 기록이에요. 실제 얼굴 분석 성능을 나타내지는 않아요.' : '서버에 저장된 최근 분석 기록이에요.'}{photo.analysis_status !== 'completed' && ' 현재 진행 중이거나 실패한 재분석 기록과 다를 수 있어요.'}</p>
                <dl>
                  {photo.analysis_provider && <div><dt>분석 방식</dt><dd>{isSample ? '지정된 샘플 확인' : photo.analysis_provider === 'rekognition' ? 'AWS 얼굴 분석' : photo.analysis_provider}</dd></div>}
                  {recordedDate && <div><dt>기록 시각</dt><dd>{new Date(recordedDate).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', year: 'numeric', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })}<small>한국시간</small></dd></div>}
                  {recordedDuration !== null && <div><dt>처리 시간</dt><dd>{recordedDuration < 1000 ? `${recordedDuration.toLocaleString('ko-KR')}밀리초` : `${(recordedDuration / 1000).toLocaleString('ko-KR', { maximumFractionDigits: 2 })}초`}</dd></div>}
                  {recordedCalls !== null && <div><dt>서비스 호출</dt><dd>{recordedCalls.toLocaleString('ko-KR')}회</dd></div>}
                  {recordedModel && <div><dt>분석 버전</dt><dd>{recordedModel === 'fixture-v1' ? '샘플 분석 v1' : recordedModel === 'rekognition-2016-06-27' ? 'AWS Rekognition · 2016-06-27' : recordedModel}</dd></div>}
                </dl>
              </> : <p>아직 저장된 처리 시간과 호출 기록이 없어요.</p>}
            </details>
            <dl className="editor-metadata"><div><dt>파일명</dt><dd>{photo.filename}</dd></div><div><dt>크기</dt><dd>{photo.width.toLocaleString()} × {photo.height.toLocaleString()}</dd></div><div><dt>촬영 시각</dt><dd>{photo.captured_at ? `${photo.captured_at.replace('T', ' ')}${photo.capture_timezone ? ` (${photo.capture_timezone})` : ' (시간대 미확인)'}` : '촬영 정보 없음'}</dd></div><div><dt>업로드</dt><dd>{timeLabel(photo.created_at)}</dd></div><div><dt>장소</dt><dd>{photo.location_name || (photo.latitude != null && photo.longitude != null ? `${photo.latitude.toFixed(4)}, ${photo.longitude.toFixed(4)} · 장소명 없음` : '위치 정보 없음')}</dd></div></dl>
            <h3 className="editor-small-heading">태그</h3><div className="editor-tag-list">{photo.tags.length ? photo.tags.map(tag => <span key={tag}>#{tag}</span>) : <p className="editor-help">분석된 키워드가 없어요.</p>}</div>
            <form className="editor-note-form" onSubmit={event => { event.preventDefault(); void act(() => patch(`/photos/${photoId}`, { note, purpose }), '메모와 사진 용도를 저장했어요.'); }}><label htmlFor="photo-purpose">사진 용도<select id="photo-purpose" value={purpose} onChange={event => setPurpose(event.target.value)}><option value="undecided">아직 정하지 않았어요</option><option value="share">함께 공유하기</option><option value="print">인화하기</option><option value="keep">소중히 보관하기</option><option value="social">SNS에 게시하기</option><option value="profile">프로필 사진</option><option value="memory">추억으로 남기기</option><option value="exclude">게시하지 않기</option>{["게시용", "인화용", "보관용", "게시 제외"].includes(purpose) && <option value={purpose}>{purpose}</option>}</select></label><label htmlFor="photo-note">메모<textarea id="photo-note" rows={3} maxLength={2000} value={note} onChange={event => setNote(event.target.value)} placeholder="이 사진에 대한 메모"/></label><button className="editor-button full" disabled={busy} type="submit">사진 정보 저장</button></form>
            {canDelete && <section className="editor-delete-section" aria-labelledby="editor-delete-heading">
              <div><h3 id="editor-delete-heading">사진 삭제</h3><p>사진을 올린 멤버와 앨범 소유자만 삭제할 수 있어요.</p></div>
              {!deleteOpen ? <button className="editor-button danger full" disabled={busy} onClick={() => { setDeleteOpen(true); setDeleteConfirmed(false); setDeleteError(null); }}><Trash2 size={16}/>사진 삭제</button> : <div className="editor-delete-confirm">
                <p><strong>이 사진을 모든 멤버의 앨범에서 영구 삭제해요.</strong> 원본, 모든 보정본과 최종본, 승인 기록, 댓글이 함께 삭제되며 되돌릴 수 없어요.</p>
                <label><input type="checkbox" checked={deleteConfirmed} disabled={deleting} onChange={event => setDeleteConfirmed(event.target.checked)}/><span>모든 멤버에게서 삭제되며 되돌릴 수 없다는 점을 확인했어요.</span></label>
                {deleteError && <ErrorBox error={deleteError}/>}
                <div className="editor-delete-actions"><button className="editor-button" disabled={deleting} onClick={() => { setDeleteOpen(false); setDeleteConfirmed(false); setDeleteError(null); }}>취소</button><button className="editor-button danger" disabled={busy || !deleteConfirmed} onClick={() => void deletePhoto()}>{deleting ? <LoaderCircle className="spin" size={16}/> : <Trash2 size={16}/>}사진 영구 삭제</button></div>
                {deleting && <p className="editor-delete-status" role="status">사진과 연결된 기록을 삭제하고 있어요.</p>}
              </div>}
            </section>}
          </>}
        </div>
      </aside>
    </div>}
  </div></div>, document.body);
}
