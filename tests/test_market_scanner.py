"""Unit tests for the MarketScanner helper logic."""

from types import SimpleNamespace
from unittest.mock import ANY, MagicMock

import pytest

from src.strategy.scanner import MarketScanner


def _build_scanner(order_block: bool = True, top_pairs: list | None = None):
    market_data = MagicMock()
    market_data.client.get_usdt_perpetual_symbols.return_value = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    market_data.scan_market.return_value = [
        {"symbol": "BTCUSDT", "score": 95.0, "price_change_pct": 12.3, "volume_change_pct": 40.0}
    ]

    config = SimpleNamespace(
        pump_threshold_pct=15.0,
        pump_period_hours_min=1,
        pump_period_hours_max=6,
        cooldown_period_hours_min=1,
        cooldown_period_hours_max=4,
        volume_decrease_threshold_pct=20.0,
    )

    top_pairs_service = MagicMock()
    top_pairs_service.get_pairs.return_value = top_pairs or ["ADAUSDT", "XRPUSDT", "BNBUSDT"]

    order_block_strategy = MagicMock() if order_block else None
    if order_block_strategy:
        order_block_strategy.scan.return_value = [{"symbol": "ADAUSDT", "direction": "short"}]

    scanner = MarketScanner(
        market_data=market_data,
        config=config,
        top_pairs_service=top_pairs_service,
        order_block_strategy=order_block_strategy,
    )
    scanner.detector = MagicMock()
    return scanner, market_data, top_pairs_service, order_block_strategy


def test_get_order_block_universe_limits_results():
    """Order block universe honors the optional limit."""
    scanner, _, top_pairs_service, _ = _build_scanner(top_pairs=[f"SYM{i}" for i in range(20)])

    subset = scanner.get_order_block_universe(limit=5)

    top_pairs_service.get_pairs.assert_called_once()
    assert subset == ["SYM0", "SYM1", "SYM2", "SYM3", "SYM4"]


def test_scan_routes_to_pump_mode():
    """Default scan path uses pump/cooldown detector."""
    scanner, market_data, _, _ = _build_scanner()

    results = scanner.scan(top_n=1, symbols=["BTCUSDT"])

    market_data.scan_market.assert_called_once()
    assert results[0]["symbol"] == "BTCUSDT"


def test_scan_routes_to_order_block_mode():
    """Order block mode delegates to the configured strategy."""
    scanner, _, _, order_block_strategy = _build_scanner()

    results = scanner.scan(top_n=2, strategy_mode="order_block", progress_callback=None)

    order_block_strategy.scan.assert_called_once()
    assert results == order_block_strategy.scan.return_value


def test_scan_order_block_raises_without_strategy():
    """Missing order block strategy should raise an error."""
    scanner, _, _, _ = _build_scanner(order_block=False)

    with pytest.raises(ValueError):
        scanner.scan(strategy_mode="order_block")


def test_scan_order_block_uses_universe_when_symbols_missing():
    """Order block scans compute their own universe when symbols absent."""
    scanner, _, _, order_block_strategy = _build_scanner()
    scanner.get_order_block_universe = MagicMock(return_value=["BTCUSDT"])

    scanner.scan(strategy_mode="order_block")

    scanner.get_order_block_universe.assert_called_once()
    order_block_strategy.scan.assert_called_once()
    _, kwargs = order_block_strategy.scan.call_args
    assert kwargs["symbols"] == ["BTCUSDT"]
    assert kwargs["top_n"] == 1
    assert "progress_callback" in kwargs
    assert "max_workers" in kwargs


def test_quick_check_delegates_to_detector():
    """Quick check simply proxies to the pump detector."""
    scanner, _, _, _ = _build_scanner()
    scanner.detector.detect.return_value = {"ok": True}

    assert scanner.quick_check("BTCUSDT") == {"ok": True}
    scanner.detector.detect.assert_called_once_with("BTCUSDT")
