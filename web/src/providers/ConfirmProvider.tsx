import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from 'react';
import type { ReactNode } from 'react';
import { Modal } from '../components/Modal';
import { Spinner } from '../components/Spinner';
import { cn } from '../lib/cn';

export interface ConfirmRow {
  label: string;
  value: ReactNode;
}

export interface ConfirmOptions {
  title: string;
  /** Short summary of what will happen. */
  summary: ReactNode;
  /** Structured target/impact detail rendered as a definition list. */
  details?: ConfirmRow[];
  /** Extra emphasis line (e.g. "실제 API를 호출하고 쿼터를 소비합니다"). */
  impact?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
}

type ConfirmFn = (opts: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmFn | null>(null);

interface DialogState extends ConfirmOptions {
  open: boolean;
}

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<DialogState | null>(null);
  const [busy, setBusy] = useState(false);
  const resolver = useRef<((v: boolean) => void) | null>(null);

  const confirm = useCallback<ConfirmFn>((opts) => {
    setBusy(false);
    setState({ ...opts, open: true });
    return new Promise<boolean>((resolve) => {
      resolver.current = resolve;
    });
  }, []);

  const settle = useCallback((result: boolean) => {
    resolver.current?.(result);
    resolver.current = null;
    setState((prev) => (prev ? { ...prev, open: false } : prev));
    // Allow the close animation before clearing.
    window.setTimeout(() => setState(null), 150);
  }, []);

  const onConfirm = useCallback(() => {
    // Give the caller a moment of "busy" feedback; the actual await happens
    // in the caller after the promise resolves true.
    setBusy(true);
    settle(true);
  }, [settle]);

  const value = useMemo(() => confirm, [confirm]);

  return (
    <ConfirmContext.Provider value={value}>
      {children}
      {state && (
        <Modal
          open={state.open}
          onClose={() => (busy ? undefined : settle(false))}
          title={state.title}
          size="max-w-md"
          footer={
            <>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => settle(false)}
                disabled={busy}
              >
                {state.cancelLabel ?? '취소'}
              </button>
              <button
                type="button"
                className={cn('btn', state.danger ? 'btn-danger' : 'btn-primary')}
                onClick={onConfirm}
                disabled={busy}
              >
                {busy && <Spinner size={14} />}
                {state.confirmLabel ?? '확인'}
              </button>
            </>
          }
        >
          <div className="space-y-3 text-sm text-fg">
            <p className="text-fg-muted">{state.summary}</p>
            {state.details && state.details.length > 0 && (
              <dl className="divide-y divide-border overflow-hidden rounded-lg border border-border">
                {state.details.map((row, i) => (
                  <div
                    key={i}
                    className="flex items-start justify-between gap-4 bg-surface-2 px-3 py-2"
                  >
                    <dt className="shrink-0 text-xs font-medium text-fg-muted">
                      {row.label}
                    </dt>
                    <dd className="break-all text-right font-mono text-xs text-fg">
                      {row.value}
                    </dd>
                  </div>
                ))}
              </dl>
            )}
            {state.impact && (
              <p
                className={cn(
                  'rounded-lg border px-3 py-2 text-xs',
                  state.danger
                    ? 'border-critical bg-critical-weak text-critical'
                    : 'border-warn bg-warn-weak text-warn',
                )}
              >
                {state.impact}
              </p>
            )}
          </div>
        </Modal>
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirm(): ConfirmFn {
  const ctx = useContext(ConfirmContext);
  if (!ctx) throw new Error('useConfirm must be used within ConfirmProvider');
  return ctx;
}
