"""Run approved V4 manual-signal engine on the existing experimental Laith service.

Reuse only this service's existing Telegram and market credentials. Never place
orders. Preserve the old /data/laith.db for rollback.
"""
import os


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    key = os.getenv("TWELVE_DATA_API_KEY")
    if not token or not chat or not key:
        raise RuntimeError("experimental_laith_missing_credentials")
    os.environ["V4_TELEGRAM_BOT_TOKEN"] = token
    os.environ["V4_TELEGRAM_CHAT_ID"] = chat
    os.environ["V4_TWELVE_DATA_API_KEY"] = key
    os.environ["V4_DB_PATH"] = "/data/laith_v4_experiment.db"
    # No verified broker calendar is fabricated. V4 must fail closed until supplied.
    import v4_group_runtime
    import v4_runtime
    v4_runtime.run(v4_runtime.parser().parse_args())


if __name__ == "__main__":
    main()
