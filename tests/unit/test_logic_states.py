# -*- coding: utf-8 -*-
"""
核心逻辑层状态机单元测试（5 个用例）
不依赖 Qt，使用纯 Python Signal + SimpleTimer。
"""
import time
import pytest
from server.utils.signal_bus import Signal
from server.utils.simple_timer import SimpleTimer


# ---- Signal 测试 ----

def test_signal_emit_triggers_callback():
    """Signal.emit 应触发已连接的回调"""
    results = []
    sig = Signal()
    sig.connect(lambda x: results.append(x))
    sig.emit(42)
    assert results == [42]


def test_signal_disconnect():
    """disconnect 后回调不再触发"""
    results = []
    sig = Signal()

    def cb(x):
        results.append(x)

    sig.connect(cb)
    sig.disconnect(cb)
    sig.emit(99)
    assert results == []


# ---- SimpleTimer 测试 ----

def test_simple_timer_is_active():
    """start 后 isActive 应为 True"""
    t = SimpleTimer()
    t.start(5000)  # 5 秒，不会在测试期间触发
    assert t.isActive()
    t.stop()


def test_simple_timer_stop():
    """stop 后 isActive 应为 False"""
    t = SimpleTimer()
    t.start(5000)
    t.stop()
    assert not t.isActive()


def test_simple_timer_remaining_time():
    """remainingTime 应在 start 后返回正值"""
    t = SimpleTimer()
    t.start(5000)
    remaining = t.remainingTime()
    t.stop()
    assert remaining > 0
    assert remaining <= 5000
