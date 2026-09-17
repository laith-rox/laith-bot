# Laith V4

Laith V4 is an independent paper-trading bot for XAU/USD built from the validated V3 research snapshot.

## Isolation
- Git branch: `v4-main`
- Expected Railway project/service: dedicated to V4
- Database: `/data/laith_v4.db`
- No Telegram transport
- No broker execution
- No writes to Laith Bot or V3 databases
- Paper results only until an explicit promotion decision

## Initial decision stack
V4 inherits the current tested research stack: strict-signal gating, session classification, ATR volatility regime, global macro context with fallback proxies, causal support/resistance zones, confirmed/failed breakouts, correction maps, structural stops, reward-room checks, news guard, fresh-price validation, and experiment-versioned statistics.

## Promotion rule
Nothing is moved to live execution merely because a backtest looks good. Changes are promoted only after unit tests, paper trading, out-of-sample/walk-forward evaluation, realistic spread/slippage costs, and drawdown review.
