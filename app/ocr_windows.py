"""Windows' own text recognition, so Windows reads as well as the Mac does.

Without this the Windows build falls back to Tesseract, which is markedly
worse on screen text and worst of all on Chinese — the language this app
exists to read. Windows has had a real OCR engine since Windows 10
(Windows.Media.Ocr); it needs nothing downloaded, and it recognises every
language the machine has a language pack for, which on a Chinese
company's PC certainly includes Chinese.

It is a WinRT API, reached through the `winsdk` package (or the older
`winrt`). Both are optional: if neither is installed, or the call fails
for any reason, `AVAILABLE` is False and ocr.py uses Tesseract as before.

The shape of what this returns matches ocr_vision and the Tesseract path —
text plus a pixel box in the original image's coordinates — so nothing
downstream needs to know which engine ran.
"""
import re
import threading

AVAILABLE = False
_import_error = ""
_lock = threading.Lock()

try:                                       # the current package
    from winsdk.windows.media.ocr import OcrEngine
    from winsdk.windows.globalization import Language
    from winsdk.windows.graphics.imaging import (
        BitmapDecoder, BitmapPixelFormat, SoftwareBitmap)
    from winsdk.windows.storage.streams import (
        DataWriter, InMemoryRandomAccessStream)
    AVAILABLE = True
except Exception as first_error:           # pragma: no cover - platform only
    try:                                   # the older name for the same thing
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.globalization import Language
        from winrt.windows.graphics.imaging import (
            BitmapDecoder, BitmapPixelFormat, SoftwareBitmap)
        from winrt.windows.storage.streams import (
            DataWriter, InMemoryRandomAccessStream)
        AVAILABLE = True
    except Exception as second_error:
        _import_error = "%s / %s" % (first_error, second_error)
        OcrEngine = Language = BitmapDecoder = None
        BitmapPixelFormat = SoftwareBitmap = None
        DataWriter = InMemoryRandomAccessStream = None


# The app's language codes are not BCP-47 tags.
WINDOWS_TAG = {
    "en": "en-US", "zh": "zh-Hans-CN", "zh-TW": "zh-Hant-TW",
    "ja": "ja-JP", "ko": "ko-KR", "ru": "ru-RU", "uk": "uk-UA",
    "fr": "fr-FR", "de": "de-DE", "es": "es-ES", "it": "it-IT",
    "pt": "pt-BR", "ar": "ar-SA", "th": "th-TH", "hi": "hi-IN",
    "nl": "nl-NL", "pl": "pl-PL", "tr": "tr-TR", "sv": "sv-SE",
}


def tag_for(code):
    """A Windows language tag for one of the app's codes, or None."""
    if not code or code == "auto":
        return None
    code = str(code)
    return WINDOWS_TAG.get(code) or WINDOWS_TAG.get(code.split("-")[0])


# What went wrong last time, in words a person can act on. The UI reads it;
# nothing depends on it, so it is never raised as an error.
last_note = ""


# -- telling a reading from noise ---------------------------------------
#
# Windows picks ONE language per pass and reports no confidence at all, so
# there is no score to compare readings by — they have to be judged on what
# they say. An English engine pointed at Chinese does not fail: it returns
# a handful of lines of plausible-looking rubbish ("探店东风风神L8Y" came
# back as "iRERJXIJXFL8Y"), which then gets translated and drawn over the
# page. Noise that announces itself is a bug; noise that looks like output
# is a much worse one.
_SCRIPT_RANGES = (
    (0x0370, 0x03FF), (0x0400, 0x04FF),          # Greek, Cyrillic
    (0x0590, 0x05FF), (0x0600, 0x06FF),          # Hebrew, Arabic
    (0x0900, 0x097F), (0x0E00, 0x0E7F),          # Devanagari, Thai
    (0x3040, 0x30FF), (0x3400, 0x4DBF),          # kana, CJK ext A
    (0x4E00, 0x9FFF), (0xAC00, 0xD7AF),          # CJK, Hangul
    (0xF900, 0xFAFF), (0xFF00, 0xFFEF),          # compat, fullwidth
)

_VOWELS = set("aeiouyAEIOUY")


def _is_script_char(ch):
    point = ord(ch)
    return any(low <= point <= high for low, high in _SCRIPT_RANGES)


_ACCENTED_VOWELS = set("àáâãäåæèéêëìíîïòóôõöøœùúûüýÿ"
                       "ÀÁÂÃÄÅÆÈÉÊËÌÍÎÏÒÓÔÕÖØŒÙÚÛÜÝŸ")
