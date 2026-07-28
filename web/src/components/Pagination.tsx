import { cn } from '../lib/cn';
import { formatNumber } from '../lib/format';
import { IconChevron } from './Icons';

interface PaginationProps {
  /** Zero-based or one-based page index — display only, controlled by parent. */
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  totalElements?: number;
  pageSize?: number;
  /** Whether `page` counts from 0. Default true (Spring-style). */
  zeroBased?: boolean;
  disabled?: boolean;
}

export function Pagination({
  page,
  totalPages,
  onPageChange,
  totalElements,
  pageSize,
  zeroBased = true,
  disabled,
}: PaginationProps) {
  const display = zeroBased ? page + 1 : page;
  const maxDisplay = Math.max(totalPages, 1);
  const atStart = display <= 1;
  const atEnd = display >= maxDisplay;

  const rangeLabel = (() => {
    if (totalElements === undefined || pageSize === undefined) return null;
    if (totalElements === 0) return '0건';
    const startIdx = (display - 1) * pageSize + 1;
    const endIdx = Math.min(display * pageSize, totalElements);
    return `${formatNumber(startIdx)}–${formatNumber(endIdx)} / ${formatNumber(totalElements)}건`;
  })();

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-1 py-1 text-xs text-fg-muted">
      <span>{rangeLabel ?? `페이지 ${display} / ${maxDisplay}`}</span>
      <div className="flex items-center gap-1">
        <button
          type="button"
          className={cn('btn btn-ghost btn-sm', 'px-2')}
          disabled={disabled || atStart}
          onClick={() => onPageChange(page - 1)}
          aria-label="이전 페이지"
        >
          <IconChevron className="rotate-180" width={16} height={16} />
        </button>
        <span className="min-w-[5rem] text-center tabular-nums">
          {display} / {maxDisplay}
        </span>
        <button
          type="button"
          className={cn('btn btn-ghost btn-sm', 'px-2')}
          disabled={disabled || atEnd}
          onClick={() => onPageChange(page + 1)}
          aria-label="다음 페이지"
        >
          <IconChevron width={16} height={16} />
        </button>
      </div>
    </div>
  );
}
