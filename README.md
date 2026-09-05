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

## 配置说明
- 配置文件会在首次运行时自动生成到 `%APPDATA%/install_new_apk_hap/app_config.json`（Windows）。
- 该配置为本地运行状态，已被忽略提交；打包的 exe 运行后会在 AppData 目录生成/更新该配置。

## 版本与变更记录
- 版本号文件：`VERSION`
- 变更记录：`CHANGELOG.md`
- 技术路径稳定说明：`docs/anchor.md`
- UI 阶段计划与进展：`docs/ui_refactor_tracking.md`

## 开发验证
安装 `pytest` 后运行 `python -m pytest -q -p no:cacheprovider`。
测试包含真实 Tk 控件和事件检查，需要带 Tkinter 和桌面显示的 Python 环境；设备命令使用替身，配置写入测试临时目录。
PR 和主线提交会运行 Windows 测试检查；exe 打包仍通过原有手动/tag 流程触发。

## v0.6.0 构建与发布
本轮 `VERSION` 已更新为 `v0.6.0`；PR 分支的 exe 是待发布构建，不能当作已发布 Release。
在 GitHub Actions 的 **Build Windows EXE** 中选择对应分支运行，或使用 `gh workflow run build-exe.yml --ref <分支名> -f version=v0.6.0`。
成功后下载 `install_new_apk_hap-windows-v0.6.0` artifact 中的 `install_new_apk_hap.exe`（保留 30 天），以运行页面的提交 SHA 确认代码版本。
正式发布需在合入后单独创建与 `VERSION` 一致的 `v0.6.0` 标签；标签流程通过测试和打包后才上传 Release asset。
