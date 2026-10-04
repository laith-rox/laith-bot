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


### Core historical walk-forward check — 2026-09-02 to 2026-10-02
Read-only research using broker-native MT5 history. External historical macro,
ETF, CFTC and options snapshots were deliberately excluded because using today's
external context on old candles would create look-ahead / data contamination.

Method:
- evaluated the core engine once per 15 minutes;
- 484 historical qualifying setups;
- 12 M5 bars (~60 minutes) evaluation horizon;
- SL/TP first-touch simulation;
- if SL and TP were both touched inside the same M5 bar, the result was counted
  as SL first (conservative because intrabar order is unknown).

Results:
- 249 SL, 202 TP, 33 still mark-to-market at the horizon.
- Conservative mean outcome: about -0.038R per setup.
- MAIN: 29 observations, about +0.132R mean; sample is too small for
  out-of-sample promotion.
- SNIPER: 455 observations, about -0.049R mean.
- Chronological train/test validation labelled the SNIPER bucket
  STABLE_NEGATIVE over this one-month core-only sample.
- No bucket with enough observations qualified as a stable positive
  out-of-sample candidate.
- Several rules changed sign between train and test, including fast 2-of-3,
  MTF medium continuation and sniper stop-cap setups. This is evidence against
  tuning the bot to one recent period.
- M15 support-break-retest looked positive in this sample (~+0.42R, n=13), but
  n=13 is explicitly too small to promote.

Research conclusion:
- Do NOT loosen REAL execution merely because a pattern looked good in a short
  sample.
- Do NOT interpret the current 7-condition score as monotonic win probability;
  strength 6/7/7 did not show a clean monotonic edge in this sample.
- Keep the new regime/macro/flow/options layers in SHADOW while collecting
  clean forward observations.
- Any learned weight must survive chronological out-of-sample validation before
  it can even be suggested as a shadow weight.


## Session structure added

- London and New York session anchors are DST-aware, not fixed UTC offsets.
- Gigi now tracks a broker-native M5 tick-volume-weighted VWAP proxy from:
  - London 08:00 local;
  - New York 08:20 local.
- Tick volume is explicitly treated as a broker activity proxy, not centralized
  exchange volume.
- Overnight range, London opening range and New York opening range are tracked
  for acceptance versus failed-break behaviour.
- A failed break above/below a session range is context only; it cannot choose
  BUY/SELL by itself.
- Distance from session VWAP is normalized by ATR so an identical dollar
  distance is not treated the same in quiet and explosive regimes.

## Macro-event learning added

- High/medium USD events are now grouped by class so their behaviour is learned
  separately: CPI, PCE, PPI, LABOR_NFP, FOMC_FED, LABOR_OTHER, ISM,
  RETAIL_SALES, GDP, PMI, SENTIMENT and OTHER.
- PRE_EVENT, SHOCK_0_5M and DIGESTION_5_15M remain separate dimensions.
- This allows future shadow validation to answer questions such as whether a
  first NFP spike behaves differently from CPI or FOMC in this broker feed,
  instead of assuming all red-folder news is the same.


## MT5 price-only walk-forward finding — 3 non-overlapping 60-day windows

The current technical/structure engine was replayed chronologically on broker
M5/M15/H4 bars, with historical spread approximation, 05:00-20:00 Palestine
entry hours, the six-per-hour cap, and the candidate profit-protection policy.
External historical macro/CFTC/ETF/options/yield states were deliberately
excluded to avoid look-ahead.

Latest 60-day window after spread:
- whole book: -0.0948R mean despite a 56.61% win rate;
- static-stop comparison: -0.1432R mean;
- MAIN: +0.1117R mean over 223 observations;
- SNIPER: -0.1147R mean over 2,319 observations.

Across three independent 60-day windows:
- MAIN mean R: +0.1117, -0.0650, +0.0278 -> mixed, not a stable positive edge;
- SNIPER mean R: -0.1147, -0.1508, -0.1723 -> consistently negative after spread;
- m15_support_break_retest stayed positive in all three windows:
  +0.3229, +0.0988, +0.0180R;
- several high-frequency reasons stayed negative across all three windows,
  including fast_primary_2of3, mtf_countertrend_medium,
  mtf_medium_continuation, sniper_strength_stop_cap,
  technical_medium_local_invalidation, and technical_medium_recovered.

Research lesson:
- profit protection materially improves the distribution but does not create an
  edge by itself;
- a higher win rate can coexist with negative expectancy;
- historical reason-level priors remain SHADOW and cannot directly veto or
  promote live execution;
- fresh forward confirmation plus regime/macro/liquidity context is required
  before trusting any historical edge.


## Calibration discipline added

- The Gigi alignment score remains a context score, not a claimed win probability.
- Context scores are grouped only into coarse buckets:
  NEG_STRONG / NEG / ZERO / POS / POS_STRONG.
