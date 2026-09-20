"""Generate clear Arabic educational visuals for Laith V4.

All chart prices are synthetic training examples. The goal is to teach the eye:
direction, correction, breakout, invalidation, entry, stop and target.
"""
from io import BytesIO

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1080

BG = (13, 16, 21)
PANEL = (20, 24, 31)
GRID = (45, 51, 61)
TEXT = (239, 241, 245)
MUTED = (157, 164, 176)
UP = (39, 184, 132)
DOWN = (226, 79, 79)
WAIT = (229, 187, 70)
INFO = (91, 157, 219)
LEVEL = (145, 154, 169)


def _font(size=34, bold=False):
    names = ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf") if bold else ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _shape(text):
    text = str(text or "")
    if any("\u0600" <= ch <= "\u06ff" for ch in text):
        return get_display(arabic_reshaper.reshape(text))
    return text


def _draw_ar(d, xy, text, size=24, fill=TEXT, bold=False, anchor="la"):
    d.text(xy, _shape(text), font=_font(size, bold=bold), fill=fill, anchor=anchor)


def _text_width(d, text, size=22, bold=False):
    box = d.textbbox((0, 0), _shape(text), font=_font(size, bold=bold))
    return box[2] - box[0]


def _base(side="شرح"):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((24, 20, W - 24, H - 20), radius=28, fill=PANEL, outline=(63, 69, 80), width=2)

    _draw_ar(d, (48, 48), "شرح تعليمي للذهب", size=44, bold=True)
    _draw_ar(d, (48, 108), "مثال تدريبي فقط — الأسعار داخل الصورة ليست أسعارًا حية", size=27, fill=MUTED)

    side = side if side in ("شراء", "بيع", "انتظار", "شرح") else "شرح"
    side_color = {"شراء": UP, "بيع": DOWN, "انتظار": WAIT, "شرح": INFO}[side]
    label = {"شراء": "نوع المثال: شراء", "بيع": "نوع المثال: بيع", "انتظار": "القرار هنا: انتظار", "شرح": "شرح بصري"}[side]
    shaped = _shape(label)
    fw = _text_width(d, label, size=31, bold=True) + 44
    x1 = W - 48 - fw
    d.rounded_rectangle((x1, 48, W - 48, 104), radius=15, fill=side_color)
    d.text((W - 68, 76), shaped, font=_font(31, bold=True), fill=(10, 14, 18), anchor="rm")
    return img, d


def _chart_box(d):
    left, top, right, bottom = 56, 188, 1005, 820
    for i in range(6):
        y = top + (bottom - top) * i / 5
        d.line((left, y, right, y), fill=GRID, width=1)
    for i in range(9):
        x = left + (right - left) * i / 8
        d.line((x, top, x, bottom), fill=GRID, width=1)
    d.rectangle((left, top, right, bottom), outline=(76, 83, 95), width=2)
    return left, top, right, bottom


def _ohlc(closes):
    rows = []
    previous = closes[0] - 0.7
    wicks = (1.4, 2.2, 1.7, 2.6, 1.5, 2.0)
    for i, close in enumerate(closes):
        open_ = previous
        wick = wicks[i % len(wicks)]
        high = max(open_, close) + wick
        low = min(open_, close) - wick * 0.82
        rows.append((open_, high, low, close))
        previous = close
    return rows


def _mirror(closes, pivot=4310.0):
    return [pivot * 2 - x for x in closes]


