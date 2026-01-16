# Release 下载校验

## 发布产物
- `install_new_apk_hap.exe`：主程序
- `install_new_apk_hap.exe.sha256`：SHA256 校验文件
- `install_new_apk_hap.exe.sha256.asc`：GPG 签名（对 `.sha256` 文件签名）

## SHA256 校验
下载 `install_new_apk_hap.exe` 与 `install_new_apk_hap.exe.sha256`，然后在下载目录执行：

```bash
sha256sum -c install_new_apk_hap.exe.sha256
```

Windows PowerShell：

```powershell
$hash = (Get-FileHash -Path .\install_new_apk_hap.exe -Algorithm SHA256).Hash.ToLower()
Get-Content .\install_new_apk_hap.exe.sha256
$hash
```

## GPG 签名验证
维护者会在 release 说明中提供公钥指纹或公钥文件。导入公钥后执行：

```bash
gpg --verify install_new_apk_hap.exe.sha256.asc install_new_apk_hap.exe.sha256
```
