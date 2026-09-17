import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, CheckCheck, ChevronRight, Clock3, RefreshCw, Sparkles } from 'lucide-react';
import { api, post } from './api';
import { ErrorBox, Modal, Spinner } from './ui';
import type { Album, AnalysisStatus as Status } from './types';
import './Management.css';

function duration(ms: number) { return ms < 1000 ? `${Math.round(ms)}ms` : ms < 60000 ? `${(ms / 1000).toFixed(1)}초` : `${Math.floor(ms / 60000)}분 ${Math.round(ms % 60000 / 1000)}초`; }
export default function AnalysisStatus({ album, onClose, onPhoto }: { album: Album; onClose: () => void; onPhoto: (photoId: string) => void }) {
  const client = useQueryClient();
  const [notice, setNotice] = useState('');
  const [confirmRetry, setConfirmRetry] = useState(false);
  const status = useQuery({ queryKey: ['analysis-status', album.id], queryFn: () => api<Status>(`/albums/${album.id}/analysis-status`), refetchInterval: 3000 });
  const retry = useMutation({ mutationFn: () => post<{ queued: number }>(`/albums/${album.id}/reanalyze-failed`), onSuccess: result => {
    setConfirmRetry(false); setNotice(result.queued ? `${result.queued}장의 분석을 다시 요청했어요. 원본은 그대로 유지돼요.` : '다시 분석할 실패 사진이 없어요.');
    client.invalidateQueries({ queryKey: ['analysis-status', album.id] }); client.invalidateQueries({ queryKey: ['photos', album.id] });
  } });
  const data = status.data;
  return <Modal title="사진 정리 현황" subtitle={album.name} onClose={onClose} closeDisabled={retry.isPending}>
    {status.isPending ? <Spinner/> : status.error ? <ErrorBox error={status.error} retry={() => status.refetch()}/> : data && <div className="analysis-overview">
      <div className="analysis-mode-note"><Sparkles size={20}/><div><strong>{data.mode === 'sample' ? '샘플 사진 분석 모드' : '실제 사진 분석 모드'}</strong><p>{data.mode === 'sample' ? '등록된 샘플만 자동으로 분류해요. 다른 사진은 인물을 직접 지정할 수 있어요.' : '등록한 기준 얼굴로 같은 앨범의 사진 속 인물을 찾아요. 결과를 직접 확인해 주세요.'}</p></div></div>
      <div className="analysis-counts" aria-label="분석 상태별 사진 수">{([
        ['completed', '완료', CheckCheck], ['processing', '분석 중', RefreshCw], ['pending', '대기', Clock3], ['failed', '확인 필요', AlertCircle],
      ] as const).map(([key, label, Icon]) => <div key={key} className={key}><Icon size={18}/><strong>{data.stats[key]}<small>장</small></strong><span>{label}</span></div>)}</div>
      <p className="settings-help">총 {data.total}장의 원본이 저장되어 있어요. 분석에 실패해도 사진을 보정하고 내려받을 수 있어요.</p>
      <dl className="analysis-records"><div><dt>기록된 분석 실행</dt><dd>{data.recorded_runs.toLocaleString()}회</dd></div><div><dt>누적 처리 시간</dt><dd>{duration(data.elapsed_ms)}</dd></div><div><dt>외부 분석 요청</dt><dd>{data.calls.toLocaleString()}회</dd></div></dl>
      <p className="settings-help">재시도 포함 누적값이며 실제 대기 시간과는 다릅니다.</p>
      {(data.stats.pending + data.stats.processing) > 0 && <div className="panel-note"><Clock3 size={17}/><span>분석 중에는 이 창을 닫아도 괜찮아요. 대기 상태가 오래 지속되면 분석 작업이 실행 중인지 확인해 주세요.</span></div>}
      {retry.error && <ErrorBox error={retry.error}/>}{notice && <p className="management-notice" role="status">{notice}</p>}
      {data.stats.failed > 0 ? <section className="settings-section"><div className="analysis-failure-heading"><h3>다시 확인할 사진</h3><button className="button secondary small" onClick={() => setConfirmRetry(true)} disabled={retry.isPending}><RefreshCw size={14}/>실패한 사진 재분석</button></div>
        {confirmRetry && <div className="management-confirm" role="group" aria-label="실패한 사진 재분석 확인"><h4>실패한 {data.stats.failed}장을 다시 분석할까요?</h4><p>{data.mode === 'sample' ? '샘플에 없는 사진은 다시 요청해도 자동으로 분류되지 않아요. 각 사진에서 인물을 직접 지정하거나 실제 분석을 연결해 주세요.' : '현재 연결된 분석 서비스로 다시 요청해요. 새 분석 결과로 등장 인물이 달라지면 기존 승인을 다시 확인해야 해요.'}</p><div><button className="button primary small" disabled={retry.isPending} onClick={() => retry.mutate()}>재분석 요청</button><button className="button subtle small" onClick={() => setConfirmRetry(false)} disabled={retry.isPending}>취소</button></div></div>}
        <div className="analysis-failures">{data.failures.map(item => <button key={item.photo_id} onClick={() => onPhoto(item.photo_id)}><AlertCircle size={17}/><span><strong>{item.filename}</strong><small>{(item.error || '분석을 완료하지 못했어요. 사진에서 상태를 확인해 주세요.').replace(/^[A-Z_]+:\s*/, '')}</small></span><ChevronRight size={17}/></button>)}</div>
        {data.stats.failed > data.failures.length && <p className="settings-help">최근 실패 {data.failures.length}장을 보여줘요. 사진 목록의 ‘확인 필요’ 필터에서 나머지를 볼 수 있어요.</p>}
      </section> : <p className="management-notice"><CheckCheck size={17}/>{data.total ? '현재 분석에 실패한 사진이 없어요.' : '첫 사진을 올리면 정리 현황을 보여드려요.'}</p>}
    </div>}
  </Modal>;
}
