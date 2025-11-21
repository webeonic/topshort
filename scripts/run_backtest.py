#!/usr/bin/env python3
"""CLI helper to run Order Block Breakout backtests."""

from __future__ import annotations

import argparse
import json
import sys
from typing import List

from src.backtesting.engine import BacktestEngine
from src.config import load_config
from src.data.top_pairs_service import TopPairsService
from src.exchange.binance_client import BinanceClient
from src.exchange.market_data import MarketData
from src.strategy.order_block_breakout import OrderBlockBreakoutStrategy


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the backtest script."""
    parser = argparse.ArgumentParser(description="Run Order Block Breakout backtest.")
    parser.add_argument(
        "--symbols",
        help="Comma-separated list of symbols (e.g. BTC/USDT:USDT,ETH/USDT:USDT). Overrides --top.",
        default="",
    )
    parser.add_argument("--top", type=int, default=10, help="Use top N symbols from CoinGecko cache (default: 10).")
    parser.add_argument("--max-trades", type=int, default=50, help="Maximum number of trades to simulate.")
    parser.add_argument("--trade-horizon", type=int, default=150, help="Candles to look ahead per trade.")
    return parser.parse_args()


def resolve_symbols(args: argparse.Namespace, client: BinanceClient, config) -> List[str]:
    """Resolve target symbols either from CLI or CoinGecko top list."""
    if args.symbols:
        return [sym.strip() for sym in args.symbols.split(",") if sym.strip()]

    pairs_service = TopPairsService(client, config.pairs)
    return pairs_service.get_pairs()[: args.top]


def main() -> None:
    """Entry point for the backtest CLI."""
    args = parse_args()
    config = load_config()

    if not config.binance.api_key or not config.binance.api_secret:
        print("❌ BINANCE_API_KEY / BINANCE_API_SECRET are required", file=sys.stderr)
        sys.exit(1)

    client = BinanceClient(config.binance.api_key, config.binance.api_secret, testnet=config.binance.testnet)
    symbols = resolve_symbols(args, client, config)

    if not symbols:
        print("❌ No symbols resolved for backtest", file=sys.stderr)
        sys.exit(1)

    market_data = MarketData(client)
    strategy = OrderBlockBreakoutStrategy(market_data, config.order_block_strategy)
    engine = BacktestEngine(strategy, trade_horizon=args.trade_horizon)

    result = engine.run(symbols, max_trades=args.max_trades)

    print("=== Backtest Summary ===")
    for key, value in result["stats"].items():
        print(f"{key:>15}: {value}")

    print("\n=== Sample Trades ===")
    for trade in result["trades"][:10]:
        print(
            f"{trade.symbol} {trade.direction.upper()} "
            f"{trade.entry_time.isoformat()} -> {trade.exit_time.isoformat()} "
            f"{trade.result.upper()} R={trade.r_multiple:.2f}"
        )

    # Save trades to JSON for further analysis
    output_path = "backtest_trades.json"
    with open(output_path, "w", encoding="utf-8") as fp:
        json.dump(
            [
                {
                    "symbol": t.symbol,
                    "direction": t.direction,
                    "entry_time": t.entry_time.isoformat(),
                    "exit_time": t.exit_time.isoformat(),
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "stop_loss": t.stop_loss,
                    "target_price": t.target_price,
                    "result": t.result,
                    "r_multiple": t.r_multiple,
                }
                for t in result["trades"]
            ],
            fp,
            indent=2,
        )
    print(f"\nSaved detailed trades to {output_path}")


if __name__ == "__main__":
    main()
