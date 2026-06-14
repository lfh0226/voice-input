"""Tests for Xunfei WebSocket streamer behavior without real network calls."""

from __future__ import annotations

import json
import time

from voice_input.recognizer.xunfei import XunfeiStreamer


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.close_calls = 0

    def send(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    def close(self) -> None:
        self.close_calls += 1


def make_streamer() -> XunfeiStreamer:
    return XunfeiStreamer(
        app_id="test_app_id",
        api_key="test_api_key",
        api_secret="test_api_secret",
    )


def test_send_first_frame_uses_websocket_api_shape() -> None:
    streamer = make_streamer()
    ws = FakeWebSocket()

    streamer._ws = ws
    streamer._connected = True
    streamer._send_first_frame()

    frame = ws.sent[0]
    assert frame["common"]["app_id"] == "test_app_id"
    assert frame["business"]["domain"] == "iat"
    assert frame["business"]["dwa"] == "wpgs"
    assert frame["data"]["status"] == 0


def test_stop_can_keep_connection_open() -> None:
    streamer = make_streamer()
    ws = FakeWebSocket()
    streamer._ws = ws
    streamer._connected = True
    streamer._running = True
    streamer._user_stopped = False
    streamer._server_final = True
    streamer._result_text = "ok"

    assert streamer.stop(close_connection=False) == "ok"

    assert ws.close_calls == 0
    assert streamer._connected is True
    assert streamer._running is False


def test_stop_closes_connection_by_default() -> None:
    streamer = make_streamer()
    ws = FakeWebSocket()
    streamer._ws = ws
    streamer._connected = True
    streamer._running = True
    streamer._user_stopped = False
    streamer._server_final = True

    streamer.stop()

    assert ws.close_calls == 1
    assert streamer._connected is False


def test_stop_respects_short_final_result_timeout() -> None:
    streamer = make_streamer()
    ws = FakeWebSocket()
    streamer._ws = ws
    streamer._connected = True
    streamer._running = True
    streamer._user_stopped = False

    started_at = time.monotonic()
    streamer.stop(close_connection=False, final_result_timeout=0.01)

    assert time.monotonic() - started_at < 0.5
    assert ws.close_calls == 0


def test_cleanup_is_idempotent_and_closes_connection() -> None:
    streamer = make_streamer()
    ws = FakeWebSocket()
    streamer._ws = ws
    streamer._connected = True
    streamer._running = True

    streamer.cleanup()
    streamer.cleanup()

    assert ws.close_calls == 1
    assert streamer._connected is False
    assert streamer._running is False
    assert streamer._ws is None
