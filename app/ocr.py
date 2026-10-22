"""Tesseract OCR with automatic script detection and on-demand language packs."""
import os
import time
import re
import shutil
import threading

from PIL import Image, ImageOps

from . import config, platform_util
from .langs import SCRIPT_TO_TESS, KNOWN_TESSDATA, tessdata_path

try:
    from . import ocr_vision
except Exception:      # pragma: no cover
    ocr_vision = None

try:
    from . import ocr_windows
except Exception:      # pragma: no cover
    ocr_windows = None

try:
    from . import ocr_paddle
except Exception:
    ocr_paddle = None

try:
    from . import ocr_google
except Exception:      # pragma: no cover
    ocr_google = None

try:
    from . import ocr_gemini
except Exception:      # pragma: no cover
    ocr_gemini = None

try:
    import pytesseract
except Exception:  # pragma: no cover
    pytesseract = None

# Two spellings of the same file: the raw host is canonical, the github.com
# form redirects to it. Some corporate proxies allow one and not the other.
TESSDATA_URLS = (
    "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/"
    "%s.traineddata",
    "https://github.com/tesseract-ocr/tessdata_fast/raw/main/%s.traineddata",
)

_setup_lock = threading.Lock()
_ready = False


class OcrError(RuntimeError):
    pass


# Which reader to use, as chosen in Settings. "auto" is the computer's own
# recogniser with Google behind it; the other two pin it.
OCR_CHOICE_KEY = "ocr_engine"
OCR_AUTO, OCR_LOCAL, OCR_CLOUD = "auto", "local", "cloud"
OCR_GEMINI = "gemini"


# Set on a thread that must not send anything off the computer - the
# read-ahead in the background (app/preread.py). While it is set, every
# choice reads as "on this computer only".
_thread = threading.local()


class local_only:
    """`with ocr.local_only():` - read with this computer's readers only."""

    def __enter__(self):
        _thread.local_only = True

    def __exit__(self, *exc):
        _thread.local_only = False
        return False


class quick_only:
    """`with ocr.quick_only():` - Windows' own reader only, never the slow
    one. For the read-ahead in the background, which reads every page you
    stop on: PaddleOCR takes 5-15 seconds of the processor on a 4K screen,
    and read-ahead ran it page after page, whether or not anything was
    ever snipped. What it would have been needed for is noted
    (`skipped_slow`) so that reading is not used, and the snip reads the
    page itself."""

    def __enter__(self):
        _thread.no_slow = True
        _thread.skipped = False

    def __exit__(self, *exc):
        _thread.no_slow = False
        _thread.skipped = False
        return False


def reading_detail():
    """What the last reading on this thread cost, for the log: on a Mac,
    Vision's passes and any wait for a reading done in the background."""
    try:
        if use_vision():
            return ocr_vision.last_detail()
    except Exception:
        pass
    return ""


def skipped_slow():
    """Whether the last reading on this thread under `quick_only` left
    out a reader it needed."""
    return bool(getattr(_thread, "skipped", False))


def ocr_choice():
    """Which reader, decided by the one engine setting.

    This used to be its own dropdown. It is not a separate decision:
    somebody who picks DeepL has not thereby said anything about what
    should read their screen, and being asked implies they have.
    """
    if getattr(_thread, "local_only", False):
        return OCR_LOCAL
    try:
        from . import profile
        return profile.reading()
    except Exception:
        pass
    value = str(config.CONFIG.get(OCR_CHOICE_KEY, "") or "").strip()
    if value in (OCR_AUTO, OCR_LOCAL, OCR_CLOUD, OCR_GEMINI):
        return value
    # Migrated from the switch this replaced, so anyone who turned cloud
    # reading off keeps it off.
    if config.CONFIG.get("use_cloud_vision", True) is False:
        return OCR_LOCAL
    return OCR_AUTO


def use_windows_ocr():
    """True when Windows' own recogniser should handle this.

    Windows.Media.Ocr is part of Windows, needs nothing downloaded, and is
    far better than Tesseract on screen text — especially Chinese, which is
    the whole point of this app. So on Windows it leads and Tesseract is
    the fallback, exactly as Vision leads on a Mac.
    """
    if not platform_util.IS_WINDOWS or ocr_windows is None:
        return False
    return bool(getattr(ocr_windows, "AVAILABLE", False))


def use_paddle():
    """PaddleOCR, bundled with the Windows install: after Windows' own
    reader and before the cloud. See ocr_paddle."""
    if ocr_paddle is None:
        return False
    try:
        return bool(ocr_paddle.use_here())
    except Exception:
        return False


def _misread(text):
    try:
        return bool(ocr_windows is not None
                    and ocr_windows.might_be_misread(text))
    except Exception:
        return False


# Which readers a snip went through and how long each took, for the timing
# line in the log. Reset at the start of every reading.
last_steps = []


def _step(name, started):
    try:
        last_steps.append("%s %.0fms" % (name, 1000 * (time.time() - started)))
    except Exception:
        pass


def _paddle_can_help(windows_text):
    """Whether PaddleOCR is worth its seconds after Windows has read.

    PaddleOCR reads Chinese, Japanese, Korean and English. On a page
    Windows read as Latin text, with a word or two it doubts, PaddleOCR
    reads the same page worse — it has no umlauts or accents — and it cost
    two full passes (the second looking for Korean) before the cloud was
    asked anyway: seconds on every German or French snip. There the cloud
    reader goes next, as it did before PaddleOCR arrived."""
    if not windows_text or not windows_text.strip():
        return True
    if not cloud_readers():
        return True
    try:
        return ocr_windows.script_chars(windows_text) >= 2
    except Exception:
        return True


def _paddle_read(img, source, want_lines=True):
    """(result, used, doubtful) from PaddleOCR, or None.

    The default model reads Chinese, Japanese and English. A Korean page
    in it comes back as noise, so when the language is not known and the
    reading is empty or looks wrong, Korean's model is asked as well.
    """
    reader = (ocr_paddle.image_to_lines if want_lines
              else ocr_paddle.image_to_text)
    try:
        result, used = reader(img, source=source)
    except Exception:
        return None

    def text_of(value):
        return (" ".join(line["text"] for line in value) if want_lines
                else value)
    text = text_of(result)
    # Korean's model only for a reading that is empty or strewn with
    # characters from another script. A Latin page with a doubtful word is
    # not Korean, and asking cost a second full pass.
    try:
        foreign = ocr_windows is not None and ocr_windows.script_chars(
            text) >= 2
    except Exception:
        foreign = False
    if (not source or str(source) == "auto") and (
            not text.strip() or (_misread(text) and foreign)):
        try:
            again, used_again = reader(img, source="ko")
            again_text = text_of(again)
            if again_text.strip() and not ocr_paddle.korean_needed(
                    again_text):
                result, used, text = again, used_again, again_text
        except Exception:
            pass
    if not text.strip():
        return None
    return result, used, _misread(text)


def use_vision():
    """True when Apple's built-in OCR should handle this.

    Vision is part of macOS, needs no downloaded models, and beats Tesseract
    on screen text — so on a Mac it is the default and Tesseract is the
    fallback, which is the opposite of the Windows arrangement.
    """
    if not platform_util.IS_MAC or ocr_vision is None:
        return False
    if not getattr(ocr_vision, "AVAILABLE", False):
        return False
    return bool(config.CONFIG.get("use_apple_vision", True))


def use_cloud_vision():
    """Google's reader, when a key is saved and it has not been turned off.

    On "auto" it is a fallback and nothing else: it costs a round-trip and
    an allowance, and it sends the selection to Google, so it is only
    reached once the machine's own reader has failed or come back with
    nonsense.
    """
    if ocr_google is None or ocr_choice() == OCR_LOCAL:
        return False
    try:
        return bool(ocr_google.api_key())
    except Exception:
        return False


def prefer_cloud_vision():
    """True when the user has pinned reading to Google."""
    return ocr_choice() == OCR_CLOUD and use_cloud_vision()


def use_gemini_ocr():
    """Gemini's reader, when an AI Studio key is saved.

    The point of it is the sign-up rather than the reading: a Gemini key
    needs a Google account and no credit card, where Google Cloud demands
    card details before it will let anyone near even the free tier. Four
    testers stopped at that card.
    """
    if ocr_gemini is None or ocr_choice() == OCR_LOCAL:
        return False
    try:
        return bool(ocr_gemini.available())
    except Exception:
        return False


def prefer_gemini_ocr():
    return ocr_choice() == OCR_GEMINI and use_gemini_ocr()


def cloud_readers():
    """The remote readers to try, best first, for the choice in Settings.

    On a pinned choice, only that one. On automatic, Cloud Vision leads
    when it is configured: it measures where text sits rather than
    estimating, and its terms do not put the picture into anyone's training
    data. Gemini is what someone has when they would not give Google Cloud
    a card, and for them it is the only rung there is.
    """
    if ocr_choice() == OCR_LOCAL:
        return []
    if prefer_cloud_vision():
        return [ocr_google] if use_cloud_vision() else []
    if prefer_gemini_ocr():
        return [ocr_gemini] if use_gemini_ocr() else []
    readers = []
    if use_cloud_vision():
        readers.append(ocr_google)
    if use_gemini_ocr():
        readers.append(ocr_gemini)
    return readers


