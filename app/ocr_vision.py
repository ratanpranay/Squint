"""OCR through Apple's Vision framework, on macOS.

Vision ships with the OS, so there is no engine to download and no language
models to manage. It is also faster and more accurate than Tesseract on
screen text, and it returns per-line bounding boxes, which is exactly what
the in-place overlay needs.

Everything here is optional: if pyobjc is missing or the call fails, the
caller falls back to Tesseract. Import of this module never raises.
"""
import io
import threading
import time

AVAILABLE = False
_import_error = None
_lock = threading.Lock()


class _Gate:
    """One Vision request at a time - they are not re-entrant here - and a
    snip's own reading first.

    Reading ahead (the page you stop on, the page at the key press,
    hold-to-see's page) reads the whole screen, several passes of it on a
    page in more than one script, and a snip of part of that screen waited
    behind all of it: 34 and 45 seconds for a snip in one log, where the
    snip's own reading takes under one. A reading in the background
    (ocr.quick_only) now lets a waiting snip go before each of its passes,
    and leaves out its optional ones while a snip is waiting."""

    def __init__(self):
        self._cv = threading.Condition()
        self._busy = False
        self._urgent = 0

    def wanted(self):
        return self._urgent > 0

    def __enter__(self):
        urgent = not _background()
        started = time.monotonic()
        with self._cv:
            if urgent:
                self._urgent += 1
            try:
                while self._busy or (not urgent and self._urgent):
                    self._cv.wait(0.25)
            finally:
                if urgent:
                    self._urgent -= 1
            self._busy = True
        waited = time.monotonic() - started
        if urgent:
            _stats.waited = getattr(_stats, "waited", 0.0) + waited
        _stats.passes = getattr(_stats, "passes", 0) + 1
        return self

    def __exit__(self, *exc):
        with self._cv:
            self._busy = False
            self._cv.notify_all()
        return False


_gate = _Gate()
_stats = threading.local()


def _background():
    """A reading done ahead of time, not one somebody is waiting for."""
    try:
        from . import ocr
        return bool(getattr(ocr._thread, "no_slow", False))
    except Exception:
        return False


def last_detail():
    """What the last reading on this thread cost: Vision passes, and how
    long it waited for a reading done in the background. For the log."""
    passes = getattr(_stats, "passes", 0)
    waited = getattr(_stats, "waited", 0.0)
    if not passes:
        return ""
    return "%d pass%s%s" % (passes, "" if passes == 1 else "es",
                            ", waited %.0fms" % (1000 * waited)
                            if waited >= 0.05 else "")

try:
    import Quartz
    import Vision
    from Foundation import NSData
    AVAILABLE = True
except Exception as exc:  # pragma: no cover - only importable on macOS
    _import_error = exc
    Quartz = Vision = NSData = None


# Vision wants BCP-47 tags. It only accepts languages it actually supports,
# and an unsupported one makes the whole request fail, so this list is
# conservative and the result is filtered against what Vision reports.
SCRIPT_HINTS = {
    "Latin": ["en-US", "fr-FR", "de-DE", "es-ES", "it-IT", "pt-BR"],
    "Cyrillic": ["ru-RU", "uk-UA"],
    "HanS": ["zh-Hans"],
    "HanT": ["zh-Hant"],
    "Japanese": ["ja-JP"],
    "Hangul": ["ko-KR"],
    "Arabic": ["ar-SA"],
    "Thai": ["th-TH"],
}
ALL_HINTS = ["en-US", "zh-Hans", "zh-Hant", "ja-JP", "ko-KR", "fr-FR",
             "de-DE", "es-ES", "it-IT", "pt-BR", "ru-RU", "uk-UA", "ar-SA",
             "th-TH"]

#: The scripts that get read as one another. Han, kana and Hangul share
#: a good deal of their shape vocabulary and Vision will hand back one
#: for another without lowering its confidence at all. When the user has
#: named one of these, it is read as that one and nothing else — a list
#: with the other two still in it is a preference, and a preference is
#: what produced a Chinese page with Korean characters through it.
CONFUSABLE = ("zh-Hans", "zh-Hant", "ja-JP", "ko-KR")


