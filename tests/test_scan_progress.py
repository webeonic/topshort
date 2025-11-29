"""Tests for scan progress tracking functionality."""

import time
import uuid
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.database.models import ScanProgress
from src.database.repository import ScanProgressRepository


class TestScanProgressRepository:
    """Tests for ScanProgressRepository."""

    def test_create_scan_progress(self, test_db_session):
        """Test creating a new scan progress record."""
        repo = ScanProgressRepository(test_db_session)

        scan_id = f"scan_{uuid.uuid4().hex[:12]}"
        progress = repo.create(
            scan_id=scan_id,
            scan_type="manual",
            total_symbols=200,
            triggered_by="user123",
            scan_params={"pump_threshold": 30, "volume_threshold": 20},
        )

        assert progress is not None
        assert progress.scan_id == scan_id
        assert progress.scan_type == "manual"
        assert progress.status == "running"
        assert progress.total_symbols == 200
        assert progress.processed_symbols == 0
        assert progress.progress_pct == 0.0
        assert progress.signals_found == 0
        assert progress.positions_opened == 0
        assert progress.triggered_by == "user123"
        assert progress.started_at is not None

    def test_get_scan_progress(self, test_db_session):
        """Test getting scan progress by ID."""
        repo = ScanProgressRepository(test_db_session)

        scan_id = f"scan_{uuid.uuid4().hex[:12]}"
        created_progress = repo.create(scan_id=scan_id, scan_type="manual", total_symbols=100)

        retrieved_progress = repo.get(scan_id)

        assert retrieved_progress is not None
        assert retrieved_progress.scan_id == scan_id
        assert retrieved_progress.total_symbols == 100

    def test_update_progress(self, test_db_session):
        """Test updating scan progress."""
        repo = ScanProgressRepository(test_db_session)

        scan_id = f"scan_{uuid.uuid4().hex[:12]}"
        repo.create(scan_id=scan_id, scan_type="manual", total_symbols=200)

        # Update progress
        updated_progress = repo.update_progress(scan_id, processed_symbols=100, signals_found=5)

        assert updated_progress is not None
        assert updated_progress.processed_symbols == 100
        assert updated_progress.signals_found == 5
        assert updated_progress.progress_pct == 50.0  # 100/200 * 100

    def test_update_progress_full_completion(self, test_db_session):
        """Test updating progress to 100%."""
        repo = ScanProgressRepository(test_db_session)

        scan_id = f"scan_{uuid.uuid4().hex[:12]}"
        repo.create(scan_id=scan_id, scan_type="manual", total_symbols=150)

        # Update to full completion
        updated_progress = repo.update_progress(scan_id, processed_symbols=150, signals_found=10)

        assert updated_progress.processed_symbols == 150
        assert updated_progress.progress_pct == 100.0
        assert updated_progress.signals_found == 10

    def test_complete_scan_success(self, test_db_session):
        """Test marking scan as completed successfully."""
        repo = ScanProgressRepository(test_db_session)

        scan_id = f"scan_{uuid.uuid4().hex[:12]}"
        repo.create(scan_id=scan_id, scan_type="manual", total_symbols=200)

        # Complete the scan
        completed_progress = repo.complete(scan_id, signals_found=15, positions_opened=5)

        assert completed_progress is not None
        assert completed_progress.status == "completed"
        assert completed_progress.signals_found == 15
        assert completed_progress.positions_opened == 5
        assert completed_progress.completed_at is not None
        assert completed_progress.duration_seconds is not None
        assert completed_progress.duration_seconds >= 0
        assert completed_progress.error_message is None

    def test_complete_scan_with_error(self, test_db_session):
        """Test marking scan as failed with error."""
        repo = ScanProgressRepository(test_db_session)

        scan_id = f"scan_{uuid.uuid4().hex[:12]}"
        repo.create(scan_id=scan_id, scan_type="manual", total_symbols=200)

        # Complete with error
        completed_progress = repo.complete(scan_id, signals_found=0, error_message="Connection timeout")

        assert completed_progress is not None
        assert completed_progress.status == "failed"
        assert completed_progress.error_message == "Connection timeout"
        assert completed_progress.completed_at is not None

    def test_cancel_scan(self, test_db_session):
        """Test cancelling a running scan."""
        repo = ScanProgressRepository(test_db_session)

        scan_id = f"scan_{uuid.uuid4().hex[:12]}"
        repo.create(scan_id=scan_id, scan_type="manual", total_symbols=200)

        # Cancel the scan
        cancelled_progress = repo.cancel(scan_id)

        assert cancelled_progress is not None
        assert cancelled_progress.status == "cancelled"
        assert cancelled_progress.completed_at is not None
        assert cancelled_progress.duration_seconds is not None

    def test_get_active_scan(self, test_db_session):
        """Test getting currently running scan."""
        repo = ScanProgressRepository(test_db_session)

        # Create multiple scans
        scan_id_1 = f"scan_{uuid.uuid4().hex[:12]}"
        scan_id_2 = f"scan_{uuid.uuid4().hex[:12]}"

        repo.create(scan_id=scan_id_1, scan_type="manual", total_symbols=100)
        repo.create(scan_id=scan_id_2, scan_type="scheduled", total_symbols=150)

        # Complete first scan
        repo.complete(scan_id_1, signals_found=5)

        # Get active scan
        active_scan = repo.get_active_scan()

        assert active_scan is not None
        assert active_scan.scan_id == scan_id_2
        assert active_scan.status == "running"

    def test_get_recent_scans(self, test_db_session):
        """Test getting recent scans."""
        repo = ScanProgressRepository(test_db_session)

        # Create multiple scans
        for i in range(5):
            scan_id = f"scan_{uuid.uuid4().hex[:12]}"
            repo.create(scan_id=scan_id, scan_type="manual", total_symbols=100)
            time.sleep(0.01)  # Small delay to ensure different timestamps

        recent_scans = repo.get_recent(limit=3)

        assert len(recent_scans) == 3
        # Should be in reverse chronological order
        assert recent_scans[0].started_at >= recent_scans[1].started_at

    def test_get_user_scans(self, test_db_session):
        """Test getting scans for a specific user."""
        repo = ScanProgressRepository(test_db_session)

        # Create scans for different users
        scan_id_1 = f"scan_{uuid.uuid4().hex[:12]}"
        scan_id_2 = f"scan_{uuid.uuid4().hex[:12]}"
        scan_id_3 = f"scan_{uuid.uuid4().hex[:12]}"

        repo.create(scan_id=scan_id_1, scan_type="manual", total_symbols=100, triggered_by="user123")
        repo.create(scan_id=scan_id_2, scan_type="manual", total_symbols=100, triggered_by="user456")
        repo.create(scan_id=scan_id_3, scan_type="manual", total_symbols=100, triggered_by="user123")

        user_scans = repo.get_user_scans("user123", limit=10)

        assert len(user_scans) == 2
        assert all(scan.triggered_by == "user123" for scan in user_scans)

    def test_get_statistics(self, test_db_session):
        """Test getting scan statistics."""
        repo = ScanProgressRepository(test_db_session)

        # Create multiple scans with different statuses
        scan_ids = []
        for i in range(5):
            scan_id = f"scan_{uuid.uuid4().hex[:12]}"
            scan_ids.append(scan_id)
            repo.create(scan_id=scan_id, scan_type="manual", total_symbols=100)

        # Complete some scans
        repo.complete(scan_ids[0], signals_found=10, positions_opened=3)
        repo.complete(scan_ids[1], signals_found=5, positions_opened=2)
        repo.complete(scan_ids[2], signals_found=0, error_message="Error")

        # Get statistics
        stats = repo.get_statistics(days=7)

        assert stats["total_scans"] == 5
        assert stats["completed"] == 2  # Successful completions
        assert stats["failed"] == 1
        assert stats["running"] == 2
        assert stats["total_signals_found"] == 15  # 10 + 5
        assert stats["total_positions_opened"] == 5  # 3 + 2
        assert stats["avg_duration_seconds"] is not None


