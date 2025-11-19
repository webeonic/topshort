-- Migration V003: Add scan progress tracking table
-- This migration adds a new table to track real-time progress of market scans

CREATE TABLE IF NOT EXISTS scan_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT NOT NULL UNIQUE,
    scan_type TEXT NOT NULL DEFAULT 'manual',  -- 'manual', 'scheduled', 'on_demand'
    status TEXT NOT NULL DEFAULT 'running',     -- 'running', 'completed', 'failed', 'cancelled'

    -- Progress tracking
    total_symbols INTEGER NOT NULL DEFAULT 0,
    processed_symbols INTEGER NOT NULL DEFAULT 0,
    progress_pct REAL NOT NULL DEFAULT 0.0,

    -- Results
    signals_found INTEGER NOT NULL DEFAULT 0,
    positions_opened INTEGER NOT NULL DEFAULT 0,

    -- Timing
    started_at DATETIME NOT NULL,
    completed_at DATETIME,
    duration_seconds REAL,

    -- Error tracking
    error_message TEXT,

    -- Metadata
    triggered_by TEXT,  -- user_id or 'scheduler'
    scan_params TEXT,   -- JSON with scan parameters

    -- Timestamps
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Index for quick lookups by scan_id
CREATE INDEX IF NOT EXISTS idx_scan_progress_scan_id ON scan_progress(scan_id);

-- Index for status queries
CREATE INDEX IF NOT EXISTS idx_scan_progress_status ON scan_progress(status);

-- Index for time-based queries
CREATE INDEX IF NOT EXISTS idx_scan_progress_started_at ON scan_progress(started_at);

-- Index for user-specific scans
CREATE INDEX IF NOT EXISTS idx_scan_progress_triggered_by ON scan_progress(triggered_by);

-- Composite index for active scans
CREATE INDEX IF NOT EXISTS idx_scan_progress_type_status ON scan_progress(scan_type, status);
