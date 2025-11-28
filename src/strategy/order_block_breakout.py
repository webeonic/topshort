"""Order Block Breakout with FVG confirmation strategy."""

from __future__ import annotations

import logging
import math
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Callable, Dict, List, Optional, TypedDict

import pandas as pd

from ..config import OrderBlockStrategyConfig, SessionWindow
from ..exchange.market_data import MarketData

logger = logging.getLogger(__name__)

TIMEFRAME_TO_MINUTES = {
    "1m": 1,
    "3m": 3,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "4h": 240,
    "6h": 360,
    "8h": 480,
    "12h": 720,
    "1d": 1440,
}

MAX_CANDLES_PER_REQUEST = 1500
TIMEFRAME_WORKER_CAP = 16

# Minimum TP distance as percentage of entry price to cover trading fees
MIN_TP_PERCENT = 0.1  # 0.1% minimum to cover ~0.06% round-trip fees + buffer


class OrderBlockSignal(TypedDict, total=False):
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    targets: List[float]
    rr_ratio: float
    confidence: float
    timeframe_notes: Dict[str, str]
    meets_criteria: bool
    reason: str
    score: float
    session_match: bool
    indicator_context: Dict[str, str]
    metadata: Dict[str, float]


@dataclass
class TrendContext:
    bias: str
    higher_timeframe_trend: Dict[str, str]
    last_bos_timeframe: Optional[str]
    choch_detected: bool