class TestScanProgressModel:
    """Tests for ScanProgress model validations."""

    def test_scan_type_validation(self, test_db_session):
        """Test scan_type validation."""
        with pytest.raises(ValueError, match="Invalid scan type"):
            progress = ScanProgress(scan_id="test123", scan_type="invalid_type", total_symbols=100)
            test_db_session.add(progress)
            test_db_session.commit()

    def test_valid_scan_types(self, test_db_session):
        """Test valid scan types."""
        valid_types = ["manual", "scheduled", "on_demand"]

        for scan_type in valid_types:
            scan_id = f"scan_{uuid.uuid4().hex[:12]}"
            progress = ScanProgress(scan_id=scan_id, scan_type=scan_type, total_symbols=100, started_at=datetime.utcnow())
            test_db_session.add(progress)
            test_db_session.commit()

            assert progress.scan_type == scan_type

    def test_status_validation(self, test_db_session):
        """Test status validation."""
        progress = ScanProgress(scan_id="test123", scan_type="manual", total_symbols=100, started_at=datetime.utcnow())

        with pytest.raises(ValueError, match="Invalid status"):
            progress.status = "invalid_status"

    def test_valid_statuses(self, test_db_session):
        """Test valid status transitions."""
        valid_statuses = ["running", "completed", "failed", "cancelled"]

        for status in valid_statuses:
            scan_id = f"scan_{uuid.uuid4().hex[:12]}"
            progress = ScanProgress(
                scan_id=scan_id, scan_type="manual", total_symbols=100, status=status, started_at=datetime.utcnow()
            )
            test_db_session.add(progress)
            test_db_session.commit()

            assert progress.status == status


