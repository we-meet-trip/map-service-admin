import { prettyJson } from '../lib/format';

interface JsonBlockProps {
  value: unknown;
  className?: string;
  maxHeight?: string;
}

export function JsonBlock({ value, className, maxHeight = '20rem' }: JsonBlockProps) {
  return (
    <pre
      className={`overflow-auto rounded-lg border border-border bg-surface-2 p-3 font-mono text-xs leading-relaxed text-fg ${className ?? ''}`}
      style={{ maxHeight }}
    >
      {prettyJson(value)}
    </pre>
  );
}
