# install_new_apk_hap

面向 **Android（ADB）** 与 **HarmonyOS（HDC）** 的桌面安装、包元数据解析与日志辅助工具。`v1.0.0` 起完成界面栈与性能重构（#96）：后端为零 Tk 依赖的 Python，界面为 **PyWebView（Windows Edge WebView2）+ React / TypeScript / Tailwind CSS**，安装语义、`-t` 规则、工具解析与内置离线解析工具链保持不变。

---

## 核心重构亮点

### 1. 并发与响应性能全面升级
- **ADB / HDC 并行设备探测**：使用 `ThreadPoolExecutor` 并发执行 `adb devices -l` 与 `hdc list targets`，并自动提取 Android 设备 `model` / `product` 型号信息；任一平台探测失败仍保留另一平台设备并明确提示，不误判为空列表。
- **多设备并行安装**：支持多台设备并发下发安装（可配置并发上限 2–8 路，也可一键切换顺序安装），每台设备独立展示实时状态徽章（等待中 / 安装中 / 成功耗时 / 失败原因 / 跳过），支持随时一键中止全部任务。
- **实时流式命令输出**：重构 `backend/infra/process.py`，基于无缓冲流式读取线程实时推送 `adb install` / `hdc install` 进度日志，同时保留无黑框、防管道死锁、超时、取消与输出上限保护。
- **优先并发 + 增量推送 + 磁盘持久化缓存的包元数据解析**：
  - 单趟 `os.scandir` 后台目录扫描，大目录/网络盘不卡顿 UI。
  - 按文件指纹（路径、大小、修改时间、inode）+ 工具指纹做原子化 JSON 磁盘缓存（`metadata_cache.json`），二次打开或重扫秒级呈现。
  - 未命中缓存时，优先并发解析当前选中的最新 APK / HAP，率先刷新界面，再以受控并发池增量推送其余候选包。

### 2. 现代桌面审美与人机交互重塑
- **浅色 / 深色 / 跟随系统**三态主题无缝切换，持久化保存。
- **全窗口原生拖放（Drag & Drop）**：直接把 `.apk`、`.hap` 文件或整个构建输出目录拖进窗口——拖入单文件自动切换目录并精准选中该文件，拖入目录立即扫描。
- **设备管理体验升级**：
  - 平台语义徽章（Android 翡翠绿 / Harmony 天空蓝）、在线状态脉动绿点、自动识别设备型号、新接入设备置顶与“新接入”标签高亮。
  - 支持平台筛选胶囊（全部 / Android / Harmony）、一键全选/取消全选、**双击行或点击铅笔图标原地内联重命名**、一键复制设备码。
- **双列安装包卡片 + 可搜索切换器**：
  - 清晰呈现应用名、版本徽章、可一键复制的包名 / bundleName、文件大小、相对修改时间及 Android 自动 `-t` 策略标识。
  - 候选包过多时支持内置搜索框按应用名 / 版本号 / 文件名即时过滤；目录栏保留最近使用目录历史与一键打开资源管理器。
- **非阻塞 Toast 轻提示 + 键盘快捷键**：
  - 获取 UDID 自动复制并弹出带“复制”按钮的 Toast；导出崩溃日志 / Harmony APP 日志后 Toast 内直接提供**“打开位置”**按钮。
  - 全局快捷键：`F5` 刷新设备与安装包、`Ctrl+Enter` 开始安装、`Esc` 中止当前任务。

