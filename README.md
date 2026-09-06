# install_new_apk_hap

从指定文件夹最新的 apk、hap 安装到已连接设备上（Android adb / Harmony hdc）。

## 功能
- 自动检测连接设备（adb/hdc）
- 扫描指定目录最新 apk/hap
- 支持 apk `-t` 安装规则记忆
- 设备自定义命名
- 设备统计、已选设备和当前 APK/HAP 摘要随刷新、选择和命名同步更新
- Harmony 最近 7 天崩溃日志 zip 打包
- NEXTdemo 日志（`haps/entry/files/log-ads`）zip 打包
- 可视化界面
- 紧凑原生工作区与固定安装/中止入口，支持窄窗口滚动、长内容横向查看和键盘操作

## 使用方式
```bash
python3 src/main.py
```

界面初始宽度按四列基准宽度加原生滚动条与边距计算，当前约 590x740，最小 480x560。设备区至少显示 4 行，超过 8 台后滚动查看。设备、安装包和日志采用少边框的紧凑布局；按钮按各自宽度依次排列，空间不足时换行。底部显示已选设备和安装状态，安装/中止按钮始终可见。
长设备名称/设备码可通过表格横向滚动查看；下拉框保留全部安装包候选。当底栏或包下拉框无法显示完整名称时，相应区域自动展开完整摘要，避免短名称重复占位。日志可横纵滚动。
Tab / Shift+Tab 切换控件时页面会自动滚动到焦点；Ctrl+Home/End 跳至页首/页尾，Ctrl+PageUp/PageDown 翻页。鼠标位于设备表、包下拉或日志上时，滚轮优先作用于该控件。
重复刷新相同设备或安装包结果不会追加日志；首次刷新、设备或文件变化、错误恢复仍记录。安装前校验、安装命令与失败日志完整保留，清空日志后下一次刷新会重新记录结果。

UDID 与 NEXTdemo 日志仅对单选 Harmony 设备启用；崩溃日志支持单选 Android/Harmony。耗时操作显示进行中状态，安装时底部按钮切为“中止安装”。“安装失败”“安装异常”“安装未完成”和“已中止”分别表示命令失败、运行异常、目标被跳过和用户主动中止。

## 安装包应用名称

扫描后先按修改时间显示全部文件，后台补充“应用名称（文件名）”。只更新现有下拉框和必要时展开的摘要，不增加说明行。重名应用保留每个文件，安装路径和 `-t` 记忆仍使用真实路径、文件名。

- **v0.8.2 起的 Windows x64 exe 自带名称解析工具**。下载单个 exe 后直接运行即可读取支持格式的 APK/HAP 名称，不需要另装 SDK、旁置 tools 目录、启动脚本或环境变量，也不在运行时下载工具。内置版本为 AAPT2 `8.9.1-12782657`、RestoolV2 `6.1.0.003`。
- APK：通过 `aapt2 dump badging` 读取默认 `application-label`，支持编译资源引用。HAP Stage 读取 `module.json` 的 `app.label`；FA 读取 `config.json` 中 `module.mainAbility` 精确对应 Ability 的 label；`$string:xxx` 通过 restool 读取默认资源值，并核对声明的 labelId。
- 高级覆盖：`AAPT2_EXECUTABLE` / `RESTOOL_EXECUTABLE` 可显式指定完整路径，优先于内置工具；显式路径无效时不换用其他版本。未覆盖时，exe 只使用自身解包目录中的工具，不借用 PATH 或旁置同名文件。内置文件缺失会明确提示，不能用开发机 SDK 掩盖打包遗漏。
- 源码运行仍支持外部 SDK：AAPT2 依次查找 PATH、`ANDROID_SDK_ROOT` / `ANDROID_HOME` 的最高稳定 build-tools；restool 依次查找 PATH、已解析 HDC 的同目录工具。缺少工具时仍可按文件名选择和安装。
- 本轮采用包的默认名称，不模拟设备语言。只有本地化值、别名/跨包引用、未知 JSON5/pack.info 格式均不猜测；下拉框区分资源未解析、未声明名称、格式不支持、读取失败与读取受限。模块 `name`、bundleName 和文件名不作为解析成功。名称中的控制字符、方向/格式控制符和段落分隔符会按读取失败处理，避免干扰真实文件名显示。
- SDK 返回失败时显示 `[aapt2 解析失败]` / `[restool 解析失败]`，下次刷新重新尝试。此状态不能直接证明安装包损坏。内置 restool 已支持此前失败的 RestoolV2 资源；若显式覆盖成旧版工具，仍可能不兼容。更新环境变量后应重启应用。

元数据读取由单个后台线程执行；新扫描替换等待中的旧请求，过期目录结果丢弃。缓存最多 256 项，按文件和解析工具的路径、大小、纳秒时间及文件身份失效；读取失败下次刷新重试。名称更新不改当前选择，不追加逐包日志。单工具调用最长 5 秒、输出最多 4 MiB；ZIP 目录/JSON/manifest 最多 1 MiB、资源表最多 32 MiB，不将包内文件解压执行。
ZIP 目录按实际字节数限制，不再额外限制为 10,000 个文件；目录大小和条目最小长度仍约束内存分配，ZIP64 与不一致的目录继续拒绝。

