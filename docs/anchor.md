# Anchor 文档

本文件只记录当前架构约束。历史实现、PR 过程和临时兼容方案不在这里长期保留。

## 核心流程

1. `backend/main.py` 创建 PyWebView 窗口（Windows 使用 Edge WebView2 + `win_window.NativeWindowController` 一体化无边框窗口，保留原生阴影、缩放与 Aero Snap），通过持久化 `storage_path`（`private_mode=False`）与无反查 DNS 本地静态服务（`FastLocalServer`）加载 `backend/web_dist/index.html`，经由显式薄门面 `bridge.JsApiFacade` 暴露 23 个 RPC 方法给前端，并在 DOM `drop` 事件上读取原生文件路径。
2. 设备刷新调用 `platforms.detect_devices`：各平台驱动**并行**探测；任一平台失败时保留其他平台设备并明确记录原因，且不做“单设备自动选择”。
3. 安装包扫描为单趟 `os.scandir`，在后台线程执行；APK/HAP 各自按修改时间默认选最新候选。每种包一个 `packages.PackageSlot`；前端按索引回报选择，显示文本从不用来反查文件。扫描失败保留上次结果；拖入单个文件时扫描其目录并选中该文件。
4. 包元数据由 `metadata.loader.PackageLabelLoader` 读取：先返回缓存命中，再优先解析当前选中包，其余候选受控并发、增量回传。结果必须属于最近一次扫描且文件指纹未变才合并；合并只改显示，不改选择。成功结果按“文件指纹 + 基于 manifest/内容 SHA-256 的工具指纹”持久化到配置目录 `metadata_cache.json`，瞬时失败（`invalid` / `limited` / `tool_failed`）不缓存。
5. 点击安装后冻结设备选择与 APK/HAP 路径并执行一次设备 preflight；仍在线的原选择被恢复，未选择且只剩一台设备时自动选择。preflight 后冻结安装计划（设备、驱动、包、显示名），安装期间刷新设备不影响目标。
6. 后端状态变化通过 `window.evaluate_js` 推送事件（`devices` / `packages` / `task` / `log` / `toast` / `settings` / `tools` / `window_state` / `logs_cleared`）；前端只渲染事件和 `get_initial_state` 快照，不持有业务真相。后端共享状态由 `InstallerBridge._state_lock` 保护，启动时 `diagnose_tools()` 在后台线程预热。
7. 设备任务经 `controller.TaskRunner` 调度：安装、UDID、崩溃日志、APP 日志共用一个任务槽，同一时刻只有一个，均可中止；设备刷新与扫描不占用该槽，最新请求胜出。
8. 单设备操作（UDID、崩溃日志、APP 日志）与按钮可用性统一用 `controller.resolve_target`：选中一台用该台；未选且只有一台、且上次探测未失败时用那一台。

## APK/HAP 元数据

- APK 使用 AAPT2 的同一次 `dump badging` 读取应用名、包名、版本以及 `testOnly`。
- HAP 直接读取明确声明的 bundle/version/label 字段；资源型名称按需使用 RestoolV2。
- Windows 单文件 exe 内置压缩后的 `package_tools.zip`（含固定版本 AAPT2/RestoolV2 与声明），运行时按 manifest 摘要懒解压持久化到 `%LOCALAPPDATA%/install_new_apk_hap/package_tools/<hash>/`（缺失时回退临时目录），避免每次启动重复解压；源码运行优先外部 SDK 工具，Windows 下找不到时回退仓库 `vendor/metadata-tools/windows-x64/`。
- 元数据是**增强信息，不是安装前置条件**。缺少工具、格式不支持、解析失败、读取受限或结果尚未返回，都不能阻止安装。
- APK 的 `-t` 策略只有一条：**默认使用 `-t`，只有当前已解析元数据明确 `test_only is False` 时才省略 `-t`**。
- 元数据读取保持 ZIP/资源大小、工具输出和超时限制；不执行包内代码，也不通过文件名猜测元数据。

## UI 约束

- 界面为 PyWebView + React/TypeScript/Tailwind CSS（`frontend/`，构建输出到 `backend/web_dist/`，不入库）。**不再使用 Tkinter/ttk**（#96 有意变更）。
- Python 后端不得导入 Tk；前端不直接执行命令，只调用 `JsApiFacade` 暴露的显式 RPC 方法。
- 默认窗口尺寸 `860 × 860`（按主屏工作区钳位），最小尺寸 `700 × 660`；采用一体化自绘标题栏（去掉重复系统标题栏，集成窗口控制按钮与自定义应用图标 `backend/assets/app_icon.ico`），并记住用户窗口尺寸。
- 主题：浅色 / 深色 / 跟随系统，保存在配置 `theme`，窗口背景色在创建阶段即与主题同步防闪白。
- 底部安装/中止按钮固定可达；运行中主按钮变为“中止…”。
- 结果提示使用非阻塞 Toast；产生文件的操作提供“打开位置”，且对应成功日志行也附带直达「打开位置」按钮。
- 日志区保持至少 4 行可见，向上翻阅历史日志时自动暂停滚底，滚回底部自动恢复。
- 设备行身份始终是 `device_id`；自定义名称只影响显示。
- 设备操作区以一个“APP 日志”菜单承载乾崑 / Demo 两种 Harmony 应用日志。
- 无桌面容器时（纯浏览器打开 `web_dist`）前端使用内置预览数据，仅用于布局检查。

