"""Scheduled 15-minute scenarios and 5-minute follow-ups; never broker orders."""
import math
from datetime import datetime
from html import escape

from engine import make_trade
from context import describe
from messages import REASONS, local_time, price_time, fully_qualified


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
                '🟢 شروط الشراء: غير متاحة\n🔴 شروط البيع: غير متاحة')
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
    state += (f"\n\n🟢 شروط الشراء: <b>{d['buy']}/7</b>\n"
              f"🔴 شروط البيع: <b>{d['sell']}/7</b>\n"
              "عدد الشروط المتحققة؛ ليس نسبة نجاح.")
    state += f"\n\nآخر إغلاق 5د: <b>{d['price']:.2f}</b>\nوقت السعر: {price_time(d)} فلسطين"
    if old.get('price') is not None:
        state += f"\nحركة الذهب منذ المرجع: {d['price']-old['price']:+.2f}$ للأونصة"
    return state


def trade_follow_message(trade, d, now):
    side = 'شراء' if trade['side'] == 'BUY' else 'بيع'
    previous = {'side': trade['side'], 'price': trade['entry'],
                'buy': trade.get('entry_buy'), 'sell': trade.get('entry_sell')}
    text = (f"🔎 <b>تحديث الإشارة | {side}</b>\n"
            f"المرجع: <code>{escape(trade['id'])}</code>\n"
            f"وقت التحديث: {local_time(now.timestamp())} فلسطين\n\n" + progress(previous, d))
    if trade.get('delivery_uncertain'):
        text += '\n⚠️ وصول رسالة الدخول غير مؤكد؛ تحقق من الرسالة الأصلية.'
    tp1_state = ' ✅ تم رصده' if trade.get('tp1_hit') else ''
    text += (f"\n\n🛑 وقف الخسارة: <b>{trade['stop']:.2f}</b>\n"
             f"🎯 TP1: <b>{trade['tp1']:.2f}</b>{tp1_state}\n"
             f"🎯 TP2: <b>{trade['tp2']:.2f}</b>\n"
             "المتابعة مستمرة؛ هذا تحديث لنفس الإشارة.\n"
             "غير مضمونة؛ حركة الأونصة ليست ربح حسابك. لا تعديل آلي عند الوسيط.")
    return text


def report_message(s, d, previous=None):
    names = {'BUY': 'شراء', 'SELL': 'بيع', 'WAIT': 'انتظار — لا اقتراح دخول', None: 'غير متاح'}
    label = ('مستوفية شروط الدخول — غير مضمونة' if s['qualified'] else
             'إشارة مبكّرة — غير مضمونة' if s['side'] in ('BUY', 'SELL') and not s['blocked'] else
             'تحديث مراقبة — لا اقتراح دخول')
    text = (f"🕒 <b>ملخص السوق | 15 دقيقة</b>\nالمرجع: <code>{escape(s['id'])}</code>\n"
            f"{local_time(s['created'])} فلسطين\n\n"
            f"الاتجاه الغالب: <b>{names[s['side']]}</b>\n{label}\n"
            f"الخطر التقديري: {s['risk']}\n")
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
    text = (f"🔎 <b>تحديث ملخص السوق</b>\nالمرجع: <code>{escape(s['id'])}</code>\n\n" + progress(s, d) +
            '\n\nالخطر التقديري: ' + risk_label(d, blocked))
    if blocked:
        text += '\nالدخول محجوب: ' + escape(REASONS.get(blocked, blocked))
    watch = s.get('watch')
    if watch:
        text += (f"\n\n🛑 وقف الخسارة/إلغاء السيناريو: <b>{watch['stop']:.2f}</b>\n"
                 f"🎯 TP1: <b>{watch['tp1']:.2f}</b>\n"
                 f"🎯 TP2: <b>{watch['tp2']:.2f}</b>")
    if watch and watch['status'] == 'closed':
        text += '\nانتهى سيناريو المستويات: ' + {'STOP':'رُصد مستوى الإلغاء', 'TP2':'رُصد الهدف الثاني',
            'PROTECTED_STOP':'رُصد مستوى الحماية', 'AMBIGUOUS':'ترتيب لمس المستويات غير محسوم'}[watch['outcome']]
    elif watch and watch['tp1_hit']:
        text += '\nرُصد الهدف الأول؛ الحماية المقترحة عند المرجع الأصلي، ولا تُنفّذ تلقائيًا.'
    return text + '\nغير مضمون؛ لا نسبة نجاح مقاسة. هذا تحديث وليس صفقة جديدة.'
