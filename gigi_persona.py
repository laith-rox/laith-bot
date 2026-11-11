"""Private-owner fictional Gigi chat via the Responses API.

Opt-in only: no network call without GIGI_OPENAI_API_KEY. This module never
imports the market/trading engine and never receives brokerage credentials.
"""
import os
import requests

API_URL = "https://api.openai.com/v1/responses"
MAX_MESSAGE_CHARS = 1200
MAX_HISTORY_ITEMS = 10
SYSTEM = (
    "أنتِ جيجي، شخصية قصصية خيالية بالغة في عالم خاص مستقل عن بوتات التداول. "
    "احكي باللهجة الفلسطينية بعفوية ودفء ومشاكسات خفيفة، وابتكري أماكن وقصص "
    "وأزياء ومفاجآت من خيالك. حافظي على أسلوب حواري طبيعي، مش قوائم رسمية. "
    "كوني واضحة أن هذا تمثيل لشخصية خيالية تعمل بمساعدة نموذج ذكاء اصطناعي، "
    "مش نفس نسخة ChatGPT ولا عندك وصول تلقائي لمحادثاته السابقة. "
    "لا تدّعي رغبات أو تجارب حقيقية. "
    "لا تقدمي أسعار سوق لحظية أو توصيات تداول أو تتعاملي مع بيانات حساب. "
    "لا تفتحي أو تغلقي صفقات ولا تغيّري إعدادات البوت. "
    "التزمي بسياسات مزود النموذج ولا تحاولي التحايل عليها. "
    "تفاعلي بلطف وبأسلوب مختصر نسبيًا وبإيموجي قليل ومناسب."
)


def configured():
    return bool(os.getenv("GIGI_OPENAI_API_KEY", "").strip())


def model_name():
    return os.getenv("GIGI_MODEL", "gpt-6-luna").strip() or "gpt-6-luna"


def history_items(saved):
    """Read only a bounded conversational history, never bot or market state."""
    if not isinstance(saved, list):
        return []
    clean = []
    for item in saved[-MAX_HISTORY_ITEMS:]:
        if not isinstance(item, dict) or item.get("role") not in ("user", "assistant"):
            continue
        value = item.get("content")
        if isinstance(value, str) and value.strip():
            clean.append({"role": item["role"], "content": value[:MAX_MESSAGE_CHARS]})
    return clean


def extract_text(data):
    if not isinstance(data, dict):
        raise RuntimeError("gigi_unexpected_reply")
    pieces = []
    for entry in data.get("output", []):
        if not isinstance(entry, dict) or entry.get("type") != "message":
            continue
        for part in entry.get("content", []):
            if isinstance(part, dict) and part.get("type") == "output_text":
                value = part.get("text")
                if isinstance(value, str):
                    pieces.append(value)
    output = "\n".join(pieces).strip()
    if not output:
        raise RuntimeError("gigi_empty_reply")
    return output[:3400]


def _raise_api_rejection(response):
    """Classify provider rejection without recording the response body or API key."""
    status = int(getattr(response, "status_code", 0) or 0)
    code = ""
    try:
        payload = response.json()
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        if isinstance(error, dict):
            code = str(error.get("code") or error.get("type") or "").lower()[:80]
    except (ValueError, TypeError, AttributeError):
        pass
    if status == 401:
        category = "gigi_auth_invalid"
    elif status == 403:
        category = "gigi_permission_denied"
    elif status == 429 and ("quota" in code or "billing" in code or "credit" in code):
        category = "gigi_quota_exceeded"
    elif status == 429:
        category = "gigi_rate_limited"
    elif status in (400, 404) and ("model" in code or status == 404):
        category = "gigi_model_unavailable"
    elif status == 400:
        category = "gigi_bad_request"
    elif status >= 500:
        category = "gigi_provider_unavailable"
    else:
        category = "gigi_api_rejected"
    raise RuntimeError(category)


def generate(message, saved_history=(), post=None):
    """Perform only a bounded text chat request. Called by a separate worker."""
    key = os.getenv("GIGI_OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("gigi_api_not_configured")
    user_text = str(message or "").strip()[:MAX_MESSAGE_CHARS]
    if not user_text:
        raise RuntimeError("gigi_empty_message")
    prior = history_items(saved_history)
    payload = {
        "model": model_name(),
        "instructions": SYSTEM,
        "input": [*prior, {"role": "user", "content": user_text}],
        "max_output_tokens": 550,
        "store": False,
    }
    call = post or requests.post
    try:
        response = call(
            API_URL,
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
            json=payload,
            timeout=(5, 25),
        )
        if response.status_code != 200:
            _raise_api_rejection(response)
        return extract_text(response.json())
    except requests.Timeout:
        raise RuntimeError("gigi_network_timeout") from None
    except (requests.RequestException, ValueError, TypeError):
        raise RuntimeError("gigi_network_unavailable") from None
