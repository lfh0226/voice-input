"""IBus engine 进程入口 - 由 ibus-daemon 通过 component XML 拉起."""

import gi

gi.require_version("IBus", "1.0")

from gi.repository import IBus  # noqa: E402

from voice_input.ibus_engine.engine import VoiceEngine  # noqa: E402


def main():
    IBus.init()
    bus = IBus.Bus()
    if not bus.is_connected():
        print("无法连接 ibus-daemon", flush=True)
        return 1

    factory = IBus.Factory(bus=bus)
    factory.add_engine("voice-input", VoiceEngine)

    bus.request_name("org.freedesktop.IBus.VoiceInput", 0)

    loop = GLib.MainLoop()
    loop.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