def unavailable_reason():
    if AVAILABLE:
        return ""
    return ("Apple Vision is unavailable (%s). Install pyobjc, or the app "
            "will use Tesseract instead." % (_import_error or "unknown"))


def supported_languages():
    """Languages this machine's Vision build can actually recognise."""
    if not AVAILABLE:
        return []
    try:
        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(0)   # accurate
        langs = request.supportedRecognitionLanguagesAndReturnError_(None)
        if isinstance(langs, tuple):
            langs = langs[0]
        return [str(x) for x in (langs or [])]
    except Exception:
        return []


def _cgimage_from_pil(image):
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    data = NSData.dataWithBytes_length_(buffer.getvalue(),
                                        len(buffer.getvalue()))
    source = Quartz.CGImageSourceCreateWithData(data, None)
    if not source:
        raise RuntimeError("could not decode the image for Vision")
    cgimage = Quartz.CGImageSourceCreateImageAtIndex(source, 0, None)
    if not cgimage:
        raise RuntimeError("could not create a CGImage")
    return cgimage


# Recognition languages are a PRIORITY LIST, not a set. With "en-US" first,
# Vision reads a page of Chinese as badly-spelled English and returns things
# like "1*01574E8 HEV „OORA T6 Q" for 体验传祺E8 PHEV … 试驾启源Q06 — the Latin
# fragments survive and the Chinese becomes noise. So: let Vision detect the
# language itself where it can, and otherwise try CJK-first as well and keep
# whichever pass the engine was more confident about.
CJK_FIRST = ["zh-Hans", "zh-Hant", "ja-JP", "ko-KR", "en-US"]

# One retry order per writing system. There used to be only the CJK one,
# which is why Russian came back as Latin nonsense: АБВГДЕЁ was read as
# "AEBTAEE". Vision will confidently read Cyrillic as the Latin letters
# that look like it if Latin is what it was asked for, and nothing in the
# result says it guessed the alphabet wrong — the confidence is high and
# the text is not empty. The only defence is to read the image more than
# one way and keep the best.
SCRIPT_ORDERS = (
    ["zh-Hans", "zh-Hant", "ja-JP", "ko-KR", "en-US"],
    ["ru-RU", "uk-UA", "en-US"],
    ["ar-SA", "en-US"],
    ["th-TH", "en-US"],
)


def _run(cgimage, languages, fast, auto):
    request = Vision.VNRecognizeTextRequest.alloc().init()
    # Automatic detection only exists in later revisions, so ask for the
    # newest one this machine has before configuring anything else.
    try:
        revisions = Vision.VNRecognizeTextRequest.supportedRevisions()
        if revisions:
            request.setRevision_(max(int(r) for r in revisions))
    except Exception:
        pass
    request.setRecognitionLevel_(1 if fast else 0)
    request.setUsesLanguageCorrection_(True)
    used_auto = False
    if auto:
        try:
            request.setAutomaticallyDetectsLanguage_(True)
            used_auto = True
        except Exception:
            used_auto = False
    # A language list is a *priority* list, and setting one alongside
    # automatic detection tells Vision which alphabet to prefer — which
    # defeats the detection entirely. This code used to do both, with
    # en-US at the head, so the "automatic" pass was really an
    # English-first pass and Cyrillic came back as Latin lookalikes.
    # When detection is on, nothing is imposed on it.
    if languages and not used_auto:
        try:
            request.setRecognitionLanguages_(languages)
        except Exception:
            pass

    handler = Vision.VNImageRequestHandler.alloc().\
        initWithCGImage_options_(cgimage, None)
    with _gate:
        ok, error = handler.performRequests_error_([request], None)
    if not ok:
        raise RuntimeError("Vision failed: %s" % error)
    return (request.results() or []), used_auto


