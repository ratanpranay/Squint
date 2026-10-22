"""Google Cloud Vision as a reader of last resort.

Windows recognises exactly the languages it has packs for. On an
English-language PC that is English, and pointed at Chinese it does not
fail — it returns confident nonsense, which the app then translated and
drew over the page. Adding the pack fixes that machine; it does not fix
anybody else's, and it is not always the user's to install.

Cloud Vision reads Chinese, Japanese, Korean, Cyrillic and Arabic properly,
needs nothing installed, and behaves identically on both platforms. It uses
the same Google Cloud project and the same API key as the translation
already does. The first 1,000 images a month are free; after that it is
$1.50 per 1,000, so the count is tracked and shown in Settings for the same
reason the character count is — the first sign of overrunning an allowance
should not be a bill.

It is deliberately a fallback, not the default: it costs a network
round-trip and an allowance, and when the machine can read the language
itself there is no reason to send the screen anywhere.
"""
import base64
import io
import json
import threading
import urllib.error
import urllib.parse
import urllib.request

from . import http_pool

ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"
TIMEOUT = 20
FREE_IMAGES = 1000

# Cloud Vision wants BCP-47 hints. Same idea as the Windows table, but it
# takes hints rather than a single language, and detects among them.
HINTS = {
    # Simplified Chinese without Traditional beside it. They are hints,
    # and a hint the page is not written in is a character the detector
    # can reach for: this table is read on a page whose language the
    # user has already named, so the point is to narrow it, not to hedge.
    "zh": ["zh-Hans", "en"], "zh-CN": ["zh-Hans", "en"],
    "zh-TW": ["zh-Hant", "en"], "zh-HK": ["zh-Hant", "en"],
    "ja": ["ja", "en"], "ko": ["ko", "en"], "ru": ["ru", "en"],
    "uk": ["uk", "en"], "ar": ["ar", "en"], "th": ["th", "en"],
    "hi": ["hi", "en"], "el": ["el", "en"], "he": ["iw", "en"],
    "bg": ["bg", "en"], "sr": ["sr", "en"], "fa": ["fa", "en"],
    "ur": ["ur", "en"], "mr": ["mr", "en"], "bn": ["bn", "en"],
    "ta": ["ta", "en"], "te": ["te", "en"], "ne": ["ne", "en"],
    # The Latin ones matter less — the alphabet is not in doubt — but a
    # hint still settles which of two spellings a diacritic belongs to,
    # and leaving them out meant choosing German sent nothing at all.
    "de": ["de", "en"], "fr": ["fr", "en"], "es": ["es", "en"],
    "it": ["it", "en"], "pt": ["pt", "en"], "nl": ["nl", "en"],
    "pl": ["pl", "en"], "tr": ["tr", "en"], "sv": ["sv", "en"],
    "da": ["da", "en"], "no": ["no", "en"], "fi": ["fi", "en"],
    "cs": ["cs", "en"], "ro": ["ro", "en"], "hu": ["hu", "en"],
    "vi": ["vi", "en"], "id": ["id", "en"], "en": ["en"],
}

_usage_lock = threading.Lock()
last_error = ""


def api_key():
    from . import config
    return str(config.CONFIG.get("google_api_key", "") or "").strip()


def available():
    """Only ever true with a key. There is nothing to fall back to without
    one, and asking Google without credentials just wastes eight seconds."""
    from . import config
    if not api_key():
        return False
    return bool(config.CONFIG.get("use_cloud_vision", True))


def _this_month():
    import time
    return time.strftime("%Y-%m")


def usage():
    """(images read this calendar month, the free allowance)."""
    from . import config
    with _usage_lock:
        record = config.CONFIG.get("vision_usage", {}) or {}
        if not isinstance(record, dict) or record.get("month") != _this_month():
            return 0, FREE_IMAGES
        try:
            return int(record.get("images", 0)), FREE_IMAGES
        except Exception:
            return 0, FREE_IMAGES


