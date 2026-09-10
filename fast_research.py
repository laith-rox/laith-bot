"""Forward-only evaluation of a fixed experimental rule; costs are explicit scenarios."""
from datetime import datetime, timedelta
import json
import logging
from math import isfinite
from messages import LOCAL

from fast import MinuteMarket, analyze_fast, paper_fill, advance_fast, fast_window
from market import DataError, UTC
from news import week_start

LOG = logging.getLogger('laith')
COSTS = (0.2, 0.5, 1.0)  # Total round-trip spread/slippage in quote dollars; NOT broker measurements.


def news_clear(now, events):
    return all(not -900 <= e['time']-now.timestamp() <= 1800 for e in events)


def simulate_fast(bars, costs, events, start_from=None):
    if any(not isinstance(x, (int,float)) or x < 0 or not isfinite(x) for x in costs):
        raise ValueError('invalid_fast_cost')
    active = pending = None
    trades = []
    skipped = signals = 0
    last_entry = 0
    first_signal = None
    daily = {}
    for i, bar in enumerate(bars):
        now = bar.end + timedelta(seconds=8)
        if active:
            active = advance_fast(active, [bar])
            if active['status'] == 'closed':
                trades.append(active)
                date = datetime.fromtimestamp(active['closed'], UTC).astimezone(LOCAL).date().isoformat()
                daily[date] = daily.get(date,0)+(active['r'] if active['r'] is not None else -1)
                active = None
        if pending and bar.start > pending['decision_time']:
            # First FULL minute after the decision, not the minute already in flight.
            candidate = pending['decision']
            if fast_window(bar.start) and news_clear(bar.start, events):
                active = paper_fill(candidate, bar)
                if active:
                    last_entry = bar.start.timestamp()
                    active = advance_fast(active, [bar])
                    if active['status'] == 'closed':
                        trades.append(active)
                        date = bar.start.astimezone(LOCAL).date().isoformat()
                        daily[date] = daily.get(date,0)+(active['r'] if active['r'] is not None else -1)
                        active = None
                else:
                    skipped += 1
            else:
                skipped += 1
            pending = None
        if i < 299 or active or pending or (start_from and now < start_from):
            continue
        if not fast_window(now) or not news_clear(now, events) or now.timestamp()-last_entry < 300:
            continue
        if daily.get(now.astimezone(LOCAL).date().isoformat(),0) <= -3:
            continue
        try:
            d = analyze_fast(bars[max(0,i-599):i+1], now)
        except DataError:
            continue
        if d['side'] in ('BUY','SELL'):
            signals += 1
            first_signal = first_signal or now.isoformat()
            pending = {'decision':d, 'decision_time':now}
    result = {'signals':signals, 'closed':len(trades), 'skipped_fills':skipped,
              'open_at_end':int(active is not None), 'pending_at_end':int(pending is not None),
              'excluded':sum(t['r'] is None for t in trades), 'first_signal':first_signal, 'cost_scenarios':[]}
    valid = [t for t in trades if t['r'] is not None]
    for cost in costs:
        nets = [t['r']-cost/abs(t['entry']-t['initial_sl']) for t in valid]
        positive = sum(max(v,0) for v in nets)
        negative = -sum(min(v,0) for v in nets)
        peak = equity = dd = 0
        for v in nets:
            equity += v
            peak = max(peak,equity)
            dd = max(dd,peak-equity)
        result['cost_scenarios'].append({'round_trip_dollars_per_ounce':cost,
            'measured':len(nets), 'wins':sum(v>0 for v in nets), 'losses':sum(v<0 for v in nets),
            'net_r':round(sum(nets),4), 'max_drawdown_r':round(dd,4),
            'profit_factor':round(positive/negative,4) if negative else None})
    return result


def evaluate(market, now, events):
    by_time = {}
    end = None
    # Bounded four-request probe. Prices stay in the bot's persistent local storage.
    for _ in range(4):
        batch = market.fetch(now, end=end, size=2400, fresh=end is None)
        if not batch:
            break
        for bar in batch:
            existing = by_time.get(bar.start)
            if existing and existing != bar:
                raise DataError('minute_history_conflict')
            by_time[bar.start] = bar
        oldest = batch[0].start
        if end and oldest >= end:
            raise DataError('minute_pagination_not_advancing')
        if oldest <= week_start(now).astimezone(UTC):
            break
        end = oldest-timedelta(seconds=1)
    bars = sorted(by_time.values(), key=lambda b:b.start)
    # Calendar coverage is current week only. Keep preceding bars for indicator warm-up.
    covered = [b for b in bars if b.start >= week_start(now).astimezone(UTC)]
    if len(covered) < 600:
        raise DataError('minute_research_history_insufficient')
    split = covered[int(len(covered)*.7)].start
    full = simulate_fast(bars, COSTS, events, start_from=covered[0].start)
    holdout = simulate_fast(bars, COSTS, events, start_from=split)
    # A prerequisite for considering a forward paper trial, not proof of future success.
    last = holdout['cost_scenarios'][-1]
    promising = (last['measured'] >= 30 and last['net_r'] > 0 and
                 last['profit_factor'] is not None and last['profit_factor'] >= 1.2)
    result = {'rule':'fast-v1', 'mode':'RESEARCH_ONLY', 'source':'Twelve Data XAU/USD 1min',
              'sample_start':covered[0].start.isoformat(), 'sample_end':covered[-1].end.isoformat(),
              'candles':len(covered), 'holdout_from':split.isoformat(),
              'hours':'20:00–23:30 Asia/Hebron weekdays', 'target_price_distance':5,
              'costs':'Hypothetical total round-trip costs; JustMarkets spread is NOT connected',
              'news_filter':'Current-week scheduled USD High, -30/+15min; no unscheduled news',
              'full':full, 'holdout':holdout,
              'gate':'PROMISING_FOR_PAPER_ONLY' if promising else 'NOT_VALIDATED_FOR_SIGNALS'}
    return result, bars


def summary(result):
    h = result['holdout']['cost_scenarios'][-1]
    return ('🧪 <b>نتيجة فحص المسار السريع — ليست صفقة</b>\n'
            f"شموع دقيقة فعلية: {result['candles']}\n"
            f"فترة البيانات: {result['sample_start']} إلى {result['sample_end']}\n"
            f"العينة اللاحقة: {h['measured']} متابعة قابلة للقياس | موجبة {h['wins']} | سالبة {h['losses']}\n"
            f"المحصلة {h['net_r']:+.2f}R مع تكلفة مفترضة {h['round_trip_dollars_per_ounce']}$ للأونصة لكل دورة.\n"
            'التكلفة ليست سبريد حسابك الفعلي، والأرقام ليست أرباح حساب. '
            'المسار سريع تجريبي فقط؛ لا تُرسل منه أوامر دخول. /fast يعرض تفاصيل حالته.')
