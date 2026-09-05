# Anchor 文档

## 技术路径
- **运行方式**：本地 Python 3（内置 Tkinter GUI），不依赖额外 GUI 框架。
- **UI 装配**：`App` 创建并持有 Tk 变量、配置和任务状态，初始化后调用一次 `ui_layout.build_ui`。布局模块按设备、包选择、执行和日志分段构建，绑定 App 提供的变量/回调并挂接控件引用；不读取配置、不创建运行状态、不执行设备操作。后台线程和主线程回写仍由 App 编排。
- **视觉配置**：`ui_styles.py` 按四列基准宽度与实际原生边距/滚动条测量初始宽度（当前约 590x740），最小 480x560；后续刷新不改变用户窗口尺寸。设备列根据实际文本测量宽度，长内容通过水平滚动访问；集中管理设备行数、下拉可视行数、列宽/标题与高亮，保留平台原生 ttk 主题。
- **可达性**：设备、安装包、日志三区位于 `ScrollableArea`，采用紧凑标题和自然宽度按钮；底部安装/中止按钮和紧凑状态摘要固定。底栏/下拉框显示不全时，在对应区域展开完整摘要；不让长摘要撑高底栏。`ActionRow` 按控件实际请求宽度换行，名称/目录行在空间不足时将操作移到下一行。滚轮绑定仅限当前窗口，设备表/下拉/日志保留自身滚动；Tab 焦点自动显露，Ctrl+Home/End 与 Ctrl+PageUp/PageDown 控制页面，销毁容器时清理绑定。
- **日志输出**：普通刷新只在首次或设备 ID/平台/状态、包目录/候选文件/大小/修改时间、扫描后选择发生变化时写结果日志。错误始终记录，恢复或清空日志后下一次成功刷新重新记录；安装前校验与安装命令、输出、结果不参与去重。扫描目录无效或文件读取失败会明确提示，不记成功日志。
- **线程策略**：设备刷新、安装前探测与 UDID 获取在后台线程执行，避免 UI 主线程阻塞。
- **设备探测**：
  - Android：`adb devices -l`
    - 过滤规则：跳过 `emulator-xxx` 设备，不计入设备列表。
  - Harmony：`hdc list targets`；`DeviceDetectionResult` 分开返回设备与 Harmony 错误，HDC 失败仍保留可用 Android。返回码非零、`[Fail]` 输出、工具缺失或无法启动均为失败，不能记为空列表成功。
- **HDC 寻址**：`services/hdc.py` 统一解析，优先级为 `HDC_EXECUTABLE` → `HDC_PATH` → `DEVECO_SDK_HOME` → PATH → Windows 常见 DevEco SDK 位置（详见 README）。显式配置失败即报错；没有全局缓存，每项操作保留已解析路径，安装日志与实际执行、NEXTdemo 查找与拉取不各自换工具。
- **设备列表**：默认至少 4 行，设备较多时最多展示 8 行并滚动访问其余项；行高根据字体测量，避免缩放后文字裁切。刷新后相对上次新增的设备置顶并以浅绿色高亮。
- **状态显示**：表格视觉顺序为名称、平台、状态、设备码，行身份仍为 `device_id`，状态保留探测原值。`ui_display.py` 统一名称、平台和摘要格式化；统计表示当前检测列表，不将未授权/离线设备宣称为可安装。
  - 设备刷新完成后同步统计及当前选择；执行区与底部状态栏绑定同一个选择摘要，选择、取消选择、重命名及设备断开后同步更新。
  - 摘要中没有自定义名称时显示设备码；命名输入框读取真实配置，不把显示回退值写入配置。
  - 包摘要反映当前 APK/HAP 选择，扫描空目录后清空；安装过程中改变当前选择不改变已冻结的安装参数，实际任务目标以安装请求日志为准。
  - 统计、完整摘要与紧凑底栏共享 App 变量；窗口内容超高时通过页面滚动访问，不裁掉关键操作。布局及摘要换行由 `ui_layout.py` 维护。
