"""毫秒级全链路时间线日志.

每个关键环节一条记录,格式: [T+秒.毫秒] 事件(相对本次按键按下).
文件: ~/.local/state/voice-input/timeline.log
开关: config.yaml → logging.timeline(默认 true)
"""

import logging
import os
import time
from typing import Optional


class Timeline:
    def __init__(self) -> None:
        self._t0 = time.perf_counter()
        self._logger = logging.getLogger("voice_input.timeline")
        self._logger.propagate = False
        self._logger.setLevel(logging.INFO)
        self._handler_added = False

    def use_file(self, path: str) -> None:
        """绑定时间线日志文件(幂等)."""
        if self._handler_added:
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        handler = logging.FileHandler(path)
        handler.setFormatter(
            logging.Formatter("%(asctime)s.%(msecs)03d | %(message)s", datefmt="%H:%M:%S")
        )
        self._logger.addHandler(handler)
        self._handler_added = True

    def set_enabled(self, enabled: bool) -> None:
        self._logger.setLevel(logging.INFO if enabled else logging.CRITICAL)

    def reset(self, label: str = "") -> None:
        """重置 T0(每次按键按下时调用)."""
        self._t0 = time.perf_counter()
        if label:
            self.mark(f"—— {label} ——")

    def mark(self, msg: str) -> None:
        self._logger.info("[T+%7.3fs] %s", time.perf_counter() - self._t0, msg)


timeline = Timeline()
