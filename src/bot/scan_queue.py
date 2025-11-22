"""Queue and worker management for manual scan commands."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict

logger = logging.getLogger(__name__)


class ScanQueueFullError(Exception):
    """Raised when scan queue exceeds configured capacity."""


@dataclass
class ScanQueueItem:
    """Represents a queued scan request."""

    scan_id: str
    strategy_mode: str
    handler: Callable[[], Awaitable[None]]


class ScanQueueManager:
    """Ensures manual scan commands execute sequentially per strategy."""

    def __init__(self, max_queue_size: int = 3, worker_delay_seconds: float = 0.1):
        self._max_queue_size = max_queue_size
        self._worker_delay_seconds = worker_delay_seconds
        self._queues: Dict[str, asyncio.Queue[ScanQueueItem]] = {}
        self._workers: Dict[str, asyncio.Task] = {}
        self._queue_lock = asyncio.Lock()

    async def submit(self, item: ScanQueueItem) -> int:
        """Add scan request to per-strategy queue.

        Returns:
            int: Zero-based position in the queue (0 means executes immediately).
        """
        async with self._queue_lock:
            queue = self._queues.setdefault(item.strategy_mode, asyncio.Queue())
            if queue.qsize() >= self._max_queue_size:
                raise ScanQueueFullError(f"Scan queue for {item.strategy_mode} is full ({self._max_queue_size})")

            position = queue.qsize()
            queue.put_nowait(item)

            if item.strategy_mode not in self._workers:
                self._workers[item.strategy_mode] = asyncio.create_task(self._worker(item.strategy_mode))

            return position

    async def _worker(self, strategy_mode: str) -> None:
        queue = self._queues[strategy_mode]
        logger.info("Starting scan queue worker for %s", strategy_mode)

        while True:
            item = await queue.get()
            try:
                await item.handler()
            except Exception:
                logger.exception("Queued scan failed (%s)", item.scan_id)
            finally:
                queue.task_done()

            if queue.empty():
                should_stop = False
                async with self._queue_lock:
                    current_queue = self._queues.get(strategy_mode)
                    if current_queue is queue and queue.empty():
                        logger.info("Scan queue worker for %s completed", strategy_mode)
                        self._workers.pop(strategy_mode, None)
                        self._queues.pop(strategy_mode, None)
                        should_stop = True
                if should_stop:
                    break

            await asyncio.sleep(self._worker_delay_seconds)


__all__ = ["ScanQueueManager", "ScanQueueItem", "ScanQueueFullError"]