def note_usage(count=1):
    from . import config
    month = _this_month()
    with _usage_lock:
        record = config.CONFIG.get("vision_usage", {}) or {}
        if not isinstance(record, dict) or record.get("month") != month:
            record = {"month": month, "images": 0}
        try:
            record["images"] = int(record.get("images", 0)) + int(count)
        except Exception:
            record = {"month": month, "images": int(count)}
        try:
            config.CONFIG.set("vision_usage", record)
        except Exception:
            pass


def _friendly_error(status, body):
    """Google's own words, plus what to do about them.

    The two failures worth naming are the ones a new project hits: the API
    is not switched on, and the key is restricted to Translation only. Both
    come back as a bare 403, which on its own sends people looking at their
    key when the fix is two clicks elsewhere.
    """
    message = ""
    try:
        message = json.loads(body)["error"]["message"]
    except Exception:
        message = (body or "").strip()[:200]
    low = message.lower()
    if "has not been used" in low or "is disabled" in low \
            or "not enabled" in low:
        return ("Cloud Vision is not switched on for this project yet. "
                "Open console.cloud.google.com/apis/library/vision."
                "googleapis.com and press Enable, then try again. "
                "(Google said: %s)" % message[:120])
    if status == 403 and "restrict" in low:
        return ("This API key is restricted to the Translation API. Add "
                "“Cloud Vision API” to its allowed APIs at "
                "console.cloud.google.com/apis/credentials. "
                "(Google said: %s)" % message[:120])
    if status == 403:
        return ("Google refused the key for Cloud Vision: %s" % message)
    return "Cloud Vision failed (HTTP %s): %s" % (status, message)


# One snip can ask twice: the overlay wants positioned lines, and if it
# cannot draw them it falls back to the card, which wants the plain text.
# That is one screenshot but would be two billable units, halving the free
# allowance for no benefit — the answer is identical. So the last response
# is kept for a few seconds, keyed by the actual image.
_cache = {"key": None, "at": 0.0, "response": None}
_CACHE_SECONDS = 20.0


def _annotate(image, hints):
    import hashlib
    import time

    payload = io.BytesIO()
    image.convert("RGB").save(payload, format="PNG")
    key = (hashlib.sha1(payload.getvalue()).hexdigest(), tuple(hints or ()))
    with _usage_lock:
        if (_cache["key"] == key
                and time.time() - _cache["at"] < _CACHE_SECONDS
                and _cache["response"] is not None):
            return _cache["response"]

    body = {
        "requests": [{
            "image": {"content": base64.b64encode(
                payload.getvalue()).decode("ascii")},
            # DOCUMENT_TEXT_DETECTION, not TEXT_DETECTION: it is the one
            # built for dense blocks of text, which is what a page of email
            # or a car site is. Same price.
            "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
        }]
    }
    if hints:
        body["requests"][0]["imageContext"] = {"languageHints": list(hints)}

    data = json.dumps(body).encode("utf-8")
    url = ENDPOINT + "?key=" + urllib.parse.quote(api_key())
    try:
        # Kept open between calls — see `http_pool`. This one is on the
        # path of every snip for anyone using Cloud Vision to read the
        # screen, so it pays the connection cost twice a capture: once
        # here and once translating what was read.
        raw = http_pool.fetch(
            url, data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=TIMEOUT).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")
        except Exception:
            pass
        try:
            from . import google_billing
            google_billing.note_refusal(detail)
        except Exception:
            pass
        raise RuntimeError(_friendly_error(exc.code, detail))
    except urllib.error.URLError as exc:
        raise RuntimeError("Could not reach Cloud Vision: %s"
                           % getattr(exc, "reason", exc))

    parsed = json.loads(raw)
    first = (parsed.get("responses") or [{}])[0]
    if "error" in first:
        raise RuntimeError(_friendly_error(400, json.dumps(first)))
    note_usage(1)
    with _usage_lock:
        _cache.update({"key": key, "at": time.time(), "response": first})
    return first


