"""Fixed, experimental one-minute breakout rules. No broker execution or guarantees."""
from copy import deepcopy
from datetime import timedelta
import math

from engine import ema, atr, make_trade, advance_trade
from market import Bar, DataError, closed_only, parse_bars, require_fresh, UTC
from messages import LOCAL
import requests

TARGET = 5.0
MAX_HOLD = 20 * 60


def fast_window(now):
    local = now.astimezone(LOCAL)
    return local.weekday() < 5 and 20 <= local.hour < 23 or (
        local.weekday() < 5 and local.hour == 23 and local.minute < 30)


def aggregate_five(bars):
    groups = {}
    for b in bars:
        bucket = int(b.start.timestamp()) // 300 * 300
        groups.setdefault(bucket, []).append(b)
    result = []
    for _, group in sorted(groups.items()):
        if len(group) == 5 and group[0].start.minute % 5 == 0 and all(
                (b.start-a.start).total_seconds() == 60 for a,b in zip(group,group[1:])):
            result.append(Bar(group[0].start, group[0].open, max(b.high for b in group),
                              min(b.low for b in group), group[-1].close, 5))
    return result


def analyze_fast(bars, now):
    require_fresh(bars, now, 90)
    if len(bars) < 300 or any(b.minutes != 1 for b in bars):
        raise DataError('fast_history_insufficient')
    recent = bars[-30:]
    if any((b.start-a.start).total_seconds() != 60 for a,b in zip(recent,recent[1:])):
        raise DataError('fast_recent_gap')
    fives = aggregate_five(bars)
    if len(fives) < 40:
        raise DataError('fast_five_history_insufficient')
    require_fresh(fives, now, 360)
    closes = [b.close for b in bars]
    a = atr(bars)
    p, bar = closes[-1], bars[-1]
    decision = {'side':'WAIT', 'reason':'fast_conditions_missing', 'bar':bar.end.isoformat(),
                'price':p, 'atr':a}
    if not math.isfinite(a) or a <= 0 or 1.2*a > 3.5:
        return dict(decision, reason='fast_volatility_too_high')
    e9, e21 = ema(closes,9), ema(closes,21)
    f = [b.close for b in fives]
    f9, f21 = ema(f,9), ema(f,21)
    upper, lower = max(b.high for b in bars[-7:-1]), min(b.low for b in bars[-7:-1])
    # Fast reversal can qualify before slow 5m EMA alignment by breaking a prior 15m range.
    five_up = f9[-1] > f21[-1] or p > max(b.high for b in fives[-3:])
    five_down = f9[-1] < f21[-1] or p < min(b.low for b in fives[-3:])
    width = bar.high-bar.low
    strong_up = width > 0 and bar.close > bar.open and (bar.close-bar.low)/width >= .7
    strong_down = width > 0 and bar.close < bar.open and (bar.high-bar.close)/width >= .7
    not_chasing = abs(p-e9[-1]) <= 2*a
    buy = p > upper+.1*a and e9[-1] > e21[-1] and e9[-1] > e9[-4] and five_up and strong_up
    sell = p < lower-.1*a and e9[-1] < e21[-1] and e9[-1] < e9[-4] and five_down and strong_down
    side = 'BUY' if buy and not_chasing else 'SELL' if sell and not_chasing else 'WAIT'
    if side == 'WAIT':
        return decision
    direction = 1 if side == 'BUY' else -1
    risk = max(1.5, 1.2*a)
    return dict(decision, side=side, sl=p-direction*risk, tp1=p+direction*3,
                tp2=p+direction*TARGET, reason='fast_breakout_confirmed')


def paper_fill(decision, bar):
    direction = 1 if decision['side'] == 'BUY' else -1
    # Do not fill a stale entry beyond invalidation, or after most of the target is gone.
    if not (direction*(bar.open-decision['sl']) > 0 and direction*(decision['tp1']-bar.open) > 0):
        return None
    if abs(bar.open-decision['price']) > .5*decision['atr']:
        return None
    filled = dict(decision, price=bar.open)
    trade = make_trade(filled, bar.start)
    trade.update(status='active', announced=bar.start.timestamp(), rule='fast-v1')
    return trade


def advance_fast(original, bars):
    trade = deepcopy(original)
    for bar in bars:
        if trade['status'] == 'closed':
            break
        if bar.end.timestamp() <= (trade['last_end'] or trade['announced']):
            continue
        # Known in advance, evaluated at the first bar open after the 20m holding limit.
        if bar.start.timestamp() >= trade['announced'] + MAX_HOLD:
            gap = trade['last_end'] is not None and bar.start.timestamp() > trade['last_end']
            risk = abs(trade['entry']-trade['initial_sl'])
            r = (1 if trade['side']=='BUY' else -1)*(bar.open-trade['entry'])/risk
            trade.update(status='closed', outcome='TIME_LIMIT', exit=bar.open,
                         closed=bar.start.timestamp(), data_gap=trade['data_gap'] or gap,
                         r=None if trade['data_gap'] or gap or trade['delivery_uncertain'] else r)
            break
        # Keep first-bar data-gap checking minute-aware without changing the slow engine.
        if trade['last_end'] is None and bar.start.timestamp() > trade['announced']+60:
            trade['data_gap'] = True
        trade, _ = advance_trade(trade, [bar])
    return trade


class MinuteMarket:
    def __init__(self, key, session=None):
        self.key, self.session = key, session or requests.Session()

    def fetch(self, now, end=None, size=600, fresh=True):
        params = {'symbol':'XAU/USD', 'interval':'1min', 'outputsize':size,
                  'timezone':'UTC', 'order':'ASC', 'format':'JSON', 'apikey':self.key}
        params['end_date'] = (end or now).astimezone(UTC).strftime('%Y-%m-%d %H:%M:%S')
        try:
            response = self.session.get('https://api.twelvedata.com/time_series', params=params, timeout=(5,25))
            if response.status_code != 200:
                raise DataError('minute_http_' + str(response.status_code))
            payload = response.json()
        except (requests.RequestException, ValueError):
            raise DataError('minute_connection_or_json_failed') from None
        if isinstance(payload, dict) and payload.get('status') == 'error':
            code = payload.get('code')
            raise DataError('minute_quota_reached' if code == 429 else 'minute_access_rejected')
        bars = closed_only(parse_bars(payload, now, minutes=1), now, settle_seconds=5)
        if fresh:
            require_fresh(bars, now, 90)
        return bars
