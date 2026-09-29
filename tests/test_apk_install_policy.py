"""The -t rule as the install flow applies it; the rule itself is in test_packages."""
from pathlib import Path

from platforms import DeviceInfo
from metadata import PackageLabel


def _prepare_apk(app, apk: Path, label=None) -> None:
    app.packages['APK'].replace([apk])
    if label is not None:
        app._apply_package_labels({apk: label})
    else:
        app._render_packages()


def test_unknown_metadata_never_blocks_known_android_install(app, tmp_path, deferred_tasks, preflight,
                                                           install_plans):
    apk = tmp_path / 'pending.apk'
    apk.touch()
    devices = [DeviceInfo('a', 'android', 'device')]
    app._apply_device_refresh(devices)
    app.device_tree.selection_set('a')
    app.on_device_select(None)
    _prepare_apk(app, apk)

    app.install_to_selected()

    assert app.install_button.cget('text') == '中止安装'
    preflight(devices)
    deferred_tasks.run_all()
    assert install_plans == [([('a', apk)], True)]


def test_unknown_target_snapshot_stays_installable_when_preflight_selects_android(
        app, tmp_path, preflight, install_plans):
    """Regression: the target can become Android only after fresh preflight."""
    apk = tmp_path / 'unknown.apk'
    apk.touch()
    app._apply_device_refresh([
        DeviceInfo('old-a', 'android', 'device'),
        DeviceInfo('old-h', 'harmony', 'device'),
    ])
    app.device_tree.selection_remove(*app.device_tree.selection())
    _prepare_apk(app, apk)
    preflight([DeviceInfo('fresh-a', 'android', 'device')])

    app.install_to_selected()

    assert install_plans == [([('fresh-a', apk)], True)]


def test_explicit_non_test_metadata_keeps_precise_no_t_snapshot(app, tmp_path, preflight, install_plans):
    apk = tmp_path / 'release.apk'
    apk.touch()
    devices = [DeviceInfo('a', 'android', 'device')]
    app._apply_device_refresh(devices)
    app.device_tree.selection_set('a')
    app.on_device_select(None)
    _prepare_apk(app, apk, PackageLabel('Release', 'resolved', test_only=False))
    preflight(devices)

    app.install_to_selected()

    assert install_plans == [([('a', apk)], False)]
