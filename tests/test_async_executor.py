"""Unit tests for async_executor module."""

import asyncio
from unittest.mock import patch

import pytest

from src.utils import async_executor
from src.utils.async_executor import _get_executor, configure_async_executor, run_blocking, shutdown_async_executor


class TestAsyncExecutor:
    """Test async executor functionality."""

    def setup_method(self):
        """Reset executor state before each test."""
        shutdown_async_executor(wait=True)

    def teardown_method(self):
        """Clean up executor after each test."""
        shutdown_async_executor(wait=True)

    def test_configure_executor_creates_pool(self):
        """Test that configuring executor creates thread pool."""
        configure_async_executor(max_workers=2)
        executor = _get_executor()
        assert executor is not None
        assert executor._max_workers == 2

    def test_configure_executor_with_default_workers(self):
        """Test configuring with None uses default workers."""
        configure_async_executor(max_workers=None)
        executor = _get_executor()
        assert executor is not None
        assert executor._max_workers >= 4  # Default is max(4, cpu_count)

    def test_configure_executor_with_zero_uses_default(self):
        """Test that zero workers uses default."""
        configure_async_executor(max_workers=0)
        executor = _get_executor()
        assert executor._max_workers >= 4

    def test_shutdown_executor(self):
        """Test shutting down executor."""
        configure_async_executor(max_workers=2)
        shutdown_async_executor(wait=True)
        # After shutdown, _executor should be None
        assert async_executor._executor is None

    def test_get_executor_auto_configures(self):
        """Test that _get_executor auto-configures if not configured."""
        # Ensure no executor exists
        shutdown_async_executor(wait=True)
        assert async_executor._executor is None

        # Getting executor should auto-configure
        executor = _get_executor()
        assert executor is not None

    def test_get_executor_raises_runtime_error_on_failure(self):
        """Test that _get_executor raises RuntimeError if initialization fails."""
        # Mock configure_async_executor to not actually create an executor
        with patch.object(async_executor, "configure_async_executor") as mock_configure:
            # Make configure not set _executor
            mock_configure.return_value = None
            # Ensure executor is None
            async_executor._executor = None

            with pytest.raises(RuntimeError, match="Failed to initialize async executor"):
                _get_executor()

    @pytest.mark.asyncio
    async def test_run_blocking_executes_function(self):
        """Test that run_blocking executes function in thread pool."""
        configure_async_executor(max_workers=2)

        def blocking_func(x, y):
            return x + y

        result = await run_blocking(blocking_func, 2, 3)
        assert result == 5

    @pytest.mark.asyncio
    async def test_run_blocking_with_kwargs(self):
        """Test run_blocking with keyword arguments."""
        configure_async_executor(max_workers=2)

        def blocking_func(a, b=10):
            return a * b

        result = await run_blocking(blocking_func, 5, b=3)
        assert result == 15

    @pytest.mark.asyncio
    async def test_run_blocking_propagates_exceptions(self):
        """Test that exceptions from blocking function propagate."""
        configure_async_executor(max_workers=2)

        def failing_func():
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            await run_blocking(failing_func)

    def test_reconfigure_executor_shuts_down_old(self):
        """Test reconfiguring executor shuts down old pool."""
        configure_async_executor(max_workers=2)
        old_executor = async_executor._executor

        configure_async_executor(max_workers=4)
        new_executor = async_executor._executor

        assert new_executor is not old_executor
        assert new_executor._max_workers == 4

    def test_reconfigure_with_same_workers_does_nothing(self):
        """Test reconfiguring with same worker count doesn't recreate pool."""
        configure_async_executor(max_workers=3)
        executor1 = async_executor._executor

        configure_async_executor(max_workers=3)
        executor2 = async_executor._executor

        assert executor1 is executor2
