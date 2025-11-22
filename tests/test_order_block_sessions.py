"""Regression tests for OrderBlockBreakout session handling."""

from datetime import time, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.config import SessionWindow
from src.strategy.order_block_breakout import OrderBlockBreakoutStrategy


class _FakeConvertedTimestamp:
    def __init__(self, time_object: time):
        self._time_object = time_object

    def time(self) -> time:
        return self._time_object


class _FakeTimestamp:
    def __init__(self, time_object: time):
        self._converted = _FakeConvertedTimestamp(time_object)

    def tz_convert(self, _tz):
        return self._converted


def _build_strategy() -> OrderBlockBreakoutStrategy:
    config = SimpleNamespace(
        sessions_utc=[SessionWindow(name="Test", start_utc="08:00", end_utc="10:00")],
    )
    return OrderBlockBreakoutStrategy(MagicMock(), config)


def test_is_within_session_handles_timezone_aware_time():
    """Regression: timezone-aware times should not raise TypeError."""
    strategy = _build_strategy()
    aware_time = time(hour=9, minute=0, tzinfo=timezone.utc)

    assert strategy._is_within_session(_FakeTimestamp(aware_time)) is True


def test_is_within_session_handles_naive_time():
    """Naive times continue to work as before."""
    strategy = _build_strategy()
    naive_time = time(hour=5, minute=0)

    assert strategy._is_within_session(_FakeTimestamp(naive_time)) is False
