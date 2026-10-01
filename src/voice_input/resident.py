"""Resident listening session relay.

The relay keeps one prepared ASR session available while another one is being
finalized.  This turns "connect after the user starts speaking" into "queue
audio while the connection completes", which removes first-utterance startup
latency without losing audio.
"""

from __future__ import annotations

import logging
import threading
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
    ) -> None:
        if final_result_timeout < 0:
            raise ValueError("final_result_timeout must be non-negative")
        self._create_session = create_session
        self._on_result = on_result
        self._on_final = on_final
        self._final_result_timeout = final_result_timeout
        self._reuse_connection = reuse_connection

        self._lock = threading.RLock()
        self._session: object | None = None
        self._starting: set[object] = set()
        self._workers: list[threading.Thread] = []
        self._stopped = False

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

    def stop(self) -> None:
        """Stop accepting sessions and clean up the active one."""
        with self._lock:
            self._stopped = True
            sessions = [self._session]
            self._session = None
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
