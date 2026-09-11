# install_new_apk_hap

一个面向 Android / Harmony 设备的桌面安装与日志辅助工具：扫描目录中的 APK/HAP，识别包信息，安装到已连接设备，并提供常用设备与日志操作。

当前版本：`v0.8.5`

## 功能概览

- 自动检测 Android（ADB）与 Harmony（HDC）设备。
- 扫描目录内全部 APK/HAP，默认选中修改时间最新的安装包。
- 后台解析应用名称、包名 / bundleName、`versionName`、`versionCode`。
- Android 自动处理 `adb install -t`：
  - 明确解析到 `testOnly=false` 时省略 `-t`；
  - 尚未解析、解析失败、不支持或 `testOnly=true` 时默认使用 `-t`，优先保证安装可用。
- 支持多设备选择、设备自定义命名、安装前设备重新校验和安装中止。
- 获取 Android / Harmony 崩溃日志。
- 获取 Harmony APP 日志：
  - 乾崑日志；
  - Demo 日志。
- 获取 Harmony UDID。
- Windows 单文件 exe 内置 APK/HAP 元数据解析工具，不要求用户额外安装 Android / Harmony SDK 才能读取支持格式的包信息。

## 快速开始

### 源码运行

需要 Python 3.11+，并确保 Tkinter 可用。

```bash
python src/main.py
```

### 基本流程

1. 连接手机。
2. 点击 **刷新设备**。
3. 点击 **选择目录**，选择包含 APK/HAP 的目录。
4. 工具自动扫描并选择最新 APK/HAP；后台补充应用名与版本信息。
5. 选择一个或多个设备。
6. 点击 **安装到所选设备**。

安装前会重新检测设备，避免把任务发送到已经断开的目标。安装开始后，本次任务使用点击安装时冻结的 APK/HAP 路径和 Android `-t` 决策，后续切换下拉框不会影响正在执行的任务。

## 安装包显示与元数据

安装包下拉框直接显示解析结果，不再额外重复一行摘要。典型格式：

```text
应用名称 · 1.3.08.107 (142)（app.apk）
```

### APK

使用同一次 `aapt2 dump badging` 读取：

- `application-label`
- package name
- `versionName`
- `versionCode`
- `testOnly`

### HAP

读取 Stage / FA 包中的明确声明字段，并在需要时使用 RestoolV2 解析资源型名称，可获得：

- 应用名称
- bundleName
- versionName
- versionCode

元数据解析只是增强能力，不是安装前置条件。工具缺失、格式不支持或解析失败时，仍可以按真实文件路径选择并安装。

Windows x64 单文件 exe 当前内置：

- AAPT2 `8.9.1-12782657`
- RestoolV2 `6.1.0.003`

显式覆盖仍可使用：

```text
AAPT2_EXECUTABLE
RESTOOL_EXECUTABLE
```

设置显式覆盖后只尝试该路径；如果路径不存在或不可执行，对应解析工具会被视为不可用，不会静默回退到内置工具、PATH 或 SDK 中的其他版本。元数据解析不可用不会阻止按真实文件路径选择和安装。

更完整的解析边界、读取限制和模块职责见 [`docs/anchor.md`](docs/anchor.md)。内置工具来源与 NOTICE 见 [`vendor/metadata-tools/README.md`](vendor/metadata-tools/README.md)。

## Android `-t` 策略

当前没有手工 `-t` 复选框，也没有按 APK 文件名保存 `-t` 配置。

规则只有一条：

```text
明确 testOnly=false  -> adb install <apk>
其余情况             -> adb install -t <apk>
```

这样包信息解析失败不会反过来阻塞安装，也不会因为解析尚未完成导致 test-only APK 安装失败。

## Harmony APP 日志

设备操作区提供 **获取APP日志** 菜单，只对单选 Harmony 设备启用。

### 乾崑日志

远端固定目录：

```text
/data/app/el2/100/base/com.yinwang.qiankunapp.hm/haps/phone/files/qklog/
```

### Demo 日志

远端固定目录：

```text
/data/app/el2/100/base/adsmobilesdk.all.huawei/haps/entry/files
```

两种日志都直接执行：

```text
hdc -t <device_id> file recv <remote_path> <temporary_local_path>
```

不再扫描 `/data/app`，也不执行全局 `find`。

拉取成功后自动压缩为 ZIP：

```text
qiankun_logs_<device>_<timestamp>.zip
demo_logs_<device>_<timestamp>.zip
```

输出目录：

