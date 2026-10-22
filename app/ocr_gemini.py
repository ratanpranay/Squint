"""Gemini as a reader of the screen, for people who will not add a card.

Cloud Vision is the better reader and it is the one to use for anything
private. It has a problem that has nothing to do with quality: Google Cloud
demands a credit card before you may use *anything*, the free tier
included. The card is identity checking rather than payment, but from the
outside it is a stranger's app asking for card details, and people
reasonably say no. Four testers stopped there.

Gemini keys come from Google AI Studio, which is a different sign-up
altogether: a Google account, no card, about a minute. And Gemini reads
images as well as it writes text, so one key covers both halves of what
this app does.

Two things are worse and are not hidden from the user anywhere this module
is mentioned:

  - The free tier says content may be used to improve Google's products.
    For a public web page that is nothing; for a company's mail it is the
    whole argument for the paid key, and it is the honest reason to offer
    Cloud Vision rather than a nag about limits.
  - It is a language model, so the boxes it draws round lines are
    estimates. Vision measures them. Where the boxes come back implausible
    the overlay is not drawn over the page at all — a translation printed
    in the wrong place over the sentence it is translating is worse than a
    card beside it.

Free limits are per-day request counts rather than characters, and Google
has moved them before, so nothing here quotes a number. The app finds out
by being refused, and says so.
"""
import base64
import io
import json
import threading
import time

# A screenshot of a whole monitor is several megabytes as PNG, and base64
# makes it a third bigger again. Uploading that on an office connection is
# most of the time the user spends waiting, and the reading is no better
# for it: text stays legible far below native resolution, and the boxes
# come back normalised to 0-1000 so they land in the right place whatever
# the picture was scaled to.
# 1600, and it stayed 1600.
#
# It was briefly cut to 1100 as a speed measure, on the reasoning that
# screen text is rendered type and survives shrinking. That reasoning
# holds for a paragraph and breaks for a screen: somebody dragging across
# a whole 4K display is asking for 3840 pixels to become 1100, which turns
# 14px body text into 4px and reads nothing at all. The snip is not
# supposed to have a size limit, and a cap that silently degrades a large
# one is a size limit that does not announce itself.
#
# The speed problem was never the picture. It was seventy-five-second
# first attempts and a model listing fetched twice on a cold key, both
# fixed elsewhere. A big capture is simply a bigger job, and the time
# budget grows with it rather than the picture shrinking to fit.
MAX_EDGE = 1600

# The reply is asked for as JSON against this schema rather than as prose.
# Asking a model for "JSON only, no explanation" and parsing what arrives
# works until the day it apologises first, and the failure is a crash in a
# hotkey handler rather than a bad translation.
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "lines": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "text": {"type": "STRING"},
                    # Google's own convention for coordinates from a
                    # multimodal model: [ymin, xmin, ymax, xmax], each 0-1000
                    # of the image's height or width. Normalised, so it
                    # survives the model not knowing the pixel size.
                    "box_2d": {"type": "ARRAY",
                               "items": {"type": "INTEGER"}},
                },
                "required": ["text"],
            },
        },
    },
    "required": ["lines"],
}

PROMPT = """Read every piece of text in this image, exactly as it appears.

- One entry per visual line, in reading order.
- Copy the characters as they are. Do not translate, correct spelling,
  expand abbreviations, or tidy punctuation.
- Include numbers, prices, codes and web addresses.
- box_2d is [ymin, xmin, ymax, xmax] on a 0-1000 scale of the image.
- If the image contains no text, return an empty list."""

#: Added to the prompt when the user has named the source language. It
#: is the one piece of context that changes the answer on a CJK page:
#: asked to read a Chinese screenshot with no hint, a model will happily
#: return Korean and Japanese characters for shapes it is unsure of, and
#: nothing downstream can tell that it guessed.
LANGUAGE_NOTE = ("\n- The text in this image is in %s. Read it as %s; do "
                 "not substitute characters from another writing system.")

#: Language names for the codes the app uses, for that sentence. Only the
#: ones worth naming — a hint of "English" on an English page changes
#: nothing, and a wrong hint is worse than none.
PROMPT_LANGUAGE = {
    "zh": "Chinese (Simplified)", "zh-CN": "Chinese (Simplified)",
    "zh-TW": "Chinese (Traditional)", "zh-HK": "Chinese (Traditional)",
    "ja": "Japanese", "ko": "Korean", "ru": "Russian", "uk": "Ukrainian",
    "bg": "Bulgarian", "sr": "Serbian", "el": "Greek", "ar": "Arabic",
    "fa": "Persian", "ur": "Urdu", "he": "Hebrew", "hi": "Hindi",
    "mr": "Marathi", "bn": "Bengali", "ta": "Tamil", "te": "Telugu",
    "th": "Thai",
}


