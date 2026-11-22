import type { MouseEvent } from 'react';
import {
  Copy,
  Minus,
  Monitor,
  Moon,
  PackageCheck,
  Settings,
  Square,
  Sun,
  Wrench,
  X,
} from 'lucide-react';
import type { ThemeMode, ToolDiagnostic } from '../types';

interface HeaderBarProps {
  version: string;
  theme: ThemeMode;
  tools: Record<string, ToolDiagnostic>;
  maximized: boolean;
  onThemeChange: (mode: ThemeMode) => void;
  onOpenSettings: () => void;
  onStartDrag: () => void;
  onStartResize: (edge: string) => void;
  onMinimize: () => void;
  onToggleMaximize: () => void;
  onClose: () => void;
}

const THEME_CYCLE: { mode: ThemeMode; label: string; Icon: typeof Sun }[] = [
  { mode: 'light', label: '浅色', Icon: Sun },
  { mode: 'dark', label: '深色', Icon: Moon },
  { mode: 'system', label: '跟随系统', Icon: Monitor },
];

export function HeaderBar({
  version,
  theme,
  tools,
  maximized,
  onThemeChange,
  onOpenSettings,
  onStartDrag,
  onStartResize,
  onMinimize,
  onToggleMaximize,
  onClose,
}: HeaderBarProps) {
  const adbOk = tools.adb?.available ?? false;
  const hdcOk = tools.hdc?.available ?? false;
  const toolsLoaded = Object.keys(tools).length > 0;
  const allDeviceToolsOk = adbOk && hdcOk;
  const anyDeviceToolOk = adbOk || hdcOk;

  const statusTone = !toolsLoaded
    ? 'bg-slate-500/10 text-slate-600 dark:text-slate-300 border-slate-500/20'
    : allDeviceToolsOk
      ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/20'
      : anyDeviceToolOk
        ? 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20'
        : 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-500/20';

  const statusDot = !toolsLoaded
    ? 'bg-slate-400 animate-pulse'
    : allDeviceToolsOk
      ? 'bg-emerald-500'
      : anyDeviceToolOk
        ? 'bg-amber-500'
        : 'bg-rose-500';

  const statusText = !toolsLoaded
    ? '工具链检测中…'
    : allDeviceToolsOk
      ? 'ADB · HDC 就绪'
      : adbOk
        ? 'ADB 就绪 · HDC 未配置'
        : hdcOk
          ? 'HDC 就绪 · ADB 未配置'
          : '工具链待配置';

  const handleHeaderMouseDown = (e: MouseEvent<HTMLElement>) => {
    if (e.button !== 0) return;
    const target = e.target as HTMLElement | null;
    if (target?.closest('button, input, a, [data-no-drag]')) {
      return;
    }
    if (e.detail >= 2) {
      onToggleMaximize();
      return;
    }
    onStartDrag();
  };

  return (
    <header
      onMouseDown={handleHeaderMouseDown}
      className="relative flex h-10 shrink-0 items-center justify-between border-b border-[var(--border-hairline)] bg-[var(--surface-card)] pl-3.5 pr-1 select-none"
    >
      {/* Top edge & top corners resize hotspots for borderless Win32 frame */}
      {!maximized && (
        <div className="pointer-events-auto absolute inset-x-0 top-0 z-30 flex h-[4px]">
          <div
            data-no-drag
            onMouseDown={(e) => {
              if (e.button === 0) {
                e.stopPropagation();
                onStartResize('top-left');
              }
            }}
            className="h-full w-2.5 cursor-nwse-resize"
          />
          <div
            data-no-drag
            onMouseDown={(e) => {
              if (e.button === 0) {
                e.stopPropagation();
                onStartResize('top');
              }
            }}
            className="h-full flex-1 cursor-ns-resize"
          />
          <div
            data-no-drag
            onMouseDown={(e) => {
              if (e.button === 0) {
                e.stopPropagation();
                onStartResize('top-right');
              }
            }}
            className="h-full w-2.5 cursor-nesw-resize"
          />
        </div>
      )}

      {/* Brand title */}
      <div className="flex min-w-0 items-center gap-2">
        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-gradient-to-br from-blue-600 to-indigo-600 text-white shadow-xs shadow-blue-600/25">
          <PackageCheck className="h-3.5 w-3.5" />
        </div>
        <div className="flex items-baseline gap-1.5 min-w-0">
          <h1 className="truncate text-[13.5px] font-semibold tracking-tight text-[var(--ink-primary)]">
            APK / HAP 安装工具
          </h1>
          <span className="font-mono-code shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[10.5px] font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400">
            v{version}
          </span>
        </div>
      </div>

      {/* Tools, theme, settings + integrated window controls */}
      <div className="flex shrink-0 items-center gap-1.5">
        <button
          type="button"
          onClick={onOpenSettings}
          title="查看 ADB / HDC / AAPT2 / Restool 环境诊断"
          className={`flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium transition-opacity hover:opacity-85 cursor-pointer ${statusTone}`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${statusDot}`} />
          <span>{statusText}</span>
          <Wrench className="ml-0.5 h-3 w-3 opacity-70" />
        </button>

        <div className="flex items-center rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-subtle)] p-0.5">
          {THEME_CYCLE.map(({ mode, label, Icon }) => {
            const active = theme === mode;
            return (
              <button
                key={mode}
                type="button"
                title={`主题：${label}`}
                onClick={() => onThemeChange(mode)}
                className={`flex h-5.5 w-5.5 items-center justify-center rounded-md transition-all cursor-pointer ${
                  active
                    ? 'bg-[var(--surface-card)] text-blue-600 shadow-xs dark:text-blue-400'
                    : 'text-[var(--ink-muted)] hover:text-[var(--ink-primary)]'
                }`}
              >
                <Icon className="h-3 w-3" />
              </button>
            );
          })}
        </div>

        <button
          type="button"
          onClick={onOpenSettings}
          title="设置与环境诊断"
          className="flex h-6.5 w-6.5 items-center justify-center rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-subtle)] text-[var(--ink-secondary)] transition-colors hover:bg-slate-200/70 hover:text-[var(--ink-primary)] dark:hover:bg-slate-700/60 cursor-pointer"
        >
          <Settings className="h-3.5 w-3.5" />
        </button>

        <div className="mx-0.5 h-4 w-px bg-[var(--border-hairline)]" />

        <div className="flex items-center">
          <button
            type="button"
            onClick={onMinimize}
            title="最小化"
            aria-label="最小化"
            className="flex h-8 w-9 items-center justify-center rounded-md text-[var(--ink-secondary)] transition-colors hover:bg-slate-200/70 hover:text-[var(--ink-primary)] dark:hover:bg-slate-700/60 cursor-pointer"
          >
            <Minus className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={onToggleMaximize}
            title={maximized ? '向下还原' : '最大化'}
            aria-label={maximized ? '向下还原' : '最大化'}
            className="flex h-8 w-9 items-center justify-center rounded-md text-[var(--ink-secondary)] transition-colors hover:bg-slate-200/70 hover:text-[var(--ink-primary)] dark:hover:bg-slate-700/60 cursor-pointer"
          >
            {maximized ? <Copy className="h-3 w-3 -scale-x-100" /> : <Square className="h-3 w-3" />}
          </button>
          <button
            type="button"
            onClick={onClose}
            title="关闭"
            aria-label="关闭"
            className="flex h-8 w-9 items-center justify-center rounded-md text-[var(--ink-secondary)] transition-colors hover:bg-rose-600 hover:text-white cursor-pointer"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </header>
  );
}
