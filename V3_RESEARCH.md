# Laith Bot V3 Research Lab

This branch is an isolated research track. It is **not** imported by `bot.py` and must not be merged into `main` until paper and out-of-sample evidence justify individual changes.

## Objective

Build a transparent, testable XAU/USD research system that combines market structure with independent context instead of stacking more lagging indicators.  The goal is not to claim a guaranteed or uniquely best trading system; the goal is to find components that remain useful on unseen data, after realistic costs, and across changing regimes.

## Current experimental layers

1. **No forced-bias entries**
   - If the live analyzer only has `best_available_bias` / `forced=True`, V3 returns `WAIT`.
   - Goal: measure whether removing weak directional guesses improves expectancy and drawdown.

2. **Session regime**
   - DST-aware labels: `ASIA`, `LONDON`, `NEW_YORK`, `LONDON_NEW_YORK_OVERLAP`, `OTHER`.
   - First pass blocks only `OTHER` and records the session on every decision.
   - Goal: measure session-specific behavior before tuning any session threshold.

3. **Intraday volatility regime**
   - Percentile of 15-minute ATR using trailing closed bars only.
   - Labels: `LOW`, `NORMAL`, `HIGH`, `EXTREME`.
   - First pass blocks only `EXTREME` (>=95th percentile).

4. **Slow global macro context**
   - Public daily series are fetched at low frequency and evaluated with a strict previous-day rule to prevent intraday look-ahead.
   - Current factors: broad U.S. dollar (`DTWEXBGS`), U.S. 10y nominal yield (`DGS10`), U.S. 10y real yield (`DFII10`), VIX (`VIXCLS`), and WTI (`DCOILWTICO`).
   - Dollar and real yields are the primary opportunity-cost legs.  VIX is a coarse risk proxy.  Oil is recorded but not given a directional vote because its relationship with gold is regime-dependent.
   - V3 only vetoes a strict technical candidate when the macro score is a **strong conflict**; macro data never invents a trade.

5. **Economic-event protection**
   - Existing high-impact USD blackout remains in force for paper entries.
   - Future research will store actual/forecast/previous values when a trustworthy source is available and test standardized surprise magnitude separately from event timing.

## Research data roadmap

### Tier A — already implemented / low-risk
- XAU/USD closed 5-minute candles and timestamped provider quote.
- Public U.S. macro market series listed above.
- High-impact USD event schedule.
- Session and ATR regimes derived causally from closed data.

### Tier B — shadow-only until data quality is proven
- COMEX Gold futures volume and VWAP.
- Open interest.
- Gold options implied volatility / CVOL-style features.
- DXY / rates intraday confirmation rather than only prior-day macro context.
- Economic surprise values (actual vs consensus) with event-family normalization.

### Tier C — research only, never promoted without strong evidence
- Order-book / DOM imbalance.
- Machine-learning ensembles.
- Nonlinear parameter optimization.
- News/sentiment embeddings.

## Isolation rules

- `v3_research.py` contains the candidate analyzer.
- `v3_global_data.py` contains as-of-safe macro features.
- `v3_metrics.py` contains descriptive performance metrics.
- `v3_backtest.py` compares current logic, strict logic, and V3 under identical fills/cost assumptions.
- `v3_service.py` is a standalone paper worker and does not send Telegram messages or broker orders.
- Default V3 database path is separate from the live `/data/laith.db`.
- The live Railway service remains on `main`; experimental deployment uses `research/v3-signal-lab`.

## Anti-overfitting rules

1. Never promote a feature because one backtest looks attractive.
2. Record every candidate configuration tried; failed variants count too.
3. Use chronological out-of-sample periods and, when enough history exists, purged/combinatorial validation rather than one lucky holdout.
4. Compare all variants under identical spread/slippage assumptions.
5. Re-run results at multiple plausible cost levels.
6. Require a useful number of measured trades; small samples are labelled inconclusive.
7. Inspect performance by session, volatility regime, and macro alignment to detect hidden concentration.
8. Prefer a simpler rule that degrades gracefully over a highly tuned rule with a spectacular in-sample result.

## Minimum promotion report

For every candidate change record at least:

- measured trade count,
- net R and mean/median R,
- win/loss counts and win rate,
- profit factor,
- maximum drawdown R,
- longest losing streak,
- moving-block bootstrap interval for mean R when sample size permits,
- results by session,
- results by volatility regime,
- results by macro alignment,
- sensitivity to spread/slippage,
- in-sample vs out-of-sample degradation,
- exact data period and exact code commit.

## Promotion rule

No "merge everything" step.  Each layer must earn promotion independently.  A feature can be useful in research yet harmful in the live system.  Only components that remain useful out-of-sample, survive reasonable execution costs, do not rely on look-ahead, and improve the risk/return profile without unacceptable trade-count collapse should be proposed for `main`.
