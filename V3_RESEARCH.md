# Laith Bot V3 Research Lab

This branch is an isolated research track. It is not imported by `bot.py` and must not be merged into `main` until paper results justify it.

## First three experiments

1. **No forced bias entries**
   - If the live analyzer only has `best_available_bias` / `forced=True`, V3 returns `WAIT`.
   - Goal: test whether removing weak directional guesses improves drawdown and expectancy.

2. **Session tagging/filtering**
   - DST-aware labels: ASIA, LONDON, NEW_YORK, LONDON_NEW_YORK_OVERLAP, OTHER.
   - V3 first pass blocks only OTHER and records the session on every decision.
   - Goal: measure results separately by session before tuning thresholds.

3. **Volatility regime**
   - Uses the percentile of 15-minute ATR from trailing closed bars only.
   - Labels: LOW, NORMAL, HIGH, EXTREME.
   - V3 first pass blocks only EXTREME (>=95th percentile) and records the regime.
   - Goal: avoid blindly applying the same entry logic during exceptional volatility while preserving data for later comparison.

## Isolation rules

- `v3_research.py` contains the candidate analyzer.
- `v3_service.py` is a standalone paper worker and does not send Telegram messages or broker orders.
- Default database is `/data/laith_v3.db`, separate from the live `/data/laith.db`.
- No import from `bot.py` into the live path points to V3.
- Main branch and live Railway service remain unchanged.

## Promotion rule

No V3 filter should be promoted on the basis of a visually attractive backtest. Compare against the current strict baseline on unseen data, with identical spread/slippage assumptions, and track at minimum:

- measured trade count,
- net R,
- maximum drawdown R,
- win/loss counts,
- results by session,
- results by volatility regime,
- sensitivity to realistic execution costs.

Only changes that remain useful out-of-sample and across reasonable cost assumptions should be considered for the live bot.