- **最新安装包**：APK/HAP 默认选中最新文件，下拉列表按修改时间展示目录内全部候选；下拉面板最多显示 10 行，更多候选通过滚动访问。
- **联动刷新**：界面的“刷新设备”和“扫描最新包”按钮都会触发设备检测与当前安装包目录扫描，设备刷新期间两个入口同步禁用。
- **Harmony 部分探测失败**：刷新日志保留原因和可用 Android 数量；恢复后首次普通刷新重新记录成功，随后继续去重。安装前若原选择包含 Harmony 或无法确认的平台则停止；纯 Android 选择可继续，避免自动转移到其他设备。
- **安装前刷新**：点击安装后立即记录请求目标，再刷新设备列表；校验完成日志包含耗时，并使用点击瞬间的设备 ID 快照显式恢复仍在线设备的选中状态。已选设备断开会提示，若仅剩单设备则默认安装到该设备。
- **安装状态**：安装中按钮文案切换为“中止安装”，请求中止后显示“正在中止…”并禁用，任务结束后恢复。
  - 单个命令非零退出显示“安装失败”，有目标被跳过显示“安装未完成”，运行异常显示“安装异常”；仅用户主动中止显示“已中止”。安装前探测异常也恢复操作状态，并同步日志和提示。
  - 平台限定动作由 App 根据当前单选设备及刷新/安装/UDID/日志忙碌状态统一更新；任务结束重新计算可用性，不盲目启用旧选择的动作。UDID worker 异常恢复按钮并显示失败。
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
- **NEXTdemo 日志采集**：设备列表新增“获取NEXTdemo日志”按钮，按相对路径 `haps/entry/files/log-ads` 在 `/data/app` 下匹配目录并打包为 zip；任一拉取命令失败均返回该命令的返回码和输出，不把失败或不完整拉取当作空结果成功。
- **日志输出目录**：Windows 默认输出到 `D:\`；非 Windows 输出到 `~/install_new_apk_hap_logs`。
- **Windows 运行**：调用 adb/hdc 时使用无控制台模式，避免弹窗闪现。
- **配置文件**：`%APPDATA%/install_new_apk_hap/app_config.json`（Windows）
  - `device_names`：设备自定义命名
  - `last_scan_dir`：最近扫描目录
  - `apk_needs_t`：需要 `-t` 的 APK 名称列表；保存按钮会按当前复选框状态新增或删除对应记忆
  - **生成规则**：首次运行自动创建；exe 运行后在 AppData 目录生成/更新
- **自动化打包**：GitHub Actions 在 Windows 环境使用 PyInstaller 生成 exe，可手动触发或打 tag；tag 触发时会将 exe 上传到 release assets。
  - 当前候选版本 `v0.7.0`；分支手动构建的版本输入必须匹配 `VERSION`，产物仍需按运行 SHA 区分。PR 交付不等于正式 tag/Release 发布。
- **PR 验证**：`tests.yml` 在 PR 和 main push 时运行 Windows/Python 3.11 测试，包含真实 Tk 事件及窗口布局检查，不执行设备命令或发布制品。
  - `pytest.ini` 使用 `--capture=sys` 保留 Python 输出捕获，避免 Windows 文件描述符捕获造成间歇性的 Tcl 库读取失败；布局测试逐项隔离 Tk 窗口和状态。


## 代码分析基线（2026-05-28）
- **入口与状态管理**：`App` 负责 UI 组件装配与交互编排，安装状态、刷新状态、UDID/日志抓取状态通过实例字段统一管理。
- **并发模型**：设备刷新、安装执行、UDID 获取、日志抓取均通过后台线程 + `after` 回主线程更新 UI，避免 Tk 跨线程直接写控件。
- **安装链路一致性**：安装命令由 `services/installer.py` 统一封装，Android/Harmony 分流执行；支持中止事件轮询，并在 Windows 下使用 `CREATE_NO_WINDOW`。
- **设备探测与过滤**：`device_detector` 对 `adb devices -l` 与 `hdc list targets` 做最小解析，明确过滤 Android 模拟器与 Harmony 空列表占位。
- **包扫描策略**：`package_scanner` 对 APK/HAP 各扫描一次并按文件修改时间排序，返回“最新项 + 全部候选”，避免重复遍历目录。
- **配置持久化**：`config_manager` 以 JSON 持久化 `device_names`、`last_scan_dir`、`apk_needs_t`，首次运行自动落盘默认配置，并支持幂等新增或删除 APK 的 `-t` 记忆。

## 目录结构与职责
- `src/main.py`：应用状态、交互处理、后台任务与主线程回写入口
- `src/ui_layout.py`：一次性 UI 装配；设备/包选择/执行/日志构建与事件绑定
- `src/ui_styles.py`：现有视觉常量与窗口/Treeview 配置，保留原生 ttk 主题
- `src/ui_widgets.py`：页面滚动、焦点显露、窗口内滚轮与动作换行；无业务状态或设备服务
- `src/ui_display.py`：无 Tk 依赖的显示格式化；不持有运行状态或执行设备命令
- `src/services/hdc.py`：共享 HDC 路径解析与配置错误
- `src/services/device_detector.py`：设备检测与 Harmony 诊断
- `src/services/package_scanner.py`：扫描最新 apk/hap
- `src/services/installer.py`：安装执行
- `src/config_manager.py`：配置加载/保存
- `.github/workflows/build-exe.yml`：Windows exe 自动化打包流程
- `.github/workflows/tests.yml`：PR 与主线测试检查
- `docs/ui_refactor_tracking.md`：已合入进展、阶段依赖与旧 PR 的证据边界

## 版本管理
- **版本号规则**：`v主.次.修`
- **变更类型标记**：`refactor`、`feature`、`bugfix`
- **变更记录**：所有版本变更写入 `CHANGELOG.md`，按倒序展示

## 修改日志稳定要求
- 只允许在 `CHANGELOG.md` 中追加版本条目，不修改历史条目。
- 重大重构、文档版本治理或行为变更必须同步更新本 Anchor 文档。
- 新功能开发时必须在本 Anchor 文档同步记录技术路径变化；当对历史版本做汇总归并时，必须在 `CHANGELOG.md` 与本 Anchor 文档同时落地，防止实现与修改日志漂移。
