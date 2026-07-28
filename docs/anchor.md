# Anchor 文档

## 技术路径
- **运行方式**：本地 Python 3（内置 Tkinter GUI），不依赖额外 GUI 框架。
- **日志输出**：日志窗口记录刷新、扫描、安装命令与执行结果，便于调试定位。
- **线程策略**：设备刷新、安装前探测与 UDID 获取在后台线程执行，避免 UI 主线程阻塞。
- **设备探测**：
  - Android：`adb devices -l`
    - 过滤规则：跳过 `emulator-xxx` 设备，不计入设备列表。
  - Harmony：`hdc list targets`
- **设备列表**：行数在 8 条以内根据设备数量自适应高度，避免空白占位；刷新后相对上次新增的设备会置顶并以浅绿色高亮。
- **最新安装包**：APK/HAP 默认选中最新文件，下拉列表按修改时间展示目录内全部候选；下拉面板最多显示 10 行，更多候选通过滚动访问。
- **联动刷新**：界面的“刷新设备”和“扫描最新包”按钮都会触发设备检测与当前安装包目录扫描，设备刷新期间两个入口同步禁用。
- **安装前刷新**：点击安装后立即记录请求目标，再刷新设备列表；校验完成日志包含耗时，并使用点击瞬间的设备 ID 快照显式恢复仍在线设备的选中状态。已选设备断开会提示，若仅剩单设备则默认安装到该设备。
- **安装状态**：安装中按钮文案切换为“中止下载”，支持中止当前安装流程并更新状态显示。
  - 稳定性约束：安装线程不直接读取 Tk 变量；安装参数在主线程快照后传入后台线程，避免设备断连/重连场景下 UI 状态卡在“正在中止”。
  - 快照时机约束：安装参数（APK/HAP 路径与 `-t`）在点击安装时立即快照，并贯穿安装前刷新流程传递，避免预刷新期间切换包选择影响进行中的任务。
  - 包一致性约束：安装线程使用主线程快照的 APK/HAP 路径与 `-t` 配置，避免安装过程中切换下拉选择造成“包与参数不匹配”。
  - 异常语义约束：仅当用户主动中止时显示“已中止”；安装命令运行异常需显示“安装异常”，避免将运行时故障误报为用户中止。
- **安装命令**：
  - Android：`adb -s <device_id> install [-t] <apk>`
  - Harmony：`hdc -t <device_id> install <hap>`
  - 日志在命令启动前同步冻结完整命令及时间戳，再交由 Tk 主线程按队列渲染；命令返回后记录返回码、执行耗时，并逐行保留标准输出和错误输出。
- **UDID 获取**：设备列表“获取UDID”按钮支持对 NEXT（Harmony）设备执行 `hdc -t <device_id> shell bm get --udid`；仅在命令返回成功且输出有效时才展示并复制 UDID，Android 设备会提示仅支持 NEXT。
- **崩溃日志采集**：设备列表“获取崩溃日志”按钮会根据选中设备平台自动分发；Android 执行 `adb -s <device_id> shell dumpsys dropbox --print` 并追加写入日志文件，Harmony 拉取 `/data/log/faultlog/faultlogger` 后筛选最近 7 天含 `crash` 关键字的文件并打包为 zip。
- **NEXTdemo 日志采集**：设备列表新增“获取NEXTdemo日志”按钮，按相对路径 `haps/entry/files/log-ads` 在 `/data/app` 下匹配目录并打包为 zip。
- **日志输出目录**：Windows 默认输出到 `D:\`；非 Windows 输出到 `~/install_new_apk_hap_logs`。
- **Windows 运行**：调用 adb/hdc 时使用无控制台模式，避免弹窗闪现。
- **配置文件**：`%APPDATA%/install_new_apk_hap/app_config.json`（Windows）
  - `device_names`：设备自定义命名
  - `last_scan_dir`：最近扫描目录
  - `apk_needs_t`：需要 `-t` 的 APK 名称列表；保存按钮会按当前复选框状态新增或删除对应记忆
  - **生成规则**：首次运行自动创建；exe 运行后在 AppData 目录生成/更新
- **自动化打包**：GitHub Actions 在 Windows 环境使用 PyInstaller 生成 exe，可手动触发或打 tag；tag 触发时会将 exe 上传到 release assets。


## 代码分析基线（2026-05-28）
- **入口与状态管理**：`App` 负责 UI 组件装配与交互编排，安装状态、刷新状态、UDID/日志抓取状态通过实例字段统一管理。
- **并发模型**：设备刷新、安装执行、UDID 获取、日志抓取均通过后台线程 + `after` 回主线程更新 UI，避免 Tk 跨线程直接写控件。
- **安装链路一致性**：安装命令由 `services/installer.py` 统一封装，Android/Harmony 分流执行；支持中止事件轮询，并在 Windows 下使用 `CREATE_NO_WINDOW`。
- **设备探测与过滤**：`device_detector` 对 `adb devices -l` 与 `hdc list targets` 做最小解析，明确过滤 Android 模拟器与 Harmony 空列表占位。
- **包扫描策略**：`package_scanner` 对 APK/HAP 各扫描一次并按文件修改时间排序，返回“最新项 + 全部候选”，避免重复遍历目录。
- **配置持久化**：`config_manager` 以 JSON 持久化 `device_names`、`last_scan_dir`、`apk_needs_t`，首次运行自动落盘默认配置，并支持幂等新增或删除 APK 的 `-t` 记忆。

## 目录结构与职责
- `src/main.py`：UI 与交互入口
- `src/services/device_detector.py`：设备检测
- `src/services/package_scanner.py`：扫描最新 apk/hap
- `src/services/installer.py`：安装执行
- `src/config_manager.py`：配置加载/保存
- `.github/workflows/build-exe.yml`：Windows exe 自动化打包流程

## 版本管理
- **版本号规则**：`v主.次.修`
- **变更类型标记**：`refactor`、`feature`、`bugfix`
- **变更记录**：所有版本变更写入 `CHANGELOG.md`，按倒序展示

## 修改日志稳定要求
- 只允许在 `CHANGELOG.md` 中追加版本条目，不修改历史条目。
- 重大重构、文档版本治理或行为变更必须同步更新本 Anchor 文档。
- 新功能开发时必须在本 Anchor 文档同步记录技术路径变化；当对历史版本做汇总归并时，必须在 `CHANGELOG.md` 与本 Anchor 文档同时落地，防止实现与修改日志漂移。
