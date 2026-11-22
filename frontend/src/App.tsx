import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Loader2, RefreshCw, Upload } from 'lucide-react';
import { bridgeApi, isDesktopBridgeAvailable, waitForBridge } from './api';
import { DevicePanel } from './components/DevicePanel';
import { ExecutionBar } from './components/ExecutionBar';
import { HeaderBar } from './components/HeaderBar';
import { LogConsole } from './components/LogConsole';
import { PackagePanel } from './components/PackagePanel';
import { SettingsModal } from './components/SettingsModal';
import { ToastContainer } from './components/ToastContainer';
import type {
  ActiveTask,
  AppLogTargetItem,
  AppSettings,
  DeviceInstallProgress,
  DeviceItem,
  InstallerEvent,
  LogEntry,
  PackageSlotState,
  ThemeMode,
  ToastItem,
  ToolDiagnostic,
} from './types';

function applyThemeClass(mode: ThemeMode) {
  const root = document.documentElement;
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  const shouldDark = mode === 'dark' || (mode === 'system' && prefersDark);
  root.classList.toggle('dark', shouldDark);
}

export default function App() {
  const [ready, setReady] = useState(false);
  const [initError, setInitError] = useState<string | null>(null);
  const [initAttempt, setInitAttempt] = useState(0);
  const [version, setVersion] = useState('1.0.0');
  const [devices, setDevices] = useState<DeviceItem[]>([]);
  const [selectedDeviceIds, setSelectedDeviceIds] = useState<string[]>([]);
  const [deviceErrors, setDeviceErrors] = useState<Record<string, string>>({});
  const [lastProbeFailed, setLastProbeFailed] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [folder, setFolder] = useState('');
  const [recentDirs, setRecentDirs] = useState<string[]>([]);
  const [packages, setPackages] = useState<Record<string, PackageSlotState>>({});
  const [task, setTask] = useState<ActiveTask | null>(null);
  const [installStatus, setInstallStatus] = useState('就绪');
  const [deviceProgress, setDeviceProgress] = useState<Record<string, DeviceInstallProgress>>({});
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [settings, setSettings] = useState<AppSettings>({
    theme: 'system',
    logOutputDir: '',
    defaultLogOutputDir: 'D:\\',
    parallelInstall: true,
    maxConcurrency: 4,
  });
  const [tools, setTools] = useState<Record<string, ToolDiagnostic>>({});
  const [appLogTargets, setAppLogTargets] = useState<AppLogTargetItem[]>([]);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [windowMaximized, setWindowMaximized] = useState(false);
  const [draggingOver, setDraggingOver] = useState(false);
  const dragDepthRef = useRef(0);
  const revisionsRef = useRef<Record<string, number>>({
    devices: 0,
    packages: 0,
    task: 0,
    settings: 0,
  });
  const logClearGenRef = useRef<number>(0);
  const toolsEventSeenRef = useRef(false);

  const pushToast = useCallback((toast: ToastItem) => {
    setToasts((prev) => [...prev.slice(-3), toast]);
    const timeout = toast.actionPath || toast.copyText ? 7000 : 4000;
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((item) => item.id !== toast.id));
    }, timeout);
  }, []);

  const copyToClipboard = useCallback(
    async (text: string, label: string) => {
      try {
        await navigator.clipboard.writeText(text);
        pushToast({
          id: `copy-${Date.now()}`,
          title: `已复制${label}`,
          message: text.length > 64 ? `${text.slice(0, 64)}…` : text,
          variant: 'success',
        });
      } catch {
        pushToast({
          id: `copy-err-${Date.now()}`,
          title: '复制失败',
          message: '剪贴板权限受限，请手动选择复制',
          variant: 'warn',
        });
      }
    },
    [pushToast],
  );

  const acceptEventRevision = useCallback((channel: string, rev?: number): boolean => {
    if (typeof rev !== 'number') return true;
    const current = revisionsRef.current[channel] ?? 0;
    if (rev <= current) return false;
    revisionsRef.current[channel] = rev;
    return true;
  }, []);

  const acceptSnapshotRevision = useCallback((channel: string, rev?: number): boolean => {
    if (typeof rev !== 'number') return true;
    const current = revisionsRef.current[channel] ?? 0;
    if (rev < current) return false;
    revisionsRef.current[channel] = rev;
    return true;
  }, []);

  // Subscribe to backend push events + load initial snapshot
  useEffect(() => {
    revisionsRef.current = { devices: 0, packages: 0, task: 0, settings: 0 };
    logClearGenRef.current = 0;
    toolsEventSeenRef.current = false;

    window.__INSTALLER_EVENT__ = (event: InstallerEvent) => {
      const { type, payload } = event;
      if (type === 'devices') {
        if (!acceptEventRevision('devices', payload?.rev)) return;
        setDevices(payload.devices ?? []);
        setSelectedDeviceIds(payload.selectedDeviceIds ?? []);
        setDeviceErrors(payload.deviceErrors ?? {});
        setLastProbeFailed(Boolean(payload.lastProbeFailed));
        setRefreshing(Boolean(payload.refreshing));
      } else if (type === 'packages') {
        if (!acceptEventRevision('packages', payload?.rev)) return;
        setFolder(payload.folder ?? '');
        setRecentDirs(payload.recentDirs ?? []);
        setScanning(Boolean(payload.scanning));
        setPackages(payload.packages ?? {});
      } else if (type === 'task') {
        if (!acceptEventRevision('task', payload?.rev)) return;
        setTask(payload.task ?? null);
        setInstallStatus(payload.installStatus ?? '就绪');
        setDeviceProgress(payload.deviceProgress ?? {});
      } else if (type === 'log') {
        const entry = payload as LogEntry;
        if (entry.preview && isDesktopBridgeAvailable()) return;
        const entryGen = entry.clearGen ?? 0;
        if (entryGen < logClearGenRef.current) return;
        if (entryGen > logClearGenRef.current) {
          logClearGenRef.current = entryGen;
        }
        const dropPreview = !entry.preview && isDesktopBridgeAvailable();
        setLogs((prev) => {
          const minGen = logClearGenRef.current;
          if (entryGen < minGen) return prev;
          let base =
            prev.length > 0 && (prev[0].clearGen ?? 0) < minGen
              ? prev.filter((item) => (item.clearGen ?? 0) >= minGen)
              : prev;
          if (dropPreview && base.some((item) => item.preview)) {
            base = base.filter((item) => !item.preview);
          }
          if (base.length === 0 || entry.id > base[base.length - 1].id) {
            const next = [...base, entry];
            return next.length > 2000 ? next.slice(-2000) : next;
          }
          if (base.some((item) => item.id === entry.id)) {
            return base;
          }
          return [...base, entry].sort((a, b) => a.id - b.id).slice(-2000);
        });
      } else if (type === 'logs_cleared') {
        const nextGen =
          typeof payload?.clearGen === 'number' ? payload.clearGen : logClearGenRef.current + 1;
        if (nextGen > logClearGenRef.current) {
          logClearGenRef.current = nextGen;
        }
        setLogs((prev) => {
          const minGen = logClearGenRef.current;
          return prev.filter((item) => (item.clearGen ?? 0) >= minGen);
        });
      } else if (type === 'settings') {
        if (!acceptEventRevision('settings', payload?.rev)) return;
        setSettings(payload as AppSettings);
      } else if (type === 'tools') {
        if (payload && typeof payload === 'object') {
          toolsEventSeenRef.current = true;
          setTools(payload as Record<string, ToolDiagnostic>);
        }
      } else if (type === 'window_state') {
        setWindowMaximized(Boolean(payload?.maximized));
      } else if (type === 'toast') {
        const t = payload as ToastItem;
        if (t.copyText) {
          navigator.clipboard?.writeText(t.copyText).catch(() => {});
        }
        pushToast(t);
      }
    };

    let alive = true;
    let lateReadyHandler: (() => void) | null = null;
    waitForBridge().then(async (bridgeReady) => {
      if (!alive) return;
      if (!bridgeReady && !isDesktopBridgeAvailable()) {
        lateReadyHandler = () => {
          if (alive) setInitAttempt((n) => n + 1);
        };
        window.addEventListener('pywebviewready', lateReadyHandler, { once: true });
      }
      try {
        const init = await bridgeApi.getInitialState();
        if (!alive) return;
        setVersion(init.version);
        if (acceptSnapshotRevision('devices', init.revisions?.devices)) {
          setDevices(init.devices);
          setSelectedDeviceIds(init.selectedDeviceIds);
          setDeviceErrors(init.deviceErrors);
          setLastProbeFailed(init.lastProbeFailed);
          setRefreshing(init.refreshing);
        }
        if (acceptSnapshotRevision('packages', init.revisions?.packages)) {
          setScanning(init.scanning);
          setFolder(init.folder);
          setRecentDirs(init.recentDirs);
          setPackages(init.packages);
        }
        if (acceptSnapshotRevision('task', init.revisions?.task)) {
          setTask(init.task);
          setInstallStatus(init.installStatus);
          setDeviceProgress(init.deviceProgress);
        }
        const isDesktop = isDesktopBridgeAvailable();
        const initGen = init.logClearGen ?? 0;
        if (initGen > logClearGenRef.current) {
          logClearGenRef.current = initGen;
        }
        setLogs((prev) => {
          const minGen = logClearGenRef.current;
          const liveFiltered = prev.filter(
            (item) => (!isDesktop || !item.preview) && (item.clearGen ?? 0) >= minGen,
          );
          const initFiltered = init.logs.filter(
            (item) => (!isDesktop || !item.preview) && (item.clearGen ?? 0) >= minGen,
          );
          if (liveFiltered.length === 0) return initFiltered;
          const byId = new Map<number, LogEntry>();
          for (const item of initFiltered) byId.set(item.id, item);
          for (const item of liveFiltered) byId.set(item.id, item);
          const merged = Array.from(byId.values()).sort((a, b) => a.id - b.id);
          return merged.length > 2000 ? merged.slice(-2000) : merged;
        });
        if (acceptSnapshotRevision('settings', init.revisions?.settings)) {
          setSettings(init.settings);
        }
        if (!toolsEventSeenRef.current && init.tools && Object.keys(init.tools).length > 0) {
          setTools(init.tools);
        }
        setAppLogTargets(init.appLogTargets);
        setWindowMaximized(Boolean(init.windowMaximized));
        setInitError(null);
        setReady(true);
      } catch (err) {
        if (!alive) return;
        setInitError(err instanceof Error ? err.message : String(err));
      }
    });

    return () => {
      alive = false;
      if (lateReadyHandler) {
        window.removeEventListener('pywebviewready', lateReadyHandler);
      }
      delete window.__INSTALLER_EVENT__;
    };
  }, [pushToast, initAttempt, acceptEventRevision, acceptSnapshotRevision]);

  // Apply theme & listen to system color scheme changes
  useEffect(() => {
    applyThemeClass(settings.theme);
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => {
      if (settings.theme === 'system') applyThemeClass('system');
    };
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, [settings.theme]);

  // Drag-and-drop visual overlay (actual OS path handling is wired via PyWebView DOM drop)
  useEffect(() => {
    const onDragEnter = (e: DragEvent) => {
      e.preventDefault();
      dragDepthRef.current += 1;
      setDraggingOver(true);
    };
    const onDragOver = (e: DragEvent) => {
      e.preventDefault();
    };
    const onDragLeave = (e: DragEvent) => {
      e.preventDefault();
      dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
      if (dragDepthRef.current === 0) setDraggingOver(false);
    };
    const onDrop = (e: DragEvent) => {
      e.preventDefault();
      dragDepthRef.current = 0;
      setDraggingOver(false);
    };
    window.addEventListener('dragenter', onDragEnter);
    window.addEventListener('dragover', onDragOver);
    window.addEventListener('dragleave', onDragLeave);
    window.addEventListener('drop', onDrop);
    return () => {
      window.removeEventListener('dragenter', onDragEnter);
      window.removeEventListener('dragover', onDragOver);
      window.removeEventListener('dragleave', onDragLeave);
      window.removeEventListener('drop', onDrop);
    };
  }, []);

  const hasAnyPackage = Object.values(packages).some((slot) => slot.candidates.length > 0);

  // Global keyboard shortcuts: F5 (refresh), Ctrl+Enter (install), Esc (cancel running task)
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (settingsOpen) return;
      if (e.key === 'F5') {
        e.preventDefault();
        bridgeApi.refreshDevices(true);
      } else if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        if (!task && !scanning && hasAnyPackage) {
          bridgeApi.startInstall(selectedDeviceIds);
        }
      } else if (e.key === 'Escape' && task && !task.cancelled) {
        e.preventDefault();
        bridgeApi.cancelTask();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [settingsOpen, task, scanning, hasAnyPackage, selectedDeviceIds]);

  const handleCloseSettings = useCallback(() => setSettingsOpen(false), []);

  const handleUpdateSettings = async (updates: Partial<AppSettings>) => {
    const prevSettings = settings;
    const revBefore = revisionsRef.current.settings ?? 0;
    setSettings((prev) => ({ ...prev, ...updates }));
    try {
      const res = await bridgeApi.updateSettings(updates);
      if (res?.settings && acceptEventRevision('settings', res.settings.rev)) {
        setSettings(res.settings);
      }
    } catch (err) {
      if ((revisionsRef.current.settings ?? 0) === revBefore) {
        setSettings(prevSettings);
      }
      pushToast({
        id: `settings-err-${Date.now()}`,
        title: '保存设置失败',
        message: err instanceof Error ? err.message : String(err),
        variant: 'error',
      });
    }
  };

  if (!ready) {
    if (initError) {
      return (
        <div className="flex h-full items-center justify-center bg-[var(--surface-canvas)] p-6 text-[var(--ink-primary)]">
          <div className="flex max-w-md flex-col items-center gap-3 rounded-2xl border border-rose-500/30 bg-[var(--surface-card)] p-6 text-center shadow-lg">
            <AlertTriangle className="h-7 w-7 text-rose-500" />
            <div className="text-[14px] font-semibold">初始化桌面工作区失败</div>
            <p className="break-all text-[12px] text-[var(--ink-secondary)]">{initError}</p>
            <button
              type="button"
              onClick={() => {
                setInitError(null);
                setInitAttempt((n) => n + 1);
              }}
              className="mt-1 inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-1.5 text-[12.5px] font-semibold text-white hover:bg-blue-700 cursor-pointer"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              <span>重试初始化</span>
            </button>
          </div>
        </div>
      );
    }
    return (
      <div className="flex h-full items-center justify-center bg-[var(--surface-canvas)] text-[var(--ink-secondary)]">
        <div className="flex items-center gap-2.5 text-[13px] font-medium">
          <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
          <span>正在初始化设备与工作区…</span>
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex h-full flex-col bg-[var(--surface-canvas)] text-[var(--ink-primary)]">
      <HeaderBar
        version={version}
        theme={settings.theme}
        tools={tools}
        maximized={windowMaximized}
        onThemeChange={(theme) => handleUpdateSettings({ theme })}
        onOpenSettings={() => setSettingsOpen(true)}
        onStartDrag={() => bridgeApi.windowStartDrag()}
        onStartResize={(edge) => bridgeApi.windowStartResize(edge)}
        onMinimize={() => bridgeApi.windowMinimize()}
        onToggleMaximize={() => bridgeApi.windowToggleMaximize()}
        onClose={() => bridgeApi.windowClose()}
      />

      {/* Main Workspace */}
      <main className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto p-3">
        <DevicePanel
          devices={devices}
          selectedDeviceIds={selectedDeviceIds}
          deviceErrors={deviceErrors}
          lastProbeFailed={lastProbeFailed}
          refreshing={refreshing}
          task={task}
          deviceProgress={deviceProgress}
          appLogTargets={appLogTargets}
          onRefresh={() => bridgeApi.refreshDevices(true)}
          onSelectChange={(ids) => {
            setSelectedDeviceIds(ids);
            bridgeApi.setSelectedDevices(ids);
          }}
          onSaveName={(deviceId, name) => bridgeApi.saveDeviceName(deviceId, name)}
          onCopyId={(deviceId) => copyToClipboard(deviceId, '设备码')}
          onFetchUdid={() => bridgeApi.fetchUdid()}
          onFetchCrashLog={() => bridgeApi.fetchCrashLog()}
          onFetchAppLog={(key) => bridgeApi.fetchAppLog(key)}
        />

        <PackagePanel
          folder={folder}
          recentDirs={recentDirs}
          scanning={scanning}
          packages={packages}
          onChooseFolder={() => bridgeApi.chooseFolder()}
          onScanFolder={(dir) => bridgeApi.scanFolder(dir)}
          onOpenFolder={(dir) => bridgeApi.openPathInExplorer(dir)}
          onSelectPackage={(kind, index, revision) => bridgeApi.selectPackage(kind, index, revision)}
          onCopyText={(text, label) => copyToClipboard(text, label)}
        />

        <LogConsole
          logs={logs}
          onClear={() => bridgeApi.clearLogs()}
          onCopyLogs={(text) => {
            if (text) copyToClipboard(text, '日志');
          }}
          onCopyLine={(text) => {
            if (text) copyToClipboard(text, '日志行');
          }}
          onOpenPath={(path) => bridgeApi.openPathInExplorer(path)}
        />
      </main>

      <ExecutionBar
        devices={devices}
        selectedDeviceIds={selectedDeviceIds}
        task={task}
        scanning={scanning}
        installStatus={installStatus}
        parallelInstall={settings.parallelInstall}
        maxConcurrency={settings.maxConcurrency}
        hasAnyPackage={hasAnyPackage}
        onToggleParallel={() => handleUpdateSettings({ parallelInstall: !settings.parallelInstall })}
        onPrimaryAction={() => {
          if (task) bridgeApi.cancelTask();
          else bridgeApi.startInstall(selectedDeviceIds);
        }}
      />

      <SettingsModal
        open={settingsOpen}
        settings={settings}
        tools={tools}
        onClose={handleCloseSettings}
        onUpdateSettings={handleUpdateSettings}
        onChooseLogDir={async () => {
          const res = await bridgeApi.chooseLogOutputDir();
          if (res?.settings && acceptEventRevision('settings', res.settings.rev)) {
            setSettings(res.settings);
          }
        }}
        onRefreshDiagnostics={async () => {
          const res = await bridgeApi.diagnoseEnvironment();
          if (res?.tools) setTools(res.tools);
        }}
      />

      <ToastContainer
        toasts={toasts}
        onDismiss={(id) => setToasts((prev) => prev.filter((t) => t.id !== id))}
        onOpenPath={(path) => bridgeApi.openPathInExplorer(path)}
        onCopyText={(text, label) => copyToClipboard(text, label)}
      />

      {/* Full-window Drag & Drop overlay */}
      {draggingOver && (
        <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center bg-blue-600/15 backdrop-blur-xs">
          <div className="flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed border-blue-500 bg-[var(--surface-card)]/95 px-10 py-8 shadow-2xl">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-500/15 text-blue-600 dark:text-blue-400">
              <Upload className="h-6 w-6" />
            </div>
            <div className="text-[15px] font-semibold text-[var(--ink-primary)]">
              释放以加载 APK / HAP 或切换扫描目录
            </div>
            <p className="text-[12px] text-[var(--ink-secondary)]">
              支持拖入单个安装包直接定位选中，或拖入构建输出文件夹
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
