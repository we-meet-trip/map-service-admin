import { useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { get, post, selectedEnvironment } from '../api/client';
import { useAuth } from '../providers/AuthProvider';
import { PageHeader } from '../components/PageHeader';
import { ErrorBanner } from '../components/ErrorBanner';

type Status = 'OPEN' | 'IN_REVIEW' | 'ACTIONED' | 'DISMISSED';
type Action = 'REVIEW' | 'DISMISS' | 'RESOLVE' | 'HIDE_CHAT_MESSAGE' | 'RESTRICT_CHAT' | 'LIFT_CHAT_RESTRICTION';
interface Report { report_id: string; status: Status; content_type: string; reason: string; resolution: string | null; created_at: string; updated_at: string }
interface Detail { report: Report; description: string | null; current_message: string | null; room_id: number | null; message_seq: number | null; schedule_id: number | null; recommend_job_id: string | null; actions: { action_id: string; action: Action; admin_actor: string; restriction_hours: number | null; created_at: string }[] }
const labels: Record<Action, string> = { REVIEW: '검토 시작', DISMISS: '위반 없음으로 종결', RESOLVE: '대응 완료', HIDE_CHAT_MESSAGE: '이 메시지 숨김', RESTRICT_CHAT: '발신자 채팅 전송 제한', LIFT_CHAT_RESTRICTION: '발신자 채팅 제한 해제' };
const contentLabels: Record<string, string> = { CHAT_MESSAGE: '채팅 메시지', TRIP: '생성 일정', VISION: 'Vision 결과', REVIEW_SUMMARY: '리뷰 요약' };
const states: Record<Status, string> = { OPEN: '접수', IN_REVIEW: '검토 중', ACTIONED: '조치 완료', DISMISSED: '종결' };

export function ModerationPage() {
  const { user } = useAuth();
  const cache = useQueryClient();
  const environment = selectedEnvironment();
  const [status, setStatus] = useState<Status>('OPEN');
  const [selected, setSelected] = useState<string | null>(null);
  const [hours, setHours] = useState(24);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [confirmed, setConfirmed] = useState<Action | null>(null);
  const retry = useRef<{ key: string; action_id: string } | null>(null);
  const canReview = user?.role === 'operator' || user?.role === 'owner';
  const canEnforce = user?.role === 'owner';
  const queue = useQuery({ queryKey: ['moderation', environment, status],
    queryFn: () => get<Report[]>(`/v1/moderation/reports?status=${status}&limit=100`), refetchInterval: 30000 });
  const detail = useQuery({ queryKey: ['moderation-detail', environment, selected], enabled: !!selected && canReview,
    queryFn: () => get<Detail>(`/v1/moderation/reports/${selected}`), gcTime: 0, staleTime: 0, refetchOnWindowFocus: false });
  const row = detail.data?.report;
  const active = row?.status === 'OPEN' || row?.status === 'IN_REVIEW';

  function choose(id: string) { setSelected(id); setConfirmed(null); setError(null); retry.current = null; }
  async function apply(action: Action) {
    if (!selected || busy || !row) return;
    setBusy(true); setError(null);
    const key = `${environment}:${selected}:${action}:${action === 'RESTRICT_CHAT' ? hours : ''}`;
    if (retry.current?.key !== key) retry.current = { key, action_id: crypto.randomUUID() };
    try {
      await post(`/v1/moderation/reports/${selected}/actions`, {
        action_id: retry.current.action_id, action,
        ...(action === 'RESTRICT_CHAT' ? { restriction_hours: hours } : {}),
      });
      retry.current = null; setConfirmed(null);
    } catch (failure) { setError(failure); }
    finally {
      await cache.invalidateQueries({ queryKey: ['moderation', environment] });
      await cache.invalidateQueries({ queryKey: ['moderation-detail', environment, selected] });
      setBusy(false);
    }
  }

  return <div className="space-y-5">
    <PageHeader title="콘텐츠 신고 처리" />
    <p className="text-sm text-fg-muted">대상 환경: <strong>{environment}</strong>. 접수 목록, 원문 검토, 제재 권한을 구분합니다. 원문은 열람을 기록하며 이 화면을 닫으면 캐시에서 제거됩니다.</p>
    <p className="text-sm text-fg-muted">위협·괴롭힘·혐오·성착취·불법행위·개인정보 노출·스팸을 검토하세요. 자동 생성 일정, Vision, 리뷰 요약의 부정확하거나 위험한 결과도 처리 대상입니다. Vision·리뷰 요약 신고는 사용자 설명만 보관합니다.</p>
    {(error || queue.error || detail.error) ? <ErrorBanner error={error || queue.error || detail.error} /> : null}
    <label className="block">상태 <select aria-label="신고 상태" className="rounded border border-border bg-bg p-2" value={status}
      onChange={(event) => { setStatus(event.target.value as Status); setSelected(null); setConfirmed(null); }}>
      {Object.entries(states).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
    </select></label>
    {queue.isLoading ? <p>신고를 조회하고 있습니다.</p> : queue.data?.length === 0 ? <p>이 상태의 신고가 없습니다.</p> : null}
    <div className="overflow-auto rounded border border-border"><table className="w-full text-left text-sm">
      <thead><tr><th className="p-3">접수 시각</th><th>종류</th><th>사유</th><th>상태</th><th>검토</th></tr></thead>
      <tbody>{queue.data?.map((item) => <tr key={item.report_id} className="border-t border-border">
        <td className="p-3">{new Date(item.created_at).toLocaleString()}</td><td>{contentLabels[item.content_type] ?? item.content_type}</td><td>{item.reason}</td><td>{states[item.status]}</td>
        <td>{canReview ? <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => choose(item.report_id)}>검토 열기</button> : '검토 권한 필요'}</td>
      </tr>)}</tbody></table></div>
    {selected && <section className="space-y-4 rounded border border-border bg-surface p-4" aria-label="신고 상세">
      <div className="flex items-center justify-between"><h2 className="font-semibold">신고 상세 · {environment}</h2>
        <button className="btn btn-ghost" disabled={busy} onClick={() => { setSelected(null); setConfirmed(null); }}>원문 닫기</button></div>
      {detail.isFetching ? <p>현재 처리 상태를 확인하고 있습니다.</p> : null}
      {detail.data && <>
        <p>현재 상태: {states[detail.data.report.status]} / {detail.data.report.resolution ?? '조치 없음'}</p>
        <h3 className="font-medium">신고 설명</h3><p className="whitespace-pre-wrap break-words">{detail.data.description ?? '설명 없음 또는 보존기간 만료·탈퇴로 삭제됨'}</p>
        {detail.data.report.content_type === 'CHAT_MESSAGE' && <><h3 className="font-medium">대상 메시지 (현재 저장 내용)</h3>
          <p className="whitespace-pre-wrap break-words">{detail.data.current_message ?? '대상 내용이 삭제되었습니다.'}</p></>}
        {detail.data.report.content_type === 'TRIP' && <p className="break-all text-sm">일정 참조: {detail.data.schedule_id ?? detail.data.recommend_job_id ?? '삭제됨'}. 확인한 문제는 서비스 개선·안내 후 대응 완료로 처리하세요.</p>}
        {['VISION', 'REVIEW_SUMMARY'].includes(detail.data.report.content_type) && <p className="text-sm text-fg-muted">사용자가 제공한 설명입니다. 실제 생성 원문이나 작성자를 검증한 기록이 아닙니다. 신고 내용을 검토하고 서비스 개선·안내 후 대응 완료 또는 기각으로 처리하세요.</p>}
        <div className="flex flex-wrap gap-2">
          {active && canReview && (['REVIEW', 'DISMISS', 'RESOLVE'] as Action[]).map((action) => <button key={action} className="btn btn-ghost" disabled={busy || detail.isFetching} onClick={() => setConfirmed(action)}>{labels[action]}</button>)}
          {active && canEnforce && row?.content_type === 'CHAT_MESSAGE' && <>
            <button className="btn btn-ghost" disabled={busy || detail.isFetching} onClick={() => setConfirmed('HIDE_CHAT_MESSAGE')}>{labels.HIDE_CHAT_MESSAGE}</button>
            <label>제한 시간 <input aria-label="채팅 제한 시간" className="w-20 rounded border border-border bg-bg p-2" type="number" min={1} max={720} value={hours} onChange={(event) => setHours(Number(event.target.value))} /></label>
            <button className="btn btn-ghost" disabled={busy || detail.isFetching || !Number.isInteger(hours) || hours < 1 || hours > 720} onClick={() => setConfirmed('RESTRICT_CHAT')}>{labels.RESTRICT_CHAT}</button>
          </>}
          {canEnforce && row?.status === 'ACTIONED' && row?.resolution === 'RESTRICT_CHAT' && <button className="btn btn-ghost" disabled={busy || detail.isFetching} onClick={() => setConfirmed('LIFT_CHAT_RESTRICTION')}>{labels.LIFT_CHAT_RESTRICTION}</button>}
        </div>
        {confirmed && <div role="alert" className="space-y-3 rounded border border-border p-4">
          <p><strong>{environment}</strong> 환경에서 ‘{labels[confirmed]}’을 실행합니다.
            {confirmed === 'RESTRICT_CHAT' && ` 이 사용자는 모든 채팅방에서 ${hours}시간 동안 새 메시지를 보낼 수 없습니다.`}
            {confirmed === 'LIFT_CHAT_RESTRICTION' && ' 이 사용자의 모든 채팅방 전송 제한을 해제합니다. 다른 신고의 제재 이력도 확인하세요.'}
            {confirmed === 'HIDE_CHAT_MESSAGE' && ' 모든 참여자의 조회와 실시간 전달에서 이 메시지를 숨깁니다.'}</p>
          <button className="btn btn-primary" disabled={busy || detail.isFetching} onClick={() => void apply(confirmed)}>{busy ? '처리 상태 확인 중…' : '확인 후 실행'}</button>
          <button className="btn btn-ghost" disabled={busy} onClick={() => setConfirmed(null)}>취소</button>
        </div>}
        <h3 className="font-medium">처리 이력</h3>
        <ul className="space-y-1 text-sm">{detail.data.actions.map((action) => <li key={action.action_id}>{new Date(action.created_at).toLocaleString()} · {labels[action.action]} · {action.admin_actor}{action.restriction_hours ? ` · ${action.restriction_hours}시간` : ''}</li>)}</ul>
      </>}
    </section>}
    <p className="text-xs text-fg-muted">처리 완료 신고의 설명·대상 참조는 완료 90일 후 정리하며, 완료 접수 기록과 User 조치 이력은 365일 기준으로 정리합니다. 중앙 관리자 감사 기록은 별도 정책을 따릅니다.</p>
  </div>;
}
