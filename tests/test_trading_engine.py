"""Tests for trading engine helpers."""

from concurrent.futures import TimeoutError as FuturesTimeoutError
from unittest.mock import MagicMock, patch

from src.trading.engine import _YIELD_TIMEOUT_SECONDS, TradingEngine


def _engine_with_loop(loop):
    engine = TradingEngine.__new__(TradingEngine)
    engine._async_loop = loop
    return engine


def _fake_sleep(*_args, **_kwargs):
    return "noop"


def test_yield_callback_waits_for_future_result():
    """Ensure yield callback blocks until scheduled sleep completes."""
    loop = object()
    engine = _engine_with_loop(loop)
    future = MagicMock()
    future.result = MagicMock()

    with (
        patch("src.trading.engine.asyncio.sleep", new=_fake_sleep),
        patch("src.trading.engine.asyncio.run_coroutine_threadsafe", return_value=future) as mock_run,
    ):
        yield_cb = engine._get_yield_callback()
        assert yield_cb is not None

        yield_cb()

        mock_run.assert_called_once()
        future.result.assert_called_once_with(timeout=_YIELD_TIMEOUT_SECONDS)


def test_yield_callback_swallows_timeout(caplog):
    """Timeouts should not propagate to blocking threads."""
    loop = object()
    engine = _engine_with_loop(loop)
    future = MagicMock()
    future.result = MagicMock(side_effect=FuturesTimeoutError())

    with (
        patch("src.trading.engine.asyncio.sleep", new=_fake_sleep),
        patch("src.trading.engine.asyncio.run_coroutine_threadsafe", return_value=future),
    ):
        yield_cb = engine._get_yield_callback()
        yield_cb()

    assert any("Yield callback timed out" in message for *_, message in caplog.record_tuples)