def prompt_for(source):
    """The reading prompt, with the language named when there is one."""
    code = str(source or "").strip()
    if not code or code.lower() in ("auto", "detect"):
        return PROMPT
    name = PROMPT_LANGUAGE.get(code) or PROMPT_LANGUAGE.get(
        code.split("-")[0])
    if not name:
        return PROMPT
    return PROMPT + (LANGUAGE_NOTE % (name, name))

_lock = threading.Lock()
last_error = ""

# When Google says the allowance is gone, believe it for a while.
#
# Without this every snip keeps asking, and each refusal costs a network
# round-trip before the machine's own reader takes over — so the app gets
# slower at exactly the moment it has stopped being able to use the thing
# making it slow. Rate limits are per minute as well as per day, so this is
# a rest rather than a write-off.
_rest_until = 0.0
REST_AFTER_LIMIT = 15 * 60


def resting():
    """Seconds until it is worth asking again, or 0."""
    return max(0, int(_rest_until - time.time()))


def note_limit(seconds=REST_AFTER_LIMIT):
    global _rest_until
    _rest_until = time.time() + seconds

# One snip asks twice: the overlay wants positioned lines and, if it cannot
# draw them, the card wants the plain text. Same picture, same answer, two
# requests against a daily allowance. So the last reply is kept briefly,
# keyed by the image itself.
_cache = {"key": None, "at": 0.0, "reply": None}
_CACHE_SECONDS = 20.0


def api_key():
    from . import config
    return str(config.CONFIG.get("gemini_api_key", "") or "").strip()


def available():
    """Only ever true with a key, and only when not switched off.

    Without a key there is nothing to fall back to, and asking Google
    anyway spends a round-trip to be told so.
    """
    from . import config
    if not api_key():
        return False
    if resting():
        return False
    return bool(config.CONFIG.get("use_gemini_ocr", True))


def _friendly_error(message):
    """Google's words, plus what to do about them.

    The three that matter are the three a new key hits: the daily allowance
    is gone, the key is not valid, and the API was never switched on. Each
    has a different fix and they all arrive as a bare status code.
    """
    text = str(message or "")
    low = text.lower()
    if "timed out" in low or "timeout" in low:
        return ("Gemini did not answer in time. It may just be slow right "
                "now — but if this happens every time, this network is "
                "probably blocking generativelanguage.googleapis.com. That "
                "is a different address from the Cloud APIs, so Google "
                "Translate and Cloud Vision can work while this does not. "
                "Worth testing on a phone hotspot.")
    if ("503" in low or "high demand" in low or "overloaded" in low
            or "busy at the moment" in low or "unavailable" in low):
        # Google's own capacity, not the key and not the user. Said as a
        # failure it makes a working setup look broken, which is what a
        # tester reported: a valid key shown in red on the day it was made.
        return ("Gemini is busy at the moment — Google's side, not your "
                "key. Squint used this computer's own reader instead. It "
                "is usually over in a minute.")
    if "429" in low or "quota" in low or "rate limit" in low \
            or "resource_exhausted" in low:
        return ("Gemini's free allowance for today is used up. It resets "
                "tomorrow. Squint will keep reading with this computer's "
                "own recogniser until then. (Google said: %s)" % text[:120])
    if "api key not valid" in low or "api_key_invalid" in low:
        return ("That Gemini key was not accepted. Make a new one at "
                "aistudio.google.com/apikey — it takes a minute and needs "
                "no card.")
    if "has not been used" in low or "is disabled" in low \
            or "not enabled" in low:
        return ("The Generative Language API is not switched on for this "
                "key's project. A key made at aistudio.google.com/apikey "
                "has it on already. (Google said: %s)" % text[:120])
    if "permission" in low or "403" in low:
        return "Google refused the Gemini key for reading images: %s" % text
    return "Gemini could not read the image: %s" % text


def _shrink(image):
    """Down to MAX_EDGE on the long side, if it is bigger."""
    width, height = image.size
    longest = max(width, height)
    if longest <= MAX_EDGE:
        return image
    scale = MAX_EDGE / float(longest)
    try:
        from PIL import Image as _Image
        resample = _Image.LANCZOS
    except Exception:                       # pragma: no cover
        resample = None
    size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(size, resample) if resample else image.resize(size)


