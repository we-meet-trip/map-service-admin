import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { actionsApi, opsApi } from '../api/endpoints';
import type { KmaWhich } from '../api/endpoints';
import type { ForecastTableRow } from '../api/types';
import { PageHeader } from '../components/PageHeader';
import { Card } from '../components/Card';
import { StatTile } from '../components/StatTile';
import { DataTable } from '../components/DataTable';
import type { Column } from '../components/DataTable';
import { Switch } from '../components/Switch';
import { Spinner } from '../components/Spinner';
import { Badge } from '../components/Badge';
import { ErrorBanner, errorMessage } from '../components/ErrorBanner';
import { IconBolt, IconRefresh } from '../components/Icons';
import { useConfirm } from '../providers/ConfirmProvider';
import { useToast } from '../providers/ToastProvider';
import { ApiError } from '../api/client';
import { formatCell, formatDateTime, formatNumber } from '../lib/format';

const WHICH_LABEL: Record<KmaWhich, string> = {
  short: '단기예보 (short)',
  mid: '중기예보 (mid)',
  housekeep: '정리 작업 (housekeep)',
};

export function WeatherPage() {
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const { toast } = useToast();

  const polling = useQuery({
    queryKey: ['ops', 'polling'],
    queryFn: () => opsApi.polling(),
    refetchInterval: 60_000,
  });
  const forecast = useQuery({
    queryKey: ['ops', 'forecast-rows'],
    queryFn: () => opsApi.forecastRows(),
  });

  const [which, setWhich] = useState<KmaWhich>('short');
  const [gridId, setGridId] = useState('');
  const [gridActive, setGridActive] = useState(true);

  const kmaRun = useMutation({
    mutationFn: (w: KmaWhich) => actionsApi.kmaRunNow(w),
    onSuccess: (res, w) => {
      toast({
        kind: res.ok ? 'success' : 'info',
        title: `${WHICH_LABEL[w]} 수집 트리거`,
        message: `triggered: ${formatCell(res.triggered)}`,
      });
      void queryClient.invalidateQueries({ queryKey: ['ops', 'polling'] });
    },
    onError: (err) => {
      const already = err instanceof ApiError && err.status === 409;
      toast({
        kind: already ? 'info' : 'error',
        title: already ? '이미 실행 중' : 'KMA 수집 실패',
        message: errorMessage(err),
      });
    },
  });

  const gridPatch = useMutation({
    mutationFn: (vars: { id: number; active: boolean }) =>
      actionsApi.patchGrid(vars.id, vars.active),
    onSuccess: (res) => {
      toast({
        kind: 'success',
        title: '격자 상태 변경',
        message: `변경됨: ${res.changed ? '예' : '아니오'} · ${formatCell(
          res.before,
        )} → ${formatCell(res.after)}`,
      });
      void queryClient.invalidateQueries({ queryKey: ['ops', 'polling'] });
    },
    onError: (err) => {
      toast({ kind: 'error', title: '격자 변경 실패', message: errorMessage(err) });
    },
  });

  async function runKma() {
    const ok = await confirm({
      title: 'KMA 강제 수집',
      summary: '선택한 파이프라인의 수집 작업을 지금 즉시 실행합니다.',
      details: [{ label: '대상', value: WHICH_LABEL[which] }],
      impact: '이미 실행 중이면 409로 거부될 수 있습니다. 외부 KMA API를 호출합니다.',
      confirmLabel: '수집 실행',
    });
    if (!ok) return;
    kmaRun.mutate(which);
  }

  async function applyGrid() {
    const idNum = Number(gridId);
    if (!gridId.trim() || Number.isNaN(idNum)) {
      toast({ kind: 'error', title: '격자 ID 오류', message: '유효한 숫자를 입력하세요.' });
      return;
    }
    const ok = await confirm({
      title: '격자 활성 상태 변경',
      summary: '지정한 격자의 활성 여부를 변경합니다.',
      details: [
        { label: '격자 ID', value: idNum },
        { label: '변경 후', value: gridActive ? '활성' : '비활성' },
      ],
      confirmLabel: '적용',
    });
    if (!ok) return;
    gridPatch.mutate({ id: idNum, active: gridActive });
  }

  const p = polling.data;

  const forecastColumns: Column<ForecastTableRow>[] = [
    { key: 'table', header: '테이블', render: (r) => <span className="font-mono text-xs">{r.table}</span> },
    {
      key: 'rows',
      header: '행 수',
      align: 'right',
      render: (r) => <span className="tabular-nums">{formatNumber(r.rows)}</span>,
    },
    {
      key: 'min',
      header: '최소 만료',
      render: (r) => <span className="text-fg-muted">{formatDateTime(r.min_expires_at)}</span>,
    },
    {
      key: 'max',
      header: '최대 만료',
      render: (r) => <span className="text-fg-muted">{formatDateTime(r.max_expires_at)}</span>,
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="기상 수집"
        description="KMA 폴링 상태, 격자 관리, 예보 캐시 행 및 강제 수집"
        actions={
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => {
              void polling.refetch();
              void forecast.refetch();
            }}
            disabled={polling.isFetching}
          >
            <IconRefresh width={16} height={16} className={polling.isFetching ? 'animate-spin' : ''} />
            새로고침
          </button>
        }
      />

      {polling.isError && (
        <ErrorBanner title="폴링 상태를 불러오지 못했습니다" error={polling.error} onRetry={() => polling.refetch()} />
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="활성 격자"
          value={p ? formatNumber(p.grids.active_grids) : '—'}
          hint={p ? `총 ${formatNumber(p.grids.total_grids)}` : undefined}
          tone="brand"
          loading={polling.isLoading}
        />
        <StatTile
          label="단기예보 행"
          value={p ? formatNumber(p.short_term.rows) : '—'}
          hint={p ? `base ${formatDateTime(p.short_term.last_base_at)}` : undefined}
          loading={polling.isLoading}
        />
        <StatTile
          label="중기육상 행"
          value={p ? formatNumber(p.mid_land.rows) : '—'}
          hint={p ? `tmfc ${formatDateTime(p.mid_land.last_tm_fc)}` : undefined}
          loading={polling.isLoading}
        />
        <StatTile
          label="중기기온 행"
          value={p ? formatNumber(p.mid_temp.rows) : '—'}
          hint={p ? `tmfc ${formatDateTime(p.mid_temp.last_tm_fc)}` : undefined}
          loading={polling.isLoading}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title="KMA 강제 수집" description="수집 파이프라인을 수동으로 트리거">
          <div className="space-y-4">
            <div>
              <label className="label" htmlFor="which">
                대상 파이프라인
              </label>
              <select
                id="which"
                className="input"
                value={which}
                onChange={(e) => setWhich(e.target.value as KmaWhich)}
                disabled={kmaRun.isPending}
              >
                <option value="short">단기예보 (short)</option>
                <option value="mid">중기예보 (mid)</option>
                <option value="housekeep">정리 작업 (housekeep)</option>
              </select>
            </div>
            <button
              type="button"
              className="btn btn-primary"
              onClick={runKma}
              disabled={kmaRun.isPending}
            >
              {kmaRun.isPending ? <Spinner size={16} /> : <IconBolt width={16} height={16} />}
              지금 수집 실행
            </button>
            <p className="text-xs text-fg-subtle">
              실행 결과는 토스트로, 상세 감사는 감사 로그에 남습니다.
            </p>
          </div>
        </Card>

        <Card title="격자 활성 토글" description="격자 ID로 활성 여부를 직접 변경">
          <div className="space-y-4">
            <div>
              <label className="label" htmlFor="gridId">
                격자 ID
              </label>
              <input
                id="gridId"
                type="number"
                inputMode="numeric"
                className="input"
                placeholder="예: 60127"
                value={gridId}
                onChange={(e) => setGridId(e.target.value)}
                disabled={gridPatch.isPending}
              />
            </div>
            <div className="flex items-center justify-between rounded-lg border border-border bg-surface-2 px-3 py-2">
              <span className="text-sm text-fg">활성 상태</span>
              <Switch
                checked={gridActive}
                onChange={setGridActive}
                label={gridActive ? '활성' : '비활성'}
                disabled={gridPatch.isPending}
              />
            </div>
            <button
              type="button"
              className="btn btn-primary"
              onClick={applyGrid}
              disabled={gridPatch.isPending || !gridId.trim()}
            >
              {gridPatch.isPending ? <Spinner size={16} /> : null}
              변경 적용
            </button>
          </div>
        </Card>
      </div>

      <Card
        title="예보 캐시 행"
        description="테이블별 행 수와 만료 범위"
        flush
        actions={forecast.data ? <Badge tone="neutral">{forecast.data.tables.length}개 테이블</Badge> : undefined}
      >
        <DataTable
          columns={forecastColumns}
          rows={forecast.data?.tables ?? []}
          rowKey={(r) => r.table}
          loading={forecast.isLoading}
          error={forecast.isError ? forecast.error : undefined}
          onRetry={() => forecast.refetch()}
          emptyTitle="예보 테이블 없음"
        />
      </Card>
    </div>
  );
}
