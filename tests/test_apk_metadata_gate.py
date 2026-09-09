from pathlib import Path

import pytest

import main
from services.device_detector import DeviceInfo
from services.package_metadata import PackageLabel


class DeferredThread:
    created = []

    def __init__(self, *, target, args, daemon):
        self.target = target
        self.args = args
        self.daemon = daemon
        self.created.append((target, args))

    def start(self):
        pass


def _prepare_package(app, apk: Path, hap: Path | None = None):
    app.latest_apk = apk
    app.latest_hap = hap
    app._package_candidates = ([apk], [hap] if hap else [])
    app.apk_name_map = {apk.name: apk}
    app.apk_combo.configure(values=[apk.name], state='readonly')
    app.apk_var.set(apk.name)
    if hap:
        app.hap_name_map = {hap.name: hap}
        app.hap_combo.configure(values=[hap.name], state='readonly')
        app.hap_var.set(hap.name)


def test_pending_testonly_metadata_blocks_known_android_until_resolved(app, tmp_path, monkeypatch):
    apk = tmp_path / 'test-only.apk'
    apk.touch()
    app._apply_device_refresh([DeviceInfo('a', 'android', 'device')])
    app.device_tree.selection_set('a')
    app.on_device_select(None)
    _prepare_package(app, apk)
    app._package_metadata_pending = {apk}
    app._update_apk_test_flag()
    app._update_device_actions()

    # Unknown metadata uses the permissive install flag, while a known Android
    # target is still gated until the exact parsed value arrives.
    assert app.apk_test_var.get() is True
    assert app.install_button.instate(['disabled'])
    assert app.install_button.cget('text') == '等待 APK 解析…'

    warnings = []
    monkeypatch.setattr(main.messagebox, 'showwarning', lambda *args: warnings.append(args))
    DeferredThread.created = []
    monkeypatch.setattr(main.threading, 'Thread', DeferredThread)

    # Defensive gate still applies if the command is invoked programmatically.
    app.install_to_selected()
    assert DeferredThread.created == []
    assert warnings and '元数据尚未就绪' in warnings[-1][1]

    app._apply_package_labels({
        apk: PackageLabel('Test App', 'resolved', test_only=True),
    })
    assert apk not in app._package_metadata_pending
    assert app.apk_test_var.get() is True
    assert app.install_button.instate(['!disabled'])
    assert app.install_button.cget('text') == '安装到所选设备'

    app.install_to_selected()
    assert len(DeferredThread.created) == 1
    _target, args = DeferredThread.created[0]
    assert args == ({'a'}, apk, None, True)


def test_harmony_only_install_is_not_blocked_by_pending_apk_metadata(app, tmp_path, monkeypatch):
    apk = tmp_path / 'pending.apk'
    hap = tmp_path / 'ready.hap'
    apk.touch(); hap.touch()
    app._apply_device_refresh([
        DeviceInfo('a', 'android', 'device'),
        DeviceInfo('h', 'harmony', 'device'),
    ])
    app.device_tree.selection_set('h')
    app.on_device_select(None)
    _prepare_package(app, apk, hap)
    app._package_metadata_pending = {apk}
    app._update_apk_test_flag()
    app._update_device_actions()

    assert app.apk_test_var.get() is True
    assert app.install_button.instate(['!disabled'])
    DeferredThread.created = []
    monkeypatch.setattr(main.threading, 'Thread', DeferredThread)
    app.install_to_selected()
    assert len(DeferredThread.created) == 1
    _target, args = DeferredThread.created[0]
    assert args == ({'h'}, apk, hap, True)


def test_unknown_target_snapshots_safe_t_before_preflight_auto_selects_android(app, tmp_path, monkeypatch):
    """Regression for P1: target becomes Android only after fresh preflight."""
    apk = tmp_path / 'pending.apk'
    apk.touch()
    app._apply_device_refresh([
        DeviceInfo('old-a', 'android', 'device'),
        DeviceInfo('old-h', 'harmony', 'device'),
    ])
    app.device_tree.selection_remove(*app.device_tree.selection())
    _prepare_package(app, apk)
    app._package_metadata_pending = {apk}
    app._update_apk_test_flag()
    app._update_device_actions()

    # With no selected target and multiple cached devices, preflight must decide
    # the target. The snapshot is nevertheless safe because unknown => -t=True.
    assert app.apk_test_var.get() is True
    assert app.install_button.instate(['!disabled'])

    DeferredThread.created = []
    monkeypatch.setattr(main.threading, 'Thread', DeferredThread)
    app.install_to_selected()
    assert len(DeferredThread.created) == 1
    _preflight_target, preflight_args = DeferredThread.created[0]
    assert preflight_args == (set(), apk, None, True)

    # Fresh detection now sees exactly one Android and auto-selects it.
    app._finalize_install(
        [DeviceInfo('fresh-a', 'android', 'device')],
        *preflight_args,
    )
    assert len(DeferredThread.created) == 2
    _install_target, install_args = DeferredThread.created[1]
    assert install_args == (['fresh-a'], apk, None, True)


@pytest.mark.parametrize('status,source', [
    ('unavailable', 'aapt2'),
    ('tool_failed', 'aapt2'),
    ('invalid', ''),
    ('limited', ''),
])
def test_parser_failure_releases_gate_and_defaults_to_installable_t(app, tmp_path, monkeypatch, status, source):
    apk = tmp_path / f'{status}.apk'
    apk.touch()
    app._apply_device_refresh([DeviceInfo('a', 'android', 'device')])
    app.device_tree.selection_set('a')
    app.on_device_select(None)
    _prepare_package(app, apk)
    app._package_metadata_pending = {apk}
    app._update_apk_test_flag()
    app._update_device_actions()
    assert app.apk_test_var.get() is True
    assert app.install_button.instate(['disabled'])

    app._apply_package_labels({
        apk: PackageLabel(status=status, source=source),
    })
    assert apk not in app._package_metadata_pending
    assert app.apk_test_var.get() is True
    assert app.install_button.instate(['!disabled'])

    DeferredThread.created = []
    monkeypatch.setattr(main.threading, 'Thread', DeferredThread)
    app.install_to_selected()
    assert DeferredThread.created[0][1] == ({'a'}, apk, None, True)
