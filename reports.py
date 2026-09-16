"""Scheduled 15-minute scenarios and 5-minute follow-ups; never broker orders."""
import math
from datetime import datetime
from html import escape

from engine import make_trade
from context import describe
from messages import (REASONS, local_time, price_time, fully_qualified,
                      strength_message, signal_assessment, correction_estimate)


def bias(d):
    if not all(k in d for k in ('price', 'atr', 'buy', 'sell', 'checks', 'price_time')):
        return None
    if not all(math.isfinite(d[k]) and d[k] > 0 for k in ('price', 'atr')):
        return None
    side = 'BUY' if d['buy'] > d['sell'] else 'SELL' if d['sell'] > d['buy'] else 'WAIT'
    context = d.get('context')
    if context and (not context['entry_allowed'] or side != context['trend']):
        return 'WAIT'
    return side


def risk_label(d, blocked=None):
    side = bias(d)
    if side is None:
        return 'غير قابل للتقييم — البيانات غير كافية'
    if blocked or side == 'WAIT' or not fully_qualified(d, side):
        return 'مرتفع — الشروط ناقصة أو الدخول محجوب'
    return 'متوسط وفق القواعد — رغم اكتمال الشروط يمكن أن تخسر'


def snapshot(d, now, blocked=None):
    epoch = now.timestamp()
    slot = int(epoch // 900)
    side = bias(d)
    result = {'id': 'report-' + str(slot), 'slot': slot, 'created': epoch,
              'ends_at': (slot + 1)*900, 'side': side, 'price': d.get('price') if side else None,
              'buy': d.get('buy'), 'sell': d.get('sell'), 'blocked': blocked,
              'qualified': side in ('BUY', 'SELL') and fully_qualified(d, side) and not blocked,
              'risk': risk_label(d, blocked), 'context': d.get('context'), 'watch': None}
    if side in ('BUY', 'SELL') and not blocked:
        direction = 1 if side == 'BUY' else -1
        p, a = d['price'], d['atr']
        levels = dict(d, side=side, sl=p-direction*1.4*a, tp1=p+direction*1.8*a,
                      tp2=p+direction*2.6*a, bar=d['price_time'])
        if min(levels[k] for k in ('sl', 'tp1', 'tp2')) > 0:
            result['watch'] = make_trade(levels, now)
            result['watch']['id'] = result['id']
    return result


def progress(old, d):
    side = bias(d)
    if side is None:
        return ('⚠️ تعذّر تحديث الاتجاه؛ لا تعتمد على السعر السابق كأنه حي.\n\n'
                '🟢 شروط الشراء: غير متاحة\n🔴 شروط البيع: غير متاحة\n' +
                strength_message(d, old.get('side'), current=True))
    names = {'BUY': 'شراء', 'SELL': 'بيع', 'WAIT': 'متعادل'}
    if d.get('context') and (not d['context']['entry_allowed'] or side == 'WAIT'):
        state = describe(d['context'])
    elif old.get('side') not in ('BUY', 'SELL'):
        state = 'الاتجاه الحالي: ' + names[side]
    elif side == 'WAIT':
        state = '🟠 تلاشت الأفضلية؛ شروط الشراء والبيع متعادلة.'
    elif side != old['side']:
        state = '⚠️ تغيّر الاتجاه الغالب إلى ' + names[side] + '؛ راجع المخاطر، لا تدخل عكسًا تلقائيًا.'
    else:
        score = d['buy'] if side == 'BUY' else d['sell']
        before = old.get('buy') if side == 'BUY' else old.get('sell')
        state = ('🟠 الاتجاه مستمر لكن شروطه ضعفت.' if before is not None and score < before
                 else 'الاتجاه الغالب مستمر: ' + names[side] + '؛ الاستمرار غير مضمون.')
    assessed_side = old.get('side') if old.get('side') in ('BUY', 'SELL') else side
    state += '\n\n' + strength_message(d, assessed_side, current=True)
    state += (f"\n\n🟢 شروط الشراء: <b>{d['buy']}/7</b>\n"
              f"🔴 شروط البيع: <b>{d['sell']}/7</b>\n"
              "عدد الشروط المتحققة؛ ليس نسبة نجاح.")
    state += f"\n\nآخر إغلاق 5د: <b>{d['price']:.2f}</b>\nوقت السعر: {price_time(d)} فلسطين"
    if old.get('price') is not None:
        state += f"\nحركة الذهب منذ المرجع: {d['price']-old['price']:+.2f}$ للأونصة"
    return state


def compact_follow(d, side, watch=None):
    """Presentation only: never move stored stops, targets or an account order."""
    current = bias(d)
    name = {'BUY':'الشراء', 'SELL':'البيع'}.get(side, 'الاتجاه')
    if current is None:
        lines = ['⚠️ بيانات السعر غير متاحة.',
                 '🟢 شروط الشراء: —/7 | 🔴 شروط البيع: —/7',
                 f'⭐ قوة دعم {name} الآن: غير قابلة للتقييم']
    else:
        grade, _, _ = signal_assessment(d, side)
        lines = [f"🟢 شروط الشراء: <b>{d['buy']}/7</b> | 🔴 شروط البيع: <b>{d['sell']}/7</b>",
                 f'⭐ <b>قوة دعم {name} الآن: {grade}</b>',
                 f"إغلاق 5د: <b>{d['price']:.2f}</b> | {price_time(d)} فلسطين"]
        phase = (d.get('context') or {}).get('phase')
        if phase in ('conflict', 'trend_break'):
            lines.append('⚠️ تعارض/كسر اتجاه؛ راجع المخاطر.')
        elif current in ('BUY','SELL') and side in ('BUY','SELL') and current != side:
            lines.append('⚠️ الترجيح الحالي عكس الإشارة.')
    if not watch:
        lines.append('الستوب والأهداف والتأمين: لا سيناريو دخول قائم.')
        lines.append('🔄 التصحيح: غير محدد | ⚡ القوة: غير قابلة للتقييم')
        return '\n'.join(lines)
    hit = ' ✅' if watch.get('tp1_hit') else ''
    lines += [f"🛑 وقف الخسارة: <b>{watch['stop']:.2f}</b>",
              f"🎯 TP1: <b>{watch['tp1']:.2f}</b>{hit} | TP2: <b>{watch['tp2']:.2f}</b>"]
    if watch.get('status') == 'closed':
        outcome = {'STOP':'الوقف', 'TP2':'الهدف الثاني', 'PROTECTED_STOP':'وقف الحماية',
                   'AMBIGUOUS':'ترتيب لمس المستويات غير محسوم'}.get(watch.get('outcome'),'انتهاء المتابعة')
        lines.append('🏁 انتهى السيناريو: ' + outcome)
        return '\n'.join(lines)
    if current is None:
        lines.append('التأمين والتصحيح: تعذّر تحديثهما')
        lines.append('⚡ قوة التصحيح: غير قابلة للتقييم')
        return '\n'.join(lines)
    # Existing rule: price breakeven only after TP1. Partial realization is a
    # displayed suggestion, not a new trailing-stop rule or recorded execution.
    protection_state = 'بعد رصد TP1' if watch.get('tp1_hit') else 'مشروط ببلوغ TP1'
    lines.append(f"🔒 تأمين الدخول المقترح: <b>{watch['entry']:.2f}</b>؛ {protection_state}")
    if watch.get('tp1_hit'):
        lines.append(f"💵 مستوى الجني الأول مرصود؛ التالي <b>{watch['tp2']:.2f}</b>")
    else:
        lines.append(f"💵 جني ربح جزئي مقترح: <b>{watch['tp1']:.2f}</b> عند بلوغه")
    phase = (d.get('context') or {}).get('phase')
    if phase in ('conflict', 'trend_break', 'unclear') or not d.get('context'):
        lines.append('🔄 منطقة التصحيح: غير مؤكدة مع تعارض/غموض الاتجاه')
        lines.append('⚡ قوة التصحيح: غير قابلة للتقييم')
        return '\n'.join(lines)
    corr_side, likelihood, lo, hi, target_lo, target_hi, _ = correction_estimate(watch, d)
    strength = {'مرتفع': 'قوي', 'متوسط': 'متوسط', 'ضعيف': 'ضعيف'}.get(likelihood, likelihood)
    passed = d['price'] > hi if watch['side'] == 'BUY' else d['price'] < lo
    if passed:
        lines.append('🔄 منطقة التصحيح السابقة تم تجاوزها؛ لا منطقة جديدة مؤكدة')
        lines.append('⚡ قوة التصحيح: غير قابلة للتقييم')
    else:
        lines += [f"🔄 بداية تصحيح {corr_side} مقدّرة: <b>{lo:.2f}–{hi:.2f}</b>",
                  f"↩️ امتداده المقدّر: <b>{target_lo:.2f}–{target_hi:.2f}</b>",
                  f'⚡ قوة التصحيح: <b>{strength}</b>']
    return '\n'.join(lines)


def trade_follow_message(trade, d, now):
    side = 'شراء' if trade['side'] == 'BUY' else 'بيع'
    text = (f"🔎 <b>تحديث 5د | {side}</b> | <code>{escape(trade['id'])}</code>\n"
            f"{local_time(now.timestamp())} فلسطين\n" + compact_follow(d, trade['side'], trade))
    if trade.get('delivery_uncertain'):
        text += '\n⚠️ وصول إشارة الدخول غير مؤكد.'
    return text + ('\nTwelve Data؛ ليس سعر الوسيط الحي.\n'
                   'متابعة فقط؛ تقديرات غير مضمونة، والتأمين يدوي قبل الرسوم.')


def report_message(s, d, previous=None):
    names = {'BUY': 'شراء', 'SELL': 'بيع', 'WAIT': 'انتظار — لا اقتراح دخول', None: 'غير متاح'}
    label = ('مستوفية شروط الدخول — غير مضمونة' if s['qualified'] else
             'إشارة مبكّرة — غير مضمونة' if s['side'] in ('BUY', 'SELL') and not s['blocked'] else
             'تحديث مراقبة — لا اقتراح دخول')
    text = (f"🕒 <b>ملخص السوق | 15 دقيقة</b>\nالمرجع: <code>{escape(s['id'])}</code>\n"
            f"{local_time(s['created'])} فلسطين\n\n"
            f"الاتجاه الغالب: <b>{names[s['side']]}</b>\n{label}\n"
            f"الخطر التقديري: {s['risk']}\n" + strength_message(d, s['side']) + '\n')
    if d.get('context'):
        text += describe(d['context']) + '\n'
    if s['side'] is not None:
        text += f"\nآخر إغلاق 5د: <b>{d['price']:.2f}</b>\nوقت السعر: {price_time(d)} فلسطين\n"
        text += f"شروط الشراء {d['buy']}/7 | البيع {d['sell']}/7\n"
    if s['blocked']:
        text += '\nسبب عدم الدخول: ' + escape(REASONS.get(s['blocked'], s['blocked'])) + '\n'
    watch = s['watch']
    if watch:
        text += (f"\nمستويات سيناريو للمراقبة:\nهدف 1: <b>{watch['tp1']:.2f}</b>\n"
                 f"هدف 2: <b>{watch['tp2']:.2f}</b>\nإلغاء: <b>{watch['stop']:.2f}</b>\n"
                 'مستويات افتراضية؛ لا تتنبأ بحركة خلال 15د.\n')
    text += (f"\nالتقرير التالي: {local_time(s['ends_at'])} فلسطين؛ متابعة كل 5د.\n"
             'نسبة احتمال الخسارة/النجاح غير مقاسة.\n'
             'تقرير مراقبة خارج سجل الإشارات؛ البوت لا ينفّذ عند الوسيط.')
    return text


def follow_message(s, d, blocked=None):
    watch = s.get('watch')
    text = (f"🔎 <b>تحديث 5د | ملخص السوق</b> | <code>{escape(s['id'])}</code>\n" +
            compact_follow(d, s.get('side'), watch))
    if blocked:
        text += '\nالدخول محجوب: ' + escape(REASONS.get(blocked, blocked))
    return text + ('\nTwelve Data؛ ليس سعر الوسيط الحي.\n'
                   'سيناريو مراقبة فقط؛ التأمين يدوي والتقديرات غير مضمونة.')