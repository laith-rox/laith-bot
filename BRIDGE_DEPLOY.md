# Laith Execution Bridge deployment

This branch hosts the isolated DEMO-only execution bridge.

Railway service start command: `python bridge_api.py`.
MT5 client: `mt5/LaithDemoBridge.mq5`.

Live accounts are blocked by the EA and the bridge accepts DEMO commands only.


## Independent signal worker

The automatic DEMO publisher runs as a separate Railway service using:

`python bridge_signal_worker.py`

It is isolated from V4 and the legacy bot. It reads a keyless 5-minute gold-market proxy feed for DEMO commissioning,
requires at least 6 of 7 mirrored directional checks, publishes at most two
new DEMO orders per hour, and skips publishing while the bridge reports an
open position, a pending command, stale MT5 state, or a disabled bridge.

Required worker variables:
- `TWELVE_DATA_API_KEY`
- `BRIDGE_URL`
- `BRIDGE_PUBLISH_TOKEN`

The execution bridge and EA remain the final safety gate: DEMO-only,
XAUUSD-only, 0.01 lot, one open position.


### Commissioning compatibility

If an older installed EA polls `/next` but does not yet report `/state`, the
worker may be started with `ALLOW_STALE_MT5_STATE=true` for commissioning
only. In that mode, keep `MAX_PUBLISH_PER_HOUR=1`. The EA's local safety
gate must still enforce DEMO account, XAUUSD, 0.01 lot, one gold position max,
valid SL/TP, and its local kill switch/risk budget.
