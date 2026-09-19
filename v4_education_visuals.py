"""Generate offline educational chart-style visuals for V4 lessons."""
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 675


def _font(size=34):
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _small(size=24):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _base(title, subtitle):
    img = Image.new("RGB", (W, H), (17, 19, 24))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((40, 35, W-40, H-35), radius=28, outline=(85, 88, 98), width=2)
    d.text((72, 58), title[:42], font=_font(36), fill=(240, 240, 240))
    d.text((72, 106), subtitle[:72], font=_small(23), fill=(180, 184, 194))
    return img, d


def _axes(d):
    d.line((95, 560, 1110, 560), fill=(95, 99, 110), width=3)
    d.line((95, 175, 95, 560), fill=(95, 99, 110), width=3)


def _poly(d, pts, width=8, fill=(224, 224, 224)):
    d.line(pts, fill=fill, width=width, joint="curve")


def _label(d, xy, text):
    x, y = xy
    box=(x, y, x+150, y+42)
    d.rounded_rectangle(box, radius=10, fill=(35, 38, 47), outline=(120, 124, 135), width=1)
    d.text((x+12,y+8), text, font=_small(20), fill=(238,238,238))


def _arrow(d, a, b):
    d.line((a[0],a[1],b[0],b[1]), fill=(220,220,220), width=5)
    x,y=b
    d.polygon([(x,y),(x-16,y-10),(x-12,y+12)], fill=(220,220,220))


