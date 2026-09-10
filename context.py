"""Causal trend context: distinguish countertrend pressure from confirmed range breaks."""

def recent_structure(bars):
    """Three complete recent blocks: higher highs/lows or lower highs/lows.

    This is a conservative veto against stale trend signals, not a buy/sell trigger.
    A small final retracement does not erase the preceding rising blocks.
    """
    if len(bars) < 9:
        return 'WAIT'
    bars = bars[-9:]
    if any((b.start-a.start).total_seconds() != 300 for a,b in zip(bars, bars[1:])):
        return 'WAIT'
    blocks = [bars[i:i+3] for i in (0, 3, 6)]
    highs = [max(b.high for b in block) for block in blocks]
    lows = [min(b.low for b in block) for block in blocks]
    if all(a < b for a,b in zip(highs, highs[1:])) and all(a < b for a,b in zip(lows, lows[1:])):
        return 'BUY'
    if all(a > b for a,b in zip(highs, highs[1:])) and all(a > b for a,b in zip(lows, lows[1:])):
        return 'SELL'
    return 'WAIT'


def market_context(m15, price, volatility, h20, h50, h20_before, e20, momentum, fast_bars=()):
    trend = 'BUY' if h20 > h50 and h20 > h20_before else (
        'SELL' if h20 < h50 and h20 < h20_before else 'WAIT')
    # Fix the reference range BEFORE both confirmation candles; no future pivots.
    prior = m15[-10:-2]
    support, resistance = min(b.low for b in prior), max(b.high for b in prior)
    contiguous = all((b.start-a.start).total_seconds() == 900 for a,b in zip(m15[-10:-1],m15[-9:]))
    structure = recent_structure(fast_bars)
    result = {'trend': trend, 'local_structure': structure, 'support': support, 'resistance': resistance,
              'phase': 'unclear', 'entry_allowed': False}
    if not contiguous or trend == 'WAIT':
        return result
    buffer = .15 * volatility
    broken = (all(b.close < support-buffer for b in m15[-2:]) and price < support-buffer
              if trend == 'BUY' else
              all(b.close > resistance+buffer for b in m15[-2:]) and price > resistance+buffer)
    counter = (price < e20 or momentum < 0 or m15[-1].close < m15[-1].open
               if trend == 'BUY' else
               price > e20 or momentum > 0 or m15[-1].close > m15[-1].open)
    conflict = structure in ('BUY', 'SELL') and structure != trend
    result['phase'] = ('trend_break' if broken else 'conflict' if conflict else
                       'pullback' if counter else 'aligned')
    result['entry_allowed'] = result['phase'] == 'aligned'
    return result


def describe(c):
    trend = {'BUY':'صاعد', 'SELL':'هابط', 'WAIT':'غير محسوم'}[c['trend']]
    text = 'اتجاه الساعة: ' + trend + '. '
    if c['phase'] == 'pullback':
        text += ('تصحيح هابط محتمل داخل اتجاه صاعد؛ ننتظر تأكيد عودة الصعود قبل شراء، وليس بيعًا لمجرد الهبوط.'
                 if c['trend'] == 'BUY' else
                 'تصحيح صاعد محتمل داخل اتجاه هابط؛ ننتظر تأكيد عودة الهبوط قبل بيع، وليس شراءً لمجرد الصعود.')
    elif c['phase'] == 'trend_break':
        text += 'كسر نطاق سابق بتأكيد إغلاقين 15د؛ فكرة الاتجاه مهددة، والاتجاه الجديد يحتاج تأكيدًا. راجع وقفك والخروج إذا دخلت.'
    elif c['phase'] == 'conflict':
        text += ('لكن القمم والقيعان القصيرة تصعد؛ مؤشرات الساعة قد تتأخر. لا اقتراح بيع قبل زوال التعارض.'
                 if c['local_structure'] == 'BUY' else
                 'لكن القمم والقيعان القصيرة تهبط؛ مؤشرات الساعة قد تتأخر. لا اقتراح شراء قبل زوال التعارض.')
    elif c['phase'] == 'unclear':
        text += 'الاتجاه أو استمرارية البيانات غير كافية؛ انتظار بلا اقتراح دخول.'
    else:
        text += 'الحركة الحالية متوافقة مع الاتجاه؛ الدخول يحتاج بقية الشروط.'
    return text + f"\nنطاق مرجعي سابق: دعم {c['support']:.2f} | مقاومة {c['resistance']:.2f}. التصنيف احتمالي وقد يتغيّر؛ لا تؤخّر وقفك بانتظار تأكيده."
