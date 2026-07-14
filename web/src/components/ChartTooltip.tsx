import type { TooltipProps } from 'recharts';
import { formatNumber } from '../lib/format';

/** Theme-aware tooltip for Recharts (uses design tokens). */
export function ChartTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs shadow-pop">
      {label !== undefined && (
        <p className="mb-1 font-medium text-fg">{String(label)}</p>
      )}
      {payload.map((entry, i) => (
        <p key={i} className="flex items-center gap-2 text-fg-muted">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ backgroundColor: entry.color }}
          />
          <span>{entry.name}</span>
          <span className="ml-auto font-semibold text-fg">
            {typeof entry.value === 'number'
              ? formatNumber(entry.value)
              : String(entry.value)}
          </span>
        </p>
      ))}
    </div>
  );
}