def _series(kind, side="شراء", variant=0):
    side = side if side in ("شراء", "بيع", "انتظار") else "شراء"

    if kind == "correction":
        closes = [4290, 4295, 4300, 4305, 4311, 4317, 4314, 4310, 4307, 4310, 4314, 4319, 4324, 4329, 4326, 4332, 4336, 4340]
        meta = {
            "support": 4306.0,
            "entry": 4311.0,
            "stop": 4303.0,
            "target": 4334.0,
            "corr_start": 5,
            "corr_end": 8,
            "key_index": 8,
        }
        if variant:
            closes = [4290, 4295, 4300, 4305, 4311, 4317, 4313, 4308, 4304, 4299, 4295, 4291, 4287, 4284, 4281, 4278, 4274, 4271]
            meta.update({"entry": 4302.0, "stop": 4310.0, "target": 4280.0, "break_index": 9})
    elif kind == "breakout":
        closes = [4294, 4297, 4296, 4300, 4298, 4302, 4300, 4304, 4306, 4312, 4317, 4310, 4314, 4319, 4323, 4327, 4325, 4330]
        meta = {"level": 4308.0, "entry": 4312.0, "stop": 4303.0, "target": 4327.0, "break_index": 9, "retest_index": 11}
        if variant:
            closes = [4294, 4297, 4296, 4300, 4298, 4302, 4300, 4304, 4306, 4314, 4306, 4301, 4298, 4295, 4292, 4290, 4288, 4286]
            meta.update({"entry": 0.0, "stop": 0.0, "target": 0.0, "fake_index": 10})
    elif kind == "event":
        closes = [4300, 4301, 4299, 4300, 4302, 4301, 4300, 4301, 4300, 4318, 4309, 4314, 4311, 4317, 4321, 4318, 4324, 4327]
        meta = {"entry": 4314.0, "stop": 4305.0, "target": 4325.0, "news_index": 9}
    elif kind == "volatility":
        closes = [4300, 4301, 4300, 4302, 4301, 4303, 4302, 4304, 4303, 4310, 4305, 4314, 4307, 4317, 4310, 4321, 4315, 4325]
        meta = {"entry": 4310.0, "stop": 4300.0, "target": 4324.0}
    else:
        closes = [4290, 4295, 4293, 4299, 4297, 4304, 4301, 4308, 4305, 4312, 4309, 4316, 4313, 4320, 4317, 4324, 4321, 4328]
        meta = {"support": 4296.0, "entry": 4307.0, "stop": 4299.0, "target": 4325.0}

    if side == "بيع" and kind not in ("correction",):
        closes = _mirror(closes)
        for key in ("entry", "stop", "target", "level", "support"):
            if key in meta and meta[key]:
                meta[key] = 8620.0 - meta[key]

    return _ohlc(closes), meta


def _price_to_y(price, top, bottom, lo, hi):
    return bottom - (price - lo) / (hi - lo) * (bottom - top)


def _draw_price_axis(d, box, lo, hi):
    left, top, right, bottom = box
    for i in range(6):
        price = hi - (hi - lo) * i / 5
        y = top + (bottom - top) * i / 5
        d.text((right + 8, y - 11), f"{price:.1f}", font=_font(20), fill=MUTED)
    times = ("09:00", "10:00", "11:00", "12:00", "13:00", "14:00")
    for i, label in enumerate(times):
        x = left + (right - left) * i / (len(times) - 1)
        d.text((x - 22, bottom + 12), label, font=_font(18), fill=MUTED)


def _draw_candles(d, box, rows):
    left, top, right, bottom = box
    lo = min(x[2] for x in rows)
    hi = max(x[1] for x in rows)
    pad = max(2.0, (hi - lo) * 0.08)
    lo -= pad
    hi += pad
    step = (right - left - 28) / len(rows)
    body_w = max(11, int(step * 0.55))
    centers = []

    for i, (open_, high, low, close) in enumerate(rows):
        x = left + 14 + step * (i + 0.5)
        centers.append(x)
        yh = _price_to_y(high, top, bottom, lo, hi)
        yl = _price_to_y(low, top, bottom, lo, hi)
        yo = _price_to_y(open_, top, bottom, lo, hi)
        yc = _price_to_y(close, top, bottom, lo, hi)
        color = UP if close >= open_ else DOWN
        d.line((x, yh, x, yl), fill=color, width=3)
        y1, y2 = min(yo, yc), max(yo, yc)
        if y2 - y1 < 4:
            y2 = y1 + 4
        d.rectangle((x - body_w / 2, y1, x + body_w / 2, y2), fill=color, outline=color)

    _draw_price_axis(d, box, lo, hi)
    return centers, lo, hi


