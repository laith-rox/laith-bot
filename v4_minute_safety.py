"""Independent minute warnings for V4 paper trades. Never places/manages orders."""
from datetime import datetime
import json
import logging
import threading
import time

from fast import MinuteMarket
from market import DataError, UTC
from safety_monitor import evaluate_warning, warning_message
from storage import Store
from transport import Telegram, dispatch

LOG = logging.getLogger('laith.v4.safety')
KIND = 'v4_safety'


def active_trades(store):
    trades = []
    official = store.get('v4_active')
    if official and official.get('status') == 'active':
        trades.append(official)
    for row in store.db.execute('SELECT data FROM v4_quick_paper'):
        trade = json.loads(row[0])
        if trade.get('status') == 'active':
            trades.append(trade)
    return {t['id']: t for t in trades}


def monitor(store, bars, now):
    with store.db:
        store.db.execute('BEGIN IMMEDIATE')
        for trade in active_trades(store).values():
            key = 'v4_minute_safety:' + trade['id']
            previous = store.get(key) or {'peak': trade['entry']}
            event, state = evaluate_warning(trade, bars, now, previous)
            store._set(key, state)
            if event:
                event_id = f"v4rapid:{trade['id']}:{event['episode']}:{event['kind']}"
                store._enqueue(event_id, KIND, '⛔️ <b>طوارئ V4 — مراقبة الدقيقة</b>\n' + warning_message(trade, event),
                               now.timestamp(), None, now.timestamp()+90)
                store._set('v4_alert_trade:'+event_id, trade['id'])
                LOG.info('minute_alert trade=%s kind=%s', trade['id'], event['kind'])
        store._set('v4_minute_safety_status', {'ok': True, 'checked': now.timestamp(),
                                            'source_time': bars[-1].end.timestamp()})


def flush(store, telegram, now=None):
    epoch = time.time() if now is None else now
    active = active_trades(store)
    # Drop warnings for trades closed by the lifecycle worker before delivery.
    for row in store.db.execute("SELECT id,signal_id FROM outbox WHERE kind=? AND status='pending'", (KIND,)).fetchall():
        trade_id = store.get('v4_alert_trade:'+row['id'])
        if not active or (trade_id and trade_id not in active):
            with store.db:
                store.db.execute("UPDATE outbox SET status='failed',error='signal_no_longer_active' WHERE id=? AND status='pending'", (row['id'],))
    dispatch(store, telegram, now=epoch, only_kind=KIND, limit=10)


def run(args, stop, market_closed):
    store = Store(args.db)
    market = MinuteMarket(args.twelve_key)
    telegram = Telegram(args.telegram_token, args.telegram_chat or '') if args.telegram_token else None
    next_fetch = 0
    LOG.info('minute_safety_started interval=60 independent=true source=closed_1m')
    try:
        while not stop.is_set():
            try:
                now = datetime.now(UTC)
                if market_closed(now):
                    stop.wait(2)
                    continue
                trades = active_trades(store)
                if trades and time.time() >= next_fetch:
                    next_fetch = time.time()+60
                    try:
                        bars = market.fetch(now, size=60)
                        monitor(store, bars, datetime.now(UTC))
                        LOG.info('minute_safety_checked trades=%s source=%s',len(trades),bars[-1].end.isoformat())
                    except DataError as exc:
                        previous = store.get('v4_minute_safety_status') or {}
                        epoch = time.time()
                        store.set('v4_minute_safety_status', {'ok': False, 'checked': epoch, 'reason': str(exc)})
                        if previous.get('ok', True):
                            store.enqueue('v4rapid:unavailable:'+str(int(epoch)), KIND,
                                '⛔️ طوارئ V4: تعذّر تحديث بيانات الدقيقة.\nراقب وقفك عند الوسيط؛ التنبيه قد يتأخر.',
                                epoch, expires=epoch+180)
                        if str(exc) == 'minute_quota_reached': next_fetch = epoch+900
                        LOG.warning('minute_safety_unavailable reason=%s', str(exc))
                destination = store.get('v4_telegram_group_id') or store.get('v4_telegram_chat_id') or args.telegram_chat
                if telegram and destination:
                    telegram.chat_id = str(destination)
                    flush(store, telegram)
            except Exception as exc:
                LOG.error('minute_safety_failed category=%s', type(exc).__name__)
            stop.wait(2)
    finally:
        store.close()


def start(args, market_closed):
    stop = threading.Event()
    threading.Thread(target=run, args=(args,stop,market_closed), daemon=True, name='v4-minute-safety').start()
    return stop
