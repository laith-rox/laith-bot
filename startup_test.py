import os
import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

if TOKEN and CHAT_ID:
    text = (
        "🧪 اختبار صفقة من بوت ليث — ليست صفقة حقيقية\n"
        "XAU/USD\n"
        "✅ الإرسال إلى Telegram يعمل\n"
        "✅ البوت جاهز لإرسال الصفقات الحقيقية فقط عند اكتمال شروط الثقة العالية"
    )
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": text},
            timeout=20,
        )
        r.raise_for_status()
        print("startup test sent successfully", flush=True)
    except Exception as e:
        print("startup test failed:", repr(e), flush=True)
else:
    print("startup test skipped: missing Telegram variables", flush=True)