def _tag(d, x, y, text, color=(37, 43, 53), text_color=TEXT, size=27):
    shaped = _shape(text)
    font = _font(size, bold=True)
    box = d.textbbox((0, 0), shaped, font=font)
    w = max(126, box[2] - box[0] + 34)
    h = 52
    x = max(34, min(W - w - 34, x))
    y = max(160, min(880 - h, y))
    d.rounded_rectangle((x, y, x + w, y + h), radius=12, fill=color, outline=(105, 113, 126), width=2)
    d.text((x + w - 16, y + h / 2), shaped, font=font, fill=text_color, anchor="rm")
    return x, y, w, h


def _arrow(d, start, end, color=INFO, width=6):
    d.line((start[0], start[1], end[0], end[1]), fill=color, width=width)
    x, y = end
    if end[0] >= start[0]:
        head = [(x, y), (x - 14, y - 9), (x - 11, y + 11)]
    else:
        head = [(x, y), (x + 14, y - 9), (x + 11, y + 11)]
    d.polygon(head, fill=color)


def _hline(d, box, price, lo, hi, label, color=LEVEL):
    left, top, right, bottom = box
    y = _price_to_y(price, top, bottom, lo, hi)
    d.line((left, y, right, y), fill=color, width=2)
    _tag(d, left + 15, y - 40, label)
    return y


def _trade_levels(d, box, meta, lo, hi, side):
    left, top, right, bottom = box
    if not meta.get("entry"):
        return

    # Keep thin reference lines on the chart.
    for key, color in (("entry", WAIT), ("stop", DOWN), ("target", UP)):
        value = meta.get(key)
        if not value:
            continue
        y = _price_to_y(value, top, bottom, lo, hi)
        d.line((right - 250, y, right - 12, y), fill=color, width=3)

    # Large mobile-readable legend under the chart.
    items = (
        ("الدخول", meta.get("entry"), WAIT),
        ("وقف الخسارة", meta.get("stop"), DOWN),
        ("الهدف", meta.get("target"), UP),
    )
    x = 58
    y1, y2 = 886, 1002
    box_w = 300
    for label, value, color in items:
        d.rounded_rectangle((x, y1, x + box_w, y2), radius=18, fill=(31, 36, 45), outline=color, width=4)
        _draw_ar(d, (x + box_w / 2, y1 + 34), label, size=29, bold=True, anchor="mm")
        d.text((x + box_w / 2, y1 + 79), f"{float(value):.1f}" if value else "—", font=_font(28, bold=True), fill=color, anchor="mm")
        x += 330


def _number_marker(d, x, y, number, color=INFO):
    """Large numbered marker that matches the explanation cards below."""
    r = 23
    d.ellipse((x - r, y - r, x + r, y + r), fill=color, outline=TEXT, width=3)
    d.text((x, y), str(number), font=_font(25, bold=True), fill=(10, 14, 18), anchor="mm")


def _explanation_cards(d, steps):
    """Four short numbered explanations, readable in Telegram mobile preview."""
    left = 52
    top = 844
    gap_x = 18
    gap_y = 14
    card_w = 479
    card_h = 78
    colors = (INFO, WAIT, UP, DOWN)

    for i, text in enumerate(steps):
        row = i // 2
        col = i % 2
        x1 = left + col * (card_w + gap_x)
        y1 = top + row * (card_h + gap_y)
        x2 = x1 + card_w
        y2 = y1 + card_h
        color = colors[i]
        d.rounded_rectangle((x1, y1, x2, y2), radius=16, fill=(31, 36, 45), outline=color, width=3)
        _number_marker(d, x1 + 34, y1 + card_h / 2, i + 1, color=color)
        _draw_ar(d, (x2 - 18, y1 + card_h / 2), text, size=23, bold=True, anchor="rm")


