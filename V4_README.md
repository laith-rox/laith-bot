# Laith V4

Laith V4 is an independent paper-trading bot for XAU/USD built from the validated V3 research snapshot.

## Isolation
- Git branch: `v4-main`
- Expected Railway project/service: dedicated to V4
- Database: `/data/laith_v4.db`
- Dedicated V4 Telegram transport only
- No writes to Laith Bot or V3 databases
- Analysis and paper results remain the source of truth

## Optional MT5 execution bridge
- The MT5 bridge is a separate transport layer and does not change V4 analysis logic.
- The bridge is demo-first and publishes only fresh official V4 paper entries; quick/H4 streams are not auto-executed.
- Live execution is fail-closed: Railway requires an explicit live-arming value and the MT5 Expert Advisor has a separate `AllowLiveTrading` switch.
- Default test size is 0.01 lot with a server-side maximum of 0.02 lot.
- The MT5 executor rejects stale signals, excessive spread, excessive entry-price movement, invalid stops/targets, duplicate orders, and a second V4 executor position.

## Initial decision stack
V4 inherits the current tested research stack: strict-signal gating, session classification, ATR volatility regime, global macro context with fallback proxies, causal support/resistance zones, confirmed/failed breakouts, correction maps, structural stops, reward-room checks, news guard, fresh-price validation, and experiment-versioned statistics.

## Promotion rule
Nothing is moved to live execution merely because a backtest looks good. Changes are promoted only after unit tests, paper trading, out-of-sample/walk-forward evaluation, realistic spread/slippage costs, drawdown review, and a successful demo execution test.
