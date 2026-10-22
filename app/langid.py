"""Is this text already in the language it is being translated into?

Translating a German page into German is not a no-op for a translation
model: it rewrites. "Herbst hat Schwarz-Rot viel vor" came back as "Herbst
hat viel zu tun", "Was wird aus den Eigenanteilen?" as "Was wird mit den
eigenen Anteilen passieren?" - the meaning changed and the page was painted
over with it, at the full cost of a translation. The same happens to the
English parts of a page for someone reading in English, and to the German
parts of a mixed page for someone reading in German.

So text already in the target language is left as it is. The answer is
True (it is), False (it is not) or None (cannot tell - short Latin labels,
languages that share a script); the caller decides what None means.
"""
import re
import threading

_RANGES = {
    "han": ((0x4E00, 0x9FFF), (0x3400, 0x4DBF), (0xF900, 0xFAFF)),
    "kana": ((0x3040, 0x30FF), (0x31F0, 0x31FF), (0xFF66, 0xFF9F)),
    "hangul": ((0xAC00, 0xD7AF), (0x1100, 0x11FF), (0x3130, 0x318F)),
    "cyrillic": ((0x0400, 0x04FF),),
    "greek": ((0x0370, 0x03FF),),
    "arabic": ((0x0600, 0x06FF), (0x0750, 0x077F)),
    "hebrew": ((0x0590, 0x05FF),),
    "devanagari": ((0x0900, 0x097F),),
    "bengali": ((0x0980, 0x09FF),),
    "gurmukhi": ((0x0A00, 0x0A7F),),
    "gujarati": ((0x0A80, 0x0AFF),),
    "tamil": ((0x0B80, 0x0BFF),),
    "telugu": ((0x0C00, 0x0C7F),),
    "kannada": ((0x0C80, 0x0CFF),),
    "malayalam": ((0x0D00, 0x0D7F),),
    "thai": ((0x0E00, 0x0E7F),),
}

# The script each target is written in. Anything not here is Latin.
_SCRIPT_OF = {
    "zh": "han", "ja": "kana", "ko": "hangul",
    "ru": "cyrillic", "uk": "cyrillic", "bg": "cyrillic", "sr": "cyrillic",
    "el": "greek", "ar": "arabic", "fa": "arabic", "ur": "arabic",
    "he": "hebrew", "hi": "devanagari", "mr": "devanagari",
    "ne": "devanagari", "bn": "bengali", "pa": "gurmukhi",
    "gu": "gujarati", "ta": "tamil", "te": "telugu", "kn": "kannada",
    "ml": "malayalam", "th": "thai",
}

# Letters one language of a shared script has and the others do not.
_UKRAINIAN = set(u"іїєґІЇЄҐ")
_RUSSIAN = set(u"ыэъёЫЭЪЁ")
_PERSIAN_URDU = set(u"پچژگکیٹڈڑںے")

# Latin languages are told apart by a detector, and only on text long
# enough for it to be right: a label of a word or two is None.
MIN_WORDS = 4
MIN_PROB = 0.9
_lock = threading.Lock()


def _base(target):
    return str(target or "").split("-")[0].lower()


def _script_of_char(ch):
    code = ord(ch)
    for name, ranges in _RANGES.items():
        for low, high in ranges:
            if low <= code <= high:
                return name
    if ch.isalpha():
        return "latin" if code < 0x0250 or 0x1E00 <= code <= 0x1EFF \
            else "other"
    return None


def scripts(text):
    """{script: letters} for the letters in `text`."""
    counts = {}
    for ch in str(text or ""):
        name = _script_of_char(ch)
        if name:
            counts[name] = counts.get(name, 0) + 1
    return counts


def _latin_language(text):
    """The detector's language for longer Latin text, or None."""
    if len(re.findall(r"\w+", text)) < MIN_WORDS:
        return None
    try:
        from langdetect import DetectorFactory, detect_langs
        with _lock:
            DetectorFactory.seed = 0
            found = detect_langs(text)
    except Exception:
        return None
    if not found or found[0].prob < MIN_PROB:
        return None
    return _base(found[0].lang)


def in_language(text, target):
    """True when `text` is already in `target`, False when it is not,
    None when that cannot be told."""
    counts = scripts(text)
    letters = sum(counts.values())
    if not letters:
        return None
    base = _base(target)
    want = _SCRIPT_OF.get(base, "latin")
    if want == "kana":
        # Japanese is kana with kanji; kanji alone may be Chinese.
        own = counts.get("kana", 0) + counts.get("han", 0)
        if own < 0.8 * letters:
            return False
        return True if counts.get("kana", 0) else None
    if want == "han":
        if counts.get("kana") or counts.get("hangul"):
            return False
        return counts.get("han", 0) >= 0.8 * letters
    own = counts.get(want, 0)
    if own < 0.8 * letters:
        return False
    if want == "cyrillic":
        chars = set(str(text))
        if base == "ru" and chars & _UKRAINIAN:
            return False
        if base == "uk" and chars & _RUSSIAN:
            return False
        if base not in ("ru", "uk"):
            return None
        return True if base == "ru" or chars & _UKRAINIAN else None
    if want == "arabic":
        special = bool(set(str(text)) & _PERSIAN_URDU)
        if base == "ar":
            return not special
        return True if special else None
    if want != "latin":
        return True
    found = _latin_language(text)
    if found is None:
        return None
    if base == "no" and found in ("nb", "nn", "no", "da"):
        return True
    return found == base


def page_in_language(texts, target, share=0.8):
    """Whether most of what a page has in `target`'s script, of what can
    be judged, is in `target` - the German of a page that is German and
    Chinese, for someone reading in German."""
    verdicts = [in_language(t, target) for t in texts
                if same_script(t, target)]
    judged = [v for v in verdicts if v is not None]
    return len(judged) >= 2 and sum(judged) >= share * len(judged)


def same_script(text, target):
    """Whether `text` is written in the script `target` is written in."""
    counts = scripts(text)
    letters = sum(counts.values())
    if not letters:
        return False
    want = _SCRIPT_OF.get(_base(target), "latin")
    own = counts.get(want, 0)
    if want == "kana":
        own += counts.get("han", 0)
    return own >= 0.8 * letters