def _box(vertices):
    xs = [int(v.get("x", 0)) for v in vertices or []]
    ys = [int(v.get("y", 0)) for v in vertices or []]
    if not xs or not ys:
        return None
    return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def _angle(vertices):
    """How far off horizontal this word sits, in degrees.

    Vision returns a real quadrilateral, not an upright rectangle, so the
    tilt of a word is there to be read — and a diagonal watermark is the
    one thing on a page that is reliably tilted. Windows OCR gives upright
    boxes only, which is part of why the watermark went undetected there.
    """
    try:
        import math
        (x0, y0), (x1, y1) = ((int(vertices[0].get("x", 0)),
                               int(vertices[0].get("y", 0))),
                              (int(vertices[1].get("x", 0)),
                               int(vertices[1].get("y", 0))))
    except Exception:
        return 0.0
    if x1 == x0 and y1 == y0:
        return 0.0
    return math.degrees(math.atan2(y1 - y0, x1 - x0))


def _word_text(word):
    out = []
    for symbol in word.get("symbols", []):
        out.append(symbol.get("text", ""))
        brk = (symbol.get("property", {})
               .get("detectedBreak", {}) or {}).get("type", "")
        if brk in ("SPACE", "EOL_SURE_SPACE"):
            out.append(" ")
    return "".join(out)


def _ends_line(word):
    for symbol in reversed(word.get("symbols", [])):
        brk = (symbol.get("property", {})
               .get("detectedBreak", {}) or {}).get("type", "")
        return brk in ("EOL_SURE_SPACE", "LINE_BREAK", "HYPHEN")
    return False


def lines_from(response):
    """Vision's nested blocks, flattened into the app's line shape.

    The response is pages → blocks → paragraphs → words → symbols, with the
    line endings marked on the symbols rather than given as lines. The
    overlay needs one box per visual line, so they are rebuilt here.
    """
    lines = []
    annotation = response.get("fullTextAnnotation") or {}
    for page in annotation.get("pages", []):
        for block in page.get("blocks", []):
            for paragraph in block.get("paragraphs", []):
                words, boxes, angles = [], [], []
                for word in paragraph.get("words", []):
                    words.append(_word_text(word))
                    vertices = (word.get("boundingBox") or {}).get("vertices")
                    box = _box(vertices)
                    if box:
                        boxes.append(box)
                        angles.append(_angle(vertices))
                    if _ends_line(word):
                        line = _flush(words, boxes, angles)
                        if line:
                            lines.append(line)
                        words, boxes, angles = [], [], []
                line = _flush(words, boxes, angles)
                if line:
                    lines.append(line)
    return lines


def _flush(words, boxes, angles=()):
    text = "".join(words).strip()
    if not text or not boxes:
        return None
    left = min(b[0] for b in boxes)
    top = min(b[1] for b in boxes)
    right = max(b[0] + b[2] for b in boxes)
    bottom = max(b[1] + b[3] for b in boxes)
    angle = 0.0
    if angles:
        ordered = sorted(angles)
        angle = ordered[len(ordered) // 2]        # median, not mean
    return {"text": text, "angle": angle,
            "box": (left, top, right - left, bottom - top)}


def hints_for(source):
    if not source or source == "auto":
        return []
    return HINTS.get(source) or HINTS.get(str(source).split("-")[0]) or []


def image_to_lines(image, languages=None, source=None):
    del languages
    global last_error
    last_error = ""
    try:
        response = _annotate(image, hints_for(source))
    except Exception as exc:
        last_error = str(exc)
        raise
    return lines_from(response), "Google Cloud Vision"


def image_to_text(image, languages=None, source=None):
    del languages
    global last_error
    last_error = ""
    try:
        response = _annotate(image, hints_for(source))
    except Exception as exc:
        last_error = str(exc)
        raise
    text = ((response.get("fullTextAnnotation") or {}).get("text") or "")
    return text.strip(), "Google Cloud Vision"


def check_key():
    """Prove the key works for Vision, so Settings can say so plainly.

    A 1x1 image is a real billable unit, so this is only ever run when the
    user presses Save & test.
    """
    from PIL import Image
    if not api_key():
        return False, "no Google key saved"
    try:
        _annotate(Image.new("RGB", (32, 32), "white"), [])
    except Exception as exc:
        return False, str(exc)
    return True, "Cloud Vision ok"
