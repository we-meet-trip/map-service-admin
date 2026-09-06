import { useQuery } from '@tanstack/react-query';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { opsApi } from '../api/endpoints';
import type { HealthItem } from '../api/types';
import { PageHeader } from '../components/PageHeader';
import { StatTile } from '../components/StatTile';
import { Card } from '../components/Card';
import { DataTable } from '../components/DataTable';
import type { Column } from '../components/DataTable';
import { StatusPill } from '../components/StatusPill';
import { Badge } from '../components/Badge';
import { ErrorBanner } from '../components/ErrorBanner';
import { EmptyState } from '../components/EmptyState';
import { ChartTooltip } from '../components/ChartTooltip';
import { PageSpinner } from '../components/Spinner';
import { IconBolt, IconCloud, IconDatabase, IconJobs, IconRefresh } from '../components/Icons';
import { formatLatency, formatNumber, formatRelative } from '../lib/format';
import { healthLevel } from '../lib/status';

export function OverviewPage() {
  const query = useQuery({
    queryKey: ['ops', 'overview'],
    queryFn: () => opsApi.overview(),
    refetchInterval: 30_000,
  });

  const data = query.data;

  if (query.isLoading) return <PageSpinner label="개요 불러오는 중…" />;
  if (query.isError || !data) {
    return (
      <div className="space-y-6">
        <PageHeader title="개요" />
        <ErrorBanner error={query.error} onRetry={() => query.refetch()} />
      </div>
    );
  }

  const health = data.health ?? [];
  const upCount = health.filter((h) => h.ok).length;
  const total = health.length;
  const allUp = total > 0 && upCount === total;

  const gemini = data.gemini_quota;
  const geminiRatio =
    gemini && gemini.daily_cap > 0 ? gemini.daily_remaining / gemini.daily_cap : 1;
  const dlqLen = data.streams?.dlq?.length;

  const healthColumns: Column<HealthItem>[] = [
    {
      key: 'service',
      header: '서비스',
      render: (r) => (
        <div className="flex items-center gap-2">
          <span className="font-medium text-fg">{r.service}</span>
          <Badge tone="neutral">{r.kind}</Badge>
        </div>
      ),
    },
    {
      key: 'status',
      header: '상태',
      render: (r) => <StatusPill level={healthLevel(r)} />,
    },
    {
      key: 'latency',
      header: '지연',
      align: 'right',
      render: (r) => (
        <span className="tabular-nums text-fg-muted">
          {formatLatency(r.latency_ms)}
        </span>
      ),
    },
    {
      key: 'http',
      header: 'HTTP',
      align: 'right',
      render: (r) =>
        r.http_status ? (
          <span className="tabular-nums text-fg-muted">{r.http_status}</span>
        ) : (
          <span className="text-fg-subtle">—</span>
        ),
    },
    {
      key: 'detail',
      header: '비고',
      render: (r) =>
        r.error ? (
          <span className="text-critical" title={r.error}>
            {r.error}
          </span>
        ) : r.configured === false ? (
          <span className="text-fg-subtle">미구성</span>
        ) : (
          <span className="text-fg-subtle">—</span>
        ),
    },
  ];

  const chartData =
    data.places?.by_source.map((s) => ({ source: s.source, rows: s.rows })) ?? [];

  const sectionErrors = Object.entries(data.errors ?? {});

  return (
    <div className="space-y-6">
      <PageHeader
        title="개요"
        description="서비스 헬스와 핵심 운영 지표 롤업 (30초마다 자동 갱신)"
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

      {sectionErrors.length > 0 && (
        <div className="space-y-2">
          {sectionErrors.map(([section, msg]) => (
            <ErrorBanner
              key={section}
              compact
              title={`${section} 섹션 오류`}
              message={msg}
            />
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <StatTile
          label="서비스 정상"
          value={`${upCount}/${total || '—'}`}
          hint={allUp ? '전체 정상' : `${total - upCount}개 비정상`}
          tone={allUp ? 'good' : upCount === 0 ? 'critical' : 'warn'}
          icon={<IconBolt />}
        />
        <StatTile
          label="활성 격자"
          value={
            data.polling ? formatNumber(data.polling.grids.active_grids) : '—'
          }
          hint={
            data.polling
              ? `총 ${formatNumber(data.polling.grids.total_grids)} 격자`
              : '데이터 없음'
          }
          tone="brand"
          icon={<IconCloud />}
        />
        <StatTile
          label="Gemini 일일 사용"
          value={gemini ? formatNumber(gemini.daily_used) : '—'}
          hint={
            gemini
              ? `한도 ${formatNumber(gemini.daily_cap)} · 잔여 ${formatNumber(gemini.daily_remaining)}`
              : '데이터 없음'
          }
          tone={geminiRatio < 0.1 ? 'critical' : geminiRatio < 0.25 ? 'warn' : 'good'}
          icon={<IconBolt />}
        />
        <StatTile
          label="DLQ 길이"
          value={dlqLen === undefined ? '—' : formatNumber(dlqLen)}
          hint={dlqLen === undefined ? '조회 불가' : dlqLen > 0 ? '확인 필요' : '비어 있음'}
          tone={dlqLen === undefined ? 'warn' : dlqLen > 0 ? 'critical' : 'good'}
          icon={<IconJobs />}
        />
        <StatTile
          label="스트림 완료"
          value={data.streams?.done ? formatNumber(data.streams.done.length) : '—'}
          hint={data.streams?.done?.stream ?? '조회 불가'}
          tone="neutral"
          icon={<IconDatabase />}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card
          title="서비스 헬스"
          description="내부 서비스 및 외부 의존성 프로브"
          className="xl:col-span-2"
          flush
        >
          <DataTable
            columns={healthColumns}
            rows={health}
            rowKey={(r) => `${r.service}:${r.kind}`}
            emptyTitle="헬스 데이터 없음"
          />
        </Card>

        <Card title="장소 소스 분포" description="by_source 행 수">
          {chartData.length === 0 ? (
            <EmptyState title="장소 데이터 없음" />
          ) : (
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={chartData}
                  margin={{ top: 8, right: 8, bottom: 8, left: 0 }}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="var(--color-border)"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="source"
                    tick={{ fill: 'var(--color-fg-muted)', fontSize: 12 }}
                    tickLine={false}
                    axisLine={{ stroke: 'var(--color-border)' }}
                  />
                  <YAxis
                    tick={{ fill: 'var(--color-fg-muted)', fontSize: 12 }}
                    tickLine={false}
                    axisLine={false}
                    width={40}
                  />
                  <Tooltip
                    cursor={{ fill: 'var(--color-surface-2)' }}
                    content={<ChartTooltip />}
                  />
                  <Bar
                    dataKey="rows"
                    name="행 수"
                    fill="var(--color-brand)"
                    radius={[4, 4, 0, 0]}
                    maxBarSize={48}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
          {data.places && (
            <p className="mt-3 text-xs text-fg-muted">
              전체 장소{' '}
              <span className="font-semibold text-fg">
                {formatNumber(data.places.total)}
              </span>
              개
            </p>
          )}
        </Card>
      </div>

      <p className="text-right text-xs text-fg-subtle">
        마지막 갱신 {formatRelative(new Date(query.dataUpdatedAt).toISOString())}
      </p>
    </div>
  );
}