def _draw_correction_explanation(d, box, rows, centers, meta, lo, hi, variant):
    left, top, right, bottom = box
    if not variant:
        y_support = _hline(d, box, meta["support"], lo, hi, "القاع المهم", INFO)
        s = meta["corr_start"]
        e = meta["corr_end"]
        sy = _price_to_y(rows[s][3], top, bottom, lo, hi)
        ey = _price_to_y(rows[e][3], top, bottom, lo, hi)

        # Keep the chart clean: numbered markers point to the explanation cards.
        _arrow(d, (centers[s], sy - 12), (centers[e], ey + 10), color=WAIT, width=6)
        _tag(d, centers[s] + 26, (sy + ey) / 2 - 28, "هذا هو التصحيح", color=(76, 62, 26), size=25)

        _number_marker(d, centers[3], _price_to_y(rows[3][3], top, bottom, lo, hi) - 45, 1, UP)
        _number_marker(d, centers[e], ey + 42, 2, WAIT)
        _number_marker(d, centers[e] + 72, y_support - 28, 3, UP)
        _number_marker(d, right - 80, y_support + 38, 4, DOWN)

        _explanation_cards(d, (
            "الاتجاه العام صاعد",
            "النزول الحالي تصحيح",
            "بقاء القاع = نراقب شراء",
            "كسر القاع = تبطل فكرة الشراء",
        ))
    else:
        break_i = meta.get("break_index", 9)
        y_structure = _hline(d, box, 4306.0, lo, hi, "القاع المهم", INFO)
        by = _price_to_y(rows[break_i][3], top, bottom, lo, hi)

        _arrow(d, (centers[break_i - 2], by - 50), (centers[break_i], by), color=DOWN, width=6)
        _tag(d, centers[break_i] + 26, by + 10, "هنا انكسر القاع", color=(91, 33, 33), size=25)

        _number_marker(d, centers[4], _price_to_y(rows[4][3], top, bottom, lo, hi) - 42, 1, UP)
        _number_marker(d, centers[break_i], by - 42, 2, DOWN)
        _number_marker(d, centers[break_i + 2], _price_to_y(rows[break_i + 2][3], top, bottom, lo, hi) + 38, 3, DOWN)
        _number_marker(d, right - 82, y_structure + 55, 4, WAIT)

        _explanation_cards(d, (
            "كان الاتجاه صاعدًا",
            "انكسر القاع المهم",
            "السعر ثبت تحت القاع",
            "نوقف الشراء وننتظر اتجاهًا جديدًا",
        ))

def _draw_breakout_explanation(d, box, rows, centers, meta, lo, hi, variant):
    left, top, right, bottom = box
    level = meta["level"]
    y_level = _hline(d, box, level, lo, hi, "المقاومة", INFO)

    if not variant:
        bi = meta["break_index"]
        ri = meta["retest_index"]
        by = _price_to_y(rows[bi][3], top, bottom, lo, hi)
        ry = _price_to_y(rows[ri][3], top, bottom, lo, hi)

        _arrow(d, (centers[bi] - 25, y_level + 28), (centers[bi], by), color=UP, width=6)
        _tag(d, centers[bi] - 75, by - 56, "كسر المقاومة", color=(24, 82, 62), size=25)
        _tag(d, centers[ri] - 50, ry + 24, "إعادة اختبار", color=(56, 62, 72), size=25)

        _number_marker(d, centers[7], y_level - 40, 1, INFO)
        _number_marker(d, centers[bi], by - 45, 2, UP)
        _number_marker(d, centers[ri], ry + 64, 3, WAIT)
        _number_marker(d, centers[ri + 2], _price_to_y(rows[ri + 2][3], top, bottom, lo, hi) - 42, 4, UP)

        _explanation_cards(d, (
            "هذه مقاومة مهمة",
            "السعر كسرها وأغلق فوقها",
            "رجع واختبرها من الأعلى",
            "ثباته فوقها يجعل الشراء أقوى",
        ))
    else:
        fi = meta["fake_index"]
        fy = _price_to_y(rows[fi][3], top, bottom, lo, hi)

        _tag(d, centers[fi] - 72, fy + 22, "رجع تحت المقاومة", color=(91, 33, 33), size=25)
        _number_marker(d, centers[7], y_level - 40, 1, INFO)
        _number_marker(d, centers[9], _price_to_y(rows[9][3], top, bottom, lo, hi) - 46, 2, UP)
        _number_marker(d, centers[fi], fy + 62, 3, DOWN)
        _number_marker(d, right - 82, y_level + 56, 4, WAIT)

        _explanation_cards(d, (
            "هذه مقاومة مهمة",
            "السعر اخترقها للأعلى",
            "رجع بسرعة وأغلق تحتها",
            "هذا كسر كاذب: القرار انتظار",
        ))

