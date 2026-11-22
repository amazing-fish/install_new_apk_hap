import { Monitor, Moon, PackageCheck, Settings, Sun, Wrench } from 'lucide-react';
import type { ThemeMode, ToolDiagnostic } from '../types';

interface HeaderBarProps {
  version: string;
  theme: ThemeMode;
  tools: Record<string, ToolDiagnostic>;
  onThemeChange: (mode: ThemeMode) => void;
  onOpenSettings: () => void;
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
  onThemeChange,
  onOpenSettings,
}: HeaderBarProps) {
  const adbOk = tools.adb?.available ?? false;
  const hdcOk = tools.hdc?.available ?? false;
  const allDeviceToolsOk = adbOk && hdcOk;
  const anyDeviceToolOk = adbOk || hdcOk;

  const statusTone = allDeviceToolsOk
    ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/20'
    : anyDeviceToolOk
      ? 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20'
      : 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-500/20';

  const statusDot = allDeviceToolsOk
    ? 'bg-emerald-500'
    : anyDeviceToolOk
      ? 'bg-amber-500'
      : 'bg-rose-500';

  const statusText = allDeviceToolsOk
    ? 'ADB · HDC 就绪'
    : adbOk
      ? 'ADB 就绪 · HDC 未配置'
      : hdcOk
        ? 'HDC 就绪 · ADB 未配置'
        : '工具链待配置';

  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-[var(--border-hairline)] bg-[var(--surface-card)] px-4 select-none">
      <div className="flex items-center gap-2.5">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-blue-600 to-indigo-600 text-white shadow-sm shadow-blue-600/25">
          <PackageCheck className="h-4 w-4" />
        </div>
        <div className="flex items-baseline gap-2">
          <h1 className="text-[14px] font-semibold tracking-tight text-[var(--ink-primary)]">
            APK / HAP 安装工具
          </h1>
          <span className="font-mono-code rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400">
            v{version}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onOpenSettings}
          title="查看 ADB / HDC / AAPT2 / Restool 环境诊断"
          className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11.5px] font-medium transition-opacity hover:opacity-85 cursor-pointer ${statusTone}`}
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
                className={`flex h-6 w-6 items-center justify-center rounded-md transition-all cursor-pointer ${
                  active
                    ? 'bg-[var(--surface-card)] text-blue-600 shadow-xs dark:text-blue-400'
                    : 'text-[var(--ink-muted)] hover:text-[var(--ink-primary)]'
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
              </button>
            );
          })}
        </div>

        <button
          type="button"
          onClick={onOpenSettings}
          title="设置与环境诊断"
          className="flex h-7 w-7 items-center justify-center rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-subtle)] text-[var(--ink-secondary)] transition-colors hover:bg-slate-200/70 hover:text-[var(--ink-primary)] dark:hover:bg-slate-700/60 cursor-pointer"
        >
          <Settings className="h-3.5 w-3.5" />
        </button>
      </div>
    </header>
  );
}