- Windows：`D:\`
- 其他系统：`~/install_new_apk_hap_logs`

`recv` 返回非 0 时保留命令、返回码、stdout 和 stderr；命令成功但没有文件时会明确提示空结果，不生成空 ZIP。

## 其他日志与设备操作

### 崩溃日志

- Android：执行 `adb -s <device_id> shell dumpsys dropbox --print`，输出追加到 `D:\crash.log`（Windows）。
- Harmony：拉取 `/data/log/faultlog/faultlogger`，筛选最近 7 天文件名包含 `crash` 的日志并打包 ZIP。

### Harmony UDID

单选 Harmony 设备后执行：

```text
hdc -t <device_id> shell bm get --udid
```

成功后展示并复制到剪贴板。

## HDC 路径配置

设备检测、UDID、HAP 安装、Harmony 崩溃日志和 APP 日志共用同一套 HDC 路径解析。

优先级：

1. `HDC_EXECUTABLE`：完整 HDC 可执行文件路径。
2. `HDC_PATH`：HDC 文件或包含 HDC 的目录。
3. `DEVECO_SDK_HOME`：DevEco SDK 根目录。
4. `PATH`。
5. Windows 常见 DevEco SDK 安装目录。

前三项属于显式配置；配置错误时直接报告，不回退到其他 HDC。

PowerShell 示例：

```powershell
$env:HDC_EXECUTABLE = 'D:\DevEco Studio\sdk\default\openharmony\toolchains\hdc.exe'
python src/main.py
```

HDC 缺失或执行失败时，已检测到的 Android 设备仍会保留；不会把 Harmony 探测失败伪装成“没有设备”。

## UI 行为

- 设备列表默认至少显示 3 行，最多 8 行。
- 页面、设备列表和日志滚动条只在内容真实溢出时显示，不需要滚动时不占空间。
- 安装包只保留一行下拉显示，不重复展示包摘要。
- 操作按钮在窗口变窄时自动换行。
- 底部安装 / 中止入口固定可达。
- 日志支持横向和纵向滚动。
- `Tab` / `Shift+Tab` 切换控件时自动保证焦点可见。
- `Ctrl+Home` / `Ctrl+End` 跳到页面首尾，`Ctrl+PageUp` / `Ctrl+PageDown` 翻页。

相同设备或安装包状态重复刷新不会持续刷重复日志；错误、恢复、设备/文件变化、安装前校验及安装命令仍会记录。

## 配置文件

Windows：

```text
%APPDATA%/install_new_apk_hap/app_config.json
```

当前持久化内容主要包括：

- `device_names`：设备自定义名称；
- `last_scan_dir`：最近扫描目录。

旧版本留下的未知字段可以继续存在，但不会参与当前逻辑。

## 开发与测试

安装 pytest 后：

```bash
python -m pytest -q -p no:cacheprovider
```

测试包含真实 Tk 控件/事件、设备状态、HDC 路径、包元数据、安装参数快照以及日志固定路径检查；设备命令使用替身，不等同于真机安装验收。

PR 与 `main` push 会在 Windows / Python 3.11 上运行测试。

## Windows EXE 构建

GitHub Actions 工作流：**Build Windows EXE**。

PowerShell 中可以直接读取仓库当前版本，避免手写版本号漂移：

```powershell
$version = (Get-Content -Raw VERSION).Trim()
gh workflow run build-exe.yml --ref <branch> -f version=$version
```

本地构建：

```bash
python scripts/build_exe.py
python scripts/verify_exe.py dist/install_new_apk_hap.exe --output build/standalone-exe-validation.json
```

`build_exe.py` 会校验内置元数据工具和 NOTICE 后再执行 onefile 打包；`verify_exe.py` 会把最终 exe 放进无 SDK 配置的隔离环境中验证 APK/HAP 元数据读取、内置工具哈希和许可导出。

分支构建产物不是正式 Release。正式发布时 tag 必须与 `VERSION` 完全一致。

### EXE 诊断命令

不启动 GUI、不连接设备：

```powershell
.\install_new_apk_hap.exe --package-label-report labels.json package.apk package.hap
.\install_new_apk_hap.exe --tool-notices new-notices-directory
```

## 文档

- [`CHANGELOG.md`](CHANGELOG.md)：版本变化。
- [`docs/anchor.md`](docs/anchor.md)：当前架构、约束和模块职责。
- [`docs/ui_refactor_tracking.md`](docs/ui_refactor_tracking.md)：历史 UI 重构归档，不作为当前行为说明。
- [`vendor/metadata-tools/README.md`](vendor/metadata-tools/README.md)：内置工具版本、来源和许可。
