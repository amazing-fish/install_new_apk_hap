# install_new_apk_hap

从指定文件夹最新的 apk、hap 安装到已连接设备上（Android adb / Harmony hdc）。

## 功能
- 自动检测连接设备（adb/hdc）
- 扫描指定目录最新 apk/hap
- 支持 apk `-t` 安装规则记忆
- 设备自定义命名
- 可视化界面

## 使用方式
```bash
python3 src/main.py
```

## 配置说明
- 配置文件会在首次运行时自动生成到 `%APPDATA%/install_new_apk_hap/app_config.json`（Windows）。
- 该配置为本地运行状态，已被忽略提交；打包的 exe 运行后会在 AppData 目录生成/更新该配置。

## 版本与变更记录
- 版本号文件：`VERSION`
- 变更记录：`CHANGELOG.md`
- 技术路径稳定说明：`docs/anchor.md`

## Release 校验
- Release 会提供 `install_new_apk_hap.exe.sha256` 与签名文件 `install_new_apk_hap.exe.sha256.asc`。
- 校验方法参考：`docs/release_verification.md`
