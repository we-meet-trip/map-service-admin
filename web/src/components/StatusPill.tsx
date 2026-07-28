import { cn } from '../lib/cn';

export type StatusLevel = 'ok' | 'warn' | 'serious' | 'down' | 'unknown';

const LEVEL_STYLE: Record<
  StatusLevel,
  { dot: string; text: string; bg: string; label: string }
> = {
  ok: {
    dot: 'bg-good',
    text: 'text-good',
    bg: 'bg-good-weak border-good',
    label: '정상',
  },
  warn: {
    dot: 'bg-warn',
    text: 'text-warn',
    bg: 'bg-warn-weak border-warn',
    label: '주의',
  },
  serious: {
    dot: 'bg-serious',
    text: 'text-serious',
    bg: 'bg-serious-weak border-serious',
    label: '경고',
  },
  down: {
    dot: 'bg-critical',
    text: 'text-critical',
    bg: 'bg-critical-weak border-critical',
    label: '중단',
  },
  unknown: {
    dot: 'bg-fg-subtle',
    text: 'text-fg-muted',
    bg: 'bg-surface-2 border-border',
    label: '미확인',
  },
};

interface StatusPillProps {
  level: StatusLevel;
  /** Override the default Korean label. Color is never used alone. */
  label?: string;
  className?: string;
}

export function StatusPill({ level, label, className }: StatusPillProps) {
  const style = LEVEL_STYLE[level];
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium',
        style.bg,
        style.text,
        className,
      )}
    >
      <span
        className={cn('h-2 w-2 shrink-0 rounded-full', style.dot)}
        aria-hidden="true"
      />
      {label ?? style.label}
    </span>
  );
}
