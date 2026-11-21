import type { AppSettings, InitialAppState, InstallerEvent, ToolDiagnostic } from './types';

interface PyWebViewAPI {
  get_initial_state: () => Promise<InitialAppState>;
  refresh_devices: (includePackages?: boolean) => Promise<{ ok: boolean }>;
  set_selected_devices: (deviceIds: string[]) => Promise<{ ok: boolean; selectedDeviceIds: string[] }>;
  save_device_name: (deviceId: string, name: string) => Promise<{ ok: boolean; label?: string; error?: string }>;
  choose_folder: () => Promise<{ ok: boolean; cancelled?: boolean; error?: string }>;
  scan_folder: (folderPath: string) => Promise<{ ok: boolean; error?: string }>;
  handle_dropped_paths: (paths: string[]) => Promise<{ ok: boolean; error?: string }>;
  select_package: (kind: string, index: number) => Promise<{ ok: boolean; error?: string }>;
  start_install: (deviceIds?: string[]) => Promise<{ ok: boolean; error?: string }>;
  cancel_task: () => Promise<{ ok: boolean }>;
  fetch_udid: (deviceId?: string) => Promise<{ ok: boolean }>;
  fetch_crash_log: (deviceId?: string) => Promise<{ ok: boolean }>;
  fetch_app_log: (targetKey: string, deviceId?: string) => Promise<{ ok: boolean }>;
  open_path_in_explorer: (targetPath: string) => Promise<{ ok: boolean; error?: string }>;
  choose_log_output_dir: () => Promise<{ ok: boolean; settings?: AppSettings; cancelled?: boolean }>;
  update_settings: (updates: Partial<AppSettings>) => Promise<{ ok: boolean; settings: AppSettings }>;
  diagnose_environment: () => Promise<{ ok: boolean; tools: Record<string, ToolDiagnostic> }>;
  clear_logs: () => Promise<{ ok: boolean }>;
}

declare global {
  interface Window {
    pywebview?: { api?: PyWebViewAPI };
    __INSTALLER_EVENT__?: (event: InstallerEvent) => void;
  }
}

export function isDesktopBridgeAvailable(): boolean {
  return Boolean(window.pywebview?.api);
}

/** Wait briefly for pywebviewready when running inside Edge WebView2. */
export function waitForBridge(timeoutMs = 2000): Promise<boolean> {
  if (isDesktopBridgeAvailable()) {
    return Promise.resolve(true);
  }
  return new Promise((resolve) => {
    let settled = false;
    const finish = (ok: boolean) => {
      if (settled) return;
      settled = true;
      window.removeEventListener('pywebviewready', onReady);
      resolve(ok);
    };
    const onReady = () => finish(true);
    window.addEventListener('pywebviewready', onReady);
    window.setTimeout(() => finish(isDesktopBridgeAvailable()), timeoutMs);
  });
}

