"""Scheduled 15-minute scenarios and 5-minute follow-ups; never broker orders."""
import math
from datetime import datetime
from html import escape

from engine import make_trade
from context import describe
from messages import CHECK_LABELS, REASONS, local_time


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
    if blocked or side == 'WAIT' or d.get('side') != side:
        return 'مرتفع — الشروط ناقصة أو الدخول محجوب'
    return 'متوسط وفق القواعد — رغم اكتمال الشروط يمكن أن تخسر'


def snapshot(d, now, blocked=None):
    epoch = now.timestamp()
    slot = int(epoch // 900)
    side = bias(d)
    result = {'id': 'report-' + str(slot), 'slot': slot, 'created': epoch,
              'ends_at': (slot + 1)*900, 'side': side, 'price': d.get('price') if side else None,
              'buy': d.get('buy'), 'sell': d.get('sell'), 'blocked': blocked,
              'qualified': side in ('BUY', 'SELL') and d.get('side') == side and not blocked,
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
        return '⚠️ تعذّر تحديث الاتجاه؛ لا تعتمد على السعر السابق كأنه حي.'
    names = {'BUY': 'شراء', 'SELL': 'بيع', 'WAIT': 'متعادل'}
    if d.get('context') and (not d['context']['entry_allowed'] or side == 'WAIT'):
        state = describe(d['context'])
    elif old.get('side') not in ('BUY', 'SELL'):
        state = 'الاتجاه الحالي: ' + names[side]
    elif side == 'WAIT':
        state = '🟠 تلاشت الأفضلية؛ شروط الشراء والبيع متعادلة.'
    elif side != old['side']:
        state = '🚨 تغيّر الاتجاه الغالب إلى ' + names[side] + '؛ راجع الخروج إذا دخلت، ولا تفتح عكسًا تلقائيًا.'
    else:
        score = d['buy'] if side == 'BUY' else d['sell']
        before = old.get('buy') if side == 'BUY' else old.get('sell')
        state = ('🟠 الاتجاه مستمر لكن شروطه ضعفت.' if before is not None and score < before
                 else 'الاتجاه الغالب مستمر: ' + names[side] + '؛ الاستمرار غير مضمون.')
    state += f"\nشراء {d['buy']}/7 | بيع {d['sell']}/7 | آخر سعر مغلق {d['price']:.2f}"
    if old.get('price') is not None:
        state += f"\nالتغيّر عن المرجع السابق: {d['price']-old['price']:+.2f}$ بسعر الأونصة؛ ليس ربح حسابك."
    return state


def report_message(s, d, previous=None):
    names = {'BUY': 'شراء', 'SELL': 'بيع', 'WAIT': 'انتظار — لا اقتراح دخول', None: 'غير متاح'}
    label = ('مستوفية شروط الدخول — غير مضمونة' if s['qualified'] else
             'إشارة مبكّرة — غير مضمونة' if s['side'] in ('BUY', 'SELL') and not s['blocked'] else
             'تحديث مراقبة — لا اقتراح دخول')
    text = (f"🕒 <b>ليث — تقرير 15 دقيقة</b> <code>{s['id']}</code>\n"
            f"<b>{label}</b>\nالاتجاه الغالب بالمؤشرات: <b>{names[s['side']]}</b>\n"
            f"درجة الخطر التقديرية: {s['risk']}\nنسبة احتمال الخسارة/النجاح غير مقاسة.\n")
    if d.get('context'):
        text += describe(d['context']) + '\n'
    if s['side'] is not None:
        text += f"شراء {d['buy']}/7 | بيع {d['sell']}/7؛ عدد الشروط ليس احتمال نجاح.\n"
        text += f"السعر المرجعي {d['price']:.2f} | وقت السعر {escape(d['price_time'])} UTC\n"
    if s['side'] in ('BUY', 'SELL'):
        missing = [label for label, ok in zip(CHECK_LABELS, d['checks'][s['side']]) if not ok]
        text += 'الشروط الناقصة: ' + ('، '.join(missing) if missing else 'لا يوجد') + '\n'
    if s['blocked']:
        text += 'اقتراح الدخول محجوب: ' + escape(REASONS.get(s['blocked'], s['blocked'])) + '\n'
    watch = s['watch']
    if watch:
        text += (f"هدف محتمل أول {watch['tp1']:.2f} ({watch['tp1']-watch['entry']:+.2f}$)\n"
                 f"هدف محتمل ثانٍ {watch['tp2']:.2f} ({watch['tp2']-watch['entry']:+.2f}$)\n"
                 f"إلغاء السيناريو {watch['stop']:.2f} — مسافة {abs(watch['stop']-watch['entry']):.2f}$\n"
                 'مستويات ATR افتراضية؛ ليست توقعًا لحركة ستحدث خلال 15د. الدولار فرق سعر الأونصة، وليس ربح حسابك.\n')
    if previous and s['created'] - previous['created'] <= 1800:
        text += '\nخلاصة التقرير السابق:\n' + progress(previous, d) + '\n'
    text += (f"\nالمتابعة كل 5د حتى التقرير التالي {local_time(s['ends_at'])} فلسطين. "
             'هذه متابعة مستقلة خارج إحصاءات الصفقات، ولا تعني فتح صفقة جديدة كل ربع ساعة. '
             'المراقبة ليست لحظية والبوت لا ينفّذ عند الوسيط.')
    return text


def follow_message(s, d, blocked=None):
    text = (f"🔎 <b>متابعة 5 دقائق</b> <code>{s['id']}</code>\n" + progress(s, d) +
            '\nالخطر التقديري: ' + risk_label(d, blocked) + '؛ لا نسبة نجاح مقاسة.')
    if blocked:
        text += '\nالدخول محجوب: ' + escape(REASONS.get(blocked, blocked))
    watch = s.get('watch')
    if watch and watch['status'] == 'closed':
        text += '\nانتهى سيناريو المستويات: ' + {'STOP':'رُصد مستوى الإلغاء', 'TP2':'رُصد الهدف الثاني',
            'PROTECTED_STOP':'رُصد مستوى الحماية', 'AMBIGUOUS':'ترتيب لمس المستويات غير محسوم'}[watch['outcome']]
    elif watch and watch['tp1_hit']:
        text += '\nرُصد الهدف الأول؛ الحماية المقترحة عند المرجع الأصلي، ولا تُنفّذ تلقائيًا.'
    return text + '\nغير مضمون؛ افحص سعر وسيطك. هذا تحديث للمتابعة وليس صفقة جديدة.'
