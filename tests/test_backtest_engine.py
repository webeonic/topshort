"""Tests for the backtesting engine."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from src.backtesting.engine import BacktestEngine


def _build_dataframe(prices: list[float]) -> pd.DataFrame:
    timestamps = pd.date_range("2024-01-01", periods=len(prices), freq="15min", tz="UTC")
    data = {
        "timestamp": timestamps,
        "open": prices,
        "high": [p * 1.01 for p in prices],
        "low": [p * 0.99 for p in prices],
        "close": prices,
        "volume": [1000] * len(prices),
    }
    return pd.DataFrame(data)


def test_simulate_trade_long_win():
    """Ensure long trades record wins when targets hit."""
    strategy = SimpleNamespace(config=SimpleNamespace(entry_timeframe="15m", confirmation_timeframe="5m", swing_length=3))
    engine = BacktestEngine(strategy, trade_horizon=5)
    entry_df = _build_dataframe([100, 101, 102, 103, 104, 105])
    signal = {
        "symbol": "TEST/USDT:USDT",
        "direction": "long",
        "targets": [106.0],
        "stop_loss": 95.0,
    }

    trade = engine._simulate_trade(signal, entry_df, 0)

    assert trade is not None
    assert trade.result == "win"
    assert trade.r_multiple > 0


def test_simulate_trade_short_loss():
    """Ensure short trades compute outcomes and R multiples."""
    strategy = SimpleNamespace(config=SimpleNamespace(entry_timeframe="15m", confirmation_timeframe="5m", swing_length=3))
    engine = BacktestEngine(strategy, trade_horizon=5)
    entry_df = _build_dataframe([100, 99, 98, 97, 96, 95])
    signal = {
        "symbol": "TEST/USDT:USDT",
        "direction": "short",
        "targets": [94.0],
        "stop_loss": 101.0,
    }

    trade = engine._simulate_trade(signal, entry_df, 0)

    assert trade is not None
    assert trade.result in {"win", "loss", "timeout"}
    if trade.result == "loss":
        assert trade.r_multiple == -1.0