## 安装语义

- Android：`adb -s <device_id> install [-t] <apk>`。
- Harmony：`hdc -t <device_id> install <hap>`。
- 安装请求冻结 APK/HAP 路径和当时计算出的 Android `allow_test`，之后切换选择不会改变进行中的任务。
- 多设备默认并行（配置 `parallel_install`、`max_concurrency` 1–8），可切回顺序；每台独立判定、独立回传状态。
- 安装输出逐行实时写入日志；stderr 只是输出通道。
- 用户主动中止显示“已中止”；命令失败显示“安装失败”；目标被跳过显示“安装未完成”；运行异常显示“安装异常”。
- 安装判定：非零退出码失败；退出码 0 但某行以明确失败标记开头（hdc `[Fail]` / `error: failed to install`，adb `Failure [` / `adb: failed to install`）也判失败。输出文字永远不能把非零退出码改判为成功。

## Harmony APP 日志

- APP 日志只作用于目标设备，且目标必须是 Harmony。
- 不在 `/data/app` 下执行全局 `find`，固定应用直接 `file recv`。
- 乾崑：`/data/app/el2/100/base/com.yinwang.qiankunapp.hm/haps/phone/files/qklog/`。
- Demo：`/data/app/el2/100/base/adsmobilesdk.all.huawei/haps/entry/files`。
- 拉取成功后打包为 ZIP，输出到日志输出目录（默认 Windows `D:\`，不存在时 `~/install_new_apk_hap_logs`；可在设置中修改），前缀分别为 `qiankun_logs_`、`demo_logs_`。
- `recv` 非零返回码保留完整命令、stdout/stderr 与返回码；成功但无文件时明确报告空结果，不生成空 ZIP。

## 设备与工具

- 平台差异只写在 `backend/platforms/` 驱动里，调用方按能力（`package_kind`、`supports_udid`、`app_log_targets`）决定可用性。
- 所有外部命令只通过 `infra/process.run` 执行：无控制台窗口、stdin 为空、支持超时/取消/输出上限。默认输出写临时文件；传入 `on_output` 时改为无缓冲读取线程逐行回调（用于安装）。无法启动抛 `ToolLaunchError`。
- 超时：设备检测/UDID 15 秒，日志拉取 120 秒，安装不设超时但可中止。
- Android 探测：`adb devices -l`，过滤 `emulator-*`。Harmony 探测：`hdc list targets`。
- 工具路径统一由 `infra/tools.py` 解析；显式配置无效时直接报错，不静默换用其他工具。

## 配置

Windows 配置文件：`%APPDATA%/install_new_apk_hap/app_config.json`。字段：

- `device_names`、`last_scan_dir`（v0.10 起）；
- `recent_dirs`、`log_output_dir`、`theme`、`parallel_install`、`max_concurrency`（#96 新增，非法值逐字段回退默认）；
- `window_width`、`window_height`（窗口正常态尺寸记忆）。

未知字段保留在磁盘但不参与逻辑。写入为原子替换；损坏时改名 `.bak` 后以默认配置启动。

## 模块职责

- `backend/main.py`：PyWebView 启动、持久化 WebView2 缓存与 `FastLocalServer`、原生拖放绑定、窗口尺寸记忆、CLI 分派。
- `backend/win_window.py`：Win32 `WM_NCCALCSIZE` 无边框一体化窗口、DPI 工作区尺寸计算、DWM 主题/圆角与自定义图标加载。
- `backend/bridge.py`：前端显式 RPC 门面 `JsApiFacade`、状态持有与事件推送、后台工具预热、安装/日志/UDID 编排。
- `backend/controller.py`：`TaskRunner`、`resolve_target`、安装计划冻结与并行/顺序执行。
- `backend/packages.py`：扫描、`PackageCandidate`、`PackageSlot`、`apk_allow_test`。
- `backend/config_manager.py`：配置持久化与校验。
- `backend/platforms/`、`backend/metadata/`、`backend/infra/`：职责同 v0.10，另有 `metadata/cache.py` 持久化缓存。
- `backend/cli.py`：无 GUI 诊断（`--package-label-report`、`--tool-notices`、`--env-check`）。
- `frontend/src/`：`App.tsx` 状态与事件订阅，`components/` 各面板，`api.ts` 桥接与浏览器预览数据。

## 测试与发布

- PR 和 `main` push 在 Windows/Python 3.11 上运行 pytest，并单独构建前端。
- 后端测试不依赖 GUI；设备命令使用替身，不等同于真机验收。
- exe 构建先构建前端，打包前校验内置工具；`verify_exe.py` 在无 SDK 环境验证内置工具哈希与元数据读取。
