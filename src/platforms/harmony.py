"""Harmony (NEXT) devices through hdc."""
from datetime import datetime, timedelta
from pathlib import Path
import subprocess
import tempfile
import threading
import zipfile
from typing import List, Optional

from infra.tools import HdcError, resolve_hdc_executable
from platforms.base import (
    AppLogTarget, CollectResult, DeviceInfo, PlatformDriver, parse_device_lines, run_probe,
    run_transfer, safe_filename_part,
)


# Fixed app sandboxes are received directly; there is no `find` over /data/app.
APP_LOG_TARGETS = {
    "qiankun": AppLogTarget(
        display_name="乾崑日志",
        remote_path="/data/app/el2/100/base/com.yinwang.qiankunapp.hm/haps/phone/files/qklog/",
        archive_prefix="qiankun_logs",
    ),
    "demo": AppLogTarget(
        display_name="Demo日志",
        remote_path="/data/app/el2/100/base/adsmobilesdk.all.huawei/haps/entry/files",
        archive_prefix="demo_logs",
    ),
}
CRASH_LOG_REMOTE_DIR = "/data/log/faultlog/faultlogger"
CRASH_LOG_DAYS = 7


def _hdc_probe(command: List[str], cancel: Optional[threading.Event] = None) -> str:
    return run_probe(command, HdcError, "HDC", fail_marker="[Fail]", cancel=cancel)


def _zip(files: List[Path], base: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(base).as_posix())


class HarmonyDriver(PlatformDriver):
    key = "harmony"
    label = "Harmony"
    package_kind = "HAP"
    supports_udid = True
    app_log_targets = APP_LOG_TARGETS
    crash_log_description = f"Harmony 最近 {CRASH_LOG_DAYS} 天崩溃日志"
    tool_error = HdcError

    def detect(self) -> List[DeviceInfo]:
        output = _hdc_probe([resolve_hdc_executable(), "list", "targets"])
        return [DeviceInfo(device_id=line, platform=self.key, status="device") for line in parse_device_lines(output)]

    def install_command(self, device_id: str, package: Path, *, allow_test: bool = False,
                        executable: Optional[str] = None) -> List[str]:
        # allow_test is an adb concept; HAP installs have no equivalent flag.
        return [executable or resolve_hdc_executable(), "-t", device_id, "install", str(package)]

    def udid(self, device_id: str, cancel: Optional[threading.Event] = None) -> Optional[str]:
        output = _hdc_probe([resolve_hdc_executable(), "-t", device_id, "shell", "bm", "get", "--udid"], cancel)
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        return lines[-1] if lines else None

    def collect_crash_log(self, device_id: str, output_dir: Path,
                          cancel: Optional[threading.Event] = None) -> CollectResult:
        """Receive faultlogger, then archive files named *crash* from the last 7 days."""
        hdc = resolve_hdc_executable()
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_device_id = safe_filename_part(device_id)
        with tempfile.TemporaryDirectory(prefix=f"harmony_crash_{safe_device_id}_", dir=output_dir) as temp_dir:
            receive_dir = Path(temp_dir)
            command = [hdc, "-t", device_id, "file", "recv", CRASH_LOG_REMOTE_DIR, str(receive_dir)]
            fetched = run_transfer(command, cancel)
            if fetched.returncode != 0:
                return CollectResult(command=command, process=fetched)
            local_dir = receive_dir / "faultlogger"
            if not local_dir.exists():
                return CollectResult(command, subprocess.CompletedProcess(command, 1, "", "未找到拉取后的 faultlogger 目录"))
            cutoff = datetime.now() - timedelta(days=CRASH_LOG_DAYS)
            files = [
                path for path in local_dir.rglob("*")
                if path.is_file() and "crash" in path.name.lower()
                and datetime.fromtimestamp(path.stat().st_mtime) >= cutoff
            ]
            if not files:
                return CollectResult(command, subprocess.CompletedProcess(
                    command, 0, "", f"最近 {CRASH_LOG_DAYS} 天未匹配到 crash 文件"))
            zip_path = output_dir / f"harmony_crash_{safe_device_id}_{timestamp}.zip"
            _zip(files, local_dir, zip_path)
        return CollectResult(command=command, process=fetched, zip_path=zip_path, file_count=len(files))

    def collect_app_log(self, device_id: str, output_dir: Path, target_key: str,
                        cancel: Optional[threading.Event] = None) -> CollectResult:
        """Receive one known app log directory directly and archive it locally."""
        try:
            target = APP_LOG_TARGETS[target_key]
        except KeyError as error:
            raise ValueError(f"unknown Harmony app log target: {target_key}") from error
        hdc = resolve_hdc_executable()
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_device_id = safe_filename_part(device_id)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        with tempfile.TemporaryDirectory(prefix=f"{target.archive_prefix}_{safe_device_id}_", dir=output_dir) as temp_dir:
            temp_base = Path(temp_dir)
            command = [hdc, "-t", device_id, "file", "recv", target.remote_path, str(temp_base / target_key)]
            received = run_transfer(command, cancel)
            if received.returncode != 0:
                return CollectResult(command=command, process=received)
            files = sorted(path for path in temp_base.rglob("*") if path.is_file())
            if not files:
                return CollectResult(command, subprocess.CompletedProcess(
                    command, 0, received.stdout, received.stderr or f"{target.display_name}拉取成功但未发现文件"))
            zip_path = output_dir / f"{target.archive_prefix}_{safe_device_id}_{timestamp}.zip"
            _zip(files, temp_base, zip_path)
        return CollectResult(command=command, process=received, zip_path=zip_path, file_count=len(files))


HARMONY = HarmonyDriver()
