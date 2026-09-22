# Laith Execution Bridge deployment

This branch hosts the isolated DEMO-only execution bridge.

Railway service start command: `python bridge_api.py`.
MT5 client: `mt5/LaithDemoBridge.mq5`.

Live accounts are blocked by the EA and the bridge accepts DEMO commands only.


## Independent signal worker

The automatic DEMO publisher runs as a separate Railway service using:

`python bridge_signal_worker.py`

It is isolated from V4 and the legacy bot. It reads a keyless 5-minute gold-market proxy feed for DEMO commissioning,
requires at least 6 of 7 mirrored directional checks, and skips publishing while the bridge reports an
open position, a pending command, stale MT5 state, or a disabled bridge.
`MAX_PUBLISH_PER_HOUR=0` removes the hourly count limit; positive values retain
a cap. Signals are still evaluated once per distinct closed five-minute bar.

Required worker variables:
- `BRIDGE_URL`
- `BRIDGE_PUBLISH_TOKEN`

The execution bridge and EA remain the final safety gate: DEMO-only,
XAUUSD-only, 0.01 lot, one open position.


### Commissioning compatibility

If an older installed EA polls `/next` but does not yet report `/state`, the
worker may be started with `ALLOW_STALE_MT5_STATE=true` for DEMO commissioning.
Compatibility requires a successful authenticated `/next` request within ten
seconds and no previously reported state. It never marks missing state as fresh,
and it blocks if a reporting EA stops reporting or the legacy EA disconnects.
The hourly cap is independent and can be zero when authorized by the user.
The EA's local safety gate still enforces DEMO account, XAUUSD, 0.01 lot, one
gold position max, valid SL/TP, and its configured local kill switch/risk budget.
Remote position management and risk-wallet visibility require the reporting EA.

The API logs `bridge_order_published` and `bridge_order_ack` with the order key,
side and MT5 result. Publishing or HTTP 200 alone does not prove a filled trade;
inspect the acknowledgement's success, broker retcode and ticket.
