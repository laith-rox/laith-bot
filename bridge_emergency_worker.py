"""DEMO-only emergency manager for the isolated Laith execution bridge.

Uses fresh MT5 state reported by the EA. It never opens trades. It can only
close a bridge-owned XAUUSD DEMO position after confirmed adverse movement.

v3 adds a lifetime Profit Guardian: once a trade has meaningful floating
profit, the manager remembers the highest profit seen for that ticket and can
close on confirmed giveback before a formerly profitable trade reaches its
original stop. SL/TP are never modified.
"""
from __future__ import annotations

from collections import deque
import json
import os
import time
from urllib.request import Request, urlopen

BRIDGE_URL = os.getenv("BRIDGE_URL", "").rstrip("/")
TOKEN = os.getenv("BRIDGE_PUBLISH_TOKEN", "")
POLL = max(2, int(os.getenv("EMERGENCY_POLL_SECONDS", "5")))
WINDOW = max(8, int(os.getenv("EMERGENCY_WINDOW", "18")))
MIN_ADVERSE = max(0.20, float(os.getenv("EMERGENCY_MIN_ADVERSE_USD", "0.80")))
CONFIRM = max(1, int(os.getenv("EMERGENCY_CONFIRM", "2")))
HEARTBEAT_EVERY = max(6, int(os.getenv("EMERGENCY_HEARTBEAT_EVERY", "12")))
PROFIT_GUARD_ARM_USD = max(0.50, float(os.getenv("PROFIT_GUARD_ARM_USD", "1.00")))
PROFIT_GUARD_MIN_GIVEBACK_USD = max(0.20, float(os.getenv("PROFIT_GUARD_MIN_GIVEBACK_USD", "0.40")))


def req(path, method="GET", payload=None):
    data = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
        headers["X-Publish-Token"] = TOKEN
    request = Request(BRIDGE_URL + path, data=data, method=method, headers=headers)
    with urlopen(request, timeout=8) as response:
        raw = response.read().decode()
        return response.status, json.loads(raw) if raw else {}


def manage_close(ticket, reason):
    key = f"emg:{ticket}:{int(time.time())}"
    body = {"mode": "DEMO", "key": key, "symbol": "XAUUSD",
            "action": "CLOSE", "ticket": str(ticket), "reason": reason}
    return req("/manage", "POST", body)


def protected_profit_floor(peak_profit):
    """Profit floor used only after the guardian has armed."""
    if peak_profit < PROFIT_GUARD_ARM_USD:
        return None
    if peak_profit < 2.0:
        return max(0.20, 0.35 * peak_profit)
    if peak_profit < 3.0:
        return 0.50 * peak_profit
    if peak_profit < 5.0:
        return 0.60 * peak_profit
    return 0.70 * peak_profit


def evaluate_profit_guardian(state, price_samples, profit_samples, peak_profit):
    """Return (reason, hard) when lifetime floating profit needs protection.

    A hard floor protects a substantial part of an established peak. Before
    that floor is reached, a softer correction exit requires both a meaningful
    giveback and confirmed adverse movement. This avoids treating every small
    pullback as an emergency.
    """
    try:
        current_profit = float(state.get("profit") or 0)
        current_price = float(state.get("price") or 0)
    except (TypeError, ValueError):
        return None, False
    side = str(state.get("side") or "").upper()
    if side not in ("BUY", "SELL") or current_price <= 0:
        return None, False

    peak_profit = max(float(peak_profit or 0), current_profit)
    floor = protected_profit_floor(peak_profit)
    if floor is None:
        return None, False

    # If a profitable trade gives back enough to reach the protected floor,
    # request an immediate close. This is deliberately independent of TP/SL.
    if current_profit <= floor:
        return "profit_guardian_floor", True

    if len(price_samples) < 3 or len(profit_samples) < 3:
        return None, False

    direction = 1.0 if side == "BUY" else -1.0
    adverse_price = direction * (float(price_samples[-1]) - float(price_samples[-3])) < 0
    falling_profit = (
        float(profit_samples[-1]) < float(profit_samples[-2])
        and float(profit_samples[-2]) < float(profit_samples[-3])
    )
    giveback = peak_profit - current_profit
    correction_trigger = max(PROFIT_GUARD_MIN_GIVEBACK_USD, 0.20 * peak_profit)

    if giveback >= correction_trigger and falling_profit and adverse_price:
        return "profit_guardian_confirmed_correction", False
    return None, False


def evaluate_emergency(state, samples):
    """Return (reason, hard) for an adverse setup, else (None, False)."""
    if len(samples) < 6:
        return None, False
    side = str(state.get("side") or "").upper()
    if side not in ("BUY", "SELL"):
        return None, False
    try:
        price = float(state.get("price") or samples[-1])
        entry = float(state.get("open_price") or 0)
        stop = float(state.get("sl") or 0)
    except (TypeError, ValueError):
        return None, False
    if min(price, entry, stop) <= 0:
        return None, False

    direction = 1.0 if side == "BUY" else -1.0
    risk = max(0.01, direction * (entry - stop))
    stop_room = direction * (price - stop)
    edge = direction * (price - entry)
    edges = [direction * (float(value) - entry) for value in samples]
    best_edge = max(edges)
    giveback = best_edge - edge
    short_momentum = direction * (float(samples[-1]) - float(samples[-3]))
    long_momentum = direction * (float(samples[-1]) - float(samples[0]))

    near_stop = stop_room <= max(0.25, 0.18 * risk)
    # Do not mistake a normal early pullback for a true accelerating loss.
    # This exit now needs a deeper move (roughly half the planned stop risk),
    # a longer observation window, and adverse momentum on both horizons.
    # Near-stop remains an immediate hard exit below.
    accelerated_loss = (
        len(samples) >= 10
        and edge <= -max(1.00, 0.50 * risk)
        and short_momentum <= -max(0.30, 0.10 * risk)
        and long_momentum <= -max(0.45, 0.15 * risk)
    )
    failed_breakout = (
        best_edge >= max(0.35, 0.12 * risk)
        and edge <= -max(0.20, 0.08 * risk)
        and giveback >= max(MIN_ADVERSE, 0.30 * risk)
        and short_momentum < 0
    )
    adverse_reversal = (
        giveback >= max(MIN_ADVERSE, 0.28 * risk)
        and short_momentum < 0
        and long_momentum < 0
    )

    if near_stop:
        return "emergency_near_stop", True
    if failed_breakout:
        return "emergency_failed_breakout", False
    if accelerated_loss:
        return "emergency_accelerating_loss", False
    if adverse_reversal:
        return "emergency_confirmed_reversal", False
    return None, False


