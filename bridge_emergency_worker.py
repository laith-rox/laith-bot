"""DEMO-only emergency manager for the isolated Laith execution bridge.

Uses fresh MT5 state reported by the EA. It never opens trades. It can only
close a bridge-owned XAUUSD DEMO position after confirmed adverse movement.
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
            "action": "CLOSE", "reason": reason}
    return req("/manage", "POST", body)


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
    accelerated_loss = (
        edge <= -max(0.60, 0.20 * risk)
        and short_momentum <= -max(0.20, 0.08 * risk)
        and long_momentum < 0
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


def validate_config():
    missing = [name for name, value in (
        ("BRIDGE_URL", BRIDGE_URL),
        ("BRIDGE_PUBLISH_TOKEN", TOKEN),
    ) if not value]
    if missing:
        raise RuntimeError("missing_config:" + ",".join(missing))


def run_forever():
    validate_config()
    prices = deque(maxlen=WINDOW)
    last_ticket = ""
    pressure = 0
    close_requested_ticket = ""
    ticks = 0
    print(
        f"bridge_emergency_started version=2 poll={POLL}s window={WINDOW} "
        f"confirm={CONFIRM} min_adverse={MIN_ADVERSE:.2f}",
        flush=True,
    )
    while True:
        try:
            status, health = req("/health")
            if status != 200 or health.get("mode") != "DEMO" or not health.get("client_state_fresh"):
                prices.clear(); pressure = 0; time.sleep(POLL); continue
            if not health.get("position_open") or not health.get("position_owned"):
                prices.clear(); pressure = 0; last_ticket = ""; close_requested_ticket = ""
                time.sleep(POLL); continue

            ticket = str(health.get("ticket") or "")
            side = str(health.get("side") or "").upper()
            try:
                price = float(health.get("price") or 0)
                stop = float(health.get("sl") or 0)
                entry = float(health.get("open_price") or 0)
            except (TypeError, ValueError):
                price = stop = entry = 0
            if not ticket or side not in ("BUY", "SELL") or min(price, stop, entry) <= 0:
                print("bridge_emergency_wait reason=position_fields_missing", flush=True)
                time.sleep(POLL); continue
            if ticket != last_ticket:
                prices.clear(); pressure = 0; last_ticket = ticket; close_requested_ticket = ""
                print(f"bridge_emergency_tracking ticket={ticket} side={side} entry={entry:.2f} stop={stop:.2f}", flush=True)
            if close_requested_ticket == ticket:
                time.sleep(POLL); continue

            prices.append(price)
            reason, hard = evaluate_emergency(health, list(prices))
            pressure = pressure + 1 if reason else max(0, pressure - 1)
            ticks += 1
            if ticks % HEARTBEAT_EVERY == 0:
                print(f"bridge_emergency_heartbeat ticket={ticket} side={side} price={price:.2f} pressure={pressure}/{CONFIRM} reason={reason or 'clear'}", flush=True)
            if reason and (hard or pressure >= CONFIRM):
                code, response = manage_close(ticket, reason)
                print(f"bridge_emergency_close ticket={ticket} reason={reason} hard={hard} http={code} response={response}", flush=True)
                if code == 201 and response.get("ok") is True:
                    close_requested_ticket = ticket
                pressure = 0
                prices.clear()
        except Exception as exc:
            print(f"bridge_emergency_error type={type(exc).__name__} detail={exc}", flush=True)
        time.sleep(POLL)


if __name__ == "__main__":
    run_forever()
