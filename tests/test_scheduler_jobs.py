"""Unit tests for SchedulerJobs orchestration logic."""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.scheduler.jobs import SchedulerJobs


def _build_jobs(order_block_enabled: bool = True, order_block_interval: int = 60):
    engine = MagicMock()
    engine.execute_pump_scan_and_trade.return_value = {}
    engine.execute_order_block_cycle.return_value = {}
    engine.monitor_and_close.return_value = {}
    engine.top_pairs_service = None

    telegram_bot = AsyncMock()
    config = SimpleNamespace(
        scheduler=SimpleNamespace(scan_interval_minutes=60, monitor_interval_seconds=30, signal_retention_days=30),
        strategy_runtime=SimpleNamespace(order_block_cycle_interval_seconds=order_block_interval, order_block_top_pairs=50),
        order_block_strategy=SimpleNamespace(enabled=order_block_enabled),
    )

    jobs = SchedulerJobs(session=MagicMock(), engine=engine, telegram_bot=telegram_bot, config=config)
    jobs.bot_status_repo = MagicMock()
    jobs.signal_repo = MagicMock()
    jobs.scheduler = MagicMock()
    return jobs, engine, telegram_bot


@pytest.mark.asyncio
async def test_scan_and_trade_job_runs_when_active():
    """Scan job should call pump strategy and send notifications."""
    jobs, engine, telegram_bot = _build_jobs()
    jobs.bot_status_repo.get.return_value = SimpleNamespace(is_active=True, is_paused=False)
    jobs.engine.execute_pump_scan_and_trade.return_value = {
        "positions_opened": 1,
        "opened_positions": [{"symbol": "BTCUSDT"}],
    }

    await jobs.scan_and_trade_job()

    engine.execute_pump_scan_and_trade.assert_called_once_with(max_signals=30, triggered_by="scheduler")
    telegram_bot.notify_scan_complete.assert_awaited_once()
    telegram_bot.notify_position_opened.assert_awaited_once()


@pytest.mark.asyncio
async def test_scan_and_trade_job_skips_when_paused():
    """Paused bot must bypass scan logic."""
    jobs, engine, telegram_bot = _build_jobs()
    jobs.bot_status_repo.get.return_value = SimpleNamespace(is_active=True, is_paused=True)

    await jobs.scan_and_trade_job()

    engine.execute_pump_scan_and_trade.assert_not_called()
    telegram_bot.notify_scan_complete.assert_not_called()


@pytest.mark.asyncio
async def test_order_block_cycle_job_disabled_returns_early():
    """When order-block strategy disabled, cycle job exits immediately."""
    jobs, engine, telegram_bot = _build_jobs(order_block_enabled=False)

    await jobs.order_block_cycle_job()

    engine.execute_order_block_cycle.assert_not_called()
    telegram_bot.notify_scan_complete.assert_not_called()


@pytest.mark.asyncio
async def test_order_block_cycle_job_notifies_on_results():
    """Order-block cycle should notify when results exist."""
    jobs, engine, telegram_bot = _build_jobs(order_block_enabled=True)
    jobs.bot_status_repo.get.return_value = SimpleNamespace(is_active=True, is_paused=False)
    jobs.engine.execute_order_block_cycle.return_value = {
        "strategy_mode": "order_block",
        "signals_found": 2,
        "positions_opened": 1,
        "opened_positions": [{"symbol": "ETHUSDT"}],
    }

    await jobs.order_block_cycle_job()

    engine.execute_order_block_cycle.assert_called_once_with(triggered_by="scheduler")
    telegram_bot.notify_scan_complete.assert_awaited_once()
    telegram_bot.notify_position_opened.assert_awaited_once()


@pytest.mark.asyncio
async def test_monitor_positions_job_sends_closed_notifications():
    """Monitor job should notify Telegram when positions close."""
    jobs, engine, telegram_bot = _build_jobs()
    jobs.bot_status_repo.get.return_value = SimpleNamespace(is_active=True)
    jobs.engine.monitor_and_close.return_value = {
        "positions_closed": 1,
        "closed_positions": [{"symbol": "SOLUSDT"}],
    }

    await jobs.monitor_positions_job()

    jobs.bot_status_repo.update_monitor_time.assert_called_once()
    telegram_bot.notify_position_closed.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_data_job_invokes_repository():
    """Cleanup job must invoke repository cleanup with default retention."""
    jobs, engine, _ = _build_jobs()
    jobs.signal_repo.cleanup_old_signals.return_value = 5
    engine.cleanup_stale_locks = MagicMock(return_value=3)

    await jobs.cleanup_data_job()

    jobs.signal_repo.cleanup_old_signals.assert_called_once_with(retention_days=30)
    engine.cleanup_stale_locks.assert_called_once()


@pytest.mark.asyncio
async def test_refresh_top_pairs_job_refreshes_when_service_available(monkeypatch):
    """Refresh job should call top-pairs service when available."""
    jobs, engine, _ = _build_jobs()
    service = MagicMock()
    service.get_metadata.return_value = {"count": 10, "source": "test", "last_updated": "now"}
    engine.top_pairs_service = service

    async def fake_to_thread(fn, *args, **kwargs):
        fn(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    await jobs.refresh_top_pairs_job()

    service.refresh.assert_called_once()
    service.get_metadata.assert_called_once()


def test_start_schedules_all_jobs():
    """Starting scheduler should register all expected jobs."""
    jobs, _, _ = _build_jobs()
    jobs.start()

    assert jobs.scheduler.add_job.call_count == 5
    jobs.scheduler.start.assert_called_once()


def test_stop_pause_and_resume_control_scheduler():
    """Stop/pause/resume should delegate to scheduler hooks."""
    jobs, _, _ = _build_jobs()
    jobs.scheduler.running = True

    jobs.stop()
    jobs.scheduler.shutdown.assert_called_once()

    jobs.pause()
    jobs.scheduler.pause.assert_called_once()

    jobs.resume()
    jobs.scheduler.resume.assert_called_once()


def test_get_jobs_status_serializes_scheduler_state():
    """get_jobs_status must serialize job metadata cleanly."""
    jobs, _, _ = _build_jobs()

    class DummyTrigger:
        def __str__(self):
            return "interval[0:05:00]"

    class DummyJob:
        def __init__(self):
            self.id = "scan"
            self.name = "Market Scan"
            self.next_run_time = datetime(2024, 1, 1, 12, 0, 0)
            self.trigger = DummyTrigger()

    jobs.scheduler.get_jobs.return_value = [DummyJob()]

    status = jobs.get_jobs_status()

    assert status == [
        {
            "id": "scan",
            "name": "Market Scan",
            "next_run": "2024-01-01T12:00:00",
            "trigger": "interval[0:05:00]",
        }
    ]