def _ask(image, attempts=None, source=None):
    """One request, or the cached reply for the same picture."""
    import hashlib
    from . import translator

    key = api_key()
    if not key:
        raise RuntimeError("no Gemini key saved")

    buffer = io.BytesIO()
    shrunk = _shrink(image).convert("RGB")
    shrunk.save(buffer, format="PNG")
    raw_png = buffer.getvalue()
    prompt = prompt_for(source)
    # The language is part of what was asked, so it is part of what the
    # cache is keyed on: the same picture read as Chinese and read with
    # no hint are two different questions.
    stamp = hashlib.sha1(raw_png).hexdigest() + "|" + hashlib.sha1(
        prompt.encode("utf-8")).hexdigest()
    with _lock:
        if (_cache["key"] == stamp
                and time.time() - _cache["at"] < _CACHE_SECONDS
                and _cache["reply"] is not None):
            return _cache["reply"]

    body = json.dumps({
        "contents": [{"parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": "image/png",
                             "data": base64.b64encode(raw_png)
                             .decode("ascii")}},
        ]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": SCHEMA,
        },
    })

    # Reuses the translator's model walk on purpose. It already knows how to
    # step past model names that are listed but refuse to run, and it
    # remembers the one that answered — solved once, in one place, rather
    # than twice with only one of them maintained.
    try:
        # No fixed timeout: the walk gives the first attempt a short one
        # and the retry the long one. Pinning the ceiling here made every
        # first try wait seventy-five seconds before giving up, which on a
        # fresh machine is the whole difference between "slow" and
        # "broken".
        raw = translator._gemini_generate(
            key, body, attempts=attempts, image=True,
            pixels=shrunk.width * shrunk.height)
    except Exception as exc:
        message = _friendly_error(exc)
        if "allowance" in message:
            note_limit()
        raise RuntimeError(message)

    payload = json.loads(raw)
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError(_friendly_error(str(payload)[:120]))
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts).strip()
    try:
        reply = json.loads(text)
    except Exception:
        raise RuntimeError("Gemini's reply was not readable.")
    if not isinstance(reply, dict):
        raise RuntimeError("Gemini's reply was not readable.")

    with _lock:
        _cache.update({"key": stamp, "at": time.time(), "reply": reply})
    return reply


def _entries(reply):
    out = []
    for entry in (reply.get("lines") or []):
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text", "")).strip()
        if text:
            out.append((text, entry.get("box_2d")))
    return out


def _box(box_2d, width, height):
    """[ymin, xmin, ymax, xmax] out of 1000 -> (left, top, w, h) in pixels.

    Returns None for anything that does not describe a rectangle on the
    picture. A model asked for coordinates will occasionally give three
    numbers, or a zero-height box, or one that starts past the right-hand
    edge; drawing from those puts a translation somewhere it does not
    belong, which is worse than not drawing it.
    """
    try:
        ymin, xmin, ymax, xmax = (float(v) for v in box_2d)
    except Exception:
        return None
    if not (0 <= xmin < xmax <= 1000 and 0 <= ymin < ymax <= 1000):
        return None
    left = int(xmin / 1000.0 * width)
    top = int(ymin / 1000.0 * height)
    right = int(xmax / 1000.0 * width)
    bottom = int(ymax / 1000.0 * height)
    if right - left < 2 or bottom - top < 2:
        return None
    return (left, top, right - left, bottom - top)


def image_to_lines(image, languages=None, source=None):
    """Positioned lines, or nothing at all.

    Nothing at all when the boxes cannot be trusted — the caller then falls
    back to the card, which is the right outcome. Half the lines placed and
    half missing would look like the app losing text.
    """
    del languages
    global last_error
    last_error = ""
    try:
        reply = _ask(image, source=source)
    except Exception as exc:
        last_error = str(exc)
        raise
    entries = _entries(reply)
    if not entries:
        return [], "Gemini"

    width, height = image.size
    lines, placed = [], 0
    for text, box_2d in entries:
        box = _box(box_2d, width, height)
        if box is None:
            continue
        placed += 1
        # Angle 0: a language model reports a rectangle, not a quadrilateral,
        # so there is no tilt to read. The watermark test degrades to its
        # other two signals rather than being told everything is upright.
        lines.append({"text": text, "angle": 0.0, "box": box})

    if placed < len(entries) * 0.6:
        last_error = ("Gemini read the text but could not place it on the "
                      "picture accurately enough to draw over it.")
        return [], "Gemini"
    return lines, "Gemini"


def image_to_text(image, languages=None, source=None):
    del languages
    global last_error
    last_error = ""
    try:
        reply = _ask(image, source=source)
    except Exception as exc:
        last_error = str(exc)
        raise
    return "\n".join(text for text, _box in _entries(reply)), "Gemini"


def check_key():
    """Prove the key can read a picture, for Save & test.

    A key that translates does not necessarily read: the two go through the
    same API but the app walks a model list, and a text-only model answers
    one and refuses the other. Worth one small request to find out here
    rather than mid-snip.
    """
    from PIL import Image, ImageDraw
    if not api_key():
        return False, "no Gemini key saved"
    image = Image.new("RGB", (240, 80), "white")
    ImageDraw.Draw(image).text((12, 30), "SQUINT OK", fill="black")
    try:
        # One attempt. Retrying to answer "does this key work" is how a
        # daily allowance is spent on testing rather than translating.
        reply = _ask(image, attempts=1)
        text = "\n".join(t for t, _b in _entries(reply))
    except Exception as exc:
        return False, str(exc)
    if not text.strip():
        return False, "Gemini answered but read no text from a test image"
    return True, "Gemini can read images"
