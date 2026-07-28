import type { ReactNode } from 'react';
import { ApiError } from '../api/client';
import { IconAlert, IconRefresh } from './Icons';

interface ErrorBannerProps {
  title?: string;
  error?: unknown;
  message?: ReactNode;
  onRetry?: () => void;
  compact?: boolean;
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  if (typeof error === 'string') return error;
  return '알 수 없는 오류가 발생했습니다.';
}

export function ErrorBanner({
  title = '데이터를 불러오지 못했습니다',
  error,
  message,
  onRetry,
  compact,
}: ErrorBannerProps) {
  const text = message ?? (error !== undefined ? errorMessage(error) : null);
  return (
    <div
      role="alert"
      className={`flex items-start gap-3 rounded-lg border border-critical bg-critical-weak text-critical ${
        compact ? 'px-3 py-2 text-xs' : 'p-4 text-sm'
      }`}
    >
      <IconAlert className="mt-0.5 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="font-semibold">{title}</p>
        {text && <p className="mt-0.5 break-words opacity-90">{text}</p>}
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex shrink-0 items-center gap-1 rounded-md border border-critical px-2 py-1 text-xs font-medium hover:bg-critical hover:text-white"
        >
          <IconRefresh width={14} height={14} />
          재시도
        </button>
      )}
    </div>
  );
}
