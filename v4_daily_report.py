"""Pure daily V4 paper-trade report, local Palestine time.

Integration with the runtime/Telegram scheduler is intentionally separate.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

LOCAL = ZoneInfo("Asia/Hebron")


def _local_day(timestamp):
    if timestamp is None:
        return None
    try:
        return datetime.fromtimestamp(float(timestamp), LOCAL).date()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def daily_trade_counts(official, quick, day):
    """Count only resolved, timestamped paper trades closed on the given local day.

    A zero-R or ambiguous outcome is unresolved, not a loss.
    """
    result = {}
    for name, trades in (("official", official), ("quick", quick)):
        wins = losses = unresolved = 0
        for trade in trades:
            if trade.get("status") != "closed" or _local_day(trade.get("closed")) != day:
                continue
            try:
                r = float(trade.get("r"))
            except (TypeError, ValueError):
                unresolved += 1
                continue
            if r != r or r in (float("inf"), float("-inf")) or r == 0:
                unresolved += 1
            elif r > 0:
                wins += 1
            else:
                losses += 1
        result[name] = {"wins": wins, "losses": losses, "unresolved": unresolved}
    wins = sum(v["wins"] for v in result.values())
    losses = sum(v["losses"] for v in result.values())
    result["total"] = {
        "wins": wins, "losses": losses,
        "unresolved": sum(v["unresolved"] for v in result.values()),
        "win_rate": round(100 * wins / (wins + losses), 1) if wins + losses else None,
    }
    return result


def should_send_report(now, last_sent_day):
    local = now.astimezone(LOCAL)
    return (local.hour == 23 and local.minute >= 30
            and local.date().isoformat() != last_sent_day)
