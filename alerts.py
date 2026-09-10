"""Informational early watches and reversal alerts, separate from trade statistics."""
import math
from datetime import datetime


def leading_side(d):
    if not all(k in d for k in ('price', 'atr', 'buy', 'sell', 'price_time', 'checks')):
        return None
    if not all(math.isfinite(d[k]) and d[k] > 0 for k in ('price', 'atr')):
        return None
    if d['buy'] >= 4 and d['buy'] - d['sell'] >= 2:
        return 'BUY'
    if d['sell'] >= 4 and d['sell'] - d['buy'] >= 2:
        return 'SELL'
    return None


def early_candidate(d):
    side = leading_side(d)
    if d['side'] != 'WAIT' or not side:
        return None
    direction = 1 if side == 'BUY' else -1
    p, a = d['price'], d['atr']
    levels = {'side': side, 'price': p, 'sl': p-direction*1.4*a,
              'tp1': p+direction*1.8*a, 'tp2': p+direction*2.6*a}
    if min(levels[k] for k in ('sl', 'tp1', 'tp2')) <= 0:
        return None
    return dict(d, **levels)


def reversal(watch, d, previous=None):
    """Full opposite entry immediately; partial reversal on two distinct consecutive closes."""
    previous = previous or {}
    if watch['status'] not in ('active', 'uncertain_delivery') or not leading_side(d):
        return None, {}
    opposite = 'SELL' if watch['side'] == 'BUY' else 'BUY'
    stamp = datetime.fromisoformat(d['price_time']).timestamp()
    if stamp <= (watch.get('announced') or watch['created']):
        return None, {}
    if d['side'] == opposite:
        return 'urgent', {'stamp': stamp, 'count': 2}
    checks = d['checks'][opposite]
    weak = leading_side(d) == opposite and checks[2] and checks[4]
    if not weak:
        return None, {}
    if previous.get('stamp') == stamp:
        return ('weak' if previous.get('count', 0) >= 2 else None), previous
    count = previous.get('count', 0) + 1 if stamp - previous.get('stamp', 0) == 300 else 1
    state = {'stamp': stamp, 'count': count}
    return ('weak' if count >= 2 else None), state
