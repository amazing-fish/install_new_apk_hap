# SDK-generated package label fixtures

These are unsigned, metadata-only ZIP packages generated for this repository from the adjacent `source/` files. They contain no executable app code and are **not installable application samples**. Expected default label: `Demo 默认名称`.

- `compiled.apk`: AAPT2 `8.9.1-12782657` (Windows), linked against Android 35 platform revision 2. `AndroidManifest.xml` is compiled binary XML and `resources.arsc` contains the referenced string.
- `compiled.hap`: Restool `5.1.0.008`, compiled `module.json` (including `labelId`) and `resources.index`.
- `compiled-v2.hap`: RestoolV2 `6.1.0.003`, generated from `source/hap-v2/module.json` and the same `source/hap/resources`; the module declares API 24. Its resource header starts with `RestoolV2`; old restool 5.1 rejects it. The final EXE verifier reads both HAP versions.
- `aapt2-badging.txt` / `restool-dump.json`: stdout captured from the corresponding real SDK tool, not invented output. Unit tests replay it so CI needs no SDK. The delivery report separately records live SDK validation.

Tool sources: [Google AAPT2 artifact](https://dl.google.com/dl/android/maven2/com/android/tools/build/aapt2/8.9.1-12782657/aapt2-8.9.1-12782657-windows.jar), [Google Android 35 platform](https://dl.google.com/android/repository/platform-35_r02.zip), installed DevEco SDK toolchains restool. Starting with v0.8.2 the two name-reading tools and their notices are pinned under `vendor/metadata-tools`; see its README for provenance.

Reproduce from this directory in a scratch output directory (replace SDK executable paths and android.jar):

```text
aapt2 compile --dir source/apk/res -o scratch/apk-res.zip
aapt2 link -I android.jar --manifest source/apk/AndroidManifest.xml -o scratch/compiled.apk scratch/apk-res.zip
aapt2 dump badging scratch/compiled.apk
restool -i source/hap -j source/hap/module.json -p com.example.labels -o scratch/hap-out -r scratch/ResourceTable.txt
```

Create `scratch/hap-out` before running restool, then ZIP its generated `module.json` and `resources.index` at archive root as `scratch/compiled.hap`. Run `restool dump scratch/compiled.hap`. Output-directory creation and ZIP packaging do not require executing any package content. Exact ZIP hashes may vary with SDK timestamps.

For v2, use the pinned restool, select `source/hap-v2/module.json` with `-j`, and keep `source/hap` as `-i`. On Windows pass absolute native paths (for example PowerShell `Resolve-Path` values); this restool's Stage filename detection does not recognize forward-slash paths. Store the two resulting files in `compiled-v2.hap` with ZIP timestamps fixed to 1980-01-01. These fixtures contain no user package content.
