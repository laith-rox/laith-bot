# Laith V3 Research Notes — 2026-09-16

This memo records the evidence used to design the current research layer. It is not a claim of guaranteed profitability. The purpose is to make every rule traceable, testable and removable if it fails out-of-sample.

## 1. Support / resistance and clustered orders

**Federal Reserve Bank of New York — Carol Osler, “Support for Resistance: Technical Analysis and Intraday Exchange Rates” (2000)**
- Empirical evidence found dealer-supplied support/resistance levels helped predict intraday trend interruptions in the currencies studied.
- Implementation consequence: V3 represents levels as *zones*, not exact magic prices, and records whether price interrupts/rejects there.
- Source: https://www.newyorkfed.org/research/epr/00v06n2/0007osle.html

**Federal Reserve Bank of New York — Carol Osler, “Currency Orders and Exchange-Rate Dynamics” (2001/2003)**
- Stop-loss and take-profit orders were found to cluster at predictable levels/round numbers; crossings and reversals can have different dynamics.
- Implementation consequence: V3 distinguishes intact levels, confirmed breaks, retests, and failed breaks rather than treating every touch the same.
- Source: https://www.newyorkfed.org/research/staff_reports/sr125.html

## 2. Technical patterns should be objective, not eyeballed

**Lo, Mamaysky & Wang — “Foundations of Technical Analysis” (NBER / Journal of Finance, 2000)**
- Shows that technical patterns can be transformed from subjective chart drawings into systematic algorithms and then tested statistically.
- Implementation consequence: V3 only uses mechanically confirmed pivots (2 bars left + 2 bars right), deterministic clustering, and fixed causal rules.
- Source: https://www.nber.org/papers/w7613

## 3. Trend following and loss control

**Hurst, Ooi & Pedersen — “A Century of Evidence on Trend-Following Investing” (2017)**
- Documents long-run evidence for trend-following across multiple asset classes and emphasizes loss cutting / letting trends run as a general principle.
- Implementation consequence: V3 does not counter-trend trade merely because price pulled back. The correction engine is primarily a *do-not-enter-too-early* tool inside the dominant trend.
- Source: https://www.aqr.com/insights/research/journal-article/a-century-of-evidence-on-trend-following-investing

**CMT Association material on Seykota / trend following / money management**
- Repeated practitioner emphasis on systematic trend rules, cutting losses and money management.
- Implementation consequence: V3 separates setup quality from risk management and records the exact stop invalidation logic for every paper trade.
- Sources:
  - https://cmtassociation.org/technically_speaking/technically-speaking-february-2020/
  - https://cmtassociation.org/technical_insights/technical-insights-november-2020/

## 4. Stop losses are not automatically beneficial if they are too tight

**Kaminski & Lo — “When Do Stop-Loss Rules Stop Losses?” (Journal of Financial Markets, 2014)**
- Stop-loss rules can reduce risk in some conditions, but their benefit depends on the process and costs; they are not universally optimal.
- Later work by Lo & Remorov also shows tight stops can underperform when transaction costs dominate.
- Implementation consequence: V3 stops are not arbitrary fixed-dollar stops. They sit beyond a structural invalidation zone plus an ATR buffer, have a minimum width (0.65 ATR), and reject trades requiring excessively wide stops (>2.20 ATR).
- Sources:
  - https://dspace.mit.edu/entities/publication/bb69ca4b-0cdc-487f-831d-63b2e84fafee
  - https://alo.mit.edu/topic/risk-management-and-systemic-risk/

## 5. Failed breakouts / springs / upthrusts are worth testing, but remain hypotheses

**Wyckoff educational material (StockCharts)**
- Describes springs and upthrusts as breaks beyond support/resistance that reverse back into the range, and retests as relevant context.
- This is practitioner methodology, not proof that every spring/upthrust is profitable.
- Implementation consequence: V3 records a `FAILED_BREAK` when price wicks through a zone with an ATR buffer and closes back inside; it does not automatically reverse direction, it only vetoes the conflicting entry until evidence improves.
- Source: https://chartschool.stockcharts.com/table-of-contents/market-analysis/wyckoff-analysis-articles/the-wyckoff-method-a-tutorial

## 6. Gold-specific price discovery and event behavior

**Hauptfleisch, Putniņš & Lucey — “Who Sets the Price of Gold? London or New York” (Journal of Futures Markets, 2016)**
- Both London spot and New York futures contribute to price discovery; New York futures play a major role and the contribution varies intraday and around macro announcements.
- Implementation consequence: V3 keeps explicit session labels and treats COMEX/futures volume and VWAP as a planned shadow-data layer rather than assuming spot-only structure is complete.
- Source: https://onlinelibrary.wiley.com/doi/10.1002/fut.21775

**Awartani, Hussain & Virk — gold intraday reaction to monetary policy shocks (2024)**
- Using 5-minute gold futures data, finds price/volatility adjustment can continue beyond the first 5 minutes after FOMC shocks.
- Implementation consequence: V3 retains news blackout and will separately test post-event stabilization/re-entry windows instead of immediately treating the first reaction as final trend confirmation.
- Source: https://www.sciencedirect.com/science/article/abs/pii/S1057521924004186

**Federal Reserve research on macro news / investor attention and jumps**
- Market responses to macro surprises vary with attention, disagreement and regime; high-frequency volume and volatility can surge around announcements.
- Implementation consequence: future V3 news-surprise engine must use actual-vs-consensus standardized by event family and cannot assign a permanent fixed sign/weight to all CPI/FOMC releases.
- Sources:
  - https://www.federalreserve.gov/econres/feds/how-markets-process-macro-news-the-importance-of-investor-attention.htm
  - https://www.federalreserve.gov/econres/feds/macroeconomic-news-announcements-systemic-risk-financial-market-volatility-and-jumps.htm
  - https://www.federalreserve.gov/econres/ifdp/trading-activity-and-exchange-rates-in-high-frequency-ebs-data.htm

## 7. Current V3 structural rules created from the research

The live bot is unchanged. The research branch now tests:

- confirmed 15m + 1h swing zones rather than single exact support/resistance lines;
- ATR-scaled zone width;
- nearest support and resistance with repeated-touch scoring;
- two-close breakout confirmation with an ATR buffer;
- retest-held detection;
- failed-break / rejection detection;
- correction start zone from the last causally confirmed impulse extreme;
- correction strength as completed conditions (weak/medium/strong), **not win probability**;
- primary correction destinations from structural zones, with 38.2/50/61.8 retracement marks stored only as research reference points;
- structural stop beyond invalidation + ATR buffer;
- rejection if the stop required is abnormally wide;
- rejection if the nearest opposing structure leaves less than 1.15R of room;
- TP1 at 1.40R and TP2 at 2.20R for the current experiment so payout is measurable and comparable;
- no automatic opposite trade from a failed breakout or correction warning.

## 8. What still needs data before promotion

No feature should move to `main` until it survives out-of-sample comparison. Planned shadow layers:

- COMEX Gold futures volume / VWAP and, if reliable access is obtained, order-flow imbalance;
- open interest and options-implied volatility (GVZ/CVOL-like context);
- intraday U.S. dollar and Treasury-rate confirmation;
- standardized economic surprise engine (actual - consensus, normalized by historical surprise volatility);
- event-specific post-news stabilization windows;
- round-number proximity as a separately measured feature;
- multiple walk-forward periods and cost stress tests.

Every failed experiment remains part of the audit trail. We will not keep a rule just because it looks impressive on one chart.
