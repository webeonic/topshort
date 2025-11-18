"""Tests for configuration module."""

import pytest

from src.config import load_config, validate_config


def test_load_config():
    """Test loading configuration."""
    config = load_config()
    assert config is not None
    assert config.binance is not None
    assert config.telegram is not None
    assert config.trading is not None


def test_validate_config_missing_api_key(monkeypatch):
    """Test config validation with missing API key."""
    monkeypatch.setenv("BINANCE_API_KEY", "")
    config = load_config()
    errors = validate_config(config)
    assert "BINANCE_API_KEY is required" in errors
