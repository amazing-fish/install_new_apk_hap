"""Dropdown text for packages; the path, never the text, is the identity."""
from pathlib import Path

from metadata.model import PackageLabel


def package_version_text(label: PackageLabel) -> str:
    if label.version_name and label.version_code is not None:
        return f'{label.version_name} ({label.version_code})'
    if label.version_name:
        return label.version_name
    if label.version_code is not None:
        return f'versionCode {label.version_code}'
    return ''


def package_display_labels(paths: list[Path], labels: dict[Path, PackageLabel]) -> dict[str, Path]:
    """Display strings are unique even if filenames imitate formatted labels."""
    result = {}
    statuses = {'unresolved': '资源名未解析', 'unavailable': '缺少解析工具',
                'invalid': '名称读取失败', 'missing': '未声明名称',
                'unsupported': '名称格式不支持', 'limited': '名称读取受限'}
    for path in paths:
        label = labels.get(path)
        if label is None:
            display = path.name
        else:
            version = package_version_text(label)
            if label.name and label.status == 'resolved':
                details = [label.name]
                if version:
                    details.append(version)
                display = f'{" · ".join(details)}（{path.name}）'
            else:
                if label.status == 'unavailable':
                    reason = f'缺少 {label.source}'
                elif label.status == 'tool_failed':
                    reason = f'{label.source} 解析失败'
                else:
                    reason = statuses.get(label.status, '名称未解析')
                display = f'{version}（{path.name}）' if version else path.name
                display = f'{display} [{reason}]'
        unique, number = display, 2
        while unique in result:
            unique = f'{display} [{number}]'
            number += 1
        result[unique] = path
    return result