class OrderBlockBreakoutStrategy:
    """SMC-inspired strategy for detecting order block breakouts with FVG confirmation."""

    def __init__(self, market_data: MarketData, config: OrderBlockStrategyConfig):
        self.market_data = market_data
        self.config = config

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def analyze(self, symbol: str) -> OrderBlockSignal:
        """Analyze a single symbol and return signal data."""
        try:
            tf_data = self._load_timeframes(symbol)
            if not tf_data:
                return self._invalid(symbol, "Insufficient OHLCV data")
            return self.analyze_from_datasets(symbol, tf_data)
        except Exception as exc:
            logger.error(f"Error analyzing {symbol} with OrderBlock strategy: {exc}", exc_info=True)
            return self._invalid(symbol, f"Exception: {exc}")

    def analyze_from_datasets(self, symbol: str, datasets: Dict[str, pd.DataFrame]) -> OrderBlockSignal:
        """Analyze symbol using pre-loaded timeframe datasets (useful for backtests)."""
        try:
            if self.config.entry_timeframe not in datasets or self.config.confirmation_timeframe not in datasets:
                return self._invalid(symbol, "Missing entry or confirmation timeframe data")

            context = self._evaluate_trend(datasets)
            if context.bias == "neutral":
                return self._invalid(symbol, "No clear higher timeframe bias")

            direction = "long" if context.bias == "bullish" else "short"
            entry_tf_df = datasets[self.config.entry_timeframe]
            confirmation_df = datasets[self.config.confirmation_timeframe]

            order_block = self._find_order_block(entry_tf_df, direction)
            if not order_block:
                return self._invalid(symbol, "No fresh order block detected")

            fvg = self._find_nearby_fvg(entry_tf_df, order_block["index"], direction)
            if not fvg:
                return self._invalid(symbol, "No confirming fair value gap near order block")

            volume_context = self._volume_confirmation(entry_tf_df)
            if not volume_context["spike_confirmed"]:
                return self._invalid(symbol, "Volume spike confirmation missing")

            session_match = self._is_within_session(entry_tf_df.iloc[-1]["timestamp"])

            atr = self._calculate_atr(entry_tf_df)
            if atr is None or atr <= 0:
                return self._invalid(symbol, "ATR calculation failed")

            entry_price = (order_block["low"] + order_block["high"]) / 2
            stop_loss = self._calculate_stop(entry_price, atr, direction, order_block)
            targets = self._calculate_targets(entry_price, atr, direction)

            # Validate minimum TP distance to cover trading fees
            if targets:
                tp_distance_pct = abs(targets[0] - entry_price) / entry_price * 100
                if tp_distance_pct < MIN_TP_PERCENT:
                    return self._invalid(
                        symbol,
                        f"TP too small ({tp_distance_pct:.3f}% < {MIN_TP_PERCENT}% min) - insufficient to cover fees",
                    )

            rr = abs(targets[0] - entry_price) / abs(entry_price - stop_loss) if stop_loss != entry_price else 0

            confirmation = self._confirm_breakout(confirmation_df, direction, entry_price)
            if not confirmation:
                return self._invalid(symbol, "Lower timeframe BOS confirmation missing")

            score = self._score_signal(
                context=context,
                has_fvg=True,
                volume_multiplier=volume_context["spike_multiple"],
                session_match=session_match,
                rr_ratio=rr,
            )

            metadata = {
                "bos_timeframe": self.config.confirmation_timeframe,
                "atr": atr,
                "volume_spike": volume_context["spike_multiple"],
                "order_block_age": order_block["age_candles"],
            }

            return OrderBlockSignal(
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                stop_loss=stop_loss,
                targets=targets,
                rr_ratio=round(rr, 2),
                confidence=round(score / 100, 2),
                timeframe_notes=context.higher_timeframe_trend,
                meets_criteria=True,
                reason=f"{direction.upper()} OB + FVG confirmed",
                score=round(score, 2),
                session_match=session_match,
                indicator_context={
                    "order_block": f"{order_block['low']:.4f}-{order_block['high']:.4f}",
                    "fvg": f"{fvg['low']:.4f}-{fvg['high']:.4f}",
                    "confirmation_signal": confirmation,
                },
                metadata=metadata,
            )
        except Exception as exc:
            logger.error(f"Error analyzing {symbol} datasets: {exc}", exc_info=True)
            return self._invalid(symbol, f"Exception: {exc}")

    def scan(
        self,
        symbols: List[str],
        top_n: int = 10,
        progress_callback: Optional[Callable[[int, int, int], None]] = None,
        max_workers: Optional[int] = None,
    ) -> List[OrderBlockSignal]:
        """Scan multiple symbols in parallel."""
        if not symbols:
            return []

        workers = self._determine_symbol_workers(len(symbols), max_workers)
        logger.info(
            "Scanning %s symbols for order block setups with %s workers (limit=%s)",
            len(symbols),
            workers,
            max_workers or self.config.max_workers,
        )

        results: List[OrderBlockSignal] = []
        processed = 0

        def analyze_symbol(sym: str) -> OrderBlockSignal:
            return self.analyze(sym)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {executor.submit(analyze_symbol, symbol): symbol for symbol in symbols}

            for future in as_completed(future_map):
                processed += 1
                signal = future.result()
                if signal.get("meets_criteria"):
                    results.append(signal)

                if progress_callback and (processed % 5 == 0 or processed == len(symbols)):
                    try:
                        progress_callback(processed, len(symbols), len(results))
                    except Exception as exc:  # pragma: no cover - defensive
                        logger.error(f"Progress callback failed: {exc}")

        results.sort(key=lambda item: item.get("score", 0), reverse=True)
        return results[:top_n]

    # ------------------------------------------------------------------ #
    # Data loading helpers
    # ------------------------------------------------------------------ #
    def _load_timeframes(self, symbol: str) -> Dict[str, pd.DataFrame]:
        datasets: Dict[str, pd.DataFrame] = {}
        timeframes = list(self.config.timeframes)
        if not timeframes:
            return datasets

        def fetch_timeframe(tf: str) -> tuple[str, Optional[pd.DataFrame]]:
            tf_minutes = TIMEFRAME_TO_MINUTES.get(tf)
            if not tf_minutes:
                logger.warning("Unsupported timeframe '%s' in config", tf)
                return tf, None

            candles_needed = self._candles_for_timeframe(tf_minutes)
            try:
                ohlcv = self.market_data.client.get_ohlcv(symbol, timeframe=tf, limit=candles_needed)
            except Exception as exc:  # pragma: no cover - network guard
                logger.error("Failed to fetch OHLCV for %s %s: %s", symbol, tf, exc)
                return tf, None

            if not ohlcv or len(ohlcv) < max(self.config.swing_length * 4, 50):
                logger.debug("Skipping %s %s timeframe - insufficient candles", symbol, tf)
                return tf, None

            return tf, self._to_dataframe(ohlcv)

        worker_count = self._timeframe_worker_count()
        if worker_count == 1:
            for tf in timeframes:
                tf_name, df = fetch_timeframe(tf)
                if df is not None:
                    datasets[tf_name] = df
            return datasets

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_map = {executor.submit(fetch_timeframe, tf): tf for tf in timeframes}
            for future in as_completed(future_map):
                try:
                    tf_name, df = future.result()
                except Exception as exc:  # pragma: no cover - defensive
                    tf_label = future_map.get(future, "?")
                    logger.error("Timeframe download task failed for %s %s: %s", symbol, tf_label, exc)
                    continue

                if df is not None:
                    datasets[tf_name] = df

        return datasets

    @staticmethod
    def _to_dataframe(ohlcv: List[List]) -> pd.DataFrame:
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        numeric_cols = ["open", "high", "low", "close", "volume"]
        df[numeric_cols] = df[numeric_cols].astype(float)
        return df

    def _candles_for_timeframe(self, tf_minutes: int) -> int:
        total_minutes = self.config.lookback_months * 30 * 24 * 60
        candles = math.ceil(total_minutes / tf_minutes)
        return min(max(candles, self.config.swing_length * 5), MAX_CANDLES_PER_REQUEST)

    def _determine_symbol_workers(self, symbol_count: int, override: Optional[int]) -> int:
        if symbol_count <= 1:
            return 1

        limit = override if override and override > 0 else self.config.max_workers
        if limit <= 0:
            cpu_count = max(1, os.cpu_count() or 4)
            limit = max(4, cpu_count * 2)

        return min(limit, symbol_count)

    def _timeframe_worker_count(self) -> int:
        tf_count = len(self.config.timeframes)
        if tf_count <= 1:
            return tf_count or 1

        limit = max(1, min(self.config.max_workers, TIMEFRAME_WORKER_CAP))
        return min(limit, tf_count)

    # ------------------------------------------------------------------ #
    # Trend and structure evaluation
    # ------------------------------------------------------------------ #
    def _evaluate_trend(self, datasets: Dict[str, pd.DataFrame]) -> TrendContext:
        higher_tf_trend: Dict[str, str] = {}
        bos_timeframe = None
        choch_detected = False

        biases = []
        for tf in ["1d", "4h", "1h"]:
            df = datasets.get(tf)
            if df is None:
                continue

            trend = self._determine_trend(df)
            higher_tf_trend[tf] = trend
            if trend in {"bullish", "bearish"}:
                biases.append(trend)

            if bos_timeframe is None:
                bos_detected = self._detect_bos(df, trend)
                if bos_detected:
                    bos_timeframe = tf

            if not choch_detected:
                choch_detected = self._detect_choch(df, trend)

        if not biases:
            return TrendContext(
                bias="neutral",
                higher_timeframe_trend=higher_tf_trend,
                last_bos_timeframe=bos_timeframe,
                choch_detected=choch_detected,
            )

        bias = "bullish" if biases.count("bullish") >= biases.count("bearish") else "bearish"
        return TrendContext(
            bias=bias, higher_timeframe_trend=higher_tf_trend, last_bos_timeframe=bos_timeframe, choch_detected=choch_detected
        )

    def _determine_trend(self, df: pd.DataFrame) -> str:
        swings = self._find_swing_points(df, self.config.swing_length)
        if len(swings["highs"]) < 2 or len(swings["lows"]) < 2:
            return "neutral"

        last_high = df["high"].iloc[swings["highs"][-1]]
        prev_high = df["high"].iloc[swings["highs"][-2]]
        last_low = df["low"].iloc[swings["lows"][-1]]
        prev_low = df["low"].iloc[swings["lows"][-2]]

        if last_high > prev_high and last_low > prev_low:
            return "bullish"
        if last_high < prev_high and last_low < prev_low:
            return "bearish"
        return "neutral"

    @staticmethod
    def _find_swing_points(df: pd.DataFrame, swing_length: int) -> Dict[str, List[int]]:
        highs: List[int] = []
        lows: List[int] = []
        for idx in range(swing_length, len(df) - swing_length):
            window = df.iloc[idx - swing_length : idx + swing_length + 1]
            high = df["high"].iloc[idx]
            low = df["low"].iloc[idx]
            if high >= window["high"].max():
                highs.append(idx)
            if low <= window["low"].min():
                lows.append(idx)
        return {"highs": highs, "lows": lows}

    def _detect_bos(self, df: pd.DataFrame, trend: str) -> bool:
        swings = self._find_swing_points(df, self.config.swing_length)
        if trend == "bullish" and len(swings["highs"]) >= 2:
            return df["close"].iloc[-1] > df["high"].iloc[swings["highs"][-2]]
        if trend == "bearish" and len(swings["lows"]) >= 2:
            return df["close"].iloc[-1] < df["low"].iloc[swings["lows"][-2]]
        return False

    def _detect_choch(self, df: pd.DataFrame, trend: str) -> bool:
        swings = self._find_swing_points(df, self.config.swing_length)
        if trend == "bullish" and len(swings["lows"]) >= 2:
            return df["close"].iloc[-1] < df["low"].iloc[swings["lows"][-1]]
        if trend == "bearish" and len(swings["highs"]) >= 2:
            return df["close"].iloc[-1] > df["high"].iloc[swings["highs"][-1]]
        return False

    # ------------------------------------------------------------------ #
    # Order block & FVG detection
    # ------------------------------------------------------------------ #
    def _find_order_block(self, df: pd.DataFrame, direction: str) -> Optional[Dict]:
        lookback = min(len(df) - 3, 250)
        if lookback <= 3:
            return None

        for idx in range(len(df) - lookback, len(df) - 3):
            candle = df.iloc[idx]
            body_direction = "bullish" if candle["close"] > candle["open"] else "bearish"

            if direction == "long" and body_direction != "bearish":
                continue
            if direction == "short" and body_direction != "bullish":
                continue

            impulse_window = df.iloc[idx + 1 : idx + 4]
            if impulse_window.empty:
                continue

            if direction == "long":
                broke_high = impulse_window["high"].max() > candle["high"] * 1.001
                if not broke_high:
                    continue
                zone_high = max(candle["open"], candle["high"])
                zone_low = min(candle["open"], candle["low"])
                if self._zone_mitigated(df.iloc[idx + 1 :], zone_low, zone_high, direction):
                    continue
                return {
                    "index": idx,
                    "low": zone_low,
                    "high": zone_high,
                    "age_candles": len(df) - idx,
                }

            else:
                broke_low = impulse_window["low"].min() < candle["low"] * 0.999
                if not broke_low:
                    continue
                zone_high = max(candle["open"], candle["high"])
                zone_low = min(candle["open"], candle["low"])
                if self._zone_mitigated(df.iloc[idx + 1 :], zone_low, zone_high, direction):
                    continue
                return {
                    "index": idx,
                    "low": zone_low,
                    "high": zone_high,
                    "age_candles": len(df) - idx,
                }

        return None

    @staticmethod
    def _zone_mitigated(df: pd.DataFrame, low: float, high: float, direction: str) -> bool:
        if df.empty:
            return False

        if direction == "long":
            return (df["close"] < low).any()
        return (df["close"] > high).any()

    def _find_nearby_fvg(self, df: pd.DataFrame, center_index: int, direction: str) -> Optional[Dict]:
        start = max(center_index - 5, 2)
        end = min(center_index + 6, len(df) - 2)
        min_size = self.config.min_fvg_size_pct / 100

        for idx in range(start, end):
            prev_candle = df.iloc[idx - 1]
            current = df.iloc[idx]
            next_candle = df.iloc[idx + 1]

            if direction == "long":
                if prev_candle["high"] < next_candle["low"]:
                    gap_size = next_candle["low"] - prev_candle["high"]
                    if gap_size / current["close"] >= min_size:
                        return {"low": prev_candle["high"], "high": next_candle["low"], "index": idx}
            else:
                if prev_candle["low"] > next_candle["high"]:
                    gap_size = prev_candle["low"] - next_candle["high"]
                    if gap_size / current["close"] >= min_size:
                        return {"low": next_candle["high"], "high": prev_candle["low"], "index": idx}

        return None

    # ------------------------------------------------------------------ #
    # Volume, ATR, sessions
    # ------------------------------------------------------------------ #
    def _volume_confirmation(self, df: pd.DataFrame) -> Dict[str, float]:
        period = min(self.config.volume_ma_period, len(df) // 2)
        if period < 5:
            return {"spike_confirmed": False, "spike_multiple": 0.0}

        volume_ma = df["volume"].rolling(period).mean()
        if volume_ma.isna().all():
            return {"spike_confirmed": False, "spike_multiple": 0.0}

        latest_volume = df["volume"].iloc[-1]
        ma_value = volume_ma.iloc[-1]
        if ma_value == 0 or pd.isna(ma_value):
            return {"spike_confirmed": False, "spike_multiple": 0.0}

        multiple = latest_volume / ma_value
        spike = multiple >= self.config.volume_spike_threshold
        return {"spike_confirmed": spike, "spike_multiple": round(float(multiple), 2)}

    def _calculate_atr(self, df: pd.DataFrame) -> Optional[float]:
        period = min(self.config.atr_period, len(df) - 1)
        if period < 5:
            return None

        high = df["high"]
        low = df["low"]
        close = df["close"]

        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = true_range.rolling(period).mean().iloc[-1]
        return float(atr) if not math.isnan(atr) else None

    def _calculate_stop(self, entry: float, atr: float, direction: str, order_block: Dict) -> float:
        multiplier = self.config.atr_stop_multiplier
        if direction == "long":
            raw = min(order_block["low"], entry - atr * multiplier)
        else:
            raw = max(order_block["high"], entry + atr * multiplier)
        return round(raw, 6)

    def _calculate_targets(self, entry: float, atr: float, direction: str) -> List[float]:
        targets = []
        multipliers = [1.0, self.config.atr_target_multiplier, self.config.atr_target_multiplier * 1.5]
        sign = 1 if direction == "long" else -1

        for mult in multipliers:
            target = entry + sign * atr * mult
            targets.append(round(target, 6))
        return targets

    def _is_within_session(self, timestamp: pd.Timestamp) -> bool:
        if not self.config.sessions_utc:
            return True

        time_utc = timestamp.tz_convert(timezone.utc).time()
        if getattr(time_utc, "tzinfo", None) is not None:
            # Normalize to naive time to avoid comparing aware vs naive
            time_utc = time_utc.replace(tzinfo=None)
        for session in self.config.sessions_utc:
            start = self._parse_time(session.start_utc)
            end = self._parse_time(session.end_utc)
            if start <= end:
                if start <= time_utc <= end:
                    return True
            else:  # Overnight session
                if time_utc >= start or time_utc <= end:
                    return True
        return False

    @staticmethod
    def _parse_time(value: str) -> time:
        hour, minute = map(int, value.split(":"))
        return time(hour=hour, minute=minute)

    # ------------------------------------------------------------------ #
    # Confirmation, scoring, utils
    # ------------------------------------------------------------------ #
    def _confirm_breakout(self, df: pd.DataFrame, direction: str, entry_price: float) -> Optional[str]:
        recent = df.tail(self.config.swing_length * 2)
        if len(recent) < self.config.swing_length + 2:
            return None

        swings = self._find_swing_points(recent, max(2, self.config.swing_length // 2))
        if direction == "long" and len(swings["highs"]) >= 1:
            last_high = recent["high"].iloc[swings["highs"][-1]]
            if recent["close"].iloc[-1] > last_high and recent["close"].iloc[-1] > entry_price:
                return "Bullish BOS on confirmation timeframe"
        if direction == "short" and len(swings["lows"]) >= 1:
            last_low = recent["low"].iloc[swings["lows"][-1]]
            if recent["close"].iloc[-1] < last_low and recent["close"].iloc[-1] < entry_price:
                return "Bearish BOS on confirmation timeframe"
        return None

    def _score_signal(
        self,
        context: TrendContext,
        has_fvg: bool,
        volume_multiplier: float,
        session_match: bool,
        rr_ratio: float,
    ) -> float:
        score = 0.0

        if context.bias in {"bullish", "bearish"}:
            score += 30
        if context.last_bos_timeframe is not None:
            score += 10
        if has_fvg:
            score += 15
        if session_match:
            score += 10

        volume_score = min(volume_multiplier / self.config.volume_spike_threshold, 2.0) * 15
        score += volume_score

        rr_score = min(rr_ratio / 2.0, 1.5) * 20
        score += rr_score

        if context.choch_detected:
            score -= 10

        return max(0.0, min(score, 100.0))

    @staticmethod
    def _invalid(symbol: str, reason: str) -> OrderBlockSignal:
        return OrderBlockSignal(symbol=symbol, meets_criteria=False, reason=reason, score=0.0)


__all__ = ["OrderBlockBreakoutStrategy", "OrderBlockSignal"]
