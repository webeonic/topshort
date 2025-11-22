"""Tests for the manual scan queue worker logic."""

import asyncio

import pytest

from src.bot.scan_queue import ScanQueueItem, ScanQueueManager


@pytest.mark.asyncio
async def test_worker_waits_for_new_items_after_queue_refill():
    """Ensure worker does not exit if new tasks arrive while it is shutting down."""
    manager = ScanQueueManager(max_queue_size=5, worker_delay_seconds=0.0)
    strategy_mode = "pump"
    processed: list[str] = []
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    second_processed = asyncio.Event()

    async def first_handler():
        first_started.set()
        await release_first.wait()
        processed.append("first")

    async def second_handler():
        processed.append("second")
        second_processed.set()

    await manager.submit(ScanQueueItem(scan_id="scan-1", strategy_mode=strategy_mode, handler=first_handler))
    await first_started.wait()

    await manager._queue_lock.acquire()
    try:
        release_first.set()
        await asyncio.sleep(0)
        queue = manager._queues[strategy_mode]
        queue.put_nowait(ScanQueueItem(scan_id="scan-2", strategy_mode=strategy_mode, handler=second_handler))
    finally:
        manager._queue_lock.release()

    await asyncio.wait_for(second_processed.wait(), timeout=1)
    assert processed == ["first", "second"]

    await asyncio.sleep(0)
