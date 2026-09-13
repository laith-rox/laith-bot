# 2.6 — Observed deployment and saved-price delay audit

Observed on 2026-09-13. This is software release evidence and a retrospective development comparison, not a profitability validation.

## Release evidence

- Deployed code: `aa249007f7daf734fb225c2dd47aa8fc7f39d200` ([commit](https://github.com/laith-rox/laith-bot/commit/aa249007f7daf734fb225c2dd47aa8fc7f39d200)).
- Railway deployment: `c3eeca42-2895-4f56-898c-058de0cf3eaa`, status `SUCCESS`, last status update `2026-09-13T20:00:52.669Z`.
- Runtime at 20:00:50 UTC verified username `LaithGoldSignalsBot`, version `2.6.0`, persistent state enabled and owner commands enabled.
- Telegram acknowledged release notice `release:2.6.0`, message ID **398**. The ordinary new-week research notice was separately acknowledged as **399**.
- The measured-clock paper cohort started at `2026-09-13T20:00:50.479791+00:00`. No new-cohort trading performance is claimed at release.
- All **111** tests passed locally. The unchanged live pre-deployment command separately ran **72** slow-bot regression tests successfully. These counts describe different test scopes; the runtime gate was not changed.

The explicit deployment used the requested commit and existing live service configuration. Its only infrastructure mutation was `deployServiceTool`; the unrelated staged configuration was not committed. No original-bot or broker operation was performed.

## Saved-price comparison

Runtime logged the audit at 20:00:53 UTC. Source: 7,552 saved Twelve Data XAU/USD one-minute candles, covering `2026-09-06T04:00:00+00:00` through `2026-09-11T20:39:00+00:00`, with indicator warm-up prices and the matching retained scheduled-news calendar. This sample extends beyond the September 10 comparison and is not a new out-of-sample validation.

The schedule snapshot belongs to the week beginning `2026-09-06T00:00:00-04:00`; it is not a point-in-time history of calendar revisions. Both strategies are fixed. Observation delays and total round-trip costs are hypothetical, not measured JustMarkets values.

| Fixed strategy | Observation delay | Closed paper trades | Skipped fills | Net R at $0.50/ounce cost | Net R at $1.00/ounce cost |
|---|---:|---:|---:|---:|---:|
| Baseline breakout | 8 seconds | 40 | 10 | +4.6566 | -5.4508 |
| Baseline breakout | 68 seconds | 31 | 32 | +13.8305 | +6.2324 |
| Structure/retest | 8 seconds | 29 | 9 | -5.1624 | -12.0618 |
| Structure/retest | 68 seconds | 19 | 34 | -3.3344 | -7.9209 |

R is each modeled price outcome divided by its initial stop distance, after the stated hypothetical cost. It is not account-dollar profit. All four runs had zero open/pending trades at the end and zero excluded closed outcomes.

The retest candidate remains negative under both delay assumptions and both cost assumptions. The baseline changes sign when timing and cost assumptions change. Delays change which trades pass fill, time, news and subsequent daily-risk gates, so the rows are not the same set of trades with a constant deduction. Selecting the profitable 68-second case would be retrospective selection, not evidence that intentionally delaying signals improves future performance.

Decision: keep both fast strategies in paper-only comparison and collect the new timing fields prospectively. No thresholds were tuned to these results, no fast entry alerts were activated, and no success percentage was generated.

The separate current-week startup research recorded zero eligible signals and `NOT_VALIDATED_FOR_SIGNALS`; it is not evidence of trading accuracy.

Full parsed audit: [research/2026-09-13-timing-v1.json](research/2026-09-13-timing-v1.json). Method and limits: [TIMING.md](TIMING.md).
