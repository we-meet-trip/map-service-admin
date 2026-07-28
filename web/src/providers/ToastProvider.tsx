import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from 'react';
import type { ReactNode } from 'react';
import { cn } from '../lib/cn';
import { IconAlert, IconCheck, IconClose, IconInfo } from '../components/Icons';

export type ToastKind = 'success' | 'error' | 'info';

export interface ToastOptions {
  kind?: ToastKind;
  title: string;
  message?: string;
  /** When present, a subtle "audit #<id>" note is shown. */
  auditId?: number | string | null;
  duration?: number;
}

interface ToastItem extends Required<Omit<ToastOptions, 'message' | 'auditId'>> {
  id: number;
  message?: string;
  auditId?: number | string | null;
}

interface ToastContextValue {
  toast: (opts: ToastOptions) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const KIND_STYLE: Record<
  ToastKind,
  { bar: string; icon: ReactNode; label: string }
> = {
  success: {
    bar: 'bg-good',
    icon: <IconCheck className="text-good" />,
    label: '성공',
  },
  error: {
    bar: 'bg-critical',
    icon: <IconAlert className="text-critical" />,
    label: '오류',
  },
  info: {
    bar: 'bg-brand',
    icon: <IconInfo className="text-brand" />,
    label: '정보',
  },
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const counter = useRef(0);

  const dismiss = useCallback((id: number) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    (opts: ToastOptions) => {
      const id = ++counter.current;
      const item: ToastItem = {
        id,
        kind: opts.kind ?? 'info',
        title: opts.title,
        message: opts.message,
        auditId: opts.auditId ?? null,
        duration: opts.duration ?? 6000,
      };
      setItems((prev) => [...prev, item]);
      if (item.duration > 0) {
        window.setTimeout(() => dismiss(id), item.duration);
      }
    },
    [dismiss],
  );

  const value = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-[min(92vw,22rem)] flex-col gap-2"
        role="region"
        aria-label="알림"
      >
        {items.map((item) => {
          const style = KIND_STYLE[item.kind];
          return (
            <div
              key={item.id}
              role="status"
              className="pointer-events-auto flex animate-slide-in overflow-hidden rounded-xl border border-border bg-surface shadow-pop"
            >
              <div className={cn('w-1 shrink-0', style.bar)} />
              <div className="flex flex-1 items-start gap-3 p-3">
                <div className="mt-0.5 shrink-0">{style.icon}</div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-fg">{item.title}</p>
                  {item.message && (
                    <p className="mt-0.5 break-words text-xs text-fg-muted">
                      {item.message}
                    </p>
                  )}
                  {item.auditId !== null && item.auditId !== undefined && (
                    <p className="mt-1 inline-flex items-center gap-1 rounded-md bg-surface-2 px-1.5 py-0.5 font-mono text-[11px] text-fg-muted">
                      audit #{item.auditId}
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => dismiss(item.id)}
                  className="rounded-md p-1 text-fg-subtle hover:bg-surface-2 hover:text-fg"
                  aria-label="알림 닫기"
                >
                  <IconClose width={14} height={14} />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
}
