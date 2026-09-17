"""V4-specific market key selection without exposing secret values."""
import os


def select_v4_twelve_key(env=None):
    """Prefer the dedicated V4 key, with the shared key only as fallback."""
    env = os.environ if env is None else env
    v4_key = env.get("V4_TWELVE_DATA_API_KEY")
    if v4_key:
        return v4_key, "V4_TWELVE_DATA_API_KEY"
    shared_key = env.get("TWELVE_DATA_API_KEY")
    if shared_key:
        return shared_key, "TWELVE_DATA_API_KEY"
    return None, "missing"


def apply_v4_twelve_key_precedence(env=None):
    """Put the selected V4 key where the existing parser expects it.

    This changes only this worker process environment. It does not mutate Railway
    variables and never logs or returns a secret unless the caller explicitly asks
    select_v4_twelve_key for the value.
    """
    target = os.environ if env is None else env
    key, source = select_v4_twelve_key(target)
    if key:
        target["TWELVE_DATA_API_KEY"] = key
    return source
