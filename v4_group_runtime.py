"""Laith V4 entrypoint with paired Telegram group mirroring."""
import v4_runtime
from v4_group_telegram import V4Telegram

v4_runtime.V4Telegram = V4Telegram


if __name__ == "__main__":
    v4_runtime.run(v4_runtime.parser().parse_args())
