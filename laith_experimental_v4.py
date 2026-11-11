"""Run approved V4 manual-signal engine on the existing experimental Laith service.

Reuse only this service's existing Telegram and market credentials. Never place
orders. Preserve the old /data/laith.db for rollback.
"""
import os
import logging
import threading


def _gigi_api_preflight():
    """Opt-in one-off connectivity check, never blocks V4 or sends trades."""
    from gigi_persona import generate
    try:
        generate("جاوبي فقط: تمام")
    except RuntimeError as exc:
        safe_codes = {
            "gigi_auth_invalid", "gigi_permission_denied", "gigi_quota_exceeded",
            "gigi_rate_limited", "gigi_model_unavailable", "gigi_bad_request",
            "gigi_provider_unavailable", "gigi_network_timeout",
            "gigi_network_unavailable", "gigi_empty_reply", "gigi_unexpected_reply",
        }
        reason = str(exc)
        logging.getLogger("laith.v4.gigi").warning(
            "gigi_api_preflight_failed category=%s",
            reason if reason in safe_codes else "gigi_unknown_error",
        )
    except Exception:
        logging.getLogger("laith.v4.gigi").warning("gigi_api_preflight_failed category=gigi_unknown_error")
    else:
        logging.getLogger("laith.v4.gigi").info("gigi_api_preflight_ok")




def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    key = os.getenv("TWELVE_DATA_API_KEY")
    if not token or not chat or not key:
        raise RuntimeError("experimental_laith_missing_credentials")
    os.environ["V4_TELEGRAM_BOT_TOKEN"] = token
    os.environ["V4_TELEGRAM_CHAT_ID"] = chat
    os.environ["V4_TWELVE_DATA_API_KEY"] = key
    os.environ["V4_DB_PATH"] = "/data/laith_v4_experiment.db"
    # Explicit owner-approved BTC/USD Telegram signals on experimental Laith only.
    # This opt-in enables market analysis and Telegram alerts, NOT MT5/broker orders.
    os.environ["V4_BTC_SIGNALS_ENABLED"] = "1"
    # One BTC Telegram research idea per quarter-hour; weak ideas say NO ENTRY.
    os.environ["V4_BTC_QUARTERLY_REPORTS_ENABLED"] = "1"
    # Evening M5 quick-alert lane: paper/manual only, no broker orders.
    os.environ["V4_BTC_M5_QUICK_ENABLED"] = "1"
    # No verified broker calendar is fabricated. V4 must fail closed until supplied.
    import v4_group_runtime
    import v4_runtime
    if os.getenv("GIGI_API_PREFLIGHT") == "1" and os.getenv("GIGI_OPENAI_API_KEY"):
        threading.Thread(target=_gigi_api_preflight, daemon=True, name="gigi-api-preflight").start()
    v4_runtime.run(v4_runtime.parser().parse_args())


if __name__ == "__main__":
    main()
