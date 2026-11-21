import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  Bug,
  Check,
  CheckSquare,
  ChevronDown,
  Copy,
  FileArchive,
  Fingerprint,
  Loader2,
  Pencil,
  RefreshCw,
  Smartphone,
  Sparkles,
  Square,
  X,
  XCircle,
} from 'lucide-react';
import type {
  ActiveTask,
  AppLogTargetItem,
  DeviceInstallProgress,
  DeviceItem,
} from '../types';

interface DevicePanelProps {
  devices: DeviceItem[];
  selectedDeviceIds: string[];
  deviceErrors: Record<string, string>;
  lastProbeFailed: boolean;
  refreshing: boolean;
  task: ActiveTask | null;
  deviceProgress: Record<string, DeviceInstallProgress>;
  appLogTargets: AppLogTargetItem[];
  onRefresh: () => void;
  onSelectChange: (ids: string[]) => void;
  onSaveName: (deviceId: string, name: string) => void;
  onCopyId: (deviceId: string, label: string) => void;
  onFetchUdid: () => void;
  onFetchCrashLog: () => void;
  onFetchAppLog: (targetKey: string) => void;
}

type PlatformFilter = 'all' | 'android' | 'harmony';

export function DevicePanel({
  devices,
  selectedDeviceIds,
  deviceErrors,
  lastProbeFailed,
  refreshing,
  task,
  deviceProgress,
  appLogTargets,
  onRefresh,
  onSelectChange,
  onSaveName,
  onCopyId,
  onFetchUdid,
  onFetchCrashLog,
  onFetchAppLog,
}: DevicePanelProps) {
  const [filter, setFilter] = useState<PlatformFilter>('all');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftName, setDraftName] = useState('');
  const [appLogOpen, setAppLogOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setAppLogOpen(false);
      }
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  const counts = useMemo(() => {
    let android = 0;
    let harmony = 0;
    for (const d of devices) {
      if (d.platform === 'android') android += 1;
      else if (d.platform === 'harmony') harmony += 1;
    }
    return { total: devices.length, android, harmony };
  }, [devices]);

  const filteredDevices = useMemo(() => {
    if (filter === 'all') return devices;
    return devices.filter((d) => d.platform === filter);
  }, [devices, filter]);

  const selectedSet = useMemo(() => new Set(selectedDeviceIds), [selectedDeviceIds]);

  // Single-device target resolution mirrors backend `resolve_target`.
  const targetDevice = useMemo(() => {
    if (selectedDeviceIds.length === 1) {
      return devices.find((d) => d.deviceId === selectedDeviceIds[0]) ?? null;
    }
    if (selectedDeviceIds.length === 0 && !lastProbeFailed && devices.length === 1) {
      return devices[0];
    }
    return null;
  }, [devices, selectedDeviceIds, lastProbeFailed]);

  const busy = refreshing || Boolean(task);
  const canUdid = !busy && Boolean(targetDevice?.supportsUdid);
  const canCrashLog = !busy && Boolean(targetDevice);
  const canAppLog = !busy && Boolean(targetDevice?.hasAppLogs);

  const toggleSelect = (deviceId: string) => {
    if (selectedSet.has(deviceId)) {
      onSelectChange(selectedDeviceIds.filter((id) => id !== deviceId));
    } else {
      onSelectChange([...selectedDeviceIds, deviceId]);
    }
  };

  const selectAllVisible = () => {
    const visibleIds = filteredDevices.map((d) => d.deviceId);
    const allSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedSet.has(id));
    if (allSelected) {
      onSelectChange(selectedDeviceIds.filter((id) => !visibleIds.includes(id)));
    } else {
      onSelectChange(Array.from(new Set([...selectedDeviceIds, ...visibleIds])));
    }
  };

  const startEdit = (device: DeviceItem) => {
    setEditingId(device.deviceId);
    setDraftName(device.name);
  };

  const commitEdit = (deviceId: string) => {
    setEditingId(null);
    onSaveName(deviceId, draftName);
  };

  const allVisibleSelected =
    filteredDevices.length > 0 && filteredDevices.every((d) => selectedSet.has(d.deviceId));

  const errorList = Object.entries(deviceErrors);

  return (
    <section className="flex flex-col rounded-xl border border-[var(--border-hairline)] bg-[var(--surface-card)] shadow-xs">
      {/* Header + Action Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-hairline)] px-3.5 py-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1.5">
            <Smartphone className="h-4 w-4 text-blue-600 dark:text-blue-400" />
            <h2 className="text-[13px] font-semibold text-[var(--ink-primary)]">连接设备</h2>
          </div>

          {/* Platform filter pills */}
          <div className="flex items-center rounded-lg bg-[var(--surface-subtle)] p-0.5 border border-[var(--border-hairline)]">
            {(
              [
                ['all', `全部 ${counts.total}`],
                ['android', `Android ${counts.android}`],
                ['harmony', `Harmony ${counts.harmony}`],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setFilter(key)}
                className={`rounded-md px-2 py-0.5 text-[11px] font-medium transition-all cursor-pointer ${
                  filter === key
                    ? 'bg-[var(--surface-card)] text-[var(--ink-primary)] shadow-xs'
                    : 'text-[var(--ink-secondary)] hover:text-[var(--ink-primary)]'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {filteredDevices.length > 0 && (
            <button
              type="button"
              onClick={selectAllVisible}
              className="flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] font-medium text-[var(--ink-secondary)] transition-colors hover:bg-[var(--surface-subtle)] hover:text-[var(--ink-primary)] cursor-pointer"
            >
              {allVisibleSelected ? (
                <CheckSquare className="h-3.5 w-3.5 text-blue-600 dark:text-blue-400" />
              ) : (
                <Square className="h-3.5 w-3.5" />
              )}
              <span>{allVisibleSelected ? '取消全选' : '全选'}</span>
            </button>
          )}
        </div>

        {/* Device operations */}
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            disabled={refreshing}
            onClick={onRefresh}
            title="并行探测 ADB / HDC 设备并重新扫描安装包 (F5)"
            className="flex items-center gap-1.5 rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-subtle)] px-2.5 py-1.5 text-[12px] font-medium text-[var(--ink-primary)] transition-colors hover:bg-slate-200/70 disabled:opacity-50 dark:hover:bg-slate-700/50 cursor-pointer"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin text-blue-500' : ''}`} />
            <span>{refreshing ? '刷新中…' : '刷新设备'}</span>
          </button>

          <button
            type="button"
            disabled={!canUdid}
            onClick={onFetchUdid}
            title={
              canUdid
                ? '获取当前 Harmony 设备的 UDID 并复制到剪贴板'
                : '需选中单台 Harmony 设备（或仅连接一台 Harmony 设备）'
            }
            className="flex items-center gap-1.5 rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-card)] px-2.5 py-1.5 text-[12px] font-medium text-[var(--ink-primary)] transition-colors hover:bg-[var(--surface-subtle)] disabled:cursor-not-allowed disabled:opacity-45 cursor-pointer"
          >
            {task?.action === 'udid' ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-sky-500" />
            ) : (
              <Fingerprint className="h-3.5 w-3.5 text-sky-600 dark:text-sky-400" />
            )}
            <span>{task?.action === 'udid' ? '获取中…' : '获取 UDID'}</span>
          </button>

          <button
            type="button"
            disabled={!canCrashLog}
            onClick={onFetchCrashLog}
            title={
              canCrashLog
                ? '拉取目标设备的崩溃日志（Android dropbox / Harmony 近 7 天 ZIP）'
                : '需选中单台目标设备'
            }
            className="flex items-center gap-1.5 rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-card)] px-2.5 py-1.5 text-[12px] font-medium text-[var(--ink-primary)] transition-colors hover:bg-[var(--surface-subtle)] disabled:cursor-not-allowed disabled:opacity-45 cursor-pointer"
          >
            {task?.action === 'crash_log' ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-amber-500" />
            ) : (
              <Bug className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
            )}
            <span>{task?.action === 'crash_log' ? '拉取中…' : '崩溃日志'}</span>
          </button>

          {/* Harmony APP Log dropdown */}
          <div className="relative" ref={menuRef}>
            <button
              type="button"
              disabled={!canAppLog}
              onClick={() => setAppLogOpen((v) => !v)}
              title={
                canAppLog
                  ? '直接拉取 Harmony 应用沙箱日志并打包 ZIP'
                  : '仅支持单台 Harmony 设备'
              }
              className="flex items-center gap-1.5 rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-card)] px-2.5 py-1.5 text-[12px] font-medium text-[var(--ink-primary)] transition-colors hover:bg-[var(--surface-subtle)] disabled:cursor-not-allowed disabled:opacity-45 cursor-pointer"
            >
              {task?.action === 'app_log' ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-500" />
              ) : (
                <FileArchive className="h-3.5 w-3.5 text-indigo-600 dark:text-indigo-400" />
              )}
              <span>{task?.action === 'app_log' ? `${task.name}中…` : 'APP 日志'}</span>
              <ChevronDown className="h-3 w-3 opacity-60" />
            </button>

            {appLogOpen && canAppLog && (
              <div className="absolute right-0 z-30 mt-1.5 w-52 overflow-hidden rounded-xl border border-[var(--border-hairline)] bg-[var(--surface-card)] p-1 shadow-lg shadow-slate-900/10 dark:shadow-black/40">
                {appLogTargets.map((target) => (
                  <button
                    key={target.key}
                    type="button"
                    onClick={() => {
                      setAppLogOpen(false);
                      onFetchAppLog(target.key);
                    }}
                    className="flex w-full flex-col items-start rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-[var(--surface-subtle)] cursor-pointer"
                  >
                    <span className="text-[12.5px] font-medium text-[var(--ink-primary)]">
                      {target.displayName}
                    </span>
                    <span className="font-mono-code mt-0.5 w-full truncate text-[10.5px] text-[var(--ink-muted)]">
                      {target.remotePath}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Probe error banner */}
      {errorList.length > 0 && (
        <div className="flex flex-col gap-1 border-b border-amber-500/20 bg-amber-500/8 px-3.5 py-2 text-[11.5px] text-amber-800 dark:text-amber-200">
          {errorList.map(([platform, msg]) => (
            <div key={platform} className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
              <span className="line-clamp-2">
                <strong className="font-semibold uppercase">{platform}</strong> 探测异常：{msg}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Device list */}
      <div className="max-h-[216px] overflow-y-auto divide-y divide-[var(--border-hairline)]">
        {filteredDevices.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-1.5 py-8 text-center">
            <Smartphone className="h-7 w-7 text-[var(--ink-muted)] opacity-50" />
            <p className="text-[12.5px] font-medium text-[var(--ink-secondary)]">
              {devices.length === 0 ? '未检测到已连接的 Android 或 Harmony 设备' : '当前筛选条件下无设备'}
            </p>
            <p className="text-[11.5px] text-[var(--ink-muted)]">
              请连接 USB 调试后点击右上角「刷新设备」或按 F5
            </p>
          </div>
        ) : (
          filteredDevices.map((device) => {
            const isSelected = selectedSet.has(device.deviceId);
            const isEditing = editingId === device.deviceId;
            const progress = deviceProgress[device.deviceId];
            const isOnline = device.status === 'device';
            const isAndroid = device.platform === 'android';

            return (
              <div
                key={device.deviceId}
                onClick={() => {
                  if (!isEditing) toggleSelect(device.deviceId);
                }}
                onDoubleClick={() => startEdit(device)}
                className={`group flex items-center gap-3 px-3.5 py-2.5 transition-colors cursor-pointer ${
                  isSelected
                    ? 'bg-blue-500/[0.06] dark:bg-blue-500/[0.11]'
                    : device.isNew
                      ? 'bg-emerald-500/[0.05] hover:bg-emerald-500/[0.09]'
                      : 'hover:bg-[var(--surface-subtle)]'
                }`}
              >
                {/* Checkbox */}
                <div
                  className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-all ${
                    isSelected
                      ? 'border-blue-600 bg-blue-600 text-white dark:border-blue-500 dark:bg-blue-500'
                      : 'border-slate-300 bg-transparent dark:border-slate-600'
                  }`}
                >
                  {isSelected && <Check className="h-3 w-3 stroke-[3]" />}
                </div>

                {/* Platform badge */}
                <span
                  className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-semibold tracking-wide ${
                    isAndroid
                      ? 'bg-emerald-500/12 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300'
                      : 'bg-sky-500/12 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300'
                  }`}
                >
                  {device.platformLabel}
                </span>

                {/* Main info: Name / Inline rename + model + device ID */}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    {isEditing ? (
                      <div
                        className="flex items-center gap-1.5"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <input
                          autoFocus
                          value={draftName}
                          onChange={(e) => setDraftName(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') commitEdit(device.deviceId);
                            if (e.key === 'Escape') setEditingId(null);
                          }}
                          placeholder="输入设备备注名（留空清除）"
                          className="h-6 w-48 rounded-md border border-blue-500 bg-[var(--surface-card)] px-2 text-[12.5px] text-[var(--ink-primary)] outline-none ring-2 ring-blue-500/20"
                        />
                        <button
                          type="button"
                          onClick={() => commitEdit(device.deviceId)}
                          className="flex h-6 w-6 items-center justify-center rounded-md bg-blue-600 text-white hover:bg-blue-700 cursor-pointer"
                          title="保存 (Enter)"
                        >
                          <Check className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditingId(null)}
                          className="flex h-6 w-6 items-center justify-center rounded-md border border-[var(--border-hairline)] text-[var(--ink-secondary)] hover:bg-[var(--surface-subtle)] cursor-pointer"
                          title="取消 (Esc)"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ) : (
                      <>
                        <span className="truncate text-[13px] font-semibold text-[var(--ink-primary)]">
                          {device.name || device.model || device.deviceId}
                        </span>
                        {device.name && device.model && (
                          <span className="hidden sm:inline-block rounded bg-slate-100 px-1.5 py-0.5 text-[10.5px] font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                            {device.model}
                          </span>
                        )}
                        {device.isNew && (
                          <span className="inline-flex items-center gap-0.5 rounded-full bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 dark:text-emerald-300">
                            <Sparkles className="h-2.5 w-2.5" />
                            新接入
                          </span>
                        )}
                      </>
                    )}
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 text-[11px] text-[var(--ink-muted)]">
                    <span className="font-mono-code truncate">{device.deviceId}</span>
                  </div>
                </div>

                {/* Live per-device install status badge */}
                {progress && (
                  <DeviceProgressBadge progress={progress} />
                )}

                {/* Connection status */}
                <div className="hidden md:flex shrink-0 items-center gap-1.5 text-[11.5px]">
                  <span
                    className={`h-2 w-2 rounded-full ${
                      isOnline ? 'bg-emerald-500 online-pulse' : 'bg-amber-500'
                    }`}
                  />
                  <span className={isOnline ? 'text-emerald-700 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'}>
                    {isOnline ? '在线' : device.status}
                  </span>
                </div>

                {/* Quick hover actions */}
                <div
                  className="flex shrink-0 items-center gap-1 opacity-70 transition-opacity group-hover:opacity-100"
                  onClick={(e) => e.stopPropagation()}
                >
                  <button
                    type="button"
                    onClick={() => startEdit(device)}
                    title="自定义设备名称（也可双击行）"
                    className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--ink-secondary)] transition-colors hover:bg-slate-200/70 hover:text-[var(--ink-primary)] dark:hover:bg-slate-700/60 cursor-pointer"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => onCopyId(device.deviceId, device.name || device.deviceId)}
                    title="复制设备码"
                    className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--ink-secondary)] transition-colors hover:bg-slate-200/70 hover:text-[var(--ink-primary)] dark:hover:bg-slate-700/60 cursor-pointer"
                  >
                    <Copy className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}

function DeviceProgressBadge({ progress }: { progress: DeviceInstallProgress }) {
  const styles: Record<DeviceInstallProgress['state'], string> = {
    queued: 'bg-slate-500/10 text-slate-600 dark:text-slate-300',
    installing: 'bg-blue-500/12 text-blue-700 dark:text-blue-300',
    success: 'bg-emerald-500/12 text-emerald-700 dark:text-emerald-300',
    failed: 'bg-rose-500/12 text-rose-700 dark:text-rose-300',
    skipped: 'bg-amber-500/12 text-amber-700 dark:text-amber-300',
    cancelled: 'bg-slate-500/15 text-slate-600 dark:text-slate-400',
  };

  return (
    <span
      title={progress.detail}
      className={`inline-flex max-w-[160px] shrink-0 items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-medium ${styles[progress.state]}`}
    >
      {progress.state === 'installing' && <Loader2 className="h-3 w-3 shrink-0 animate-spin" />}
      {progress.state === 'success' && <Check className="h-3 w-3 shrink-0" />}
      {progress.state === 'failed' && <XCircle className="h-3 w-3 shrink-0" />}
      <span className="truncate">{progress.detail}</span>
    </span>
  );
}
