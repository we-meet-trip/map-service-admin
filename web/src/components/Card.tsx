import type { ReactNode } from 'react';
import { cn } from '../lib/cn';

interface CardProps {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  /** Remove body padding (useful when embedding a full-bleed table). */
  flush?: boolean;
}

export function Card({
  title,
  description,
  actions,
  children,
  className,
  bodyClassName,
  flush,
}: CardProps) {
  const hasHeader = title || description || actions;
  return (
    <section className={cn('card overflow-hidden', className)}>
      {hasHeader && (
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-5 py-4">
          <div className="min-w-0">
            {title && (
              <h2 className="text-sm font-semibold text-fg">{title}</h2>
            )}
            {description && (
              <p className="mt-0.5 text-xs text-fg-muted">{description}</p>
            )}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cn(flush ? '' : 'p-5', bodyClassName)}>{children}</div>
    </section>
  );
}
