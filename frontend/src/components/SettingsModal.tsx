import { useEffect, useRef, useState } from 'react';
import {
  CheckCircle2,
  FolderOpen,
  Monitor,
  Moon,
  RefreshCw,
  RotateCcw,
  Sun,
  X,
  XCircle,
  Zap,
} from 'lucide-react';
import type { AppSettings, ThemeMode, ToolDiagnostic } from '../types';

interface SettingsModalProps {
  open: boolean;
  settings: AppSettings;
  tools: Record<string, ToolDiagnostic>;
  onClose: () => void;
  onUpdateSettings: (updates: Partial<AppSettings>) => void;
  onChooseLogDir: () => void;
  onRefreshDiagnostics: () => Promise<void>;
}

const TOOL_LABELS: Record<string, { name: string; role: string }> = {
  adb: { name: 'ADB', role: 'Android 设备探测、安装与崩溃日志' },
  hdc: { name: 'HDC', role: 'Harmony 设备探测、安装、UDID 与日志' },
  aapt2: { name: 'AAPT2', role: 'APK 应用名、版本号与 testOnly 解析' },
  restool: { name: 'RestoolV2', role: 'HAP 资源型应用名称解析' },
};

export function SettingsModal({
  open,
  settings,
  tools,
  onClose,
  onUpdateSettings,
  onChooseLogDir,
  onRefreshDiagnostics,
}: SettingsModalProps) {
  const [checking, setChecking] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    const prevFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const dialog = dialogRef.current;
    const focusables = () =>
      Array.from(
        dialog?.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      );
    const initial = focusables()[0] ?? dialog;
    initial?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onCloseRef.current();
        return;
      }
      if (e.key === 'Tab' && dialog) {
        const items = focusables();
        if (items.length === 0) {
          e.preventDefault();
          return;
        }
        const first = items[0];
        const last = items[items.length - 1];
        const active = document.activeElement;
        if (e.shiftKey) {
          if (active === first || !dialog.contains(active)) {
            e.preventDefault();
            last.focus();
          }
        } else if (active === last || !dialog.contains(active)) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      prevFocus?.focus();
    };
  }, [open]);

  if (!open) return null;

  const handleRecheck = async () => {
    setChecking(true);
    try {
      await onRefreshDiagnostics();
    } finally {
      setChecking(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4 backdrop-blur-[2px]"
      onClick={onClose}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="设置与工具链诊断"
        tabIndex={-1}
        className="flex max-h-[85vh] w-full max-w-xl flex-col overflow-hidden rounded-2xl border border-[var(--border-hairline)] bg-[var(--surface-card)] shadow-2xl outline-none"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[var(--border-hairline)] px-5 py-3.5">
          <h3 className="text-[14.5px] font-semibold text-[var(--ink-primary)]">设置与工具链诊断</h3>
          <button
            type="button"
            onClick={onClose}
            className="flex h-7 w-7 items-center justify-center rounded-lg text-[var(--ink-secondary)] hover:bg-[var(--surface-subtle)] hover:text-[var(--ink-primary)] cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          {/* Theme */}
          <div className="space-y-2">
            <label className="text-[12.5px] font-semibold text-[var(--ink-primary)]">外观主题</label>
            <div className="grid grid-cols-3 gap-2">
              {(
                [
                  ['light', '浅色模式', Sun],
                  ['dark', '深色模式', Moon],
                  ['system', '跟随系统', Monitor],
                ] as [ThemeMode, string, typeof Sun][]
              ).map(([mode, label, Icon]) => {
                const active = settings.theme === mode;
                return (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => onUpdateSettings({ theme: mode })}
                    className={`flex items-center justify-center gap-2 rounded-xl border px-3 py-2 text-[12.5px] font-medium transition-all cursor-pointer ${
                      active
                        ? 'border-blue-500 bg-blue-500/10 text-blue-700 dark:text-blue-300'
                        : 'border-[var(--border-hairline)] bg-[var(--surface-subtle)] text-[var(--ink-secondary)] hover:text-[var(--ink-primary)]'
                    }`}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    <span>{label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Parallel Install */}
          <div className="space-y-2.5 rounded-xl border border-[var(--border-hairline)] bg-[var(--surface-subtle)] p-3.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Zap className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                <div>
                  <div className="text-[12.5px] font-semibold text-[var(--ink-primary)]">多设备并行安装</div>
                  <div className="text-[11px] text-[var(--ink-muted)]">
                    选中多台设备时并发下发安装命令，显著减少批量装机耗时
                  </div>
                </div>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={settings.parallelInstall}
                onClick={() => onUpdateSettings({ parallelInstall: !settings.parallelInstall })}
                className={`relative h-5 w-9 rounded-full transition-colors cursor-pointer ${
                  settings.parallelInstall ? 'bg-blue-600' : 'bg-slate-300 dark:bg-slate-700'
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
                    settings.parallelInstall ? 'translate-x-4' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>

            {settings.parallelInstall && (
              <div className="flex items-center justify-between border-t border-[var(--border-hairline)] pt-2.5">
                <span className="text-[12px] text-[var(--ink-secondary)]">最大并发数</span>
                <div className="flex items-center gap-1.5">
                  {[2, 4, 6, 8].map((n) => (
                    <button
                      key={n}
                      type="button"
                      onClick={() => onUpdateSettings({ maxConcurrency: n })}
                      className={`h-6 w-8 rounded-md text-[11.5px] font-semibold transition-colors cursor-pointer ${
                        settings.maxConcurrency === n
                          ? 'bg-blue-600 text-white'
                          : 'border border-[var(--border-hairline)] bg-[var(--surface-card)] text-[var(--ink-secondary)] hover:text-[var(--ink-primary)]'
                      }`}
                    >
                      {n}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Log output dir */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-[12.5px] font-semibold text-[var(--ink-primary)]">日志导出目录</label>
              {settings.logOutputDir && (
                <button
                  type="button"
                  onClick={() => onUpdateSettings({ logOutputDir: '' })}
                  className="inline-flex items-center gap-1 text-[11px] font-medium text-blue-600 hover:underline dark:text-blue-400 cursor-pointer"
                >
                  <RotateCcw className="h-3 w-3" />
                  恢复默认 ({settings.defaultLogOutputDir})
                </button>
              )}
            </div>
            <div className="flex items-center gap-2">
              <input
                readOnly
                value={settings.logOutputDir || `${settings.defaultLogOutputDir}（默认）`}
                className="font-mono-code h-8 flex-1 rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-subtle)] px-2.5 text-[11.5px] text-[var(--ink-secondary)]"
              />
              <button
                type="button"
                onClick={onChooseLogDir}
                className="flex h-8 items-center gap-1.5 rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-card)] px-3 text-[12px] font-medium text-[var(--ink-primary)] hover:bg-[var(--surface-subtle)] cursor-pointer"
              >
                <FolderOpen className="h-3.5 w-3.5 text-blue-600 dark:text-blue-400" />
                <span>更改</span>
              </button>
            </div>
          </div>

          {/* Tool diagnostics */}
          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <label className="text-[12.5px] font-semibold text-[var(--ink-primary)]">工具链环境诊断</label>
              <button
                type="button"
                disabled={checking}
                onClick={handleRecheck}
                className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] font-medium text-blue-600 hover:bg-blue-500/10 dark:text-blue-400 cursor-pointer"
              >
                <RefreshCw className={`h-3 w-3 ${checking ? 'animate-spin' : ''}`} />
                <span>重新检测</span>
              </button>
            </div>

            <div className="divide-y divide-[var(--border-hairline)] overflow-hidden rounded-xl border border-[var(--border-hairline)] bg-[var(--surface-subtle)]">
              {Object.entries(TOOL_LABELS).map(([key, meta]) => {
                const info = tools[key];
                const ok = info?.available ?? false;
                return (
                  <div key={key} className="flex items-start gap-2.5 px-3 py-2.5">
                    {ok ? (
                      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
                    ) : (
                      <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-500" />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[12.5px] font-semibold text-[var(--ink-primary)]">{meta.name}</span>
                        <span className="text-[11px] text-[var(--ink-muted)]">{meta.role}</span>
                      </div>
                      <p className="font-mono-code mt-0.5 break-all text-[11px] text-[var(--ink-secondary)]">
                        {ok ? info?.path : info?.error || '未检测到'}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end border-t border-[var(--border-hairline)] px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg bg-blue-600 px-4 py-1.5 text-[12.5px] font-semibold text-white hover:bg-blue-700 cursor-pointer"
          >
            完成
          </button>
        </div>
      </div>
    </div>
  );
}
