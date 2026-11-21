import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  FolderOpen,
  Info,
  X,
  XCircle,
} from 'lucide-react';
import type { ToastItem } from '../types';

interface ToastContainerProps {
  toasts: ToastItem[];
  onDismiss: (id: string) => void;
  onOpenPath: (path: string) => void;
  onCopyText: (text: string, label: string) => void;
}

const VARIANT_STYLES: Record<ToastItem['variant'], { border: string; Icon: typeof Info; iconColor: string }> = {
  info: { border: 'border-blue-500/30', Icon: Info, iconColor: 'text-blue-500' },
  success: { border: 'border-emerald-500/30', Icon: CheckCircle2, iconColor: 'text-emerald-500' },
  warn: { border: 'border-amber-500/30', Icon: AlertTriangle, iconColor: 'text-amber-500' },
  error: { border: 'border-rose-500/30', Icon: XCircle, iconColor: 'text-rose-500' },
};

export function ToastContainer({
  toasts,
  onDismiss,
  onOpenPath,
  onCopyText,
}: ToastContainerProps) {
  if (toasts.length === 0) return null;

  return (
    <div className="pointer-events-none fixed bottom-20 right-4 z-50 flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2">
      {toasts.map((toast) => {
        const { border, Icon, iconColor } = VARIANT_STYLES[toast.variant] ?? VARIANT_STYLES.info;
        return (
          <div
            key={toast.id}
            className={`animate-toast pointer-events-auto flex items-start gap-2.5 rounded-xl border ${border} bg-[var(--surface-card)] p-3 shadow-xl shadow-slate-950/15 dark:shadow-black/50`}
          >
            <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${iconColor}`} />
            <div className="min-w-0 flex-1">
              <div className="text-[12.5px] font-semibold text-[var(--ink-primary)]">{toast.title}</div>
              {toast.message && (
                <div className="mt-0.5 break-all text-[11.5px] text-[var(--ink-secondary)]">
                  {toast.message}
                </div>
              )}
              {(toast.actionPath || toast.copyText) && (
                <div className="mt-2 flex items-center gap-2">
                  {toast.actionPath && (
                    <button
                      type="button"
                      onClick={() => onOpenPath(toast.actionPath!)}
                      className="inline-flex items-center gap-1 rounded-md bg-blue-500/10 px-2 py-1 text-[11px] font-semibold text-blue-700 hover:bg-blue-500/20 dark:text-blue-300 cursor-pointer"
                    >
                      <FolderOpen className="h-3 w-3" />
                      <span>{toast.actionLabel || '打开位置'}</span>
                    </button>
                  )}
                  {toast.copyText && (
                    <button
                      type="button"
                      onClick={() => onCopyText(toast.copyText!, 'UDID')}
                      className="inline-flex items-center gap-1 rounded-md bg-emerald-500/10 px-2 py-1 text-[11px] font-semibold text-emerald-700 hover:bg-emerald-500/20 dark:text-emerald-300 cursor-pointer"
                    >
                      <Copy className="h-3 w-3" />
                      <span>复制</span>
                    </button>
                  )}
                </div>
              )}
            </div>
            <button
              type="button"
              onClick={() => onDismiss(toast.id)}
              className="flex h-5 w-5 shrink-0 items-center justify-center rounded text-[var(--ink-muted)] hover:text-[var(--ink-primary)] cursor-pointer"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
