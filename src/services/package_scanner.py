from dataclasses import dataclass
import json
from pathlib import Path
from typing import List, Optional, Tuple
import zipfile


@dataclass
class PackageInfo:
    apk_path: Optional[Path]
    hap_path: Optional[Path]
    apk_candidates: List[Path]
    hap_candidates: List[Path]
    apk_display_map: List[Tuple[str, Path]]
    hap_display_map: List[Tuple[str, Path]]


def _latest_file(directory: Path, suffix: str) -> Optional[Path]:
    candidates = [p for p in directory.glob(f"*{suffix}") if p.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _latest_files(directory: Path, suffix: str, limit: int = 5) -> List[Path]:
    candidates = [p for p in directory.glob(f"*{suffix}") if p.is_file()]
    if not candidates:
        return []
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]


def _safe_text(value: object) -> Optional[str]:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def _build_display_name(path: Path, app_name: Optional[str]) -> str:
    if app_name and app_name != path.name:
        return f"{app_name}（{path.name}）"
    return path.name


def _parse_apk_app_name(apk_path: Path) -> Optional[str]:
    # 纯 Python 场景下不强依赖 aapt，优先回退文件名
    return None


def _parse_hap_app_name(hap_path: Path) -> Optional[str]:
    try:
        with zipfile.ZipFile(hap_path, "r") as zip_file:
            for name in ("module.json", "module.json5", "pack.info"):
                if name not in zip_file.namelist():
                    continue
                content = zip_file.read(name).decode("utf-8", errors="ignore")
                if name.endswith(".json5"):
                    # 轻量兼容：尽力抽取 label/name 关键字段，不做完整 json5 解析
                    for line in content.splitlines():
                        if "label" in line or "name" in line:
                            quote_start = line.find('"')
                            quote_end = line.rfind('"')
                            if quote_start >= 0 and quote_end > quote_start:
                                parsed = _safe_text(line[quote_start + 1:quote_end])
                                if parsed:
                                    return parsed
                    continue
                data = json.loads(content)
                for key in ("label", "appName", "name"):
                    parsed = _safe_text(data.get(key))
                    if parsed:
                        return parsed
    except Exception:
        return None
    return None


def _build_display_map(paths: List[Path], parser) -> List[Tuple[str, Path]]:
    result: List[Tuple[str, Path]] = []
    for path in paths:
        app_name = parser(path)
        result.append((_build_display_name(path, app_name), path))
    return result


def find_latest_packages(directory: Path) -> PackageInfo:
    apk = _latest_file(directory, ".apk")
    hap = _latest_file(directory, ".hap")
    apk_candidates = _latest_files(directory, ".apk")
    hap_candidates = _latest_files(directory, ".hap")
    apk_display_map = _build_display_map(apk_candidates, _parse_apk_app_name)
    hap_display_map = _build_display_map(hap_candidates, _parse_hap_app_name)
    return PackageInfo(
        apk_path=apk,
        hap_path=hap,
        apk_candidates=apk_candidates,
        hap_candidates=hap_candidates,
        apk_display_map=apk_display_map,
        hap_display_map=hap_display_map,
    )


def package_display_info(package_info: PackageInfo) -> Tuple[str, str]:
    apk_name = package_info.apk_path.name if package_info.apk_path else "未找到"
    hap_name = package_info.hap_path.name if package_info.hap_path else "未找到"
    return apk_name, hap_name
