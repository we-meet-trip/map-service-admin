import { useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { dbApi } from '../api/endpoints';
import type { DbColumn, JsonValue } from '../api/types';
import { PageHeader } from '../components/PageHeader';
import { Card } from '../components/Card';
import { DataTable } from '../components/DataTable';
import type { Column, SortState } from '../components/DataTable';
import { Pagination } from '../components/Pagination';
import { Badge } from '../components/Badge';
import { CenterSpinner } from '../components/Spinner';
import { ErrorBanner } from '../components/ErrorBanner';
import { EmptyState } from '../components/EmptyState';
import {
  IconChevronDown,
  IconDownload,
  IconRefresh,
  IconSearch,
} from '../components/Icons';
import { formatCell, formatNumber } from '../lib/format';
import { cn } from '../lib/cn';

const PAGE_LIMIT = 50;

type Row = Record<string, JsonValue>;

function SchemaPanel({ table }: { table: string }) {
  const [open, setOpen] = useState(false);
  const schema = useQuery({
    queryKey: ['db', 'schema', table],
    queryFn: () => dbApi.schema(table),
    enabled: open,
  });

  const columns: Column<DbColumn>[] = [
    { key: 'name', header: '컬럼', render: (c) => <span className="font-mono text-xs text-fg">{c.name}</span> },
    { key: 'data_type', header: '타입', render: (c) => <span className="font-mono text-xs text-fg-muted">{c.data_type}</span> },
    { key: 'udt', header: 'UDT', render: (c) => <span className="font-mono text-xs text-fg-subtle">{c.udt_name}</span> },
    {
      key: 'nullable',
      header: 'NULL 허용',
      render: (c) => (
        <Badge tone={c.is_nullable === 'YES' ? 'neutral' : 'good'}>
          {c.is_nullable === 'YES' ? 'YES' : 'NO'}
        </Badge>
      ),
    },
  ];

  return (
    <Card flush>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-5 py-3 text-left"
        aria-expanded={open}
      >
        <span className="text-sm font-semibold text-fg">스키마 (컬럼 · 인덱스)</span>
        <IconChevronDown
          className={cn('transition-transform text-fg-muted', open && 'rotate-180')}
        />
      </button>
      {open && (
        <div className="border-t border-border">
          {schema.isLoading ? (
            <CenterSpinner />
          ) : schema.isError ? (
            <div className="p-4">
              <ErrorBanner error={schema.error} onRetry={() => schema.refetch()} />
            </div>
          ) : schema.data ? (
            <div className="space-y-4 p-4">
              <div className="overflow-hidden rounded-lg border border-border">
                <DataTable
                  columns={columns}
                  rows={schema.data.columns}
                  rowKey={(c) => c.name}
                  dense
                  emptyTitle="컬럼 정보 없음"
                />
              </div>
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-fg-subtle">
                  인덱스 ({schema.data.indexes.length})
                </p>
                {schema.data.indexes.length === 0 ? (
                  <p className="text-xs text-fg-muted">인덱스 없음</p>
                ) : (
                  <ul className="space-y-1">
                    {schema.data.indexes.map((idx) => (
                      <li
                        key={idx.indexname}
                        className="overflow-x-auto rounded-md border border-border bg-surface-2 px-3 py-1.5 font-mono text-xs text-fg-muted"
                      >
                        <span className="text-fg">{idx.indexname}</span> — {idx.indexdef}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          ) : null}
        </div>
      )}
    </Card>
  );
}

function TableBrowser({ table }: { table: string }) {
  const [qInput, setQInput] = useState('');
  const [q, setQ] = useState('');
  const [sort, setSort] = useState<SortState | null>(null);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [offset, setOffset] = useState(0);

  const [filterCol, setFilterCol] = useState('');
  const [filterVal, setFilterVal] = useState('');

  const sortStr = sort ? `${sort.key}:${sort.dir}` : undefined;

  const rows = useQuery({
    queryKey: ['db', 'rows', table, q, sortStr ?? '', filters, offset],
    queryFn: () =>
      dbApi.rows(table, {
        limit: PAGE_LIMIT,
        offset,
        sort: sortStr,
        q: q || undefined,
        filters,
      }),
    placeholderData: (prev) => prev,
  });

  const data = rows.data;
  const columnNames = data?.columns ?? [];

  const tableColumns: Column<Row>[] = useMemo(
    () =>
      columnNames.map((name) => ({
        key: name,
        header: name,
        sortable: true,
        render: (row: Row) => {
          const val = row[name];
          const text = formatCell(val);
          return (
            <span
              className="line-clamp-2 max-w-[24rem] break-words font-mono text-xs text-fg"
              title={text}
            >
              {text === '' ? <span className="text-fg-subtle">∅</span> : text}
            </span>
          );
        },
      })),
    [columnNames],
  );

  function onSearch(e: FormEvent) {
    e.preventDefault();
    setOffset(0);
    setQ(qInput.trim());
  }

  function addFilter(e: FormEvent) {
    e.preventDefault();
    if (!filterCol || !filterVal.trim()) return;
    setFilters((prev) => ({ ...prev, [filterCol]: filterVal.trim() }));
    setFilterVal('');
    setOffset(0);
  }

  function removeFilter(col: string) {
    setFilters((prev) => {
      const next = { ...prev };
      delete next[col];
      return next;
    });
    setOffset(0);
  }

  const csvUrl = dbApi.exportCsvUrl(table, {
    sort: sortStr,
    q: q || undefined,
    filters,
  });

  const page = Math.floor(offset / PAGE_LIMIT);
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_LIMIT)) : 1;
  const activeFilters = Object.entries(filters);

  return (
    <Card
      flush
      title={<span className="font-mono">{table}</span>}
      description={data ? `${formatNumber(data.total)} 행` : undefined}
      actions={
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => rows.refetch()}
            disabled={rows.isFetching}
          >
            <IconRefresh
              width={16}
              height={16}
              className={rows.isFetching ? 'animate-spin' : ''}
            />
          </button>
          <a className="btn btn-ghost btn-sm" href={csvUrl}>
            <IconDownload width={16} height={16} />
            CSV 내보내기
          </a>
        </div>
      }
    >
      <div className="space-y-3 border-b border-border p-4">
        <form onSubmit={onSearch} className="flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[12rem]">
            <IconSearch
              width={16}
              height={16}
              className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-fg-subtle"
            />
            <input
              className="input pl-8"
              placeholder="전체 텍스트 검색 (q)"
              value={qInput}
              onChange={(e) => setQInput(e.target.value)}
            />
          </div>
          <button type="submit" className="btn btn-primary btn-sm">
            검색
          </button>
        </form>

        <form onSubmit={addFilter} className="flex flex-wrap items-center gap-2">
          <select
            className="input h-9 w-40"
            value={filterCol}
            onChange={(e) => setFilterCol(e.target.value)}
          >
            <option value="">컬럼 필터…</option>
            {columnNames.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <input
            className="input h-9 w-40"
            placeholder="값"
            value={filterVal}
            onChange={(e) => setFilterVal(e.target.value)}
            disabled={!filterCol}
          />
          <button
            type="submit"
            className="btn btn-ghost btn-sm"
            disabled={!filterCol || !filterVal.trim()}
          >
            필터 추가
          </button>
          {activeFilters.map(([col, val]) => (
            <button
              key={col}
              type="button"
              onClick={() => removeFilter(col)}
              className="inline-flex items-center gap-1 rounded-md border border-brand bg-brand-weak px-2 py-1 text-xs text-brand hover:opacity-80"
              title="필터 제거"
            >
              <span className="font-mono">
                {col}={val}
              </span>
              <span aria-hidden="true">×</span>
            </button>
          ))}
        </form>
      </div>

      <DataTable
        columns={tableColumns}
        rows={data?.rows ?? []}
        rowKey={(_row) => {
          const idx = data?.rows.indexOf(_row) ?? 0;
          return `${offset}-${idx}`;
        }}
        loading={rows.isLoading || rows.isFetching}
        error={rows.isError ? rows.error : undefined}
        onRetry={() => rows.refetch()}
        sort={sort}
        onSortChange={(next) => {
          setSort(next);
          setOffset(0);
        }}
        emptyTitle="행 없음"
        emptyMessage="조건에 맞는 행이 없습니다."
        footer={
          data ? (
            <Pagination
              page={page}
              totalPages={totalPages}
              totalElements={data.total}
              pageSize={PAGE_LIMIT}
              onPageChange={(p) => setOffset(p * PAGE_LIMIT)}
              disabled={rows.isFetching}
            />
          ) : undefined
        }
      />
    </Card>
  );
}

export function DbPage() {
  const tables = useQuery({
    queryKey: ['db', 'tables'],
    queryFn: () => dbApi.tables(),
  });

  const [selected, setSelected] = useState<string>('');

  const tableList = tables.data?.tables ?? [];
  const activeTable = selected || tableList[0]?.table || '';

  return (
    <div className="space-y-6">
      <PageHeader
        title="데이터 탐색"
        description={
          tables.data
            ? `스키마 ${tables.data.schema} · 읽기 전용 행 조회`
            : 'hub_data 스키마 읽기 전용 행 조회'
        }
      />

      {tables.isLoading ? (
        <CenterSpinner label="테이블 목록 불러오는 중…" />
      ) : tables.isError ? (
        <ErrorBanner error={tables.error} onRetry={() => tables.refetch()} />
      ) : tableList.length === 0 ? (
        <Card>
          <EmptyState title="테이블 없음" />
        </Card>
      ) : (
        <>
          <Card>
            <div className="flex flex-wrap items-end gap-3">
              <div className="min-w-[16rem] flex-1">
                <label className="label" htmlFor="tableSelect">
                  테이블 선택
                </label>
                <select
                  id="tableSelect"
                  className="input"
                  value={activeTable}
                  onChange={(e) => setSelected(e.target.value)}
                >
                  {tableList.map((t) => (
                    <option key={t.table} value={t.table}>
                      {t.table} ({formatNumber(t.rows)} 행)
                    </option>
                  ))}
                </select>
              </div>
              <div className="text-xs text-fg-muted">
                총 {tableList.length}개 테이블
              </div>
            </div>
          </Card>

          {activeTable && (
            <>
              <SchemaPanel key={`schema-${activeTable}`} table={activeTable} />
              <TableBrowser key={`browser-${activeTable}`} table={activeTable} />
            </>
          )}
        </>
      )}
    </div>
  );
}
