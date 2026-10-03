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


### Cboe GVZ options-volatility proxy — 2026-10-02
- GVZ: 23.23.
- 5-session change: +0.79.
- Approximate 1-year percentile from the public Cboe history: 15.1%.
- Shadow classification: LOW implied-volatility regime relative to its own recent history.
- Important limitation: GVZ is based on GLD options. It is an options-implied
  volatility proxy for gold exposure, not CME gold-futures CVOL and not a
  directional BUY/SELL signal.

## Volatility reasoning added

- Separate realised volatility from options-implied volatility.
- Rising implied volatility does not mean bearish direction.
- Compression + elevated implied volatility is tagged as
  PRICED_MOVE_COMPRESSION: options are pricing movement before realised
  expansion, but direction still comes from structure/liquidity/flows.
- Elevated implied + elevated realised is tagged STRESS_EXPANSION.
- Volatility context may change execution quality, stop behaviour and expected
  noise, but never chooses BUY or SELL by itself.


### World Gold Council weekly ETF flow snapshot — 2026-09-25
- Global weekly USD flow: about +US$134.2m.
- Four-week cumulative USD flow: about +US$9.61bn.
- Total holdings in the public weekly table: about 4,248.92t.
- North America: about -US$610.3m.
- Europe: about +US$614.5m.
- Asia: about +US$101.5m.
- Other: about +US$28.5m.
- Weekly holdings change from the flow table: about -1.64t.
- Shadow classification: MIXED_INFLOW, because the headline global inflow masks
  a large North American outflow offset by European and Asian inflows.
- Lesson: aggregate ETF flow alone can hide important regional rotation; Gigi
  therefore tracks breadth and does not label this as BROAD_INFLOW.

## ETF-flow reasoning added

- Broad inflow/outflow requires agreement across North America, Europe and Asia.
- Mixed regional rotation is recorded but does not become a directional trigger.
- ETF flow remains a slow H4/D1 context layer, never an M5 entry signal.
- The learning layer records ETF regime and regional breadth separately.


## Crowding / liquidation-cascade layer

Gigi now separates normal directional context from squeeze/liquidation risk.

Long-liquidation risk rises when several pieces align:
- Managed Money is long-biased but deleveraging, or long crowding is elevated.
- ETF flows are broad/mixed outflows.
- Price rejects buy-side liquidity and closes back below the swept area.
- H4 is down.
- Realised volatility is expanding; this is the speed gate that can turn a
  slow vulnerability into a cascade.

Short-squeeze risk is the mirror image:
- short crowding or active short covering;
- broad ETF inflow;
- sell-side sweep and bullish rejection;
- H4 up;
- expanding realised volatility.

Without a volatility speed gate, even a high slow-context score stays WATCH,
not HIGH. The layer is context-only and never generates BUY/SELL by itself.

### Slow snapshot while market is closed — 2026-10-03
- CFTC: LONG_BIASED_DELEVERAGING.
- ETF: MIXED_INFLOW.
- GVZ: LOW relative to its recent 1-year history.
- Live realised volatility/liquidity: unavailable while market is closed.
- Result: BALANCED crowding risk; no active cascade/squeeze state.


### Cboe delayed GLD options snapshot — 2026-10-03
- Proxy underlying GLD: about 380.14.
- Selected expiry for the ~30-day window: 2026-10-30 (27 DTE).
- 25-delta call IV: about 20.68%.
- 25-delta put IV: about 21.19%.
- 25-delta put-minus-call skew: about +0.51 vol points -> BALANCED.
- Put/call open-interest ratio inside +/-20% moneyness: about 0.629 -> CALL_HEAVY.
- Put/call volume ratio: about 0.289 -> call activity dominated this delayed snapshot.
- Gross unsigned gamma-OI: about 22.3% sits within +/-2% of spot -> MODERATE_NEAR_SPOT_CONVEXITY.
- Largest gross gamma-OI strike in the selected expiry: about GLD 400, but this is
  NOT a signed dealer-gamma level. Public chain data does not tell Gigi whether
  dealers are net long or short gamma.

## Options reasoning added

- 25-delta skew is treated as hedging demand, not an automatic price forecast.
- Put/call OI and volume are crowding clues only.
- Gross gamma*OI is deliberately unsigned; Gigi must not invent "dealer gamma"
  support/resistance without dealer-side positioning.
- Convexity concentration near spot is learned as a context bucket, not a BUY/SELL rule.

## Contradiction-first thesis audit

Before calling a setup "clean", Gigi now searches for independent evidence
against it. Families include H4 structure, intermarket, liquidity, CFTC
positioning, ETF flows, crowding/liquidation risk and event uncertainty.
The audit labels each setup CLEAN, MIXED, FRAGILE or UNPROVEN.
A missing invalidation automatically makes the thesis FRAGILE.
This layer is SHADOW only and is tracked in the learning database so we can
later test whether FRAGILE setups actually underperform CLEAN setups instead of
assuming they do.


## Evidence-independence guard

Gigi no longer lets related slow-flow evidence stack as if it were independent.
CFTC positioning, ETF flows and positioning crowding are one flow family for
the context score. They can corroborate each other, but together contribute at
most one directional context point. This reduces false confidence from
double-counting correlated evidence.

## Out-of-sample learning guard

Shadow learning now has a chronological validation layer:
- a bucket needs at least 40 resolved observations before out-of-sample review;
- the later 35% of observations is reserved as a test segment;
- train/test sign disagreement is labelled UNSTABLE_SIGN_FLIP;
- extreme R outcomes are clipped at +/-5R for stability checks so one outlier
  cannot make a weak bucket look robust;
- even a STABLE_POSITIVE bucket is only a shadow candidate and never changes
  live execution automatically.

This is specifically designed to defend against overfitting and data snooping.


### Cross-market persistence rule — added 2026-10-03
- A short-window correlation is not enough to call another market a gold driver.
- Gigi now compares short and longer rolling correlations.
- WTI/Brent, equities and FX only vote when the relationship is directionally
  persistent across both windows.
- A relationship that flips sign is logged as FLIPPING and contributes zero
  directional evidence until it stabilizes.
- This specifically protects against the common mistake of learning a temporary
  oil/gold or dollar/gold relationship and treating it as permanent.

### Current slow-context snapshot — 2026-10-03
- CFTC: Managed Money remains strongly net long, but the latest weekly change
  is deleveraging rather than fresh long addition.
- WGC ETF: four-week flows are strongly positive, while the latest week is
  regionally mixed, with North American outflow offset by Europe/Asia.
- Cboe GVZ: 23.23, relatively low versus its own recent one-year history.
- Delayed GLD options proxy, ~27 DTE:
  - 25-delta call IV ~20.68%; 25-delta put IV ~21.19%.
  - 25-delta risk reversal (put minus call IV) ~+0.51 vol points: broadly
    balanced rather than an extreme downside hedge bid.
  - put/call open-interest ratio ~0.629 and volume ratio ~0.289: call-heavy
    participation in this GLD proxy, but not a standalone bullish signal.
  - gross gamma-open-interest is moderately concentrated near spot; this is
    unsigned public-chain gamma, so no dealer-gamma sign is inferred.
- US Treasury context as of 2026-10-02:
  - 2y nominal ~4.83%, 10y nominal ~5.28%, 10y real ~2.92%.
  - 10y real yield +4bp day/day and +9bp over five sessions.
  - Current classifier still treats the move as stable rather than a fresh
    directional yield regime.
- Combined conclusion for shadow analysis: the slow backdrop is MIXED, not a
  clean one-factor bullish or bearish regime. Price structure, liquidity and
  fresh session flow must still decide the trade thesis.
