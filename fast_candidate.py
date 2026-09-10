"""Fixed structure/retest candidate. Research only; no hour-trend veto or broker orders."""
import math

from engine import atr, ema
from fast import aggregate_five
from market import DataError, require_fresh

RULE = 'structure-retest-v1'


def confirmed_swings(bars):
    """A pivot is usable only AFTER both right-hand candles have closed."""
    highs, lows = [], []
    for i in range(2, len(bars)-2):
        neighbours = bars[i-2:i] + bars[i+1:i+3]
        if all(bars[i].high > b.high for b in neighbours):
            highs.append((i, bars[i].high))
        if all(bars[i].low < b.low for b in neighbours):
            lows.append((i, bars[i].low))
    return highs, lows


def structure(fives):
    closes = [b.close for b in fives]
    e9, e21 = ema(closes, 9), ema(closes, 21)
    highs, lows = confirmed_swings(fives)
    # EMA initializes the historical fold. After that only a two-close structural break
    # switches sides; a short correction or a later EMA crossover cannot flip it alone.
    bias = 'BUY' if e9[25] > e21[25] else 'SELL' if e9[25] < e21[25] else 'WAIT'
    flipped, broken = -100, None
    for i in range(26,len(fives)):
        known_highs = [p for p in highs if p[0] <= i-2]
        known_lows = [p for p in lows if p[0] <= i-2]
        upper = known_highs[-1][1] if known_highs else max(b.high for b in fives[i-7:i-1])
        lower = known_lows[-1][1] if known_lows else min(b.low for b in fives[i-7:i-1])
        a = atr(fives[:i+1])
        up_break = all(b.close > upper+.1*a for b in fives[i-1:i+1])
        down_break = all(b.close < lower-.1*a for b in fives[i-1:i+1])
        if bias != 'BUY' and up_break and not down_break:
            bias, flipped, broken = 'BUY',i,upper
        elif bias != 'SELL' and down_break and not up_break:
            bias, flipped, broken = 'SELL',i,lower
    if bias == 'WAIT':
        return {'bias':'WAIT','phase':'mixed','level':None}
    if len(fives)-1-flipped < 3:
        return {'bias':bias,'phase':'confirmed_break','level':broken}
    return {'bias':bias,'phase':'trend','level':lower if bias=='BUY' else upper}


def analyze_candidate(bars, now):
    require_fresh(bars, now, 90)
    if len(bars) < 300 or any(b.minutes != 1 for b in bars):
        raise DataError('candidate_history_insufficient')
    # Validate the entire last hour used by context, not only the trigger candle.
    if any((b.start-a.start).total_seconds() != 60 for a,b in zip(bars[-60:],bars[-59:])):
        raise DataError('candidate_recent_gap')
    fives = aggregate_five(bars)
    if len(fives) < 40:
        raise DataError('candidate_five_history_insufficient')
    require_fresh(fives, now, 360)
    c, b, a = [x.close for x in bars], bars[-1], atr(bars)
    ctx = structure(fives)
    d = {'side':'WAIT', 'reason':'candidate_context_mixed', 'rule':RULE,
         'bar':b.end.isoformat(), 'price':b.close, 'atr':a, 'context':ctx}
    if ctx['bias'] == 'WAIT':
        return d
    if not math.isfinite(a) or a <= 0 or 1.2*a > 3.5:
        return dict(d, reason='candidate_volatility_too_high')
    direction = 1 if ctx['bias'] == 'BUY' else -1
    # Orient both sides into the same uptrend coordinate system.
    q = [direction*x for x in c]
    e9 = ema(q, 9)
    high = lambda x: x.high if direction == 1 else -x.low
    low = lambda x: x.low if direction == 1 else -x.high
    p, op = q[-1], direction*b.open
    prior = bars[-7:-1]
    retraced = any(q[j] < q[j-1] for j in range(len(q)-6,len(q)-1))
    touched_mean = any(low(x) <= e9[len(q)-7+j]+.2*a for j,x in enumerate(prior))
    level = direction*ctx['level']
    if ctx['phase'] == 'confirmed_break':
        # A confirmed structural break still needs a retest near the broken level.
        touched = any(level-.35*a <= low(x) <= level+.5*a for x in prior)
        held = min(low(x) for x in bars[-4:]) >= level-.5*a
        if not (touched and held and p > level+.1*a):
            return dict(d, reason='candidate_break_waiting_retest')
    elif not (retraced and touched_mean):
        return dict(d, reason='candidate_waiting_pullback')
    width = high(b)-low(b)
    resumes = (p > max(high(x) for x in bars[-3:-1])+.05*a and p > e9[-1]
               and e9[-1] > e9[-3] and p > op and width > 0 and (p-low(b))/width >= .65)
    if not resumes:
        return dict(d, reason='candidate_waiting_resumption')
    if p-e9[-1] > 1.5*a:
        return dict(d, reason='candidate_price_extended')
    # Place the stop behind the observed pullback; never squeeze it inside to force a trade.
    stop = min(low(x) for x in bars[-5:])-.15*a
    risk = max(1.5, p-stop, 1.2*a)
    if risk > 3.5:
        return dict(d, reason='candidate_structural_stop_too_wide')
    return dict(d, side=ctx['bias'], reason='candidate_retest_resumption',
                sl=b.close-direction*risk, tp1=b.close+direction*3,
                tp2=b.close+direction*5, max_fill_risk=3.5, min_reward_risk=1.2)