def warm(timeout=25):
    """Load this computer's recogniser now, rather than on the first snip.

    The first read of a session is slower than every read after it, and by
    a lot: Windows loads a recognition model per installed pack, and Vision
    loads its own on the first request. It is the same work either way —
    the only question is whether the user is sitting watching a toast while
    it happens.

    They always were, and it happened at the worst possible moment: the
    first snip somebody takes is the one that decides whether the app
    works. "Very slow to read, so slow it doesn't give the results" was
    this, on a machine where nothing had been loaded yet, and it looked
    like a broken app rather than a cold one.

    Runs on a background thread at startup, touches no network (but for the
    reader's Korean model, fetched once in the background), and
    swallows everything — a warm-up that fails has cost nothing, because
    the real read will do the same work again.
    """
    del timeout
    try:
        from PIL import Image
        sample = Image.new("RGB", (48, 24), (255, 255, 255))
    except Exception:
        return False
    warmed = False
    if use_vision() and ocr_vision is not None:
        try:
            ocr_vision.recognise(sample, fast=True)
            warmed = True
        except Exception:
            pass
    if use_windows_ocr() and ocr_windows is not None:
        try:
            # Every pack, because the read tries every pack. Warming one
            # of five leaves four cold and the first snip still waiting.
            for tag in ocr_windows._candidate_tags(None):
                try:
                    engine = ocr_windows.OcrEngine.try_create_from_language(
                        ocr_windows.Language(tag))
                    if engine is not None:
                        warmed = True
                except Exception:
                    continue
        except Exception:
            pass
    if use_paddle():
        # Loading the models is most of a first read's time.
        try:
            ocr_paddle.image_to_lines(sample)
            warmed = True
        except Exception:
            pass
        try:
            threading.Thread(target=ocr_paddle.prefetch, daemon=True,
                             name="reader-models").start()
        except Exception:
            pass
    return warmed


def local_engine_name():
    """The recogniser built into this computer, whatever the choice is."""
    if platform_util.IS_MAC and ocr_vision is not None \
            and getattr(ocr_vision, "AVAILABLE", False):
        return "Apple Vision"
    if platform_util.IS_WINDOWS and ocr_windows is not None \
            and getattr(ocr_windows, "AVAILABLE", False):
        return "Windows OCR and PaddleOCR" if use_paddle() \
            else "Windows OCR"
    if use_paddle():
        return "PaddleOCR"
    return "Tesseract" if _find_tesseract_exe() else "none"


def engine_name():
    if prefer_cloud_vision():
        return "Google Cloud Vision"
    if prefer_gemini_ocr():
        return "Gemini"
    if use_vision():
        return "Apple Vision"
    if use_windows_ocr():
        return "Windows OCR"
    if use_cloud_vision():
        return "Google Cloud Vision"
    if use_gemini_ocr():
        return "Gemini"
    exe = _find_tesseract_exe()
    return "Tesseract" if exe else "none"


def readable_languages():
    """Which languages the reading engine can actually recognise here.

    On Windows this is not a detail: the engine reads the languages the PC
    has packs for and nothing else, and asking it to read one it does not
    have returns confident nonsense rather than an error.
    """
    if use_windows_ocr():
        try:
            return ocr_windows.available_languages()
        except Exception:
            return []
    return []


# What the last read wants the user to know — a missing Windows language
# pack, or Cloud Vision refusing the key. Set by the dispatch below, so it
# reflects the engine that actually answered rather than one that was tried
# and passed over.
_last_note = ""


def _note(text=""):
    global _last_note
    _last_note = str(text or "")


def reading_note():
    """Anything the last read wants the user to know. Usually empty."""
    return _last_note


def missing_language_note(wanted):
    if use_windows_ocr():
        try:
            return ocr_windows.missing_language_note(wanted)
        except Exception:
            return ""
    return ""


def _find_tesseract_exe():
    bundled = config.bundled_tesseract_dir()
    if bundled:
        return os.path.join(bundled, "tesseract.exe")
    found = shutil.which("tesseract")
    if found:
        return found
    for guess in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""),
                     "Programs", "Tesseract-OCR", "tesseract.exe"),
    ):
        if guess and os.path.isfile(guess):
            return guess
    return None


def ensure_ready():
    """Locate tesseract and seed the writable tessdata dir. Idempotent."""
    global _ready
    if use_vision():
        return            # nothing to install; Vision is part of the OS
    if _ready:
        return
    with _setup_lock:
        if _ready:
            return
        if pytesseract is None:
            raise OcrError("pytesseract is not installed")
        exe = _find_tesseract_exe()
        if not exe:
            raise OcrError(
                "The OCR engine is missing. Run setup.bat in the "
                "Squint folder to install it.")
        pytesseract.pytesseract.tesseract_cmd = exe

        dest = config.tessdata_dir()
        # Seed from whatever shipped next to the exe.
        for src in (os.path.join(os.path.dirname(exe), "tessdata"),
                    os.path.join(config.resource_dir(), "tessdata")):
            if os.path.isdir(src):
                for name in os.listdir(src):
                    if name.endswith(".traineddata"):
                        target = os.path.join(dest, name)
                        if not os.path.exists(target):
                            try:
                                shutil.copy2(os.path.join(src, name), target)
                            except Exception:
                                pass
        os.environ["TESSDATA_PREFIX"] = dest
        _ready = True


def installed_packs():
    if use_vision() and ocr_vision is not None:
        return set(ocr_vision.supported_languages())
    d = config.tessdata_dir()
    try:
        return {n[:-len(".traineddata")] for n in os.listdir(d)
                if n.endswith(".traineddata")}
    except Exception:
        return set()


def download_pack(pack, timeout=60):
    """Fetch one traineddata file from tessdata_fast. Returns True on success."""
    if pack not in KNOWN_TESSDATA:
        return False
    if pack in installed_packs():
        return True
    import urllib.request
    target = os.path.join(config.tessdata_dir(), pack + ".traineddata")
    tmp = target + ".part"
    path = tessdata_path(pack)
    for template in TESSDATA_URLS:
        try:
            req = urllib.request.Request(
                template % path, headers={"User-Agent": "Squint"})
            with urllib.request.urlopen(req, timeout=timeout) as resp, \
                    open(tmp, "wb") as fh:
                shutil.copyfileobj(resp, fh)
            if os.path.getsize(tmp) < 10000:
                raise OcrError("downloaded file looks truncated")
            os.replace(tmp, target)
            return True
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
    return False


MAX_PIXELS = 12_000_000     # keep a rescaled full-screen grab sane
TARGET_TEXT_PX = 34         # verified: below this, accuracy drops
MEASURE_PIXELS = 700_000    # the sizing pass only needs word heights
# Measured: at a word-box height of ~13px and above, Tesseract already reads
# at ~93% confidence and enlarging changes nothing; below it, accuracy falls
# off a cliff (68% at 9px, recovered to 95% by upscaling). So that is where
# the second pass earns its keep, and above it the first pass is the answer.
UPSCALE_BELOW_PX = 13


def preprocess(img, scale=1.0):
    """Grayscale + gentle contrast stretch, optionally rescaled.

    Scaling is deliberately *not* fixed. Blowing up text that is already
    large smears diacritics (German umlauts turn into plain vowels), while
    small UI text is unreadable without it — so the caller measures first.
    """
    img = img.convert("L")
    img = ImageOps.autocontrast(img, cutoff=1)
    if scale and scale > 1.01:
        w, h = img.size
        if w * h * scale * scale > MAX_PIXELS:
            scale = max(1.0, (MAX_PIXELS / float(w * h)) ** 0.5)
        if scale > 1.01:
            # BICUBIC beats LANCZOS here: less ringing around thin strokes.
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))),
                             Image.BICUBIC)
    return img


def lines_from_data(data, scale=1.0, min_conf=25.0):
    """Group words into lines with bounding boxes, in ORIGINAL image pixels.

    `scale` is whatever magnification the OCR ran at, so the boxes can be
    mapped back onto the untouched screenshot for drawing over.
    """
    groups = {}
    order = []
    for i, word in enumerate(data["text"]):
        if not word.strip():
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            continue
        if conf < min_conf:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        x, y = int(data["left"][i]), int(data["top"][i])
        w, h = int(data["width"][i]), int(data["height"][i])
        if key not in groups:
            groups[key] = {"words": [], "boxes": [], "x0": x, "y0": y,
                           "x1": x + w, "y1": y + h, "confs": []}
            order.append(key)
        g = groups[key]
        g["words"].append(word)
        g["confs"].append(conf)
        g["boxes"].append((x, y, w, h))
        g["x0"] = min(g["x0"], x)
        g["y0"] = min(g["y0"], y)
        g["x1"] = max(g["x1"], x + w)
        g["y1"] = max(g["y1"], y + h)

    lines = []
    for key in order:
        for seg in _split_columns(groups[key]):
            text = strip_cjk_spaces(" ".join(seg["words"])).strip()
            if not text:
                continue
            lines.append({
                "text": text,
                "box": (int(seg["x0"] / scale), int(seg["y0"] / scale),
                        int((seg["x1"] - seg["x0"]) / scale),
                        int((seg["y1"] - seg["y0"]) / scale)),
                "conf": sum(seg["confs"]) / len(seg["confs"]),
            })
    return lines


