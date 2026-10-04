"""Telegram decision notices for Gigi REAL analysis.

Notification-only. This module cannot publish broker commands and contains no
MT5/order execution path. It reports every generated BUY/SELL idea, including
ideas rejected by execution gates.
"""
from __future__ import annotations

import json
import os
import time
from urllib.request import Request, urlopen

RELAY_URL=os.getenv("REAL_DECISION_RELAY_URL","").strip()
RELAY_TOKEN=os.getenv("REAL_DECISION_RELAY_TOKEN","").strip()
TIMEOUT_SECONDS=8


def _f(value):
    try:
        return f"{float(value):.2f}"
    except Exception:
        return "-"


def trade_levels(signal, spot):
    side=str(signal.get("side") or "").upper()
    try:
        spot=float(spot)
        risk=float(signal.get("risk_distance") or 0)
        target_r=float(signal.get("target_r") or 1.5)
    except Exception:
        return None
    if side not in ("BUY","SELL") or spot<=0 or risk<=0:
        return None
    if side=="BUY":
        sl=spot-risk; tp=spot+risk*target_r
    else:
        sl=spot+risk; tp=spot-risk*target_r
    return {"entry":spot,"sl":sl,"tp":tp,"target_r":target_r}


def build(signal, spot, outcome, reject_reason=None):
    side=str(signal.get("side") or "").upper()
    if side not in ("BUY","SELL"):
        return None
    levels=trade_levels(signal,spot)
    if not levels:
        return None
    mode="MAIN" if str(signal.get("mode") or "").upper()=="MAIN" else "SNIPER"
    strength=sum(bool(x) for x in (signal.get("checks") or {}).get(side,[]))
    ctx=signal.get("gigi_context") or {}
    readiness=signal.get("readiness") or {}
    setup=signal.get("setup") or {}
    crowding=signal.get("crowding") or {}
    uncertainty=signal.get("uncertainty") or {}
    status={
        "PUBLISHED":"✅ مرّرت للجسر",
        "REJECTED":"⛔️ رفضها حاجز التنفيذ",
        "ANALYSIS_ONLY":"🧠 تحليل فقط",
    }.get(str(outcome).upper(),str(outcome))
    direction="شراء 🟢" if side=="BUY" else "بيع 🔴"
    reason=str(reject_reason or "-")
    text=(
        "🧠 جيجي — صفقة XAUUSD\n"
        f"الحالة: {status}\n"
        f"الاتجاه: {direction}\n"
        f"النمط: {mode}\n"
        f"الدخول المرجعي: {_f(levels['entry'])}\n"
        f"وقف الخسارة المقترح: {_f(levels['sl'])}\n"
        f"الهدف المقترح: {_f(levels['tp'])} ({levels['target_r']:.2f}R)\n"
        f"توافق الشروط: {strength}/7\n"
        f"Setup: {setup.get('name') or setup.get('setup') or '-'}\n"
        f"Gigi: {ctx.get('alignment') or '-'} | score={ctx.get('score',0)}\n"
        f"Crowding: {crowding.get('dominant_risk') or 'BALANCED'}\n"
        f"Uncertainty: {uncertainty.get('state') or uncertainty.get('level') or '-'}\n"
        f"جاهزية: {readiness.get('state') or readiness.get('decision') or '-'}\n"
        f"سبب الرفض/المنع: {reason}\n"
        "ملاحظة: الرفض لا يمسح الفكرة؛ تُحفظ للتعلّم والمراجعة."
    )
    event_id="|".join([
        str(signal.get("bar") or ""),
        mode,side,str(outcome).upper(),reason,
    ])
    return {"event_id":event_id,"text":text,"levels":levels}


def send(signal, spot, outcome, reject_reason=None, relay_url=None, relay_token=None, opener=None):
    notice=build(signal,spot,outcome,reject_reason)
    if notice is None:
        return {"ok":False,"reason":"no_trade_idea"}
    url=(relay_url if relay_url is not None else RELAY_URL).strip()
    token=(relay_token if relay_token is not None else RELAY_TOKEN).strip()
    if not url or not token:
        return {"ok":False,"reason":"decision_relay_not_configured","notice":notice}
    payload=json.dumps(
        {"event_id":notice["event_id"],"text":notice["text"]},
        ensure_ascii=False,
    ).encode("utf-8")
    req=Request(url,data=payload,headers={
        "Content-Type":"application/json",
        "X-Relay-Token":token,
    },method="POST")
    opener=opener or urlopen
    with opener(req,timeout=TIMEOUT_SECONDS) as resp:
        body=json.loads(resp.read().decode("utf-8"))
    return {"ok":bool(body.get("ok")),"relay":body,"notice":notice,"sent_at":time.time()}
