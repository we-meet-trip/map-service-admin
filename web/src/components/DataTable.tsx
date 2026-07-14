import type { ReactNode } from 'react';
import { cn } from '../lib/cn';
import { CenterSpinner } from './Spinner';
import { EmptyState } from './EmptyState';
import { ErrorBanner } from './ErrorBanner';
import { IconSort, IconSortAsc, IconSortDesc } from './Icons';

export type SortDir = 'asc' | 'desc';
export interface SortState {
  key: string;
  dir: SortDir;
}

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  sortable?: boolean;
  align?: 'left' | 'right' | 'center';
  className?: string;
  headerClassName?: string;
  width?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  loading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  emptyTitle?: string;
  emptyMessage?: ReactNode;
  sort?: SortState | null;
  onSortChange?: (next: SortState) => void;
  onRowClick?: (row: T) => void;
  footer?: ReactNode;
  dense?: boolean;
  /** Row highlight predicate (e.g. failed rows). */
  rowClassName?: (row: T) => string | undefined;
}

const ALIGN: Record<'left' | 'right' | 'center', string> = {
  left: 'text-left',
  right: 'text-right',
  center: 'text-center',
};

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading,
  error,
  onRetry,
  emptyTitle,
  emptyMessage,
  sort,
  onSortChange,
  onRowClick,
  footer,
  dense,
  rowClassName,
}: DataTableProps<T>) {
  const colCount = columns.length;

  function handleSort(col: Column<T>) {
    if (!col.sortable || !onSortChange) return;
    if (sort && sort.key === col.key) {
      onSortChange({ key: col.key, dir: sort.dir === 'asc' ? 'desc' : 'asc' });
    } else {
      onSortChange({ key: col.key, dir: 'asc' });
    }
  }

  return (
    <div className="flex flex-col">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-border bg-surface-2">
              {columns.map((col) => {
                const active = sort?.key === col.key;
                const align = col.align ?? 'left';
                return (
                  <th
                    key={col.key}
                    scope="col"
                    style={col.width ? { width: col.width } : undefined}
                    className={cn(
                      'whitespace-nowrap px-3 py-2.5 text-xs font-semibold uppercase tracking-wide text-fg-muted',
                      ALIGN[align],
                      col.headerClassName,
                    )}
                    aria-sort={
                      active
                        ? sort?.dir === 'asc'
                          ? 'ascending'
                          : 'descending'
                        : undefined
                    }
                  >
                    {col.sortable ? (
                      <button
                        type="button"
                        onClick={() => handleSort(col)}
                        className={cn(
                          'inline-flex items-center gap-1 hover:text-fg',
                          align === 'right' && 'flex-row-reverse',
                          active && 'text-fg',
                        )}
                      >
                        <span>{col.header}</span>
                        {active ? (
                          sort?.dir === 'asc' ? (
                            <IconSortAsc width={14} height={14} />
                          ) : (
                            <IconSortDesc width={14} height={14} />
                          )
                        ) : (
                          <IconSort
                            width={14}
                            height={14}
                            className="opacity-40"
                          />
                        )}
                      </button>
                    ) : (
                      col.header
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {loading && rows.length === 0 ? (
              <tr>
                <td colSpan={colCount} className="p-0">
                  <CenterSpinner />
                </td>
              </tr>
            ) : error ? (
              <tr>
                <td colSpan={colCount} className="p-4">
                  <ErrorBanner error={error} onRetry={onRetry} />
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={colCount} className="p-0">
                  <EmptyState title={emptyTitle} message={emptyMessage} />
                </td>
              </tr>
            ) : (
              rows.map((row) => {
                const clickable = Boolean(onRowClick);
                return (
                  <tr
                    key={rowKey(row)}
                    onClick={clickable ? () => onRowClick?.(row) : undefined}
                    className={cn(
                      'border-b border-border transition-colors last:border-0',
                      clickable && 'cursor-pointer hover:bg-surface-2',
                      !clickable && 'hover:bg-surface-2',
                      rowClassName?.(row),
                    )}
                  >
                    {columns.map((col) => (
                      <td
                        key={col.key}
                        className={cn(
                          dense ? 'px-3 py-1.5' : 'px-3 py-2.5',
                          'align-middle text-fg',
                          ALIGN[col.align ?? 'left'],
                          col.className,
                        )}
                      >
                        {col.render(row)}
                      </td>
                    ))}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
      {loading && rows.length > 0 && (
        <div className="h-0.5 w-full overflow-hidden bg-transparent">
          <div className="h-full w-1/3 animate-pulse rounded-full bg-brand" />
        </div>
      )}
      {footer && <div className="border-t border-border px-3 py-2">{footer}</div>}
    </div>
  );
}
