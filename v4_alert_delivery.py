"""Persistent-alert delivery adapter for Laith V4 Telegram-only workflow.

Caller owns a Store with get/set and a notifier with send. No MT5 access.
"""


def deliver_once(store, notifier, notice):
    """Send once per alert key. Mark only after notifier confirms success.

    A failed send remains retryable; persistence across restarts depends on Store.
    """
    if not notice or not notice.get("key") or not notice.get("message"):
        return False
    key = str(notice["key"])
    state_key = "v4_alert_sent:" + key
    if store.get(state_key):
        return False
    try:
        result = notifier.send(notice["message"])
    except (OSError, TimeoutError, ConnectionError):
        # Transport failure is not delivery confirmation; permit a later retry.
        return False
    if result is not True:
        return False
    store.set(state_key, True)
    return True
