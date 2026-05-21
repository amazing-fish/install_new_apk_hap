# 变更记录

## v0.5.2 - bugfix
- 修复 HAP JSON 元数据仅按顶层 key 解析导致的应用名丢失问题：`module.json/pack.info` 现支持递归遍历对象与数组，兼容 `module.name` 等嵌套结构，避免错误回退到文件名。

## v0.5.1 - bugfix
- 修复仅包含 `module.json5` 的 HAP 应用名解析错误：改为按 `key: "value"` 提取冒号后的字符串，避免出现 `label\": \"My App` 这类异常展示文本。

## v0.5.0 - feature
- 新增安装包应用名称展示：扫描后在“安装到所选设备”按钮上方一行展示 APK/HAP 应用名称。
- 安装包下拉框展示从“仅文件名”升级为“应用名称（文件名）”，解析失败自动回退文件名。

## v0.4.3 - bugfix
- 修复 PR #24 覆盖 Android 崩溃日志入口的问题：“获取崩溃日志”会根据选中设备平台自动分发，Android 走 `adb dumpsys dropbox`，Harmony 走 `hdc faultlogger` 打包。

## v0.4.2 - feature
- 刷新设备列表时识别相对上次新增的设备，将新增设备置顶并以浅绿色高亮，同时在日志区记录新增设备码。

## v0.4.1 - feature
- 设备列表“获取崩溃日志”改为 Harmony 场景：拉取 `/data/log/faultlog/faultlogger` 后筛选最近 7 天 crash 文件并打包 zip。
- 新增“获取NEXTdemo日志”按钮：匹配相对路径 `haps/entry/files/log-ads`，批量拉取并打包 zip。
- 日志打包路径统一：Windows 输出到 `D:\`，非 Windows 输出到 `~/install_new_apk_hap_logs`。

## v0.4.0 - feature
- 设备列表新增“获取崩溃日志”按钮，支持对 Android 设备执行 `adb -s <device_id> shell dumpsys dropbox --print`。
- 崩溃日志获取成功后会将输出内容追加写入 `D:\crash.log`，并在日志区记录执行命令与结果。

## v0.3.3 - bugfix
- 获取 UDID 时增加 `hdc` 返回码校验：仅当命令成功（exit code = 0）且输出有效时才认定为成功，避免将错误文本当作 UDID 展示与复制。

## v0.3.2 - bugfix
- 获取UDID改为后台线程执行，避免 `hdc` 响应慢时阻塞 Tk 主线程导致界面卡死。
- 获取UDID过程中按钮会临时禁用并提示“获取 UDID 中：请稍候”，完成后恢复。

## v0.3.1 - bugfix
- 设备操作按钮文案由“获取 HDC UDID”调整为“获取UDID”。
- 选中 Android 设备获取 UDID 时提示“仅支持NEXT”，明确仅支持 NEXT（Harmony）设备。

## v0.3.0 - feature
- 设备列表新增“获取 HDC UDID”按钮，针对 Harmony 设备执行 `hdc -t 设备序列号 shell bm get --udid`。
- 获取成功后会弹窗展示 UDID，并自动复制到剪贴板，日志同步记录。

## v0.2.3 - bugfix
- Android 设备探测时过滤 emulator-xxx，避免虚拟设备进入设备列表与刷新日志统计。

## v0.2.2 - bugfix
- 安装执行轮询增加等待，避免空转占用 CPU。

## v0.2.1 - feature
- 安装中按钮文案切换为“中止下载”，支持中止安装流程并显示状态。

## v0.2.0 - feature
- APK/HAP 默认选中最新安装包，下拉列表展示最近 5 个候选。
## v0.1.13 - bugfix
- 默认大小下设备列表缩减设备码与名称列宽。

## v0.1.12 - feature
- 日志区域支持复制与清空按钮，日志框保持只读写入。

## v0.1.11 - bugfix
- tag 触发的 release 构建会将 exe 上传到 release assets。
- 默认窗口宽度调整为 500dp。

## v0.1.10 - bugfix
- 刷新设备列表与安装前探测改为后台线程执行，避免 exe 刷新时主线程卡死。
- Windows 打包运行时调用 adb/hdc 使用无控制台模式，避免弹窗闪现。

## v0.1.9 - bugfix
- 配置文件路径调整为 AppData 目录，统一 exe 与本地运行配置位置。

## v0.1.8 - bugfix
- 补充本地配置生成与 exe 运行时配置更新说明。

## v0.1.7 - feature
- 增加 GitHub Actions 自动化打包 Windows exe 的流程。
- 忽略本地配置目录，避免提交运行时配置文件。

## v0.1.6 - bugfix
- 安装前刷新设备列表，断开设备提示并在仅剩单设备时自动默认安装。

## v0.1.5 - bugfix
- 变更记录改为倒序展示，保持版本阅读一致性。

## v0.1.4 - bugfix
- 设备列表行数在 8 条以内自动贴合设备数量，避免空白占位。

## v0.1.3 - bugfix
- 单设备场景下可直接保存设备名称，无需手动选中设备。
- 安装流程改为后台线程执行，避免界面卡死。

## v0.1.2 - feature
- 设备列表展示设备码、名称、状态与平台信息。
- 修复 hdc 输出 [Empty] 时误显示鸿蒙设备的问题。

## v0.1.1 - feature
- 调试阶段补充设备刷新、目录扫描、安装命令与结果的详细日志输出。

## v0.1.0 - feature
- 初始版本：提供设备检测、最新安装包扫描、安装与自定义命名功能。
