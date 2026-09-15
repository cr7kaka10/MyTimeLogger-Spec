# -*- coding: utf-8 -*-
"""轻量级同步信号。"""


class Signal:
    """最小 Qt-like signal，用于无 GUI 环境中的回调通知。"""

    def __init__(self):
        self._callbacks = []

    def connect(self, callback):
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def disconnect(self, callback):
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def emit(self, *args, **kwargs):
        for callback in list(self._callbacks):
            callback(*args, **kwargs)
