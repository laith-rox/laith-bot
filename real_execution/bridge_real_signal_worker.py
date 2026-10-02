"""Future REAL signal runner. Disabled and fail-closed by default.

When explicitly configured later it reuses the tested gold analysis engine, but
publishes REAL commands only to the isolated REAL bridge.
"""
from __future__ import annotations

from collections import deque
import json
import os
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

REAL_SIGNAL_ENABLED = os.getenv("REAL_SIGNAL_ENABLED", "false").strip().lower() == "true"
BRIDGE_URL = os.getenv("REAL_BRIDGE_URL", "").strip().rstrip("/")
PUBLISH_TOKEN = os.getenv("REAL_BRIDGE_PUBLISH_TOKEN", "").strip()
VOLUME = float(os.getenv("REAL_VOLUME", "0") or 0)
POLL_SECONDS = int(os.getenv("REAL_POLL_SECONDS", "30"))
MAX_PUBLISH_PER_HOUR = int(os.getenv("REAL_MAX_PUBLISH_PER_HOUR", "0") or 0)


def _json_request(url, method="GET", payload=None, headers=None, timeout=8):
    data = None
    hs = {"Accept": "application/json"}
    if headers:
        hs.update(headers)
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode()
        hs["Content-Type"] = "application/json"
    req = Request(url, data=data, method=method, headers=hs)
    try:
        with urlopen(req, timeout=timeout) as res:
            raw = res.read().decode()
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode() if exc.fp else ""
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {"detail": raw[:200]}
        return exc.code, payload


def config_reason():
    if not REAL_SIGNAL_ENABLED:
        return "real_signal_disabled"
    if not BRIDGE_URL or not PUBLISH_TOKEN:
        return "real_signal_auth_not_configured"
    if VOLUME <= 0:
        return "real_signal_volume_not_configured"
    if MAX_PUBLISH_PER_HOUR <= 0:
        return "real_signal_hourly_cap_not_configured"
    return None


def bridge_health():
    status, payload = _json_request(f"{BRIDGE_URL}/health")
    if status != 200:
        raise RuntimeError(f"bridge_health_http_{status}")
    return payload


def run_forever():
    print(
        "REAL_SIGNAL_START "
        f"enabled={REAL_SIGNAL_ENABLED} volume_configured={VOLUME > 0} "
        f"hourly_cap_configured={MAX_PUBLISH_PER_HOUR > 0}",
        flush=True,
    )
    publishes = deque()
    while True:
        reason = config_reason()
        if reason:
            print(f"real_signal_wait reason={reason}", flush=True)
            time.sleep(POLL_SECONDS)
            continue

        health = bridge_health()
        if not health.get("ready"):
            print(
                "real_signal_wait reason=real_bridge_not_ready "
                f"armed={health.get('armed')} execution_enabled={health.get('execution_enabled')} "
                f"configured={health.get('configured')}",
                flush=True,
            )
            time.sleep(POLL_SECONDS)
            continue

        # Intentionally no signal-to-order handoff yet. This is the last safety
        # boundary before live execution and will be wired only after the REAL
        # MT5 EA and user-selected financial limits are configured and verified.
        print("real_signal_wait reason=live_handoff_not_enabled", flush=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    run_forever()
