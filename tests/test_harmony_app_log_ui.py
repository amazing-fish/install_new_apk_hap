import main
from services.device_detector import DeviceInfo


class DeferredThread:
    created = []

    def __init__(self, *, target, args, daemon):
        self.target = target
        self.args = args
        self.daemon = daemon
        self.created.append((target, args))

    def start(self):
        pass


def test_qiankun_log_starts_shared_worker_for_selected_harmony(app, monkeypatch):
    app._apply_device_refresh([DeviceInfo('h', 'harmony', 'device')])
    app.device_tree.selection_set('h')
    app.on_device_select(None)
    DeferredThread.created = []
    monkeypatch.setattr(main.threading, 'Thread', DeferredThread)

    app.fetch_qiankun_log()

    assert app.crash_log_fetching is True
    assert app.log_operation == '乾崑日志'
    assert app.app_log_button.cget('text') == '获取乾崑日志中…'
    assert len(DeferredThread.created) == 1
    target, args = DeferredThread.created[0]
    assert target == app._fetch_harmony_app_log_worker
    assert args[0] == 'h'
    assert args[2] == 'qiankun'


def test_demo_log_rejects_android_without_starting_worker(app, monkeypatch):
    app._apply_device_refresh([DeviceInfo('a', 'android', 'device')])
    app.device_tree.selection_set('a')
    app.on_device_select(None)
    warnings = []
    monkeypatch.setattr(main.messagebox, 'showwarning', lambda *args: warnings.append(args))
    DeferredThread.created = []
    monkeypatch.setattr(main.threading, 'Thread', DeferredThread)

    app.fetch_demo_log()

    assert DeferredThread.created == []
    assert app.crash_log_fetching is False
    assert warnings and warnings[-1][1] == '仅支持 Harmony 设备'
    assert '获取Demo日志失败' in app.log_text.get('1.0', 'end')
