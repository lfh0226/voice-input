import pytest

from voice_input import hotkey as hotkey_module
from voice_input.hotkey import HotkeyListener


class FakeDevice:
    def __init__(self, name="keyboard", events=None):
        self.name = name
        self.events = events or []
        self.read_calls = 0
        self.closed = False

    def read(self):
        self.read_calls += 1
        return list(self.events)

    def close(self):
        self.closed = True


@pytest.mark.unit
def test_hotkey_listener_waits_for_ready_devices_without_busy_sleep(monkeypatch):
    fake_device = FakeDevice()
    select_calls = []

    listener = HotkeyListener("alt", on_press=lambda: None)
    listener._running = True

    monkeypatch.setattr(listener, "_find_keyboard_devices", lambda: [fake_device])

    def fake_select(devices, _write, _error, timeout):
        select_calls.append((devices, timeout))
        listener._running = False
        return ([], [], [])

    monkeypatch.setattr(hotkey_module.select, "select", fake_select)

    listener._run()

    assert select_calls == [([fake_device], hotkey_module.HOTKEY_POLL_TIMEOUT)]
    assert fake_device.read_calls == 0


@pytest.mark.unit
def test_hotkey_listener_only_reads_ready_devices(monkeypatch):
    ready_event = object()
    ready_device = FakeDevice(name="ready", events=[ready_event])
    idle_device = FakeDevice(name="idle")
    handled_events = []

    listener = HotkeyListener("alt", on_press=lambda: None)
    listener._running = True

    monkeypatch.setattr(listener, "_find_keyboard_devices", lambda: [ready_device, idle_device])

    def fake_select(devices, _write, _error, timeout):
        return ([ready_device], [], [])

    def handle_event(event):
        handled_events.append(event)
        listener._running = False

    monkeypatch.setattr(listener, "_handle_event", handle_event)
    monkeypatch.setattr(hotkey_module.select, "select", fake_select)

    listener._run()

    assert ready_device.read_calls == 1
    assert idle_device.read_calls == 0
    assert handled_events == [ready_event]


@pytest.mark.unit
def test_hotkey_listener_returns_without_waiting_when_no_devices(monkeypatch):
    listener = HotkeyListener("alt", on_press=lambda: None)
    listener._running = True

    monkeypatch.setattr(listener, "_find_keyboard_devices", lambda: [])
    monkeypatch.setattr(
        hotkey_module.select,
        "select",
        lambda *_args, **_kwargs: pytest.fail("select should not be called without devices"),
    )

    listener._run()

    assert listener._devices == []
