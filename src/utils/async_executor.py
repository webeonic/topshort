"""Shared thread pool utilities for running blocking code."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()
_DEFAULT_WORKERS = max(4, os.cpu_count() or 4)


def configure_async_executor(max_workers: int | None = None) -> None:
    """Configure global blocking executor shared across the app."""
    global _executor
    with _executor_lock:
        if max_workers is None or max_workers <= 0:
            max_workers = _DEFAULT_WORKERS

        current_workers = getattr(_executor, "_max_workers", None)
        if _executor and current_workers == max_workers:
            return

        if _executor:
            logger.info("Reconfiguring async executor: shutting down old pool")
            _executor.shutdown(wait=False)

        _executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="blocking-worker")
        logger.info("Async executor configured with %s workers", max_workers)


def shutdown_async_executor(wait: bool = False) -> None:
    """Shutdown executor to release threads on app exit."""
    global _executor
    with _executor_lock:
        if not _executor:
            return
        logger.info("Shutting down async executor (wait=%s)", wait)
        _executor.shutdown(wait=wait)
        _executor = None


def _get_executor() -> ThreadPoolExecutor:
    if not _executor:
        logger.warning("Async executor not configured, using default settings")
        configure_async_executor()
    if _executor is None:
        raise RuntimeError("Failed to initialize async executor")
    return _executor


async def run_blocking(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run blocking callable in the shared executor."""
    loop = asyncio.get_running_loop()
    executor = _get_executor()
    bound = partial(func, *args, **kwargs)
    return await loop.run_in_executor(executor, bound)