_CLUSTERS = (("sch", "S"), ("ch", "C"), ("ck", "K"), ("th", "T"),
             ("ph", "P"), ("sh", "H"), ("tz", "Z"))


def _is_latin_letter(ch):
    return ch.isalpha() and 0x00C0 <= ord(ch) <= 0x024F


def _is_vowel(ch):
    return ch in _VOWELS or ch in _ACCENTED_VOWELS


def _fold_clusters(text):
    for cluster, mark in _CLUSTERS:
        text = text.replace(cluster, mark)
    return text


def _is_jumble(word):
    """A token that no language would produce.

    No single signal is enough — every one of them has an innocent
    explanation somewhere, and calling real text nonsense is the worse
    mistake here. Two together is the bar.

    Short tokens are exempt outright: XC60, L8Y, GX7, N8L and M9 are model
    names, and this app is pointed at car pages. So are URLs and paths,
    which are legitimately unpronounceable.
    """
    letters = [c for c in word if c.isalpha()]
    if len(word) < 5 or len(letters) < 4:
        return False
    if any(_is_script_char(c) for c in word):
        return False
    if any(mark in word for mark in ("://", "/", "@", "\\")):
        return False

    ascii_letters = [c for c in letters if c.isascii()]
    signals = 0

    # Vowels and runs are counted over every Latin letter, with the
    # accented vowels as vowels. Counting only the plain ones made German
    # rubbish: "Fahrradhändler" lost its ä, which left "dhndl" - a run no
    # word has - and too few vowels, and single-word labels ("Fahrradhändler",
    # "Datenschutzerklärung", "Gesellschaftsform") were thrown away as
    # noise, so they were never translated at all.
    latin = [c for c in letters if c.isascii() or _is_latin_letter(c)]

    # 1. Too few vowels to be pronounceable. German runs lower than English
    #    ("Gesellschaftsform" is 0.24, "Herbststurm" 0.18).
    if latin:
        vowels = sum(1 for c in latin if _is_vowel(c))
        if vowels / float(len(latin)) < 0.15:
            signals += 1

    # 2. A run of consonants no word has. The common clusters count as one
    #    ("sch", "ch", "ck", "th", "ph", "sh", "tz"): "Gesellschaft" is five
    #    in a row otherwise. A long German word may still have one run
    #    ("Angstschweiß"); it takes a second signal to call it rubbish.
    folded = _fold_clusters("".join(latin).lower())
    run = longest = 0
    for c in folded:
        run = 0 if _is_vowel(c) else run + 1
        longest = max(longest, run)
    if longest >= 4:
        signals += 1

    # 3. Case flipping about inside one word.
    #    Each part of a hyphenated word on its own: "Kfz-Haftpflicht" and
    #    "E-Mail-Adresse" start each part with a capital.
    switches = 0
    for part in word.split("-"):
        plain = [c for c in part if c.isalpha() and c.isascii()]
        switches = max(switches, sum(1 for a, b in zip(plain, plain[1:])
                                     if a.isupper() != b.isupper()))
    if len(ascii_letters) >= 4 and switches >= 2:
        signals += 1

    # 4. A digit wedged between letters — L61E, not XC60.
    body = word.strip("0123456789")
    if any(c.isdigit() for c in body):
        signals += 1

    # 5. Accented letters mixed in with capitals: ä next to RJ is what a
    #    Latin engine reaches for when the shape is not in its alphabet.
    #    A capital at the start is only a noun: "Fahrradhändler".
    inner = [c for c in letters[1:] if c.isascii()]
    if (any(c.isalpha() and not c.isascii() for c in letters)
            and any(c.isupper() for c in inner)
            and not word.isupper()):
        signals += 1

    return signals >= 2


def reading_score(text):
    """How much of this looks like language rather than noise."""
    dense = "".join(str(text).split())
    if not dense:
        return 0.0
    words = [w for w in str(text).split() if w]
    junk = sum(1 for w in words if _is_jumble(w))
    ratio = (junk / float(len(words))) if words else 0.0
    return len(dense) * (1.0 - 0.85 * ratio)


def script_chars(text):
    return sum(1 for ch in str(text) if _is_script_char(ch))


