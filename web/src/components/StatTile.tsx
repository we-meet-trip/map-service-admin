import type { ReactNode } from 'react';
import { cn } from '../lib/cn';

export type StatTone = 'neutral' | 'good' | 'warn' | 'serious' | 'critical' | 'brand';

const TONE_ACCENT: Record<StatTone, string> = {
  neutral: 'text-fg',
  good: 'text-good',
  warn: 'text-warn',
  serious: 'text-serious',
  critical: 'text-critical',
  brand: 'text-brand',
};

const TONE_ICON_BG: Record<StatTone, string> = {
  neutral: 'bg-surface-2 text-fg-muted',
  good: 'bg-good-weak text-good',
  warn: 'bg-warn-weak text-warn',
  serious: 'bg-serious-weak text-serious',
  critical: 'bg-critical-weak text-critical',
  brand: 'bg-brand-weak text-brand',
};

interface StatTileProps {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
  tone?: StatTone;
  loading?: boolean;
}

export function StatTile({
  label,
  value,
  hint,
  icon,
  tone = 'neutral',
  loading,
}: StatTileProps) {
  return (
    <div className="card flex items-start gap-3 p-4">
      {icon && (
        <div
          className={cn(
            'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg',
            TONE_ICON_BG[tone],
          )}
          aria-hidden="true"
        >
          {icon}
        </div>
      )}
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-medium uppercase tracking-wide text-fg-subtle">
          {label}
        </p>
        {loading ? (
          <div className="mt-2 h-7 w-16 animate-pulse rounded bg-surface-2" />
        ) : (
          <p
            className={cn(
              'mt-1 text-2xl font-semibold leading-tight',
              TONE_ACCENT[tone],
            )}
          >
            {value}
          </p>
        )}
        {hint && !loading && (
          <p className="mt-1 truncate text-xs text-fg-muted">{hint}</p>
        )}
      </div>
    </div>
  );
}
