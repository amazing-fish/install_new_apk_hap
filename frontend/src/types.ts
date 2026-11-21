export type PlatformKey = 'android' | 'harmony' | string;

export interface DeviceItem {
  deviceId: string;
  name: string;
  platform: PlatformKey;
  platformLabel: string;
  status: string;
  model: string;
  product: string;
  isNew: boolean;
  supportsUdid: boolean;
  hasAppLogs: boolean;
}

export interface PackageCandidateItem {
  index: number;
  path: string;
  filename: string;
  sizeBytes: number;
  mtimeMs: number;
  display: string;
  labelLoaded: boolean;
  appName: string | null;
  status: string;
  statusHint: string;
  packageName: string | null;
  versionName: string | null;
  versionCode: number | null;
  versionText: string;
  testOnly: boolean | null;
}

export interface PackageSlotState {
  kind: 'APK' | 'HAP' | string;
  revision?: number;
  selectedIndex: number;
  allowTest: boolean | null;
  candidates: PackageCandidateItem[];
}

export interface ActiveTask {
  action: 'install' | 'udid' | 'crash_log' | 'app_log' | string;
  name: string;
  label: string;
  cancelled: boolean;
}

export interface DeviceInstallProgress {
  state: 'queued' | 'installing' | 'success' | 'failed' | 'skipped' | 'cancelled';
  detail: string;
  duration: number | null;
}

export type LogLevel = 'info' | 'cmd' | 'success' | 'warn' | 'error';

export interface LogEntry {
  id: number;
  clearGen?: number;
  preview?: boolean;
  timestamp: string;
  level: LogLevel;
  message: string;
  deviceId: string | null;
}

export type ThemeMode = 'system' | 'light' | 'dark';

export interface AppSettings {
  rev?: number;
  theme: ThemeMode;
  logOutputDir: string;
  defaultLogOutputDir: string;
  parallelInstall: boolean;
  maxConcurrency: number;
}

export interface ToolDiagnostic {
  available: boolean;
  path: string | null;
  error: string | null;
}

export interface AppLogTargetItem {
  key: string;
  displayName: string;
  remotePath: string;
  platform: string;
}

export interface ToastItem {
  id: string;
  title: string;
  message: string;
  variant: 'info' | 'success' | 'warn' | 'error';
  actionLabel?: string | null;
  actionPath?: string | null;
  copyText?: string | null;
}

export interface InitialAppState {
  version: string;
  devices: DeviceItem[];
  selectedDeviceIds: string[];
  deviceErrors: Record<string, string>;
  lastProbeFailed: boolean;
  refreshing: boolean;
  scanning: boolean;
  folder: string;
  recentDirs: string[];
  packages: Record<string, PackageSlotState>;
  task: ActiveTask | null;
  installStatus: string;
  deviceProgress: Record<string, DeviceInstallProgress>;
  logs: LogEntry[];
  logClearGen?: number;
  settings: AppSettings;
  tools: Record<string, ToolDiagnostic>;
  appLogTargets: AppLogTargetItem[];
  revisions?: {
    devices: number;
    packages: number;
    task: number;
    settings: number;
  };
}

export interface InstallerEvent {
  type: 'devices' | 'packages' | 'task' | 'log' | 'logs_cleared' | 'toast' | 'settings';
  payload: any;
}