- Empirical positive-rate calibration requires at least 30 resolved shadow
  observations per bucket.
- Calibration reports include a 95% Wilson interval, sample size and mean R.
- A bucket is not called calibrated when the sample is small or the confidence
  interval is still too wide.
- The live shadow observer now writes a separate
  `gigi_calibration_report.json`; this report never changes execution.

## Wiring review

- LBMA AM/PM benchmark-auction context is now explicitly attached to the REAL
  shadow signal before context/thesis/readiness are evaluated.
- This fixed a wiring gap where the module existed and was previewed but the
  live shadow worker had not populated the benchmark field.
- Duplicate options-module import was removed.


## China / India local-premium layer — added 2026-10-04

World Gold Council's local gold premium/discount series is now tracked as slow
physical-demand context. WGC explicitly describes the series as an indicative
directional gauge, not a trading metric, so Gigi does not turn it into an
intraday BUY/SELL score.

Current public snapshot (data to 2026-09-25):
- China theoretical local premium: about +US$20.84/oz.
- China 1-year percentile in the public series: about 81% -> STRONG_PREMIUM.
- China 5-session change: about -US$3.49/oz; 20-session change: +US$14.62/oz.
- India theoretical local premium/discount: about -US$6.30/oz -> DISCOUNT.

Interpretation:
- China's premium is evidence of relatively firm local pricing versus the
  international benchmark, but it is not an M5 timing signal.
- A high premium can reflect local demand/supply tightness, import constraints
  and regional conditions; it must not be mistaken for a guaranteed global
  gold rally.
- Gigi records China and India states separately so future forward learning can
  test whether local premium regimes add useful information after controlling
  for trend, liquidity, yields and ETF flows.

## Options-sign correction — added 2026-10-04

Public GLD option-chain open interest is unsigned. A CALL_HEAVY or PUT_HEAVY
chain does not reveal whether customers or dealers are net long/short those
contracts. Gigi therefore no longer allows option OI imbalance to create a
directional squeeze/liquidation score by itself.

- OI imbalance is recorded as context only.
- 25-delta skew may amplify an already-existing liquidation/squeeze risk from
  independent evidence, but cannot create that risk from zero.
- Gross gamma*OI remains unsigned and is never labelled dealer gamma.
- This correction prevents a common options-analysis error: inferring dealer
  positioning from public open interest without trade-side inventory data.

## Structural demand remains slow context

World Gold Council Q2 2026 data showed central-bank net purchases rebounded to
about 289t, while H1 demand remained uneven. Its 2026 reserve-manager survey
also showed strong intentions to keep/increase gold holdings. Gigi treats this
as structural background only, not a timing signal: quarterly/official-reserve
demand cannot justify an intraday entry against fresh price structure.


## Recent broker-price walk-forward checkpoint — 2026-07-20 to 2026-10-02

A fresh price-only walk-forward was run on the broker's own XAUUSD history using
three non-overlapping blocks of 5,000 M5 bars. Historical broker spreads and the
candidate profit-protection replay were included. External slow feeds were
excluded to avoid look-ahead.

### Portfolio result after spread
- Window 1: mean R = -0.1228
- Window 2: mean R = -0.1235
- Window 3: mean R = -0.0878

This means the current technical engine as a whole is not yet validated as a
positive-expectancy system after spread.

### MAIN versus SNIPER
MAIN:
- +0.2425R
- -0.0514R
- +0.1420R

SNIPER:
- -0.1648R
- -0.1294R
- -0.1085R

The important finding is that the current SNIPER population was negative in all
three recent windows. MAIN was materially better but not stable-positive in all
three windows, so it also cannot be called proven.

### Strength score is not monotonic edge
The recent walk-forward did not show a simple rule that a higher 7-condition
score means higher expectancy. In particular, strength-6 observations were
strongly negative in all three windows, while strength-7 was positive in two
windows and negative in one. This reinforces the rule that 7/7 is alignment,
not a calibrated win probability.

### Stable-negative reason quarantine study
The existing long-window price prior marks several reasons stable-negative:
fast_primary_2of3, m15_resistance_break_retest, mtf_countertrend_medium,
mtf_medium_continuation, sniper_strength_stop_cap,
technical_medium_local_invalidation and technical_medium_recovered.

A research-only exclusion of those reasons improved the three recent windows:
- +0.1467R
- -0.0262R
- +0.0438R

That is a large improvement, but still not three-for-three positive. Therefore
the correct action is not to declare a new edge. These reasons should remain
high-attention/shadow candidates while better subsets are studied.

### Implication
Do not solve a negative price-only base by adding more correlated indicators.
Use the external layers (liquidity, macro, options, ETF, positioning, yields)
to form testable subsets, then validate those subsets out of sample before any
promotion.
