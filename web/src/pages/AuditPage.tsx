import { Fragment, useState } from 'react';
import type { FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { auditApi } from '../api/endpoints';
import type { AuditRow } from '../api/types';
import { PageHeader } from '../components/PageHeader';
import { Card } from '../components/Card';
import { Pagination } from '../components/Pagination';
import { Badge } from '../components/Badge';
import { JsonBlock } from '../components/JsonBlock';
import { CenterSpinner } from '../components/Spinner';
import { ErrorBanner } from '../components/ErrorBanner';
import { EmptyState } from '../components/EmptyState';
import { IconChevronDown, IconRefresh, IconSearch } from '../components/Icons';
import { cn } from '../lib/cn';
import { formatDateTime } from '../lib/format';

const LIMIT = 25;

interface Filters {
  actor: string;
  action: string;
  from: string;
  to: string;
}

const EMPTY_FILTERS: Filters = { actor: '', action: '', from: '', to: '' };

function statusTone(status: string): 'good' | 'critical' | 'warn' | 'neutral' {
  const s = status.toLowerCase();
  if (s === 'ok' || s === 'success' || s === 'succeeded') return 'good';
  if (s === 'error' || s === 'failed' || s === 'denied') return 'critical';
  if (s === 'warn' || s === 'partial') return 'warn';
  return 'neutral';
}

function targetLabel(row: AuditRow): string {
  const parts = [row.target_service, row.target_table, row.target_id].filter(
    Boolean,
  );
  return parts.length ? parts.join(' / ') : '—';
}

export function AuditPage() {
  const [applied, setApplied] = useState<Filters>(EMPTY_FILTERS);
  const [draft, setDraft] = useState<Filters>(EMPTY_FILTERS);
  const [offset, setOffset] = useState(0);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const query = useQuery({
    queryKey: ['audit', applied, offset],
    queryFn: () =>
      auditApi.list({
        actor: applied.actor || undefined,
        action: applied.action || undefined,
        from: applied.from || undefined,
        to: applied.to || undefined,
        limit: LIMIT,
        offset,
      }),
    placeholderData: (prev) => prev,
  });

  function onApply(e: FormEvent) {
    e.preventDefault();
    setOffset(0);
    setApplied(draft);
  }

  function onReset() {
    setDraft(EMPTY_FILTERS);
    setApplied(EMPTY_FILTERS);
    setOffset(0);
  }

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const data = query.data;
  const items = data?.items ?? [];
  const page = Math.floor(offset / LIMIT);
  const totalPages = data ? Math.max(1, Math.ceil(data.total / LIMIT)) : 1;

  return (
    <div className="space-y-6">
      <PageHeader
        title="감사 로그"
        description="운영자 액션 감사 추적 · 필터 및 상세 확장"
        actions={
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => query.refetch()}
            disabled={query.isFetching}
          >
            <IconRefresh
              width={16}
              height={16}
              className={query.isFetching ? 'animate-spin' : ''}
            />
            새로고침
          </button>
        }
      />

      <Card>
        <form onSubmit={onApply} className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <div>
            <label className="label" htmlFor="actor">
              액터
            </label>
            <input
              id="actor"
              className="input"
              placeholder="운영자명"
              value={draft.actor}
              onChange={(e) => setDraft({ ...draft, actor: e.target.value })}
            />
          </div>
          <div>
            <label className="label" htmlFor="action">
              액션
            </label>
            <input
              id="action"
              className="input"
              placeholder="예: probe"
              value={draft.action}
              onChange={(e) => setDraft({ ...draft, action: e.target.value })}
            />
          </div>
          <div>
            <label className="label" htmlFor="from">
              시작
            </label>
            <input
              id="from"
              type="datetime-local"
              className="input"
              value={draft.from}
              onChange={(e) => setDraft({ ...draft, from: e.target.value })}
            />
          </div>
          <div>
            <label className="label" htmlFor="to">
              종료
            </label>
            <input
              id="to"
              type="datetime-local"
              className="input"
              value={draft.to}
              onChange={(e) => setDraft({ ...draft, to: e.target.value })}
            />
          </div>
          <div className="flex items-end gap-2">
            <button type="submit" className="btn btn-primary flex-1">
              <IconSearch width={16} height={16} />
              조회
            </button>
            <button type="button" className="btn btn-ghost" onClick={onReset}>
              초기화
            </button>
          </div>
        </form>
      </Card>

      <Card flush description={data ? `총 ${data.total}건` : undefined}>
        {query.isLoading ? (
          <CenterSpinner label="감사 로그 불러오는 중…" />
        ) : query.isError ? (
          <div className="p-4">
            <ErrorBanner error={query.error} onRetry={() => query.refetch()} />
          </div>
        ) : items.length === 0 ? (
          <EmptyState title="감사 기록 없음" message="조건에 맞는 감사 로그가 없습니다." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-border bg-surface-2 text-xs font-semibold uppercase tracking-wide text-fg-muted">
                  <th className="w-8 px-3 py-2.5" />
                  <th className="px-3 py-2.5 text-left">시각</th>
                  <th className="px-3 py-2.5 text-left">액터</th>
                  <th className="px-3 py-2.5 text-left">액션</th>
                  <th className="px-3 py-2.5 text-left">대상</th>
                  <th className="px-3 py-2.5 text-left">상태</th>
                  <th className="px-3 py-2.5 text-left">IP</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => {
                  const id = String(row.id);
                  const isOpen = expanded.has(id);
                  return (
                    <Fragment key={id}>
                      <tr
                        onClick={() => toggle(id)}
                        className="cursor-pointer border-b border-border hover:bg-surface-2"
                      >
                        <td className="px-3 py-2.5 text-fg-subtle">
                          <IconChevronDown
                            width={16}
                            height={16}
                            className={cn('transition-transform', isOpen && 'rotate-180')}
                          />
                        </td>
                        <td className="whitespace-nowrap px-3 py-2.5 text-fg-muted">
                          {formatDateTime(row.created_at)}
                        </td>
                        <td className="px-3 py-2.5 font-medium text-fg">{row.actor}</td>
                        <td className="px-3 py-2.5">
                          <span className="font-mono text-xs text-fg">{row.action}</span>
                        </td>
                        <td className="px-3 py-2.5 font-mono text-xs text-fg-muted">
                          {targetLabel(row)}
                        </td>
                        <td className="px-3 py-2.5">
                          <Badge tone={statusTone(row.status)}>{row.status}</Badge>
                        </td>
                        <td className="px-3 py-2.5 font-mono text-xs text-fg-muted">
                          {row.request_ip ?? '—'}
                        </td>
                      </tr>
                      {isOpen && (
                        <tr className="border-b border-border bg-surface-2">
                          <td colSpan={7} className="px-4 py-4">
                            <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
                              <div>
                                <p className="mb-1 text-xs font-semibold text-fg-muted">params</p>
                                <JsonBlock value={row.params_json} maxHeight="16rem" />
                              </div>
                              <div>
                                <p className="mb-1 text-xs font-semibold text-fg-muted">before</p>
                                <JsonBlock value={row.before_json} maxHeight="16rem" />
                              </div>
                              <div>
                                <p className="mb-1 text-xs font-semibold text-fg-muted">after</p>
                                <JsonBlock value={row.after_json} maxHeight="16rem" />
                              </div>
                            </div>
                            {(row.target_schema || row.target_service) && (
                              <p className="mt-3 text-xs text-fg-subtle">
                                schema: {row.target_schema ?? '—'} · service:{' '}
                                {row.target_service ?? '—'} · id: {row.target_id ?? '—'}
                              </p>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
            {query.isFetching && (
              <div className="h-0.5 w-full overflow-hidden">
                <div className="h-full w-1/3 animate-pulse rounded-full bg-brand" />
              </div>
            )}
            <div className="border-t border-border px-3 py-2">
              <Pagination
                page={page}
                totalPages={totalPages}
                totalElements={data?.total}
                pageSize={LIMIT}
                onPageChange={(p) => setOffset(p * LIMIT)}
                disabled={query.isFetching}
              />
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
