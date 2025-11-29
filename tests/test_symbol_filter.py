"""Tests for SymbolPreFilter - critical for scan performance optimization."""

import pytest

from src.exchange.symbol_filter import SymbolPreFilter


class TestSymbolPreFilterBasics:
    """Basic functionality tests for SymbolPreFilter."""

    def test_filter_excludes_low_change_symbols(self):
        """Symbols with low 24h change should be filtered out."""
        pre_filter = SymbolPreFilter(min_24h_change_pct=10.0, min_volume_usdt=0)
        tickers = {
            "BTC/USDT:USDT": {"percentage": 5.0, "quoteVolume": 1000000},
            "ETH/USDT:USDT": {"percentage": 15.0, "quoteVolume": 1000000},
            "SOL/USDT:USDT": {"percentage": -20.0, "quoteVolume": 1000000},  # Negative but abs > 10
        }

        result = pre_filter.filter_for_pump_scan(
            symbols=["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"],
            tickers=tickers,
            pump_threshold_pct=30.0,
        )

        # BTC should be filtered (5% < 10%)
        # ETH and SOL should pass (15% and abs(-20%) > 10%)
        assert "BTC/USDT:USDT" not in result
        assert "ETH/USDT:USDT" in result
        assert "SOL/USDT:USDT" in result

    def test_filter_excludes_low_volume_symbols(self):
        """Symbols with low volume should be filtered out."""
        pre_filter = SymbolPreFilter(min_24h_change_pct=0, min_volume_usdt=100000)
        tickers = {
            "BTC/USDT:USDT": {"percentage": 20.0, "quoteVolume": 50000},
            "ETH/USDT:USDT": {"percentage": 20.0, "quoteVolume": 200000},
        }

        result = pre_filter.filter_for_pump_scan(
            symbols=["BTC/USDT:USDT", "ETH/USDT:USDT"],
            tickers=tickers,
            pump_threshold_pct=30.0,
        )

        # BTC should be filtered (50000 < 100000)
        assert "BTC/USDT:USDT" not in result
        assert "ETH/USDT:USDT" in result

    def test_filter_uses_pump_threshold_for_quick_filter(self):
        """Quick threshold should be max(min_change, pump_threshold/3)."""
        # With min_change=5% and pump_threshold=30%, quick_threshold = max(5, 30/3) = 10%
        pre_filter = SymbolPreFilter(min_24h_change_pct=5.0, min_volume_usdt=0)
        tickers = {
            "SYM1": {"percentage": 6.0, "quoteVolume": 1000000},  # 6% < 10% (pump_threshold/3)
            "SYM2": {"percentage": 12.0, "quoteVolume": 1000000},  # 12% > 10%
        }

        result = pre_filter.filter_for_pump_scan(
            symbols=["SYM1", "SYM2"],
            tickers=tickers,
            pump_threshold_pct=30.0,
        )

        # SYM1 should be filtered (6% < 10%)
        assert "SYM1" not in result
        assert "SYM2" in result

    def test_filter_handles_missing_tickers(self):
        """Symbols without ticker data should be filtered out."""
        pre_filter = SymbolPreFilter(min_24h_change_pct=10.0, min_volume_usdt=0)
        tickers = {
            "BTC/USDT:USDT": {"percentage": 20.0, "quoteVolume": 1000000},
        }

        result = pre_filter.filter_for_pump_scan(
            symbols=["BTC/USDT:USDT", "NONEXISTENT/USDT:USDT"],
            tickers=tickers,
            pump_threshold_pct=30.0,
        )

        assert "BTC/USDT:USDT" in result
        assert "NONEXISTENT/USDT:USDT" not in result

    def test_filter_respects_excluded_symbols(self):
        """Excluded symbols should be skipped regardless of metrics."""
        pre_filter = SymbolPreFilter(min_24h_change_pct=0, min_volume_usdt=0)
        tickers = {
            "BTC/USDT:USDT": {"percentage": 50.0, "quoteVolume": 10000000},
            "ETH/USDT:USDT": {"percentage": 50.0, "quoteVolume": 10000000},
        }

        result = pre_filter.filter_for_pump_scan(
            symbols=["BTC/USDT:USDT", "ETH/USDT:USDT"],
            tickers=tickers,
            pump_threshold_pct=30.0,
            excluded_symbols={"BTC/USDT:USDT"},
        )

        # BTC should be excluded even though it passes all thresholds
        assert "BTC/USDT:USDT" not in result
        assert "ETH/USDT:USDT" in result


