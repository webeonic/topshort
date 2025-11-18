# TopShort Trading Bot - Multi-Source Position Tracking & Limit Order Implementation

## Overview

This implementation adds two critical features to the TopShort trading bot:

1. **Multi-Source Position Tracking**: Track trading pairs opened by the bot, manually, or by other systems
2. **Limit Order Take-Profit**: Place take-profit as limit orders instead of monitoring and closing with market orders

## Features Implemented

### 1. Database Schema Enhancements

#### New Fields in `positions` Table:
- `source` (VARCHAR): Track position origin ('bot_auto', 'manual', 'external_system')
- `source_metadata` (TEXT): JSON metadata about the position source
- `take_profit_order_id` (VARCHAR): ID of the take-profit limit order
- `take_profit_order_status` (VARCHAR): Status of TP order ('pending', 'filled', 'cancelled', 'failed')
- `take_profit_placed_at` (DATETIME): When the TP order was placed
- `stop_loss_order_id` (VARCHAR): ID of stop-loss order (for future use)
- `stop_loss_order_status` (VARCHAR): Status of SL order

#### New `limit_orders` Table:
Comprehensive tracking of all limit orders with fields:
- `order_id`, `position_id`, `symbol`, `order_type`, `side`, `price`, `quantity`
- `status`, `filled_quantity`, `avg_fill_price`, `exchange_status`
- `error_message`, `created_at`, `updated_at`, `filled_at`, `cancelled_at`

#### Updated `trade_history` Table:
- `source`: Position source tracking
- `take_profit_order_id`: Link to TP limit order
- `stop_loss_order_id`: Link to SL order

### 2. New Services

#### `LimitOrderMonitor` (`src/trading/limit_order_monitor.py`)
Monitors pending take-profit limit orders and handles:
- Checking order status on exchange
- Automatically closing positions when TP orders are filled
- Handling cancelled/expired orders
- Retrying failed TP orders
- Manual TP order cancellation

**Key Methods:**
- `monitor_take_profit_orders()`: Main monitoring loop
- `retry_failed_take_profit_orders()`: Retry failed TP placements
- `cancel_take_profit_order(position_id)`: Cancel a TP order

#### `ExchangePositionSync` (`src/trading/exchange_position_sync.py`)
Syncs positions from the exchange to track all active positions:
- Import positions opened manually or by other systems
- Count total active pairs across all sources
- Check position limits before opening new trades
- Reconcile closed positions (detect external closures)
- Comprehensive risk summary including all sources

**Key Methods:**
- `sync_positions_from_exchange()`: Import external positions
- `get_total_active_pairs()`: Count all open positions
- `get_active_pairs_by_source()`: Breakdown by source
- `check_position_limits()`: Validate against limits
- `reconcile_closed_positions()`: Detect external closures
- `get_risk_summary()`: Full risk metrics

### 3. Updated Components

#### `PositionManager` Enhancements
- Now places take-profit limit orders immediately when opening positions
- Records TP order ID and status in database
- Handles TP order placement failures gracefully
- **Old behavior removed**: No longer monitors prices and closes with market orders

#### `PositionRepository` New Methods
- `place_take_profit_order()`: Record TP limit order
- `update_take_profit_status()`: Update TP order status
- `get_positions_with_pending_tp()`: Get positions with pending TP
- `get_positions_with_failed_tp()`: Get positions with failed TP
- `get_by_source()`: Get positions by source
- `count_by_source()`: Count positions grouped by source

#### `LimitOrderRepository` (New)
Dedicated repository for limit order operations:
- `get_by_order_id()`: Fetch order by ID
- `get_by_position()`: Get all orders for a position
- `get_pending_orders()`: Get pending orders
- `update_status()`: Update order status

#### `RiskManager` Updates
- `get_risk_summary()` now includes `positions_by_source` breakdown
- Position limits now consider ALL sources (bot + manual + external)

## Database Migration

### Running the Migration

For **existing databases**:
```bash
# Backup your database first!
cp data/topshort.db data/topshort.db.backup

# Run migration
python3 src/database/migrate_v1.py data/topshort.db
```

The migration will:
1. Create automatic backup with timestamp
2. Add new columns to `positions` and `trade_history` tables
3. Create new `limit_orders` table
4. Create indexes for performance
5. Verify migration success

For **new installations**:
The schema will be created automatically with all new fields when you first run the bot.

### Migration Safety
- Automatic backup created before migration
- Idempotent (safe to run multiple times)
- Validates all changes after completion
- Rollback support if errors occur

## Integration Guide

### 1. Update Main Bot Loop

Replace the old monitoring logic with the new limit order monitoring:

