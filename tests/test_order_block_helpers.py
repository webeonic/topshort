"""Focused unit tests for OrderBlockBreakout helper utilities."""

from datetime import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.config import SessionWindow
from src.strategy.order_block_breakout import OrderBlockBreakoutStrategy, TrendContext


def _make_strategy(**overrides) -> OrderBlockBreakoutStrategy:
    defaults = {
        "atr_stop_multiplier": 1.5,
        "atr_target_multiplier": 2.0,
        "volume_spike_threshold": 2.0,
        "atr_period": 5,
        "sessions_utc": [SessionWindow(name="London", start_utc="08:00", end_utc="10:00")],
    }
    defaults.update(overrides)
    config = SimpleNamespace(**defaults)
    return OrderBlockBreakoutStrategy(MagicMock(), config)


def test_parse_time_returns_naive_time():
    """Ensure _parse_time drops tzinfo and keeps hh:mm."""
    parsed = OrderBlockBreakoutStrategy._parse_time("12:30")

    assert parsed.hour == 12
    assert parsed.minute == 30
    assert parsed.tzinfo is None


def test_is_within_session_handles_overnight_windows():
    """Session filtering must handle windows that wrap midnight."""
    strategy = _make_strategy(sessions_utc=[SessionWindow(name="NY Overnight", start_utc="22:00", end_utc="02:00")])
    ts_inside = pd.Timestamp("2024-01-01T23:30:00Z")
    ts_outside = pd.Timestamp("2024-01-01T12:00:00Z")

    assert strategy._is_within_session(ts_inside) is True
    assert strategy._is_within_session(ts_outside) is False


def test_calculate_stop_respects_direction():
    """Stop calculation should respect trade direction."""
    strategy = _make_strategy()
    order_block = {"low": 95.0, "high": 105.0}

    long_stop = strategy._calculate_stop(entry=100.0, atr=2.0, direction="long", order_block=order_block)
    short_stop = strategy._calculate_stop(entry=100.0, atr=2.0, direction="short", order_block=order_block)

    assert long_stop == pytest.approx(95.0)  # min(low, entry - atr * multiplier)
    assert short_stop == pytest.approx(105.0)  # max(high, entry + atr * multiplier)


def test_calculate_targets_returns_three_levels():
    """Target calculator should always return three levels."""
    strategy = _make_strategy()

    targets_long = strategy._calculate_targets(entry=100.0, atr=2.0, direction="long")
    targets_short = strategy._calculate_targets(entry=100.0, atr=2.0, direction="short")

    assert targets_long == [102.0, 104.0, 106.0]
    assert targets_short == [98.0, 96.0, 94.0]


def test_score_signal_applies_all_components():
    """Scoring should combine structural, volume, and RR components."""
    strategy = _make_strategy(volume_spike_threshold=2.0)
    context = TrendContext(
        bias="bullish",
        higher_timeframe_trend={"4h": "bullish"},
        last_bos_timeframe="4h",
        choch_detected=False,
    )

    score = strategy._score_signal(
        context=context,
        has_fvg=True,
        volume_multiplier=4.0,
        session_match=True,
        rr_ratio=3.0,
    )

    assert score == pytest.approx(100.0)  # Score is clamped at 100


def test_calculate_atr_requires_sufficient_history():
    """ATR should match manual calculation when enough candles exist."""
    strategy = _make_strategy(atr_period=6)
    data = pd.DataFrame(
        {
            "high": [10.0, 12.0, 11.5, 14.0, 15.0, 16.0, 17.0, 18.0, 19.5, 20.0],
            "low": [8.0, 9.5, 9.0, 11.0, 13.5, 14.0, 15.0, 16.5, 17.5, 18.0],
            "close": [9.0, 11.0, 10.5, 13.0, 14.0, 15.5, 16.0, 17.0, 18.5, 19.0],
        }
    )

    expected = (
        pd.concat(
            [
                data["high"] - data["low"],
                (data["high"] - data["close"].shift()).abs(),
                (data["low"] - data["close"].shift()).abs(),
            ],
            axis=1,
        )
        .max(axis=1)
        .rolling(6)
        .mean()
        .iloc[-1]
    )

    assert strategy._calculate_atr(data) == pytest.approx(expected)


def test_calculate_atr_returns_none_for_short_series():
    """ATR returns None when not enough data is provided."""
    strategy = _make_strategy(atr_period=100)
    short_df = pd.DataFrame(
        {
            "high": [10.0, 10.5, 11.0, 11.5],
            "low": [9.0, 9.5, 9.8, 10.5],
            "close": [9.5, 10.0, 10.5, 11.0],
        }
    )

    assert strategy._calculate_atr(short_df) is None
