# -*- coding: utf-8 -*-
"""轻量级一次性计时器。"""

import threading
import time


class SimpleTimer:
    """提供类似 QTimer 的 start/stop/isActive/remainingTime 接口。"""

    def __init__(self, callback=None):
        self.callback = callback
        self._timer = None
        self._deadline = None
        self._lock = threading.Lock()

    def start(self, milliseconds: int):
        self.stop()
        delay = max(milliseconds, 0) / 1000.0
        with self._lock:
            self._deadline = time.monotonic() + delay
            self._timer = threading.Timer(delay, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self):
        callback = None
        with self._lock:
            callback = self.callback
            self._timer = None
            self._deadline = None
        if callback:
            callback()

    def stop(self):
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = None
            self._deadline = None

    def isActive(self) -> bool:
        with self._lock:
            return self._timer is not None

    def remainingTime(self) -> int:
        with self._lock:
            if self._deadline is None:
                return 0
            return max(0, int((self._deadline - time.monotonic()) * 1000))