def _split_columns(group):
    """Break one Tesseract "line" where a wide gap says it is two columns.

    Tesseract happily joins side-by-side columns into a single line if they
    share a baseline, which for an overlay means one translated string
    smeared across both. A gap several times the normal word spacing is the
    giveaway, and splitting there keeps each column in its own box.
    """
    boxes = group["boxes"]
    if len(boxes) < 2:
        return [group]

    gaps = []
    for i in range(1, len(boxes)):
        gaps.append(boxes[i][0] - (boxes[i - 1][0] + boxes[i - 1][2]))
    positive = sorted(g for g in gaps if g > 0)
    if not positive:
        return [group]
    height = max(1, group["y1"] - group["y0"])
    # The reference is the width of a *word space*, and a word space is
    # never wider than the line is tall. Taking the median of every gap
    # instead was exactly backwards on the lines this exists for: on a row
    # that is entirely columns, every gap is a column gap, so the median is
    # enormous and the threshold derived from it can never be reached. The
    # more table-like a row was, the less likely it was to be split.
    #
    # Measured on a bill, at a capture 900 pixels wide:
    #
    #   Zählernummer / Zeitraum / Zählerstand / Verbrauch
    #       widest gap 254, threshold required 756   -> not split
    #   Ihre Stromkosten ......................  8,34 €
    #       widest gap 658, threshold required 2303  -> not split
    #
    # A label and a figure 658 pixels apart stayed one box, and every
    # column position on the page was gone before layout began. Measured
    # over the same page's prose lines, this change moves nothing: their
    # gaps are four or five pixels either way.
    word_gaps = [g for g in positive if g <= height]
    typical = word_gaps[len(word_gaps) // 2] if word_gaps else 0
    # A real column break is both far wider than the usual word gap and
    # comparable to the line height, which stops ordinary wide spacing from
    # triggering it.
    threshold = max(typical * 3.5, height * 1.2, 18)

    segments, current = [], [0]
    for i, gap in enumerate(gaps, start=1):
        if gap >= threshold:
            segments.append(current)
            current = []
        current.append(i)
    segments.append(current)
    if len(segments) == 1:
        return [group]

    out = []
    for indices in segments:
        if not indices:
            continue
        xs0 = min(boxes[i][0] for i in indices)
        ys0 = min(boxes[i][1] for i in indices)
        xs1 = max(boxes[i][0] + boxes[i][2] for i in indices)
        ys1 = max(boxes[i][1] + boxes[i][3] for i in indices)
        out.append({
            "words": [group["words"][i] for i in indices],
            "confs": [group["confs"][i] for i in indices],
            "boxes": [boxes[i] for i in indices],
            "x0": xs0, "y0": ys0, "x1": xs1, "y1": ys1,
        })
    return out


def _cjk_pack_installed():
    """Windows can read Chinese, Japanese and Korean on this computer."""
    try:
        heads = {str(t).lower()[:2] for t in ocr_windows.available_languages()}
        return {"zh", "ja", "ko"} <= heads
    except Exception:
        return True


def _text_rows_covered(lines, img):
    """Share of the picture's rows of text that the reading has a line on,
    or None when the picture has too little text to judge."""
    from PIL import ImageChops
    gray = img.convert("L")
    if gray.width > 800:
        gray = gray.resize((800, max(1, int(gray.height * 800.0 / gray.width))))
    scale = gray.width / float(max(1, img.width))
    shifted = ImageChops.offset(gray, 1, 0)
    edges = ImageChops.difference(gray, shifted).point(
        lambda v: 255 if v > 50 else 0)
    per_row = list(edges.resize((1, gray.height), Image.BOX).tobytes())
    texty = [i for i, v in enumerate(per_row) if v > 0.02 * 255]
    if len(texty) < 8:
        return None
    covered = set()
    for line in lines or ():
        _x, y, _w, h = line["box"]
        top, bottom = int(y * scale), int((y + h) * scale) + 1
        covered.update(range(max(0, top), bottom))
    return sum(1 for i in texty if i in covered) / float(len(texty))


SHORT_READING = 40


def _looks_unread(text, lines=None, img=None):
    """A reading that looks clean word by word but is not the page: a
    Latin pack pointed at Chinese says "fR3 A — Bj, fifi A fifi A A fifi"
    - no one word is rubbish, but it is mostly one- and two-letter scraps,
    and it has a line on only part of the text that is there."""
    tokens = [t for t in str(text or "").split()]
    if len(tokens) >= 5:
        scraps = sum(1 for t in tokens
                     if sum(1 for c in t if c.isalpha()) <= 2)
        if scraps * 2 > len(tokens):
            return True
    # The coverage test only for a reading with little in it: a Chinese
    # page read by a Latin pack comes back as a few scraps, where an English
    # page beside photographs comes back whole - and the photographs, which
    # are "rows with edges" too, made it look half unread, and sent it to
    # the slow reader for 6 seconds a snip on a friend's PC.
    dense = len("".join(str(text or "").split()))
    if lines is not None and img is not None and dense < SHORT_READING:
        try:
            share = _text_rows_covered(lines, img)
            if share is not None and share < 0.5:
                return True
        except Exception:
            pass
    return False


def _second_opinion(text, lines=None, img=None, source=None):
    """Whether Windows' reading needs another reader: "misread" when it
    is plainly rubbish, "unread" when a page it has no pack for may have
    gone unread, None when it stands.

    A second opinion used to mean only the cloud, so with no cloud key the
    rubbish was the answer - on a PC with only English and Italian packs a
    page of Chinese came back as "L-i*4Dfi7," although PaddleOCR, which
    reads Chinese on this computer, was installed and never asked."""
    if not text.strip():
        return "misread"
    try:
        if ocr_windows.looks_like_noise(text):
            return "misread"
    except Exception:
        pass
    # A small doubt - one odd word, a stray character - is worth asking the
    # cloud reader about when there is one (it answers in about a second),
    # but not this computer's slower reader: on a 4K screen that is 5-9
    # seconds a snip, for a reading of Latin text no better than Windows'
    # own. It is asked only where Windows may not have read the page at
    # all: a Chinese, Japanese or Korean page with no pack for it.
    if cloud_readers():
        try:
            if ocr_windows.might_be_misread(text):
                return "misread"
        except Exception:
            pass
    if not use_paddle() or _cjk_pack_installed():
        return None
    named = str(source or "auto").lower()[:2]
    if named in ("zh", "ja", "ko"):
        return None if _has_pack(named) else "misread"
    if named not in ("au", ""):
        return None               # a Latin language was named
    return "unread" if _looks_unread(text, lines, img) else None


def _has_pack(head):
    try:
        return any(str(t).lower().startswith(head)
                   for t in ocr_windows.available_languages())
    except Exception:
        return True


def _paddle_better(windows_text, paddle_text):
    """After an "unread" doubt: PaddleOCR's reading only if it found text
    in a script Windows could not read, or clearly more of it."""
    try:
        dense_w = len("".join(str(windows_text).split()))
        dense_p = len("".join(str(paddle_text).split()))
        if ocr_windows.script_chars(paddle_text) >= max(2, 0.3 * dense_p):
            return True
        return dense_p > 1.3 * dense_w
    except Exception:
        return True


STAMP_WAIT = 4.0      # longest a reading waits for the look for a stamp


def image_to_lines(img, lang=None, psm=6, source=None):
    """Positioned lines for the overlay, from whichever engine is in use.

    A watermark stamped across the page in a grid is looked for at the
    same time as the page is read, and when there is one the page is read
    again with it taken out (app/stamp.py): read with it, lines that
    crossed it came back broken and pieces of it were translated.
    """
    found = {}

    def look():
        try:
            from . import stamp
            found["grid"], found["whole"], found["box"] = stamp.grid_for(img)
        except Exception:
            found["grid"] = None
    looking = threading.Thread(target=look, daemon=True,
                               name="stamp-look")
    looking.start()
    lines, used = _image_to_lines(img, lang, psm, source)
    looking.join(STAMP_WAIT)
    if not found.get("grid"):
        return lines, used
    try:
        from . import stamp
        clean = stamp.cleaned(img, found["grid"], found.get("whole"),
                              found.get("box"))
        if clean is img:
            return lines, used
        again, used_again = _image_to_lines(clean, lang, psm, source)
        try:
            from .main import log
            log(stamp.describe() + "; read again: %d lines (were %d)"
                % (len(again), len(lines)))
        except Exception:
            pass
        if again:
            return again, used_again
    except Exception:
        pass
    return lines, used


def _image_to_lines(img, lang=None, psm=6, source=None):
    """One reading of `img` (see image_to_lines).

    `source` is the language the user chose in the app, if any. Passing it
    on matters: Vision will otherwise read one alphabet as another that
    looks like it, and report high confidence while doing so.
    """
    _note("")
    # A pinned choice is honoured before anything else is tried. Every one
    # of these hands the lines to _clean_lines on the way out — pinning a
    # reader chooses who reads the page, not whether the page is cleaned
    # afterwards, and two of these used to return straight past it.
    if prefer_cloud_vision() or prefer_gemini_ocr():
        for reader in cloud_readers():
            try:
                lines, used = reader.image_to_lines(img, source=source)
                if lines:
                    return _clean_lines(lines, img), used
            except Exception:
                pass
            _note(getattr(reader, "last_error", "") or _last_note)
    if use_vision():
        try:
            lines, used = ocr_vision.image_to_lines(img, source=source)
            if lines:
                return _clean_lines(lines, img), used
        except Exception:
            pass          # fall through
    windows_lines = None
    windows_text = ""
    windows_doubt = None
    if use_windows_ocr():
        try:
            started = time.time()
            lines, used = ocr_windows.image_to_lines(img, source=source)
            _step("windows", started)
            if lines:
                text = " ".join(line["text"] for line in lines)
                # Any sign of a misreading is worth a second opinion, not
                # just an overwhelming one: PaddleOCR on this computer
                # first, then the cloud if there is one.
                doubt = _second_opinion(text, lines, img, source)
                if doubt is None or not (use_paddle() or cloud_readers()):
                    _note(getattr(ocr_windows, "last_note", ""))
                    return _clean_lines(lines, img), used
                if getattr(_thread, "no_slow", False):
                    _thread.skipped = True
                    return _clean_lines(lines, img), used
                windows_lines = (lines, used)
                windows_text = text
                windows_doubt = doubt
        except Exception:
            pass          # fall through
    # Windows had no pack for this, or read nonsense: PaddleOCR, on this
    # computer, before anything is sent anywhere.
    if getattr(_thread, "no_slow", False) and use_paddle():
        _thread.skipped = True
        if windows_lines:
            return _clean_lines(windows_lines[0], img), windows_lines[1]
        return [], "skipped"
    if use_paddle() and _paddle_can_help(windows_text):
        started = time.time()
        got = _paddle_read(img, source, want_lines=True)
        _step("paddle", started)
        if got:
            lines, used, doubtful = got
            paddle_text = " ".join(line["text"] for line in lines)
            if windows_lines and windows_doubt == "unread" and \
                    not _paddle_better(windows_text, paddle_text):
                _note(getattr(ocr_windows, "last_note", ""))
                return _clean_lines(windows_lines[0], img), windows_lines[1]
            if not (doubtful and cloud_readers()):
                _note("")
                return _clean_lines(lines, img), used
            if windows_lines is None:
                windows_lines = (lines, used)
    for reader in cloud_readers():
        started = time.time()
        try:
            lines, used = reader.image_to_lines(img, source=source)
            _step(getattr(reader, "__name__", "cloud").split(".")[-1],
                  started)
            if lines:
                return _clean_lines(lines, img), used
        except Exception:
            _step("cloud failed", started)
        _note(getattr(reader, "last_error", "")
              or getattr(ocr_windows, "last_note", ""))
    if windows_lines:
        # Google could not improve on it, so the doubtful reading is still
        # the best there is. Better than nothing, with the reason attached.
        _note(getattr(ocr_windows, "last_note", ""))
        return _clean_lines(windows_lines[0], img), windows_lines[1]
    # Only if it has something to add: this runs after Google may already
    # have explained the failure, and an empty note would erase that.
    if use_windows_ocr() and getattr(ocr_windows, "last_note", ""):
        _note(ocr_windows.last_note)
    return _tesseract_lines(img, lang, psm, source=source)


# A gutter is a band of the page with no ink in it at all. Below this
# share of the busiest column it counts as empty — not zero, because a
# scan, a JPEG and an anti-aliased screenshot all leave a little dirt in
# a blank column.
GUTTER_INK = 0.04

# And it has to be wide enough to be a gutter rather than a word space.
# Measured against the page, so a wide page and a narrow one are judged
# the same way.
GUTTER_WIDTH = 0.012

# What is left between two gutters has to be wide enough to be a column.
# This is the rule that tells a magazine's gutter from the gap after a
# hanging "1.1", from the ragged left edge of a vertical watermark, and
# from ordinary wide word spacing.
#
# It used to be 0.18, which is a fifth of the page, and that is a rule
# about magazines rather than about screens. A news portal or a shop
# front page is five or six cards across; every column on it is under a
# fifth of the width, so every gutter was thrown away and a page laid
# out in columns was treated as prose running edge to edge. The reading
# that came back had the end of one caption welded to the start of
# another, and a translator handed a sentence made of two unrelated
# halves returns something that is nobody's sentence.
#
# It is 0.11 rather than lower because of the one rule it still has to
# enforce: six narrow cells across a table row are not six columns. A
# cell is a tenth of the page there, and that is the floor this sits on.
#
# It can be this low because nothing is cut on the strength of it alone:
# `_no_ink` checks the picture, on that line's own rows, before every
# single cut. A headline crossing the gutter has its own letters in the
# way and survives. The old value was buying with accuracy a safety the
# next check was already providing.
GUTTER_COLUMN = 0.11

# Gutters are looked for over horizontal bands rather than over the whole
# page, because that is how every newspaper is laid out: a full-width
# masthead, then three columns, then a two-column reference list. Over
# the whole page the masthead closes every gutter underneath it.
GUTTER_BANDS = 12


def _profile(page, top, bottom):
    """Ink per column of one horizontal band, as a list one entry wide."""
    width = page.size[0]
    band = page.crop((0, int(top), width, int(bottom)))
    return list(band.resize((width, 1), Image.BOX).tobytes())


def _blank_runs(profile, width):
    """The blank vertical runs wide enough to be gutters, edges dropped."""
    peak = max(profile) if profile else 0
    if not peak:
        return []
    least = peak * GUTTER_INK
    wide_enough = max(8, int(width * GUTTER_WIDTH))
    found, start = [], None
    for x, ink in enumerate(profile):
        if ink <= least:
            if start is None:
                start = x
        elif start is not None:
            if x - start >= wide_enough:
                found.append((start, x))
            start = None
    if start is not None and width - start >= wide_enough:
        found.append((start, width))
    # The runs at the two edges are the page margins, not gutters.
    return [(a, b) for a, b in found if a > 0 and b < width]


def _wide_enough_to_be_columns(gaps, left, right, width):
    """Drop the gaps that would leave a column too narrow to be one.

    Dropping the narrowest gap first, and then looking again, matters:
    the gaps between the cells of a table row are each a candidate, and
    removing one widens its neighbours, so a row of six cells collapses
    back to no gutters at all rather than to five bad ones.
    """
    least = width * GUTTER_COLUMN
    gaps = list(gaps)
    while gaps:
        starts = [left] + [b for a, b in gaps]
        ends = [a for a, b in gaps] + [right]
        widths = [end - start for start, end in zip(starts, ends)]
        worst = min(range(len(widths)), key=lambda i: widths[i])
        if widths[worst] >= least:
            break
        touching = [i for i in (worst - 1, worst) if 0 <= i < len(gaps)]
        gaps.pop(min(touching, key=lambda i: gaps[i][1] - gaps[i][0]))
    return gaps


def gutters(image, top=None, bottom=None):
    """The blank vertical bands of one horizontal slice of a page.

    `overlay.columns()` looks for gutters in the boxes the recogniser
    returned, and on a page in columns those boxes are the one thing that
    cannot be trusted: a line read straight across two columns covers the
    gutter, so the evidence that there *is* a gutter is destroyed by the
    very fault it would be used to find. On the three-column page in the
    corpus it reports no gutters at all.

    The picture does not have that problem. Ink either is or is not there,
    whatever the recogniser made of it, and on that same page this finds
    both gutters exactly — 304 to 331, and 578 to 605.
    """
    try:
        page = _inked(image)
        width, height = page.size
        top = 0 if top is None else max(0, int(top))
        bottom = height if bottom is None else min(height, int(bottom))
        if bottom - top < 8 or width < 40:
            return []
        return _gutters_of(page, top, bottom)
    except Exception:
        return []


def _inked(image):
    """The page as ink: bright where the writing is, dark where it is not.

    Which way round that is cannot be assumed. Half the screenshots this
    app is handed are dark mode, where the page is black and the letters
    are white, and inverting one of those turns the empty page into solid
    ink and every gutter in it disappears. The background is whatever
    most of the picture is — the median — so that decides.
    """
    from PIL import ImageOps, ImageStat
    grey = image.convert("L")
    try:
        background = ImageStat.Stat(grey).median[0]
    except Exception:
        background = 255
    return ImageOps.invert(grey) if background >= 128 else grey


def _gutters_of(page, top, bottom):
    width = page.size[0]
    profile = _profile(page, top, bottom)
    gaps = _blank_runs(profile, width)
    if not gaps:
        return []
    peak = max(profile)
    least = peak * GUTTER_INK
    inked = [x for x, ink in enumerate(profile) if ink > least]
    if not inked:
        return []
    return _wide_enough_to_be_columns(gaps, inked[0], inked[-1] + 1, width)


def _ink_extent(page, floor):
    """The first and last rows of the page that have anything on them."""
    width, height = page.size
    try:
        rows = list(page.resize((1, height), Image.BOX).tobytes())
    except Exception:
        return 0, height
    inked = [y for y, value in enumerate(rows) if value > floor]
    if not inked:
        return 0, height
    return inked[0], inked[-1] + 1


def _running_down_the_page(bands):
    """Keep only the gutters that continue into the band above or below.

    A column boundary runs down a page. A blank strip that appears in one
    band and nowhere else is a coincidence — the gap between two cells of
    one table row, the ragged right edge of a short paragraph, the space
    beside a heading — and treating it as a column cuts a sentence in half.

    That was happening, and worse than the false cut was the instability
    it caused. The same page snipped by hand twice is two crops a few
    pixels apart; a few pixels move a band boundary; a band boundary moves
    the evidence; and one page came back laid out three different ways in
    three attempts. Cutting text on evidence this thin makes the whole
    result unrepeatable, which reads as the app being unreliable rather
    than as one rule being too eager.

    Two adjacent bands is a low bar deliberately. A real two-column body
    spans most of the page's height and clears it easily; a table row is
    one band tall and does not.
    """
    kept = []
    for index, gutters_here in enumerate(bands):
        neighbours = []
        if index:
            neighbours.extend(bands[index - 1])
        if index + 1 < len(bands):
            neighbours.extend(bands[index + 1])
        kept.append([(a, b) for a, b in gutters_here
                     if any(a < other_b and other_a < b
                            for other_a, other_b in neighbours)])
    return kept


def split_at_gutters(lines, image):
    """Cut any line that was read straight across a gutter.

    A recogniser handed a page in columns will happily join the end of one
    column's line to the start of the next one's, because they sit on the
    same baseline and it has not been told there is a wall between them.
    What comes back is one box, one string, and two unrelated halves of two
    unrelated sentences — a fifth of the lines on the corpus's three-column
    page.

    Everything downstream inherits it. The box is wrong, so placement is
    wrong; the text is two halves of two sentences, so the translation is
    nonsense however good the engine; and the paragraph it belongs to can
    never be found because it is in two paragraphs at once.

    A headline is the case that has to survive. It crosses every gutter on
    the page and is supposed to, so cutting one would invent a column it is
    not in. Guessing from its width does not work — on a three-column page
    a line merged across all three columns is very nearly page-wide itself,
    which is how the first version of this quietly did nothing on the very
    page it was written for. So the picture is asked instead: a line only
    crosses a gutter if that rectangle of the page, on that line's own
    rows, has no ink in it. A headline has its own letters there.

    The text is divided where the box is divided. For Chinese, Japanese
    and Korean that is close to exact — every character is the same width —
    and for anything else it is an approximation that is still far better
    than leaving the two columns joined.
    """
    if not lines or image is None:
        return lines
    try:
        page = _inked(image)
        width, height = page.size
        if width < 40 or height < 40:
            return lines
        floor = max(_profile(page, 0, height)) * GUTTER_INK
        # Bands measured across the writing, not across the picture.
        #
        # A snip is drawn by hand, so the same page captured twice is two
        # crops a few pixels apart. Dividing the picture into twelve bands
        # moves every band boundary when the margin changes, which moves
        # what evidence each band sees, which changes what gets cut — and
        # one page came back laid out three different ways in three tries.
        # The words are in the same place both times; the margin around
        # them is not. So the bands are laid over the words.
        top, bottom = _ink_extent(page, floor)
        step = max(1.0, (bottom - top) / float(GUTTER_BANDS))
        bands = [(int(top + i * step), int(top + (i + 1) * step)) for i
                 in range(GUTTER_BANDS)]
        found = [_gutters_of(page, top, bottom) for top, bottom in bands]
        found = _running_down_the_page(found)
    except Exception:
        return lines

    # The page's own line height, for judging gaps inside a line: a box
    # swollen by something tall read into it (a rotated label, an icon)
    # would otherwise make every gap in it look like a word space.
    heights = sorted(int(l["box"][3]) for l in lines if l.get("box"))
    typical = heights[len(heights) // 2] if heights else 0
    out = []
    for line in lines:
        if line.get("quad"):
            # Text at an angle: its box is mostly empty page, which is not
            # a gutter.
            out.append(line)
            continue
        try:
            x, y, w, h = line["box"]
            text = str(line.get("text", ""))
            middle = y + h // 2
            gaps = []
            for index, (top, bottom) in enumerate(bands):
                if top <= middle < bottom:
                    gaps = found[index]
                    break
            crossed = [(a, b) for a, b in gaps if x < a and x + w > b
                       and _no_ink(page, a, b, y, h, floor)]
            # And a gap inside the line itself far wider than any space
            # between words - the edge of an infobox, a sidebar, the next
            # item of a toolbar set well apart - whether or not it runs
            # down the whole page as a gutter does.
            crossed = sorted(set(crossed) | set(
                _wide_gaps(page, x, y, w, min(h, typical or h), floor,
                           rows=h)))
            menu = _menu_gaps(page, x, y, w, min(h, typical or h),
                              floor, h, text)
            if menu:
                crossed = sorted(set(crossed) | set(menu))
            merged = []
            for a, b in crossed:
                if merged and a <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
                else:
                    merged.append((a, b))
            crossed = merged
        except Exception:
            out.append(line)
            continue
        if not crossed or not text.strip():
            out.append(line)
            continue
        out.extend(_cut(line, crossed, x, y, w, h, text))
    return out


# A blank run inside one line this many times its height is not a space
# between words: words sit a fraction of the height apart, items of a menu
# about one height, and neighbouring columns or panels further than this.
LINE_GAP = 2.5


def _wide_gaps(page, x, y, w, h, floor, rows=None, factor=None):
    """Blank runs inside a line's own box wider than LINE_GAP heights,
    as (start, end) - not counting blank at either end. `h` is the height
    to judge by; `rows` how many rows of the box to look at."""
    if w < 4 * h or h < 4:
        return []
    band = page.crop((int(x), max(0, int(y)), int(x + w),
                      int(y + (rows or h))))
    profile = list(band.resize((band.size[0], 1), Image.BOX).tobytes())
    blank = [v <= floor for v in profile]
    runs, start = [], None
    for i, empty in enumerate(blank + [False]):
        if empty and start is None:
            start = i
        elif not empty and start is not None:
            if start > 0 and i < len(blank) and \
                    i - start >= (factor or LINE_GAP) * h:
                runs.append((int(x) + start, int(x) + i))
            start = None
    return runs


# A row of menu items or tabs ("Startseite  Pflege  Ukraine  Inland ...")
# is read as one line and went to the engine as one sentence: "Care for
# Ukraine: Inside and Outside. Economy, Knowledge, ...". Items of a menu
# sit further apart than words; cut at those gaps only when every piece
# is a short label - a sentence never splits into those.
MENU_GAP = 0.6


def _menu_gaps(page, x, y, w, h, floor, rows, text):
    if " " not in text and not any(0x3000 <= ord(c) <= 0xD7AF for c in text):
        return []
    gaps = _wide_gaps(page, x, y, w, h, floor, rows=rows, factor=MENU_GAP)
    if len(gaps) < 2:
        return []
    pieces = _cut({"box": (x, y, w, rows), "text": text}, gaps, x, y, w,
                  rows, text)
    if len(pieces) < 3:
        return []
    for piece in pieces:
        t = piece["text"]
        cjk = sum(1 for c in t if 0x3040 <= ord(c) <= 0x9FFF
                  or 0xAC00 <= ord(c) <= 0xD7AF)
        if (cjk and len(t.replace(" ", "")) > 8) or \
                (not cjk and (len(t.split()) > 3 or len(t) > 24)):
            return []
    return gaps


def _no_ink(page, a, b, y, h, floor):
    """Is this rectangle of the page empty? The question that separates a
    line lying across a gutter from a headline written over one.

    Averaged, not the darkest pixel in it, and against the same "this
    little ink counts as empty" line the gutters themselves were found
    with. A screenshot is anti-aliased and a photograph is dirty; asking
    for a rectangle with not one dark pixel in it would be asking for
    something real pages do not have, and the whole cut would quietly
    never happen.
    """
    try:
        from PIL import ImageStat
        patch = page.crop((int(a), max(0, int(y)), int(b), int(y + h)))
        return ImageStat.Stat(patch).mean[0] <= floor
    except Exception:
        return False


def _cut(line, crossed, x, y, w, h, text):
    """One merged line, as the several lines it should have been."""
    pieces, taken, left = [], 0, x
    # The writing is only where the gaps are not: shares are measured along
    # the written part of the line, so a wide gap does not count as text.
    written = max(1.0, w - sum(b - a for a, b in crossed))
    before = 0
    for a, b in crossed:
        # Where the gutter falls along the line, as a share of its writing,
        # and so where it falls along the text.
        share = (a - x - before) / written if w else 0
        before += b - a
        cut = max(taken + 1, min(len(text) - 1, int(round(len(text) * share))))
        # At the nearest space, in a language that has them: the share is an
        # estimate, and a word cut in two is two wrong words.
        if " " in text[taken:]:
            spaces = [i for i, c in enumerate(text) if c == " " and i > taken]
            if spaces:
                cut = min(spaces, key=lambda i: abs(i - cut))
        part = dict(line)
        part["box"] = (left, y, max(1, a - left), h)
        part["text"] = text[taken:cut].strip()
        if part["text"]:
            pieces.append(part)
        taken, left = cut, b
    last = dict(line)
    last["box"] = (left, y, max(1, x + w - left), h)
    last["text"] = text[taken:].strip()
    if last["text"]:
        pieces.append(last)
    return pieces or [line]


def is_debris(text):
    """Marks with no word in them: strokes and quotes read off a picture.

    Three or more separate marks, none with a run of three letters, most
    of them not letters, and no number or real script character among
    them. A lone mark ("•", "a)", "z.B.") is never debris: it may be a
    list marker or an abbreviation."""
    tokens = str(text or "").split()
    if len(tokens) < 3:
        return False
    dense = "".join(tokens)
    if any(c.isdigit() for c in dense):
        return False
    if any(c.isalpha() and ord(c) > 0x024F for c in dense):
        return False
    run = longest = 0
    for c in dense:
        run = run + 1 if c.isalpha() else 0
        longest = max(longest, run)
    if longest >= 3:
        return False
    letters = sum(1 for c in dense if c.isalpha())
    return letters * 2 <= len(dense)


STRAY_SHARE = 0.8         # the page's own script is at least this much
STRAY_BUSY = 0.5          # and a stray line sits on a background this busy


def drop_stray_script(lines, image):
    """Lines in a script the rest of the page is not written in, sitting
    on a picture, left out: they are a reader seeing letters in a photo."""
    if image is None or len(lines) < 3:
        return lines
    from . import langid, overlay
    total, per = {}, []
    for line in lines:
        counts = langid.scripts(line.get("text", ""))
        per.append(counts)
        for name, n in counts.items():
            total[name] = total.get(name, 0) + n
    letters = sum(total.values())
    if not letters:
        return lines
    main, most = max(total.items(), key=lambda kv: kv[1])
    if most < STRAY_SHARE * letters:
        return lines
    out = []
    for line, counts in zip(lines, per):
        own = sum(counts.values())
        if own and counts.get(main, 0) < 0.5 * own:
            busy = overlay._busy_around(image, line["box"])
            if busy is not None and busy >= STRAY_BUSY:
                continue
        out.append(line)
    return out


def _clean_lines(lines, image=None):
    """Drop the page furniture nobody wants translated, and settle the
    spacing before anything downstream reads the text.

    Watermarks are the case this exists for: read correctly, translated
    correctly, and then drawn straight across the sentence underneath.

    The spacing joined it later, for a reason worth writing down. Chinese,
    Japanese and Korean are not written with spaces between words, but a
    recogniser hands back one box per glyph and something has to join
    them — and every recogniser does it slightly differently. Tesseract's
    output went through `clean`, which calls `strip_cjk_spaces`. The other
    four readers did not, so on a Mac (Apple Vision) or a PC (Windows OCR)
    the text could arrive as "享 界 G9".

    Nothing about that is visible. It translates the same, it draws the
    same, and it looks right on screen. What it silently breaks is every
    exact match downstream: the glossary asks whether "享界" is in the
    text, and in "享 界 G9" it is not. So a marque that was written down,
    tested and shipped simply never fired for the people using the two
    readers this app leads with — the ones on Tesseract were the only ones
    it ever worked for.

    That is the third time a step has been missing from some of the ways a
    page can be read, after the watermark filter and wrapped lines. It is
    settled here because here is the one place all five of them pass
    through on the way out.
    """
    try:
        for line in lines:
            text = line.get("text")
            if text:
                line["text"] = close_digit_joins(strip_cjk_spaces(text))
    except Exception:
        pass
    # Specks read off a photo or a texture - '| "If | "If' on a cyclist's
    # jacket - are not text: nothing is translated or drawn for them.
    try:
        lines = [line for line in lines
                 if not is_debris(line.get("text", ""))]
    except Exception:
        pass
    # Writing in another script, read off a photograph on a page in one
    # script: the reader that knows several (Windows with Japanese and
    # Korean packs) reads grass and a tent as "Bengneng'ya Kangtung" and
    # "Suei Ti Bu Min", which were then translated and drawn over the
    # photograph.
    try:
        lines = drop_stray_script(lines, image)
    except Exception:
        pass
    # Before the watermark filter, because a line read across two columns
    # is two lines and either half may be the watermark.
    try:
        lines = split_at_gutters(lines, image)
    except Exception:
        pass
    # Which lines this page sets in bold. No recogniser reports weight, so
    # it is measured off the picture — and this is the one place all five
    # of them pass through with the picture still in hand.
    try:
        from . import overlay
        lines = overlay.weigh_lines(lines, image)
    except Exception:
        pass
    # And which of them are printed on a picture rather than on a page.
    # Those are left exactly as they are: see `overlay.mark_pictures`.
    try:
        from . import config as _config
        if not _config.CONFIG.get("translate_pictures", True):
            from . import overlay
            lines = overlay.mark_pictures(lines, image)
    except Exception:
        pass
    try:
        from . import watermark
        keep, dropped = watermark.strip(lines, image)
        if dropped:
            _note(_last_note or (
                "%d watermark line%s ignored." %
                (len(dropped), "" if len(dropped) == 1 else "s")))
        return keep
    except Exception:
        return lines


def _tesseract_lines(img, lang=None, psm=6, source=None):
    """Like image_to_text, but returns positioned lines for overlay drawing.

    Reuses the same sizing and script decisions, then keeps the word boxes
    from the winning pass instead of throwing them away.

    `source` is the language named in the app. When there is one, it
    settles the script outright — no measuring pass to seed a guess, no
    search through the common scripts, and above all no carrying over
    whatever the last snip happened to be. Every other reader was told;
    this one was not, which is how a page the user had labelled Chinese
    could be read with the Korean model because the snip before it was
    Korean.
    """
    ensure_ready()
    base = preprocess(img, 1.0)
    named = script_for_source(source)
    if named and lang in (None, "", "auto"):
        try:
            lang = langs_for_script(named)
        except OcrError:
            lang = None
    sizing_script, sizing_lang = _sizing_choice()
    if named:
        sizing_script = named
        sizing_lang = lang or sizing_lang
    probe = _bakeoff_sample(base, MEASURE_PIXELS)
    probe_scale = (probe.size[0] / float(base.size[0])) if base.size[0] else 1.0
    cfg = "--oem 1 --psm %d" % psm

    try:
        data = pytesseract.image_to_data(
            probe, lang=sizing_lang, config=cfg,
            output_type=pytesseract.Output.DICT)
    except Exception as exc:
        raise OcrError("OCR failed: %s" % exc)

    confs, heights = [], []
    for i, word in enumerate(data["text"]):
        if word.strip():
            try:
                c = float(data["conf"][i])
            except (TypeError, ValueError):
                continue
            if c >= 0:
                confs.append(c)
                heights.append(int(data["height"][i]))
    conf = sum(confs) / len(confs) if confs else 0.0
    median_h = _median(heights) / max(1e-6, probe_scale)

    ceiling = float(config.CONFIG.get("ocr_upscale", 3.0) or 3.0)
    hint = 1.0
    if median_h and median_h < UPSCALE_BELOW_PX:
        hint = min(max(TARGET_TEXT_PX / float(median_h), 1.0), ceiling)

    if lang in (None, "", "auto"):
        if conf >= SCRIPT_CONFIDENT and len(confs) >= 3:
            lang = langs_for_script(sizing_script)
        else:
            work = base if hint <= 1.25 else preprocess(img, hint)
            lang = langs_for_script(
                choose_script(base, work, sizing_script, conf,
                              _weighted(conf, len(confs)), psm))

    # The measuring pass can be reused as the answer, but only when it
    # looked at the whole page. It is a band of the page when the page is
    # large, and returning that band's lines would silently drop everything
    # above and below it — a page translated from the waist up. Judged by
    # whether the probe *is* the whole image rather than by a scale factor,
    # because a band and a full-size image have the same scale factor and
    # that is exactly how this would be got wrong.
    whole_page = probe.size == base.size
    if conf >= SCRIPT_CONFIDENT and hint <= 1.25 and whole_page \
            and lang == sizing_lang:
        return _clean_lines(lines_from_data(data, 1.0), img), lang

    scale = hint if hint > 1.25 else 1.0
    work = preprocess(img, scale) if scale > 1.25 else base
    try:
        data = pytesseract.image_to_data(
            work, lang=lang, config=cfg,
            output_type=pytesseract.Output.DICT)
    except Exception as exc:
        raise OcrError("OCR failed: %s" % exc)
    # Through the same cleaning as every other reader. This was the one
    # path that returned straight to the caller, so on a machine with
    # neither the built-in reader nor a cloud key — which is the plainest
    # install there is — watermarks were never filtered at all, and the
    # feature looked as though it worked on some machines and not others.
    return _clean_lines(lines_from_data(data, scale), img), lang


def _text_from_data(data):
    """Rebuild the page text from image_to_data output.

    Tesseract's own `image_to_string` would do this, but it means a second
    process launch, and each launch reloads the language model — the single
    biggest cost in a snip. The layout fields in the data pass carry the same
    structure, so the text can be reassembled from the pass already made.
    """
    lines, current, key = [], [], None
    for i, word in enumerate(data["text"]):
        if not word.strip():
            continue
        here = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        if key is not None and here[:2] != key[:2]:
            if current:
                lines.append(" ".join(current))
                current = []
            lines.append("")                # paragraph break
        elif key is not None and here != key:
            if current:
                lines.append(" ".join(current))
                current = []
        current.append(word)
        key = here
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)


def _run(img, lang, psm, want_text=True):
    """One OCR pass. Returns (text, mean_confidence, word_count, heights)."""
    cfg = "--oem 1 --psm %d" % psm
    data = pytesseract.image_to_data(
        img, lang=lang, config=cfg, output_type=pytesseract.Output.DICT)
    confs, heights, words = [], [], []
    for i, word in enumerate(data["text"]):
        if not word.strip():
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            continue
        if conf < 0:
            continue
        confs.append(conf)
        heights.append(int(data["height"][i]))
        words.append(word)
    mean_conf = sum(confs) / len(confs) if confs else 0.0
    text = _text_from_data(data) if want_text else ""
    return text, mean_conf, len(words), heights


def _median(values):
    if not values:
        return 0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


#: What script a language is written in, for the one question the reader
#: actually has to answer. The app already knows the language when the
#: user has named it, and a reader guessing at the alphabet of a page
#: somebody has just told it the language of is the whole of this bug:
#: a Chinese page came back with Korean glyphs in it because nothing
#: downstream of that choice was ever told.
SOURCE_SCRIPT = {
    "zh": "HanS", "zh-CN": "HanS", "zh-Hans": "HanS",
    "zh-TW": "HanT", "zh-Hant": "HanT", "zh-HK": "HanT",
    "ja": "Japanese", "ko": "Korean",
    "ru": "Cyrillic", "uk": "Cyrillic", "bg": "Cyrillic", "sr": "Cyrillic",
    "el": "Greek", "ar": "Arabic", "fa": "Arabic", "ur": "Arabic",
    "he": "Hebrew", "iw": "Hebrew",
    "hi": "Devanagari", "mr": "Devanagari", "ne": "Devanagari",
    "bn": "Bengali", "ta": "Tamil", "te": "Telugu", "th": "Thai",
}


def script_for_source(source):
    """The script a named source language is written in, or None.

    None for anything Latin and for 'auto': a Latin page needs no
    constraining, and saying nothing is the honest answer to a language
    nobody has named.
    """
    code = str(source or "").strip()
    if not code or code.lower() in ("auto", "detect"):
        return None
    script = SOURCE_SCRIPT.get(code)
    if script is None:
        script = SOURCE_SCRIPT.get(code.split("-")[0])
    return script


def _sizing_choice():
    """(script, model) used for the measuring pass.

    The measuring pass has to use *some* model, so it may as well use the one
    most likely to be right: whatever won last time, else Latin. That makes
    the measurement double as a candidate score, and ordinary repeat snips
    need no script search at all.
    """
    have = installed_packs() - {"osd"}
    if _last_script:
        for pack in SCRIPT_TO_TESS.get(_last_script, []):
            if pack in have:
                return _last_script, pack
    for pack in ("Latin", "eng", "deu", "fra", "spa"):
        if pack in have:
            return "Latin", pack
    return None, (sorted(have)[0] if have else "eng")


def detect_script(img, min_conf=0.5):
    """Returns a Tesseract script name ('Latin', 'Han', ...) or None.

    OSD below the confidence floor is noise, not a guess worth keeping — it
    will cheerfully label a line of German 'Arabic'.
    """
    if "osd" not in installed_packs():
        return None
    try:
        osd = pytesseract.image_to_osd(
            img, config="--psm 0 -c min_characters_to_try=8")
    except Exception:
        return None
    script, conf = None, 0.0
    for line in osd.splitlines():
        if line.startswith("Script:"):
            script = line.split(":", 1)[1].strip()
        elif line.startswith("Script confidence:"):
            try:
                conf = float(line.split(":", 1)[1].strip())
            except ValueError:
                conf = 0.0
    if script and conf >= min_conf:
        return script
    return None


def _bakeoff_sample(img, max_pixels=400_000):
    """A smaller piece of the image for comparing models, at full size.

    Less of the page, not a smaller copy of it. That distinction is the
    whole of this function and it decided which language a page was read
    in.

    The old version shrank the whole image to fit a pixel budget. What is
    being compared here is how well each model reads *glyphs*, so shrinking
    the glyphs changes the answer — and it changes it most for the scripts
    that need the resolution most. Measured on a page of Chinese: at full
    size the Chinese model scores 92.6 against Latin's 38.9 and wins
    outright; shrunk to the same pixel budget it scores 25.9 against
    Latin's 29.7 and *loses*. The page was then read with a Latin model,
    which returns confident nonsense rather than an error, and the nonsense
    was translated and drawn over the page.

    So take a band of the page at its own resolution instead — the band
    with the most ink in it, because a strip of margin says nothing about
    any model. Same cost, and the thing being measured survives. Measured
    again over six pages in six languages, the correct model now wins every
    one of them, and wins by two to three times rather than by a few
    points.

    A band also means heights measured on it are the page's real heights,
    with no scale to undo.
    """
    w, h = img.size
    if w * h <= max_pixels:
        return img
    tall = max(1, int(max_pixels // max(1, w)))
    if tall >= h:
        return img
    try:
        grey = img.convert("L")
        # Ink is dark, so invert and the busiest rows are the brightest.
        column = ImageOps.invert(grey).resize((1, h), Image.BOX)
        rows = list(column.getdata())
    except Exception:
        return img.crop((0, max(0, (h - tall) // 2), w,
                         max(0, (h - tall) // 2) + tall))
    # The densest window of `tall` rows, found by sliding a running total
    # rather than re-adding the window at every position.
    run = sum(rows[:tall])
    best, score = 0, run
    for y in range(1, h - tall):
        run += rows[y + tall - 1] - rows[y - 1]
        if run > score:
            best, score = y, run
    return img.crop((0, best, w, best + tall))


# A measuring pass this confident has already identified the script; below
# it, the script is worth investigating properly.
SCRIPT_CONFIDENT = 80.0
GOOD_ENOUGH = 90.0
COMMON_SCRIPTS = ["Cyrillic", "Japanese", "HanS", "Hangul", "Arabic",
                  "Devanagari", "HanT", "Greek", "Hebrew", "Thai"]

# People usually snip the same language several times in a row, so the last
# script that won is tried first next time.
_last_script = None


def _weighted(conf, words):
    """Confidence alone would reward a model that reads two characters very
    surely, so weight it by how much text the model actually found."""
    if not words:
        return -1.0
    return conf * (1.0 + min(words, 60) / 120.0)


def _score(img, model, psm):
    """How well one model reads this image. Higher is better; -1 on failure."""
    try:
        _t, conf, words, _h = _run(img, model, psm, want_text=False)
    except Exception:
        return -1.0
    return _weighted(conf, words)


def choose_script(base, work, seed_script=None, seed_conf=0.0,
                  seed_score=0.0, psm=6):
    """Decide which script model to read this image with.

    OSD is treated as a hint, not an answer: it labels plain German 'Arabic'
    and plain Russian 'Latin' with total consistency across magnifications,
    so a cross-scale vote does not save it. What does work is running the
    candidate models and comparing how confidently each reads the image —
    that ordering is sharp (95 vs 53 on the same line of text).

    Latin text costs nothing extra: the sizing pass already scored the Latin
    model, so a confident result there ends the search immediately.

    Every candidate is scored on the same piece of the page, the seed
    included. It was not: the seed's score arrived from the measuring pass,
    which reads a different piece of the page at a different size, and the
    candidates were then asked to beat a number that had never been
    measured against them. Two scores from two images are not a comparison,
    and the seed is always Latin, so the bias ran one way.
    """
    global _last_script
    if seed_script and seed_conf >= SCRIPT_CONFIDENT:
        _last_script = seed_script
        return seed_script

    have = installed_packs()
    sample = _bakeoff_sample(work)
    state = {"best": seed_script, "score": seed_score, "tried": set()}
    if seed_script:
        state["tried"].add(seed_script)
        try:
            state["score"] = _score(
                sample, langs_for_script(seed_script, allow_download=False),
                psm)
        except OcrError:
            pass

    def consider(scripts):
        """Score these candidates; True once one is clearly good enough."""
        for script in scripts:
            if not script or script in state["tried"]:
                continue
            state["tried"].add(script)
            try:
                model = langs_for_script(script, allow_download=False)
            except OcrError:
                continue
            score = _score(sample, model, psm)
            if score > state["score"]:
                state["best"], state["score"] = script, score
            if state["score"] >= GOOD_ENOUGH:
                return True
        return False

    # Tiers, cheapest first. Whoever snips German twice in a row should not
    # pay for orientation detection the second time.
    done = consider([_last_script])
    if not done:
        done = consider([detect_script(work), detect_script(base)])
    if not done:
        consider([s for s in COMMON_SCRIPTS
                  if any(p in have for p in SCRIPT_TO_TESS.get(s, []))][:6])

    _last_script = state["best"] or "Latin"
    return state["best"]     # None -> caller falls back to Latin


def langs_for_script(script, allow_download=True):
    """Pick the Tesseract model for a detected script.

    An unknown script falls back to Latin rather than to English: Latin is
    overwhelmingly the common case, and English alone is exactly what strips
    accents and umlauts off everything else written in the same alphabet.
    """
    have = installed_packs()
    wanted = SCRIPT_TO_TESS.get(script or "", []) or SCRIPT_TO_TESS["Latin"]
    for pack in wanted:
        if pack in have:
            return pack
    if allow_download:
        for pack in wanted:
            if download_pack(pack):
                return pack
    # Nothing for this script - use whatever is installed rather than fail.
    for pack in ("Latin", "eng"):
        if pack in have:
            return pack
    remaining = sorted(have - {"osd"})
    if not remaining:
        raise OcrError("no OCR language packs are installed")
    return remaining[0]


def _scale_ladder(img, median_h, ceiling):
    """Which magnifications are worth trying for this image.

    Big images are already expensive and rarely need help; small ones are
    where OCR lives or dies, so they get a proper search. The measured text
    height picks the starting point, but it is only a hint — on unreadable
    input the measurement is unreliable, which is exactly when the search
    matters most.
    """
    pixels = img.size[0] * img.size[1]
    hint = 1.0
    if median_h:
        hint = min(max(TARGET_TEXT_PX / float(median_h), 1.0), ceiling)

    if pixels > 4_000_000:                 # full-screen grab or 300dpi page
        return [1.0] if hint < 1.4 else [1.0, min(hint, 1.5)]
    if pixels > 1_200_000:
        return sorted({1.0, round(min(hint, 2.0), 2)})
    ladder = {1.0, round(hint, 2)}
    if hint > 1.4 or median_h == 0:
        ladder.update({2.0, 3.0})
    return sorted(s for s in ladder if 1.0 <= s <= max(1.0, ceiling))


def image_to_text(img, lang=None, psm=6, source=None):
    """OCR a PIL image, using the best engine available on this platform."""
    _note("")
    if prefer_cloud_vision() or prefer_gemini_ocr():
        for reader in cloud_readers():
            try:
                text, used = reader.image_to_text(img, source=source)
                if text.strip():
                    return clean(text), used
            except Exception:
                pass
            _note(getattr(reader, "last_error", "") or _last_note)
    if use_vision():
        try:
            text, used = ocr_vision.image_to_text(img, source=source)
            if text.strip():
                return clean(text), used
        except Exception:
            pass          # fall through
    doubtful = None
    text_doubt = None
    if use_windows_ocr():
        try:
            text, used = ocr_windows.image_to_text(img, source=source)
            # A reading the machine cannot make sense of is not an answer.
            # Sending it on to be translated is how "iRERJXIJXFL8Y" ended
            # up on screen; better to ask something that can read it.
            if text.strip():
                doubt = _second_opinion(text, None, None, source)
                if doubt is None or not (use_paddle() or cloud_readers()):
                    _note(getattr(ocr_windows, "last_note", ""))
                    return clean(text), used
                doubtful = (clean(text), used)
                text_doubt = doubt
        except Exception:
            pass          # fall through
    if use_paddle() and _paddle_can_help(doubtful[0] if doubtful else ""):
        got = _paddle_read(img, source, want_lines=False)
        if got:
            text, used, unsure = got
            if doubtful and text_doubt == "unread" and \
                    not _paddle_better(doubtful[0], text):
                _note(getattr(ocr_windows, "last_note", ""))
                return doubtful
            if not (unsure and cloud_readers()):
                _note("")
                return clean(text), used
            if doubtful is None:
                doubtful = (clean(text), used)
    for reader in cloud_readers():
        try:
            text, used = reader.image_to_text(img, source=source)
            if text.strip():
                return clean(text), used
        except Exception:
            pass
        _note(getattr(reader, "last_error", "")
              or getattr(ocr_windows, "last_note", ""))
    if doubtful:
        _note(getattr(ocr_windows, "last_note", ""))
        return doubtful
    if use_windows_ocr() and getattr(ocr_windows, "last_note", ""):
        _note(ocr_windows.last_note)
    return _tesseract_text(img, lang, psm, source=source)


def _tesseract_text(img, lang=None, psm=6, source=None):
    """OCR a PIL image, sizing and language chosen automatically.

    `source`, when the user has named one, settles the script before any
    of the measuring and searching below — see `_tesseract_lines`.

    The measuring pass runs on a downscaled copy — word *heights* survive
    downscaling, and that is all it is measuring, so it costs a fraction of
    a full pass. When that pass is already confident (ordinary Latin text,
    which is most snips) the scale it implies is used directly and the whole
    magnification search and script run-off are skipped: two Tesseract calls
    instead of five or six.
    """
    ensure_ready()
    base = preprocess(img, 1.0)
    named = script_for_source(source)
    if named and lang in (None, "", "auto"):
        try:
            lang = langs_for_script(named)
        except OcrError:
            lang = None
    sizing_script, sizing_lang = _sizing_choice()
    if named:
        sizing_script = named
        sizing_lang = lang or sizing_lang

    # 1. measure, cheaply
    probe = _bakeoff_sample(base, MEASURE_PIXELS)
    downscaled = probe is not base
    probe_ratio = (base.size[0] / float(probe.size[0])) if probe.size[0] else 1.0
    try:
        probe_text, base_conf, words, heights = _run(probe, sizing_lang, psm)
    except Exception as exc:
        raise OcrError("OCR failed: %s" % exc)
    median_h = _median(heights) * probe_ratio

    ceiling = float(config.CONFIG.get("ocr_upscale", 3.0) or 3.0)
    hint = 1.0
    if median_h and median_h < UPSCALE_BELOW_PX:
        hint = min(max(TARGET_TEXT_PX / float(median_h), 1.0), ceiling)

    # 2. fast path — only when the text is already big enough to read.
    #
    # Confidence being high is not enough on its own: once an image needs
    # enlarging, *how much* it is enlarged decides whether diacritics
    # survive, and a single computed guess gets that wrong often enough to
    # matter (10px German loses its umlauts). Small text goes the long way
    # round and has the scale chosen by measurement instead.
    if base_conf >= SCRIPT_CONFIDENT and words >= 3 and hint <= 1.25:
        if lang in (None, "", "auto"):
            lang = langs_for_script(sizing_script)
        if not downscaled:
            return clean(probe_text), lang
        return _finish(base, lang, psm)

    # 3. slow path: search magnifications, then settle the script
    best_scale, best_conf, best_words = 1.0, base_conf, words
    for scale in _scale_ladder(img, median_h, ceiling):
        if scale <= 1.01:
            continue
        try:
            _t2, conf, n_words, _h2 = _run(preprocess(img, scale),
                                           sizing_lang, psm, want_text=False)
        except Exception:
            continue
        # More words found beats a marginally higher confidence: a pass that
        # reads nothing can be very confident about the nothing it read.
        if n_words > best_words * 1.15 or (
                n_words >= best_words * 0.9 and conf > best_conf + 1.0):
            best_scale, best_conf, best_words = scale, conf, n_words
        if best_conf >= 88.0:
            break

    work = base if best_scale <= 1.01 else preprocess(img, best_scale)

    if lang in (None, "", "auto"):
        lang = langs_for_script(choose_script(
            base, work, sizing_script, best_conf,
            _weighted(best_conf, best_words), psm))

    return _finish(work, lang, psm)


def _finish(work, lang, psm):
    try:
        text, _conf, _n, _h = _run(work, lang, psm)
    except Exception as exc:
        raise OcrError("OCR failed: %s" % exc)
    return clean(text), lang


def _is_cjk(ch):
    code = ord(ch)
    return (0x3040 <= code <= 0x30FF        # kana
            or 0x3400 <= code <= 0x4DBF     # CJK ext A
            or 0x4E00 <= code <= 0x9FFF     # CJK unified
            or 0xF900 <= code <= 0xFAFF     # compatibility
            or 0xAC00 <= code <= 0xD7AF     # hangul syllables
            or 0x3000 <= code <= 0x303F)    # CJK punctuation


def strip_cjk_spaces(text):
    """Drop the spaces Tesseract inserts between CJK characters.

    Chinese, Japanese and Korean are not written with spaces between words,
    so the gaps are an artefact of tokenisation - and they degrade the
    translation as well as the display.
    """
    out = []
    for i, ch in enumerate(text):
        if ch == " " and 0 < i < len(text) - 1:
            if _is_cjk(text[i - 1]) and _is_cjk(text[i + 1]):
                continue
        out.append(ch)
    return "".join(out)


_DIGIT_JOIN = re.compile(r"(?<=\d)[ \t]*([-–:~～])[ \t]*(?=\d)")


def close_digit_joins(text):
    """010 - 12345678 back to 010-12345678, on a CJK line.

    A reader that returns one box per word hands back the hyphen in a
    telephone number, or the colon in a time, as a word of its own, and
    the words are joined with spaces. On a Chinese, Japanese or Korean
    line nobody writes a space there, so the spaces are the reader's, not
    the page's — and they matter: the number is protected by being found
    in the source exactly as written, and "010 - 12345678" is exactly what
    was put back.

    Only on a CJK line. On a Latin page "pages 5 - 7" may be how the page
    set it, and a reader that returns words there returns "010-12345678"
    as one word anyway.
    """
    text = str(text or "")
    if not any(_is_cjk(ch) for ch in text):
        return text
    # A full-width colon or dash between digits is a time or a number
    # written in a Chinese font, not punctuation: 07：00, 027－8430. Made
    # ASCII here so the time and number repairs recognise them.
    text = re.sub(r"(?<=\d)\s*[：]\s*(?=\d)", ":", text)
    text = re.sub(r"(?<=\d)\s*[－—–]\s*(?=\d)", "-", text)
    return _DIGIT_JOIN.sub(r"\1", text)


def clean(text):
    """Join hard-wrapped lines into paragraphs; drop OCR noise lines."""
    lines = [ln.rstrip() for ln in (text or "").splitlines()]
    out, buf = [], []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if buf:
                out.append(" ".join(buf))
                buf = []
            continue
        # A line of pure punctuation/noise is almost never real text.
        letters = sum(ch.isalnum() for ch in stripped)
        if letters == 0 and len(stripped) < 4:
            continue
        if buf and buf[-1].endswith("-") and len(buf[-1]) > 1:
            buf[-1] = buf[-1][:-1] + stripped
        else:
            buf.append(stripped)
    if buf:
        out.append(" ".join(buf))
    return strip_cjk_spaces("\n\n".join(out).strip())
