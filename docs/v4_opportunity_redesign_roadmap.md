# Laith V4 — Opportunity-driven research roadmap

Status: APPROVED FOR DEVELOPMENT AND TESTING ONLY. NOT APPROVED FOR PRODUCTION.

## Non-negotiable boundaries
- Telegram signals for **manual execution only**; never send MT5 trade orders.
- No fixed-interval obligation to publish trades; publish only validated opportunities or meaningful state changes.
- No full-margin positioning, guaranteed-win labels, or fabricated confidence percentages.
- Do not modify Laith Single. Do not merge or deploy without explicit user approval.
- Keep the existing live runtime unchanged until tests, review, and approval are complete.

## Eight approved capabilities
1. **Scenario engine** — continuation, reversal, and range hypotheses; invalidate each with observable price conditions.
2. **Session liquidity hunter** — Asia range and London/New York opens, sweeps, break-and-retest, fakeout detection, timezone/DST-safe.
3. **Entry engine** — early vs retest vs late-entry decisions; verified live price, SL, TP, spread, R:R, news guard.
4. **Trade management suggestions** — partial TP, break-even, trailing structure-based stop; paper-only, no orders.
5. **Market regime detector** — trend/range/high-volatility/news regime and appropriate strategy selection.
6. **Decision journal** — log all accepted/rejected candidates with evidence and later MFE/MAE/outcome; avoid hindsight leakage.
7. **Next-opportunity radar** — trigger level, required confirmation, invalidation, and deduplicated Telegram status updates.
8. **Calibrated confidence** — out-of-sample empirical probability only with sufficient samples and calibration; otherwise 'insufficient evidence'.

## Suggested incremental delivery
- Phase A: regime + scenarios + session liquidity; deterministic fixtures and DST tests.
- Phase B: event-driven opportunity lifecycle and manual Telegram messages; freshness, risk, and news tests.
- Phase C: short/long/scalp classification and paper exit-management simulations.
- Phase D: journaling, historical replay, walk-forward evaluation, calibrated confidence, shadow comparison to current V4.

## Acceptance criteria before requesting deployment approval
- All unit/integration tests green; replay on real historical data with explicit data-source coverage.
- No stale-price 'enter now' signal, no duplicate alerts, no market-closed signal, no automatic trade execution.
- Evaluate opportunities by session and regime, win/loss, net expectancy after estimated costs, drawdown, missed opportunities, and false positives.
- No unsupported claim that profitable daily trades are guaranteed.

## Current implementation status
The existing draft PR #40 only implements a preliminary conservative Quick-entry gate and explicit WAIT/ENTRY wording; the eight capabilities above are **not implemented yet**. Tests in the PR have not yet been executed. This roadmap is the scope for subsequent development.

## Six additional proposals — pending explicit approval
9. **Gold pattern memory:** compare similar historical sessions/regimes without assuming recurrence; prevent look-ahead bias.
10. **False-breakout classifier:** distinguish genuine breakout/retest from liquidity sweep and failed breakout using measurable structure.
11. **Position sizing calculator:** recommend risk-based size from balance, stop distance, contract size, and broker specifications; no full-margin recommendations.
12. **Unexpected-news and data-integrity guard:** pause actionable alerts during abnormal volatility, feed outages, stale quotes, or unscheduled shocks.
13. **Missed-opportunity audit:** record why qualified opportunities were missed (filter, latency, data freshness, session gating), review with hindsight-safe replay.
14. **Strategy tournament:** compare breakout, pullback, and reversal strategies by session/regime using walk-forward tests, spread/slippage and drawdown.

These six are **recommendations, not yet approved implementation scope**. Do not enable them in production by default.

## Architecture and sequencing notes
- Use event triggers (session opening, range break, liquidity sweep, retest, regime change, news release) with deduplication, plus lightweight monitoring to detect triggers; remove any *obligation* to publish every N minutes.
- Separate market-data quality, strategy hypotheses, opportunity scoring, risk, Telegram presentation, and outcome journaling.
- No trade is 'guaranteed'; empirical confidence must be calibrated on held-out data.
- Keep all new work in the development branch and test before seeking explicit merge/deployment permission.
