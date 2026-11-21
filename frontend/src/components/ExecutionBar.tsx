import { Download, Loader2, OctagonX, Zap } from 'lucide-react';
import type { ActiveTask, DeviceItem } from '../types';

interface ExecutionBarProps {
  devices: DeviceItem[];
  selectedDeviceIds: string[];
  task: ActiveTask | null;
  scanning: boolean;
  installStatus: string;
  parallelInstall: boolean;
  maxConcurrency: number;
  hasAnyPackage: boolean;
  onToggleParallel: () => void;
  onPrimaryAction: () => void;
}

export function ExecutionBar({
  devices,
  selectedDeviceIds,
  task,
  scanning,
  installStatus,
  parallelInstall,
  maxConcurrency,
  hasAnyPackage,
  onToggleParallel,
  onPrimaryAction,
}: ExecutionBarProps) {
  const selectedDevices = devices.filter((d) => selectedDeviceIds.includes(d.deviceId));
  const summaryText =
    selectedDevices.length > 0
      ? `已选 ${selectedDevices.length} 台：${selectedDevices
          .map((d) => d.name || d.model || d.deviceId)
          .join('，')}`
      : devices.length === 1
        ? `将自动安装到唯一设备：${devices[0].name || devices[0].model || devices[0].deviceId}`
        : '未选择设备';

  const statusTone =
    installStatus === '安装完成' || installStatus.endsWith('完成')
      ? 'bg-emerald-500/12 text-emerald-700 dark:text-emerald-300'
      : installStatus.includes('失败') || installStatus.includes('异常')
        ? 'bg-rose-500/12 text-rose-700 dark:text-rose-300'
        : installStatus.includes('中止') || installStatus.includes('未完成')
          ? 'bg-amber-500/12 text-amber-700 dark:text-amber-300'
          : task
            ? 'bg-blue-500/12 text-blue-700 dark:text-blue-300'
            : 'bg-slate-500/10 text-slate-600 dark:text-slate-400';

  const isRunning = Boolean(task);
  const isCancelling = Boolean(task?.cancelled);

  return (
    <footer className="flex shrink-0 items-center justify-between gap-4 border-t border-[var(--border-hairline)] bg-[var(--surface-card)] px-4 py-3 select-none">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${statusTone}`}>
            {isRunning && <Loader2 className="h-3 w-3 animate-spin" />}
            {installStatus}
          </span>
          <span className="truncate text-[12.5px] font-medium text-[var(--ink-primary)]" title={summaryText}>
            {summaryText}
          </span>
        </div>

        <div className="mt-1 flex items-center gap-3 text-[11px] text-[var(--ink-muted)]">
          <button
            type="button"
            disabled={isRunning}
            onClick={onToggleParallel}
            title="开启后多设备将并行执行安装，大幅缩短多机耗时"
            className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-medium transition-colors cursor-pointer disabled:opacity-50 ${
              parallelInstall
                ? 'bg-blue-500/10 text-blue-700 dark:text-blue-300'
                : 'bg-[var(--surface-subtle)] text-[var(--ink-secondary)]'
            }`}
          >
            <Zap className="h-3 w-3" />
            <span>{parallelInstall ? `并行安装 (${maxConcurrency}路)` : '顺序安装'}</span>
          </button>
          <span className="hidden sm:inline">快捷键：F5 刷新 · Ctrl+Enter 安装 · Esc 中止</span>
        </div>
      </div>

      <button
        type="button"
        disabled={isCancelling || (!isRunning && (!hasAnyPackage || scanning))}
        onClick={onPrimaryAction}
        title={scanning && !isRunning ? '正在扫描安装包目录，请稍候…' : undefined}
        className={`flex h-10 shrink-0 items-center gap-2 rounded-xl px-5 text-[13px] font-semibold shadow-sm transition-all active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer ${
          isRunning
            ? 'bg-rose-600 text-white shadow-rose-600/25 hover:bg-rose-700'
            : 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-blue-600/25 hover:brightness-105'
        }`}
      >
        {isRunning ? (
          <>
            {isCancelling ? <Loader2 className="h-4 w-4 animate-spin" /> : <OctagonX className="h-4 w-4" />}
            <span>{isCancelling ? '正在中止…' : `中止${task!.label}`}</span>
          </>
        ) : scanning ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>扫描安装包中…</span>
          </>
        ) : (
          <>
            <Download className="h-4 w-4" />
            <span>
              {selectedDevices.length > 0 ? `安装到所选设备 (${selectedDevices.length})` : '安装到所选设备'}
            </span>
          </>
        )}
      </button>
    </footer>
  );
}
