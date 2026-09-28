# Anchor 文档

本文件只记录当前架构约束。历史实现、PR 过程和临时兼容方案不在这里长期保留。

## 核心流程

1. `App` 初始化配置、状态和 UI。
2. 设备刷新分别调用 ADB/HDC；Harmony 探测失败时保留已检测到的 Android 设备并明确记录原因。
3. 安装包扫描按文件修改时间排序，APK/HAP 各自默认选择最新候选。每种包一个 `packages.PackageSlot`（候选、元数据、选中索引）；下拉框只渲染 slot，选择按索引回报，显示文本从不用来反查文件。扫描失败保留上次结果。
4. 包元数据由单个后台 worker 异步读取；结果必须属于最近一次扫描且文件指纹未变才回写 UI，回写只改显示文本，不改选择。
5. 点击安装后冻结设备选择与 APK/HAP 路径，再执行一次设备 preflight；仍在线的原选择被恢复，未选择且只剩一台设备时自动选择该设备。preflight 通过后在主线程冻结安装计划（设备、驱动、包、显示名），安装期间刷新设备不影响目标。
6. 后台结果只有一种回到主线程的方式：worker 把回调放进 `controller.Inbox`（线程安全队列），主线程每 30 ms 取出执行。worker 线程不调用任何 Tk 接口（含 `after`）：主线程尚未进入 `mainloop` 时，跨线程 Tk 调用约 1 秒后抛错，结果会丢失。设备任务经 `controller.TaskRunner` 调度：安装、UDID、崩溃日志、APP 日志共用一个设备任务槽，同一时刻只有一个，均可由底部主按钮中止；设备刷新不占用该槽，最新结果胜出。
7. 单设备操作（UDID、崩溃日志、APP 日志、复制设备码、保存名称）与按钮可用性统一用 `controller.resolve_target`：选中一台用该台；未选且只有一台、且上次探测未失败时用那一台。

## APK/HAP 元数据

- APK 使用 AAPT2 的同一次 `dump badging` 读取应用名、包名、版本以及 `testOnly`。
- HAP 直接读取明确声明的 bundle/version/label 字段；资源型名称按需使用 RestoolV2。
- Windows 单文件 exe 内置固定版本的 AAPT2/RestoolV2；源码运行可使用外部 SDK 工具。
- 元数据是**增强信息，不是安装前置条件**。缺少工具、格式不支持、解析失败、读取受限或结果尚未返回，都不能阻止安装。
- APK 的 `-t` 策略只有一条：**默认使用 `-t`，只有当前已解析元数据明确 `test_only is False` 时才省略 `-t`**。不存在手工复选框、按文件名记忆或等待元数据后才能安装的状态。
- 元数据读取保持 ZIP/资源大小、工具输出和超时限制；不执行包内代码，也不通过文件名猜测元数据。

## UI 约束

- 使用 Tkinter/ttk，不引入额外 GUI 框架；外观只通过 ttk 主题 sv-ttk（`requirements.txt` 固定版本）提供，加载失败必须回退原生主题而不影响启动。exe 构建须打包 sv-ttk 数据文件，并由 `verify_exe.py` 检查主题生效。
- sv-ttk 的 `<<ThemeChanged>>` 调色板处理会覆盖控件颜色：`ui_styles.apply_theme` 在创建控件前同步执行一次并解除该绑定，运行期不切换主题。
- Windows 进程为系统 DPI 感知（`enable_high_dpi`），窗口初始尺寸与主题像素字号按 `ui_scale` 放大。
- sv-ttk 经 `src/ui_tile_fix.tcl` 加载：只加宽浅色主题中两端拉伸元素的贴图中段，并把元素自然尺寸固定为原贴图尺寸；外观与控件尺寸不变，只减少 Windows 上逐块 alpha 混合的平铺次数。exe 须打包该文件，`--theme-report` 的 `tile_fix_sprites` 必须大于 0；`INSTALL_APK_HAP_TILE_FIX=0` 可关闭以对比。
- 改变窗口尺寸时由 `ScrollableArea` 在顶层窗口自身的 `<Configure>` 中 `update_idletasks`，让多层 grid/pack 一次排定后再绘制；不得在子控件的 `<Configure>` 中同步排版（会打断正在进行的 grid 排版，画布不再映射、键盘焦点丢失）。
- 设备列表默认至少 3 行，最多 8 行；超过可见范围后滚动访问。
- 页面、设备表和日志的滚动条仅在内容真实溢出时显示，不需要滚动时不占布局空间。
- 设备操作区以一个“获取APP日志”菜单承载乾崑/Demo 两种 Harmony 应用日志，不为每个固定路径堆独立常驻按钮。
- 安装包区域只保留目录、APK 下拉框、HAP 下拉框；目录框回车扫描输入的目录；下拉文本可包含应用名、版本和真实文件名，不重复显示第二排摘要。
- 底部安装/中止按钮固定可达；长内容通过页面滚动、控件自身滚动或操作行换行处理。
- 设备表行身份始终是 `device_id`；自定义名称只影响显示，不替代设备身份。

