# Gigi Gold Candidate — Release Freeze 2026-10-04

Status: **candidate frozen for final review; live execution is not activated by this release.**

## Decision stack

Regime -> H4/M15 structure -> M5 timing -> liquidity -> effort/result ->
intermarket -> macro/event response -> yields -> CFTC positioning -> ETF flows ->
GLD options proxy -> volatility -> crowding/liquidation risk -> stop/target geometry ->
execution quality -> exposure -> behavioral audit -> thesis/readiness -> shadow learning.

## Trading behavior represented in candidate

- New-entry analysis window: 05:00–20:00 Palestine local time.
- MAIN and SNIPER are allowed to coexist; one mode does not automatically block
  the other.
- London and US windows are context labels, not exclusive entry gates.
- Native MT5 H4 is required; synthetic H4 aggregation is rejected.
- Market-close/reopen freshness and warm-up checks reject stale candles.
- Reason-aware signal fingerprints reject the same idea twice while preserving
  independent setups.
- MAIN and SNIPER have separate mode-risk accounting, plus a global account hard
  risk cap.
- MAIN and SNIPER use separate profit-protection logic.

## Research / shadow layers

- dynamic intermarket relationships;
- USD event phase and first-spike/digestion logic;
- CFTC COMEX gold positioning;
- World Gold Council ETF regional flow breadth;
- Cboe GVZ and delayed GLD options proxy;
- 25-delta skew, put/call OI, unsigned gross gamma-OI concentration and term structure;
- realised-vs-implied volatility;
- squeeze / liquidation-risk context;
- real/front-end yield context;
- session VWAP/range profile and LBMA benchmark windows;
- data/execution quality, exposure, behavior and thesis audits;
- chronological replay, validation, drift, walk-forward and calibration.

External slow-data layers are context only. None is a standalone BUY/SELL trigger.

## Fail-closed safety gates

- correct REAL account/server and USD account are required locally;
- MT5 account trading / expert trading and terminal AutoTrading status are checked;
- bridge readiness uses one common blocker list for status/verify/next;
- stale broker ticks/source candles are rejected;
- executor rejects execution if account hard-risk cap is absent;
- restart emergency latch starts fail-closed;
- fixed 0.01 volume remains explicit;
- no stale market data is published after market close.

## Validation performed before freeze

- Full local candidate discovery suite: **260 tests passed** (latest verification on 2026-10-04).
- All candidate Python modules plus VPS candidate executor, relay and learning
  observer compile successfully.
- Live external source smoke tests returned usable CFTC, WGC ETF, Cboe options,
  GVZ, yield and macro-calendar data.
- Learning observer is running in shadow mode and does not place orders.

## Deliberate non-actions

This freeze does **not** enable MT5 AutoTrading, does not clear the emergency
restart latch, does not set an account hard-risk cap on the user's behalf, and
does not place or submit a real order.


## Latest verification — 2026-10-04

- Python discovery suite: **260/260 passed**.
- All candidate Python modules plus the VPS candidate executor, relay and
  learning observer compiled successfully.
- Live slow-source smoke checks succeeded:
  - CFTC report: 2026-09-29, LONG_BIASED_DELEVERAGING;
  - WGC ETF: 2026-09-25, MIXED_INFLOW;
  - Cboe GLD options: delayed underlying last trade 2026-10-02 15:59:59,
    balanced 25-delta skew, CALL_HEAVY OI proxy, moderate near-spot convexity;
  - GVZ: 23.23 on 2026-10-02, LOW versus its recent one-year history.
- Options expiry/OI, gamma-OI and skew remain explicitly unsigned/context-only;
  no dealer-position sign is inferred.
- No production execution state was changed during this verification.
