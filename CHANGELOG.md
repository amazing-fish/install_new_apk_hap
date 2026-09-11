# 变更记录

## v0.8.5 - docs / maintenance（待发布）

- README 与当前主线同步，覆盖 APK/HAP 名称与版本解析、自动 `testOnly/-t` 策略、3 行设备区、按需滚动条和当前日志能力。
- Android 安装不再保留手工 `-t` 复选框或按文件名记忆：只有明确解析到 `testOnly=false` 时省略 `-t`，其余状态默认使用 `-t`，解析失败不会阻塞安装。
- Harmony APP 日志改为固定路径直接 `hdc file recv`：
  - 乾崑：`/data/app/el2/100/base/com.yinwang.qiankunapp.hm/haps/phone/files/qklog/`
  - Demo：`/data/app/el2/100/base/adsmobilesdk.all.huawei/haps/entry/files`
- “获取APP日志”菜单统一承载乾崑/Demo 日志；不再对 `/data/app` 执行全局 `find`。拉取后分别生成 `qiankun_logs_*.zip` / `demo_logs_*.zip`，失败保留 HDC 返回码和输出。
- APK/HAP 下拉框直接显示应用名、版本号与真实文件名，不再重复第二排摘要。
- 设备列表默认至少 3 行；页面、设备表和日志滚动条仅在真实溢出时显示。
- 文档职责收敛：README 面向使用者，`docs/anchor.md` 记录当前架构约束，`docs/ui_refactor_tracking.md` 仅保留历史归档。
- Windows EXE 构建示例改为直接读取 `VERSION`，避免文档中的版本号与仓库实际版本漂移。

对应主线改动包括 PR #58、#60、#62、#64。

## v0.8.2 - bugfix

- Windows x64 单文件 exe 内置固定版本的 AAPT2 与 RestoolV2，直接下载即可读取支持格式的 APK/HAP 名称，不依赖开发机 SDK 或启动脚本。
- 显式工具路径覆盖保持优先；默认使用 onefile 自身解包目录，不被 PATH 中旧版工具抢先。
- 构建时校验内置工具与 NOTICE 的 SHA-256，并在无 SDK 配置环境中验证最终 exe、包解析、工具哈希和许可导出。
- 增加无 GUI 的包名称诊断报告与第三方许可导出命令。
- 修复 Conda 环境下 PyInstaller 打包时 Tcl/Tk DLL 搜索问题。

## v0.8.1 - bugfix

- 正常 APK 即使包含超过 10,000 个文件，也改为按 1 MiB ZIP 目录字节预算判断，不再被固定条目数误拦。
- SDK 拒绝解析与元数据读取失败分开显示，并在后续刷新重试。
- 补充 RestoolV2 与旧版 restool 的兼容边界和回归覆盖。

## v0.8.0 - feature

- APK/HAP 下拉框开始展示真实应用名称与文件名。
- APK 使用 AAPT2，HAP 支持明确 label 字段和 restool 默认字符串资源。
- 元数据读取放入单 worker，合并重复请求、忽略过期目录结果并使用文件/工具指纹缓存。
- 保留真实文件路径作为安装身份，不因显示名称重名而混淆安装目标。

## v0.7.0 - feature

- 统一 Harmony HDC 路径解析，支持 `HDC_EXECUTABLE`、`HDC_PATH`、`DEVECO_SDK_HOME`、PATH 和 Windows 常见 DevEco SDK 目录。
- 显式配置无效时直接报错，不静默切换其他 HDC。
- HDC 探测失败与“无设备”分离；失败时保留已检测到的 Android 设备。
- Harmony 安装、UDID 与日志动作共享同一套 HDC 解析规则。

## v0.6.0 - feature

- 完成设备、安装包、日志三区的紧凑原生 UI 重构。
- 固定底部安装/中止入口，支持窄窗口、长内容滚动和键盘访问。
- 设备/包摘要、设备命名、选择状态和日志去重逻辑统一。
- 安装失败、安装异常、跳过目标和用户中止分别保留独立状态语义。

## v0.4.x - feature / bugfix（汇总）

- 增加 Android/Harmony 崩溃日志采集、Harmony UDID、设备新增高亮等能力。
- 安装线程改为使用主线程冻结的设备/包/参数快照，避免 Tk 跨线程读取和安装期间选择变化导致任务漂移。
- 安装前增加设备重新校验；刷新设备与扫描包入口联动。
- Windows EXE 构建流程逐步版本化。

## v0.3.x - feature / bugfix（汇总）

- 增加 Harmony UDID 获取和后台执行，避免慢 HDC 响应阻塞 UI。
- 增加命令返回码与输出有效性校验。

## v0.2.x - feature / bugfix（汇总）

- APK/HAP 默认选中最新候选并支持下拉选择。
- 安装支持中止；后台轮询降低空转 CPU。
- Android 设备检测过滤 `emulator-*`。

## v0.1.x - feature / bugfix（汇总）

- 完成首版 APK/HAP 安装 GUI：设备检测、包扫描、安装、设备命名和日志。
- 关键耗时操作后台线程化。
- 配置写入 Windows AppData。
- 建立 Windows EXE 自动化构建与 Release 资产流程。

> 更细的历史 PR/Issue 过程保留在 GitHub 提交、Issue 和 PR 中；本文件只维护版本级用户可见变化，不再重复记录实施流水账。
