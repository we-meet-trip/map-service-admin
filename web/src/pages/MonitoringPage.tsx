import { useQuery } from '@tanstack/react-query';
import { opsApi } from '../api/endpoints';
import { PageHeader } from '../components/PageHeader';
import { Card } from '../components/Card';
import { EmptyState } from '../components/EmptyState';
import { PageSpinner } from '../components/Spinner';
import { ErrorBanner } from '../components/ErrorBanner';
import { IconExternal, IconMonitor, IconRefresh } from '../components/Icons';

export function MonitoringPage() {
  const query = useQuery({
    queryKey: ['ops', 'monitoring'],
    queryFn: () => opsApi.monitoring(),
  });

  if (query.isLoading) return <PageSpinner label="패널 불러오는 중…" />;

  const panels = query.data?.panels ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="모니터링"
        description="외부 대시보드 패널 (Grafana 등) 임베드 및 링크"
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

      {query.isError ? (
        <ErrorBanner error={query.error} onRetry={() => query.refetch()} />
      ) : panels.length === 0 ? (
        <Card>
          <EmptyState
            icon={<IconMonitor width={32} height={32} />}
            title="구성된 패널이 없습니다"
            message="MONITORING_PANELS 환경변수로 대시보드 패널을 구성하면 이곳에 표시됩니다."
          />
        </Card>
      ) : (
        <div className="space-y-6">
          {panels.map((panel, i) => (
            <Card
              key={`${panel.title}-${i}`}
              title={panel.title}
              description={panel.description}
              flush={panel.embed}
              actions={
                <a
                  className="btn btn-ghost btn-sm"
                  href={panel.url}
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  <IconExternal width={16} height={16} />
                  새 탭에서 열기
                </a>
              }
            >
              {panel.embed ? (
                <iframe
                  title={panel.title}
                  src={panel.url}
                  height={panel.height || 400}
                  className="w-full border-0"
                  style={{ height: `${panel.height || 400}px` }}
                  sandbox="allow-scripts allow-same-origin allow-popups"
                  loading="lazy"
                />
              ) : (
                <a
                  href={panel.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="flex items-center gap-3 rounded-lg border border-border bg-surface-2 px-4 py-3 text-sm text-fg hover:border-brand hover:bg-brand-weak"
                >
                  <IconExternal className="text-brand" />
                  <span className="min-w-0 flex-1 truncate font-mono text-xs">
                    {panel.url}
                  </span>
                  <span className="text-fg-muted">열기 →</span>
                </a>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
