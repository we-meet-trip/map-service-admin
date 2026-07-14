import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { opsApi } from '../api/endpoints';
import type { ExternalProvider, ProbeResult } from '../api/types';
import { PageHeader } from '../components/PageHeader';
import { Card } from '../components/Card';
import { DataTable } from '../components/DataTable';
import type { Column } from '../components/DataTable';
import { BoolBadge } from '../components/Badge';
import { Spinner } from '../components/Spinner';
import { IconBolt, IconRefresh } from '../components/Icons';
import { useConfirm } from '../providers/ConfirmProvider';
import { useToast } from '../providers/ToastProvider';
import { errorMessage } from '../components/ErrorBanner';
import { formatCell, formatLatency, formatNumber } from '../lib/format';

export function ExternalPage() {
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const { toast } = useToast();

  const query = useQuery({
    queryKey: ['ops', 'external'],
    queryFn: () => opsApi.external(),
  });

  const probe = useMutation({
    mutationFn: (provider: string) => opsApi.probe(provider),
    onSuccess: (result: ProbeResult) => {
      toast({
        kind: result.ok ? 'success' : 'error',
        title: `${result.provider} 프로브 ${result.ok ? '성공' : '실패'}`,
        message: `지연 ${formatLatency(result.latency_ms)} · ${formatCell(result.detail)}`,
        auditId: result.audit_id,
      });
      void queryClient.invalidateQueries({ queryKey: ['ops', 'external'] });
    },
    onError: (err) => {
      toast({ kind: 'error', title: '프로브 실패', message: errorMessage(err) });
    },
  });

  async function handleProbe(p: ExternalProvider) {
    const ok = await confirm({
      title: `${p.label} 실시간 프로브`,
      summary: '이 제공자에 실제 요청을 보내 연결 상태를 확인합니다.',
      details: [
        { label: '제공자', value: p.provider },
        { label: '구성됨', value: p.configured ? '예' : '아니오' },
      ],
      impact: '실제 외부 API를 호출하며 해당 제공자의 쿼터를 소비할 수 있습니다.',
      confirmLabel: '프로브 실행',
    });
    if (!ok) return;
    probe.mutate(p.provider);
  }

  const columns: Column<ExternalProvider>[] = [
    {
      key: 'provider',
      header: '제공자',
      render: (p) => (
        <div>
          <p className="font-medium text-fg">{p.label}</p>
          <p className="font-mono text-xs text-fg-subtle">{p.provider}</p>
        </div>
      ),
    },
    {
      key: 'configured',
      header: '구성',
      render: (p) => (
        <BoolBadge value={p.configured} trueLabel="구성됨" falseLabel="미구성" />
      ),
    },
    {
      key: 'key',
      header: '키(마스킹)',
      render: (p) =>
        p.key_masked ? (
          <span className="font-mono text-xs text-fg-muted">{p.key_masked}</span>
        ) : (
          <span className="text-fg-subtle">—</span>
        ),
    },
    {
      key: 'cache',
      header: '캐시 키',
      align: 'right',
      render: (p) =>
        p.cache_keys != null ? (
          <span className="tabular-nums text-fg-muted">
            {formatNumber(p.cache_keys)}
          </span>
        ) : (
          <span className="text-fg-subtle">—</span>
        ),
    },
    {
      key: 'quota',
      header: '쿼터',
      render: (p) =>
        p.quota != null ? (
          <span
            className="line-clamp-1 max-w-[16rem] font-mono text-xs text-fg-muted"
            title={formatCell(p.quota)}
          >
            {formatCell(p.quota)}
          </span>
        ) : (
          <span className="text-fg-subtle">—</span>
        ),
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      render: (p) => {
        const busy = probe.isPending && probe.variables === p.provider;
        return (
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => handleProbe(p)}
            disabled={probe.isPending}
          >
            {busy ? <Spinner size={14} /> : <IconBolt width={14} height={14} />}
            프로브
          </button>
        );
      },
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="외부 API"
        description="외부 제공자 구성 상태와 마스킹된 키, 수동 실시간 프로브"
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

      <Card flush>
        <DataTable
          columns={columns}
          rows={query.data?.providers ?? []}
          rowKey={(p) => p.provider}
          loading={query.isLoading}
          error={query.isError ? query.error : undefined}
          onRetry={() => query.refetch()}
          emptyTitle="제공자 없음"
          emptyMessage="구성된 외부 제공자가 없습니다."
        />
      </Card>

      <p className="flex items-center gap-2 text-xs text-fg-subtle">
        <IconBolt width={14} height={14} />
        프로브는 실제 API 호출을 수행하며 모든 실행은 감사 로그에 기록됩니다.
      </p>
    </div>
  );
}