def _score(results):
    """Mean confidence, weighted by how much text was found.

    Comparing passes needs a single number. Confidence alone would prefer a
    pass that read one word perfectly over one that read the whole page well,
    so the amount of text matters too.
    """
    total, chars = 0.0, 0
    for observation in results:
        candidates = observation.topCandidates_(1)
        if not candidates:
            continue
        text = str(candidates[0].string())
        weight = max(1, len(text))
        total += float(candidates[0].confidence()) * weight
        chars += weight
    if not chars:
        return 0.0
    return (total / chars) * min(1.0, chars / 40.0)


def _text_of(results):
    parts = []
    for observation in results:
        candidates = observation.topCandidates_(1)
        if candidates:
            parts.append(str(candidates[0].string()))
    return " ".join(parts)


def _non_latin(results):
    """True if this reading is in a script Latin could not be mistaken for."""
    try:
        from .translator import script_of
        return bool(script_of(_text_of(results)))
    except Exception:
        return False


# The probe below is identifying an alphabet, not reading a page, and it
# does not need the pixels for that. Cyrillic still looks like Cyrillic at
# a third of the size, and the pass costs a fraction as much.
PROBE_MAX_EDGE = 700


def _shrunk(image, edge=PROBE_MAX_EDGE):
    longest = max(image.size)
    if longest <= edge:
        return image
    factor = edge / float(longest)
    from PIL import Image as _Image
    return image.resize((max(1, int(image.width * factor)),
                         max(1, int(image.height * factor))),
                        _Image.LANCZOS)


def _script_orders(wanted):
    orders = []
    for order in SCRIPT_ORDERS:
        trimmed = [lang for lang in order if lang in wanted]
        if len(trimmed) > 1:
            orders.append(trimmed)
    return orders


def _probe_for_script(cgimage, image, orders):
    """Which retry order, if any, is worth a full pass — cheaply.

    This is the fix for the thing that made every ordinary page slow. The
    early return above only fires when the automatic pass comes back in a
    non-Latin script, so a page of German — or English, or French, which is
    most pages — fell through to five more full-accuracy passes, each with
    its own set of language models to load, before picking the answer the
    first pass had already given. Six reads of the screen to translate a
    donate button.

    The run-off itself is not the mistake; a wrong alphabet reads as
    confident Latin and only a second opinion catches it. What was wrong is
    paying full price for the second opinion. Recognising *that there is
    Cyrillic here* is a much cheaper question than reading it: fast
    recognition level, on a small copy. So the alphabets are settled at that
    price, and full accuracy is spent only on an order that found something
    the automatic pass could not have invented.
    """
    probe_cg = cgimage
    if image is not None:
        try:
            probe_cg = _cgimage_from_pil(_shrunk(image))
        except Exception:
            probe_cg = cgimage
    best_order, best_score = None, 0.0
    for order in orders:
        try:
            results, _ = _run(probe_cg, order, True, auto=False)
        except Exception:
            continue
        if not _non_latin(results):
            continue          # nothing here the Latin reading missed
        score = _score(results)
        if score > best_score:
            best_order, best_score = order, score
    return best_order


