"""PyWebView JS-Python bridge and full application state coordinator (zero Tk dependency)."""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from config_manager import ConfigManager, default_log_output_dir
from controller import (
    InstallOutcome,
    Task,
    TaskRunner,
    build_install_plan,
    format_command_for_log,
    resolve_target,
    run_install_plan,
)
from infra.tools import diagnose_tools
from metadata.loader import PackageLabelLoader, file_fingerprint
from packages import PACKAGE_KINDS, SUFFIX_TO_KIND, PackageSlot, apk_allow_test, find_packages
from platforms import DRIVERS, DeviceDetectionResult, DeviceInfo, detect_devices, driver_for
from platforms.base import CollectResult, PlatformDriver


MAX_LOG_ENTRIES = 2000


def _read_version() -> str:
    candidates = [
        Path(__file__).resolve().parents[1] / "VERSION",
        Path(getattr(sys, "_MEIPASS", "")) / "VERSION" if getattr(sys, "frozen", False) else None,
    ]
    for path in candidates:
        if path and path.is_file():
            return path.read_text(encoding="utf-8").strip().lstrip("vV")
    return "0.0.0"


def reorder_devices_for_refresh(
    devices: List[DeviceInfo],
    previous_device_ids: Set[str],
) -> Tuple[List[DeviceInfo], Set[str]]:
    new_device_ids = {device.device_id for device in devices} - previous_device_ids
    new_devices = [device for device in devices if device.device_id in new_device_ids]
    existing_devices = [device for device in devices if device.device_id not in new_device_ids]
    return new_devices + existing_devices, new_device_ids


def default_config_path() -> Path:
    appdata = os.getenv("APPDATA")
    base_dir = Path(appdata) if appdata else (Path.home() / ".config")
    return base_dir / "install_new_apk_hap" / "app_config.json"


def _folder_dialog_type(webview_module):
    file_dialog = getattr(webview_module, "FileDialog", None)
    if file_dialog is not None:
        return file_dialog.FOLDER
    return webview_module.FOLDER_DIALOG


