"""Binance client wrapper using CCXT."""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import ccxt
from pybreaker import CircuitBreaker
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Circuit breaker configuration
api_circuit_breaker = CircuitBreaker(fail_max=5, reset_timeout=60, name="binance_api")


class BinanceClient:
    """Wrapper for CCXT Binance Futures client."""

    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        """Initialize Binance client."""
        self.exchange = ccxt.binance(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "options": {
                    "defaultType": "future",  # Use futures by default
                },
                "enableRateLimit": True,
            }
        )

        if testnet:
            self.exchange.set_sandbox_mode(True)
            logger.info("Binance client initialized in TESTNET mode")
        else:
            logger.info("Binance client initialized in LIVE mode")

        # Set position mode to hedge mode for short positions
        self._set_hedge_mode()

    def _set_hedge_mode(self) -> bool:
        """Set position mode to hedge mode.

        This allows holding both LONG and SHORT positions simultaneously.
        Required for proper position side handling.
        """
        try:
            response = self.exchange.fapiPrivatePostPositionSideDual({"dualSidePosition": "true"})
            logger.info("Position mode set to HEDGE mode")
            return True
        except Exception as e:
            # If already in hedge mode, this will error but that's okay
            logger.warning(f"Could not set hedge mode (might already be set): {e}")
            return False

    def load_markets(self) -> Dict[str, Any]:
        """Load all available markets."""
        try:
            markets = self.exchange.load_markets(reload=True)
            logger.info(f"Loaded {len(markets)} markets")
            return markets
        except Exception as e:
            logger.error(f"Error loading markets: {e}")
            raise

    def get_usdt_perpetual_symbols(self) -> List[str]:
        """Get all USDT perpetual futures symbols."""
        try:
            markets = self.exchange.load_markets()
            # Filter for USDT perpetual futures
            usdt_perps = [
                symbol
                for symbol, market in markets.items()
                if market.get("quote") == "USDT"
                and market.get("type") == "swap"
                and market.get("linear") is True
                and market.get("active") is True
            ]
            logger.info(f"Found {len(usdt_perps)} USDT perpetual symbols")
            return usdt_perps
        except Exception as e:
            logger.error(f"Error getting USDT perpetual symbols: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(ccxt.RateLimitExceeded),
        reraise=True,
    )
    @api_circuit_breaker
    def get_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> List[List]:
        """Get OHLCV data for a symbol.

        Returns: List of [timestamp, open, high, low, close, volume]
        """
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            return ohlcv
        except ccxt.RateLimitExceeded as e:
            logger.warning(f"Rate limit hit for {symbol}, retrying...")
            raise
        except Exception as e:
            logger.error(f"Error fetching OHLCV for {symbol}: {e}")
            return []

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(ccxt.RateLimitExceeded),
        reraise=True,
    )
    @api_circuit_breaker
    def get_ticker(self, symbol: str) -> Optional[Dict]:
        """Get current ticker for a symbol."""
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return ticker
        except ccxt.RateLimitExceeded as e:
            logger.warning(f"Rate limit hit for {symbol}, retrying...")
            raise
        except Exception as e:
            logger.error(f"Error fetching ticker for {symbol}: {e}")
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(ccxt.RateLimitExceeded),
        reraise=True,
    )
    @api_circuit_breaker
    def fetch_tickers(self, symbols: List[str]) -> Dict[str, Dict]:
        """Fetch tickers for multiple symbols in a single API call.

        Args:
            symbols: List of trading symbols

        Returns: Dict mapping symbol to ticker data
        """
        try:
            # ccxt supports batch ticker fetching
            tickers = self.exchange.fetch_tickers(symbols)
            logger.debug(f"Fetched {len(tickers)} tickers in batch")
            return tickers
        except ccxt.RateLimitExceeded as e:
            logger.warning(f"Rate limit hit for batch tickers, retrying...")
            raise
        except Exception as e:
            logger.error(f"Error batch fetching tickers: {e}")
            # Fallback to individual requests
            result = {}
            for symbol in symbols:
                ticker = self.get_ticker(symbol)
                if ticker:
                    result[symbol] = ticker
            return result

    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for a symbol."""
        try:
            market = self.exchange.market(symbol)
            response = self.exchange.fapiPrivatePostLeverage(
                {
                    "symbol": market["id"],
                    "leverage": leverage,
                }
            )
            logger.info(f"Set leverage {leverage}x for {symbol}")
            return True
        except Exception as e:
            logger.error(f"Error setting leverage for {symbol}: {e}")
            return False

    def create_market_order(
        self, symbol: str, side: str, quantity: float, position_side: Optional[str] = None
    ) -> Optional[Dict]:
        """Create market order.

        Args:
            symbol: Trading symbol (e.g., 'BTC/USDT:USDT')
            side: 'buy' or 'sell'
            quantity: Amount in base currency
            position_side: 'LONG' or 'SHORT' (required in hedge mode)
        """
        try:
            params = {}
            if position_side:
                params["positionSide"] = position_side

            order = self.exchange.create_order(symbol=symbol, type="market", side=side, amount=quantity, params=params)
            logger.info(f"Created market {side} order for {quantity} {symbol}: {order.get('id')}")
            return order
        except ccxt.ExchangeError as e:
            error_msg = str(e)
            # Check for specific error codes
            if "-2022" in error_msg or "ReduceOnly Order is rejected" in error_msg:
                logger.warning(f"ReduceOnly order rejected for {symbol} - position likely already closed")
                # Return a special marker to indicate position doesn't exist
                return {"error_code": -2022, "message": "Position already closed"}
            logger.error(f"Error creating market order for {symbol}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error creating market order for {symbol}: {e}")
            return None

    def create_limit_order(
        self, symbol: str, side: str, quantity: float, price: float, position_side: Optional[str] = None
    ) -> Optional[Dict]:
        """Create limit order.

        Args:
            symbol: Trading symbol
            side: 'buy' or 'sell'
            quantity: Amount in base currency
            price: Limit price
            position_side: 'LONG' or 'SHORT' (required in hedge mode)
        """
        try:
            params = {}
            if position_side:
                params["positionSide"] = position_side

            order = self.exchange.create_order(
                symbol=symbol, type="limit", side=side, amount=quantity, price=price, params=params
            )
            logger.info(f"Created limit {side} order for {quantity} {symbol} @ {price}")
            return order
        except Exception as e:
            logger.error(f"Error creating limit order for {symbol}: {e}")
            return None

    def open_short_position(self, symbol: str, margin_usdt: float, leverage: int) -> Optional[Dict]:
        """Open a short position.

        Args:
            symbol: Trading symbol
            margin_usdt: Margin to use in USDT
            leverage: Leverage to use

        Returns: Order info or None
        """
        try:
            # Set leverage first
            if not self.set_leverage(symbol, leverage):
                return None

            # Get current price
            ticker = self.get_ticker(symbol)
            if not ticker:
                return None

            current_price = ticker["last"]

            # Calculate quantity based on margin and leverage
            # Notional value = margin * leverage
            # Quantity = notional value / price
            notional_value = margin_usdt * leverage
            quantity = notional_value / current_price

            # Round quantity to appropriate precision
            market = self.exchange.market(symbol)
            precision = market["precision"]["amount"]
            quantity = self.exchange.amount_to_precision(symbol, quantity)

            logger.info(
                f"Opening short position: {symbol}, "
                f"Margin: {margin_usdt} USDT, "
                f"Leverage: {leverage}x, "
                f"Price: {current_price}, "
                f"Quantity: {quantity}"
            )

            # Create sell market order to open short (with SHORT position side for hedge mode)
            order = self.create_market_order(symbol, "sell", float(quantity), position_side="SHORT")
            return order

        except Exception as e:
            logger.error(f"Error opening short position for {symbol}: {e}")
            return None

    def close_short_position(self, symbol: str, quantity: float) -> Optional[Dict]:
        """Close a short position.

        Args:
            symbol: Trading symbol
            quantity: Amount to close

        Returns: Order info or None
        """
        try:
            # Create buy market order to close short (with SHORT position side for hedge mode)
            order = self.create_market_order(symbol, "buy", quantity, position_side="SHORT")
            if order:
                logger.info(f"Closed short position: {symbol}, Quantity: {quantity}")
            return order
        except Exception as e:
            logger.error(f"Error closing short position for {symbol}: {e}")
            return None

    def get_positions(self) -> List[Dict]:
        """Get all open positions."""
        try:
            balance = self.exchange.fetch_balance()
            positions = balance.get("info", {}).get("positions", [])

            # Filter out positions with zero amount
            active_positions = [p for p in positions if float(p.get("positionAmt", 0)) != 0]

            return active_positions
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []

    def get_position_by_symbol(self, symbol: str) -> Optional[Dict]:
        """Get position for specific symbol."""
        try:
            positions = self.get_positions()
            market = self.exchange.market(symbol)

            for position in positions:
                if position.get("symbol") == market["id"]:
                    return position

            return None
        except Exception as e:
            logger.error(f"Error getting position for {symbol}: {e}")
            return None

    def get_balance(self) -> Dict:
        """Get account balance."""
        try:
            balance = self.exchange.fetch_balance()
            return balance
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return {}

    def get_funding_rate(self, symbol: str) -> Optional[float]:
        """Get current funding rate for a symbol."""
        try:
            funding_rate = self.exchange.fetch_funding_rate(symbol)
            return funding_rate.get("fundingRate")
        except Exception as e:
            logger.error(f"Error fetching funding rate for {symbol}: {e}")
            return None
