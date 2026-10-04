# Gigi Proof Gate

Status: FEATURE FREEZE / SHADOW VALIDATION

The goal is no longer to add more indicators. The goal is to prove which
existing evidence families improve decisions without creating correlated
double-counting or overfitting.

## Evidence families

All tools are collapsed into only five independent families:

1. PRICE_STRUCTURE
2. MACRO_POLICY
3. FLOWS_POSITIONING
4. OPTIONS_VOLATILITY
5. CROSS_MARKET_PHYSICAL

Multiple inputs inside one family can explain the context but cannot manufacture
extra independent votes.

## Rules during proof phase

- No new analytical layer earns execution authority.
- Raw option open interest is unsigned; it cannot be treated as bullish/bearish
  without trade-side/dealer-position evidence.
- CFTC + ETF + crowding are one related flow family.
- Volatility describes state/speed, not direction.
- External slow data never overrides fresh broker-native H4/M15/M5 price.
- Alignment score is not win probability.
- Shadow learning cannot mutate live parameters automatically.
- A bucket needs at least 20 resolved observations before calibration language.
- A weight needs at least 30 observations plus out-of-sample stability and drift
  checks before it can even be suggested as a bounded shadow weight.
- If a feature does not add stable out-of-sample value, remove or demote it.
- Market-closed/stale/reopen warmup remains fail-closed for analysis freshness.

## What proves Gigi

For each resolved shadow setup record:

- R outcome, MFE_R, MAE_R;
- setup archetype and MAIN/SNIPER request;
- five evidence-family votes;
- regime/session/event phase;
- stop and target geometry;
- data/execution quality;
- whether context agreed, contradicted, or added no value.

Compare baseline technical setup vs the same setup with each evidence family.
The feature survives only if its out-of-sample contribution is stable and does
not simply duplicate another family.

## Current deployment rule

Candidate/shadow only. Do not use this proof layer to enable, arm, or approve
REAL autonomous order execution.