def select_exit_reason(emergency_reason, emergency_hard, guardian_reason, guardian_hard):
    """Runtime policy: guard profit, or act only on hard last-resort danger.

    Soft loss-side pattern detections remain diagnostic signals, but they are
    deliberately not allowed to close a DEMO position. This gives normal
    pullbacks room to recover while the broker SL and near-stop emergency stay
    intact.
    """
    if guardian_hard:
        return guardian_reason, True
    if emergency_hard:
        return emergency_reason, True
    if guardian_reason:
        return guardian_reason, False
    return None, False


def validate_config():
    missing = [name for name, value in (
        ("BRIDGE_URL", BRIDGE_URL),
        ("BRIDGE_PUBLISH_TOKEN", TOKEN),
    ) if not value]
    if missing:
        raise RuntimeError("missing_config:" + ",".join(missing))


def run_forever():
    validate_config()
    tracked = {}
    ticks = 0
    print(
        f"bridge_emergency_started version=3.3-multiposition poll={POLL}s window={WINDOW} "
        f"confirm={CONFIRM} min_adverse={MIN_ADVERSE:.2f} "
        f"profit_guard_arm={PROFIT_GUARD_ARM_USD:.2f} "
        f"profit_guard_min_giveback={PROFIT_GUARD_MIN_GIVEBACK_USD:.2f}",
        flush=True,
    )
    while True:
        try:
            status, health = req("/health")
            if status != 200 or health.get("mode") != "DEMO" or not health.get("client_state_fresh"):
                tracked.clear(); time.sleep(POLL); continue

            positions = health.get("positions")
            if not isinstance(positions, list) or not positions:
                positions = [health] if health.get("position_open") and health.get("position_owned") else []
            owned = [p for p in positions if bool(p.get("owned", p.get("position_owned", False)))]
            live_tickets = {str(p.get("ticket") or "") for p in owned}
            for stale in list(tracked):
                if stale not in live_tickets:
                    tracked.pop(stale, None)

            if not owned:
                time.sleep(POLL); continue

            for position in owned:
                ticket = str(position.get("ticket") or "")
                side = str(position.get("side") or "").upper()
                try:
                    price = float(position.get("price") or health.get("price") or 0)
                    stop = float(position.get("sl") or 0)
                    entry = float(position.get("open_price") or 0)
                    profit = float(position.get("profit") or 0)
                except (TypeError, ValueError):
                    continue
                if not ticket or side not in ("BUY","SELL") or min(price,stop,entry) <= 0:
                    continue

                state = tracked.get(ticket)
                if state is None:
                    state = {"prices":deque(maxlen=WINDOW),"profits":deque(maxlen=WINDOW),
                             "peak":max(0.0,profit),"pressure":0,"close_requested":False}
                    tracked[ticket]=state
                    print(f"bridge_emergency_tracking ticket={ticket} side={side} entry={entry:.2f} stop={stop:.2f} profit={profit:.2f}",flush=True)
                if state["close_requested"]:
                    continue

                state["prices"].append(price); state["profits"].append(profit)
                state["peak"]=max(state["peak"],profit)
                eval_state=dict(position); eval_state["price"]=price
                emergency_reason, emergency_hard = evaluate_emergency(eval_state, list(state["prices"]))
                guardian_reason, guardian_hard = evaluate_profit_guardian(
                    eval_state, list(state["prices"]), list(state["profits"]), state["peak"])
                reason, hard = select_exit_reason(emergency_reason, emergency_hard, guardian_reason, guardian_hard)
                state["pressure"] = state["pressure"] + 1 if reason else max(0,state["pressure"]-1)
                ticks += 1
                if ticks % HEARTBEAT_EVERY == 0:
                    floor=protected_profit_floor(state["peak"])
                    print(f"bridge_emergency_heartbeat ticket={ticket} side={side} price={price:.2f} profit={profit:.2f} peak_profit={state['peak']:.2f} protected_floor={'off' if floor is None else f'{floor:.2f}'} pressure={state['pressure']}/{CONFIRM} reason={reason or 'clear'}",flush=True)
                if reason and (hard or state["pressure"] >= CONFIRM):
                    code,response=manage_close(ticket,reason)
                    print(f"bridge_emergency_close ticket={ticket} reason={reason} hard={hard} profit={profit:.2f} peak_profit={state['peak']:.2f} http={code} response={response}",flush=True)
                    if code==201 and response.get("ok") is True:
                        state["close_requested"]=True
                    state["pressure"]=0
        except Exception as exc:
            print(f"bridge_emergency_error type={type(exc).__name__} detail={exc}",flush=True)
        time.sleep(POLL)


if __name__ == "__main__":
    run_forever()
