import { useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { usersApi } from '../api/endpoints';
import type { UserListItem } from '../api/types';
import { PageHeader } from '../components/PageHeader';
import { Card } from '../components/Card';
import { DataTable } from '../components/DataTable';
import type { Column } from '../components/DataTable';
import { Pagination } from '../components/Pagination';
import { Badge, BoolBadge } from '../components/Badge';
import { Modal } from '../components/Modal';
import { CenterSpinner } from '../components/Spinner';
import { ErrorBanner } from '../components/ErrorBanner';
import { IconInfo, IconSearch } from '../components/Icons';
import { formatDateTime } from '../lib/format';

const PAGE_SIZE = 20;

function DetailRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-border py-2 last:border-0 sm:flex-row sm:items-center sm:justify-between">
      <dt className="text-xs font-medium text-fg-muted">{label}</dt>
      <dd className="break-all text-sm text-fg sm:text-right">{value}</dd>
    </div>
  );
}

function UserDetailModal({
  userId,
  onClose,
}: {
  userId: string | number;
  onClose: () => void;
}) {
  const detail = useQuery({
    queryKey: ['users', 'detail', userId],
    queryFn: () => usersApi.detail(userId),
  });

  return (
    <Modal open onClose={onClose} title="사용자 상세" size="max-w-lg">
      <div className="mb-3 flex items-center gap-2 rounded-lg border border-warn bg-warn-weak px-3 py-2 text-xs text-warn">
        <IconInfo width={14} height={14} className="shrink-0" />
        전체 이메일 열람은 감사 로그에 기록됩니다 (열람 기록됨).
      </div>
      {detail.isLoading ? (
        <CenterSpinner label="상세 불러오는 중…" />
      ) : detail.isError ? (
        <ErrorBanner error={detail.error} onRetry={() => detail.refetch()} />
      ) : detail.data ? (
        <dl>
          <DetailRow label="ID" value={<span className="font-mono">{detail.data.id}</span>} />
          <DetailRow label="이메일" value={<span className="font-mono">{detail.data.email}</span>} />
          <DetailRow label="닉네임" value={detail.data.nickname} />
          <DetailRow label="인증 제공자" value={<Badge tone="neutral">{detail.data.authProvider}</Badge>} />
          <DetailRow
            label="이메일 인증"
            value={<BoolBadge value={detail.data.emailVerified} trueLabel="인증됨" falseLabel="미인증" />}
          />
          <DetailRow
            label="프로필 이미지"
            value={
              detail.data.profileImageUrl ? (
                <a
                  href={detail.data.profileImageUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="text-brand hover:underline"
                >
                  링크
                </a>
              ) : (
                '—'
              )
            }
          />
          <DetailRow label="가입일" value={formatDateTime(detail.data.createdAt)} />
          <DetailRow label="수정일" value={formatDateTime(detail.data.updatedAt)} />
        </dl>
      ) : null}
    </Modal>
  );
}

export function UsersPage() {
  const [queryInput, setQueryInput] = useState('');
  const [submitted, setSubmitted] = useState('');
  const [page, setPage] = useState(0);
  const [selectedId, setSelectedId] = useState<string | number | null>(null);

  const list = useQuery({
    queryKey: ['users', 'list', submitted, page],
    queryFn: () => usersApi.list(submitted, page, PAGE_SIZE),
    placeholderData: (prev) => prev,
  });

  function onSearch(e: FormEvent) {
    e.preventDefault();
    setPage(0);
    setSubmitted(queryInput.trim());
  }

  const columns: Column<UserListItem>[] = [
    { key: 'id', header: 'ID', render: (u) => <span className="font-mono text-xs">{u.id}</span> },
    {
      key: 'email',
      header: '이메일(마스킹)',
      render: (u) => <span className="font-mono text-xs text-fg">{u.emailMasked}</span>,
    },
    { key: 'nickname', header: '닉네임', render: (u) => <span className="text-fg">{u.nickname}</span> },
    {
      key: 'provider',
      header: '제공자',
      render: (u) => <Badge tone="neutral">{u.authProvider}</Badge>,
    },
    {
      key: 'verified',
      header: '인증',
      render: (u) => (
        <BoolBadge value={u.emailVerified} trueLabel="인증됨" falseLabel="미인증" />
      ),
    },
    {
      key: 'created',
      header: '가입일',
      render: (u) => <span className="text-fg-muted">{formatDateTime(u.createdAt)}</span>,
    },
  ];

  const data = list.data;

  return (
    <div className="space-y-6">
      <PageHeader
        title="사용자"
        description="사용자 검색 및 상세 조회 · 전체 이메일 열람은 감사됩니다"
      />

      <Card
        flush
        title="사용자 목록"
        actions={
          <form onSubmit={onSearch} className="flex items-center gap-2">
            <div className="relative">
              <IconSearch
                width={16}
                height={16}
                className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-fg-subtle"
              />
              <input
                className="input w-52 pl-8"
                placeholder="닉네임·이메일 검색"
                value={queryInput}
                onChange={(e) => setQueryInput(e.target.value)}
              />
            </div>
            <button type="submit" className="btn btn-primary btn-sm">
              검색
            </button>
          </form>
        }
      >
        <DataTable
          columns={columns}
          rows={data?.items ?? []}
          rowKey={(u) => u.id}
          loading={list.isLoading || list.isFetching}
          error={list.isError ? list.error : undefined}
          onRetry={() => list.refetch()}
          onRowClick={(u) => setSelectedId(u.id)}
          emptyTitle="사용자 없음"
          emptyMessage={submitted ? `‘${submitted}’ 검색 결과가 없습니다.` : undefined}
          footer={
            data ? (
              <Pagination
                page={page}
                totalPages={data.totalPages}
                totalElements={data.totalElements}
                pageSize={data.size || PAGE_SIZE}
                onPageChange={setPage}
                disabled={list.isFetching}
              />
            ) : undefined
          }
        />
      </Card>

      {selectedId !== null && (
        <UserDetailModal userId={selectedId} onClose={() => setSelectedId(null)} />
      )}
    </div>
  );
}
