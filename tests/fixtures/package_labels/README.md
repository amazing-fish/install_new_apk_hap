# SDK-generated package label fixtures

These are unsigned, metadata-only ZIP packages generated for this repository from the adjacent `source/` files. They contain no executable app code and are **not installable application samples**. Expected default label: `Demo 默认名称`.

- `compiled.apk`: AAPT2 `8.9.1-12782657` (Windows), linked against Android 35 platform revision 2. `AndroidManifest.xml` is compiled binary XML and `resources.arsc` contains the referenced string.
- `compiled.hap`: Restool `5.1.0.008`, compiled `module.json` (including `labelId`) and `resources.index`.
- `aapt2-badging.txt` / `restool-dump.json`: stdout captured from the corresponding real SDK tool, not invented output. Unit tests replay it so CI needs no SDK. The delivery report separately records live SDK validation.

Tool sources: [Google AAPT2 artifact](https://dl.google.com/dl/android/maven2/com/android/tools/build/aapt2/8.9.1-12782657/aapt2-8.9.1-12782657-windows.jar), [Google Android 35 platform](https://dl.google.com/android/repository/platform-35_r02.zip), installed DevEco SDK toolchains restool. No SDK binaries are committed or bundled in the application.

Reproduce from this directory in a scratch output directory (replace SDK executable paths and android.jar):

```text
aapt2 compile --dir source/apk/res -o scratch/apk-res.zip
aapt2 link -I android.jar --manifest source/apk/AndroidManifest.xml -o scratch/compiled.apk scratch/apk-res.zip
aapt2 dump badging scratch/compiled.apk
restool -i source/hap -j source/hap/module.json -p com.example.labels -o scratch/hap-out -r scratch/ResourceTable.txt
```

Create `scratch/hap-out` before running restool, then ZIP its generated `module.json` and `resources.index` at archive root as `scratch/compiled.hap`. Run `restool dump scratch/compiled.hap`. Output-directory creation and ZIP packaging do not require executing any package content. Exact ZIP hashes may vary with SDK timestamps.
