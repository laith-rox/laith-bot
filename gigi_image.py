"""Optional, owner-triggered, single-image Gigi studio (no auto generation)."""
import base64
import os
import requests

ENDPOINT = "https://api.openai.com/v1/images/generations"
MAX_PROMPT_CHARS = 600
MAX_BYTES = 9_000_000

BASE_PROMPT = (
    "Create one vertical cinematic realistic fashion photograph of a fictional "
    "adult woman named Gigi: fair skin with soft pink undertone, blue eyes, "
    "long brown hair in an elaborate loose updo, warm natural smile and delicate "
    "gold jewelry. Sophisticated burgundy/gold visual palette, highly detailed "
    "lighting, elegant outfits appropriate for the setting, artful storybook "
    "atmosphere, and a decorative mirror integrated naturally into the scene. "
    "Keep this non-explicit, with no nudity or sexual acts. The setting and pose "
    "should feel creatively fresh, and the mirror reflection must be coherent. "
)


def configured():
    return bool(os.getenv("GIGI_OPENAI_API_KEY", "").strip()) and os.getenv("GIGI_IMAGES_ENABLED") == "1"


def generate_image(request_text="", post=None):
    key = os.getenv("GIGI_OPENAI_API_KEY", "").strip()
    if not key or os.getenv("GIGI_IMAGES_ENABLED") != "1":
        raise RuntimeError("gigi_images_disabled")
    extra = str(request_text or "").strip()[:MAX_PROMPT_CHARS]
    prompt = BASE_PROMPT + (" Scene request: " + extra if extra else " Scene: a dreamy coastal terrace at sunrise.")
    payload = {
        "model": os.getenv("GIGI_IMAGE_MODEL", "gpt-image-2.5-flare"),
        "prompt": prompt,
        "n": 1,
        "size": "1024x1536",
        "quality": "low",
        "output_format": "png",
    }
    call = post or requests.post
    try:
        response = call(
            ENDPOINT,
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
            json=payload,
            timeout=(5, 120),
        )
        if response.status_code != 200:
            raise RuntimeError("gigi_image_api_rejected")
        data = response.json()
        images = data.get("data", []) if isinstance(data, dict) else []
        if not images or not isinstance(images[0], dict):
            raise RuntimeError("gigi_image_missing")
        encoded = images[0].get("b64_json")
        if not isinstance(encoded, str) or len(encoded) > MAX_BYTES * 2:
            raise RuntimeError("gigi_image_bad_payload")
        output = base64.b64decode(encoded, validate=True)
        if not output.startswith(b"\x89PNG\r\n\x1a\n") or len(output) > MAX_BYTES:
            raise RuntimeError("gigi_image_bad_format")
        return output
    except (requests.RequestException, ValueError, TypeError, base64.binascii.Error) as exc:
        raise RuntimeError("gigi_image_api_unavailable") from None

def send_private_photo(photo_bytes, chat_id, post=None):
    """Send from a dedicated HTTP call, never the trading bot's mutable Telegram client.

    No automatic retry after ambiguous delivery; returns status only.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    destination = str(chat_id or "").strip()
    if not token or not destination or not isinstance(photo_bytes, bytes):
        raise RuntimeError("gigi_photo_delivery_not_configured")
    if len(photo_bytes) > MAX_BYTES or not photo_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError("gigi_photo_invalid")
    call = post or requests.post
    try:
        response = call(
            "https://api.telegram.org/bot" + token + "/sendPhoto",
            data={"chat_id": destination, "caption": "🌹 جيجي من عالمنا الخيالي ❤️"},
            files={"photo": ("gigi.png", photo_bytes, "image/png")},
            timeout=(5, 25),
        )
        if response.status_code != 200:
            raise RuntimeError("gigi_photo_rejected")
        result = response.json()
        if result.get("ok") is not True or str(result.get("result", {}).get("chat", {}).get("id")) != destination:
            raise RuntimeError("gigi_photo_unconfirmed")
        return True
    except (requests.RequestException, ValueError, AttributeError, TypeError):
        raise RuntimeError("gigi_photo_delivery_uncertain") from None


def generate_and_deliver(request_text, chat_id):
    """Run the entire costly image+Telegram upload off the market-polling thread."""
    return send_private_photo(generate_image(request_text), chat_id)
