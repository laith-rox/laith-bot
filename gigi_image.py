"""Owner-triggered image studio for Gigi and Laith (never trading or automatic).

Owner-approved Telegram reference file IDs are kept in the bot's private state.
Image bytes are fetched only during requested generation, forwarded to the image
editing API transiently, and never persisted in GitHub, SQLite, or bot logs.
"""
import base64
import os
import re
import requests

GENERATE_ENDPOINT = "https://api.openai.com/v1/images/generations"
EDIT_ENDPOINT = "https://api.openai.com/v1/images/edits"
MAX_PROMPT_CHARS = 600
MAX_BYTES = 9_000_000
MAX_REFERENCE_BYTES = 8_000_000

GIGI_LOOK = (
    "Gigi is a fictional adult woman with a gentle youthful-looking but clearly "
    "adult face, fair skin with a soft rosy undertone, expressive blue eyes, "
    "long brown hair styled in a voluminous updo with soft loose strands, "
    "delicate features, a natural warm smile, feminine balanced curvy "
    "adult proportions, and understated gold accessories. Maintain the same "
    "general appearance across images. Show her full outfit and flattering "
    "realistic body proportions with anatomically correct posture."
)
LAITH_LOOK = (
    "Laith is an adult man with a light olive skin tone, short dark styled hair, "
    "a neatly full dark beard and moustache, brown eyes, and a slender masculine face. "
    "He prefers classic Italian-inspired clothing, white shirt and black trousers, "
    "optional black luxury sunglasses, a wristwatch on his left wrist, and no rings."
)
STYLE = (
    "Create one polished, photorealistic, high-quality vertical fashion portrait "
    "in a believable elegant location. Warm tasteful lighting, cinematic lens, "
    "coherent details, natural hands and faces. The couple may be affectionate "
    "and romantic with tasteful close poses, but no nudity or explicit sexuality. "
    "Gigi favors beautiful, feminine, figure-flattering sophisticated outfits, "
    "sometimes striking burgundy or black, with a stylish confident pose. "
    "Vary location, clothing, framing and poses with each request; no mirror is "
    "required. Respect the adult appearance and identity of reference people. "
)


def configured():
    return bool(os.getenv("GIGI_OPENAI_API_KEY", "").strip()) and os.getenv("GIGI_IMAGES_ENABLED") == "1"


def model_name():
    return os.getenv("GIGI_IMAGE_MODEL", "gpt-image-2.5-flare").strip() or "gpt-image-2.5-flare"


def quality_name():
    value = os.getenv("GIGI_IMAGE_QUALITY", "medium").lower().strip()
    return value if value in ("low", "medium", "high") else "medium"


def build_prompt(request_text="", couple=False, has_me=False, has_gigi=False):
    extra = str(request_text or "").strip()[:MAX_PROMPT_CHARS]
    prompt = STYLE + GIGI_LOOK
    if couple:
        prompt += " " + LAITH_LOOK + " Show Laith and Gigi together as two adults in one coherent scene."
    else:
        prompt += " Only Gigi is the main subject."
    if has_me:
        prompt += " Input reference 1 shows the real adult Laith. Preserve his facial identity faithfully; do not replace him with a generic model."
    if has_gigi:
        prompt += (" Input reference " + ("2" if has_me else "1") +
                   " shows the established fictional Gigi. Match her face and general silhouette to this reference while changing the scene and clothing.")
    if extra:
        prompt += " User's requested scene: " + extra
    else:
        prompt += " Scene: a classy outdoor terrace with warm evening light."
    return prompt


def _image_from_response(response):
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


def _reject_image_response(response):
    code = ""
    try:
        data = response.json()
        err = data.get("error", {}) if isinstance(data, dict) else {}
        if isinstance(err, dict):
            code = str(err.get("code") or err.get("type") or "").lower()[:80]
    except (ValueError, TypeError, AttributeError):
        pass
    status = response.status_code
    if status == 401:
        category = "gigi_image_invalid_key"
    elif status == 403:
        category = "gigi_image_permission_denied"
    elif status == 429 and ("quota" in code or "billing" in code or "credit" in code):
        category = "gigi_image_no_credits"
    elif status == 429:
        category = "gigi_image_rate_limited"
    elif status in (400, 404):
        category = "gigi_image_invalid_request"
    else:
        category = "gigi_image_provider_error"
    raise RuntimeError(category)


