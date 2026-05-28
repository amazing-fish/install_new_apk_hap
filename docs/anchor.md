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
- **最新安装包**：APK/HAP 默认选中最新文件，下拉列表展示最近 5 个候选。
- **安装前刷新**：点击安装前刷新设备列表，已选设备断开会提示，若仅剩单设备则默认安装到该设备。
- **安装状态**：安装中按钮文案切换为“中止下载”，支持中止当前安装流程并更新状态显示。
  - 稳定性约束：安装线程不直接读取 Tk 变量；安装参数在主线程快照后传入后台线程，避免设备断连/重连场景下 UI 状态卡在“正在中止”。
- **安装命令**：
  - Android：`adb -s <device_id> install [-t] <apk>`
  - Harmony：`hdc -t <device_id> install <hap>`
- **UDID 获取**：设备列表“获取UDID”按钮支持对 NEXT（Harmony）设备执行 `hdc -t <device_id> shell bm get --udid`；仅在命令返回成功且输出有效时才展示并复制 UDID，Android 设备会提示仅支持 NEXT。
- **崩溃日志采集**：设备列表“获取崩溃日志”按钮会根据选中设备平台自动分发；Android 执行 `adb -s <device_id> shell dumpsys dropbox --print` 并追加写入日志文件，Harmony 拉取 `/data/log/faultlog/faultlogger` 后筛选最近 7 天含 `crash` 关键字的文件并打包为 zip。
- **NEXTdemo 日志采集**：设备列表新增“获取NEXTdemo日志”按钮，按相对路径 `haps/entry/files/log-ads` 在 `/data/app` 下匹配目录并打包为 zip。
- **日志输出目录**：Windows 默认输出到 `D:\`；非 Windows 输出到 `~/install_new_apk_hap_logs`。
- **Windows 运行**：调用 adb/hdc 时使用无控制台模式，避免弹窗闪现。
- **配置文件**：`%APPDATA%/install_new_apk_hap/app_config.json`（Windows）
  - `device_names`：设备自定义命名
  - `last_scan_dir`：最近扫描目录
  - `apk_needs_t`：需要 `-t` 的 APK 名称列表
  - **生成规则**：首次运行自动创建；exe 运行后在 AppData 目录生成/更新
- **自动化打包**：GitHub Actions 在 Windows 环境使用 PyInstaller 生成 exe，可手动触发或打 tag；tag 触发时会将 exe 上传到 release assets。

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
- 重大重构或行为变更必须同步更新本 Anchor 文档。
- 新功能开发时必须在本 Anchor 文档同步记录技术路径变化，防止实现与修改日志漂移。
