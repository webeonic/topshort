"""Pump detector logic."""

import logging
from typing import Dict

from ..config import ScannerConfig
from ..exchange.market_data import MarketData

logger = logging.getLogger(__name__)


class PumpDetector:
    """Detects pump and cooldown patterns in trading pairs."""

    def __init__(self, market_data: MarketData, config: ScannerConfig):
        self.market_data = market_data
        self.config = config

    def detect(self, symbol: str) -> Dict:
        """Detect if symbol shows pump and cooldown pattern.

        Returns: Dict with detection results including score
        """
        return self.market_data.analyze_pump_pattern(
            symbol=symbol,
            pump_threshold=self.config.pump_threshold_pct,
            pump_hours_min=self.config.pump_period_hours_min,
            pump_hours_max=self.config.pump_period_hours_max,
            cooldown_hours_min=self.config.cooldown_period_hours_min,
            cooldown_hours_max=self.config.cooldown_period_hours_max,
            volume_decrease_threshold=self.config.volume_decrease_threshold_pct,
        )

    def is_valid_signal(self, analysis: Dict) -> bool:
        """Check if analysis result is a valid trading signal."""
        return analysis.get("meets_criteria", False) and analysis.get("score", 0) > 0
