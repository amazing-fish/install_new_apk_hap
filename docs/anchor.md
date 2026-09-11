# Anchor 文档

本文件只记录当前架构约束。历史实现、PR 过程和临时兼容方案不在这里长期保留。

## 核心流程

1. `App` 初始化配置、状态和 UI。
2. 设备刷新分别调用 ADB/HDC；Harmony 探测失败时保留已检测到的 Android 设备并明确记录原因。
3. 安装包扫描按文件修改时间排序，APK/HAP 各自默认选择最新候选。
4. 包元数据由单个后台 worker 异步读取；结果必须匹配当前请求、目录和文件指纹才回写 UI。
5. 点击安装后冻结设备选择与 APK/HAP 路径，再执行一次设备 preflight；仍在线的原选择被恢复，未选择且只剩一台设备时自动选择该设备。
6. 安装和日志采集均在线程中执行，状态、日志和提示通过 Tk 主线程更新。

## APK/HAP 元数据

- APK 使用 AAPT2 的同一次 `dump badging` 读取应用名、包名、版本以及 `testOnly`。
- HAP 直接读取明确声明的 bundle/version/label 字段；资源型名称按需使用 RestoolV2。
- Windows 单文件 exe 内置固定版本的 AAPT2/RestoolV2；源码运行可使用外部 SDK 工具。
- 元数据是**增强信息，不是安装前置条件**。缺少工具、格式不支持、解析失败、读取受限或结果尚未返回，都不能阻止安装。
- APK 的 `-t` 策略只有一条：**默认使用 `-t`，只有当前已解析元数据明确 `test_only is False` 时才省略 `-t`**。不存在手工复选框、按文件名记忆或等待元数据后才能安装的状态。
- 元数据读取保持 ZIP/资源大小、工具输出和超时限制；不执行包内代码，也不通过文件名猜测元数据。

## UI 约束

- 使用原生 Tkinter/ttk，不引入额外 GUI 框架。
- 设备列表默认至少 3 行，最多 8 行；超过可见范围后滚动访问。
- 页面、设备表和日志的滚动条仅在内容真实溢出时显示，不需要滚动时不占布局空间。
- 设备操作区以一个“获取APP日志”菜单承载乾崑/Demo 两种 Harmony 应用日志，不为每个固定路径堆独立常驻按钮。
- 安装包区域只保留目录、APK 下拉框、HAP 下拉框；下拉文本可包含应用名、版本和真实文件名，不重复显示第二排摘要。
- 底部安装/中止按钮固定可达；长内容通过页面滚动、控件自身滚动或操作行换行处理。
- 设备表行身份始终是 `device_id`；自定义名称只影响显示，不替代设备身份。

## 安装语义

- Android：`adb -s <device_id> install [-t] <apk>`。
- Harmony：`hdc -t <device_id> install <hap>`。
- 安装请求冻结 APK/HAP 路径和当时计算出的 Android `allow_test`，之后切换下拉框不会改变进行中的任务。
- 已选设备断开会提示；单设备场景允许 preflight 后自动选择。
- 用户主动中止显示“已中止”；命令失败显示“安装失败”；目标被跳过显示“安装未完成”；运行异常显示“安装异常”。
- Windows 下外部命令使用无控制台模式，避免弹窗闪现。

## Harmony APP 日志

- APP 日志只支持当前单选的 Harmony 设备；Android、多选和无选择均不执行 HDC 拉取。
- 不在 `/data/app` 下执行全局 `find`，固定应用直接 `file recv`，避免额外遍历、同名目录歧义和搜索失败。
- 乾崑：`/data/app/el2/100/base/com.yinwang.qiankunapp.hm/haps/phone/files/qklog/`。
- Demo：`/data/app/el2/100/base/adsmobilesdk.all.huawei/haps/entry/files`。
- 实际命令为 `hdc -t <device_id> file recv <remote_path> <temporary_local_path>`。
- 拉取成功后将临时目录打包为 ZIP；Windows 输出到 `D:\`，文件名前缀分别为 `qiankun_logs_`、`demo_logs_`。
- `recv` 非零返回码必须保留完整命令、stdout/stderr 与返回码；命令成功但本地没有任何文件时明确报告空结果，不生成空 ZIP。
- 两种应用日志共享同一个拉取/打包实现；旧 `run_harmony_nextdemo_log_zip()` 仅作为内部兼容入口映射到 Demo 固定路径，不再执行搜索。

## 设备与工具

- Android 探测：`adb devices -l`，过滤 `emulator-*`。
- Harmony 探测：`hdc list targets`。
- HDC 路径统一由 `services/hdc.py` 解析，优先级为显式环境配置、DevEco SDK、PATH 和 Windows 常见安装位置；显式配置无效时直接报错，不静默换用其他工具。
- UDID、Harmony 安装、崩溃日志以及乾崑/Demo APP 日志均复用同一套 HDC 路径规则。

## 配置

Windows 配置文件：`%APPDATA%/install_new_apk_hap/app_config.json`。

当前持久化字段仅有：

- `device_names`：设备自定义名称。
- `last_scan_dir`：最近扫描目录。

旧版本配置中残留的未知字段可被读取但不会参与当前运行逻辑。

## 模块职责

- `src/main.py`：应用状态、交互编排、后台任务与主线程回写。
- `src/ui_layout.py`：一次性 UI 装配与事件绑定，不读取业务配置。
- `src/ui_styles.py`：窗口、列宽、行高和视觉常量。
- `src/ui_widgets.py`：页面滚动、自动隐藏滚动条和操作行布局。
- `src/ui_display.py`：无 Tk 依赖的显示格式化。
- `src/config_manager.py`：最小配置持久化。
- `src/services/device_detector.py`：ADB/HDC 设备探测。
- `src/services/installer.py`：安装命令以及设备日志拉取/打包的命令执行。
- `src/services/package_scanner.py`：候选包扫描和 mtime 排序。
- `src/services/package_metadata.py`：APK/HAP 元数据读取。
- `src/services/package_label_loader.py`：异步元数据 worker、缓存和文件指纹校验。
- `src/services/hdc.py`：HDC 可执行文件解析。

## 测试与发布

- PR 和 `main` push 在 Windows/Python 3.11 上运行完整 pytest。
- Tk 布局、状态切换、元数据异步更新、安装参数快照、APP 日志固定路径与失败语义均有自动化覆盖。
- exe 构建流程在打包前校验内置工具和 NOTICE，并在隔离环境中验证产物；正式 Release/tag 与普通 PR 分开处理。