// Rich mock data for pure browser UI preview / layout verification when pywebview isn't attached.
function createPreviewMockState(): InitialAppState {
  const now = Date.now();
  return {
    version: '1.0.0',
    devices: [
      {
        deviceId: 'R5CW90ABCDE',
        name: '测试主力机 S24',
        platform: 'android',
        platformLabel: 'Android',
        status: 'device',
        model: 'SM S9280',
        product: 'e3qzcx',
        isNew: true,
        supportsUdid: false,
        hasAppLogs: false,
      },
      {
        deviceId: '21A0224715000482',
        name: 'Mate 70 Pro NEXT',
        platform: 'harmony',
        platformLabel: 'Harmony',
        status: 'device',
        model: '',
        product: '',
        isNew: false,
        supportsUdid: true,
        hasAppLogs: true,
      },
      {
        deviceId: 'Pixel8Pro-39101FD',
        name: '',
        platform: 'android',
        platformLabel: 'Android',
        status: 'device',
        model: 'Pixel 8 Pro',
        product: 'husky',
        isNew: false,
        supportsUdid: false,
        hasAppLogs: false,
      },
    ],
    selectedDeviceIds: ['R5CW90ABCDE', '21A0224715000482'],
    deviceErrors: {},
    lastProbeFailed: false,
    refreshing: false,
    scanning: false,
    folder: 'D:\\Builds\\Release\\2026-11-21',
    recentDirs: ['D:\\Builds\\Release\\2026-11-21', 'D:\\Builds\\Nightly', 'C:\\Users\\Dev\\Downloads'],
    packages: {
      APK: {
        kind: 'APK',
        selectedIndex: 0,
        allowTest: false,
        candidates: [
          {
            index: 0,
            path: 'D:\\Builds\\Release\\2026-11-21\\app-release-1.4.2.apk',
            filename: 'app-release-1.4.2.apk',
            sizeBytes: 64_820_112,
            mtimeMs: now - 180_000,
            display: '乾崑出行 · 1.4.2 (1420)（app-release-1.4.2.apk）',
            labelLoaded: true,
            appName: '乾崑出行',
            status: 'resolved',
            statusHint: '',
            packageName: 'com.yinwang.qiankunapp',
            versionName: '1.4.2',
            versionCode: 1420,
            versionText: '1.4.2 (1420)',
            testOnly: false,
          },
          {
            index: 1,
            path: 'D:\\Builds\\Release\\2026-11-21\\app-debug-1.4.1.apk',
            filename: 'app-debug-1.4.1.apk',
            sizeBytes: 71_204_500,
            mtimeMs: now - 5_400_000,
            display: '乾崑出行 · 1.4.1-debug (1410)（app-debug-1.4.1.apk）',
            labelLoaded: true,
            appName: '乾崑出行',
            status: 'resolved',
            statusHint: '',
            packageName: 'com.yinwang.qiankunapp.debug',
            versionName: '1.4.1-debug',
            versionCode: 1410,
            versionText: '1.4.1-debug (1410)',
            testOnly: true,
          },
        ],
      },
      HAP: {
        kind: 'HAP',
        selectedIndex: 0,
        allowTest: null,
        candidates: [
          {
            index: 0,
            path: 'D:\\Builds\\Release\\2026-11-21\\entry-default-signed.hap',
            filename: 'entry-default-signed.hap',
            sizeBytes: 38_412_990,
            mtimeMs: now - 420_000,
            display: '乾崑智驾 · 2.1.0 (20100)（entry-default-signed.hap）',
            labelLoaded: true,
            appName: '乾崑智驾',
            status: 'resolved',
            statusHint: '',
            packageName: 'com.yinwang.qiankunapp.hm',
            versionName: '2.1.0',
            versionCode: 20100,
            versionText: '2.1.0 (20100)',
            testOnly: null,
          },
        ],
      },
    },
    task: null,
    installStatus: '就绪',
    deviceProgress: {},
    logs: [
      { id: 1, timestamp: '11:50:01', level: 'info', message: '设备列表已刷新：Android 2 台，Harmony 1 台，总计 3 台', deviceId: null },
      { id: 2, timestamp: '11:50:01', level: 'success', message: '新增设备已置顶高亮：测试主力机 S24', deviceId: 'R5CW90ABCDE' },
      { id: 3, timestamp: '11:50:02', level: 'info', message: '安装包扫描完成：D:\\Builds\\Release\\2026-11-21 · APK=app-release-1.4.2.apk，HAP=entry-default-signed.hap', deviceId: null },
      { id: 4, timestamp: '11:50:02', level: 'cmd', message: '预览模式：当前运行在浏览器中（未连接 PyWebView 桌面容器）', deviceId: null },
    ],
    settings: {
      theme: 'system',
      logOutputDir: '',
      defaultLogOutputDir: 'D:\\',
      parallelInstall: true,
      maxConcurrency: 4,
    },
    tools: {
      adb: { available: true, path: 'C:\\Android\\Sdk\\platform-tools\\adb.exe', error: null },
      hdc: { available: true, path: 'D:\\DevEco Studio\\sdk\\default\\openharmony\\toolchains\\hdc.exe', error: null },
      aapt2: { available: true, path: 'vendor\\metadata-tools\\windows-x64\\aapt2.exe', error: null },
      restool: { available: true, path: 'vendor\\metadata-tools\\windows-x64\\restool.exe', error: null },
    },
    appLogTargets: [
      { key: 'qiankun', displayName: '乾崑日志', remotePath: '/data/app/el2/100/base/com.yinwang.qiankunapp.hm/haps/phone/files/qklog/', platform: 'harmony' },
      { key: 'demo', displayName: 'Demo日志', remotePath: '/data/app/el2/100/base/adsmobilesdk.all.huawei/haps/entry/files', platform: 'harmony' },
    ],
  };
}