def _recognise_best(cgimage, wanted, fast, preferred=None, image=None):
    """Recognise, and do not settle for a confidently wrong reading.

    A wrong alphabet does not look like a failure from the outside: Vision
    returns text, at high confidence, that happens to be nonsense. So the
    image is read several ways and the readings are compared.
    """
    attempts = []
    auto_results = None

    # Vision's own language detection, with nothing imposed on it.
    try:
        results, used_auto = _run(cgimage, None, fast, auto=True)
        attempts.append((_score(results), results, ["auto"]))
        if used_auto:
            auto_results = results
            if _non_latin(results) and not preferred:
                # Reading the wrong alphabet always comes out as Latin — it
                # is Latin letters that Cyrillic, Greek and Han characters
                # get mistaken for, never the other way round. So a pass
                # that returned Cyrillic or Han really did detect that
                # script, and there is nothing to be gained from reading
                # the image again.
                #
                # Confidence cannot be used for this. The misreading that
                # started all of this was confident, and the score here is
                # weighted by how much text was found, so no fixed
                # threshold means the same thing on a word and on a page.
                #
                # Unless the user has named the language. "Non-Latin" is
                # not one alphabet: Han, Hangul and kana are three, they
                # are mistaken for each other constantly, and detection
                # being right that a page is not Latin says nothing about
                # which of them it is. A Chinese page came back with
                # Korean glyphs in it through this return.
                return results, ["auto"]
    except Exception:
        pass

    if preferred:
        # An explicit choice in the app settles the alphabet, and the
        # run-off has nothing to add to it: if the user says the page is
        # Russian, that is better evidence than anything guessed here.
        # And the named one alone where the confusion actually happens.
        # A list is a preference, not a restriction — Vision will still
        # return Hangul for a Chinese page if ko-KR is anywhere in it —
        # so for the three scripts that are mistaken for one another the
        # list is the one language the user named.
        if preferred in CONFUSABLE:
            order = [preferred]
        else:
            order = ([preferred]
                     + [lang for lang in wanted if lang != preferred])
        try:
            results, _ = _run(cgimage, order, fast, auto=False)
            attempts.append((_score(results), results, order))
        except Exception:
            pass
    elif auto_results is not None:
        # Detection worked and found Latin. Check that cheaply rather than
        # re-reading the whole image once per writing system.
        winner = _probe_for_script(cgimage, image, _script_orders(wanted))
        if winner is None:
            return auto_results, ["auto"]
        try:
            results, _ = _run(cgimage, winner, fast, auto=False)
            attempts.append((_score(results), results, winner))
        except Exception:
            pass
    else:
        # No automatic detection on this machine, so there is no first
        # answer to check against and every order has to be read properly.
        for order in [list(wanted)] + _script_orders(wanted):
            try:
                results, _ = _run(cgimage, order, fast, auto=False)
            except Exception:
                continue
            attempts.append((_score(results), results, order))

    if not attempts:
        return [], wanted

    # A reading in a non-Latin script is trusted ahead of a Latin one, even
    # when the Latin one scored higher.
    #
    # The mistake only runs one way. Vision will read Cyrillic as the Latin
    # letters that look like it — and do so confidently, which is what made
    # this so hard to see — but it will not invent Cyrillic out of Latin
    # text. So Cyrillic coming back at all is strong evidence about the
    # image, while high confidence on Latin is no evidence at all.
    #
    # The floor keeps that from turning into superstition: a non-Latin
    # reading that is far worse than the best one is a failed pass, not a
    # discovery.
    best = max(score for score, _results, _order in attempts)
    solid = [item for item in attempts
             if _non_latin(item[1]) and item[0] >= best * 0.6]
    _score_of, results, order = max(solid or attempts,
                                    key=lambda item: item[0])
    return results, order


def recognise(image, languages=None, fast=False, preferred=None):
    """Return (lines, used_languages).

    `lines` matches the Tesseract path's shape: text plus a pixel box in the
    original image's coordinates, so the overlay code does not care which
    engine produced it.
    """
    if not AVAILABLE:
        raise RuntimeError(unavailable_reason())

    width, height = image.size
    wanted = list(languages or ALL_HINTS)
    supported = set(supported_languages())
    if supported:
        wanted = [lang for lang in wanted if lang in supported] or ["en-US"]

    _stats.passes, _stats.waited = 0, 0.0
    # One request at a time is _gate's job, a pass at a time, so that a
    # snip can go between the passes of a reading in the background.
    cgimage = _cgimage_from_pil(image)
    results, wanted = _recognise_best(cgimage, wanted, fast,
                                      preferred=preferred, image=image)

    lines = _lines_of(results, width, height)
    # A page in more than one writing system: read once per script and
    # judged part by part (ocr_windows.merge_readings), the same as on
    # Windows - a single reading of a German, Korean and Japanese page
    # misreads all but one of them.
    if not preferred and len(_kinds(lines)) >= 2 and \
            not (_background() and _gate.wanted()):
        try:
            from .ocr_windows import merge_readings
            readings = [("auto", lines, " ".join(l["text"] for l in lines))]
            for tag in ("zh-Hans", "ja-JP", "ko-KR"):
                if supported and tag not in supported:
                    continue
                if _background() and _gate.wanted():
                    break             # a snip is waiting: it goes first
                more, _ = _run(cgimage, [tag], fast, auto=False)
                got = _lines_of(more, width, height)
                readings.append((tag, got,
                                 " ".join(l["text"] for l in got)))
            merged = merge_readings(readings)
            if merged is not None:
                return merged[0], [merged[1]]
        except Exception:
            pass
    return lines, wanted