class InstallerBridge:
    """Exposes RPC methods to the frontend and pushes live events back."""

    def __init__(
        self,
        *,
        config_path: Optional[Path] = None,
        emit: Optional[Callable[[str, Any], None]] = None,
        auto_start: bool = True,
    ) -> None:
        self._state_lock = threading.RLock()
        self._emit_fn = emit
        self._window = None  # Attached by main.py once PyWebView window is created
        self._version = _read_version()

        cfg_path = config_path or default_config_path()
        self.config_manager = ConfigManager(cfg_path)
        cache_path = cfg_path.parent / "metadata_cache.json"

        self.devices: List[DeviceInfo] = []
        self.new_device_ids: Set[str] = set()
        self.selected_device_ids: List[str] = []
        self.device_errors: Dict[str, str] = {}
        self.last_probe_failed = False
        self.refreshing = False
        self.scanning = False
        self.folder: str = ""
        self.packages: Dict[str, PackageSlot] = {kind: PackageSlot() for kind in PACKAGE_KINDS}
        self.install_status = "就绪"
        self.device_progress: Dict[str, Dict[str, Any]] = {}

        self._logs: List[Dict[str, Any]] = []
        self._log_seq = 0
        self._event_revs: Dict[str, int] = {"devices": 0, "packages": 0, "task": 0, "settings": 0}
        self._closed = False
        self._device_ids_before_last_refresh: Optional[Set[str]] = None
        self._latest_refresh_request_id = 0
        self._latest_scan_request_id = 0
        self._last_device_refresh_snapshot = None
        self._last_package_scan_snapshot = None
        self._package_label_request = 0

        self.tasks = TaskRunner(post=self._run_inline, on_change=self._on_task_change)
        self._package_label_loader = PackageLabelLoader(post=self._run_inline, cache_path=cache_path)

        if auto_start:
            self.refresh_devices()
            last_dir = str(self.config_manager.data.get("last_scan_dir", "")).strip()
            if last_dir:
                self._append_log(f"加载上次扫描目录: {last_dir}", "info")
                self.scan_folder(last_dir, remember=False, silent_empty=True)

    # ---- Window & event plumbing -------------------------------------------------

    def attach_window(self, window) -> None:
        self._window = window

    def _run_inline(self, callback: Callable[[], None]) -> None:
        callback()

    def _emit(self, event_type: str, payload: Any) -> None:
        if self._emit_fn is not None:
            try:
                self._emit_fn(event_type, payload)
            except Exception:
                pass
            return
        win = self._window
        if win is None:
            return
        try:
            encoded = json.dumps({"type": event_type, "payload": payload}, ensure_ascii=False)
            win.evaluate_js(f"window.__INSTALLER_EVENT__ && window.__INSTALLER_EVENT__({encoded});")
        except Exception:
            pass

    def close(self, timeout: float = 10.0) -> None:
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
            self._window = None
        if self.tasks.busy:
            self.tasks.cancel()
            self.tasks.wait_idle(timeout=timeout)
        self._package_label_loader.close()

    # ---- Logging & Toast helpers -------------------------------------------------

    def _append_log(
        self,
        message: str,
        level: str = "info",
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._state_lock:
            self._log_seq += 1
            entry = {
                "id": self._log_seq,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "level": level,
                "message": message,
                "deviceId": device_id,
            }
            self._logs.append(entry)
            if len(self._logs) > MAX_LOG_ENTRIES:
                self._logs = self._logs[-MAX_LOG_ENTRIES:]
        self._emit("log", entry)
        return entry

    def _toast(
        self,
        title: str,
        message: str = "",
        *,
        variant: str = "info",
        action_label: Optional[str] = None,
        action_path: Optional[str] = None,
        copy_text: Optional[str] = None,
    ) -> None:
        self._emit(
            "toast",
            {
                "id": f"t-{time.time_ns()}",
                "title": title,
                "message": message,
                "variant": variant,
                "actionLabel": action_label,
                "actionPath": action_path,
                "copyText": copy_text,
            },
        )

    # ---- Serialization -----------------------------------------------------------

    def _device_name_mapping(self) -> Dict[str, str]:
        return self.config_manager.data.get("device_names", {})

    def _device_label(self, device_id: str) -> str:
        name = self._device_name_mapping().get(device_id, "").strip()
        return name or device_id

    def _device_labels_for_log(self, device_ids: Iterable[str]) -> str:
        return "，".join(self._device_label(did) for did in device_ids)

    def _serialize_devices(self) -> List[Dict[str, Any]]:
        names = self._device_name_mapping()
        rows = []
        for device in self.devices:
            driver = driver_for(device.platform)
            rows.append(
                {
                    "deviceId": device.device_id,
                    "name": names.get(device.device_id, "").strip(),
                    "platform": device.platform,
                    "platformLabel": driver.label if driver else device.platform,
                    "status": device.status,
                    "model": device.model,
                    "product": device.product,
                    "isNew": device.device_id in self.new_device_ids,
                    "supportsUdid": bool(driver and driver.supports_udid),
                    "hasAppLogs": bool(driver and driver.app_log_targets),
                }
            )
        return rows

    def _serialize_packages(self) -> Dict[str, Any]:
        return {kind: slot.to_payload(kind) for kind, slot in self.packages.items()}

    def _serialize_task(self) -> Optional[Dict[str, Any]]:
        task = self.tasks.current
        if task is None:
            return None
        return {
            "action": task.action,
            "name": task.name,
            "label": task.label,
            "cancelled": task.cancelled,
        }

    def _serialize_app_log_targets(self) -> List[Dict[str, str]]:
        items = []
        for driver in DRIVERS.values():
            for key, target in driver.app_log_targets.items():
                items.append(
                    {
                        "key": key,
                        "displayName": target.display_name,
                        "remotePath": target.remote_path,
                        "platform": driver.key,
                    }
                )
        return items

    def _next_rev_locked(self, channel: str) -> int:
        rev = self._event_revs.get(channel, 0) + 1
        self._event_revs[channel] = rev
        return rev

    def _build_devices_payload_locked(self) -> Dict[str, Any]:
        return {
            "rev": self._next_rev_locked("devices"),
            "devices": self._serialize_devices(),
            "selectedDeviceIds": list(self.selected_device_ids),
            "deviceErrors": dict(self.device_errors),
            "lastProbeFailed": self.last_probe_failed,
            "refreshing": self.refreshing,
        }

    def _build_packages_payload_locked(self) -> Dict[str, Any]:
        return {
            "rev": self._next_rev_locked("packages"),
            "folder": self.folder,
            "recentDirs": list(self.config_manager.data.get("recent_dirs", [])),
            "scanning": self.scanning,
            "packages": self._serialize_packages(),
        }

    def _build_task_payload_locked(self) -> Dict[str, Any]:
        return {
            "rev": self._next_rev_locked("task"),
            "task": self._serialize_task(),
            "installStatus": self.install_status,
            "deviceProgress": dict(self.device_progress),
        }

    def _emit_devices_state(self) -> None:
        with self._state_lock:
            payload = self._build_devices_payload_locked()
        self._emit("devices", payload)

    def _emit_packages_state(self) -> None:
        with self._state_lock:
            payload = self._build_packages_payload_locked()
        self._emit("packages", payload)

    def _emit_task_state(self) -> None:
        with self._state_lock:
            payload = self._build_task_payload_locked()
        self._emit("task", payload)

    # ---- Public RPC API (called from JS via pywebview.api) -----------------------

    def get_initial_state(self) -> Dict[str, Any]:
        with self._state_lock:
            cfg = self.config_manager.data
            return {
                "version": self._version,
                "devices": self._serialize_devices(),
                "selectedDeviceIds": list(self.selected_device_ids),
                "deviceErrors": dict(self.device_errors),
                "lastProbeFailed": self.last_probe_failed,
                "refreshing": self.refreshing,
                "scanning": self.scanning,
                "folder": self.folder,
                "recentDirs": list(cfg.get("recent_dirs", [])),
                "packages": self._serialize_packages(),
                "task": self._serialize_task(),
                "installStatus": self.install_status,
                "deviceProgress": dict(self.device_progress),
                "logs": list(self._logs),
                "settings": {
                    "theme": cfg.get("theme", "system"),
                    "logOutputDir": cfg.get("log_output_dir", ""),
                    "defaultLogOutputDir": str(default_log_output_dir()),
                    "parallelInstall": bool(cfg.get("parallel_install", True)),
                    "maxConcurrency": int(cfg.get("max_concurrency", 4)),
                },
                "tools": diagnose_tools(),
                "appLogTargets": self._serialize_app_log_targets(),
                "revisions": dict(self._event_revs),
            }

    def refresh_devices(self, include_packages: bool = False) -> Dict[str, Any]:
        with self._state_lock:
            self._latest_refresh_request_id += 1
            request_id = self._latest_refresh_request_id
            self.refreshing = True
        self._emit_devices_state()

        self.tasks.background(
            detect_devices,
            lambda detection: self._apply_device_refresh_result(request_id, detection),
            lambda error: self._apply_device_refresh_error(request_id, error),
        )
        if include_packages and self.folder.strip():
            self.scan_folder(self.folder, remember=False, silent_empty=True)
        return {"ok": True}

    def _apply_device_refresh_result(self, request_id: int, detection: DeviceDetectionResult) -> None:
        self._apply_device_refresh(
            detection.devices,
            harmony_error=detection.harmony_error,
            android_error=detection.android_error,
            expected_refresh_request_id=request_id,
        )

    def _apply_device_refresh_error(self, request_id: int, error: Exception) -> None:
        with self._state_lock:
            if request_id != self._latest_refresh_request_id:
                return
            self._last_device_refresh_snapshot = None
            self.last_probe_failed = True
            self.refreshing = False
            payload = self._build_devices_payload_locked()
        self._append_log(f"刷新设备列表失败：{error}", "error")
        self._emit("devices", payload)

    def _apply_device_refresh(
        self,
        devices: List[DeviceInfo],
        selection_to_restore: Optional[Iterable[str]] = None,
        summary_label: str = "设备列表已刷新",
        harmony_error: Optional[str] = None,
        android_error: Optional[str] = None,
        expected_refresh_request_id: Optional[int] = None,
    ) -> None:
        probe_errors = {
            platform: error
            for platform, error in (("android", android_error), ("harmony", harmony_error))
            if error
        }
        snapshot = (
            frozenset((d.device_id, d.platform, d.status) for d in devices),
            tuple(sorted(probe_errors.items())),
        )
        with self._state_lock:
            if (
                expected_refresh_request_id is not None
                and expected_refresh_request_id != self._latest_refresh_request_id
            ):
                return
            log_result = (
                bool(probe_errors)
                or snapshot != self._last_device_refresh_snapshot
                or summary_label != "设备列表已刷新"
            )
            self._last_device_refresh_snapshot = snapshot
            self.last_probe_failed = bool(probe_errors)
            self.device_errors = probe_errors
            current_ids = {d.device_id for d in devices}
            requested_selection = set(
                self.selected_device_ids if selection_to_restore is None else selection_to_restore
            )
            if self._device_ids_before_last_refresh is None:
                ordered_devices = list(devices)
                new_ids: Set[str] = set()
            else:
                ordered_devices, new_ids = reorder_devices_for_refresh(
                    devices, self._device_ids_before_last_refresh
                )
            self._device_ids_before_last_refresh = current_ids
            self.devices = ordered_devices
            self.new_device_ids = new_ids

            preserved = [d.device_id for d in self.devices if d.device_id in requested_selection]
            if preserved:
                self.selected_device_ids = preserved
            elif not requested_selection and len(self.devices) == 1 and not probe_errors:
                self.selected_device_ids = [self.devices[0].device_id]
            else:
                self.selected_device_ids = []
            self.refreshing = False
            counts = {key: sum(d.platform == key for d in self.devices) for key in DRIVERS}
            total = len(self.devices)
            payload = self._build_devices_payload_locked()

        self._emit("devices", payload)

        if probe_errors:
            if summary_label != "设备列表已刷新":
                parts = [
                    f"{driver.label} 探测失败" if key in probe_errors else f"{driver.label} {counts[key]} 台"
                    for key, driver in DRIVERS.items()
                ]
                self._append_log(f"{summary_label}：{'，'.join(parts)}", "warn")
            kept = [f"{driver.label} {counts[key]} 台" for key, driver in DRIVERS.items() if key not in probe_errors]
            kept_text = f"；已保留检测到的 {'、'.join(kept)}" if kept else ""
            for key, error in probe_errors.items():
                self._append_log(f"{DRIVERS[key].label} 设备探测失败：{error}{kept_text}", "error")
        elif log_result and total == 0:
            self._append_log(f"{summary_label}：未检测到设备", "warn")
        elif log_result:
            per_platform = "，".join(f"{driver.label} {counts[key]} 台" for key, driver in DRIVERS.items())
            self._append_log(f"{summary_label}：{per_platform}，总计 {total} 台", "info")
            if new_ids:
                self._append_log(f"新增设备已置顶高亮：{self._device_labels_for_log(sorted(new_ids))}", "success")

    def set_selected_devices(self, device_ids: List[str]) -> Dict[str, Any]:
        with self._state_lock:
            known = {d.device_id for d in self.devices}
            self.selected_device_ids = list(dict.fromkeys(did for did in device_ids if did in known))
        self._emit_devices_state()
        return {"ok": True, "selectedDeviceIds": list(self.selected_device_ids)}

    def save_device_name(self, device_id: str, name: str) -> Dict[str, Any]:
        with self._state_lock:
            exists = any(d.device_id == device_id for d in self.devices)
        if not exists:
            return {"ok": False, "error": "设备不在当前列表中"}
        self.config_manager.set_device_name(device_id, name)
        label = self._device_label(device_id)
        self._append_log(f"已保存设备名称：{label}", "success", device_id)
        self._emit_devices_state()
        self._toast("设备名称已更新", label, variant="success")
        return {"ok": True, "label": label}

    # ---- Package scanning & drag-and-drop ----------------------------------------

    def choose_folder(self) -> Dict[str, Any]:
        win = self._window
        if win is None:
            return {"ok": False, "error": "窗口未就绪"}
        try:
            import webview

            start_dir = self.folder if self.folder and Path(self.folder).is_dir() else ""
            result = win.create_file_dialog(_folder_dialog_type(webview), directory=start_dir)
        except Exception as error:
            self._append_log(f"打开目录选择器失败：{error}", "error")
            return {"ok": False, "error": str(error)}
        if not result:
            return {"ok": False, "cancelled": True}
        selected = result[0] if isinstance(result, (list, tuple)) else str(result)
        return self.scan_folder(selected, remember=True)

    def scan_folder(
        self,
        folder_path: str,
        *,
        remember: bool = True,
        preferred_file: Optional[str] = None,
        silent_empty: bool = False,
    ) -> Dict[str, Any]:
        folder = (folder_path or "").strip()
        if not folder:
            if not silent_empty:
                self._toast("请先选择目录", "请输入或选择一个包含 APK/HAP 的文件夹", variant="warn")
                self._append_log("扫描失败：未选择目录", "warn")
            return {"ok": False, "error": "未选择目录"}

        directory = Path(folder)
        if not directory.is_dir():
            self._last_package_scan_snapshot = None
            self._toast("目录无效", f"目录不存在或不是目录：{folder}", variant="error")
            self._append_log(f"扫描失败：目录不存在或不是目录 {directory}", "error")
            return {"ok": False, "error": "目录不存在或不是目录"}

        with self._state_lock:
            self._latest_scan_request_id += 1
            request_id = self._latest_scan_request_id
            self.scanning = True
            payload = self._build_packages_payload_locked()
        self._emit("packages", payload)

        preferred_path = Path(preferred_file) if preferred_file else None

        def _do_scan():
            found = find_packages(directory)
            files = []
            for kind in PACKAGE_KINDS:
                for cand in found[kind]:
                    files.append((str(cand.path), cand.size_bytes, cand.mtime_ns))
            snapshot = (str(directory.resolve()), tuple(files))
            return directory, found, snapshot, preferred_path

        self.tasks.background(
            _do_scan,
            lambda res: self._apply_scan_result(request_id, *res, remember=remember),
            lambda err: self._apply_scan_error(request_id, directory, err),
        )
        return {"ok": True}

    def _apply_scan_error(self, request_id: int, directory: Path, error: Exception) -> None:
        with self._state_lock:
            if request_id != self._latest_scan_request_id:
                return
            self.scanning = False
            payload = self._build_packages_payload_locked()
        self._append_log(f"扫描安装包失败：{directory}，{error}", "error")
        self._toast("扫描安装包失败", str(error), variant="error")
        self._emit("packages", payload)

    def _apply_scan_result(
        self,
        request_id: int,
        directory: Path,
        found,
        snapshot,
        preferred_path: Optional[Path],
        *,
        remember: bool = True,
    ) -> None:
        with self._state_lock:
            if request_id != self._latest_scan_request_id:
                return
            previous_selection = self._selected_packages()
            self.folder = str(directory)
            for kind, slot in self.packages.items():
                pref = (
                    preferred_path
                    if preferred_path and SUFFIX_TO_KIND.get(preferred_path.suffix.lower()) == kind
                    else None
                )
                slot.replace(found[kind], preferred_path=pref)
            self.scanning = False
            selection = self._selected_packages()
            changed = snapshot != self._last_package_scan_snapshot or selection != previous_selection
            self._last_package_scan_snapshot = snapshot

            priority = [p for p in selection.values() if p is not None]
            all_paths = [p for slot in self.packages.values() for p in slot.candidate_paths]
            self._package_label_request = self._package_label_loader.submit(
                all_paths,
                self._on_package_labels,
                priority_paths=priority,
            )
            persist_error: Optional[OSError] = None
            if remember:
                try:
                    self.config_manager.set_last_scan_dir(str(directory))
                except OSError as error:
                    persist_error = error
            payload = self._build_packages_payload_locked()

        if persist_error is not None:
            self._append_log(f"保存最近扫描目录失败：{persist_error}", "warn")
            self._toast("保存目录历史失败", str(persist_error), variant="warn")

        self._emit("packages", payload)
        if changed:
            names = "，".join(f"{kind}={path.name if path else '未找到'}" for kind, path in selection.items())
            self._append_log(f"安装包扫描完成：{directory} · {names}", "info")

    def _on_package_labels(self, generation: int, labels, fingerprints, _done: bool) -> None:
        with self._state_lock:
            if generation != self._package_label_request:
                return
            valid_labels = {}
            for path, label in labels.items():
                try:
                    if fingerprints.get(path) == file_fingerprint(path):
                        valid_labels[path] = label
                except OSError:
                    pass
            if not valid_labels:
                return
            for slot in self.packages.values():
                slot.merge_labels(valid_labels)
        self._emit_packages_state()

    def handle_dropped_paths(self, raw_paths: List[str]) -> Dict[str, Any]:
        """Support dragging an APK/HAP file or a directory directly onto the window."""
        cleaned = [p for p in raw_paths if isinstance(p, str) and p.strip()]
        if not cleaned:
            return {"ok": False, "error": "未检测到有效路径"}
        first = Path(cleaned[0])
        if first.is_dir():
            self._append_log(f"已拖入目录：{first}", "info")
            self._toast("已切换扫描目录", str(first), variant="info")
            return self.scan_folder(str(first), remember=True)
        if first.is_file():
            suffix = first.suffix.lower()
            if suffix in SUFFIX_TO_KIND:
                parent = first.parent
                self._append_log(f"已拖入安装包：{first.name}（目录：{parent}）", "success")
                self._toast("已加载拖入的安装包", first.name, variant="success")
                return self.scan_folder(str(parent), remember=True, preferred_file=str(first))
            self._toast("不支持的文件类型", f"仅支持 .apk / .hap 文件或目录：{first.name}", variant="warn")
            return {"ok": False, "error": "仅支持 .apk / .hap 文件或目录"}
        self._toast("路径不存在", str(first), variant="error")
        return {"ok": False, "error": "路径不存在"}

    def select_package(self, kind: str, index: int, revision: Optional[int] = None) -> Dict[str, Any]:
        with self._state_lock:
            slot = self.packages.get(kind)
            if slot is None:
                return {"ok": False, "error": "无效的安装包类型"}
            if revision is not None and slot.revision != revision:
                payload = self._build_packages_payload_locked()
                stale = True
            else:
                stale = False
                if not slot.choose(index):
                    return {"ok": False, "error": "无效的安装包索引"}
                selected = slot.selected
                payload = self._build_packages_payload_locked()
        if stale:
            self._emit("packages", payload)
            return {"ok": False, "error": "候选列表已更新，请重新选择", "stale": True}
        self._emit("packages", payload)
        if selected:
            self._append_log(f"已切换 {kind} 安装包：{selected.name}", "info")
        return {"ok": True}

    def _selected_packages(self) -> Dict[str, Optional[Path]]:
        return {kind: slot.selected for kind, slot in self.packages.items()}

    # ---- Device target helpers ---------------------------------------------------

    def _target_device(self, explicit_device_id: Optional[str] = None) -> Optional[DeviceInfo]:
        with self._state_lock:
            if explicit_device_id:
                return next((d for d in self.devices if d.device_id == explicit_device_id), None)
            return resolve_target(
                self.selected_device_ids,
                self.devices,
                auto_select=not self.last_probe_failed,
            )

    def _device_for_task(
        self,
        name: str,
        missing_message: str,
        explicit_device_id: Optional[str] = None,
    ) -> Optional[DeviceInfo]:
        if self.tasks.busy:
            label = self.tasks.current.label if self.tasks.current else "任务"
            self._append_log(f"{label}进行中，请稍候", "warn")
            self._toast("任务进行中", f"{label}正在执行，请等待或先中止", variant="warn")
            return None
        device = self._target_device(explicit_device_id)
        if device is None:
            self._toast("请选择目标设备", missing_message, variant="warn")
            self._append_log(f"获取{name}失败：{missing_message}", "warn")
        return device

    # ---- Install workflow --------------------------------------------------------

    def start_install(self, device_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        if self.tasks.busy:
            self.cancel_task()
            return {"ok": True, "action": "cancelled"}

        with self._state_lock:
            if self.scanning:
                self._toast("安装包扫描中", "请等待目录扫描完成后再开始安装", variant="warn")
                self._append_log("安装已拦截：正在扫描安装包目录", "warn")
                return {"ok": False, "error": "安装包扫描中，请稍候"}
            packages = self._selected_packages()
            if not any(packages.values()):
                self._toast("未找到安装包", "请先选择包含 APK 或 HAP 的目录", variant="warn")
                self._append_log("安装失败：未找到可安装的 APK/HAP", "warn")
                return {"ok": False, "error": "未找到可安装的 APK/HAP"}
            previous_selection = set(device_ids if device_ids is not None else self.selected_device_ids)
            allow_test = apk_allow_test(self.packages["APK"])
            cfg = self.config_manager.data
            parallel = bool(cfg.get("parallel_install", True))
            max_concurrency = int(cfg.get("max_concurrency", 4))
            self.device_progress = {}

        selected_text = (
            self._device_labels_for_log(sorted(previous_selection))
            if previous_selection
            else "未选择（单设备时将自动选择）"
        )
        package_text = "，".join(f"{kind}={path.name if path else '未找到'}" for kind, path in packages.items())
        self._append_log(f"收到安装请求：设备={selected_text}，{package_text}", "info")
        self._append_log("开始安装前设备校验…", "info")

        task = self.tasks.start("install", "安装", verb="")
        if task is None:
            return {"ok": False, "error": "已有任务正在运行"}

        def _preflight():
            started_at = time.perf_counter()
            detection = detect_devices(cancel=task.cancel)
            return detection, time.perf_counter() - started_at

        self.tasks.run(
            task,
            _preflight,
            lambda res: self._finalize_install(
                task,
                res[0],
                previous_selection,
                packages,
                allow_test,
                parallel,
                max_concurrency,
                res[1],
            ),
            lambda err: self._apply_install_preparation_error(task, err),
        )
        return {"ok": True}

    def _apply_install_preparation_error(self, task: Task, error: Exception) -> None:
        with self._state_lock:
            self._last_device_refresh_snapshot = None
        self._end_task(task, f"安装前设备校验失败：{error}", ok=False, status="安装异常")
        self._toast("安装前校验失败", str(error), variant="error")

    def _finalize_install(
        self,
        task: Task,
        detection: DeviceDetectionResult,
        previous_selection: Set[str],
        packages: Dict[str, Optional[Path]],
        allow_test: bool,
        parallel: bool,
        max_concurrency: int,
        validation_duration: float,
    ) -> None:
        if task.cancelled:
            self._end_task(task, "安装已中止", ok=False, status="已中止")
            return

        preflight_devices = list(detection.devices)
        failed_platforms = set(detection.errors)
        if failed_platforms:
            with self._state_lock:
                verifiable_ids = {d.device_id for d in self.devices if d.platform not in failed_platforms}
            if not previous_selection or previous_selection - verifiable_ids:
                message = "\n".join(detection.errors.values())
                self._apply_install_preparation_error(task, RuntimeError(message))
                return

        self._apply_device_refresh(
            preflight_devices,
            previous_selection,
            summary_label=f"安装前设备校验完成（耗时 {validation_duration:.2f} 秒）",
            harmony_error=detection.harmony_error,
            android_error=detection.android_error,
        )

        current_ids = {d.device_id for d in preflight_devices}
        missing = previous_selection - current_ids
        selection_list = [d.device_id for d in preflight_devices if d.device_id in previous_selection]
        auto_picked: Optional[str] = None
        if not selection_list and not previous_selection and len(preflight_devices) == 1 and not failed_platforms:
            selection_list = [preflight_devices[0].device_id]
            auto_picked = self._device_label(selection_list[0])
            with self._state_lock:
                if {d.device_id for d in self.devices} == current_ids:
                    self.selected_device_ids = list(selection_list)
                    auto_payload = self._build_devices_payload_locked()
                else:
                    auto_payload = None
        else:
            auto_payload = None

        if missing:
            missing_text = self._device_labels_for_log(sorted(missing))
            self._toast("部分设备已断开", f"已跳过断开的设备：{missing_text}", variant="warn")
            self._append_log(f"安装提示：已选设备已断开 {missing_text}", "warn")

        if auto_picked:
            if auto_payload is not None:
                self._emit("devices", auto_payload)
            self._append_log(f"检测到单设备，默认安装到：{auto_picked}", "info")

        if not selection_list:
            if previous_selection:
                self._toast("已选设备均已断开", "请重新连接设备后再试", variant="warn")
                self._end_task(task, "安装失败：已选设备均已断开", ok=False, status="就绪")
            else:
                self._toast("请先选择设备", "未选择任何可用的目标设备", variant="warn")
                self._end_task(task, "安装失败：未选择设备", ok=False, status="就绪")
            return

        plan = build_install_plan(selection_list, preflight_devices, packages, self._device_label)

        def _on_device_progress(device_id: str, state: str, detail: str, duration: Optional[float]) -> None:
            with self._state_lock:
                self.device_progress[device_id] = {
                    "state": state,
                    "detail": detail,
                    "duration": duration,
                }
            self._emit_task_state()

        self.tasks.run(
            task,
            lambda: run_install_plan(
                plan,
                allow_test,
                task.cancel,
                self._append_log,
                parallel=parallel,
                max_workers=max_concurrency,
                on_progress=_on_device_progress,
            ),
            lambda outcome: self._finish_install_outcome(task, outcome),
            lambda error: self._end_task(task, f"安装线程异常：{error}", ok=False, status="安装异常"),
        )

    def _finish_install_outcome(self, task: Task, outcome: InstallOutcome) -> None:
        summary = (
            f"{outcome.status}（成功 {outcome.succeeded}，失败 {outcome.failed}，跳过 {outcome.skipped}）"
            if (outcome.succeeded or outcome.failed or outcome.skipped)
            else outcome.status
        )
        ok = outcome.status == "安装完成"
        self._end_task(task, summary, ok=ok, status=outcome.status)
        variant = "success" if ok else ("warn" if outcome.cancelled or outcome.skipped else "error")
        self._toast(outcome.status, summary, variant=variant)

    # ---- UDID, Crash Log, Harmony App Log ----------------------------------------

    def fetch_udid(self, device_id: Optional[str] = None) -> Dict[str, Any]:
        device = self._device_for_task("UDID", "请选择一个 Harmony 设备", device_id)
        if not device:
            return {"ok": False}
        driver = driver_for(device.platform)
        if driver is None or not driver.supports_udid:
            platform_label = driver.label if driver else device.platform
            self._toast("平台不支持", f"设备为 {platform_label}，仅支持 Harmony 设备获取 UDID", variant="warn")
            self._append_log(f"获取 UDID 失败：设备 {self._device_label(device.device_id)} 为 {platform_label}", "warn")
            return {"ok": False}
        task = self.tasks.start("udid", "UDID")
        if task is None:
            return {"ok": False}
        did = device.device_id
        self._append_log(f"开始获取设备 UDID：{self._device_label(did)}", "cmd", did)
        self.tasks.run(
            task,
            lambda: driver.udid(did, cancel=task.cancel),
            lambda udid: self._apply_udid_result(task, did, udid),
            lambda err: self._apply_udid_error(task, did, err),
        )
        return {"ok": True}

    def _apply_udid_error(self, task: Task, device_id: str, error: Exception) -> None:
        if task.cancelled:
            self._end_task(task, "获取 UDID 已中止", ok=False, status="已中止")
            return
        msg = f"获取 UDID 失败：设备 {self._device_label(device_id)}，{error}"
        self._end_task(task, msg, ok=False)
        self._toast("获取 UDID 失败", str(error), variant="error")

    def _apply_udid_result(self, task: Task, device_id: str, udid: Optional[str]) -> None:
        label = self._device_label(device_id)
        if not udid:
            self._end_task(task, f"获取 UDID 失败：设备 {label} 未返回 UDID", ok=False)
            self._toast("未获取到 UDID", f"设备 {label} 未返回有效 UDID", variant="warn")
            return
        self._end_task(task, f"已获取设备 UDID：{label} -> {udid}", ok=True)
        self._toast(f"{label} 的 UDID", udid, variant="success", copy_text=udid)

    def fetch_crash_log(self, device_id: Optional[str] = None) -> Dict[str, Any]:
        device = self._device_for_task("崩溃日志", "请选择一个目标设备", device_id)
        if not device:
            return {"ok": False}
        driver = driver_for(device.platform)
        if driver is None:
            self._toast("平台不支持", "仅支持 Android 或 Harmony 设备", variant="warn")
            return {"ok": False}
        output_dir = self.config_manager.resolved_log_output_dir()
        task = self.tasks.start("crash_log", "崩溃日志")
        if task is None:
            return {"ok": False}
        did = device.device_id
        self._append_log(
            f"开始获取{driver.crash_log_description}：{self._device_label(did)} -> {driver.crash_log_destination(output_dir)}",
            "cmd",
            did,
        )
        self.tasks.run(
            task,
            lambda: driver.collect_crash_log(did, output_dir, cancel=task.cancel),
            lambda res: self._apply_crash_log_result(task, did, driver, res),
            lambda err: self._apply_log_collection_error(task, did, err),
        )
        return {"ok": True}

    def fetch_app_log(self, target_key: str, device_id: Optional[str] = None) -> Dict[str, Any]:
        target = next(
            (driver.app_log_targets[target_key] for driver in DRIVERS.values() if target_key in driver.app_log_targets),
            None,
        )
        if target is None:
            return {"ok": False, "error": f"未知日志目标：{target_key}"}
        device = self._device_for_task(target.display_name, "请选择一个 Harmony 设备", device_id)
        if not device:
            return {"ok": False}
        driver = driver_for(device.platform)
        if driver is None or target_key not in driver.app_log_targets:
            self._toast("仅支持 Harmony 设备", f"{target.display_name}仅支持 Harmony 设备", variant="warn")
            self._append_log(f"获取{target.display_name}失败：设备 {self._device_label(device.device_id)} 非 Harmony", "warn")
            return {"ok": False}
        output_dir = self.config_manager.resolved_log_output_dir()
        task = self.tasks.start("app_log", target.display_name)
        if task is None:
            return {"ok": False}
        did = device.device_id
        self._append_log(
            f"开始获取{target.display_name}：{self._device_label(did)} · {target.remote_path} -> {output_dir}",
            "cmd",
            did,
        )
        self.tasks.run(
            task,
            lambda: driver.collect_app_log(did, output_dir, target_key, cancel=task.cancel),
            lambda res: self._apply_app_log_result(task, did, target, res),
            lambda err: self._apply_log_collection_error(task, did, err),
        )
        return {"ok": True}

    def _apply_log_collection_error(self, task: Task, device_id: str, error: Exception) -> None:
        label = self._device_label(device_id)
        if task.cancelled:
            self._end_task(task, f"{task.label}已中止：设备 {label}", ok=False, status="已中止")
            return
        self._end_task(task, f"{task.label}失败：设备 {label}\n{error}", ok=False)
        self._toast(f"{task.label}失败", f"设备 {label}：{error}", variant="error")

    def _apply_crash_log_result(
        self,
        task: Task,
        device_id: str,
        driver: PlatformDriver,
        result: CollectResult,
    ) -> None:
        label = self._device_label(device_id)
        proc = result.process
        self._append_log(f"{driver.label} {label} 崩溃日志命令：{format_command_for_log(result.command)}", "cmd", device_id)
        if proc.returncode != 0:
            if task.cancelled:
                self._end_task(task, f"获取崩溃日志已中止：设备 {label}", ok=False, status="已中止")
                return
            self._end_task(
                task,
                f"获取崩溃日志失败：设备 {label} 返回码 {proc.returncode}\n{proc.stderr}",
                ok=False,
            )
            self._toast("获取崩溃日志失败", f"设备 {label} 返回码：{proc.returncode}", variant="error")
            return
        if result.zip_path:
            self._end_task(
                task,
                f"获取崩溃日志成功：设备 {label}，共 {result.file_count} 个文件，ZIP: {result.zip_path}",
                ok=True,
            )
            self._toast(
                "崩溃日志已打包",
                f"共 {result.file_count} 个文件 · {result.zip_path.name}",
                variant="success",
                action_label="打开位置",
                action_path=str(result.zip_path),
            )
            return
        if result.appended_to:
            self._end_task(task, f"获取崩溃日志成功：设备 {label}，已追加到 {result.appended_to}", ok=True)
            self._toast(
                "崩溃日志已写入",
                str(result.appended_to),
                variant="success",
                action_label="打开位置",
                action_path=str(result.appended_to),
            )
            return
        diagnostics = (proc.stderr or proc.stdout or "").strip()
        self._end_task(
            task,
            f"获取崩溃日志完成但无输出：设备 {label}" + (f"\n{diagnostics}" if diagnostics else ""),
            ok=False,
        )
        self._toast("未获取到崩溃日志", diagnostics or "目标设备上没有匹配记录", variant="warn")

    def _apply_app_log_result(self, task: Task, device_id: str, target, result: CollectResult) -> None:
        label = self._device_label(device_id)
        proc = result.process
        self._append_log(f"{target.display_name}命令：{format_command_for_log(result.command)}", "cmd", device_id)
        diagnostics = "\n".join(part for part in (proc.stdout.strip(), proc.stderr.strip()) if part)
        if proc.returncode != 0:
            if task.cancelled:
                self._end_task(task, f"获取{target.display_name}已中止：设备 {label}", ok=False, status="已中止")
                return
            self._end_task(
                task,
                f"获取{target.display_name}失败：设备 {label} 返回码 {proc.returncode}"
                + (f"\n{diagnostics}" if diagnostics else ""),
                ok=False,
            )
            self._toast(f"获取{target.display_name}失败", f"设备 {label} 返回码：{proc.returncode}", variant="error")
            return
        if not result.zip_path:
            self._end_task(
                task,
                f"获取{target.display_name}完成但无输出：设备 {label}；远端={target.remote_path}"
                + (f"\n{diagnostics}" if diagnostics else ""),
                ok=False,
            )
            self._toast(
                f"{target.display_name}为空",
                "未拉取到任何文件，请检查应用是否安装及目标目录是否存在",
                variant="warn",
            )
            return
        self._end_task(
            task,
            f"获取{target.display_name}成功：设备 {label}，共 {result.file_count} 个文件，ZIP: {result.zip_path}",
            ok=True,
        )
        self._toast(
            f"{target.display_name}已打包",
            f"共 {result.file_count} 个文件 · {result.zip_path.name}",
            variant="success",
            action_label="打开位置",
            action_path=str(result.zip_path),
        )

    # ---- Task lifecycle & utilities ----------------------------------------------

    def cancel_task(self) -> Dict[str, Any]:
        task = self.tasks.current
        if task and self.tasks.cancel(expected=task):
            self._append_log(f"已请求中止{task.label}…", "warn")
            return {"ok": True}
        return {"ok": False}

    def _end_task(
        self,
        task: Task,
        message: str,
        *,
        ok: bool = True,
        status: Optional[str] = None,
    ) -> None:
        final_status = status if status is not None else f"{task.label}{'完成' if ok else '失败'}"
        with self._state_lock:
            self.install_status = final_status
        level = "success" if ok else ("warn" if final_status in ("已中止", "安装未完成", "就绪") else "error")
        self._append_log(message, level)
        self._emit_task_state()

    def _on_task_change(self) -> None:
        task = self.tasks.current
        with self._state_lock:
            if task is not None:
                self.install_status = "正在中止…" if task.cancelled else f"{task.label}中…"
        self._emit_task_state()

    def clear_logs(self) -> Dict[str, Any]:
        with self._state_lock:
            self._logs.clear()
            self._last_device_refresh_snapshot = None
            self._last_package_scan_snapshot = None
        self._emit("logs_cleared", {})
        return {"ok": True}

    def open_path_in_explorer(self, target_path: str) -> Dict[str, Any]:
        if not target_path:
            return {"ok": False, "error": "路径为空"}
        path = Path(target_path)
        if not path.exists():
            parent = path.parent
            if parent.exists():
                path = parent
            else:
                self._toast("路径不存在", str(path), variant="warn")
                return {"ok": False, "error": "路径不存在"}
        try:
            if os.name == "nt":
                if path.is_file():
                    subprocess.Popen(["explorer", f"/select,{path}"], creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(path)] if path.is_file() else ["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path.parent if path.is_file() else path)])
            return {"ok": True}
        except OSError as error:
            self._toast("无法打开位置", str(error), variant="error")
            return {"ok": False, "error": str(error)}

    def choose_log_output_dir(self) -> Dict[str, Any]:
        win = self._window
        if win is None:
            return {"ok": False, "error": "窗口未就绪"}
        try:
            import webview

            current = str(self.config_manager.resolved_log_output_dir())
            result = win.create_file_dialog(_folder_dialog_type(webview), directory=current if Path(current).is_dir() else "")
        except Exception as error:
            return {"ok": False, "error": str(error)}
        if not result:
            return {"ok": False, "cancelled": True}
        selected = result[0] if isinstance(result, (list, tuple)) else str(result)
        return self.update_settings({"logOutputDir": selected})

    def update_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        mapped: Dict[str, Any] = {}
        if "theme" in updates:
            mapped["theme"] = updates["theme"]
        if "logOutputDir" in updates:
            mapped["log_output_dir"] = updates["logOutputDir"]
        if "parallelInstall" in updates:
            mapped["parallel_install"] = bool(updates["parallelInstall"])
        if "maxConcurrency" in updates:
            try:
                mapped["max_concurrency"] = max(1, min(8, int(updates["maxConcurrency"])))
            except (TypeError, ValueError):
                pass
        with self._state_lock:
            cfg = self.config_manager.update_settings(mapped)
            settings_payload = {
                "rev": self._next_rev_locked("settings"),
                "theme": cfg.get("theme", "system"),
                "logOutputDir": cfg.get("log_output_dir", ""),
                "defaultLogOutputDir": str(default_log_output_dir()),
                "parallelInstall": bool(cfg.get("parallel_install", True)),
                "maxConcurrency": int(cfg.get("max_concurrency", 4)),
            }
        self._emit("settings", settings_payload)
        return {"ok": True, "settings": settings_payload}

    def diagnose_environment(self) -> Dict[str, Any]:
        report = diagnose_tools()
        return {"ok": True, "tools": report}
