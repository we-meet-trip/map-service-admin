import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { actionsApi, jobsApi } from '../api/endpoints';
import type { DlqItem, JobItem } from '../api/types';
import { PageHeader } from '../components/PageHeader';
import { Card } from '../components/Card';
import { StatTile } from '../components/StatTile';
import { DataTable } from '../components/DataTable';
import type { Column } from '../components/DataTable';
import { Pagination } from '../components/Pagination';
import { Badge } from '../components/Badge';
import { Spinner } from '../components/Spinner';
import { errorMessage } from '../components/ErrorBanner';
import { IconRefresh } from '../components/Icons';
import { useConfirm } from '../providers/ConfirmProvider';
import { useToast } from '../providers/ToastProvider';
import { formatDateTime, formatNumber } from '../lib/format';
import { jobStatusTone } from '../lib/status';

const PAGE_SIZE = 20;
const DLQ_LIMIT = 100;

const STATUS_OPTIONS = [
  { value: '', label: '전체 상태' },
  { value: 'in_progress', label: '진행 중' },
  { value: 'done', label: '완료' },
  { value: 'failed', label: '실패' },
];

export function JobsPage() {
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const { toast } = useToast();

  const stats = useQuery({
    queryKey: ['jobs', 'stats'],
    queryFn: () => jobsApi.stats(),
    refetchInterval: 30_000,
  });

  const [status, setStatus] = useState('');
  const [page, setPage] = useState(0);

  const jobs = useQuery({
    queryKey: ['jobs', 'list', status, page],
    queryFn: () => jobsApi.list(status, page, PAGE_SIZE),
    placeholderData: (prev) => prev,
  });

  const dlq = useQuery({
    queryKey: ['jobs', 'dlq'],
    queryFn: () => jobsApi.dlq(DLQ_LIMIT),
  });

  const [selected, setSelected] = useState<Set<string>>(new Set());

  const dlqItems = dlq.data ?? [];
  const allSelected = dlqItems.length > 0 && selected.size === dlqItems.length;

  function toggleRow(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setSelected((prev) =>
      prev.size === dlqItems.length
        ? new Set()
        : new Set(dlqItems.map((d) => d.recordId)),
    );
  }

  const dlqAction = useMutation({
    mutationFn: (vars: { kind: 'reprocess' | 'discard'; ids: string[] }) =>
      vars.kind === 'reprocess'
        ? actionsApi.dlqReprocess(vars.ids)
        : actionsApi.dlqDiscard(vars.ids),
    onSuccess: (res, vars) => {
      toast({
        kind: res.failed > 0 ? 'info' : 'success',
        title: vars.kind === 'reprocess' ? 'DLQ 재처리 완료' : 'DLQ 폐기 완료',
        message: `요청 ${res.requested} · 성공 ${res.succeeded} · 실패 ${res.failed}`,
      });
      setSelected(new Set());
      void queryClient.invalidateQueries({ queryKey: ['jobs', 'dlq'] });
      void queryClient.invalidateQueries({ queryKey: ['jobs', 'stats'] });
    },
    onError: (err) => {
      toast({ kind: 'error', title: 'DLQ 작업 실패', message: errorMessage(err) });
    },
  });

  async function runDlqAction(kind: 'reprocess' | 'discard') {
    const ids = Array.from(selected);
    if (ids.length === 0) return;
    const ok = await confirm({
      title: kind === 'reprocess' ? 'DLQ 재처리' : 'DLQ 폐기',
      summary:
        kind === 'reprocess'
          ? '선택한 실패 레코드를 다시 처리 큐에 넣습니다.'
          : '선택한 실패 레코드를 큐에서 영구 삭제합니다.',
      details: [{ label: '선택 레코드', value: `${ids.length}건` }],
      impact:
        kind === 'discard'
          ? '폐기된 레코드는 복구할 수 없습니다.'
          : undefined,
      confirmLabel: kind === 'reprocess' ? '재처리' : '폐기',
      danger: kind === 'discard',
    });
    if (!ok) return;
    dlqAction.mutate({ kind, ids });
  }

  const jobColumns: Column<JobItem>[] = [
    { key: 'jobId', header: '작업 ID', render: (j) => <span className="font-mono text-xs">{j.jobId}</span> },
    {
      key: 'scheduleId',
      header: '스케줄',
      render: (j) => <span className="font-mono text-xs text-fg-muted">{j.scheduleId ?? '—'}</span>,
    },
    {
      key: 'status',
      header: '상태',
      render: (j) => <Badge tone={jobStatusTone(j.status)}>{j.status}</Badge>,
    },
    {
      key: 'error',
      header: '오류',
      render: (j) =>
        j.error ? (
          <span className="line-clamp-1 max-w-[18rem] text-critical" title={j.error}>
            {j.error}
          </span>
        ) : (
          <span className="text-fg-subtle">—</span>
        ),
    },
    {
      key: 'createdAt',
      header: '생성',
      render: (j) => <span className="text-fg-muted">{formatDateTime(j.createdAt)}</span>,
    },
    {
      key: 'finishedAt',
      header: '완료',
      render: (j) => <span className="text-fg-muted">{formatDateTime(j.finishedAt)}</span>,
    },
  ];

  const dlqColumns: Column<DlqItem>[] = useMemo(
    () => [
      {
        key: 'select',
        width: '2.5rem',
        header: (
          <input
            type="checkbox"
            className="h-4 w-4 cursor-pointer accent-[color:var(--color-brand)]"
            checked={allSelected}
            onChange={toggleAll}
            aria-label="전체 선택"
          />
        ),
        render: (d) => (
          <input
            type="checkbox"
            className="h-4 w-4 cursor-pointer accent-[color:var(--color-brand)]"
            checked={selected.has(d.recordId)}
            onChange={() => toggleRow(d.recordId)}
            onClick={(e) => e.stopPropagation()}
            aria-label={`레코드 ${d.recordId} 선택`}
          />
        ),
      },
      { key: 'recordId', header: '레코드', render: (d) => <span className="font-mono text-xs">{d.recordId}</span> },
      { key: 'jobId', header: '작업 ID', render: (d) => <span className="font-mono text-xs text-fg-muted">{d.jobId ?? '—'}</span> },
      {
        key: 'delivery',
        header: '전달 횟수',
        align: 'right',
        render: (d) => <span className="tabular-nums">{formatNumber(d.deliveryCount)}</span>,
      },
      {
        key: 'error',
        header: '오류',
        render: (d) =>
          d.error ? (
            <span className="line-clamp-1 max-w-[16rem] text-critical" title={d.error}>
              {d.error}
            </span>
          ) : (
            <span className="text-fg-subtle">—</span>
          ),
      },
      {
        key: 'payload',
        header: '페이로드',
        render: (d) =>
          d.payloadPreview ? (
            <span className="line-clamp-1 max-w-[16rem] font-mono text-xs text-fg-muted" title={d.payloadPreview}>
              {d.payloadPreview}
            </span>
          ) : (
            <span className="text-fg-subtle">—</span>
          ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [allSelected, selected, dlqItems],
  );

  const s = stats.data;

  return (
    <div className="space-y-6">
      <PageHeader
        title="작업 · DLQ"
        description="스케줄 작업 상태와 실패 큐(DLQ) 재처리 · 폐기"
        actions={
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => {
              void stats.refetch();
              void jobs.refetch();
              void dlq.refetch();
            }}
          >
            <IconRefresh width={16} height={16} />
            새로고침
          </button>
        }
      />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-5">
        <StatTile label="전체 작업" value={s ? formatNumber(s.total) : '—'} tone="neutral" loading={stats.isLoading} />
        <StatTile label="진행 중" value={s ? formatNumber(s.byStatus.in_progress ?? 0) : '—'} tone="brand" loading={stats.isLoading} />
        <StatTile label="완료" value={s ? formatNumber(s.byStatus.done ?? 0) : '—'} tone="good" loading={stats.isLoading} />
        <StatTile label="실패" value={s ? formatNumber(s.byStatus.failed ?? 0) : '—'} tone={s && (s.byStatus.failed ?? 0) > 0 ? 'critical' : 'neutral'} loading={stats.isLoading} />
        <StatTile label="24h 실패" value={s ? formatNumber(s.failedLast24h) : '—'} tone={s && s.failedLast24h > 0 ? 'warn' : 'good'} loading={stats.isLoading} />
      </div>

      <Card
        flush
        title="작업 목록"
        actions={
          <select
            className="input h-9 w-40"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(0);
            }}
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        }
      >
        <DataTable
          columns={jobColumns}
          rows={jobs.data?.items ?? []}
          rowKey={(j) => j.jobId}
          loading={jobs.isLoading || jobs.isFetching}
          error={jobs.isError ? jobs.error : undefined}
          onRetry={() => jobs.refetch()}
          emptyTitle="작업 없음"
          rowClassName={(j) =>
            jobStatusTone(j.status) === 'critical' ? 'bg-critical-weak' : undefined
          }
          footer={
            jobs.data ? (
              <Pagination
                page={page}
                totalPages={jobs.data.totalPages}
                totalElements={jobs.data.totalElements}
                pageSize={jobs.data.size || PAGE_SIZE}
                onPageChange={setPage}
                disabled={jobs.isFetching}
              />
            ) : undefined
          }
        />
      </Card>

      <Card
        flush
        title="DLQ (실패 큐)"
        description={`최대 ${DLQ_LIMIT}건 표시`}
        actions={
          <div className="flex items-center gap-2">
            <span className="text-xs text-fg-muted">{selected.size}건 선택</span>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => runDlqAction('reprocess')}
              disabled={selected.size === 0 || dlqAction.isPending}
            >
              {dlqAction.isPending && dlqAction.variables?.kind === 'reprocess' && (
                <Spinner size={14} />
              )}
              재처리
            </button>
            <button
              type="button"
              className="btn btn-danger btn-sm"
              onClick={() => runDlqAction('discard')}
              disabled={selected.size === 0 || dlqAction.isPending}
            >
              {dlqAction.isPending && dlqAction.variables?.kind === 'discard' && (
                <Spinner size={14} />
              )}
              폐기
            </button>
          </div>
        }
      >
        <DataTable
          columns={dlqColumns}
          rows={dlqItems}
          rowKey={(d) => d.recordId}
          loading={dlq.isLoading}
          error={dlq.isError ? dlq.error : undefined}
          onRetry={() => dlq.refetch()}
          emptyTitle="DLQ 비어 있음"
          emptyMessage="처리 실패한 레코드가 없습니다."
        />
      </Card>
    </div>
  );
}
