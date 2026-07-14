import type { ReactNode } from 'react';

interface EmptyStateProps {
  title?: string;
  message?: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
}

export function EmptyState({
  title = '표시할 데이터가 없습니다',
  message,
  icon,
  action,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-12 text-center">
      {icon && <div className="text-fg-subtle">{icon}</div>}
      <div>
        <p className="text-sm font-medium text-fg">{title}</p>
        {message && (
          <p className="mx-auto mt-1 max-w-md text-xs text-fg-muted">{message}</p>
        )}
      </div>
      {action}
    </div>
  );
}
