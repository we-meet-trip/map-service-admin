import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { actionsApi, opsApi } from '../api/endpoints';
import type { ForbiddenZone, PlaceSourceRow } from '../api/types';
import { PageHeader } from '../components/PageHeader';
import { Card } from '../components/Card';
import { StatTile } from '../components/StatTile';
import { DataTable } from '../components/DataTable';
import type { Column } from '../components/DataTable';
import { Modal } from '../components/Modal';
import { Spinner } from '../components/Spinner';
import { errorMessage } from '../components/ErrorBanner';
import { IconPlus, IconRefresh, IconTrash } from '../components/Icons';
import { useConfirm } from '../providers/ConfirmProvider';
import { useToast } from '../providers/ToastProvider';
import { formatCell, formatDateTime, formatNumber } from '../lib/format';

const SAMPLE_GEOMETRY = `{
  "type": "Polygon",
  "coordinates": [
    [
      [126.97, 37.56],
      [126.99, 37.56],
      [126.99, 37.58],
      [126.97, 37.58],
      [126.97, 37.56]
    ]
  ]
}`;

function geometrySummary(geometry: unknown): string {
  if (geometry && typeof geometry === 'object' && 'type' in geometry) {
    const type = (geometry as { type?: unknown }).type;
    if (typeof type === 'string') return type;
  }
  return formatCell(geometry as never);
}