```python
from src.trading.limit_order_monitor import LimitOrderMonitor
from src.trading.exchange_position_sync import ExchangePositionSync

# Initialize services
limit_order_monitor = LimitOrderMonitor(session, binance_client)
exchange_sync = ExchangePositionSync(session, binance_client, config)

# In your monitoring loop (every 30-60 seconds):
def monitor_and_sync():
    # 1. Sync positions from exchange (every 5 minutes)
    if should_sync_positions():
        sync_stats = exchange_sync.sync_positions_from_exchange()
        logger.info(f"Position sync: {sync_stats}")

    # 2. Monitor take-profit limit orders
    closed_positions = limit_order_monitor.monitor_take_profit_orders()
    if closed_positions:
        # Send notifications for closed positions
        for pos in closed_positions:
            send_telegram_notification(pos)

    # 3. Reconcile closed positions (every 10 minutes)
    if should_reconcile():
        reconciled = exchange_sync.reconcile_closed_positions()
        if reconciled > 0:
            logger.info(f"Reconciled {reconciled} externally closed positions")

    # 4. Retry failed TP orders (every hour)
    if should_retry_failed():
        retried = limit_order_monitor.retry_failed_take_profit_orders()
        if retried > 0:
            logger.info(f"Retried {retried} failed TP orders")
```

### 2. Update Risk Checks Before Trading

Before opening new positions, check total active pairs:

```python
# Check position limits including all sources
limit_check = exchange_sync.check_position_limits()

if not limit_check['can_open_position']:
    logger.warning(
        f"Cannot open position: {limit_check['current_positions']}/{limit_check['max_positions']} "
        f"positions active. Breakdown: {limit_check['positions_by_source']}"
    )
    return

logger.info(
    f"Position slots available: {limit_check['available_slots']}. "
    f"Active by source: {limit_check['positions_by_source']}"
)

# Proceed with normal risk checks
risk_check = risk_manager.check_before_trade(symbol, margin, leverage)
if risk_check['approved']:
    position_manager.open_position(symbol, margin, leverage)
```

### 3. Display Risk Summary with Source Breakdown

```python
def display_risk_dashboard():
    summary = exchange_sync.get_risk_summary()

    print(f"Total Positions: {summary['total_positions']}/{summary['max_positions']}")
    print(f"Position Utilization: {summary['position_utilization_pct']}%")
    print(f"Total Margin: {summary['total_margin_used']}/{summary['max_margin']} USDT")
    print(f"Margin Utilization: {summary['margin_utilization_pct']}%")
    print(f"\nPositions by Source:")
    for source, count in summary['positions_by_source'].items():
        print(f"  - {source}: {count}")
```

### 4. Remove Old Monitoring Logic

**IMPORTANT**: The old `monitor_positions()` method in `PositionManager` is **NO LONGER NEEDED** because:
- Take-profit is now handled by limit orders on the exchange
- The `LimitOrderMonitor` checks order status and closes positions automatically
- No need to poll prices and close manually

You can **remove or deprecate** the old monitoring calls:

```python
# OLD (DELETE THIS):
# closed = position_manager.monitor_positions()

# NEW (USE THIS):
closed = limit_order_monitor.monitor_take_profit_orders()
```

## Configuration

No new configuration needed! The existing settings are used:
- `max_positions`: Now enforced across ALL sources
- `max_total_margin`: Applied to total margin across all positions
- `take_profit_pct`: Used when creating limit orders

## Testing Checklist

### Manual Testing Steps

1. **Test Position Opening with Limit Orders**
   ```python
   # Open a position
   result = position_manager.open_position("BTC/USDT:USDT", margin=100, leverage=20)

   # Verify TP limit order was placed
   assert result['take_profit_order_id'] is not None

   # Check database
   position = position_repo.get(result['position_id'])
   assert position.take_profit_order_status == 'pending'
   assert position.source == 'bot_auto'
   ```

2. **Test External Position Import**
   ```python
   # Manually open position on Binance
   # Then sync
   stats = exchange_sync.sync_positions_from_exchange()

   # Verify imported
   assert stats['new'] > 0

   # Check source
   positions = position_repo.get_by_source('external_system')
   assert len(positions) > 0
   ```

3. **Test Position Limit Enforcement**
   ```python
   # Import several external positions
   # Try to open new position when limit reached
   limit_check = exchange_sync.check_position_limits()

   if not limit_check['can_open_position']:
       print(f"Limit enforced: {limit_check['current_positions']}/{limit_check['max_positions']}")
       print(f"Breakdown: {limit_check['positions_by_source']}")
   ```

4. **Test Limit Order Monitoring**
   ```python
   # Wait for TP to be hit
   closed = limit_order_monitor.monitor_take_profit_orders()

   # Verify position closed automatically
   assert len(closed) > 0

   # Check order status updated
   position = position_repo.get(closed[0]['position_id'])
   assert position.take_profit_order_status == 'filled'
   assert position.status == 'closed'
   ```

5. **Test Reconciliation**
   ```python
   # Manually close position on Binance
   # Run reconciliation
   reconciled = exchange_sync.reconcile_closed_positions()

   # Verify position marked closed in DB
   assert reconciled > 0
   ```

### Unit Tests