def render_lesson_visual(kind="structure", variant=0, title="TRADING LESSON"):
    img, d = _base(title.upper(), "Educational schematic — not a live signal")
    _axes(d)

    if kind in ("trend","structure","timeframe"):
        pts=[(120,510),(250,430),(350,470),(500,350),(620,395),(780,280),(900,325),(1070,215)]
        _poly(d, pts)
        d.rectangle((170,450,420,520), outline=(135,135,145), width=3)
        d.rectangle((760,220,1020,300), outline=(135,135,145), width=3)
        _label(d,(180,525),"SUPPORT")
        _label(d,(795,175),"TARGET")
        _arrow(d,(520,420),(690,340))
        _label(d,(500,455),"ENTRY")

    elif kind == "breakout":
        d.line((120,395,1080,395), fill=(135,135,145), width=4)
        pts=[(125,500),(260,455),(380,420),(500,398),(620,345),(730,365),(820,395),(910,320),(1070,245)]
        _poly(d,pts)
        _label(d,(150,335),"RESISTANCE")
        _label(d,(690,405),"RETEST")
        _label(d,(900,265),"FOLLOW")
        _arrow(d,(625,335),(710,360))

    elif kind == "event":
        pts=[(120,470),(300,465),(480,460),(585,455),(610,250),(645,335),(760,290),(920,305),(1070,255)]
        _poly(d,pts)
        d.line((610,180,610,560), fill=(135,135,145), width=3)
        _label(d,(520,185),"NEWS")
        _label(d,(650,405),"REPRICE")
        _label(d,(855,215),"CONFIRM")

    elif kind == "volatility":
        pts1=[(120,455),(250,430),(390,442),(520,420),(650,435),(780,410),(920,425),(1070,400)]
        pts2=[(120,500),(250,400),(390,480),(520,325),(650,470),(780,290),(920,450),(1070,245)]
        _poly(d,pts1,width=5,fill=(160,160,168))
        _poly(d,pts2,width=7,fill=(235,235,235))
        _label(d,(180,520),"LOW VOL")
        _label(d,(800,500),"HIGH VOL")
        _label(d,(780,220),"SMALLER SIZE")

    elif kind == "execution":
        d.rectangle((185,280,1015,470), outline=(145,145,155), width=3)
        d.line((600,220,600,525), fill=(145,145,155), width=3)
        _label(d,(260,225),"BID")
        _label(d,(760,225),"ASK")
        _arrow(d,(530,370),(670,370))
        _label(d,(475,430),"SPREAD")
        d.text((255,500),"SLIPPAGE  •  FEES  •  IMPACT",font=_small(26),fill=(210,210,215))

    elif kind == "matrix":
        labels=["USD","REAL YIELD","RISK","FLOWS","MOMENTUM"]
        x0=160
        for i,label in enumerate(labels):
            x=x0+i*180
            d.ellipse((x,300,x+90,390),outline=(160,160,170),width=4)
            d.text((x+16,330),label,font=_small(18),fill=(235,235,235))
            if i<4:
                _arrow(d,(x+95,345),(x+165,345))
        d.text((395,475),"READ THE SYSTEM — NOT ONE VARIABLE",font=_small(26),fill=(220,220,225))

    elif kind == "sessions":
        blocks=[("ASIA",160,320),("LONDON",370,550),("NY",580,760),("OVERLAP",790,1040)]
        for name,x1,x2 in blocks:
            d.rounded_rectangle((x1,300,x2,460),radius=18,outline=(145,145,155),width=3)
            d.text((x1+20,360),name,font=_small(22),fill=(235,235,235))
        d.text((220,500),"Liquidity and behavior change by session",font=_small(27),fill=(215,215,220))

    elif kind == "positioning":
        vals=[170,250,340,300,430,515,465,600,690,620]
        pts=[]
        for i,v in enumerate(vals):
            x=135+i*95
            y=540-v//2
            pts.append((x,y))
        _poly(d,pts)
        d.text((225,500),"POSITIONING = CONTEXT, NOT TRIGGER",font=_small(28),fill=(220,220,225))

    elif kind == "expectancy":
        d.rectangle((180,245,520,470),outline=(150,150,160),width=3)
        d.rectangle((680,245,1020,470),outline=(150,150,160),width=3)
        d.text((255,290),"WIN RATE",font=_font(30),fill=(238,238,238))
        d.text((770,290),"PAYOFF",font=_font(30),fill=(238,238,238))
        d.text((270,370),"40%",font=_font(48),fill=(238,238,238))
        d.text((760,370),"2.5R",font=_font(48),fill=(238,238,238))
        d.text((315,515),"EXPECTANCY > WIN RATE ALONE",font=_small(28),fill=(220,220,225))

    elif kind == "backtest":
        d.line((150,390,1050,390),fill=(145,145,155),width=3)
        d.rectangle((160,260,610,500),outline=(145,145,155),width=3)
        d.rectangle((650,260,1040,500),outline=(145,145,155),width=3)
        d.text((285,325),"TRAIN",font=_font(34),fill=(238,238,238))
        d.text((760,325),"TEST",font=_font(34),fill=(238,238,238))
        _arrow(d,(590,390),(680,390))
        d.text((310,520),"NO LOOK-AHEAD",font=_small(25),fill=(220,220,225))

    elif kind == "process":
        items=["THESIS","INVALIDATE","SIZE","EXECUTE","REVIEW"]
        x=130
        for i,item in enumerate(items):
            d.rounded_rectangle((x,315,x+160,410),radius=16,outline=(150,150,160),width=3)
            d.text((x+15,350),item,font=_small(19),fill=(235,235,235))
            if i<4:
                _arrow(d,(x+165,365),(x+195,365))
            x+=200

    else:
        pts=[(120,490),(240,430),(350,455),(500,340),(635,390),(760,310),(900,350),(1070,260)]
        _poly(d,pts)
        d.line((180,445,1040,445),fill=(140,140,150),width=3)
        _label(d,(185,455),"LEVEL")
        _label(d,(515,295),"TRIGGER")
        _label(d,(880,220),"TARGET")

    if variant:
        d.text((835,585),"TRAP CHECK",font=_small(28),fill=(235,235,235))
        d.line((825,620,1050,620),fill=(150,150,160),width=3)

    out=BytesIO()
    img.save(out,format="PNG",optimize=True)
    return out.getvalue()
