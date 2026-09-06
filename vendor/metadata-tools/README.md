# Embedded package-name tools

The Windows x64 onefile application includes the two standalone metadata tools in
`windows-x64/`. End users do not download SDKs or configure environment variables.
The full SDK, device tools, credentials, and user packages are not included.

| Component | Version | Provenance |
| --- | --- | --- |
| AAPT2 | 8.9.1-12782657 | `aapt2.exe` and `NOTICE` from the [official Google Maven Windows artifact](https://dl.google.com/dl/android/maven2/com/android/tools/build/aapt2/8.9.1-12782657/aapt2-8.9.1-12782657-windows.jar) |
| restool | RestoolV2 6.1.0.003 | `command-line-tools/sdk/default/openharmony/toolchains/restool.exe` and its directory's complete `NOTICE.txt`, from `commandline-tools-windows-x64-6.1.1.300.zip` obtained through the [official HarmonyOS command-line tools page](https://developer.huawei.com/consumer/cn/download/command-line-tools-for-hmos); toolchain package 6.1.1.125 |

The restool directory NOTICE explicitly lists `/toolchains/restool.exe` in an
Apache License 2.0 section. Its [OpenHarmony source repository](https://github.com/openharmony/developtools_global_resource_tool)
also declares Apache-2.0. Complete upstream notices, including third-party notices,
are retained byte-for-byte; the executable files have not been modified. The broader
SDK installation is not redistributed. Notice filenames are renamed only to keep
the two original files distinct.

`windows-x64/manifest.json` records the original locations, versions and SHA-256 of
each executable and notice. `scripts/build_exe.py` requires exactly these files and
rejects missing or changed bytes before packaging. No network download or user SDK
is consulted during the build. Keeping these small pinned inputs in Git also makes
the build independent of the authenticated SDK download page.

Both tools are x64 PE executables. Their import tables reference Windows system
libraries/UCRT, with no external SDK DLL dependencies. PyInstaller collects binary
dependencies and uses `--noupx`; the final EXE verification compares the embedded
tool hashes to the manifest and runs both tools with only System32 on PATH.

The notices and manifest are embedded in `package_tools/` inside the onefile
archive. Recipients can export readable copies without running the GUI:

```powershell
.\install_new_apk_hap.exe --tool-notices new-notices-directory
```

To update a tool, obtain it from the documented official source, retain its matching
notices, update manifest hashes/version/provenance, and pass the standalone EXE
verification. Do not copy binaries from PATH or relax a checksum after a mismatch.