# How much of a reading has to be in a writing system of its own before
# that reading is believed *because* of it.
#
# The count alone was the bug. "A misreading can only come out as Latin"
# is true of an English engine pointed at Chinese, and the rule built on
# it — two CJK characters and the reading wins — held for three releases
# because that was the only direction anyone tested. It does not hold the
# other way. A Chinese engine pointed at German reads most of the page
# correctly and drops a handful of CJK lookalikes into it, and two is all
# it takes: a screen of English came back as
#
#   「 《 ] time-read 国 〕 build check.command 国 〕 debu
#
# with exactly two characters in the 4E00 block, and that reading beat the
# two that were right. On an ordinary page it shows up as an email address
# with one letter changed, a domain with an extra dot, an accented letter
# drawn as a digit — each one clean, typeset, and untrue. Worse than
# garbage, because it reads as fine. The languages involved are whichever
# packs happen to be installed; nothing about this is specific to them.
#
# A share fixes it and keeps what the rule was for. A genuine Chinese page
# is most of the way CJK; a Latin page misread by the Chinese engine is
# two or three characters in two hundred. Anything between those is a
# mixed page, where the Latin reading is the safer of the two anyway.
SCRIPT_SHARE = 0.15

# What one stray out-of-script character takes off a reading's score when
# no reading qualifies as being in that script. Small, because the score is
# a character count and the point is only to break ties away from the
# engine that was guessing.
SCRIPT_DEBRIS_COST = 2.0


def script_share(text):
    """What fraction of the non-space characters are in their own script."""
    dense = "".join(str(text).split())
    if not dense:
        return 0.0
    return script_chars(text) / float(len(dense))


def has_real_script(text):
    """A reading that is in another writing system, rather than one that
    has a few of its characters sprinkled through Latin."""
    return script_chars(text) >= 2 and script_share(text) >= SCRIPT_SHARE


def unavailable_reason():
    if AVAILABLE:
        return ""
    return ("Windows OCR is unavailable (%s). Install the 'winsdk' package, "
            "or the app will use Tesseract instead." % (_import_error
                                                        or "unknown"))


_loops = threading.local()


def _run(coro):
    """WinRT calls are asynchronous; this waits for one.

    One loop per thread, kept. Reading a snip goes through here around ten
    times — four to hand the picture over, one per installed language pack
    — and this used to build a fresh event loop for every one of them and
    then drop it on the floor. On Windows that is a ProactorEventLoop: an
    I/O completion port and a thread pool, neither of which is returned by
    being forgotten, since the reading happens on a worker thread where
    get_event_loop() does not find the one left from last time.
    """
    import asyncio
    loop = getattr(_loops, "loop", None)
    if loop is None or loop.is_closed():
        try:
            loop = asyncio.get_event_loop_policy().get_event_loop()
            if loop.is_running() or loop.is_closed():
                raise RuntimeError("not usable here")
        except Exception:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        _loops.loop = loop
    return loop.run_until_complete(coro)


def available_languages():
    """BCP-47 tags this machine can actually recognise."""
    if not AVAILABLE:
        return []
    try:
        return [str(lang.language_tag)
                for lang in OcrEngine.available_recognizer_languages]
    except Exception:
        return []


def _software_bitmap(image):
    """A PIL image as the bitmap type WinRT wants.

    Handed over as an encoded PNG rather than raw pixels: the buffer types
    needed to build a SoftwareBitmap by hand differ between the winsdk and
    winrt packages, while the decoder is the same in both.
    """
    import io
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    payload = buffer.getvalue()

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream.get_output_stream_at(0))
    writer.write_bytes(payload)
    _run(writer.store_async())
    _run(writer.flush_async())
    stream.seek(0)

    decoder = _run(BitmapDecoder.create_async(stream))
    return _run(decoder.get_software_bitmap_async(
        BitmapPixelFormat.BGRA8, decoder.bitmap_alpha_mode))


def _engine_for(tag):
    if tag:
        try:
            engine = OcrEngine.try_create_from_language(Language(tag))
            if engine is not None:
                return engine
        except Exception:
            pass
    # Whatever the machine's own language settings imply.
    return OcrEngine.try_create_from_user_profile_languages()


def _matches(wanted, installed):
    """zh-Hans-CN asked for, zh-Hans installed — the same language.

    The rule lives in win_langpack because the hard case belongs to it:
    Windows calls the pack zh-CN and then reports the installed language
    as zh-Hans-CN, and the old comparison here split on "-" and required
    the second field to agree, so "cn" and "hans" disagreed and a pack
    that had just been installed looked absent. Imported late — that
    module reaches back into this one.
    """
    try:
        from . import win_langpack
        return win_langpack.same_language(wanted, installed)
    except Exception:
        wanted, installed = str(wanted).lower(), str(installed).lower()
        return wanted == installed


