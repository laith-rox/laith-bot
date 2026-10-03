# Gigi 60-day broker-price replay — 2026-10-03

Research-only replay on JustMarkets native XAUUSD.m M5/M15/H4 bars.

## Method
- Window: last 60 calendar days ending 2026-10-02.
- Entry study window: 05:00-20:00 Palestine time.
- Entry assumption: next M5 bar open after a closed-bar decision.
- Outcome horizon: 24 M5 bars (~2 hours).
- Same-bar stop and target: STOP counted first (conservative).
- No bid/ask spread, slippage, latency, or historical macro/ETF/options/CFTC
  reconstruction. Signals overlap and are evaluated independently.
- Therefore this is a price-layer signal study, not a profitability claim.

## Overall
- 2,312 signals.
- Mean raw outcome: -0.0595R.
- Holdout 30%: -0.0525R.
- Price-layer baseline therefore does not establish a positive overall edge.

## By mode
### MAIN
- 254 signals.
- Full sample: +0.1088R mean.
- Earlier 70%: +0.0798R.
- Holdout 30%: +0.1833R.
- Chronological validation status: STABLE_POSITIVE.
- This is promising research evidence only; costs/news/overlap are not modeled.

### SNIPER
- 2,058 signals.
- Full sample: -0.0803R mean.
- Earlier 70%: -0.0807R.
- Holdout 30%: -0.0794R.
- Chronological validation status: STABLE_NEGATIVE.
- Raw price-layer SNIPER must remain unproven; do not treat frequency or a high
  7-check score as evidence of profitability.

## Robust weak SNIPER reason families
Negative in both earlier and holdout segments with meaningful samples:
- FAST_PRIMARY_2OF3.
- MTF_COUNTERTREND_MEDIUM.
- STRONG_SIGNAL_CANDLE_INVALIDATION.
- TECHNICAL_MEDIUM_LOCAL_INVALIDATION.

Removing only those four improves SNIPER from roughly -0.08R to roughly
-0.02R in both earlier and holdout segments, but still does not establish a
positive edge.

## What this teaches Gigi
- MAIN and SNIPER are separate strategies and must be calibrated separately.
- More indicator agreement is not monotonically better: raw strength 5/6 did
  not outperform strength 4 in this period.
- A 7/7 alignment score is not a win probability.
- Countertrend and "strong signal" recovery logic can look persuasive while
  remaining negative out of sample.
- London/US labels should not be optimized from small samples; especially the
  US sample lacks historical macro-event reconstruction.
- New external-context layers (macro phase, flows, options, yields, liquidity,
  execution quality) should remain SHADOW until live observations show stable
  incremental value.

## Next validation rule
No new filter is promoted merely because it improves this 60-day replay.
A candidate must:
1. improve an earlier sample,
2. remain positive/stable in a later holdout,
3. survive spread/slippage assumptions,
4. avoid relying on a tiny subgroup,
5. then prove itself again in forward shadow data.


## Hypothetical transaction-cost sensitivity
These are NOT measured JustMarkets fills. They simply subtract a fixed XAU
price-unit cost divided by each trade's risk distance.

| Assumed total price cost | MAIN mean R | SNIPER mean R |
| --- | ---: | ---: |
| 0.00 | +0.1088 | -0.0803 |
| 0.20 | +0.0926 | -0.1623 |
| 0.40 | +0.0765 | -0.2442 |
| 0.60 | +0.0604 | -0.3262 |

The sign of MAIN remained positive across this sensitivity range, while the
raw SNIPER baseline deteriorated sharply because its risk distances are smaller.
This strengthens the case for separate execution-quality calibration by mode,
but still does not prove future profitability.
