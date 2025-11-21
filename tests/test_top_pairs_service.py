"""Tests for the TopPairsService."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.config import PairsConfig
from src.data.top_pairs_service import TopPairsService


class StubBinanceClient:
    def __init__(self, symbols):
        self._symbols = symbols
        self.calls = 0

    def get_usdt_perpetual_symbols(self):
        """Return mocked list of perpetual symbols."""
        self.calls += 1
        return list(self._symbols)


def make_pairs_config(tmp_path: Path) -> PairsConfig:
    """Create a temporary pairs config for tests."""
    return PairsConfig(
        top_n=5,
        cache_path=str(tmp_path / "top_pairs_cache.json"),
        refresh_interval_hours=24,
        coingecko_url="https://api.coingecko.com/api/v3/coins/markets",
        coingecko_vs_currency="usd",
        coingecko_order="market_cap_desc",
        http_timeout_seconds=5,
        fallback_pairs=["BTC/USDT:USDT", "ETH/USDT:USDT"],
    )


def test_refresh_uses_coingecko_data(monkeypatch, tmp_path):
    """Ensure service refreshes from CoinGecko data."""
    client = StubBinanceClient(["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"])
    config = make_pairs_config(tmp_path)
    service = TopPairsService(client, config)

    coins = [
        {"symbol": "btc", "id": "bitcoin", "name": "Bitcoin"},
        {"symbol": "eth", "id": "ethereum", "name": "Ethereum"},
        {"symbol": "sol", "id": "solana", "name": "Solana"},
    ]

    monkeypatch.setattr(TopPairsService, "_fetch_top_coins", lambda self: coins)

    refreshed = service.refresh()
    assert refreshed[:3] == ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]

    meta = service.get_metadata()
    assert meta["source"] == "coingecko"
    assert meta["count"] == len(refreshed)

    # Ensure cache is persisted and reused
    service_reloaded = TopPairsService(client, config)
    assert service_reloaded.get_pairs() == refreshed
    assert service_reloaded.get_metadata()["source"] == "coingecko"


def test_fallback_used_when_no_remote_data(monkeypatch, tmp_path):
    """Ensure fallback list is used when CoinGecko returns nothing."""
    client = StubBinanceClient(["XRP/USDT:USDT"])
    config = make_pairs_config(tmp_path)
    service = TopPairsService(client, config)

    monkeypatch.setattr(TopPairsService, "_fetch_top_coins", lambda self: [])

    pairs = service.get_pairs(force_refresh=True)
    assert pairs == config.fallback_pairs
    assert service.get_metadata()["source"] == "fallback"


def test_cache_becomes_stale_and_refreshes(monkeypatch, tmp_path):
    """Ensure cache refreshes after staleness threshold."""
    client = StubBinanceClient(["BTC/USDT:USDT"])
    config = make_pairs_config(tmp_path)
    service = TopPairsService(client, config)

    monkeypatch.setattr(TopPairsService, "_fetch_top_coins", lambda self: [{"symbol": "btc"}])

    service.refresh()
    assert client.calls == 1

    # Force cache to become stale
    service._last_updated = datetime.now(timezone.utc) - timedelta(hours=48)

    service.get_pairs()
    assert client.calls == 2  # fetch symbols called again after refresh
