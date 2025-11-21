"""Service for maintaining a curated list of top market pairs."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple, Union
from urllib import parse

import requests

from ..config import PairsConfig
from ..exchange.binance_client import BinanceClient

logger = logging.getLogger(__name__)


class TopPairsService:
    """Fetches and caches top pairs by market cap using CoinGecko + Binance data."""

    USER_AGENT = "TopShortBot/1.0 (+https://github.com/topshort)"

    def __init__(self, client: BinanceClient, config: PairsConfig):
        self.client = client
        self.config = config
        self._lock = threading.Lock()
        self._cache_file = config.cache_path
        self._pairs: List[str] = list(config.fallback_pairs)
        self._last_updated: Optional[datetime] = None
        self._source: str = "fallback"

        self._load_cache()

    def get_pairs(self, force_refresh: bool = False) -> List[str]:
        """Get curated list of pairs (refreshing cache if stale)."""
        with self._lock:
            if force_refresh or not self._is_cache_valid():
                self._refresh_cache_locked()
            return list(self._pairs)

    def get_metadata(self) -> Dict[str, Optional[Union[str, int]]]:
        """Return metadata about the current cache."""
        with self._lock:
            return {
                "last_updated": self._last_updated.isoformat() if self._last_updated else None,
                "source": self._source,
                "count": len(self._pairs),
                "cache_file": self._cache_file,
            }

    def refresh(self) -> List[str]:
        """Force refresh the cache."""
        with self._lock:
            self._refresh_cache_locked(force=True)
            return list(self._pairs)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _is_cache_valid(self) -> bool:
        if not self._pairs:
            return False
        if not self._last_updated:
            return False

        age = datetime.now(timezone.utc) - self._last_updated
        return age <= timedelta(hours=self.config.refresh_interval_hours)

    def _load_cache(self) -> None:
        if not self._cache_file or not os.path.exists(self._cache_file):
            return

        try:
            with open(self._cache_file, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            pairs = data.get("pairs") or []
            last_updated = data.get("last_updated")
            source = data.get("source", "cache")

            if pairs:
                self._pairs = pairs
                if last_updated:
                    self._last_updated = datetime.fromisoformat(last_updated)
                self._source = source
                logger.info(
                    "Loaded %s cached pairs from %s (source=%s)",
                    len(self._pairs),
                    self._cache_file,
                    self._source,
                )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning(f"Unable to load cached pairs: {exc}")

    def _save_cache_locked(self) -> None:
        if not self._cache_file:
            return

        directory = os.path.dirname(os.path.abspath(self._cache_file))
        if directory:
            os.makedirs(directory, exist_ok=True)
        payload = {
            "pairs": self._pairs,
            "last_updated": self._last_updated.isoformat() if self._last_updated else None,
            "source": self._source,
        }
        with open(self._cache_file, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=2)

    def _refresh_cache_locked(self, force: bool = False) -> None:
        if not force and self._is_cache_valid():
            return

        try:
            logger.info("Refreshing top-%s pairs via CoinGecko", self.config.top_n)
            remote_pairs = self._fetch_pairs_from_coingecko()
            if remote_pairs:
                self._pairs = remote_pairs
                self._last_updated = datetime.now(timezone.utc)
                self._source = "coingecko"
                self._save_cache_locked()
                return

            logger.warning("CoinGecko request returned no usable pairs; falling back to defaults")
        except Exception as exc:
            logger.error(f"Failed to refresh top pairs: {exc}", exc_info=True)

        # Fallback
        self._pairs = list(self.config.fallback_pairs)
        self._last_updated = datetime.now(timezone.utc)
        self._source = "fallback"
        self._save_cache_locked()

    def _fetch_pairs_from_coingecko(self) -> List[str]:
        coins = self._fetch_top_coins()
        if not coins:
            return []

        symbols = self.client.get_usdt_perpetual_symbols()
        lookup = self._build_symbol_lookup(symbols)
        selected: List[str] = []
        seen = set()

        for coin in coins:
            if len(selected) >= self.config.top_n:
                break

            candidate = self._match_coin_to_symbol(coin, lookup)
            if candidate and candidate not in seen:
                selected.append(candidate)
                seen.add(candidate)

        return selected

    def _fetch_top_coins(self) -> List[Dict]:
        params = {
            "vs_currency": self.config.coingecko_vs_currency,
            "order": self.config.coingecko_order,
            "per_page": str(self.config.top_n),
            "page": "1",
            "sparkline": "false",
            "price_change_percentage": "24h",
        }
        url = f"{self.config.coingecko_url}?{parse.urlencode(params)}"
        parsed_url = parse.urlparse(url)
        if parsed_url.scheme != "https":
            raise ValueError(f"Unsupported URL scheme for CoinGecko request: {parsed_url.scheme}")
        try:
            response = requests.get(
                url,
                headers={"Accept": "application/json", "User-Agent": self.USER_AGENT},
                timeout=self.config.http_timeout_seconds,
            )
            response.raise_for_status()
            coins = response.json()
            return coins if isinstance(coins, list) else []
        except requests.HTTPError as exc:
            logger.error(f"CoinGecko HTTP error: {exc.response.status_code} {exc.response.reason}")
        except requests.RequestException as exc:
            logger.error(f"CoinGecko network error: {exc}")
        except Exception as exc:  # pragma: no cover - safety
            logger.error(f"Unexpected error fetching CoinGecko data: {exc}")

        return []

    @staticmethod
    def _build_symbol_lookup(symbols: Sequence[str]) -> Dict[str, str]:
        lookup: Dict[str, str] = {}
        for symbol in symbols:
            base = symbol.split("/")[0]
            for key in TopPairsService._generate_symbol_keys(base):
                lookup.setdefault(key, symbol)
        return lookup

    @staticmethod
    def _generate_symbol_keys(base: str) -> List[str]:
        normalized = TopPairsService._normalize(base)
        keys = {normalized}

        # Special-case Binance's 1000- tokens (e.g., 1000SHIB -> SHIB)
        if normalized.startswith("1000") and len(normalized) > 4:
            keys.add(normalized[4:])

        # Handle wrapped tokens (e.g., WBTC -> BTC)
        if normalized.startswith("W") and len(normalized) > 1:
            keys.add(normalized[1:])

        return list(keys)

    @staticmethod
    def _normalize(value: str) -> str:
        return "".join(ch for ch in value.upper() if ch.isalnum())

    def _match_coin_to_symbol(self, coin: Dict, lookup: Dict[str, str]) -> Optional[str]:
        candidates = [
            coin.get("symbol", ""),
            coin.get("id", ""),
            coin.get("name", ""),
        ]

        for candidate in candidates:
            normalized = self._normalize(candidate)
            if not normalized:
                continue
            if normalized in lookup:
                return lookup[normalized]

        return None