def _draw_general_explanation(d, box, rows, centers, meta, lo, hi, side, variant):
    left, top, right, bottom = box
    support = meta.get("support")
    if support:
        _hline(d, box, support, lo, hi, "الدعم", INFO)
    if side == "بيع":
        _tag(d, left + 22, top + 16, "بيع: نراقب ضعف الصعود عند المقاومة", color=(91, 33, 33), size=27)
    elif side == "انتظار":
        _tag(d, left + 22, top + 16, "انتظار حتى يظهر تأكيد", color=(78, 63, 25), size=27)
    else:
        _tag(d, left + 22, top + 16, "شراء: الاتجاه صاعد وننتظر دخولًا واضحًا", color=(24, 82, 62), size=27)

    if variant:
        _tag(d, left + 22, top + 58, "الفخ: شمعة واحدة لا تكفي", color=(91, 33, 33), size=25)


def _draw_trade_chart(d, kind, side, variant):
    box = _chart_box(d)
    rows, meta = _series(kind, side=side, variant=variant)
    centers, lo, hi = _draw_candles(d, box, rows)

    if kind == "correction":
        _draw_correction_explanation(d, box, rows, centers, meta, lo, hi, variant)
    elif kind == "breakout":
        _draw_breakout_explanation(d, box, rows, centers, meta, lo, hi, variant)
    elif kind == "event":
        idx = meta["news_index"]
        left, top, right, bottom = box
        d.line((centers[idx], top, centers[idx], bottom), fill=WAIT, width=3)
        _tag(d, centers[idx] - 40, top + 16, "وقت الخبر", color=(78, 63, 25))
        _tag(d, left + 22, top + 58, "لا تحكم من أول شمعة — انتظر فهم رد السوق", color=(56, 62, 72), size=25)
    elif kind == "volatility":
        left, top, right, bottom = box
        _tag(d, left + 22, top + 16, "تذبذب هادئ", color=(56, 62, 72))
        _tag(d, right - 225, top + 16, "تذبذب قوي", color=(78, 63, 25))
        _tag(d, left + 22, top + 58, "كلما اتسعت الحركة، الستوب القديم قد يصبح قريبًا جدًا", color=(56, 62, 72), size=25)
    else:
        _draw_general_explanation(d, box, rows, centers, meta, lo, hi, side, variant)

    if kind not in ("correction", "breakout"):
        _trade_levels(d, box, meta, lo, hi, side)