格式依据：[Android AAPT2](https://developer.android.com/tools/aapt2)、[HarmonyOS restool](https://developer.huawei.com/consumer/cn/doc/doccenter-capabilities/restool)。SDK 生成的资源样例及复现方法见 `tests/fixtures/package_labels/README.md`。这些元数据样例不代表真机安装验收。

## 配置说明
- 配置文件会在首次运行时自动生成到 `%APPDATA%/install_new_apk_hap/app_config.json`（Windows）。
- 该配置为本地运行状态，已被忽略提交；打包的 exe 运行后会在 AppData 目录生成/更新该配置。

### Harmony HDC 路径

设备检测、UDID、HAP 安装和两种 Harmony 日志采集使用同一解析规则，按以下顺序选择：

1. `HDC_EXECUTABLE`：完整的 HDC 可执行文件路径。
2. `HDC_PATH`：可执行文件路径或包含 `hdc.exe`（Linux/macOS 为 `hdc`）的目录。
3. `DEVECO_SDK_HOME`：本工具支持的 SDK 根目录配置，依次检查其 `default/openharmony/toolchains`、`openharmony/toolchains`、`toolchains`。
4. `PATH` 中的 HDC。
5. Windows 常见目录：`%LOCALAPPDATA%` / `%APPDATA%` 下的 `Huawei/Sdk/default/openharmony/toolchains`，以及 `%ProgramFiles%` / `%ProgramFiles(x86)%` 下的 `Huawei/DevEco Studio/sdk/default/openharmony/toolchains`。

前三项属于显式选择，配置无效时直接报告原因；不会跳到其他工具。自定义 DevEco 安装位置建议设置 `HDC_EXECUTABLE` 或 `DEVECO_SDK_HOME`。HDC 与相关动态库应保留在 SDK toolchains 目录中，参考 [OpenHarmony HDC 环境准备](https://github.com/openharmony/docs/blob/master/zh-cn/application-dev/dfx/hdc.md#环境准备)。

PowerShell 中可为本次启动指定路径（支持空格）：

```powershell
$env:HDC_EXECUTABLE = 'D:\DevEco Studio\sdk\default\openharmony\toolchains\hdc.exe'
python src/main.py
```

修改系统环境变量后需重新启动应用。HDC 缺失或执行失败会显示诊断并保留可用 Android 设备，不自动改选其他设备；成功但无设备才视为空列表。安装前若 HDC 探测失败，仅允许已明确选择且全部为 Android 的请求继续；未选择设备或选择涉及 Harmony 时停止该次安装，保留校验耗时与错误诊断。路径在每项操作开始时解析，安装命令日志与实际执行、同次日志采集的查找与拉取共享已解析路径。

## 版本与变更记录
- 版本号文件：`VERSION`
- 变更记录：`CHANGELOG.md`
- 技术路径稳定说明：`docs/anchor.md`
- UI 阶段计划与进展：`docs/ui_refactor_tracking.md`

## 开发验证
安装 `pytest` 后运行 `python -m pytest -q -p no:cacheprovider`。
测试包含真实 Tk 控件和事件检查，需要带 Tkinter 和桌面显示的 Python 环境；设备命令使用替身，配置写入测试临时目录。
PR 和主线提交会运行 Windows 测试检查；exe 打包仍通过原有手动/tag 流程触发。

## v0.8.2 构建与发布
在 GitHub Actions 的 **Build Windows EXE** 中选择对应分支运行，或使用 `gh workflow run build-exe.yml --ref <分支名> -f version=v0.8.2`。
成功后下载 `install_new_apk_hap-windows-v0.8.2` artifact 中的单个 `install_new_apk_hap.exe`（保留 30 天），以运行页面的提交 SHA 确认代码版本。分支构建不等同于正式 Release；正式发布须另行创建与 `VERSION` 一致的标签。

本地在 Windows 64 位 Python 中安装 PyInstaller 后，使用 `python scripts/build_exe.py` 构建。脚本先核对 `vendor/metadata-tools/windows-x64/manifest.json` 中的工具与 NOTICE 哈希，再将它们打入 onefile；不得改用省略资源参数的裸 PyInstaller 命令。
`python scripts/verify_exe.py dist/install_new_apk_hap.exe --output build/standalone-exe-validation.json` 将 exe 单独复制到临时目录、移除 SDK 配置并仅保留系统 PATH，然后实际解析 APK、HAP v1/v2 编译样例，核验工具哈希与许可导出。Actions 通过这一步后才上传 exe 和发布资产；验收 JSON 作为独立 artifact 保存。

内置组件的来源、版本及完整 NOTICE 见 [工具说明](vendor/metadata-tools/README.md)。exe 提供以下可选诊断命令，不启动 GUI、不调用设备：

```powershell
.\install_new_apk_hap.exe --package-label-report labels.json package.apk package.hap
.\install_new_apk_hap.exe --tool-notices new-notices-directory
```

名称报告包含实际工具路径、内置工具哈希和每个包的读取结果；全部解析成功退出码为 0，否则为 1。许可导出要求使用尚不存在的目标目录。