export function PlacesPage() {
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const { toast } = useToast();

  const stats = useQuery({
    queryKey: ['ops', 'places-stats'],
    queryFn: () => opsApi.placesStats(),
  });
  const zones = useQuery({
    queryKey: ['actions', 'forbidden-zones'],
    queryFn: () => actionsApi.listZones(),
  });

  const [formOpen, setFormOpen] = useState(false);
  const [name, setName] = useState('');
  const [reason, setReason] = useState('');
  const [geometryText, setGeometryText] = useState(SAMPLE_GEOMETRY);
  const [jsonError, setJsonError] = useState<string | null>(null);

  const createZone = useMutation({
    mutationFn: (payload: { name: string; reason?: string; geometry: unknown }) =>
      actionsApi.createZone(payload),
    onSuccess: (zone) => {
      toast({
        kind: 'success',
        title: '금지구역 추가됨',
        message: `${zone.name} (id ${zone.zone_id})`,
      });
      setFormOpen(false);
      setName('');
      setReason('');
      setGeometryText(SAMPLE_GEOMETRY);
      void queryClient.invalidateQueries({ queryKey: ['actions', 'forbidden-zones'] });
    },
    onError: (err) => {
      toast({ kind: 'error', title: '추가 실패', message: errorMessage(err) });
    },
  });

  const deleteZone = useMutation({
    mutationFn: (id: number | string) => actionsApi.deleteZone(id),
    onSuccess: () => {
      toast({ kind: 'success', title: '금지구역 삭제됨' });
      void queryClient.invalidateQueries({ queryKey: ['actions', 'forbidden-zones'] });
    },
    onError: (err) => {
      toast({ kind: 'error', title: '삭제 실패', message: errorMessage(err) });
    },
  });

  async function submitZone() {
    setJsonError(null);
    if (!name.trim()) {
      setJsonError('이름을 입력하세요.');
      return;
    }
    let geometry: unknown;
    try {
      geometry = JSON.parse(geometryText);
    } catch {
      setJsonError('geometry가 유효한 JSON이 아닙니다.');
      return;
    }
    if (
      !geometry ||
      typeof geometry !== 'object' ||
      (geometry as { type?: unknown }).type !== 'Polygon'
    ) {
      setJsonError('geometry는 GeoJSON Polygon 객체여야 합니다 (type: "Polygon").');
      return;
    }
    const ok = await confirm({
      title: '금지구역 추가',
      summary: '새로운 비행 금지구역을 등록합니다.',
      details: [
        { label: '이름', value: name.trim() },
        { label: '형상', value: 'GeoJSON Polygon' },
      ],
      confirmLabel: '추가',
    });
    if (!ok) return;
    createZone.mutate({
      name: name.trim(),
      reason: reason.trim() || undefined,
      geometry,
    });
  }

  async function removeZone(zone: ForbiddenZone) {
    const ok = await confirm({
      title: '금지구역 삭제',
      summary: '이 금지구역을 영구적으로 삭제합니다.',
      details: [
        { label: 'ID', value: zone.zone_id },
        { label: '이름', value: zone.name },
      ],
      impact: '삭제 후에는 복구할 수 없습니다.',
      confirmLabel: '삭제',
      danger: true,
    });
    if (!ok) return;
    deleteZone.mutate(zone.zone_id);
  }

  const sourceColumns: Column<PlaceSourceRow>[] = [
    { key: 'source', header: '소스', render: (r) => <span className="font-medium text-fg">{r.source}</span> },
    {
      key: 'rows',
      header: '행 수',
      align: 'right',
      render: (r) => <span className="tabular-nums">{formatNumber(r.rows)}</span>,
    },
  ];

  const zoneColumns: Column<ForbiddenZone>[] = [
    { key: 'zone_id', header: 'ID', render: (z) => <span className="font-mono text-xs">{z.zone_id}</span> },
    { key: 'name', header: '이름', render: (z) => <span className="font-medium text-fg">{z.name}</span> },
    {
      key: 'reason',
      header: '사유',
      render: (z) => <span className="text-fg-muted">{z.reason ?? '—'}</span>,
    },
    {
      key: 'geometry',
      header: '형상',
      render: (z) => (
        <span className="font-mono text-xs text-fg-muted" title={formatCell(z.geometry)}>
          {geometrySummary(z.geometry)}
        </span>
      ),
    },
    {
      key: 'created_at',
      header: '생성',
      render: (z) => <span className="text-fg-muted">{formatDateTime(z.created_at)}</span>,
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      render: (z) => {
        const busy = deleteZone.isPending && deleteZone.variables === z.zone_id;
        return (
          <button
            type="button"
            className="btn btn-ghost btn-sm text-critical hover:bg-critical-weak"
            onClick={() => removeZone(z)}
            disabled={deleteZone.isPending}
          >
            {busy ? <Spinner size={14} /> : <IconTrash width={14} height={14} />}
            삭제
          </button>
        );
      },
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="장소 · 금지구역"
        description="장소 소스 통계와 비행 금지구역 관리"
        actions={
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => {
              void stats.refetch();
              void zones.refetch();
            }}
          >
            <IconRefresh width={16} height={16} />
            새로고침
          </button>
        }
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <StatTile
          label="전체 장소"
          value={stats.data ? formatNumber(stats.data.total) : '—'}
          tone="brand"
          loading={stats.isLoading}
        />
        <Card title="소스별 분포" className="lg:col-span-2" flush>
          <DataTable
            columns={sourceColumns}
            rows={stats.data?.by_source ?? []}
            rowKey={(r) => r.source}
            loading={stats.isLoading}
            error={stats.isError ? stats.error : undefined}
            onRetry={() => stats.refetch()}
            emptyTitle="소스 데이터 없음"
            dense
          />
        </Card>
      </div>

      <Card
        title="비행 금지구역"
        description="등록된 금지구역 목록"
        flush
        actions={
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => setFormOpen(true)}
          >
            <IconPlus width={16} height={16} />
            구역 추가
          </button>
        }
      >
        <DataTable
          columns={zoneColumns}
          rows={zones.data ?? []}
          rowKey={(z) => z.zone_id}
          loading={zones.isLoading}
          error={zones.isError ? zones.error : undefined}
          onRetry={() => zones.refetch()}
          emptyTitle="등록된 금지구역 없음"
          emptyMessage="상단의 ‘구역 추가’로 새 금지구역을 등록하세요."
        />
      </Card>

      <Modal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        title="금지구역 추가"
        size="max-w-xl"
        footer={
          <>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => setFormOpen(false)}
              disabled={createZone.isPending}
            >
              취소
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={submitZone}
              disabled={createZone.isPending}
            >
              {createZone.isPending && <Spinner size={16} />}
              추가
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="label" htmlFor="zoneName">
              이름 <span className="text-critical">*</span>
            </label>
            <input
              id="zoneName"
              className="input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="예: 공항 인근 제한구역"
            />
          </div>
          <div>
            <label className="label" htmlFor="zoneReason">
              사유 (선택)
            </label>
            <input
              id="zoneReason"
              className="input"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="예: 관제권"
            />
          </div>
          <div>
            <label className="label" htmlFor="zoneGeometry">
              형상 (GeoJSON Polygon)
            </label>
            <textarea
              id="zoneGeometry"
              className="input min-h-[10rem] font-mono text-xs"
              value={geometryText}
              onChange={(e) => setGeometryText(e.target.value)}
              spellCheck={false}
            />
          </div>
          {jsonError && (
            <p className="rounded-lg border border-critical bg-critical-weak px-3 py-2 text-xs text-critical">
              {jsonError}
            </p>
          )}
        </div>
      </Modal>
    </div>
  );
}
