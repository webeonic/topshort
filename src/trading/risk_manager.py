"""Risk management for trading operations."""

import logging
from typing import Dict, Optional

from sqlalchemy.orm import Session

from ..config import TradingConfig
from ..database.repository import PositionRepository, SettingsRepository

logger = logging.getLogger(__name__)


class RiskManager:
    """Manages trading risks and validates operations."""

    def __init__(self, session: Session, config: TradingConfig):
        self.session = session
        self.config = config
        self.position_repo = PositionRepository(session)
        self.settings_repo = SettingsRepository(session)

    def get_margin_per_trade(self) -> float:
        """Get margin per trade from settings or config."""
        return self.settings_repo.get_float("margin_per_trade", self.config.margin_per_trade)

    def get_max_positions(self) -> int:
        """Get max positions from settings or config."""
        return self.settings_repo.get_int("max_positions", self.config.max_positions)

    def get_max_total_margin(self) -> float:
        """Get max total margin from settings or config."""
        return self.settings_repo.get_float("max_total_margin", self.config.max_total_margin)

    def can_open_position(self, margin_required: float) -> Dict:
        """Check if a new position can be opened.

        Args:
            margin_required: Margin required for the position

        Returns: Dict with 'allowed' (bool) and 'reason' (str)
        """
        # Check position count
        current_positions = self.position_repo.count_open()
        max_positions = self.get_max_positions()

        if current_positions >= max_positions:
            return {"allowed": False, "reason": f"Maximum positions limit reached ({current_positions}/{max_positions})"}

        # Check total margin
        current_total_margin = self.position_repo.get_total_margin()
        max_total_margin = self.get_max_total_margin()

        if current_total_margin + margin_required > max_total_margin:
            return {
                "allowed": False,
                "reason": f"Total margin limit would be exceeded "
                f"({current_total_margin + margin_required:.2f}/{max_total_margin:.2f} USDT)",
            }

        # Check margin per trade
        margin_per_trade = self.get_margin_per_trade()
        if margin_required > margin_per_trade:
            return {
                "allowed": False,
                "reason": f"Position margin exceeds limit ({margin_required:.2f}/{margin_per_trade:.2f} USDT)",
            }

        return {
            "allowed": True,
            "reason": "All risk checks passed",
            "current_positions": current_positions,
            "max_positions": max_positions,
            "current_margin": current_total_margin,
            "max_margin": max_total_margin,
        }

    def validate_position_size(self, symbol: str, margin: float, leverage: int) -> Dict:
        """Validate position size and parameters.

        Returns: Dict with 'valid' (bool) and 'reason' (str)
        """
        # Check margin is positive
        if margin <= 0:
            return {"valid": False, "reason": "Margin must be positive"}

        # Check leverage is reasonable
        if leverage < 1:
            return {"valid": False, "reason": "Leverage must be at least 1"}

        if leverage >= 125:
            logger.warning(f"Very high leverage {leverage}x for {symbol}")

        # Check if symbol already has an open position
        existing = self.position_repo.get_by_symbol(symbol)
        if existing:
            return {"valid": False, "reason": f"Position already exists for {symbol}"}

        return {"valid": True, "reason": "Position size validated"}

    def check_before_trade(self, symbol: str, margin: float, leverage: int) -> Dict:
        """Complete risk check before opening a trade.

        Returns: Dict with 'approved' (bool), 'reason' (str), and additional info
        """
        # Validate position size
        size_check = self.validate_position_size(symbol, margin, leverage)
        if not size_check["valid"]:
            return {"approved": False, "reason": size_check["reason"], "check": "position_size"}

        # Check if can open position
        risk_check = self.can_open_position(margin)
        if not risk_check["allowed"]:
            return {"approved": False, "reason": risk_check["reason"], "check": "risk_limits"}

        logger.info(
            f"Trade approved for {symbol}: "
            f"Margin={margin} USDT, Leverage={leverage}x, "
            f"Positions={risk_check.get('current_positions')}/{risk_check.get('max_positions')}, "
            f"Total margin={risk_check.get('current_margin'):.2f}/{risk_check.get('max_margin'):.2f} USDT"
        )

        return {"approved": True, "reason": "Trade approved", "risk_info": risk_check}

    def get_risk_summary(self) -> Dict:
        """Get current risk summary including positions from all sources."""
        current_positions = self.position_repo.count_open()
        max_positions = self.get_max_positions()
        current_margin = self.position_repo.get_total_margin()
        max_margin = self.get_max_total_margin()
        margin_per_trade = self.get_margin_per_trade()

        # Get positions breakdown by source
        positions_by_source = self.position_repo.count_by_source()

        positions_utilization = (current_positions / max_positions * 100) if max_positions > 0 else 0
        margin_utilization = (current_margin / max_margin * 100) if max_margin > 0 else 0

        return {
            "current_positions": current_positions,
            "max_positions": max_positions,
            "positions_utilization_pct": round(positions_utilization, 2),
            "current_margin": round(current_margin, 2),
            "max_margin": round(max_margin, 2),
            "margin_utilization_pct": round(margin_utilization, 2),
            "margin_per_trade": round(margin_per_trade, 2),
            "available_slots": max_positions - current_positions,
            "available_margin": round(max_margin - current_margin, 2),
            "positions_by_source": positions_by_source,  # New: breakdown by source
        }
