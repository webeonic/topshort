"""Formatting utilities for bot messages."""


def format_strategy_label(strategy: str | None) -> str:
    """Format strategy name for display.

    Args:
        strategy: Strategy identifier (e.g., 'pump_cooldown', 'order_block')

    Returns:
        Human-readable strategy label or 'N/A' if strategy is None/empty
    """
    if not strategy:
        return "N/A"
    labels = {
        "pump_cooldown": "Pump & Cooldown",
        "order_block": "Order Block",
    }
    return labels.get(strategy, strategy)
