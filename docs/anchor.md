# Anchor 文档

## 技术路径
- **运行方式**：本地 Python 3（内置 Tkinter GUI），不依赖额外 GUI 框架。
- **日志输出**：日志窗口记录刷新、扫描、安装命令与执行结果，便于调试定位。
- **线程策略**：设备刷新与安装前探测在后台线程执行，避免 UI 主线程阻塞。
- **设备探测**：
  - Android：`adb devices -l`
  - Harmony：`hdc list targets`
- **设备列表**：行数在 8 条以内根据设备数量自适应高度，避免空白占位。
- **安装前刷新**：点击安装前刷新设备列表，已选设备断开会提示，若仅剩单设备则默认安装到该设备。
- **安装命令**：
  - Android：`adb -s <device_id> install [-t] <apk>`
  - Harmony：`hdc -t <device_id> install <hap>`
- **Windows 运行**：调用 adb/hdc 时使用无控制台模式，避免弹窗闪现。
- **配置文件**：`%APPDATA%/install_new_apk_hap/app_config.json`（Windows）
  - `device_names`：设备自定义命名
  - `last_scan_dir`：最近扫描目录
  - `apk_needs_t`：需要 `-t` 的 APK 名称列表
  - **生成规则**：首次运行自动创建；exe 运行后在 AppData 目录生成/更新
- **自动化打包**：GitHub Actions 在 Windows 环境使用 PyInstaller 生成 exe，可手动触发或打 tag；tag 触发时会将 exe、SHA256 校验文件与 GPG 签名上传到 release assets。

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
