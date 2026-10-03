# Gigi Gold Research Notebook — 2026-10-03

Candidate research only. These are hypotheses and context layers, not guaranteed
signals and not a substitute for live broker validation.

## What changed in modern gold

1. Gold is increasingly driven by multiple flows at once: ETF allocation,
   futures positioning, options activity, FX/rates, risk, and momentum.
2. Implied volatility is not directional by itself. In 2026 strong call buying
   sometimes lifted implied volatility while gold rallied.
3. Positioning matters most as a slow backdrop:
   - long-biased + adding = participation;
   - long-biased + deleveraging = correction/liquidation risk;
   - short-biased + covering = squeeze risk;
   - crowded positioning increases the chance of violent stop cascades.
4. ETF flows and COT are H4/D1 context, never M5 entry triggers.
5. A first post-news spike is not automatically the real direction. Separate:
   PRE_EVENT -> SHOCK_0_5M -> DIGESTION_5_15M.
6. Liquidity sweeps and failed breaks must be distinguished from confirmed
   structure breaks.
7. Rising realised/implied volatility changes stop and target behaviour; it
   does not automatically mean SELL.
8. Thin/off-market hours deserve stricter spread/slippage and stale-data checks.

## Latest public slow context captured in research

### CFTC — report dated 2026-09-29
- COMEX gold open interest: 406,456 contracts.
- Managed Money long: 131,711.
- Managed Money short: 11,393.
- Managed Money net: +120,318.
- Weekly net change: -7,071.
- Managed Money net/open-interest ratio: ~29.6%.
Interpretation for shadow analysis: LONG_BIASED_DELEVERAGING, not an automatic
sell signal.

### World Gold Council — August 2026
- Global gold ETFs added about US$18bn in August.
- Holdings rose to a record 4,189t.
- Managed-money and other-reportable futures positioning rose sharply during
  August.
- Options activity and call buying were important contributors to the rally.

## Common trader errors Gigi must defend against

- confirmation bias after choosing a side;
- anchoring to an old entry/support/resistance;
- overconfidence after a short winning streak;
- holding losers while taking winners too early;
- trading because of time/frequency targets instead of edge;
- treating DXY/yields/oil as fixed one-to-one rules;
- chasing the first candle after CPI/NFP/FOMC;
- confusing high implied volatility with bearish direction;
- overfitting after a handful of trades;
- using a weekly positioning report as an intraday trigger.

## Current Gigi reasoning order

Regime -> H4/M15 structure -> liquidity -> M5 timing -> effort/result ->
intermarket -> macro/event phase -> positioning/crowding -> invalidation ->
risk -> shadow learning.

## Learning discipline

- Minimum 20 resolved observations before a bucket is called calibrated.
- Minimum 30 before a bounded shadow weight can be suggested.
- No automatic strategy rewrite from the learning layer.
- Alignment score is not a win probability.
- New layers enter as SHADOW first and must survive out-of-sample review.