class TestSymbolPreFilterEdgeCases:
    """Edge case tests for SymbolPreFilter."""

    def test_filter_empty_symbols_list(self):
        """Empty symbols list should return empty result."""
        pre_filter = SymbolPreFilter()
        result = pre_filter.filter_for_pump_scan(
            symbols=[],
            tickers={},
            pump_threshold_pct=30.0,
        )
        assert result == []

    def test_filter_empty_tickers(self):
        """Empty tickers should filter out all symbols."""
        pre_filter = SymbolPreFilter()
        result = pre_filter.filter_for_pump_scan(
            symbols=["BTC/USDT:USDT", "ETH/USDT:USDT"],
            tickers={},
            pump_threshold_pct=30.0,
        )
        assert result == []

    def test_filter_handles_none_percentage(self):
        """None percentage should be treated as 0."""
        pre_filter = SymbolPreFilter(min_24h_change_pct=10.0, min_volume_usdt=0)
        tickers = {
            "BTC/USDT:USDT": {"percentage": None, "quoteVolume": 1000000},
            "ETH/USDT:USDT": {"percentage": 20.0, "quoteVolume": 1000000},
        }

        result = pre_filter.filter_for_pump_scan(
            symbols=["BTC/USDT:USDT", "ETH/USDT:USDT"],
            tickers=tickers,
            pump_threshold_pct=30.0,
        )

        # BTC with None percentage (treated as 0) should be filtered
        assert "BTC/USDT:USDT" not in result
        assert "ETH/USDT:USDT" in result

    def test_filter_handles_none_volume(self):
        """None volume should be treated as 0."""
        pre_filter = SymbolPreFilter(min_24h_change_pct=0, min_volume_usdt=100000)
        tickers = {
            "BTC/USDT:USDT": {"percentage": 20.0, "quoteVolume": None},
            "ETH/USDT:USDT": {"percentage": 20.0, "quoteVolume": 200000},
        }

        result = pre_filter.filter_for_pump_scan(
            symbols=["BTC/USDT:USDT", "ETH/USDT:USDT"],
            tickers=tickers,
            pump_threshold_pct=30.0,
        )

        # BTC with None volume (treated as 0) should be filtered
        assert "BTC/USDT:USDT" not in result
        assert "ETH/USDT:USDT" in result

    def test_filter_preserves_order(self):
        """Filtered result should maintain original symbol order."""
        pre_filter = SymbolPreFilter(min_24h_change_pct=10.0, min_volume_usdt=0)
        tickers = {
            "A/USDT:USDT": {"percentage": 20.0, "quoteVolume": 1000000},
            "B/USDT:USDT": {"percentage": 5.0, "quoteVolume": 1000000},  # Will be filtered
            "C/USDT:USDT": {"percentage": 30.0, "quoteVolume": 1000000},
            "D/USDT:USDT": {"percentage": 25.0, "quoteVolume": 1000000},
        }

        result = pre_filter.filter_for_pump_scan(
            symbols=["A/USDT:USDT", "B/USDT:USDT", "C/USDT:USDT", "D/USDT:USDT"],
            tickers=tickers,
            pump_threshold_pct=30.0,
        )

        # Order should be preserved (A, C, D - without B)
        assert result == ["A/USDT:USDT", "C/USDT:USDT", "D/USDT:USDT"]


class TestSymbolPreFilterActiveSymbols:
    """Tests for filter_active_symbols method."""

    def test_filter_active_by_volume(self):
        """Should filter symbols by volume only."""
        pre_filter = SymbolPreFilter(min_volume_usdt=100000)
        tickers = {
            "BTC/USDT:USDT": {"quoteVolume": 200000},
            "ETH/USDT:USDT": {"quoteVolume": 50000},
            "SOL/USDT:USDT": {"quoteVolume": 150000},
        }

        result = pre_filter.filter_active_symbols(
            symbols=["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"],
            tickers=tickers,
        )

        assert "BTC/USDT:USDT" in result
        assert "ETH/USDT:USDT" not in result  # Below volume threshold
        assert "SOL/USDT:USDT" in result

    def test_filter_active_empty_input(self):
        """Empty input should return empty result."""
        pre_filter = SymbolPreFilter()
        result = pre_filter.filter_active_symbols(symbols=[], tickers={})
        assert result == []


class TestSymbolPreFilterRealisticScenario:
    """Realistic scenario tests simulating production usage."""

    def test_realistic_filtering_reduces_symbols(self):
        """Simulate realistic pre-filtering of ~500 symbols."""
        pre_filter = SymbolPreFilter(min_24h_change_pct=10.0, min_volume_usdt=100000)

        # Generate 500 symbols with varied metrics
        symbols = [f"SYM{i}/USDT:USDT" for i in range(500)]
        tickers = {}
        for i, symbol in enumerate(symbols):
            # ~20% of symbols have high change (>10%)
            # ~60% of symbols have good volume (>100k)
            # So ~12% should pass both filters
            tickers[symbol] = {
                "percentage": 15.0 if i % 5 == 0 else 3.0,  # 20% with high change
                "quoteVolume": 200000 if i % 100 < 60 else 50000,  # 60% with good volume
            }

        result = pre_filter.filter_for_pump_scan(
            symbols=symbols,
            tickers=tickers,
            pump_threshold_pct=30.0,
        )

        # Should significantly reduce the number of symbols
        assert len(result) < len(symbols)
        # But shouldn't filter everything
        assert len(result) > 0
        # Rough expectation: ~12% pass (20% high change * 60% good volume)
        assert len(result) < 100  # Should be around 60