let mockState: InitialAppState | null = null;

function emitMock(type: InstallerEvent['type'], payload: any) {
  window.__INSTALLER_EVENT__?.({ type, payload });
}

export const bridgeApi = {
  async getInitialState(): Promise<InitialAppState> {
    if (window.pywebview?.api) {
      return window.pywebview.api.get_initial_state();
    }
    mockState = createPreviewMockState();
    return structuredClone(mockState);
  },

  async refreshDevices(includePackages = false) {
    if (window.pywebview?.api) {
      return window.pywebview.api.refresh_devices(includePackages);
    }
    if (!mockState) return { ok: true };
    emitMock('devices', { ...mockState, refreshing: true });
    setTimeout(() => {
      if (!mockState) return;
      emitMock('devices', { ...mockState, refreshing: false });
      emitMock('log', {
        id: Date.now(),
        timestamp: new Date().toTimeString().slice(0, 8),
        level: 'info',
        message: '预览模式：已完成模拟并行刷新（ADB + HDC）',
        deviceId: null,
      });
    }, 350);
    return { ok: true };
  },

  async setSelectedDevices(deviceIds: string[]) {
    if (window.pywebview?.api) {
      return window.pywebview.api.set_selected_devices(deviceIds);
    }
    if (mockState) {
      mockState.selectedDeviceIds = [...deviceIds];
      emitMock('devices', {
        devices: mockState.devices,
        selectedDeviceIds: mockState.selectedDeviceIds,
        deviceErrors: mockState.deviceErrors,
        lastProbeFailed: mockState.lastProbeFailed,
        refreshing: false,
      });
    }
    return { ok: true, selectedDeviceIds: deviceIds };
  },

  async saveDeviceName(deviceId: string, name: string) {
    if (window.pywebview?.api) {
      return window.pywebview.api.save_device_name(deviceId, name);
    }
    if (mockState) {
      mockState.devices = mockState.devices.map((d) =>
        d.deviceId === deviceId ? { ...d, name: name.trim() } : d,
      );
      emitMock('devices', {
        devices: mockState.devices,
        selectedDeviceIds: mockState.selectedDeviceIds,
        deviceErrors: mockState.deviceErrors,
        lastProbeFailed: mockState.lastProbeFailed,
        refreshing: false,
      });
      emitMock('toast', {
        id: `t-${Date.now()}`,
        title: '设备名称已更新',
        message: name.trim() || deviceId,
        variant: 'success',
      });
    }
    return { ok: true };
  },

  async chooseFolder() {
    if (window.pywebview?.api) {
      return window.pywebview.api.choose_folder();
    }
    emitMock('toast', {
      id: `t-${Date.now()}`,
      title: '预览模式',
      message: '桌面端将弹出原生文件夹选择对话框',
      variant: 'info',
    });
    return { ok: false, cancelled: true };
  },

  async scanFolder(folderPath: string) {
    if (window.pywebview?.api) {
      return window.pywebview.api.scan_folder(folderPath);
    }
    if (mockState) {
      mockState.folder = folderPath;
      emitMock('packages', {
        folder: mockState.folder,
        recentDirs: mockState.recentDirs,
        scanning: false,
        packages: mockState.packages,
      });
    }
    return { ok: true };
  },

  async selectPackage(kind: string, index: number) {
    if (window.pywebview?.api) {
      return window.pywebview.api.select_package(kind, index);
    }
    if (mockState && mockState.packages[kind]) {
      mockState.packages[kind].selectedIndex = index;
      const cand = mockState.packages[kind].candidates[index];
      if (kind === 'APK') {
        mockState.packages[kind].allowTest = !(cand && cand.testOnly === false);
      }
      emitMock('packages', {
        folder: mockState.folder,
        recentDirs: mockState.recentDirs,
        scanning: false,
        packages: structuredClone(mockState.packages),
      });
    }
    return { ok: true };
  },

  async startInstall(deviceIds?: string[]) {
    if (window.pywebview?.api) {
      return window.pywebview.api.start_install(deviceIds);
    }
    emitMock('toast', {
      id: `t-${Date.now()}`,
      title: '预览模式',
      message: '桌面端将执行并行预校验并安装到所选设备',
      variant: 'info',
    });
    return { ok: true };
  },

  async cancelTask() {
    if (window.pywebview?.api) {
      return window.pywebview.api.cancel_task();
    }
    return { ok: true };
  },

  async fetchUdid(deviceId?: string) {
    if (window.pywebview?.api) {
      return window.pywebview.api.fetch_udid(deviceId);
    }
    emitMock('toast', {
      id: `t-${Date.now()}`,
      title: 'Mate 70 Pro NEXT 的 UDID',
      message: '8E2A9F1C4B7D6039E1A5C2D4F8B90123456789ABCDEF',
      variant: 'success',
      copyText: '8E2A9F1C4B7D6039E1A5C2D4F8B90123456789ABCDEF',
    });
    return { ok: true };
  },

  async fetchCrashLog(deviceId?: string) {
    if (window.pywebview?.api) {
      return window.pywebview.api.fetch_crash_log(deviceId);
    }
    emitMock('toast', {
      id: `t-${Date.now()}`,
      title: '崩溃日志已打包（预览）',
      message: 'harmony_crash_20261121.zip',
      variant: 'success',
    });
    return { ok: true };
  },

  async fetchAppLog(targetKey: string, deviceId?: string) {
    if (window.pywebview?.api) {
      return window.pywebview.api.fetch_app_log(targetKey, deviceId);
    }
    emitMock('toast', {
      id: `t-${Date.now()}`,
      title: `已触发 ${targetKey} 日志拉取（预览）`,
      message: '桌面端将直接执行 hdc file recv 并打包 ZIP',
      variant: 'info',
    });
    return { ok: true };
  },

  async openPathInExplorer(targetPath: string) {
    if (window.pywebview?.api) {
      return window.pywebview.api.open_path_in_explorer(targetPath);
    }
    emitMock('toast', {
      id: `t-${Date.now()}`,
      title: '打开位置',
      message: targetPath,
      variant: 'info',
    });
    return { ok: true };
  },

  async chooseLogOutputDir() {
    if (window.pywebview?.api) {
      return window.pywebview.api.choose_log_output_dir();
    }
    return { ok: false, cancelled: true };
  },

  async updateSettings(updates: Partial<AppSettings>) {
    if (window.pywebview?.api) {
      return window.pywebview.api.update_settings(updates);
    }
    if (mockState) {
      mockState.settings = { ...mockState.settings, ...updates };
      emitMock('settings', mockState.settings);
      return { ok: true, settings: mockState.settings };
    }
    return {
      ok: true,
      settings: {
        theme: updates.theme ?? 'system',
        logOutputDir: updates.logOutputDir ?? '',
        defaultLogOutputDir: 'D:\\',
        parallelInstall: updates.parallelInstall ?? true,
        maxConcurrency: updates.maxConcurrency ?? 4,
      },
    };
  },

  async diagnoseEnvironment() {
    if (window.pywebview?.api) {
      return window.pywebview.api.diagnose_environment();
    }
    return { ok: true, tools: mockState?.tools ?? {} };
  },

  async clearLogs() {
    if (window.pywebview?.api) {
      return window.pywebview.api.clear_logs();
    }
    emitMock('logs_cleared', {});
    return { ok: true };
  },
};