def resolve_tag(wanted):
    """The installed tag that satisfies `wanted`, or None."""
    if not wanted:
        return None
    for tag in available_languages():
        if _matches(wanted, tag):
            return tag
    return None


def _candidate_tags(preferred):
    """Which languages to try, best bet first.

    With a language chosen in the app there is one candidate and no guessing.
    Without one, every language this PC has a pack for is tried, because
    Windows will not detect between them — and the non-Latin ones go first,
    since those are the readings a Latin engine cannot produce by accident.
    """
    installed = available_languages()
    if preferred:
        exact = resolve_tag(preferred)
        if exact:
            return [exact]
        # Asked for a language Windows cannot read here. Try the rest, but
        # remember why the answer may be poor.
        global last_note
        last_note = missing_language_note(preferred, installed)

    def rank(tag):
        head = str(tag).split("-")[0].lower()
        return (0 if head in _NON_LATIN_HEADS else 1, str(tag))

    return sorted(installed, key=rank)[:5]


_NON_LATIN_HEADS = {"zh", "ja", "ko", "ru", "uk", "bg", "sr", "el", "ar",
                    "he", "fa", "hi", "th", "ta", "te", "kn", "ml"}


def missing_language_note(wanted, installed=None):
    """What to do about a language Windows has no OCR pack for.

    This is the failure that produced garbage on screen, and it is not
    something the app can fix for the user: Windows recognises exactly the
    languages it has packs for, and a fresh PC in an English office has
    only English. The instructions matter more than the diagnosis.
    """
    installed = available_languages() if installed is None else installed
    have = ", ".join(sorted(installed)) or "none"
    return ("Windows has no text-recognition pack for %s on this PC — it "
            "can read: %s. Settings › Engines will add one; it is a "
            "Windows download, not an app one."
            % (wanted, have))


def _lines_from(result):
    lines = []
    for line in result.lines:
        text = str(line.text).strip()
        if not text:
            continue
        left = top = None
        right = bottom = 0.0
        for word in line.words:
            box = word.bounding_rect
            x0, y0 = float(box.x), float(box.y)
            x1, y1 = x0 + float(box.width), y0 + float(box.height)
            left = x0 if left is None else min(left, x0)
            top = y0 if top is None else min(top, y0)
            right, bottom = max(right, x1), max(bottom, y1)
        if left is None:
            continue
        lines.append({"text": text,
                      "box": (int(left), int(top),
                              int(right - left), int(bottom - top))})
    return lines


def choose_reading(readings):
    """Pick the reading that says something, out of one per language.

    The rule is the one that fixed Cyrillic on the Mac, for the same
    reason: a misreading can only ever come out as Latin, because that is
    the alphabet the wrong engine knows. So a reading containing real
    Chinese, Japanese, Korean, Cyrillic or Arabic characters is believed
    over a Latin one unless it is markedly shorter — it cannot have been
    invented. Between Latin readings the less jumbled one wins.

    `readings` is a list of (tag, lines, text).
    """
    scored = [(tag, lines, text, reading_score(text), script_chars(text))
              for tag, lines, text in readings if text.strip()]
    if not scored:
        return None
    best = max(score for _t, _l, _x, score, _s in scored)
    real_script = [r for r in scored
                   if has_real_script(r[2]) and r[3] >= best * 0.5]
    # A Korean reading made of syllables Korean hardly uses is the Korean
    # pack guessing at glyphs it does not know - Chinese, usually - and is
    # set aside when another pack read the same text in its own script.
    if len(real_script) > 1:
        plausible = [r for r in real_script
                     if not (str(r[0]).lower().startswith("ko")
                             and not plausible_korean(r[2]))]
        if plausible and len(plausible) < len(real_script) and any(
                native_chars(r[0], r[2]) >= 2 for r in plausible):
            real_script = plausible
    if real_script:
        return max(real_script,
                   key=lambda r: (native_chars(r[0], r[2]), r[4], r[3]))[:3]
    # None of them is in a writing system of its own, so every one of them
    # is Latin — and the stray CJK characters some of them contain are not
    # content, they are the engine reaching for a shape it did not know.
    # Ranking on length alone rewarded exactly that: a Korean pack reading
    # a screen of English produced seven characters nobody typed, which
    # made its reading the longest, which made it the winner. Debris costs
    # a reading rather than earning it.
    ranked = [latin_rank(r[2]) + (r[3], r[0]) for r in scored]
    best = _break_tie(ranked, {r[0]: r[2] for r in scored})
    return next(r for r in scored if r[0] == best[-1])[:3]


