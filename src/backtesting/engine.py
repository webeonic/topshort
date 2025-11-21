"""Offline backtesting utilities for Order Block Breakout strategy."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from ..strategy.order_block_breakout import OrderBlockBreakoutStrategy, OrderBlockSignal

logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    symbol: str
    direction: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    stop_loss: float
    target_price: float
    result: str  # win | loss | timeout
    r_multiple: float


class BacktestEngine:
    """Simple backtesting engine for Order Block Breakout strategy."""

    def __init__(
        self,
        strategy: OrderBlockBreakoutStrategy,
        *,
        max_candles: int = 1200,
        trade_horizon: int = 150,
    ):
        self.strategy = strategy
        self.max_candles = max_candles
        self.trade_horizon = trade_horizon

    def run(self, symbols: List[str], max_trades: Optional[int] = None) -> Dict:
        """Run backtest for provided symbols."""
        trades: List[BacktestTrade] = []

        for symbol in symbols:
            datasets = self.strategy._load_timeframes(symbol)  # type: ignore[attr-defined]
            if not datasets or self.strategy.config.entry_timeframe not in datasets:
                logger.warning(f"Skipping {symbol} - insufficient data for backtest")
                continue

            entry_df = datasets[self.strategy.config.entry_timeframe].tail(self.max_candles)
            min_index = self.strategy.config.swing_length * 3

            for idx in range(min_index, len(entry_df) - self.trade_horizon):
                timestamp = entry_df["timestamp"].iloc[idx]
                truncated = self._truncate_datasets(datasets, timestamp)
                signal = self.strategy.analyze_from_datasets(symbol, truncated)
                if not signal.get("meets_criteria"):
                    continue

                trade = self._simulate_trade(signal, entry_df, idx)
                if trade:
                    trades.append(trade)
                    if max_trades and len(trades) >= max_trades:
                        break

            if max_trades and len(trades) >= max_trades:
                break

        stats = self._summarize(trades)
        return {"trades": trades, "stats": stats}

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _truncate_datasets(self, datasets: Dict[str, pd.DataFrame], timestamp: pd.Timestamp) -> Dict[str, pd.DataFrame]:
        truncated = {}
        for tf, df in datasets.items():
            subset = df[df["timestamp"] <= timestamp]
            if len(subset) >= self.strategy.config.swing_length * 3:
                truncated[tf] = subset.copy()
        return truncated

    def _simulate_trade(self, signal: OrderBlockSignal, entry_df: pd.DataFrame, signal_index: int) -> Optional[BacktestTrade]:
        direction = signal.get("direction", "short")
        entry_idx = min(signal_index + 1, len(entry_df) - 1)
        entry_price = float(entry_df["open"].iloc[entry_idx])
        stop_loss = float(signal.get("stop_loss") or self._default_stop(entry_price, direction))
        targets = signal.get("targets") or []
        target_price = float(targets[0]) if targets else self._default_target(entry_price, direction)
        risk = abs(entry_price - stop_loss) or 1e-6

        horizon = min(entry_idx + self.trade_horizon, len(entry_df) - 1)
        for future_idx in range(entry_idx, horizon + 1):
            candle = entry_df.iloc[future_idx]
            high = candle["high"]
            low = candle["low"]
            timestamp = candle["timestamp"].to_pydatetime()

            if direction == "long":
                if low <= stop_loss:
                    return BacktestTrade(
                        signal["symbol"],
                        direction,
                        entry_df["timestamp"].iloc[entry_idx].to_pydatetime(),
                        timestamp,
                        entry_price,
                        stop_loss,
                        stop_loss,
                        target_price,
                        "loss",
                        -1.0,
                    )
                if high >= target_price:
                    reward = target_price - entry_price
                    r_multiple = reward / risk
                    return BacktestTrade(
                        signal["symbol"],
                        direction,
                        entry_df["timestamp"].iloc[entry_idx].to_pydatetime(),
                        timestamp,
                        entry_price,
                        target_price,
                        stop_loss,
                        target_price,
                        "win",
                        r_multiple,
                    )
            else:
                if high >= stop_loss:
                    return BacktestTrade(
                        signal["symbol"],
                        direction,
                        entry_df["timestamp"].iloc[entry_idx].to_pydatetime(),
                        timestamp,
                        entry_price,
                        stop_loss,
                        stop_loss,
                        target_price,
                        "loss",
                        -1.0,
                    )
                if low <= target_price:
                    reward = entry_price - target_price
                    r_multiple = reward / risk
                    return BacktestTrade(
                        signal["symbol"],
                        direction,
                        entry_df["timestamp"].iloc[entry_idx].to_pydatetime(),
                        timestamp,
                        entry_price,
                        target_price,
                        stop_loss,
                        target_price,
                        "win",
                        r_multiple,
                    )

        exit_idx = horizon
        exit_price = float(entry_df["close"].iloc[exit_idx])
        pnl = (exit_price - entry_price) if direction == "long" else (entry_price - exit_price)
        r_multiple = pnl / risk
        return BacktestTrade(
            signal["symbol"],
            direction,
            entry_df["timestamp"].iloc[entry_idx].to_pydatetime(),
            entry_df["timestamp"].iloc[exit_idx].to_pydatetime(),
            entry_price,
            exit_price,
            stop_loss,
            target_price,
            "timeout",
            r_multiple,
        )

    def _default_stop(self, entry_price: float, direction: str) -> float:
        buffer = 0.01  # 1%
        if direction == "long":
            return entry_price * (1 - buffer)
        return entry_price * (1 + buffer)

    def _default_target(self, entry_price: float, direction: str) -> float:
        reward = 0.02  # 2%
        if direction == "long":
            return entry_price * (1 + reward)
        return entry_price * (1 - reward)

    def _summarize(self, trades: List[BacktestTrade]) -> Dict:
        if not trades:
            return {"total_trades": 0, "win_rate": 0.0, "expectancy": 0.0, "profit_factor": 0.0, "max_drawdown": 0.0}

        total = len(trades)
        wins = [t for t in trades if t.result == "win"]
        losses = [t for t in trades if t.result == "loss"]

        win_rate = len(wins) / total * 100
        expectancy = sum(t.r_multiple for t in trades) / total

        gross_profit = sum(max(t.r_multiple, 0) for t in trades)
        gross_loss = abs(sum(min(t.r_multiple, 0) for t in trades))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

        max_dd = self._max_drawdown(trades)

        return {
            "total_trades": total,
            "win_rate": round(win_rate, 2),
            "expectancy": round(expectancy, 3),
            "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else float("inf"),
            "max_drawdown": round(max_dd, 2),
        }

    @staticmethod
    def _max_drawdown(trades: List[BacktestTrade]) -> float:
        equity = 0.0
        peak = 0.0
        max_dd = 0.0

        for trade in trades:
            equity += trade.r_multiple
            peak = max(peak, equity)
            drawdown = peak - equity
            max_dd = max(max_dd, drawdown)
        return max_dd


__all__ = ["BacktestEngine", "BacktestTrade"]
