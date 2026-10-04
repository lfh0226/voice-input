"""Resident listening session relay.

The relay keeps one prepared ASR session available while another one is being
finalized.  This turns "connect after the user starts speaking" into "queue
audio while the connection completes", which removes first-utterance startup
latency without losing audio.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

logger = logging.getLogger(__name__)


class ASRSessionRelay:
    """Coordinate hot ASR sessions and background finalization."""

    def __init__(
        self,
        create_session: Callable[[], object],
        on_result: Callable[[str, bool], None],
        on_final: Callable[[str], None],
        final_result_timeout: float = 0.2,
        reuse_connection: bool = True,
        stale_max_age_s: float = 8.0,
    ) -> None:
        if final_result_timeout < 0:
            raise ValueError("final_result_timeout must be non-negative")
        self._create_session = create_session
        self._on_result = on_result
        self._on_final = on_final
        self._final_result_timeout = final_result_timeout
        self._reuse_connection = reuse_connection
        self._stale_max_age_s = stale_max_age_s

        self._lock = threading.RLock()
        self._session: object | None = None
        self._session_created_at: float | None = None
        self._starting: set[object] = set()
        self._workers: list[threading.Thread] = []
        self._stopped = False
        self._stale_timer: threading.Timer | None = None

    @property
    def is_ready(self) -> bool:
        """Whether a session is available for a new segment."""
        with self._lock:
            return self._session is not None and not self._starting

    def warm(self) -> None:
        """Create and start a session in the background."""
        with self._lock:
            if self._stopped or self._session is not None:
                return
            session = self._create_session()
            self._session = session
            self._session_created_at = time.time()
            self._starting.add(session)

        thread = threading.Thread(target=self._start_session, args=(session,), daemon=True)
        self._workers.append(thread)
        thread.start()

    def _start_session(self, session: object) -> None:
        try:
            session.prepare_session()
            ok = session.start()
        except Exception:
            logger.exception("resident ASR session startup failed")
            ok = False

        with self._lock:
            self._starting.discard(session)
            if not ok and self._session is session:
                self._session = None
        if not ok:
            try:
                session.cleanup()
            except Exception:
                logger.debug("failed session cleanup", exc_info=True)
            # 连接失败自动重试一次（防止 warm 失败后 relay 永久死亡）
            if not self._stopped:
                logger.warning("resident ASR session failed, retrying warm...")
                self.warm()
        else:
            # 会话启动成功 → 启动后台过期回收心跳（默认 8s，讯飞 IAT ~10s 空闲踢连接）
            if self._stale_max_age_s > 0:
                self._schedule_stale_check(self._stale_max_age_s)

    def send_audio(self, pcm_bytes: bytes) -> None:
        """Send PCM to the current session if one is active."""
        with self._lock:
            session = self._session
        if session is not None:
            session.send_audio(pcm_bytes)

    def finish_segment(self) -> None:
        """Finalize the current session and immediately warm the next one."""
        with self._lock:
            session = self._session
            self._session = None
        if session is None:
            return

        self.warm()
        thread = threading.Thread(
            target=self._finalize_session,
            args=(session,),
            daemon=True,
        )
        self._workers.append(thread)
        thread.start()

    def _finalize_session(self, session: object) -> None:
        try:
            text = session.stop(
                close_connection=not self._reuse_connection,
                final_result_timeout=self._final_result_timeout,
            )
        except Exception:
            logger.exception("resident ASR session finalization failed")
            try:
                session.cleanup()
            except Exception:
                logger.debug("failed session cleanup", exc_info=True)
            return
        if text:
            self._on_final(text)

    def recycle_if_stale(self, max_age_s: float) -> None:
        """空闲预热会话超过服务器超时后已失效,主动接力新会话."""
        with self._lock:
            session = self._session
            created = self._session_created_at
        if session is None or created is None:
            return
        if time.time() - created <= max_age_s:
            return
        self.finish_segment()  # 后台结束旧会话并立即 warm() 下一个
        return

    def _schedule_stale_check(self, max_age_s: float) -> None:
        """后台定时回收过期预热会话，保证用户按下 Alt 时总有一条热连接。"""
        with self._lock:
            if self._stopped:
                return
            if self._stale_timer:
                self._stale_timer.cancel()

        def _check():
            with self._lock:
                if self._stopped:
                    return
                session = self._session
                created = self._session_created_at
            if session is None or created is None:
                return
            age = time.time() - created
            if age > max_age_s:
                logger.info("预热会话已过期(%.1fs), 后台自动接力新会话", age)
                self.finish_segment()

        timer = threading.Timer(max_age_s, _check)
        timer.daemon = True
        timer.start()
        self._stale_timer = timer

    def start_heartbeat(self) -> None:
        """启动后台过期回收心跳（在应用 start() 后调用一次）。"""
        self._schedule_stale_check(self._stale_max_age_s)

    def stop(self) -> None:
        """Stop accepting sessions and clean up the active one."""
        with self._lock:
            self._stopped = True
            sessions = [self._session]
            self._session = None
            if self._stale_timer:
                self._stale_timer.cancel()
                self._stale_timer = None
        for session in sessions:
            if session is None:
                continue
            try:
                session.cleanup()
            except Exception:
                logger.debug("resident session cleanup failed", exc_info=True)

        workers = list(self._workers)
        self._workers.clear()
        for thread in workers:
            if thread.is_alive():
                thread.join(timeout=1.0)