def generate_image(request_text="", post=None, *, couple=False, references=()):
    """Generate a single PNG; optional refs are (role, image bytes, MIME type)."""
    key = os.getenv("GIGI_OPENAI_API_KEY", "").strip()
    if not key or os.getenv("GIGI_IMAGES_ENABLED") != "1":
        raise RuntimeError("gigi_images_disabled")
    refs = list(references or ())[:2]
    roles = [r[0] for r in refs]
    if len(set(roles)) != len(roles) or any(role not in ("me", "gigi") for role in roles):
        raise RuntimeError("gigi_image_invalid_reference")
    prompt = build_prompt(request_text, couple, "me" in roles, "gigi" in roles)
    common = {
        "model": model_name(),
        "prompt": prompt,
        "n": 1,
        "size": "1024x1536",
        "quality": quality_name(),
        "output_format": "png",
    }
    call = post or requests.post
    try:
        if refs:
            upload = []
            for index, (_, raw, mime) in enumerate(refs, 1):
                if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_REFERENCE_BYTES:
                    raise RuntimeError("gigi_image_invalid_reference")
                if mime not in ("image/jpeg", "image/png", "image/webp"):
                    raise RuntimeError("gigi_image_invalid_reference")
                suffix = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[mime]
                upload.append(("image[]", ("reference_" + str(index) + "." + suffix, raw, mime)))
            response = call(
                EDIT_ENDPOINT,
                headers={"Authorization": "Bearer " + key},
                data=common,
                files=upload,
                timeout=(5, 180),
            )
        else:
            response = call(
                GENERATE_ENDPOINT,
                headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                json=common,
                timeout=(5, 180),
            )
        if response.status_code != 200:
            _reject_image_response(response)
        return _image_from_response(response)
    except requests.Timeout:
        raise RuntimeError("gigi_image_timeout") from None
    except (requests.RequestException, ValueError, TypeError, base64.binascii.Error):
        raise RuntimeError("gigi_image_network_error") from None


def fetch_private_reference(file_id, *, get=None, post=None):
    """Download one Telegram reference in the image worker only, never store bytes."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or not isinstance(file_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,300}", file_id):
        raise RuntimeError("gigi_reference_invalid")
    call = post or requests.post
    reader = get or requests.get
    try:
        response = call(
            "https://api.telegram.org/bot" + token + "/getFile",
            data={"file_id": file_id},
            timeout=(5, 15),
        )
        data = response.json() if response.status_code == 200 else {}
        info = data.get("result", {}) if isinstance(data, dict) else {}
        path = info.get("file_path")
        size = info.get("file_size", 0)
        if (data.get("ok") is not True or not isinstance(path, str)
                or not path.startswith("photos/") or ".." in path
                or not isinstance(size, int) or size > MAX_REFERENCE_BYTES):
            raise RuntimeError("gigi_reference_unavailable")
        downloaded = reader(
            "https://api.telegram.org/file/bot" + token + "/" + path,
            timeout=(5, 20),
        )
        if downloaded.status_code != 200:
            raise RuntimeError("gigi_reference_unavailable")
        raw = downloaded.content
        if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_REFERENCE_BYTES:
            raise RuntimeError("gigi_reference_unavailable")
        if raw.startswith(b"\xff\xd8\xff"):
            mime = "image/jpeg"
        elif raw.startswith(b"\x89PNG\r\n\x1a\n"):
            mime = "image/png"
        elif raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
            mime = "image/webp"
        else:
            raise RuntimeError("gigi_reference_unavailable")
        return raw, mime
    except requests.RequestException:
        raise RuntimeError("gigi_reference_unavailable") from None


def send_private_photo(photo_bytes, chat_id, post=None, couple=False):
    """Independent Telegram call off the trading poller; no automatic retry."""
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
            data={
                "chat_id": destination,
                "caption": "❤️ ليث وجيجي من عالمنا الخاص" if couple else "🌹 جيجي من عالمنا الخيالي ❤️",
            },
            files={"photo": ("gigi.png", photo_bytes, "image/png")},
            timeout=(5, 60),
        )
        if response.status_code != 200:
            raise RuntimeError("gigi_photo_rejected")
        result = response.json()
        if result.get("ok") is not True or str(result.get("result", {}).get("chat", {}).get("id")) != destination:
            raise RuntimeError("gigi_photo_unconfirmed")
        return True
    except (requests.RequestException, ValueError, AttributeError, TypeError):
        raise RuntimeError("gigi_photo_delivery_uncertain") from None


def generate_and_deliver(request_text, chat_id, couple=False, reference_file_ids=None):
    """Fetch owner refs, generate one image, and upload away from market polling."""
    refs = []
    ids = reference_file_ids if isinstance(reference_file_ids, dict) else {}
    for kind in ("me", "gigi"):
        if kind == "me" and not couple:
            continue
        file_id = ids.get(kind)
        if isinstance(file_id, str) and file_id:
            raw, mime = fetch_private_reference(file_id)
            refs.append((kind, raw, mime))
    return send_private_photo(
        generate_image(request_text, couple=couple, references=refs),
        chat_id,
        couple=couple,
    )
