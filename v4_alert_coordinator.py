"""Manual-only V4 alert coordinator. Source verification stays with adapters.

The caller provides independently verified broker sessions, quote timestamps,
and verified economic calendar events. No network calls, no broker orders.
"""
from v4_alert_delivery import deliver_once
from v4_alert_planner import plan_market_close_notice, plan_verified_news_notices


def run_alert_cycle(now, *, store, notifier, broker_sessions, quote_at,
                    verified_news_events=(), weekly_close=False):
    """Send due alerts once and report delivery outcomes without fabricating data."""
    delivered = []
    close = plan_market_close_notice(now, broker_sessions, quote_at, weekly=weekly_close)
    if close and deliver_once(store, notifier, close):
        delivered.append(close["key"])
    for notice in plan_verified_news_notices(now, verified_news_events):
        if deliver_once(store, notifier, notice):
            delivered.append(notice["key"])
    return delivered