Create tests for:
- [ ] `LimitOrderMonitor.monitor_take_profit_orders()`
- [ ] `ExchangePositionSync.sync_positions_from_exchange()`
- [ ] `ExchangePositionSync.check_position_limits()`
- [ ] `PositionRepository.place_take_profit_order()`
- [ ] `PositionRepository.count_by_source()`

## Monitoring & Alerts

### Recommended Monitoring

1. **Failed TP Orders**
   ```python
   failed_positions = position_repo.get_positions_with_failed_tp()
   if failed_positions:
       send_alert(f"⚠️ {len(failed_positions)} positions without TP protection!")
   ```

2. **External Position Detection**
   ```python
   external_count = position_repo.count_by_source().get('external_system', 0)
   if external_count > 0:
       send_notification(f"📊 Detected {external_count} externally opened positions")
   ```

3. **Position Limit Approaching**
   ```python
   summary = exchange_sync.get_risk_summary()
   if summary['position_utilization_pct'] > 80:
       send_alert(f"⚠️ Position limit at {summary['position_utilization_pct']}%!")
   ```

## Performance Considerations

### Optimizations Implemented

1. **Batch Ticker Fetching**: Already implemented in `BinanceClient.fetch_tickers()`
2. **Indexed Queries**: New indexes on `source`, `status`, `take_profit_order_status`
3. **Efficient Counting**: `count_by_source()` uses SQL GROUP BY instead of filtering in Python

### Recommended Intervals

- **Limit Order Monitoring**: Every 30-60 seconds
- **Position Sync**: Every 5 minutes (or on demand)
- **Reconciliation**: Every 10-15 minutes
- **Failed TP Retry**: Every 1 hour

## Troubleshooting

### Issue: TP Order Placement Fails

**Symptoms**: Position opens but `take_profit_order_status` is 'failed'

**Solutions**:
1. Check Binance API permissions (need order placement permission)
2. Verify position mode is set to HEDGE mode
3. Check if price precision is correct for the symbol
4. Run `limit_order_monitor.retry_failed_take_profit_orders()`

### Issue: External Positions Not Detected

**Symptoms**: Manual positions don't show up in position count

**Solutions**:
1. Ensure position mode is SHORT (not LONG)
2. Run `exchange_sync.sync_positions_from_exchange()` manually
3. Check if position has non-zero contracts
4. Verify API keys have position read permissions

### Issue: Migration Fails

**Symptoms**: Database migration script errors

**Solutions**:
1. Check if database file exists and is not corrupted
2. Verify Python sqlite3 module is available
3. Restore from backup if needed
4. For SQLite: `PRAGMA integrity_check;`

## API Reference

### LimitOrderMonitor

```python
class LimitOrderMonitor:
    def monitor_take_profit_orders(self) -> List[Dict]
    def retry_failed_take_profit_orders(self) -> int
    def cancel_take_profit_order(self, position_id: int) -> bool
```

### ExchangePositionSync

```python
class ExchangePositionSync:
    def sync_positions_from_exchange(self) -> Dict[str, int]
    def get_total_active_pairs(self) -> int
    def get_active_pairs_by_source(self) -> Dict[str, int]
    def check_position_limits(self, max_positions: Optional[int] = None) -> Dict
    def reconcile_closed_positions(self) -> int
    def get_risk_summary(self) -> Dict
```

### PositionRepository (New Methods)

```python
class PositionRepository:
    def place_take_profit_order(self, position_id: int, order_id: str) -> Position
    def update_take_profit_status(self, position_id: int, status: str, ...) -> Position
    def get_positions_with_pending_tp(self) -> List[Position]
    def get_positions_with_failed_tp(self) -> List[Position]
    def get_by_source(self, source: str, status: str = 'open') -> List[Position]
    def count_by_source(self) -> Dict[str, int]
```

## Future Enhancements

Potential improvements for future versions:

1. **Stop-Loss Limit Orders**: Extend to place SL as limit orders too
2. **Partial Take-Profit**: Close positions in stages (25%, 50%, 100%)
3. **Trailing Stop-Loss**: Implement trailing SL limit orders
4. **Position Tagging**: Add tags/labels to positions for better organization
5. **Multi-Exchange Support**: Track positions across multiple exchanges
6. **Position Analytics**: Historical analysis by source and strategy

## Support & Feedback

For issues or questions:
1. Check logs in `logs/topshort.log`
2. Verify database integrity
3. Review Binance API permissions
4. Check network connectivity to Binance

## Summary

This implementation provides:
- ✅ Multi-source position tracking (bot, manual, external)
- ✅ Automatic take-profit via limit orders (no monitoring needed)
- ✅ Position limit enforcement across all sources
- ✅ External position import and reconciliation
- ✅ Comprehensive risk metrics with source breakdown
- ✅ Failed order retry mechanism
- ✅ Database migration support
- ✅ Backward compatible (works with existing data)

The bot now has complete visibility into all trading activity and uses efficient limit orders for take-profit execution! 🎉