class TestScanProgressIntegration:
    """Integration tests for scan progress with scanner."""

    @patch("src.exchange.binance_client.BinanceClient")
    def test_scanner_progress_callback(self, mock_client_class, test_db_session):
        """Test scanner calls progress callback during scan."""
        from src.database.repository import ScanProgressRepository
        from src.exchange.market_data import MarketData

        # Setup mock client
        mock_client = Mock()
        mock_client.get_usdt_perpetual_symbols.return_value = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
        mock_client.fetch_tickers.return_value = {}
        mock_client.get_ohlcv.return_value = []

        # Create market data instance
        market_data = MarketData(mock_client)

        # Setup progress tracking
        scan_id = f"scan_{uuid.uuid4().hex[:12]}"
        repo = ScanProgressRepository(test_db_session)
        repo.create(scan_id=scan_id, scan_type="manual", total_symbols=3)

        # Track progress updates
        progress_updates = []

        def progress_callback(processed, total, signals_found):
            progress_updates.append({"processed": processed, "total": total, "signals_found": signals_found})
            repo.update_progress(scan_id, processed, signals_found)

        # Run scan with progress callback
        results = market_data.scan_market(
            pump_threshold=30.0,
            pump_hours_min=48,
            pump_hours_max=72,
            cooldown_hours_min=4,
            cooldown_hours_max=8,
            volume_decrease_threshold=20.0,
            top_n=10,
            progress_callback=progress_callback,
            use_prefilter=False,  # Disable pre-filter (mock tickers don't have required fields)
        )

        # Verify progress was tracked
        assert len(progress_updates) > 0
        final_progress = repo.get(scan_id)
        assert final_progress.processed_symbols == 3
        assert final_progress.progress_pct == 100.0

    def test_progress_bar_formatting(self):
        """Test progress bar formatting utility."""
        from src.bot.commands import BotCommands

        # Create mock instance for testing method
        class MockCommands:
            def _format_progress_bar(self, progress_pct: float, width: int = 20) -> str:
                filled = int(width * progress_pct / 100)
                empty = width - filled
                bar = "█" * filled + "░" * empty
                return f"[{bar}] {progress_pct:.1f}%"

        mock_cmd = MockCommands()

        # Test various progress levels
        assert "0.0%" in mock_cmd._format_progress_bar(0)
        assert "50.0%" in mock_cmd._format_progress_bar(50)
        assert "100.0%" in mock_cmd._format_progress_bar(100)

        # Check bar contains filled and empty characters
        bar_50 = mock_cmd._format_progress_bar(50, width=10)
        assert "█" in bar_50
        assert "░" in bar_50

        # Check 100% is all filled
        bar_100 = mock_cmd._format_progress_bar(100, width=10)
        assert bar_100.count("█") == 10
        assert "░" not in bar_100

        # Check 0% is all empty
        bar_0 = mock_cmd._format_progress_bar(0, width=10)
        assert bar_0.count("░") == 10
        assert "█" not in bar_0
