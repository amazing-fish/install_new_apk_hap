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


def _prepare_apk(app, apk: Path) -> None:
    app.latest_apk = apk
    app._package_candidates = ([apk], [])
    app.apk_name_map = {apk.name: apk}
    app.apk_combo.configure(values=[apk.name], state='readonly')
    app.apk_var.set(apk.name)


@pytest.mark.parametrize('label,expected', [
    (None, True),
    (PackageLabel('Test', 'resolved', test_only=True), True),
    (PackageLabel('Release', 'resolved', test_only=False), False),
    (PackageLabel(status='unavailable', source='aapt2'), True),
    (PackageLabel(status='tool_failed', source='aapt2'), True),
    (PackageLabel(status='invalid'), True),
    (PackageLabel(status='limited'), True),
    (PackageLabel(status='unsupported'), True),
])
def test_apk_allow_test_only_turns_off_for_explicit_false(app, tmp_path, label, expected):
    apk = tmp_path / 'demo.apk'
    apk.touch()
    _prepare_apk(app, apk)
    app._package_labels = {} if label is None else {apk: label}

    assert app._apk_allow_test(apk) is expected


def test_no_apk_does_not_request_t(app):
    assert app._apk_allow_test(None) is False


def test_unknown_metadata_never_blocks_known_android_install(app, tmp_path, monkeypatch):
    apk = tmp_path / 'pending.apk'
    apk.touch()
    app._apply_device_refresh([DeviceInfo('a', 'android', 'device')])
    app.device_tree.selection_set('a')
    app.on_device_select(None)
    _prepare_apk(app, apk)
    app._package_labels = {}

    DeferredThread.created = []
    monkeypatch.setattr(main.threading, 'Thread', DeferredThread)
    app.install_to_selected()

    assert app.install_button.cget('text') == '中止安装'
    assert DeferredThread.created[0][1] == ({'a'}, apk, None, True)


def test_unknown_target_snapshot_stays_installable_when_preflight_selects_android(app, tmp_path, monkeypatch):
    """Regression: the target can become Android only after fresh preflight."""
    apk = tmp_path / 'unknown.apk'
    apk.touch()
    app._apply_device_refresh([
        DeviceInfo('old-a', 'android', 'device'),
        DeviceInfo('old-h', 'harmony', 'device'),
    ])
    app.device_tree.selection_remove(*app.device_tree.selection())
    _prepare_apk(app, apk)
    app._package_labels = {}

    DeferredThread.created = []
    monkeypatch.setattr(main.threading, 'Thread', DeferredThread)
    app.install_to_selected()
    assert DeferredThread.created[0][1] == (set(), apk, None, True)

    app._finalize_install(
        [DeviceInfo('fresh-a', 'android', 'device')],
        *DeferredThread.created[0][1],
    )
    assert DeferredThread.created[1][1] == (['fresh-a'], apk, None, True)


def test_explicit_non_test_metadata_keeps_precise_no_t_snapshot(app, tmp_path, monkeypatch):
    apk = tmp_path / 'release.apk'
    apk.touch()
    app._apply_device_refresh([DeviceInfo('a', 'android', 'device')])
    app.device_tree.selection_set('a')
    app.on_device_select(None)
    _prepare_apk(app, apk)
    app._package_labels = {apk: PackageLabel('Release', 'resolved', test_only=False)}

    DeferredThread.created = []
    monkeypatch.setattr(main.threading, 'Thread', DeferredThread)
    app.install_to_selected()

    assert DeferredThread.created[0][1] == ({'a'}, apk, None, False)