def _overlap(a, b):
    """Share of the smaller of two boxes (x, y, w, h) covered by the other."""
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1 = min(a[0] + a[2], b[0] + b[2])
    y1 = min(a[1] + a[3], b[1] + b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    smaller = max(1, min(a[2] * a[3], b[2] * b[3]))
    return (x1 - x0) * (y1 - y0) / float(smaller)


def _script_tag(tag):
    return str(tag or "").lower()[:2] in ("zh", "ja", "ko")


def _judge_part(texts):
    """Which language's reading of one part of the page to believe.
    `texts`: {tag: text}. The tag, or None when none of them is text."""
    real = []
    for tag, text in texts.items():
        dense = "".join(text.split())
        own = native_chars(tag, text)
        if _script_tag(tag) and own >= 2 and dense and \
                own >= 0.3 * sum(1 for c in dense if not c.isdigit()):
            real.append((tag, text, own))
    if len(real) > 1:
        # A Korean pack guessing at Chinese or Japanese characters makes
        # Hangul of them. Where another pack read the same part as Han
        # characters - three or more - the Korean reading is kept only if
        # it reads like Korean and has clearly more to it.
        han = max([sum(1 for c in r[1] if _in(c, *_HAN)) for r in real
                   if not r[0].lower().startswith("ko")] or [0])
        kept = []
        for r in real:
            if r[0].lower().startswith("ko"):
                if not plausible_korean(r[1]):
                    continue
                if han >= 3 and r[2] <= 1.5 * han:
                    continue
            kept.append(r)
        real = kept or real
    if real:
        return max(real, key=lambda r: (r[2], reading_score(r[1])))[0]
    latin = []
    for tag, text in texts.items():
        if not text.strip() or looks_like_noise(text):
            continue
        dense = "".join(text.split())
        if len(dense) >= 4 and reading_score(text) < 0.6 * len(dense):
            continue
        latin.append(latin_rank(text) + (not _script_tag(tag), tag))
    if not latin:
        return None
    return _break_tie(latin, texts)[-1]


# Packs whose own alphabet is not Latin. Asked to read Latin text they read
# it, but without the language: the Russian pack read "Il corso" as
# "11 corso" and "l'esonero" as "Ilesonero".
_NON_LATIN_PACKS = {"ru", "uk", "bg", "sr", "el", "ar", "fa", "he", "hi",
                    "th", "zh", "ja", "ko"}


def _break_tie(ranked, texts):
    """The best of `ranked` (latin_rank + (…, tag) tuples). Where the best
    are level, the tie went to the tag that sorts last - "ru-RU" over
    "it-IT" and "en-US" - so on an Italian page the Russian pack's reading
    won. Now a tie goes to the pack of the language the text is in, then
    to a pack whose own alphabet is Latin."""
    ranked = sorted(ranked, reverse=True)
    top = ranked[0]
    level = [r for r in ranked if r[:2] == top[:2]]
    if len(level) < 2:
        return top
    language = None
    try:
        from . import langid
        language = langid._latin_language(texts.get(top[-1], ""))
    except Exception:
        language = None

    def fit(r):
        head = str(r[-1]).lower().split("-")[0]
        return (head == language, head not in _NON_LATIN_PACKS)
    return max(level, key=lambda r: fit(r) + tuple(r))


_WEDGED = re.compile(r"[^\W\d_][0-9]+[^\W\d_A-Z]")
_LEADING = re.compile(r"^[0-9][^\W\d_A-Z]{3,}$")
_UNIT_TAILS = {"min", "sec", "mins", "secs", "hrs", "days", "mbit", "gbit",
               "mbps", "gbps", "kwh", "mah", "khz", "mhz", "ghz", "rpm"}


def latin_rank(text):
    """How to choose between Latin readings of the same line.

    Length (less jumble and debris) first, as before. Where two packs read
    the same line to the same length, the tie used to go to whichever
    language's name came last - English over German - and the English pack
    draws what it has no letter for as the nearest thing it has: "Über"
    came back as "0ber", "persönlich" as "pers6nlich", and "für" as "fur".
    So a tie now goes to the reading with fewer letters-turned-digits,
    then to the one with more accented letters: only a pack that knows
    those letters writes them."""
    text = str(text)
    wedged = 0
    for word in text.split():
        bare = word.strip("()[]{}.,;:!?\"'")
        if _WEDGED.search(bare) or (_LEADING.match(bare) and
                                     bare[1:].lower() not in _UNIT_TAILS):
            wedged += 1
    accented = sum(1 for c in text if _is_latin_letter(c))
    return (reading_score(text) - SCRIPT_DEBRIS_COST * script_chars(text)
            - wedged, accented)


def merge_readings(readings):
    """One reading of a page in several languages, part by part.

    Windows reads one language per pass, and the passes used to be judged
    as wholes: the best reading of the page won and the rest were thrown
    away. On a page in German, Korean and Japanese, that is a German
    reading of Korean and Japanese - misread into Latin nonsense, or not
    read at all, so those parts were translated as rubbish or left alone.
    Now the page is judged part by part: where the passes found the same
    line, the language whose reading of that line is in its own script
    wins there (the same rule as choose_reading), and elsewhere the
    cleanest Latin reading. `readings`: [(tag, lines, text)].
    Returns (lines, tag of the language with most text) or None."""
    cands = []
    for order, (tag, lines, _text) in enumerate(readings):
        for index, line in enumerate(lines):
            cands.append((tag, line, order, index))
    if not cands:
        return None
    cands.sort(key=lambda c: c[1]["box"][1])
    parent = list(range(len(cands)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i, (_t, a, _o, _x) in enumerate(cands):
        bottom = a["box"][1] + a["box"][3]
        for j in range(i + 1, len(cands)):
            b = cands[j][1]
            if b["box"][1] >= bottom:
                break
            if _overlap(a["box"], b["box"]) > 0.5:
                parent[find(i)] = find(j)
    parts = {}
    for i, cand in enumerate(cands):
        parts.setdefault(find(i), []).append(cand)
    chosen, amount = [], {}
    for members in parts.values():
        by_tag = {}
        for tag, line, order, index in members:
            by_tag.setdefault(tag, []).append((index, line))
        texts = {tag: " ".join(l["text"] for _i, l in sorted(items,
                                                            key=lambda x: x[0]))
                 for tag, items in by_tag.items()}
        tag = _judge_part(texts)
        if tag is None:
            continue
        for index, line in sorted(by_tag[tag], key=lambda x: x[0]):
            chosen.append(line)
        amount[tag] = amount.get(tag, 0) + len("".join(texts[tag].split()))
    if not chosen:
        return None
    # Reading order: top to bottom, and within a band of the same height
    # left to right - the order the passes give when they agree.
    chosen.sort(key=lambda l: (l["box"][1] + l["box"][3] // 2, l["box"][0]))
    ordered, row = [], []
    for line in chosen:
        if row and line["box"][1] >= min(r["box"][1] + r["box"][3]
                                         for r in row) - 2:
            ordered.extend(sorted(row, key=lambda l: l["box"][0]))
            row = []
        row.append(line)
    ordered.extend(sorted(row, key=lambda l: l["box"][0]))
    return ordered, max(amount, key=amount.get)


def _in(ch, *ranges):
    code = ord(ch)
    return any(low <= code <= high for low, high in ranges)


_HANGUL = ((0xAC00, 0xD7AF), (0x1100, 0x11FF), (0x3130, 0x318F))
_KANA = ((0x3040, 0x309F), (0x30A0, 0x30FF))
_HAN = ((0x4E00, 0x9FFF), (0x3400, 0x4DBF))


# The syllables running Korean is mostly made of: particles, endings and
# the commonest word parts. Real Korean of any length is full of them; a
# Korean pack reading Chinese produces syllables almost at random.
_COMMON_KO = set("이다는의에하고을를가한서로지기도으은나사수어게것들대적인"
                 "정아리자시라해요니습과보부주장전제일만연성상소위생회"
                 "있되년중마구모그무여원용우화동면")


def plausible_korean(text):
    syllables = [ch for ch in str(text or "") if 0xAC00 <= ord(ch) <= 0xD7AF]
    if len(syllables) < 4:
        return True
    common = sum(1 for ch in syllables if ch in _COMMON_KO)
    return common >= 0.25 * len(syllables)


def native_chars(tag, text):
    """How many characters of this reading are in its own language's script.

    The readings used to be ranked on how many characters of *any* CJK
    script each contained, and a Korean pack pointed at a large Chinese
    headline won: it reads the unfamiliar glyphs as Hangul lookalikes, and
    a Hangul syllable counted exactly as much as the Chinese character the
    Chinese pack had read correctly. The page was then translated as
    Korean. A Korean reading is evidence of Korean only in Hangul; a Chinese
    reading only in Han; a Japanese one in kana, with Han counting for half
    since Chinese has Han and no kana.
    """
    tag = str(tag or "").lower()
    text = str(text or "")
    if tag.startswith("ko"):
        return sum(1 for ch in text if _in(ch, *_HANGUL))
    if tag.startswith("zh"):
        return sum(1 for ch in text if _in(ch, *_HAN))
    if tag.startswith("ja"):
        kana = sum(1 for ch in text if _in(ch, *_KANA))
        han = sum(1 for ch in text if _in(ch, *_HAN))
        return kana + (han if kana else han // 2)
    return script_chars(text)


# Reading at the size that suits the text. A 4K screen read at full size
# took Windows' reader 1-1.5 seconds per language pack, and every pack
# installed reads it; text that is large enough reads as well at half the
# size in a quarter of the pixels. Very small text reads better enlarged.
BIG_PIXELS = 5_000_000       # above this, try half size
HALF_MIN_HEIGHT = 14         # typical line height at half size to keep it
SMALL_PIXELS = 1_500_000     # below this, check for tiny text
SMALL_HEIGHT = 11            # typical line height that is read at 2x


def _resample():
    try:
        from PIL import Image
        return Image.LANCZOS
    except Exception:
        return 1


def _read_with(tag, bitmap):
    try:
        engine = OcrEngine.try_create_from_language(Language(tag))
        if engine is None:
            return None
        return _lines_from(_run(engine.recognize_async(bitmap)))
    except Exception:
        return None


def _unscaled(lines, factor):
    if factor == 1.0:
        return lines
    for line in lines:
        x, y, w, h = line["box"]
        line["box"] = (int(x / factor), int(y / factor),
                       max(1, int(w / factor)), max(1, int(h / factor)))
    return lines


def _typical_height(lines):
    heights = sorted(l["box"][3] for l in lines if l["box"][3] > 0)
    return heights[len(heights) // 2] if heights else 0


def _reading_size(image, tags):
    """(factor, readings already made at it, their tags). One pack reads
    first - at half size for a big capture, as it is for a small one - and
    the height of the lines it found decides the size for all of them."""
    if not tags:
        return 1.0, [], set()
    first = tags[0]
    pixels = image.width * image.height
    if pixels > BIG_PIXELS:
        half = image.resize((image.width // 2, image.height // 2),
                            _resample())
        lines = _read_with(first, _software_bitmap(half))
        if lines and _typical_height(lines) >= HALF_MIN_HEIGHT:
            lines = _unscaled(lines, 0.5)
            return 0.5, [(first, lines, " ".join(
                l["text"] for l in lines))], {first}
        return 1.0, [], set()
    if pixels < SMALL_PIXELS:
        lines = _read_with(first, _software_bitmap(image))
        if lines and _typical_height(lines) < SMALL_HEIGHT:
            return 2.0, [], set()
        if lines is not None:
            return 1.0, [(first, lines, " ".join(
                l["text"] for l in lines))], {first}
    return 1.0, [], set()


def recognise(image, languages=None, fast=False, preferred=None):
    """Return (lines, used_language). Mirrors ocr_vision.recognise.

    Windows recognises one language per pass and, unlike Vision, reports no
    confidence and does no detection at all — so asking it to read a page
    without saying what is on it means asking the machine's own display
    language, which in an English-language office is English. Pointed at
    Chinese, an English engine does not decline: it returns junk. That junk
    was then translated and drawn over the page.

    So when no language is chosen, every pack the PC has is tried and the
    readings are compared. It is one extra pass per installed language on
    an already-cropped image, which is cheap next to being wrong.
    """
    del fast, languages                    # Windows offers no such knobs
    if not AVAILABLE:
        raise RuntimeError(unavailable_reason())

    global last_note
    last_note = ""
    tags = _candidate_tags(preferred)

    with _lock:
        factor, readings, done = _reading_size(image, tags)
        work = image if factor == 1.0 else image.resize(
            (max(1, int(image.width * factor)),
             max(1, int(image.height * factor))), _resample())
        bitmap = _software_bitmap(work)
        for tag in tags:
            if tag in done:
                continue
            lines = _read_with(tag, bitmap)
            if lines is None:
                continue
            lines = _unscaled(lines, factor)
            readings.append((tag, lines, " ".join(l["text"] for l in lines)))
        if not readings:
            # No pack matched. Fall back to whatever the machine implies,
            # rather than returning nothing at all.
            engine = OcrEngine.try_create_from_user_profile_languages()
            if engine is None:
                raise RuntimeError(
                    "Windows has no text-recognition pack installed. Add "
                    "one under Settings › Time & language › Language & "
                    "region, then install “Optical character recognition” "
                    "in that language's options.")
            result = _run(engine.recognize_async(bitmap))
            lines = _lines_from(result)
            tag = "windows"
            try:
                tag = str(engine.recognizer_language.language_tag)
            except Exception:
                pass
            readings = [(tag, lines, " ".join(l["text"] for l in lines))]

    merged = merge_readings(readings) if len(readings) > 1 else None
    if merged is not None:
        lines, tag = merged
        text = " ".join(l["text"] for l in lines)
    else:
        chosen = choose_reading(readings)
        if chosen is None:
            return [], (readings[0][0] if readings else "windows")
        tag, lines, text = chosen
    # Say so when the best available reading is still mostly noise: that
    # means the language on screen is one this PC cannot read, and no
    # amount of retrying will change it.
    if lines and not has_real_script(text) and reading_score(text) < len(
            "".join(text.split())) * 0.6:
        last_note = missing_language_note("the language on screen")
    return lines, tag


def looks_like_noise(text):
    """A reading that is mostly tokens no language produces.

    Deliberately hard to trigger: several words, none of them in a script
    of their own, and most of them jumbled. A licence key or a hex dump can
    still trip it, which is why this only stops the overlay from drawing
    over the page — the text itself is never thrown away.
    """
    words = [w for w in str(text).split() if len(w) >= 3]
    if len(words) < 2 or has_real_script(text):
        return False
    junk = sum(1 for w in words if _is_jumble(w))
    return junk >= max(2, int(len(words) * 0.6))


def might_be_misread(text):
    """A softer test than looks_like_noise, for deciding whether to ask
    someone else.

    looks_like_noise has to be nearly certain, because it stops the overlay
    drawing at all. This one only decides whether a second opinion is worth
    a network round-trip, and a wrong guess costs one unit out of a thousand
    — so a single junk token on a page with no Chinese, Japanese, Korean,
    Cyrillic or Arabic in it is enough. That case was real: Windows read a
    Chinese car page as four lines, one of them "}RERJXlJXFL8Y", and
    because the other three looked like model numbers the page passed.
    """
    if has_real_script(text):
        return False
    # A few CJK or Cyrillic characters loose in an otherwise Latin reading
    # are not a language — they are the engine reaching outside the
    # alphabet actually on screen, which is the clearest evidence there is
    # that the wrong pack answered. It used to mean the opposite: two of
    # them and the reading was declared trustworthy, so the one case that
    # most deserved a second opinion was the one case that never got one.
    if script_chars(text) >= 2:
        return True
    words = [w for w in str(text).split() if len(w) >= 3]
    if not words:
        return False
    jumbled = sum(1 for w in words if _is_jumble(w))
    if not jumbled:
        return False
    # One odd word in a page of ordinary ones is German, not a misreading:
    # "Rechtsschutzversicherung" has seven consonants in a row. Asking for a
    # second opinion on it sent one German snip in ten to the cloud reader
    # - over a second slower, charged, and read differently from the same
    # page read on this computer. A short reading still asks on one; a
    # long one when more than one word in ten is jumbled.
    if len(words) < 8:
        return True
    return jumbled * 10 > len(words)


def image_to_lines(image, languages=None, source=None):
    lines, used = recognise(image, languages, preferred=tag_for(source))
    # Refuse to draw nonsense over someone's screen. Replacing 探店东风风神L8Y
    # with a translation of "iRERJXIJXFL8Y" is worse than doing nothing:
    # the page is defaced and the reason is invisible. The card path still
    # gets the text, beside the original, where it can be judged.
    joined = " ".join(line["text"] for line in lines)
    if lines and looks_like_noise(joined):
        global last_note
        last_note = last_note or missing_language_note(
            "the language on screen")
        return [], used
    return lines, used


def image_to_text(image, languages=None, source=None):
    lines, used = recognise(image, languages, preferred=tag_for(source))
    if not lines:
        return "", used

    # Group into paragraphs on vertical gaps, the same rule the Vision path
    # uses, so a page reads as prose rather than one line per visual row.
    out, previous_bottom, previous_height = [], None, None
    for line in lines:
        _x, y, _w, h = line["box"]
        if previous_bottom is not None:
            gap = y - previous_bottom
            if gap > max(6, (previous_height or h) * 0.8):
                out.append("\n")
            else:
                out.append(" ")
        out.append(line["text"])
        previous_bottom, previous_height = y + h, h
    return "".join(out).strip(), used
