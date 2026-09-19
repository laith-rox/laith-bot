"""Generate offline educational visuals for V4 lessons.

Price-reading lessons use synthetic candlestick charts so the student sees a
real trading-chart shape instead of an abstract line diagram. All visuals are
clearly marked as training examples and never use live prices.
"""
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 675
BG = (14, 17, 22)
PANEL = (19, 23, 30)
GRID = (44, 50, 60)
TEXT = (235, 238, 242)
MUTED = (151, 158, 170)
UP = (38, 181, 130)
DOWN = (225, 78, 78)
LEVEL = (148, 157, 171)
ACCENT = (233, 194, 89)


def _font(size=34):
    for name in ("DejaVuSans-Bold.ttf", "Arial Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _small(size=24):
    for name in ("DejaVuSans.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _base():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((30, 24, W - 30, H - 24), radius=26, fill=PANEL, outline=(61, 67, 77), width=2)
    d.text((60, 48), "XAU/USD TRAINING CHART", font=_font(31), fill=TEXT)
    d.text((60, 88), "Synthetic educational example  •  NOT LIVE MARKET DATA", font=_small(20), fill=MUTED)
    return img, d


def _chart_box(d):
    left, top, right, bottom = 72, 140, 1090, 585
    for i in range(6):
        y = top + (bottom - top) * i / 5
        d.line((left, y, right, y), fill=GRID, width=1)
    for i in range(8):
        x = left + (right - left) * i / 7
        d.line((x, top, x, bottom), fill=GRID, width=1)
    d.rectangle((left, top, right, bottom), outline=(74, 81, 92), width=2)
    return left, top, right, bottom


def _ohlc_from_closes(closes):
    rows = []
    prev = closes[0] - 0.8
    wick_pattern = (1.8, 2.5, 1.4, 2.1, 1.6, 2.8)
    for i, close in enumerate(closes):
        open_ = prev
        wick = wick_pattern[i % len(wick_pattern)]
        high = max(open_, close) + wick
        low = min(open_, close) - wick * 0.82
        rows.append((open_, high, low, close))
        prev = close
    return rows


def _price_series(kind, variant=0):
    if kind == "breakout":
        closes = [4295, 4298, 4296, 4300, 4298, 4302, 4301, 4304, 4307, 4313, 4317, 4311, 4314, 4319, 4323, 4328, 4326, 4332]
        meta = {"level": 4308.0, "entry": 4312.5, "stop": 4304.0, "target": 4328.0, "retest": 11}
    elif kind == "event":
        closes = [4300, 4301, 4299, 4300, 4302, 4301, 4300, 4301, 4300, 4318, 4309, 4314, 4311, 4317, 4321, 4318, 4324, 4327]
        meta = {"level": 4300.0, "entry": 4313.0, "stop": 4305.0, "target": 4325.0, "news": 9}
    elif kind == "volatility":
        closes = [4300, 4301, 4300, 4302, 4301, 4303, 4302, 4304, 4303, 4310, 4305, 4314, 4307, 4317, 4310, 4321, 4315, 4325]
        meta = {"level": 4303.0, "entry": 4310.0, "stop": 4301.0, "target": 4324.0}
    else:
        closes = [4290, 4295, 4293, 4299, 4297, 4304, 4301, 4308, 4305, 4312, 4309, 4316, 4313, 4320, 4317, 4324, 4321, 4328]
        meta = {"level": 4296.0, "entry": 4307.0, "stop": 4299.0, "target": 4325.0}
    if variant:
        # The trap version visually shows a late chase followed by a pullback.
        closes = list(closes)
        closes[-4:] = [closes[-5] + 7, closes[-5] + 11, closes[-5] + 4, closes[-5] + 1]
        meta = dict(meta)
        meta["entry"] = closes[-4] + 0.5
        meta["target"] = closes[-4] + 7.0
    return _ohlc_from_closes(closes), meta


def _draw_price_axis(d, box, lo, hi):
    left, top, right, bottom = box
    for i in range(6):
        price = hi - (hi - lo) * i / 5
        y = top + (bottom - top) * i / 5
        d.text((right + 10, y - 10), f"{price:.1f}", font=_small(17), fill=MUTED)
    labels = ("09:00", "10:00", "11:00", "12:00", "13:00", "14:00")
    for i, label in enumerate(labels):
        x = left + (right - left) * i / (len(labels) - 1)
        d.text((x - 20, bottom + 10), label, font=_small(16), fill=MUTED)


def _price_to_y(price, top, bottom, lo, hi):
    return bottom - (price - lo) / (hi - lo) * (bottom - top)


def _draw_candles(d, box, rows):
    left, top, right, bottom = box
    lo = min(r[2] for r in rows)
    hi = max(r[1] for r in rows)
    pad = max(2.0, (hi - lo) * 0.08)
    lo -= pad
    hi += pad
    step = (right - left - 26) / len(rows)
    body_w = max(10, int(step * 0.55))

    centers = []
    for i, (open_, high, low, close) in enumerate(rows):
        x = left + 13 + step * (i + 0.5)
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


def _tag(d, x, y, text, fill=(35, 41, 51)):
    font = _small(18)
    bbox = d.textbbox((0, 0), text, font=font)
    w = max(88, bbox[2] - bbox[0] + 22)
    h = 34
    x = max(48, min(W - w - 48, x))
    y = max(126, min(H - h - 45, y))
    d.rounded_rectangle((x, y, x + w, y + h), radius=8, fill=fill, outline=(97, 105, 118), width=1)
    d.text((x + 11, y + 7), text, font=font, fill=TEXT)


def _hline(d, box, price, lo, hi, text, color=LEVEL):
    left, top, right, bottom = box
    y = _price_to_y(price, top, bottom, lo, hi)
    d.line((left, y, right, y), fill=color, width=2)
    _tag(d, left + 12, y - 40, text)
    return y


def _zone(d, box, low_price, high_price, lo, hi, text):
    left, top, right, bottom = box
    y1 = _price_to_y(high_price, top, bottom, lo, hi)
    y2 = _price_to_y(low_price, top, bottom, lo, hi)
    d.rectangle((left + 6, y1, right - 6, y2), outline=(98, 111, 128), width=2)
    _tag(d, left + 18, y1 + 8, text)


def _draw_trade_chart(d, kind, variant):
    box = _chart_box(d)
    rows, meta = _price_series(kind, variant)
    centers, lo, hi = _draw_candles(d, box, rows)
    left, top, right, bottom = box

    if kind == "breakout":
        _hline(d, box, meta["level"], lo, hi, "RESISTANCE")
        idx = meta.get("retest", 11)
        y = _price_to_y(rows[idx][3], top, bottom, lo, hi)
        _tag(d, centers[idx] - 50, y + 18, "RETEST")
    elif kind == "event":
        idx = meta.get("news", 9)
        d.line((centers[idx], top, centers[idx], bottom), fill=ACCENT, width=3)
        _tag(d, centers[idx] - 40, top + 10, "NEWS")
    elif kind == "volatility":
        _tag(d, left + 75, top + 25, "LOW VOL")
        _tag(d, right - 190, top + 25, "HIGH VOL")
    else:
        _zone(d, box, meta["level"] - 2.0, meta["level"] + 2.0, lo, hi, "SUPPORT ZONE")

    y_entry = _price_to_y(meta["entry"], top, bottom, lo, hi)
    y_stop = _price_to_y(meta["stop"], top, bottom, lo, hi)
    y_target = _price_to_y(meta["target"], top, bottom, lo, hi)
    d.line((right - 330, y_entry, right - 18, y_entry), fill=ACCENT, width=2)
    _tag(d, right - 320, y_entry - 40, "ENTRY")
    d.line((right - 250, y_stop, right - 18, y_stop), fill=DOWN, width=2)
    _tag(d, right - 240, y_stop + 6, "SL")
    d.line((right - 250, y_target, right - 18, y_target), fill=UP, width=2)
    _tag(d, right - 240, y_target - 40, "TP")

    badge = "LATE ENTRY / TRAP" if variant else "M15 EXAMPLE"
    _tag(d, left + 18, bottom - 45, badge)


def _diagram_base(d):
    box = _chart_box(d)
    return box


def _arrow(d, a, b):
    d.line((a[0], a[1], b[0], b[1]), fill=TEXT, width=4)
    x, y = b
    d.polygon([(x, y), (x - 15, y - 9), (x - 12, y + 11)], fill=TEXT)


def _draw_nonprice_diagram(d, kind, variant):
    left, top, right, bottom = _diagram_base(d)
    if kind == "execution":
        d.rectangle((left + 130, top + 100, left + 410, top + 260), outline=LEVEL, width=3)
        d.rectangle((right - 410, top + 100, right - 130, top + 260), outline=LEVEL, width=3)
        _tag(d, left + 210, top + 55, "BID")
        _tag(d, right - 330, top + 55, "ASK")
        _arrow(d, (left + 430, top + 180), (right - 430, top + 180))
        _tag(d, left + 455, top + 205, "SPREAD")
        d.text((left + 250, bottom - 78), "SLIPPAGE  •  FEES  •  IMPACT", font=_small(25), fill=TEXT)
    elif kind == "matrix":
        labels = ["USD", "REAL YIELD", "RISK", "FLOWS", "MOMENTUM"]
        x0 = left + 70
        for i, label in enumerate(labels):
            x = x0 + i * 185
            d.ellipse((x, top + 135, x + 102, top + 237), outline=LEVEL, width=3)
            d.text((x + 14, top + 173), label, font=_small(17), fill=TEXT)
            if i < 4:
                _arrow(d, (x + 105, top + 186), (x + 169, top + 186))
        d.text((left + 280, bottom - 90), "READ THE SYSTEM — NOT ONE VARIABLE", font=_small(25), fill=TEXT)
    elif kind == "sessions":
        blocks = [("ASIA", left + 80, left + 265), ("LONDON", left + 300, left + 505),
                  ("NEW YORK", left + 540, left + 775), ("OVERLAP", left + 810, right - 45)]
        for name, x1, x2 in blocks:
            d.rounded_rectangle((x1, top + 125, x2, top + 285), radius=18, outline=LEVEL, width=3)
            d.text((x1 + 18, top + 190), name, font=_small(20), fill=TEXT)
        d.text((left + 250, bottom - 85), "LIQUIDITY CHANGES THROUGH THE DAY", font=_small(24), fill=TEXT)
    elif kind == "expectancy":
        d.rounded_rectangle((left + 120, top + 80, left + 440, top + 300), radius=18, outline=LEVEL, width=3)
        d.rounded_rectangle((right - 440, top + 80, right - 120, top + 300), radius=18, outline=LEVEL, width=3)
        d.text((left + 205, top + 125), "WIN RATE", font=_font(28), fill=TEXT)
        d.text((right - 355, top + 125), "PAYOFF", font=_font(28), fill=TEXT)
        d.text((left + 225, top + 205), "40%", font=_font(44), fill=TEXT)
        d.text((right - 330, top + 205), "2.5R", font=_font(44), fill=TEXT)
        d.text((left + 310, bottom - 80), "EXPECTANCY > WIN RATE ALONE", font=_small(24), fill=TEXT)
    elif kind == "backtest":
        d.rounded_rectangle((left + 110, top + 90, left + 470, top + 300), radius=18, outline=LEVEL, width=3)
        d.rounded_rectangle((right - 470, top + 90, right - 110, top + 300), radius=18, outline=LEVEL, width=3)
        d.text((left + 225, top + 165), "TRAIN", font=_font(31), fill=TEXT)
        d.text((right - 350, top + 165), "TEST", font=_font(31), fill=TEXT)
        _arrow(d, (left + 490, top + 195), (right - 490, top + 195))
        d.text((left + 350, bottom - 80), "NO LOOK-AHEAD", font=_small(25), fill=TEXT)
    else:
        items = ["THESIS", "INVALIDATE", "SIZE", "EXECUTE", "REVIEW"]
        x = left + 35
        for i, item in enumerate(items):
            d.rounded_rectangle((x, top + 150, x + 165, top + 250), radius=15, outline=LEVEL, width=3)
            d.text((x + 15, top + 190), item, font=_small(18), fill=TEXT)
            if i < 4:
                _arrow(d, (x + 170, top + 200), (x + 195, top + 200))
            x += 195

    if variant:
        _tag(d, right - 190, bottom - 48, "TRAP CHECK")


def render_lesson_visual(kind="structure", variant=0, title="TRADING LESSON"):
    # 'title' is intentionally not rendered: lesson titles can contain Arabic
    # and server fonts may not shape Arabic correctly. The Telegram caption
    # carries the full Arabic explanation while the image stays crisp.
    img, d = _base()
    if kind in ("trend", "structure", "timeframe", "breakout", "event", "volatility", "positioning"):
        _draw_trade_chart(d, kind, variant)
    else:
        _draw_nonprice_diagram(d, kind, variant)

    out = BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()
