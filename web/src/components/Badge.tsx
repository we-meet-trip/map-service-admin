import type { ReactNode } from 'react';
import { cn } from '../lib/cn';

export type BadgeTone =
  | 'neutral'
  | 'good'
  | 'warn'
  | 'serious'
  | 'critical'
  | 'brand'
  | 'info';

const TONE: Record<BadgeTone, string> = {
  neutral: 'bg-surface-2 text-fg-muted border-border',
  good: 'bg-good-weak text-good border-good',
  warn: 'bg-warn-weak text-warn border-warn',
  serious: 'bg-serious-weak text-serious border-serious',
  critical: 'bg-critical-weak text-critical border-critical',
  brand: 'bg-brand-weak text-brand border-brand',
  info: 'bg-info-weak text-info border-info',
};

interface BadgeProps {
  tone?: BadgeTone;
  children: ReactNode;
  className?: string;
  icon?: ReactNode;
}

export function Badge({ tone = 'neutral', children, className, icon }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs font-medium',
        TONE[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}

interface BoolBadgeProps {
  value: boolean | null | undefined;
  trueLabel?: string;
  falseLabel?: string;
}

/** Boolean shown as a labelled badge — never colour alone. */
export function BoolBadge({
  value,
  trueLabel = '예',
  falseLabel = '아니오',
}: BoolBadgeProps) {
  if (value === null || value === undefined) return <Badge>—</Badge>;
  return (
    <Badge tone={value ? 'good' : 'neutral'}>{value ? trueLabel : falseLabel}</Badge>
  );
}
