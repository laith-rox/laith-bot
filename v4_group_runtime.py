"""Laith V4 entrypoint with paired Telegram group mirroring."""
import v4_runtime
from v4_group_telegram import V4Telegram
from v4_quick_balance import attach_condition_balance, quick_message as balanced_quick_message


_original_build_quick = v4_runtime.build_quick


def _build_quick_with_balance(decision, *args, **kwargs):
    setup = _original_build_quick(decision, *args, **kwargs)
    return attach_condition_balance(setup, decision)


v4_runtime.build_quick = _build_quick_with_balance
v4_runtime.quick_message = balanced_quick_message
v4_runtime.V4Telegram = V4Telegram


if __name__ == "__main__":
    v4_runtime.run(v4_runtime.parser().parse_args())
