"""V4-specific market key selection without exposing secret values."""
import os


def select_v4_twelve_key(env=None):
    """Use only the dedicated V4 key; never fall back to the shared bot key."""
    env = os.environ if env is None else env
    v4_key = env.get("V4_TWELVE_DATA_API_KEY")
    if v4_key:
        return v4_key, "V4_TWELVE_DATA_API_KEY"
    return None, "missing"


def apply_v4_twelve_key_precedence(env=None):
    """Force this V4 worker to use only its dedicated Twelve Data key.

    The existing parser reads TWELVE_DATA_API_KEY, so when the dedicated V4 key
    is present we place that value into the process-local parser slot. If it is
    missing, we remove any shared key from this process so V4 cannot silently
    fall back to another bot/account.
    """
    target = os.environ if env is None else env
    key, source = select_v4_twelve_key(target)
    if key:
        target["TWELVE_DATA_API_KEY"] = key
    else:
        target.pop("TWELVE_DATA_API_KEY", None)
    return source