## 安装语义

- Android：`adb -s <device_id> install [-t] <apk>`。
- Harmony：`hdc -t <device_id> install <hap>`。
- 安装请求冻结 APK/HAP 路径和当时计算出的 Android `allow_test`，之后切换下拉框不会改变进行中的任务。
- 已选设备断开会提示；单设备场景允许 preflight 后自动选择。
- 用户主动中止显示“已中止”；命令失败显示“安装失败”；目标被跳过显示“安装未完成”；运行异常显示“安装异常”。
- 安装判定：非零退出码失败；退出码 0 但某行以明确失败标记开头（hdc `[Fail]` / `error: failed to install`，adb `Failure [` / `adb: failed to install`）也判失败。输出文字永远不能把非零退出码改判为成功；stderr 本身只是输出通道。

## Harmony APP 日志

- APP 日志只支持当前单选的 Harmony 设备；Android、多选和无选择均不执行 HDC 拉取。
- 不在 `/data/app` 下执行全局 `find`，固定应用直接 `file recv`，避免额外遍历、同名目录歧义和搜索失败。
- 乾崑：`/data/app/el2/100/base/com.yinwang.qiankunapp.hm/haps/phone/files/qklog/`。
- Demo：`/data/app/el2/100/base/adsmobilesdk.all.huawei/haps/entry/files`。
- 实际命令为 `hdc -t <device_id> file recv <remote_path> <temporary_local_path>`。
- 拉取成功后将临时目录打包为 ZIP；Windows 输出到 `D:\`，文件名前缀分别为 `qiankun_logs_`、`demo_logs_`。
- `recv` 非零返回码必须保留完整命令、stdout/stderr 与返回码；命令成功但本地没有任何文件时明确报告空结果，不生成空 ZIP。
- 两种应用日志共享同一个拉取/打包实现（`HarmonyDriver.collect_app_log`），目标表为 `platforms/harmony.py` 中的 `APP_LOG_TARGETS`。

## 设备与工具

- 平台差异只写在 `platforms/` 的驱动里：调用方按 `driver_for(device.platform)` 取驱动，按能力（`package_kind`、`supports_udid`、`app_log_targets`）决定按钮可用性和操作校验，不按平台名分支。
- 崩溃日志只有一个流程：结果要么打包为 ZIP（`zip_path`），要么追加到文件（`appended_to`），两者都没有时按“无输出”提示并附原因。

- 所有外部命令（adb/hdc/aapt2/restool）只通过 `infra/process.run` 执行：无控制台窗口、stdin 为空、输出写临时文件（不会因管道写满而卡住）、支持超时/取消/输出上限；无法启动抛 `ToolLaunchError`，其余结果均为 `ProcessResult`。
- 超时：设备检测/UDID 15 秒，日志拉取 120 秒，安装不设超时但可中止。
- Android 探测：`adb devices -l`，过滤 `emulator-*`。adb 缺失、失败或超时记为 Android 探测错误，与 HDC 对称；任一平台探测失败时保留另一平台设备，且不做“单设备自动选择”。
- Harmony 探测：`hdc list targets`。
- 工具路径统一由 `infra/tools.py` 解析；显式配置无效时直接报错，不静默换用其他工具。
  - ADB：`ADB_EXECUTABLE` → PATH → `ANDROID_SDK_ROOT`/`ANDROID_HOME` 的 `platform-tools` → Windows `%LOCALAPPDATA%\Android\Sdk`。
  - HDC：`HDC_EXECUTABLE` → `HDC_PATH` → `DEVECO_SDK_HOME` → PATH → Windows 常见安装位置。
  - AAPT2 / RestoolV2：`AAPT2_EXECUTABLE` / `RESTOOL_EXECUTABLE` → exe 内置工具（仅冻结的单文件 exe）→ 源码运行时 PATH 与 SDK（aapt2 取 `build-tools` 最新数字版本，restool 取 HDC 同目录）。元数据可选，缺失或无效时记为不可用而不是报错。
- UDID、Harmony 安装、崩溃日志以及乾崑/Demo APP 日志均复用同一套 HDC 路径规则。

## 配置

Windows 配置文件：`%APPDATA%/install_new_apk_hap/app_config.json`。

当前持久化字段仅有：

- `device_names`：设备自定义名称。
- `last_scan_dir`：最近扫描目录。

旧版本配置中残留的未知字段可被读取但不会参与当前运行逻辑。

## 模块职责

- `src/main.py`：Tk 界面状态与交互编排，把结果渲染为日志、提示和按钮状态。
- `src/controller.py`：无 Tk 依赖的 `Inbox`（唯一的主线程回写通道）、`TaskRunner`（单任务槽、可取消、可注入同步执行）、`resolve_target`、安装计划冻结与逐台执行（`build_install_plan` / `run_install_plan`）。
- `src/ui_layout.py`：一次性 UI 装配与事件绑定，不读取业务配置。
- `src/ui_styles.py`：窗口、列宽、行高和视觉常量。
- `src/ui_widgets.py`：页面滚动、自动隐藏滚动条和操作行布局。
- `src/ui_display.py`：无 Tk 依赖的设备显示格式化。
- `src/config_manager.py`：最小配置持久化。
- `src/platforms/`：平台驱动。`base.py` 定义 `DeviceInfo`、`InstallResult`、`CollectResult` 与 `PlatformDriver`；`android.py`（adb）、`harmony.py`（hdc）各实现探测、安装命令、崩溃日志，Harmony 另有 UDID 与 APP 日志；`__init__.py` 提供 `DRIVERS`、`driver_for`、`detect_devices`。
- `src/packages.py`：无 Tk 依赖的包状态：候选扫描与 mtime 排序（`find_packages`）、`PackageSlot`、`-t` 规则（`apk_allow_test`）。
- `src/metadata/`：APK/HAP 元数据读取。`guard.py` 是读取边界（ZIP/资源大小、工具超时与输出上限、不可信文本过滤），`apk.py`、`hap.py` 只写格式规则且只经 `guard` 读取；`__init__.py` 的 `read_package_label` 按后缀分派并把预期失败映射为显示状态；`display.py` 生成下拉框文本；`loader.py` 是异步 worker、缓存和文件指纹校验。
- `src/cli.py`：无 GUI 诊断（包元数据报告、许可导出、主题报告）。
- `src/infra/process.py`：唯一的外部命令执行入口。
- `src/infra/tools.py`：adb/hdc/aapt2/restool 路径解析与共用的可执行文件判定。

## 测试与发布

- PR 和 `main` push 在 Windows/Python 3.11 上运行完整 pytest。
- Tk 布局、状态切换、元数据异步更新、安装参数快照、APP 日志固定路径与失败语义均有自动化覆盖。
- exe 构建流程在打包前校验内置工具和 NOTICE，并在隔离环境中验证产物；正式 Release/tag 与普通 PR 分开处理。
