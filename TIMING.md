# 2.6 — Decision timing and delay sensitivity

## Problem and scope

The fast worker previously supplied its pre-request cycle timestamp to both analyzers. HTTP, calendar, SQLite and analysis work could therefore precede the recorded decision while being omitted from its source-age check. Historical research assumed availability eight seconds after candle close. A paper-open log recorded when a completed fill candle was processed; it was neither the original decision timestamp nor a measured broker fill.

This release corrects these execution assumptions. It keeps both fixed strategy rules (`fast-v1` and `structure-retest-v1`), their thresholds and the fast paper-only gate. It makes no broker orders, requests no new subscription, and does not change the original bot.

## Behavior

- An anchor timestamp plus monotonic elapsed time covers price requests, news requests, analysis and the two sequential paper streams. The slow report cycle also refreshes its clock after command polling, price retrieval, analysis and news retrieval.
- Freshness is rechecked before staging: at most 90 seconds after the last one-minute candle closes, and 120 seconds for the slow five-minute strategy. An elapsed request or calculation cannot bypass that limit. Session and scheduled-news gates are rechecked for paper decisions.
- Stale one-minute prices may advance an existing paper watch but cannot open another. Missing price intervals still invalidate an outcome; they are not counted as measured profit.
- New decisions save `decision_time`, `source_age_at_decision_seconds` and `execution_model=observed-clock-v1`. Paper trades preserve those fields and add `fill_observed_at`. `announced` retains its existing paper-fill-at-bar-open meaning for lifecycle compatibility.
- A modeled fill must be at the first available full minute starting strictly after the decision, within 120 seconds of it; a pending decision must be observed within 180 seconds. These are conservative paper rules, not exchange executions or guaranteed attainable fills.
- `fast_last_fetch` records request start, receipt, elapsed request time and source candle age. Source age includes candle publication delay and polling schedule; it is not measured JustMarkets latency. `fill_observed_at` is when this worker processes the candle, not a broker acknowledgement.
- Calendar requests evaluate blackout and cache validity at completion. Weekly schedule snapshots are retained for later research. They are not a point-in-time archive of schedule revisions, consensus or actual releases.

## Research and cohort separation

The saved-history audit compares the same fixed rules under hypothetical 8-second and 68-second observation delays and hypothetical total round-trip costs of $0.50 and $1.00 per ounce. It models delayed availability, rejects stale decisions, and cannot use the candle already in flight for entry. It does not optimize a delay or strategy parameter for profit. Results are explicitly `DEVELOPMENT_DELAY_SENSITIVITY_NOT_VALIDATION`.

The audit requires at least 600 saved candles in a week with a matching retained news calendar. It may use a previous archived week after rollover. Without matching coverage it reports that the audit is waiting, rather than treating unknown news as an empty calendar. It runs at startup and can retry outside the fast session at most once daily; it does not make additional market-data requests. Each week/model audit is saved once as a development snapshot, not a continuously updated performance score.

A one-time migration expires unfilled legacy paper decisions. Existing active watches and completed records retain their original model. `/fast` compares new observations only when their execution model and decision time match the new cohort; restart does not reset its start. The older aggregate remains clearly identified as the all-time paper record.

The historical baseline and retest results previously recorded in `FAST_RESEARCH_RESULT.md` and `STRUCTURE_RETEST_RESULT.md` remain historical evidence from their respective models. They are not recomputed silently or presented as measured-clock forward results.

## Verification

`python -m unittest -q test_bot test_fast test_candidate test_timing`

111 tests passed locally on 2026-09-13: 97 existing tests and 14 timing regressions. The regressions cover independent market/news/analysis delay, distinct decision and fill-observation timestamps, session/news boundary crossings, stale-data lifecycle continuity, forbidden pre-decision fills, historical delay sensitivity and invalid delays, slow-report freshness, calendar request timing/week rollover, legacy cohort exclusion and restart, and missing/matching archived calendar coverage.

Two old test fixtures were corrected: a delivery claim now occurs after processing time, and the second report receives newly timestamped candles instead of reusing prices fifteen minutes old. No entry gate was relaxed to make tests pass.

Synthetic/mocked tests verify software behavior only. Profitability, actual broker costs, variable provider latency, tick-level fill order and out-of-sample performance remain unvalidated. Live release checks and any saved-history results are documented separately in `TIMING_RESULT.md` once observed.