def _draw_diagram(d, kind, variant):
    left, top, right, bottom = _chart_box(d)

    if kind == "execution":
        _tag(d, left + 70, top + 70, "سعر البيع")
        _tag(d, right - 260, top + 70, "سعر الشراء")
        _arrow(d, (left + 290, top + 125), (right - 290, top + 125), color=WAIT)
        _tag(d, left + 410, top + 150, "الفرق بينهما = السبريد", color=(78, 63, 25), size=27)
        _tag(d, left + 120, top + 250, "التنفيذ الحقيقي قد يتأثر بالانزلاق", color=(56, 62, 72), size=27)
        _tag(d, left + 120, top + 300, "كلما كان الهدف صغيرًا، تكلفة التنفيذ تصير أهم", color=(56, 62, 72), size=25)
    elif kind == "matrix":
        labels = ["الدولار", "العوائد", "الخوف", "التدفقات", "الزخم"]
        x = left + 55
        for i, label in enumerate(labels):
            d.ellipse((x, top + 145, x + 125, top + 270), outline=LEVEL, width=3)
            _draw_ar(d, (x + 62, top + 208), label, size=18, anchor="mm")
            if i < len(labels) - 1:
                _arrow(d, (x + 130, top + 208), (x + 166, top + 208), color=LEVEL, width=3)
            x += 185
        _tag(d, left + 250, bottom - 88, "الذهب لا يتحرك بسبب عامل واحد دائمًا", color=(56, 62, 72), size=27)
    elif kind == "sessions":
        blocks = [("آسيا", left + 55), ("لندن", left + 285), ("نيويورك", left + 515), ("تداخل الجلسات", left + 745)]
        for label, x in blocks:
            d.rounded_rectangle((x, top + 120, x + 190, top + 285), radius=18, outline=LEVEL, width=3)
            _draw_ar(d, (x + 95, top + 202), label, size=21, bold=True, anchor="mm")
        _tag(d, left + 240, bottom - 90, "السيولة وسرعة الحركة تختلف حسب الجلسة", color=(56, 62, 72), size=27)
    elif kind == "expectancy":
        _tag(d, left + 125, top + 100, "نسبة الفوز", size=22)
        _tag(d, right - 340, top + 100, "متوسط الربح والخسارة", size=20)
        _draw_ar(d, (left + 250, top + 220), "٤٠٪", size=46, bold=True, anchor="mm")
        _draw_ar(d, (right - 250, top + 220), "٢٫٥ ضعف المخاطرة", size=31, bold=True, anchor="mm")
        _tag(d, left + 260, bottom - 90, "جودة النظام أهم من نسبة الفوز وحدها", color=(56, 62, 72), size=27)
    elif kind == "backtest":
        _tag(d, left + 165, top + 145, "نبني الفكرة", size=22)
        _tag(d, right - 360, top + 145, "نختبرها على بيانات جديدة", size=20)
        _arrow(d, (left + 365, top + 200), (right - 385, top + 200), color=INFO)
        _tag(d, left + 300, bottom - 100, "ممنوع استخدام معلومة من المستقبل", color=(91, 33, 33), size=27)
    else:
        items = ["الفكرة", "متى تبطل", "حجم المخاطرة", "التنفيذ", "المراجعة"]
        x = left + 25
        for i, item in enumerate(items):
            d.rounded_rectangle((x, top + 155, x + 170, top + 265), radius=15, outline=LEVEL, width=3)
            _draw_ar(d, (x + 85, top + 210), item, size=17, bold=True, anchor="mm")
            if i < len(items) - 1:
                _arrow(d, (x + 175, top + 210), (x + 198, top + 210), color=LEVEL, width=3)
            x += 200

    if variant:
        _tag(d, right - 230, bottom - 54, "انتبه للفخ", color=(91, 33, 33), size=27)


def render_lesson_visual(kind="structure", variant=0, title="", side="شراء"):
    """Return a PNG with Arabic labels and a clear teaching direction."""
    side = side if side in ("شراء", "بيع", "انتظار", "شرح") else "شرح"
    img, d = _base(side=side)

    if kind in ("trend", "structure", "timeframe", "breakout", "event", "volatility", "positioning", "correction"):
        _draw_trade_chart(d, kind, side, int(variant or 0))
    else:
        _draw_diagram(d, kind, int(variant or 0))

    if kind not in ("correction", "breakout"):
        _draw_ar(d, (540, 1040), "افهم السبب من الرسم — لا تحفظ الشكل", size=24, fill=MUTED, anchor="mm")

    out = BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()
