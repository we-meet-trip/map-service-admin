import { cn } from '../lib/cn';

interface SpinnerProps {
  size?: number;
  className?: string;
  label?: string;
}

export function Spinner({ size = 18, className, label }: SpinnerProps) {
  return (
    <span
      className={cn('inline-flex items-center gap-2', className)}
      role="status"
      aria-live="polite"
    >
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        className="animate-spin"
        aria-hidden="true"
      >
        <circle
          cx="12"
          cy="12"
          r="9"
          stroke="currentColor"
          strokeWidth="3"
          className="opacity-20"
        />
        <path
          d="M21 12a9 9 0 0 0-9-9"
          stroke="currentColor"
          strokeWidth="3"
          strokeLinecap="round"
        />
      </svg>
      {label && <span className="text-sm text-fg-muted">{label}</span>}
    </span>
  );
}

export function PageSpinner({ label = '불러오는 중…' }: { label?: string }) {
  return (
    <div className="flex min-h-[40vh] items-center justify-center text-brand">
      <Spinner size={26} label={label} />
    </div>
  );
}

export function CenterSpinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center py-12 text-brand">
      <Spinner size={22} label={label} />
    </div>
  );
}