### 3. 专业日志终端与设置诊断
- **分级着色终端**：自动区分 `CMD` / `OK` / `WARN` / `ERR` / `INFO`，支持按级别过滤、关键词实时搜索、自动滚动锁定开关、折叠收起、一键复制与清空。
- **设置与工具链诊断弹窗**：可视化检查 `ADB` / `HDC` / `AAPT2` / `RestoolV2` 解析路径与可用性，支持自定义日志导出目录（Windows 默认兼容 `D:\`，不存在时自动回退至用户目录 `~/install_new_apk_hap_logs`）。

---

## 目录结构

```text
installer/
├── backend/                  # Python 后端（零 Tk 依赖，高并发、高可测）
│   ├── main.py               # PyWebView 桌面入口、原生拖放绑定与 CLI 诊断入口
│   ├── bridge.py             # JS-Python RPC 桥接与线程安全事件推送
│   ├── controller.py         # 任务槽调度、目标解析、并行/串行多设备安装
│   ├── config_manager.py     # 原子化配置持久化与损坏备份恢复
│   ├── packages.py           # 单趟扫描、PackageSlot 与自动 -t 规则
│   ├── cli.py                # 无 GUI 诊断命令行
│   ├── infra/                # 外部进程流式执行器与统一工具链路径解析
│   ├── platforms/            # Android (ADB) / Harmony (HDC) 平台驱动与并发探测
│   └── metadata/             # 安全解析边界、APK/HAP 解析、持久化缓存与优先并发加载器
├── frontend/                 # React 19 + TypeScript + Vite + Tailwind CSS v4 前端
├── vendor/metadata-tools/    # 内置 Windows x64 AAPT2 & RestoolV2 及上游 NOTICE
├── scripts/                  # Windows 单文件 EXE 构建与隔离环境验证脚本
└── tests/                    # pytest 自动化测试套件
```

---

## 快速开始

### 环境要求
- **Python 3.11+**
- **Node.js 20+**（仅首次构建前端或开发前端时需要）
- Windows 10 / 11（内置 Edge WebView2 运行时）

### 安装依赖并构建前端

```powershell
# 1. 安装 Python 依赖
python -m pip install -r requirements.txt

# 2. 构建现代 Web 前端产物到 backend/web_dist/
cd frontend
npm install
npm run build
cd ..
```

### 启动桌面应用

```powershell
python backend/main.py
```

#### 前端热更新开发模式

```powershell
# 终端 1：启动 Vite 开发服务
cd frontend
npm run dev

# 终端 2：以开发模式启动 PyWebView 桌面容器
python backend/main.py --dev-url http://localhost:5173 --debug
```

---

## 环境变量与工具链配置

与原项目保持完全一致的显式覆盖优先策略：

| 工具 | 显式覆盖环境变量 | 自动探测顺序 |
| --- | --- | --- |
| **ADB** | `ADB_EXECUTABLE` | `PATH` → `ANDROID_SDK_ROOT` / `ANDROID_HOME` → `%LOCALAPPDATA%\Android\Sdk\platform-tools` |
| **HDC** | `HDC_EXECUTABLE` / `HDC_PATH` / `DEVECO_SDK_HOME` | `PATH` → 常见 Huawei / DevEco SDK 安装目录 |
| **AAPT2** | `AAPT2_EXECUTABLE` | 打包内置工具 → `PATH` / Android SDK `build-tools` → 仓库内置 `vendor/` |
| **RestoolV2** | `RESTOOL_EXECUTABLE` | 打包内置工具 → `PATH` / HDC 同目录 → 仓库内置 `vendor/` |

---

## 测试与打包

### 运行后端单元测试

```powershell
python -m pip install -r requirements.txt pytest
python -m pytest -v -p no:cacheprovider
```

### 诊断 CLI（无 GUI）

```powershell
python backend/main.py --env-check env.json
python backend/main.py --package-label-report labels.json path\to\app.apk path\to\app.hap
```

### 构建 Windows x64 单文件 EXE

需安装 `pyinstaller`：

```powershell
python -m pip install pyinstaller
python scripts/build_exe.py
python scripts/verify_exe.py dist/install_new_apk_hap.exe --output build/verify.json
```

---

## 文档

- [`CHANGELOG.md`](CHANGELOG.md)：版本变化。
- [`docs/anchor.md`](docs/anchor.md)：当前架构、约束和模块职责。
- [`docs/ui_refactor_tracking.md`](docs/ui_refactor_tracking.md)：历史 UI 重构归档。
- [`vendor/metadata-tools/README.md`](vendor/metadata-tools/README.md)：内置工具版本、来源和许可。

## 许可证

遵循仓库根目录 [`LICENSE`](LICENSE)（MIT License）。内置 AAPT2 / RestoolV2 工具的来源与上游许可声明详见 [`vendor/metadata-tools/README.md`](vendor/metadata-tools/README.md)。
