"""PaddleOCR, on this computer, for the languages Windows cannot read.

Windows reads only the languages it has packs for, a pack needs
administrator rights and minutes to install, and a Windows OCR asked to read
a language it has no pack for does not fail: it returns confident Latin
junk. Until now the answer to that was the cloud — Google Cloud Vision or
Gemini — which spends an allowance on every snip and needs a key before
anything works at all.

PaddleOCR is Baidu's open-source reader (Apache 2.0), run here through
RapidOCR on ONNX Runtime: no GPU, no internet, no key. Its default model
reads Chinese (simplified and traditional), Japanese and English in one
pass, and is among the best there is at Chinese. Korean has a model of its
own, fetched the first time a Korean page is read.

It runs after Windows' own reader and before the cloud: Windows first where
it has the pack, because it is already loaded and quick; this when Windows
has nothing or reads nonsense; the cloud only when this cannot either.
"""
import threading

from . import platform_util

last_note = ""

# Below this a line is more likely noise than text.
MIN_SCORE = 0.5

_lock = threading.Lock()
_engines = {}
_import_error = None

try:                                   # pragma: no cover - depends on install
    import rapidocr as _rapidocr       # noqa: F401
    AVAILABLE = True
except Exception as exc:               # pragma: no cover
    AVAILABLE = False
    _import_error = exc


def available():
    return AVAILABLE


def _model_for(source):
    """Which recogniser: the default one, or Korean's."""
    tag = str(source or "").lower()
    if tag.startswith("ko"):
        return "korean"
    return "default"


def _engine(model):
    """One loaded engine per model, built on first use and kept."""
    with _lock:
        engine = _engines.get(model)
        if engine is not None:
            return engine
        from rapidocr import RapidOCR
        params = {}
        try:
            # Quiet: RapidOCR logs every model it loads, at INFO.
            params["Global.log_level"] = "error"
        except Exception:
            pass
        if model == "korean":
            from rapidocr import LangRec, ModelType, OCRVersion
            params.update({"Rec.lang_type": LangRec.KOREAN,
                           "Rec.ocr_version": OCRVersion.PPOCRV5,
                           "Rec.model_type": ModelType.MOBILE})
        try:
            engine = RapidOCR(params=params)
        except Exception:
            params.pop("Global.log_level", None)
            engine = RapidOCR(params=params)
        _engines[model] = engine
        return engine


def prefetch():
    """Fetch and load the models that do not come with the reader, now,
    in the background, so no page waits for one.

    The reader's own model reads Chinese, Japanese and Latin-script text
    with its accents; Korean has a model of its own that is fetched the
    first time it is needed. Fetched here instead, after an update or on
    first start, it is on the computer before the first Korean page - and
    that page then reads offline like the rest. A fetch that fails (no
    network) is tried again on the next start."""
    if not AVAILABLE:
        return False
    try:
        _engine("korean")
        return True
    except Exception:
        return False


def _box(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    left, top = int(min(xs)), int(min(ys))
    return (left, top, int(max(xs)) - left, int(max(ys)) - top)


def _angle(points):
    """The slope of the top edge, in degrees, as the other readers give."""
    import math
    (x0, y0), (x1, y1) = points[0], points[1]
    if x1 == x0:
        return 0.0
    return math.degrees(math.atan2(y1 - y0, x1 - x0))


def _read(image, model):
    engine = _engine(model)
    result = engine(image.convert("RGB"))
    boxes = getattr(result, "boxes", None)
    texts = getattr(result, "txts", None) or ()
    scores = getattr(result, "scores", None) or ()
    lines = []
    if boxes is None:
        return lines
    for points, text, score in zip(boxes, texts, scores):
        text = str(text or "").strip()
        if not text or float(score) < MIN_SCORE:
            continue
        points = [(float(x), float(y)) for x, y in points]
        line = {"text": text, "box": _box(points),
                "angle": _angle(points), "conf": float(score)}
        # Written at an angle: its own corners, to be translated and drawn
        # at that angle (see app/slant.py). Level lines are unchanged.
        try:
            from . import slant
            slant.attach(line, points)
        except Exception:
            pass
        lines.append(line)
    # Top to bottom, then left to right, the order every other reader
    # hands lines over in.
    lines.sort(key=lambda line: (line["box"][1] + line["box"][3] / 2.0,
                                 line["box"][0]))
    return lines


def image_to_lines(image, source=None):
    """Positioned lines, and the name of what read them."""
    global last_note
    last_note = ""
    if not AVAILABLE:
        last_note = "PaddleOCR is not installed."
        return [], "PaddleOCR"
    model = _model_for(source)
    try:
        lines = _read(image, model)
    except Exception as exc:
        # Korean's model is fetched on first use; offline, that fails, and
        # the default model is still worth a try.
        if model == "default":
            raise
        last_note = "PaddleOCR could not load its Korean model (%s)." % (
            str(exc)[:80])
        model = "default"
        lines = _read(image, model)
    label = "PaddleOCR" if model == "default" else "PaddleOCR (Korean)"
    return lines, label


def image_to_text(image, source=None):
    lines, used = image_to_lines(image, source=source)
    from . import slant
    # Slanted labels are separate things, each on its own line, in the
    # order they start in from the left; joined into the text around them
    # they read as one sentence and were translated as one.
    level = [ln for ln in lines if not slant.is_slanted(ln)]
    tilted = sorted((ln for ln in lines if slant.is_slanted(ln)),
                    key=lambda ln: slant.start_of(ln)[0])
    out, last_bottom = [], None
    for line in level:
        _x, y, _w, h = line["box"]
        if last_bottom is not None:
            out.append("\n" if y > last_bottom - h * 0.3 else " ")
        out.append(line["text"])
        last_bottom = y + h
    for line in tilted:
        if out:
            out.append("\n")
        out.append(line["text"])
    return "".join(out).strip(), used


def korean_needed(text):
    """The default model read something, but a Korean page reads as noise
    in it: few characters it recognised, none of them Hangul."""
    hangul = sum(1 for ch in text if "가" <= ch <= "힣")
    return hangul == 0


def use_here():
    """On Windows, where it fills the gap Windows OCR leaves."""
    return bool(AVAILABLE and platform_util.IS_WINDOWS)