def _kinds(lines):
    """The writing systems a reading has lines in."""
    kinds = set()
    for line in lines:
        text = line.get("text", "")
        if any(0xAC00 <= ord(c) <= 0xD7AF for c in text):
            kinds.add("ko")
        elif any(0x3040 <= ord(c) <= 0x30FF for c in text):
            kinds.add("ja")
        elif any(0x4E00 <= ord(c) <= 0x9FFF for c in text):
            kinds.add("zh")
        elif sum(c.isalpha() for c in text) >= 3:
            kinds.add("latin")
    return kinds


def _lines_of(results, width, height):
    lines = []
    for observation in results:
        candidates = observation.topCandidates_(1)
        if not candidates:
            continue
        candidate = candidates[0]
        text = str(candidate.string()).strip()
        if not text:
            continue
        # Vision boxes are normalised with the origin at the bottom-left;
        # images are indexed from the top-left.
        box = observation.boundingBox()
        x = box.origin.x * width
        w = box.size.width * width
        h = box.size.height * height
        y = (1.0 - box.origin.y - box.size.height) * height
        line = {
            "text": text,
            "box": (int(round(x)), int(round(y)),
                    int(round(w)), int(round(h))),
            "conf": float(candidate.confidence()) * 100.0,
        }
        # Vision also gives the text's own corners, in reading order: text
        # at an angle is drawn back at that angle (see app/slant.py).
        try:
            from . import slant

            def point(p):
                return (p.x * width, (1.0 - p.y) * height)
            corners = [point(observation.topLeft()),
                       point(observation.topRight()),
                       point(observation.bottomRight()),
                       point(observation.bottomLeft())]
            slant.attach(line, corners, ordered=True)
        except Exception:
            pass
        lines.append(line)

    lines.sort(key=lambda ln: (ln["box"][1], ln["box"][0]))
    return lines


# The app's language codes are not Vision's tags.
VISION_TAG = {
    "en": "en-US", "ru": "ru-RU", "uk": "uk-UA", "zh": "zh-Hans",
    "zh-TW": "zh-Hant", "ja": "ja-JP", "ko": "ko-KR", "fr": "fr-FR",
    "de": "de-DE", "es": "es-ES", "it": "it-IT", "pt": "pt-BR",
    "ar": "ar-SA", "th": "th-TH",
}


def tag_for(code):
    """Vision's tag for one of the app's language codes, or None.

    When the user has chosen a source language, that is far better
    evidence than anything guessed from the pixels — so it is worth
    carrying all the way down here.
    """
    if not code or code == "auto":
        return None
    code = str(code)
    return VISION_TAG.get(code) or VISION_TAG.get(code.split("-")[0])


def image_to_lines(image, languages=None, source=None):
    lines, used = recognise(image, languages, preferred=tag_for(source))
    return lines, (used[0] if used else "auto")


def image_to_text(image, languages=None, source=None):
    lines, used = recognise(image, languages, preferred=tag_for(source))
    if not lines:
        return "", (used[0] if used else "auto")

    # Group into paragraphs by vertical gaps, so the text reads naturally
    # rather than as one line per visual row.
    out, previous_bottom, previous_height = [], None, None
    for line in lines:
        _x, y, _w, h = line["box"]
        if previous_bottom is not None:
            gap = y - previous_bottom
            if gap > max(6, (previous_height or h) * 0.9):
                out.append("")
        out.append(line["text"])
        previous_bottom = y + h
        previous_height = h
    text = "\n".join(out)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip(), (used[0] if used else "auto")
