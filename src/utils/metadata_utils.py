"""Metadata parsing utilities."""

import json
from typing import Any, Optional


def extract_strategy_from_metadata(source_metadata: Any) -> Optional[str]:
    """Extract strategy name from position source_metadata.

    Args:
        source_metadata: Position metadata, can be JSON string, dict, or None.

    Returns:
        Strategy name if found, None otherwise.
    """
    if not source_metadata:
        return None
    try:
        if isinstance(source_metadata, str):
            metadata = json.loads(source_metadata)
        elif isinstance(source_metadata, dict):
            metadata = source_metadata
        else:
            # Handle non-dict, non-string types (int, list, etc.)
            return None
        return metadata.get("strategy")
    except (json.JSONDecodeError, TypeError, AttributeError):
        return None
