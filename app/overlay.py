"""Draw translations back over the original text, in place.

Instead of a card beside the screenshot, this paints each translated line
into the box its source occupied — background and text colour sampled from
the pixels underneath, so the result keeps the look of the page it came from.

The hard parts are not the drawing but the sampling: deciding which colour in
a box is the paper and which is the ink, and fitting text of a different
length back into a box that was sized for the original.
"""
import os
import re
import sys
import time
import unicodedata

from PIL import Image, ImageChops, ImageDraw, ImageFont

from . import identifiers, numbering

# Faces that cover the scripts we can translate into. First hit wins.
_WINDOWS_FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
# One bucket per language, not one bucket for "CJK".
#
# Chinese, Japanese and Korean shared a list, and the list began with
# PingFang — a Chinese face with no Hangul in it at all. So a Korean
# translation was fetched correctly, handed to the renderer, and drawn as
# a row of empty boxes, because the first font found on a Mac could not
# draw a single character of it. The translation was never the problem;
# nothing downstream of it could tell, because a box is what a font
# renders when it has no glyph, not an error.
#
# They are three scripts that happen to be neighbours, and a font for one
# is not a font for the others. Each list now starts with a face that
# actually contains the script, and ends with the pan-Unicode fallbacks
# that cover all three.
_PAN_CJK = ["Arial Unicode.ttf", "NotoSansCJK-Regular.ttc",
            "NotoSansCJKsc-Regular.otf", "unifont.ttf"]
# Faces that carry a great many scripts at once, tried after the faces
# made for the script and before giving up.
_PAN_UNICODE = ["Arial Unicode.ttf", "unifont.ttf", "NotoSans-Regular.ttf"]
FONT_CANDIDATES = {
    "chinese": ["PingFang.ttc", "Hiragino Sans GB.ttc", "STHeiti Medium.ttc",
                "msyh.ttc", "msyhl.ttc", "simhei.ttf",
                "NotoSansSC-Regular.otf"] + _PAN_CJK,
    "japanese": ["Hiragino Sans GB.ttc", "HiraginoSans-W3.ttc",
                 "YuGothM.ttc", "meiryo.ttc", "msgothic.ttc",
                 "NotoSansJP-Regular.otf"] + _PAN_CJK,
    "korean": ["AppleSDGothicNeo.ttc", "AppleGothic.ttf", "malgun.ttf",
               "malgunbd.ttf", "NanumGothic.ttf",
               "NotoSansKR-Regular.otf"] + _PAN_CJK,
    # Kept so anything still asking for the old name gets something that
    # draws rather than nothing.
    "cjk": ["PingFang.ttc", "Hiragino Sans GB.ttc", "STHeiti Medium.ttc",
            "AppleSDGothicNeo.ttc", "msyh.ttc", "simhei.ttf",
            "meiryo.ttc", "malgun.ttf"] + _PAN_CJK,
    "arabic": ["GeezaPro.ttc", "Arial Unicode.ttf", "segoeui.ttf",
               "tahoma.ttf", "arial.ttf",
               "NotoSansArabic-Regular.ttf", "DejaVuSans.ttf"],
    "hebrew": ["ArialHB.ttc", "Arial Unicode.ttf", "segoeui.ttf",
               "tahoma.ttf", "NotoSansHebrew-Regular.ttf", "DejaVuSans.ttf"],
    # Windows ships one face — Nirmala UI — for every Indic script, so it
    # appears in all of them. macOS ships one per script.
    "devanagari": ["DevanagariSangamMN.ttc", "Kohinoor.ttc", "nirmala.ttf",
                   "mangal.ttf", "NotoSansDevanagari-Regular.ttf"],
    "bengali": ["BanglaSangamMN.ttc", "KohinoorBangla.ttc", "nirmala.ttf",
                "vrinda.ttf", "NotoSansBengali-Regular.ttf"],
    "tamil": ["TamilSangamMN.ttc", "KohinoorTamil.ttc", "nirmala.ttf",
              "latha.ttf", "NotoSansTamil-Regular.ttf"],
    "telugu": ["TeluguSangamMN.ttc", "KohinoorTelugu.ttc", "nirmala.ttf",
               "gautami.ttf", "NotoSansTelugu-Regular.ttf"],
    "kannada": ["KannadaSangamMN.ttc", "nirmala.ttf", "tunga.ttf",
                "NotoSansKannada-Regular.ttf"],
    "malayalam": ["MalayalamSangamMN.ttc", "nirmala.ttf", "kartika.ttf",
                  "NotoSansMalayalam-Regular.ttf"],
    "gujarati": ["GujaratiSangamMN.ttc", "nirmala.ttf", "shruti.ttf",
                 "NotoSansGujarati-Regular.ttf"],
    "gurmukhi": ["GurmukhiMN.ttc", "GurmukhiSangamMN.ttc", "nirmala.ttf",
                 "raavi.ttf", "NotoSansGurmukhi-Regular.ttf"],
    "sinhala": ["SinhalaSangamMN.ttc", "nirmala.ttf", "iskpota.ttf",
                "NotoSansSinhala-Regular.ttf"],
    "thai": ["Thonburi.ttc", "Ayuthaya.ttf", "leelawui.ttf", "leelawad.ttf",
             "tahoma.ttf", "NotoSansThai-Regular.ttf"],
    "lao": ["LaoSangamMN.ttf", "leelawui.ttf",
            "NotoSansLao-Regular.ttf"],
    "khmer": ["KhmerSangamMN.ttf", "khmerui.ttf",
              "NotoSansKhmer-Regular.ttf"],
    "myanmar": ["MyanmarSangamMN.ttc", "mmrtext.ttf",
                "NotoSansMyanmar-Regular.ttf"],
    "ethiopic": ["Kefa.ttc", "ebrima.ttf", "NotoSansEthiopic-Regular.ttf"],
    "georgian": ["NotoSansGeorgian-Regular.ttf", "sylfaen.ttf",
                 "segoeui.ttf", "DejaVuSans.ttf"],
    "armenian": ["Mshtakan.ttc", "sylfaen.ttf",
                 "NotoSansArmenian-Regular.ttf", "DejaVuSans.ttf"],
    # Helvetica Neue before the system font on a Mac: it is the face the
    # overlay is drawn in (TK_FONT_FAMILIES), and measuring in the
    # narrower system font made every line a little longer on screen than
    # the layout thought - long lines ran off the right edge.
    "default": ["HelveticaNeue.ttc", "Helvetica.ttc",
                "SFNS.ttf", "SFNSText.ttf", "SFNSDisplay.ttf",
                "segoeui.ttf", "arial.ttf", "calibri.ttf",
                "DejaVuSans.ttf", "LiberationSans-Regular.ttf"],
}
for _kind, _names in FONT_CANDIDATES.items():
    if _kind not in ("default", "cjk") and not _kind.endswith("cjk"):
        _names.extend(name for name in _PAN_UNICODE if name not in _names)

# The alias the code used when every Indian language shared one list of
# Devanagari faces. Tamil, Telugu, Kannada and Malayalam are not written
# in Devanagari, and a Devanagari font draws not one character of them.
FONT_CANDIDATES["indic"] = FONT_CANDIDATES["devanagari"]

_MAC_FONT_DIRS = ["/System/Library/Fonts",
                  "/System/Library/Fonts/Supplemental",
                  "/Library/Fonts",
                  os.path.expanduser("~/Library/Fonts")]
_LINUX_FONT_DIRS = ["/usr/share/fonts/truetype/dejavu",
                    "/usr/share/fonts/truetype/liberation",
                    "/usr/share/fonts/truetype/noto",
                    "/usr/share/fonts/truetype"]

CHINESE_TARGETS = {"zh-CN", "zh-TW", "zh", "zh-Hans", "zh-Hant", "yue"}
JAPANESE_TARGETS = {"ja"}
KOREAN_TARGETS = {"ko"}
CJK_TARGETS = CHINESE_TARGETS | JAPANESE_TARGETS | KOREAN_TARGETS
RTL_TARGETS = {"ar", "fa", "ur", "he"}
INDIC_TARGETS = {"hi", "mr", "ne", "bn", "ta", "te", "kn", "ml", "gu", "pa",
                 "si"}

# Which script each language this app can translate into is written in.
#
# There used to be three entries here — Chinese, Japanese, Korean — plus
# "indic" for every language of India and "arabic" for everything written
# right to left. Everything else fell to "default", which on a Mac is the
# system interface face and on Windows is Segoe UI. Neither of those has a
# single character of Thai in it, so Thai came back as a row of empty
# boxes; Hebrew was handed a Persian face with no Hebrew in it; and Tamil,
# Telugu, Kannada and Malayalam were each handed a Devanagari face, which
# is a different alphabet.
#
# It is the fault that hit Korean once already, arriving eleven more
# times. A font renders a box when it has no glyph — it does not fail —
# so the translation is fetched correctly, drawn, and unreadable, with
# nothing anywhere reporting a problem.
LANGUAGE_SCRIPT = {
    "hi": "devanagari", "mr": "devanagari", "ne": "devanagari",
    "bn": "bengali", "ta": "tamil", "te": "telugu", "kn": "kannada",
    "ml": "malayalam", "gu": "gujarati", "pa": "gurmukhi",
    "si": "sinhala", "th": "thai", "lo": "lao", "km": "khmer",
    "my": "myanmar", "am": "ethiopic", "ka": "georgian", "hy": "armenian",
    "he": "hebrew",
}

_font_cache = {}


def _font_family_for(target_lang):
    if target_lang in KOREAN_TARGETS:
        return "korean"
    if target_lang in JAPANESE_TARGETS:
        return "japanese"
    if target_lang in CHINESE_TARGETS:
        return "chinese"
    if target_lang in LANGUAGE_SCRIPT:
        return LANGUAGE_SCRIPT[target_lang]
    if target_lang in RTL_TARGETS:
        return "arabic"
    if target_lang in INDIC_TARGETS:
        return "devanagari"
    return "default"


# The same scripts again, as font *families* rather than files. PIL is
# handed a path because it rasterises the file itself; a Tk canvas is
# handed a name and asks the system. Both lists have to exist, and they
# have to agree about which face a script gets, or the same translation
# comes out in two different typefaces depending on where it is drawn.
TK_FONT_FAMILIES = {
    "chinese": ["PingFang SC", "Hiragino Sans GB", "Heiti SC",
                "Microsoft YaHei", "SimHei", "Noto Sans SC"],
    "japanese": ["Hiragino Sans", "Hiragino Kaku Gothic Pro", "Yu Gothic",
                 "Meiryo", "MS Gothic", "Noto Sans JP"],
    "korean": ["Apple SD Gothic Neo", "AppleGothic", "Malgun Gothic",
               "NanumGothic", "Noto Sans KR"],
    "arabic": ["Geeza Pro", "Arial Unicode MS", "Segoe UI", "Tahoma",
               "Noto Sans Arabic", "DejaVu Sans"],
    "hebrew": ["Arial Hebrew", "Arial Unicode MS", "Segoe UI", "Tahoma",
               "Noto Sans Hebrew", "DejaVu Sans"],
    "devanagari": ["Devanagari Sangam MN", "Kohinoor Devanagari",
                   "Nirmala UI", "Mangal", "Noto Sans Devanagari"],
    "bengali": ["Bangla Sangam MN", "Kohinoor Bangla", "Nirmala UI",
                "Vrinda", "Noto Sans Bengali"],
    "tamil": ["Tamil Sangam MN", "Kohinoor Tamil", "Nirmala UI", "Latha",
              "Noto Sans Tamil"],
    "telugu": ["Telugu Sangam MN", "Kohinoor Telugu", "Nirmala UI",
               "Gautami", "Noto Sans Telugu"],
    "kannada": ["Kannada Sangam MN", "Nirmala UI", "Tunga",
                "Noto Sans Kannada"],
    "malayalam": ["Malayalam Sangam MN", "Nirmala UI", "Kartika",
                  "Noto Sans Malayalam"],
    "gujarati": ["Gujarati Sangam MN", "Nirmala UI", "Shruti",
                 "Noto Sans Gujarati"],
    "gurmukhi": ["Gurmukhi MN", "Gurmukhi Sangam MN", "Nirmala UI", "Raavi",
                 "Noto Sans Gurmukhi"],
    "sinhala": ["Sinhala Sangam MN", "Nirmala UI", "Iskoola Pota",
                "Noto Sans Sinhala"],
    "thai": ["Thonburi", "Ayuthaya", "Leelawadee UI", "Tahoma",
             "Noto Sans Thai"],
    "lao": ["Lao Sangam MN", "Leelawadee UI", "Noto Sans Lao"],
    "khmer": ["Khmer Sangam MN", "Khmer UI", "Noto Sans Khmer"],
    "myanmar": ["Myanmar Sangam MN", "Myanmar Text", "Noto Sans Myanmar"],
    "ethiopic": ["Kefa", "Ebrima", "Noto Sans Ethiopic"],
    "georgian": ["Noto Sans Georgian", "Sylfaen", "Segoe UI", "DejaVu Sans"],
    "armenian": ["Mshtakan", "Sylfaen", "Noto Sans Armenian", "DejaVu Sans"],
    "cjk": ["PingFang SC", "Hiragino Sans GB", "Heiti SC",
            "Microsoft YaHei", "SimHei", "Meiryo", "Malgun Gothic"],
    "default": ["Helvetica Neue", "Helvetica", "Segoe UI", "Arial",
                "DejaVu Sans", "Liberation Sans"],
}
TK_FONT_FAMILIES["indic"] = TK_FONT_FAMILIES["devanagari"]


def tk_family(kind, widget=None):
    """A font family Tk has installed for this script, or "" for its own.

    Naming a family Tk does not have is not an error and does not warn —
    it silently falls back to a default that may not carry the script at
    all, which on screen is a row of empty boxes where the translation
    should be.
    """
    names = TK_FONT_FAMILIES.get(kind, TK_FONT_FAMILIES["default"])
    try:
        import tkinter.font as tkfont
        have = {name.lower() for name in tkfont.families(widget)}
    except Exception:
        return names[0]
    for name in names:
        if name.lower() in have:
            return name
    return ""


def _find_font_file(kind):
    """A font file on this machine that can actually draw this script.

    Two things were wrong with the way this used to answer, and they are
    the same thing twice: it trusted a file name.

    The named list was walked for a file that *exists*, and the first one
    found was returned without ever asking whether it contains the script.
    So Hebrew got Geeza Pro, which is a Persian face; Tamil got the
    Devanagari face; Thai got the system interface font. Each of those
    exists on the machine, each was chosen instantly, and each draws
    nothing but empty boxes. Every name is now checked.

    And the last-resort scan — which does check — looked only in the top
    of each font directory and never in its subdirectories, which on Linux
    is where all the fonts are. Asked for Korean on a machine with a
    perfectly good Korean font two levels down, it returned nothing at
    all and the page was drawn in a bitmap fallback with no Hangul in it.

    Returning None still means "I have nothing", which the caller can act
    on. It should now be rare and it should be true.
    """
    key = ("file", kind)
    if key in _font_cache:
        return _font_cache[key]
    names = FONT_CANDIDATES.get(kind, FONT_CANDIDATES["default"])
    sample = _SCRIPT_SAMPLE.get(kind)
    for name in names:
        for root in _font_roots():
            path = os.path.join(root, name)
            if not os.path.isfile(path):
                continue
            if sample and not covers(path, sample):
                # It is here and it is the wrong alphabet. Keep looking.
                continue
            _font_cache[key] = path
            return path
    for path in _every_font():
        if sample and not covers(path, sample):
            continue
        if not sample and not _is_scalable(path):
            continue
        _font_cache[key] = path
        return path
    _font_cache[key] = None
    return None


def _font_roots():
    if sys.platform == "darwin":
        roots = list(_MAC_FONT_DIRS)
    elif sys.platform == "win32":
        roots = [_WINDOWS_FONTS]
    else:
        roots = []
    return roots + _LINUX_FONT_DIRS


def _is_scalable(path):
    return path.lower().endswith((".ttf", ".ttc", ".otf"))


# Enough to find a font, not enough to walk a disk. Font directories are
# a couple of levels deep everywhere; anything deeper is not a font
# directory and is not worth the time it takes to find that out.
FONT_SCAN_DEPTH = 3


# A page set in the italic weight of a monospaced face is legible and
# looks like a mistake. When the only fonts left are whatever the machine
# happens to have, take the plainest of them first.
_AWKWARD = ("mono", "italic", "oblique", "bold", "black", "light", "thin",
            "condensed", "emoji", "symbol", "math", "dingbat")


def _plainest_first(name):
    low = name.lower()
    return (sum(1 for word in _AWKWARD if word in low), low)


def _every_font():
    """Every scalable font under the font directories, in a settled order.

    Sorted, so the same machine answers the same way twice — a font
    chosen by whatever order the filesystem happened to return would make
    the page look different from one run to the next.
    """
    seen = set()
    for root in _font_roots():
        if not os.path.isdir(root):
            continue
        base = root.rstrip(os.sep).count(os.sep)
        for here, folders, files in os.walk(root):
            if here.count(os.sep) - base >= FONT_SCAN_DEPTH:
                folders[:] = []
            folders.sort()
            for entry in sorted(files, key=_plainest_first):
                path = os.path.join(here, entry)
                if _is_scalable(path) and path not in seen:
                    seen.add(path)
                    yield path


# What a font for this script must be able to draw.
#
# This is the whole of the check. A font is not asked what it claims to
# support — it is asked to draw the character, and compared against what
# it draws for a character that certainly does not exist.
#
# Every sample begins with a Latin letter and a digit, because every
# document does. A notice in Chinese carries dates, a version number, a
# part number and an email address, all written in ASCII — and some of
# the best CJK faces have no ASCII in them at all: they are *fallback*
# fonts, meant to sit behind a Latin font rather than in front of one.
# Chosen on the strength of their Chinese, they drew every number and
# every code on the page as an empty box.
_SCRIPT_SAMPLE = {
    # Simplified-only forms: a Japanese face has 中 and none of these.
    "chinese": "A1\u4e2d\u8be5\u9879\u8be6",
    "japanese": "A1\u3042\u30d1\u8fbc",
    "korean": "A1\ud55c\uae00",
    "cjk": "A1\u4e2d\u3042\ud55c",
    "arabic": "A1\u0627",
    "hebrew": "A1\u05d0",
    "devanagari": "A1\u0915",
    "indic": "A1\u0915",
    "bengali": "A1\u0995",
    "tamil": "A1\u0b95",
    "telugu": "A1\u0c15",
    "kannada": "A1\u0c95",
    "malayalam": "A1\u0d15",
    "gujarati": "A1\u0a95",
    "gurmukhi": "A1\u0a15",
    "sinhala": "A1\u0d9a",
    "thai": "A1\u0e01",
    "lao": "A1\u0e81",
    "khmer": "A1\u1780",
    "myanmar": "A1\u1000",
    "ethiopic": "A1\u1200",
    "georgian": "A1\u10d0",
    "armenian": "A1\u0561",
}


def covers(path, sample):
    """Can this font file actually draw every character of this sample?

    A font asked for a character it does not have draws .notdef — an empty
    box, or nothing at all — and reports no error. So the test is to draw
    the character and draw one that certainly does not exist, and see
    whether the two come out the same.

    Every character, one at a time. Asking about a whole string at once
    cannot answer this: a run with one missing glyph in it still does not
    match the shape of a single missing glyph, so the answer came back
    yes. And one character was not enough on its own either — a Japanese
    face contains 中, so it passed as a Chinese font and then drew empty
    boxes for 该, 项 and 详, which exist only in the simplified set.
    """
    key = ("covers", path, sample)
    if key in _font_cache:
        return _font_cache[key]
    result = False
    try:
        font = ImageFont.truetype(path, 24)
        # bytes(), not tobytes(): getmask returns Pillow's raw image core,
        # which has no tobytes() and fails silently into the except below —
        # every font then reports as unusable and the search finds nothing.
        missing = bytes(font.getmask("\ufffe"))
        result = True
        for ch in str(sample):
            if not ch.strip():
                continue
            wanted = bytes(font.getmask(ch))
            if not any(wanted) or wanted == missing:
                result = False
                break
    except Exception:
        result = False
    _font_cache[key] = result
    return result


def load_font(kind, size, bold=False):
    size = max(6, int(size))
    key = (kind, size, bold)
    if key in _font_cache:
        return _font_cache[key]
    path = _find_font_file(kind)
    font = None
    if path:
        try:
            font = ImageFont.truetype(path, size)
        except Exception:
            font = None
    if font is None:
        font = ImageFont.load_default()
    _font_cache[key] = font
    return font


def _quantise(rgb, step=24):
    return tuple((c // step) * step for c in rgb)


def grow_to_ink(image, box, colour, tolerance=42, reach=1.2,
                vertical=False):
    """The box widened over writing that runs past its left or right edge.

    Readers draw a line's box a glyph short now and then - most often at
    the start of a Chinese or Japanese line, where the first character
    sat just outside it. The cover then stopped short and that character
    was left showing beside the translation ("郷 Local history museum").
    Where ink touches the edge of the box, the box is followed outward
    over it - up to about one character (`reach` x the height) - until a
    clear gap of background. Ink that does not touch the edge is left
    alone: that is the next word or cell, not this one.
    """
    x, y, w, h = [int(v) for v in box]
    if w <= 0 or h <= 0:
        return box
    limit = int(h * reach)
    # Letters of one word or one run of characters sit a letter-space
    # apart; words and cells sit further apart than that.
    near = max(3, int(h * 0.25))
    gap_needed = max(3, int(h * 0.4))
    # Which columns (and rows) have ink in them, worked out once for the
    # area around the box by the imaging library - it used to be asked
    # pixel by pixel in Python, and on a dense page that was half a second
    # of the layout.
    reach_x = limit + gap_needed + 2
    try:
        cols = _ink_projection(image, (x - reach_x, y, x + w + reach_x,
                                       y + h), colour, tolerance)[0]
    except Exception:
        return box
    base = x - reach_x

    def inked(column):
        if column < 0 or column >= image.width:
            return False
        i = column - base
        return 0 <= i < len(cols) and bool(cols[i])

    def follow(start, step):
        if not any(inked(start + step * k) for k in range(0, near)):
            return 0                       # nothing touching the edge
        blank, last_ink = 0, 0
        for k in range(0, limit + gap_needed):
            if inked(start + step * k):
                if k >= limit:
                    return 0               # runs on: a neighbour, not ours
                last_ink, blank = k + 1, 0
            else:
                blank += 1
                if blank >= gap_needed:
                    return last_ink
        return 0
    left = follow(x - 1, -1)
    right = follow(x + w, 1)
    x, w = x - left, w + left + right
    if not vertical:
        return (x, y, w, h)

    # And down (descenders: the tails of g, j, p, y left as specks under a
    # cover drawn to the body of the letters) and up (accents), by at most
    # half a line.
    reach_y = max(2, h // 2) + 2
    try:
        rows = _ink_projection(image, (x, y - reach_y, x + w,
                                       y + h + reach_y), colour,
                               tolerance)[1]
    except Exception:
        return (x, y, w, h)
    top_row = y - reach_y

    def row_inked(row):
        if row < 0 or row >= image.height:
            return False
        i = row - top_row
        return 0 <= i < len(rows) and bool(rows[i])

    def follow_rows(start, step):
        if not row_inked(start):
            return 0
        last = 0
        for k in range(0, max(2, h // 2) + 1):
            if row_inked(start + step * k):
                last = k + 1
            else:
                return last
        return 0                           # runs on: the next line's ink
    down = follow_rows(y + h, 1)
    up = follow_rows(y - 1, -1)
    return (x, y - up, w, h + up + down)


def _ink_projection(image, area, colour, tolerance):
    """(columns, rows) of `area` (x0, y0, x1, y1, clipped to the image and
    padded back to its full size with False) that hold a pixel further
    than `tolerance` from `colour` - the sum of the three channel
    differences, as the pixel walk it replaces measured it."""
    x0, y0, x1, y1 = [int(v) for v in area]
    cx0, cy0 = max(0, x0), max(0, y0)
    cx1, cy1 = min(image.width, x1), min(image.height, y1)
    width, height = max(0, x1 - x0), max(0, y1 - y0)
    if cx1 <= cx0 or cy1 <= cy0:
        return [False] * width, [False] * height
    crop = image.crop((cx0, cy0, cx1, cy1))
    if crop.mode != "RGB":
        crop = crop.convert("RGB")
    flat = Image.new("RGB", crop.size, tuple(int(c) for c in colour[:3]))
    r, g, b = ImageChops.difference(crop, flat).split()
    # Summed without clipping below 255: the threshold is far under it.
    total = ImageChops.add(ImageChops.add(r, g), b)
    mask = total.point(lambda v: 255 if v > tolerance else 0)
    cols, rows = mask.getprojection()
    cols = [False] * (cx0 - x0) + [bool(c) for c in cols] + \
        [False] * (x1 - cx1)
    rows = [False] * (cy0 - y0) + [bool(r_) for r_ in rows] + \
        [False] * (y1 - cy1)
    return cols, rows


def ink_box(image, box, colour, tolerance=42, margin=2):
    """Where the writing actually is inside this box, or None if nowhere.

    The size of the translation is taken from the height of the box the
    recogniser handed back, which trusts the recogniser to have drawn it
    round the line and nothing else. It usually has. Sometimes it has
    swallowed the blank space above the line, or run two lines together,
    and then the height is a measurement of the whitespace rather than of
    the writing — so the translation is drawn two or five times too big,
    wraps over half a dozen lines, and shoulders the rest of the page out
    of the way. One number, and the whole page looks broken.

    The pixels are not in any doubt about where the writing is. Anything
    that differs from the background is ink; everything else is blank, and
    blank is where a line is not. So the box is shrunk to what it actually
    contains before anything is measured from it.

    Done with a difference and a bounding box rather than by walking rows
    in Python, because both of those are single operations inside the
    imaging library and this runs for every line on the page.
    """
    x, y, w, h = (int(v) for v in box)
    left, top = max(0, x), max(0, y)
    right = min(image.width, x + w)
    bottom = min(image.height, y + h)
    if right - left < 2 or bottom - top < 2:
        return None
    try:
        crop = image.crop((left, top, right, bottom)).convert("RGB")
        flat = Image.new("RGB", crop.size, tuple(int(c) for c in colour[:3]))
        mask = ImageChops.difference(crop, flat).convert("L")
        bounds = mask.point(lambda v: 255 if v > tolerance else 0).getbbox()
    except Exception:
        return None
    if not bounds:
        return None                    # the recogniser found text in a gap
    bx0, by0, bx1, by1 = bounds
    # A hair of margin, so a descender or an accent clipped by the
    # threshold does not shave the line.
    bx0 = max(0, bx0 - margin)
    by0 = max(0, by0 - margin)
    bx1 = min(crop.width, bx1 + margin)
    by1 = min(crop.height, by1 + margin)
    return (left + bx0, top + by0, max(1, bx1 - bx0), max(1, by1 - by0))


# A band of writing has to be at least this much of the tallest band in
# the box to count as a line of its own. The umlaut over an A, the dot
# over an i and the bar of a t all sit above the body of their line with
# clear blank rows between, and a rule that counted every band would read
# "Über" as two lines and halve the size of every accented word on the
# page. A real second line is about as tall as the first; an accent is a
# tenth of it. Measured against the tallest band rather than against the
# box, because the box is the lines *and* the paper between them, and
# each line of a two-line box is only about a quarter of it.
MAJOR_BAND = 0.45

# Blank rows have to add up to this much of the box before they separate
# one band from the next. Below it they are the gap inside a line —
# between an accent and its letter, or across the waist of a capital.
BAND_GAP = 0.08


def ink_rows(image, box, colour, tolerance=42):
    """How many lines of writing are inside this box.

    Shrinking a box to its ink fixes a box that swallowed the blank space
    above a line. It does not fix the other way a recogniser gets a box
    wrong, which is running two lines of the page together into one: the
    ink then really is that tall, so measuring it changes nothing, and the
    translation is drawn at twice the size of everything around it. That is
    the invoice number set in headline type on an otherwise ordinary page.

    Two lines have blank paper between them and one line does not, so the
    question is answerable from the pixels rather than from the recogniser.
    The box is reduced to one column of averages — one number per row,
    how much ink that row holds — and the rows are walked to find the
    bands of writing and the blank runs between them.

    Returns at least 1. The count is used to divide the box's height into
    a per-line height; it is not used to split the box, because which
    words belong to which line is not recoverable from the translation.
    """
    x, y, w, h = (int(v) for v in box)
    left, top = max(0, x), max(0, y)
    right, bottom = min(image.width, x + w), min(image.height, y + h)
    height = bottom - top
    if right - left < 2 or height < 6:
        return 1
    try:
        crop = image.crop((left, top, right, bottom)).convert("RGB")
        flat = Image.new("RGB", crop.size, tuple(int(c) for c in colour[:3]))
        mask = ImageChops.difference(crop, flat).convert("L")
        mask = mask.point(lambda v: 255 if v > tolerance else 0)
        # One pixel wide, so each row is the share of it that is ink.
        column = mask.resize((1, height), Image.BOX)
        rows = list(column.getdata())
    except Exception:
        return 1

    # A row counts as writing if any appreciable part of it is ink. Low,
    # because a row through the tops of two ascenders is mostly paper and
    # is still part of the line.
    inked = [value > 4 for value in rows]
    bands, start = [], None
    for index, value in enumerate(inked + [False]):
        if value and start is None:
            start = index
        elif not value and start is not None:
            bands.append((start, index))
            start = None
    if len(bands) < 2:
        return 1

    # Close up the gaps too small to be paper between lines.
    gap = max(2, int(height * BAND_GAP))
    joined = [list(bands[0])]
    for band_start, band_end in bands[1:]:
        if band_start - joined[-1][1] < gap:
            joined[-1][1] = band_end
        else:
            joined.append([band_start, band_end])

    tallest = max(b[1] - b[0] for b in joined)
    floor = max(2, int(tallest * MAJOR_BAND))
    major = [b for b in joined if b[1] - b[0] >= floor]
    return max(1, len(major))


def _line_unit(line):
    """The height of one line of writing in this box.

    The same as the box's height for a box that holds one line, which is
    nearly all of them. Half of it for a box the recogniser drew round
    two. Every number that answers "how big should this text be" comes
    from here rather than from the box, because the box is sometimes a
    measurement of two lines and a font size never is.
    """
    try:
        unit = int(line.get("unit") or 0)
    except Exception:
        unit = 0
    return unit if unit > 0 else int(line["box"][3])


# The space left between a cover and whatever is beside it.
#
# `background_run` samples every few pixels and three rows out of the
# line's height, because it runs for every line on the page. That is
# accurate enough to find the edge of a column and not accurate enough to
# stop on the exact pixel, so the last two or three before the neighbour
# are not really known to be empty. Leaving them is cheaper than sampling
# every one of them.
COVER_GAP = 3


def background_below(image, box, colour, limit, tolerance=40):
    """How many rows under `box` are still plain background across its
    width - up to `limit` below its top. See the room in `layout`."""
    x, y, w, h = [int(v) for v in box]
    start = max(0, y + h)
    end = min(image.height, y + int(limit))
    left, right = max(0, x), min(image.width, x + max(1, w))
    if end <= start or right <= left:
        return max(0, end - start)
    try:
        region = image.crop((left, start, right, end))
        if region.mode != "RGB":
            region = region.convert("RGB")
        plain = Image.new("RGB", region.size, tuple(int(c) for c in colour[:3]))
        # Per pixel, the largest difference of the three channels; a pixel
        # is ink when it is more than a third of `tolerance` off in any.
        diff = ImageChops.difference(region, plain)
        r, g, b = diff.split()
        worst = ImageChops.lighter(ImageChops.lighter(r, g), b)
        marked = worst.point(lambda v: 255 if v > tolerance // 3 else 0)
        _cols, rows = marked.getprojection()
        for index, value in enumerate(rows):
            if value:
                return max(0, index - 2)
        return end - start
    except Exception:
        return limit


def background_run(image, box, colour, limit, tolerance=26, step=1,
                   ink=None):
    """How far right of `box` the same background actually continues.

    The cover painted over a line reaches to the right, on the reasoning
    that the space beside a line is the same background and free to use.
    Clipping it to the column stopped it landing on the column next door,
    but inside a column that reasoning is still only usually true: a line
    that ends beside a shaded panel, a table cell, or a rule gets a cover
    filled with its own background painted across something a different
    colour, and the result is the stray grey block on an otherwise white
    page.

    So the reach is measured rather than assumed — walk right until the
    background stops being the background. Sampled every few pixels and
    over three rows rather than every pixel of every row, because this
    runs for every line on the page and the answer does not get better
    for being exact.
    """
    x, y, w, h = box
    if limit <= 0:
        return 0
    try:
        pixels = (image if image.mode == "RGB" else image.convert("RGB")).load()
    except Exception:
        return limit
    rows = [max(0, min(image.height - 1, y + int(h * f)))
            for f in (0.15, 0.5, 0.85)]
    start = min(image.width - 1, max(0, int(x + w)))

    def distance(pixel):
        return sum(abs(int(pixel[i]) - int(colour[i])) for i in range(3))

    # With the text's own colour in hand, a faint mark can be told from a
    # real one. See `_faint_is_furniture`.
    strong = None
    if ink is not None:
        try:
            strong = max(3 * tolerance, distance(ink) // 2)
        except Exception:
            strong = None
    # The three rows' distances from the background, worked out in one go
    # by the imaging library rather than pixel by pixel in Python - this
    # was the largest part of laying a page out.
    end = min(image.width, start + int(limit) + 1)
    gaps = []
    try:
        solid = Image.new("RGB", (max(1, end - start), 1),
                          tuple(int(c) for c in colour[:3]))
        rgb = image if image.mode == "RGB" else image.convert("RGB")
        for row in rows:
            strip = rgb.crop((start, row, max(start + 1, end), row + 1))
            bands = [band.tobytes() for band in
                     ImageChops.difference(strip, solid).split()]
            gaps.append([a + b + c for a, b, c in zip(*bands)])
    except Exception:
        gaps = None
    reach = 0
    for offset in range(0, int(limit) + 1, step):
        column = start + offset
        if column >= image.width:
            break
        faint = False
        for index, row in enumerate(rows):
            if gaps is not None:
                gap = gaps[index][offset]
            else:
                try:
                    gap = distance(pixels[column, row])
                except Exception:
                    return reach
            if gap <= tolerance:
                continue
            if strong is None or gap > strong:
                return reach
            faint = True
        if faint and not _faint_is_furniture(pixels, image, column, y, h,
                                             distance, tolerance):
            return reach
        reach = offset
    return min(int(limit), reach)


def _faint_is_furniture(pixels, image, column, y, h, distance, tolerance):
    """Whether a faint mark beside a line is a watermark to reach across.

    A watermark is faint text set diagonally across the whole page, and it
    stopped every block that ran into it: a Korean translation of a
    Chinese notice wrapped at the exact point where the watermark began,
    three times on one page, with the rest of the line empty. The reach
    stopped at the first pixel that was not background, and a watermark is
    pixels that are not background.

    What the reach exists to stop is different: a shaded panel, a table
    cell, a rule — things that stand the full height of the line and
    beyond it. So a faint pixel is looked at up and down its column, from
    half a line above to half a line below. A panel or a rule fills that
    column; the stroke of a watermark letter crosses it and leaves most of
    it empty. Anything strong — the page's own text, a dark rule, a
    picture — still stops the reach at once, before this is asked.
    """
    top = max(0, int(y - h // 2))
    bottom = min(image.height - 1, int(y + h + h // 2))
    seen = filled = 0
    own_seen = own_filled = 0
    for row in range(top, bottom + 1, 2):
        try:
            pixel = pixels[column, row]
        except Exception:
            return False
        seen += 1
        marked = distance(pixel) > tolerance
        if marked:
            filled += 1
        if y <= row < y + h:
            own_seen += 1
            own_filled += marked
    # A line standing most of the height of this line's own rows is the edge
    # of something - an infobox, a panel that starts at this very line -
    # even where it does not reach half a line above: a wall, not a mark.
    if own_seen and own_filled >= 0.6 * own_seen:
        return False
    return bool(seen) and filled < 0.8 * seen


def sample_colours(image, box, pad=1):
    """Work out (background, foreground) for one line box.

    Text is a minority of the pixels in its own box — the background is
    whatever is most common, and the ink is the frequent colour furthest away
    from it. Averaging instead would produce a muddy blend of the two.
    """
    x, y, w, h = box
    left = max(0, x - pad)
    top = max(0, y - pad)
    right = min(image.width, x + w + pad)
    bottom = min(image.height, y + h + pad)
    if right - left < 2 or bottom - top < 2:
        return (255, 255, 255), (0, 0, 0)

    crop = image.crop((left, top, right, bottom)).convert("RGB")
    if crop.width * crop.height > 40000:
        crop = crop.resize((max(1, crop.width // 2),
                            max(1, crop.height // 2)), Image.NEAREST)

    # The same buckets as _quantise, counted by the imaging library rather
    # than a pixel at a time in Python: this runs for every line, several
    # times per page, and was a third of the time a layout took.
    stepped = crop.point([(c // 24) * 24 for c in range(256)] * 3)
    counts = {tuple(colour): count for count, colour in
              (stepped.getcolors(stepped.width * stepped.height) or [])}
    if not counts:
        return (255, 255, 255), (0, 0, 0)

    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    bg = ranked[0][0]
    total = sum(counts.values())

    best, best_score = None, -1.0
    for colour, count in ranked[:12]:
        if count < total * 0.01:
            continue
        distance = sum(abs(colour[i] - bg[i]) for i in range(3))
        # Weight by how much of the box it covers, so a stray antialiased
        # pixel cannot win over the actual ink.
        score = distance * (count ** 0.35)
        if score > best_score:
            best, best_score = colour, score
    if best is None or sum(abs(best[i] - bg[i]) for i in range(3)) < 40:
        luma = (bg[0] * 299 + bg[1] * 587 + bg[2] * 114) / 1000.0
        best = (0, 0, 0) if luma > 140 else (255, 255, 255)

    # Exact background beats the quantised bucket for a seamless fill.
    exact = crop.getpixel((0, 0))
    if sum(abs(_quantise(exact)[i] - bg[i]) for i in range(3)) <= 24:
        bg = exact
    return tuple(int(c) for c in bg), tuple(int(c) for c in best)


def _fit_font(draw, text, kind, box_w, box_h, bold=False, min_size=7):
    """Largest size that fits the box, falling back to wrapping if needed."""
    size = max(min_size, int(box_h * 0.86))
    while size > min_size:
        font = load_font(kind, size, bold)
        try:
            length = draw.textlength(text, font=font)
        except Exception:
            length = size * 0.6 * len(text)
        if length <= box_w and size <= box_h * 1.05:
            return font, length
        size -= 1
    font = load_font(kind, min_size, bold)
    try:
        return font, draw.textlength(text, font=font)
    except Exception:
        return font, box_w


def _size_that_fits(draw, text, kind, box_w, box_h, bold=False, min_size=7):
    """Largest point size whose text fits the box on ONE line."""
    size = max(min_size, int(box_h * 0.86))
    while size > min_size:
        font = load_font(kind, size, bold)
        try:
            length = draw.textlength(text, font=font)
        except Exception:
            length = size * 0.6 * len(text)
        if length <= box_w and size <= box_h * 1.05:
            return size
        size -= 1
    return min_size


# Characters that must not start a line, and characters that must not end
# one. Breaking before a full stop or after an opening bracket is the
# difference between typeset Chinese and Chinese with the punctuation in
# the wrong place.
_NO_LINE_START = "、。，．：；？！）】》」』’”%…"
_NO_LINE_END = "（【《「『‘“"


# Hangul: syllables, both jamo blocks, and the two extended ranges.
#
# Korean is written with spaces between words, and that is the whole
# reason this list exists. Everything above 0x2E80 used to be treated as
# one thing — "a wide script, no spaces between characters" — which is
# true of Chinese and Japanese and false of Korean. Hangul sits in the
# same numeric neighbourhood, so every Korean translation drawn onto a
# page came out as one unbroken run of syllables:
#
#     연구진은 세 도시에서  ->  연구진은세도시에서
#
# Nothing said so. It reads as if the app cannot write Korean, and the
# only reason it went unnoticed is that every test translated *into*
# English. The corpus has a Korean page; nothing ever produced Korean.
_HANGUL_RANGES = ((0x1100, 0x11FF), (0x3130, 0x318F), (0xA960, 0xA97F),
                  (0xAC00, 0xD7AF), (0xD7B0, 0xD7FF))


def _is_hangul(ch):
    point = ord(ch)
    return any(low <= point <= high for low, high in _HANGUL_RANGES)


def _pieces(text):
    """The units a line may be broken between.

    Latin scripts break between words, and splitting on spaces is the whole
    job. Chinese and Japanese do not put spaces between words at all, so a
    whole paragraph arrives as one piece — the wrapper then has nothing to
    break on, keeps it as a single line, and it runs off the side of the
    box. Nothing in the output says so: the words are simply not on screen.

    So a run without spaces is broken between characters, which is what
    those scripts do anyway, with the small politeness of not stranding
    closing punctuation at the start of a line.

    Korean is the exception that this got wrong for a long time. It is
    written with spaces, its words are units, and breaking between every
    syllable throws away the spacing the translator produced. Korean words
    stay whole here; `_wrap` splits one between syllables only when a
    single word will not fit on a line by itself, which is what Korean
    typesetting does too.
    """
    out = []
    for word in str(text).split():
        if all(ord(ch) < 0x2E80 for ch in word):
            out.append(word)                 # nothing wide in it
            continue
        if all(_is_hangul(ch) or ord(ch) < 0x2E80 for ch in word):
            out.append(word)                 # Korean: a word is a unit
            continue
        piece = ""
        for ch in word:
            if ord(ch) < 0x2E80:
                piece += ch                  # keep runs of Latin together
                continue
            if piece:
                out.append(piece)
                piece = ""
            if out and (ch in _NO_LINE_START or out[-1][-1] in _NO_LINE_END):
                out[-1] += ch
            else:
                out.append(ch)
        if piece:
            out.append(piece)
    return out


def _characters(word):
    """One word as the pieces it may be broken into, last resort.

    For a word too wide for its own line: Korean between syllables, and
    anything else between characters, so that nothing is ever drawn off
    the side of the box. Closing punctuation still does not start a line.

    A combining mark is never a place to break. Thai writes its vowels and
    tones as marks above and below the consonant they belong to, and so do
    Hindi, Arabic and Vietnamese — split between the two and the letter
    loses its vowel to the line below, which is not a wrapping fault the
    reader can see past. They stay with the character they attach to.
    """
    out = []
    for ch in str(word):
        joined = unicodedata.combining(ch) or \
            unicodedata.category(ch) in ("Mn", "Mc", "Me")
        if out and (joined or ch in _NO_LINE_START
                    or out[-1][-1] in _NO_LINE_END):
            out[-1] += ch
        else:
            out.append(ch)
    return out or [word]


def _joiner(left, right):
    """A space between words, nothing between characters of a wide script.

    Hangul is asked about first. Two Korean pieces are always two words —
    `_pieces` never splits one — so they take a space, and the rule that
    everything above 0x2E80 is joined with nothing would have removed it.
    """
    if not left or not right:
        return ""
    if _is_hangul(left[-1]) or _is_hangul(right[0]):
        return " "
    wide = ord(left[-1]) >= 0x2E80 or ord(right[0]) >= 0x2E80
    return "" if wide else " "


def _wrap(draw, text, font, max_width):
    """Break text into lines that each fit `max_width`."""
    words, lines, current = _pieces(text), [], ""
    current_w = 0.0
    for word in words:
        # A word wider than the whole box has to be broken somewhere, or
        # it is drawn off the side and the rest of the sentence is simply
        # not on screen. Korean words are kept whole above; this is where
        # a very long one is split between its syllables, and where a
        # script with no spaces at all cannot overflow either.
        if _width_of(draw, word, font) > max_width:
            parts = _characters(word)
            if len(parts) > 1:
                for index, part in enumerate(parts):
                    if not current:
                        candidate = part
                    elif index:
                        candidate = current + part       # inside one word
                    else:
                        candidate = current + _joiner(current, part) + part
                    if _width_of(draw, candidate, font) <= max_width \
                            or not current:
                        current = candidate
                    else:
                        lines.append(current)
                        current = part
                current_w = _width_of(draw, current, font) if current else 0.0
                continue
        candidate = word if not current else current + _joiner(
            current, word) + word
        # The line so far plus this word, from widths already known;
        # measured whole only where the sum is too close to call.
        if current:
            joined = _joiner(current, word) + word
            guess = current_w + _width_of(draw, joined, font)
            if abs(guess - max_width) <= 2:
                guess = _width_of(draw, candidate, font)
        else:
            guess = _width_of(draw, candidate, font)
        if guess <= max_width or not current:
            current, current_w = candidate, guess
        else:
            lines.append(current)
            current = word
            current_w = _width_of(draw, word, font)
    if current:
        lines.append(current)
    return lines


LEADING = 1.12          # the floor: line spacing for a script that is flat

# A little air between the bottom of one line and the top of the next.
LEADING_AIR = 0.06

# What each script is asked to draw when its line spacing is measured.
# Chosen to include the tallest and deepest thing the script does: the
# vowel signs that stack above and below a Devanagari or Thai consonant,
# the marks on Arabic, an ascender and a descender in Latin.
# Latin is deliberately sampled without accented capitals: Á is taller
# than any ordinary line of English and would loosen every page in the
# language most translations come back in, to protect a character most of
# them do not contain.
_LEADING_SAMPLE = {
    "devanagari": "शिक्षा हैं",
    "indic": "शिक्षा हैं",
    "bengali": "শিক্ষা",
    "tamil": "க்கும்",
    "telugu": "క్కు",
    "kannada": "ಕ್ಕು",
    "malayalam": "ക്കു",
    "gujarati": "ક્કુ",
    "gurmukhi": "ਕ੍ਕੁ",
    "sinhala": "ක්කු",
    "thai": "กิ้ง ญุ",
    "lao": "ກິ້ງ",
    "khmer": "កិ្កុ",
    "myanmar": "ကိုင်",
    "arabic": "أعلنت وزارة",
    "hebrew": "שָׁלוֹם",
    "korean": "gh한국어",
    "japanese": "あパ文字",
    "chinese": "汉字，中",
    "default": "Ahgjpqy",
}

# One measurement per script and size, kept.
_leading_cache = {}


def leading_for(kind, size):
    """How far apart to set the lines of this script, in pixels.

    1.12 of the font size is right for Latin, Cyrillic and CJK, and it was
    used for everything. It is not right for the scripts that write above
    and below the line: Devanagari stacks its vowel signs over the
    consonant and hangs others under it, and its ink measures 1.21 of the
    size — so at 1.12 the next line is drawn *through* the one above it.
    Arabic measures 1.29. Thai stacks two marks over one letter and is
    taller still.

    Nobody has to be told which those are. The font is asked to draw a
    line of the script and the ink is measured, once per script and size.
    A flat script measures under the floor and nothing changes for it.
    """
    key = (kind, int(size))
    if key in _leading_cache:
        return _leading_cache[key]
    ratio = LEADING
    try:
        font = load_font(kind, size)
        sample = _LEADING_SAMPLE.get(kind, _LEADING_SAMPLE["default"])
        box = font.getbbox(sample)
        tall = (box[3] - box[1]) / float(max(1, size))
        ratio = max(LEADING, tall + LEADING_AIR)
    except Exception:
        pass
    out = max(1, int(round(size * ratio)))
    _leading_cache[key] = out
    return out


# The most lines one block may wrap to. Not a layout preference — the
# space available is what decides that — only a guard against a box that
# asks for a hundred one-word lines.
MOST_ROWS = 16


def _size_that_fits_wrapped(draw, text, kind, box_w, avail_h, natural,
                            min_size=7):
    """Largest size that fits once the text is allowed to wrap.

    Chinese is dense: one character carries what English needs a word for, so
    an English translation of the same line runs roughly twice as wide.
    Forcing it back onto one line of the original width is what made the
    result unreadable — the only way to fit was to shrink to nothing.

    Most pages leave space between rows. Using it means the text can stay
    near its original size and simply take two lines instead of one.
    """
    size = max(min_size, int(natural))
    # A word is never cut in two while a smaller size would keep it whole:
    # "Facili / ty" and "Tim / e" in a narrow table cell read as two
    # words, and the reader cannot tell which. Languages written without
    # spaces break between characters anyway and are not held to this.
    words = [w for w in str(text or "").split() if w]
    spaced = len(words) > 1 or (words and len(words[0]) <= 24 and
                                not any(0x3000 <= ord(c) <= 0xD7AF
                                        for c in words[0]))
    longest = max(words, key=len) if words and spaced else ""
    while size > min_size:
        font = load_font(kind, size)
        if longest and _width_of(draw, longest, font) > box_w:
            size -= 1
            continue
        rows = _wrap(draw, text, font, box_w)
        height = len(rows) * leading_for(kind, size)
        # The height is the limit. The row count was a second one — no
        # more than four lines, whatever the space — and between them the
        # height was never reached: a paragraph that needed six readable
        # lines in the room it had was shrunk until it fitted four.
        #
        # `avail_h` is measured off the page and is the honest constraint.
        # The count that remains is only a guard against a pathological
        # box asking for a hundred one-word lines.
        # One row always fits the room its original line took: the
        # leading is a little taller than the line's box, which is not a
        # reason to set it smaller.
        if (height <= avail_h or len(rows) == 1) and len(rows) <= MOST_ROWS:
            return size, rows
        size -= 1
    font = load_font(kind, min_size)
    return min_size, _wrap(draw, text, font, box_w)


# What the start of a list item looks like, in the scripts this app reads.
#
# Arabic numerals and letters with a dot, bracket or colon; the CJK
# enumeration comma, which is how Chinese, Japanese and Korean number their
# sections (一、二、三、); the circled numerals; and the bullet characters.
# Deliberately anchored and deliberately short: it may only ever *split* a
# paragraph, so a false positive costs one paragraph laid out as two, and a
# false negative costs what this was written to fix.
_LIST_MARKER = re.compile(
    r"^\s*(?:[•·▪◦‣∙*\-–—]\s"
    # Bullets set without a space after them, as Japanese and Chinese
    # pages do ("・30日も関東は雨続く"), and the arrows and squares used as
    # bullets in menus and headline lists.
    r"|[・●○■□◆◇▶►▸›»※]"
    # Not a decimal: "3.5 percent" begins a sentence, not a list.
    r"|\(?[0-9]{1,2}[.)、:：](?!\d)\s?"
    r"|\(?[a-zA-Z][.)]\s"
    r"|[一二三四五六七八九十百]{1,3}[、.]"
    r"|[가-힣][.)]\s"
    r"|[①-⑳㈠-㈩])")

# And what a *section* number looks like: 3.5, 3.8.1, 2.10.4.
#
# The marker above refuses these on purpose — "3.5 percent" opens a
# sentence, not a list — and refusing them cost a whole class of document.
# Contracts, specifications and standards number themselves this way and
# almost nothing else does, so on a page of terms and conditions every
# heading was glued to the front of the paragraph it headed and every
# numbered clause was merged into its neighbours:
#
#     3.8 Laufzeit und Kündigung        ->  one paragraph of 1,200
#     3.8.1 Die Erstvertragslaufzeit...     characters, headings and
#     3.8.2 Darüber hinaus...               all, and one box to hold it
#
# Which spoils more than the shape. An engine handed twelve hundred
# characters of numbered clauses as one run stops translating and starts
# editing — it lifts the numbers out to the end, and writes "[number]
# months" where the contract said twenty-four. Sentence by sentence it
# does neither.
#
# What keeps "3.5 percent" out is the word after it. A section number is
# followed by the start of something — a capital, a quotation mark, an
# opening bracket — or by nothing at all, the number being a line of its
# own. A decimal is followed by its unit, and units are lower case. The
# German convention writes decimals with a comma anyway.
_SECTION_NUMBER = re.compile(
    r"^\s*[0-9]{1,3}(?:\.[0-9]{1,3})+\.?"
    r"(?:\s*$|\s+(?![\d\u00df-\u00ffa-z]))",
    re.UNICODE)


# How much heavier than the page's own text a line has to be set before
# it is read as a heading rather than as a sentence.
#
# A heading is bold. That is the whole of what separates "3.6
# Kommunikation per SMS" from the paragraph beneath it — they sit at the
# same margin, the same size, one line apart, and every test for "these
# are one wrapped paragraph" says yes, so the heading was swallowed by
# the text it introduces and came back translated as the opening words
# of a sentence.
#
# Weight is not in anything a recogniser hands back, but it is in the
# picture: bold type puts more ink in the same box. Measured over this
# page, body lines sit between 0.98 and 1.02 of the page's own median and
# the headings at 1.39 and 1.77 — a gap wide enough that the threshold
# does not have to be chosen carefully. It only ever *splits* a
# paragraph, so a false positive costs one paragraph laid out as two.
HEAVY = 1.22

# Below this the box is too small a sample to say anything: a two-word
# line has few enough pixels that one thick stroke moves the fraction.
ENOUGH_INK = 400

# How much darker than the paper a pixel has to be to count as ink.
INK_STEP = 60


def _ink(image, box):
    """The share of this box that is ink rather than paper."""
    x, y, w, h = (int(v) for v in box)
    if w <= 0 or h <= 0:
        return None
    try:
        crop = image.crop((x, y, x + w, y + h)).convert("L")
    except Exception:
        return None
    data = list(crop.getdata())
    if len(data) < ENOUGH_INK:
        return None
    # The paper is whatever most of the box is, and the ink is whatever is
    # far from it — in either direction. Taken as "the lightest pixel" and
    # "darker than that", a page set light-on-dark measures as no ink at
    # all on every line, which is not wrong so much as silent.
    paper = sorted(data)[len(data) // 2]
    ink = sum(1 for value in data if abs(value - paper) > INK_STEP)
    return ink / float(len(data))


def weigh_lines(lines, image):
    """Mark the lines this page sets more heavily than the rest.

    Writes `heavy` onto each line it is sure about and leaves the rest
    alone. Compared against the page's own median rather than an absolute:
    a scan, a screenshot and a PDF put down quite different amounts of
    ink for the same type, and the question is only which lines on *this*
    page are heavier than its own running text.
    """
    if image is None or len(lines) < 4:
        return lines
    weights = []
    for line in lines:
        try:
            weights.append(_ink(image, line["box"]))
        except Exception:
            weights.append(None)
    known = sorted(value for value in weights if value)
    if len(known) < 4:
        return lines
    middle = known[len(known) // 2]
    if not middle:
        return lines
    for line, value in zip(lines, weights):
        if value is not None:
            line["heavy"] = value >= middle * HEAVY
    # And the colour each line is written in: a heading set in the site's
    # colour above body text in black is a heading, not the paragraph's
    # first line (see group_paragraphs).
    for line in lines:
        try:
            _bg, fg = sample_colours(image, line["box"])
            line["ink_colour"] = tuple(int(v) for v in fg[:3])
        except Exception:
            pass
    return lines


# How much of the space immediately around a line may be something other
# than one flat colour before the line is text in a picture rather than
# text on a page.
#
# Squint covers what it translates. On paper that is right — the cover is
# the same colour as the page and nothing is lost. On a photograph it is
# vandalism: a product shot with an opaque box painted across it, and
# inside the box a translation of a wordmark the recogniser could not
# read anyway. VISION came back as "V - 0 N", GLASS FLOW as "G to ASS
# Fに ○W", and both were pasted over the artwork they came from.
#
# It is also where the layout loses its footing entirely. Everything
# downstream trusts the boxes: how far a block may grow is measured as a
# run of unbroken background, and a photograph has no unbroken
# background, so the measurement is noise. One caption inside a card was
# set six times its own size, spilled past the bottom of the card, and
# pushed every block under it hundreds of pixels down an empty page.
#
# So the question is asked before any of that: is this line on paper?
# Measured on the band just above and below it, which on a page is margin
# and on a picture is picture. Over four document pages in three scripts
# no line reached 0.43; over the gallery page the median was 0.79.
BUSY = 0.55

# The band is this much of the line's own height, above and below.
BUSY_BAND = 0.6

# Fewer pixels than this and the sample says nothing.
ENOUGH_AROUND = 150


def _busy_around(image, box):
    """How much of the space around this line is not one flat colour."""
    from collections import Counter
    x, y, w, h = (int(v) for v in box)
    if w <= 0 or h <= 0:
        return None
    pad = max(4, int(h * BUSY_BAND))
    try:
        above = image.crop((max(0, x), max(0, y - pad),
                            min(image.width, x + w), max(0, y)))
        below = image.crop((max(0, x), min(image.height, y + h),
                            min(image.width, x + w),
                            min(image.height, y + h + pad)))
        data = list(above.convert("RGB").getdata()) + \
            list(below.convert("RGB").getdata())
    except Exception:
        return None
    if len(data) < ENOUGH_AROUND:
        return None
    # Coarse buckets, because a photograph of a white cup on a white cloth
    # is still a photograph and its whites are not all the same white.
    coarse = [(p[0] // 16, p[1] // 16, p[2] // 16) for p in data]
    commonest = Counter(coarse).most_common(1)[0][1]
    return 1.0 - commonest / float(len(coarse))


def mark_pictures(lines, image):
    """Mark the lines that are printed on a picture rather than on a page.

    Writes `on_a_picture` where it can tell and leaves the rest alone.
    `held_back` then refuses to translate them or draw over them, so a
    logo, a caption baked into a product shot, or a title set across a
    photograph is left exactly as the page had it.
    """
    if image is None:
        return lines
    for line in lines:
        try:
            busy = _busy_around(image, line["box"])
        except Exception:
            busy = None
        if busy is not None:
            line["on_a_picture"] = busy >= BUSY
    return lines


_CJK_SENTENCE_END = "。；！？"


def _ends_cjk_sentence(text):
    text = str(text or "").rstrip()
    return bool(text) and text[-1] in _CJK_SENTENCE_END


def starts_a_list_item(text):
    """Does this line begin a numbered or bulleted item, or a section?"""
    text = str(text or "")
    return bool(_LIST_MARKER.match(text) or _SECTION_NUMBER.match(text))


# How much further apart than the page's own line spacing two lines may
# be and still be one paragraph. A paragraph break is a whole line of
# space or close to it — measured on the corpus, a break is 1.5 of the
# line spacing and a table row 1.4 — so this sits below both.
PITCH_SLACK = 1.25

# And a gap this much larger than the line itself is not the space inside
# a paragraph however the page is spaced.
#
# The page's own spacing is the better measurement of the two and it has
# one failure: on a page that is nothing but a table, the spacing it
# measures is the spacing between *rows*, and every row then looks like
# the next line of a paragraph. This is the sanity bound that stops that —
# a gap of twice the line's own height is a break in anybody's typography.
# Measured on the corpus, the gaps inside a paragraph run from 0.8 to 1.2
# of the line height and the gaps between them start at 1.5.
WIDEST_GAP = 2.0

# Below this many measurements the page has not said anything about its own
# spacing and the answer would be one accident.
ENOUGH_PITCHES = 4


def line_pitch(lines, indent_tolerance=0.25):
    """The distance from one line of this page to the next, in pixels.

    Whether two lines belong to the same paragraph is a question about the
    space between them, and the space was being judged against the height
    of the box around the letters. Those are not the same measurement and
    the ratio between them is not a constant: a recogniser hands back a box
    round the ink it found, so a line of Latin capitals and a line of
    lower-case Hangul on the same page, set in the same type at the same
    spacing, come back 17 and 10 pixels tall. The gap between the lines
    does not change. Divided by the box height it looks like 0.4 in one
    place and 1.0 in another, and a rule written as "0.75 of the height"
    then splits the second paragraph and not the first.

    That is what it did. On the six pages of the corpus it left three
    quarters of every page as single lines — each one sent to the engine
    with no sentence around it, each one laid out in a box the width of
    whatever fragment it happened to be. "가능하다" on its own came back
    as "It is pos sible."

    So the page is asked instead. Take, for each line, the distance down to
    the nearest line under it that is set the same way — same indent,
    similar height, overlapping it horizontally — and keep the low end of
    those distances. Paragraph breaks and the gaps between sections are in
    that list too, but they are the minority; the common distance on a page
    of prose is the distance between two lines of one paragraph.

    Returns 0 when there is not enough of a page to measure, and every
    caller falls back to the old rule when it does.
    """
    boxes = [line["box"] for line in lines]
    order = sorted(range(len(boxes)), key=lambda i: boxes[i][1])
    steps = []
    for place, i in enumerate(order):
        x, y, w, h = boxes[i]
        nearest = None
        for j in order[place + 1:]:
            bx, by, bw, bh = boxes[j]
            if by <= y:
                continue
            if bx + bw <= x or x + w <= bx:       # beside it, not under it
                continue
            if abs(bx - x) > max(w, bw) * indent_tolerance:
                continue
            if abs(bh - h) > max(h, bh) * 0.35:
                continue
            if nearest is None or by - y < nearest:
                nearest = by - y
        if nearest:
            steps.append(nearest)
    if len(steps) < ENOUGH_PITCHES:
        return 0
    steps.sort()
    # The tightest spacing the page uses more than once.
    #
    # Not a percentile of the whole list, which is what this was and what
    # made it wrong on any page with a table on it. Every distance down to
    # the next line is in that list: the lines inside a paragraph, the gap
    # between two paragraphs, the height of a table row, the space under a
    # heading. On a page whose paragraphs run to two lines — which is what
    # a dense script gives you — the paragraph spacing is a *minority* of
    # the list, and a percentile lands on the row height instead. Every
    # paragraph on the page was then joined to the next one, and every
    # column of a table was read as a paragraph of prose.
    #
    # The lines inside a paragraph are the closest together anything on a
    # page gets, and there is always more than one of them. So: walk up
    # from the smallest distance and take the first one that a group of
    # lines actually shares. A single tight gap is a misread box and is
    # stepped over.
    least = max(2, int(len(steps) * 0.1))
    for value in steps:
        near = sum(1 for step in steps if value <= step <= value * 1.1)
        if near >= least:
            return value
    return steps[len(steps) // 2]


def _short_item(text):
    """A line short enough to be a label on its own: at most four words
    and 32 characters, or twelve characters of a language written without
    spaces. A line of running text is longer than that."""
    text = str(text or "").strip()
    cjk = sum(1 for c in text if 0x3040 <= ord(c) <= 0x9FFF
              or 0xAC00 <= ord(c) <= 0xD7AF)
    if cjk:
        return len(text.replace(" ", "")) <= 12
    return len(text.split()) <= 4 and len(text) <= 32


_FOOTNOTE = re.compile(u"\\[\\d{1,3}\\]|[\u00b9\u00b2\u00b3\u2070-\u2079]")


def _footnote_heights(line, h, other, oh):
    """The heights of two lines as their text is, not as a raised footnote
    mark makes them. "Kulturen.[6]" read as a line half again as tall as the
    one above it - the [6] sits above the line - and the last line of the
    paragraph went off to be translated on its own ("…consists of dozens
    of" / "from various ethnic groups and cultures")."""
    if h > oh * 1.1 and _FOOTNOTE.search(line.get("text", "")):
        h = oh
    elif oh > h * 1.1 and _FOOTNOTE.search(other.get("text", "")):
        oh = h
    # The same for a line of a character or two that ends a paragraph:
    # "い。" and "す。" have no tall character in them, so their box is
    # shorter than the line above, and they were left on the page
    # untranslated under their translated paragraph.
    if h < oh and len("".join(str(line.get("text", "")).split())) <= 3:
        h = oh
    elif oh < h and len("".join(str(other.get("text", "")).split())) <= 3:
        oh = h
    return h, oh


def group_paragraphs(lines, gap_factor=0.75, indent_tolerance=0.25,
                     pitch=None):
    """Group OCR lines that belong to the same paragraph.

    Translating each line on its own gives the engine no context: 实拍 alone
    becomes "Actual Shot", where inside a sentence it resolves to "real shot
    of". Sending a whole paragraph in one piece produces markedly better
    wording — and lets the result be laid out across the whole block.

    Lines join when they are vertically adjacent, similarly indented, and of
    similar height. A list of separate rows keeps its rows apart.

    A line that begins with a list marker begins a paragraph, whatever the
    spacing says. Two items of a numbered list are adjacent, identically
    indented and the same height — every test for "these are one wrapped
    paragraph" says yes — so they were joined, translated as one run of
    prose, and laid out as one dense block. The numbering survived inside
    it and the structure did not:

        1. 入口一：...            1. 진입점 1: ... 2. 진입점 2: ...
        2. 入口二：...     ->     (one paragraph, one box, half the size)

    It made the cramping worse everywhere it happened, because one box then
    had to hold what the page gave two.

    Adjacency is measured two ways and either will do: against the height
    of the box, which is what it always was, and against the spacing of
    this page's own lines, which is what `line_pitch` measures and is the
    one that works on a page whose boxes are tighter than its type. Pass
    `pitch` to reuse a measurement already taken; 0 turns it off.
    """
    if pitch is None:
        pitch = line_pitch(lines, indent_tolerance)
    order = sorted(range(len(lines)), key=lambda i: (lines[i]["box"][1],
                                                     lines[i]["box"][0]))
    groups = []
    for index in order:
        x, y, w, h = lines[index]["box"]
        best = None
        if starts_a_list_item(lines[index].get("text", "")):
            groups.append([index])
            continue
        # A heading is bold and the paragraph under it is not, which is
        # the only thing separating the two — same margin, same size, one
        # line apart. See `weigh_lines`.
        if lines[index].get("heavy"):
            groups.append([index])
            continue
        for group in groups:
            px, py, pw, ph = lines[group[-1]]["box"]
            gap = y - (py + ph)
            # A line that starts above the previous one's bottom is either
            # beside it — on the same row — or just tightly set. Only the
            # first of those is a reason to skip it.
            #
            # This used to be `gap < 0`, and a tightly set page broke it.
            # Chinese is commonly set with each line's box running a pixel
            # or two into the next — the box holds the full height of the
            # tallest glyph, and the lines are pitched closer than that —
            # so every line after the first looked like it was sitting
            # beside the one above rather than under it. Nothing joined.
            # Each paragraph's last line went off to be translated on its
            # own, which is half a word ("户个性化需求" is the second half of
            # 用户), and was then drawn in a box as narrow as that short
            # line, so the Korean came back stacked one word to a line.
            #
            # Overlapping by more than half a line is the same row. A
            # sliver is the next line down.
            if gap < -0.5 * min(h, ph):
                continue
            gap = max(0, gap)
            close = gap <= max(ph, h) * gap_factor
            if pitch and gap <= max(ph, h) * WIDEST_GAP:
                close = close or (y - py) <= pitch * PITCH_SLACK
            if not close:
                continue
            # Against the narrower of the two, not the wider. A quarter
            # of the *wide* one is a large number of pixels, and on a page
            # in columns it is enough to reach a caption in the column
            # next door that happens to sit a little lower — which is
            # then joined to this paragraph and translated as part of its
            # sentence. The narrower box is the one whose left edge the
            # indent is actually a fraction of.
            if abs(x - px) > min(pw, w) * indent_tolerance:
                continue
            h_, ph_ = _footnote_heights(lines[index], h,
                                        lines[group[-1]], ph)
            if abs(h_ - ph_) > max(h_, ph_) * 0.35:
                continue
            # A different size and a different colour: a heading and the
            # text under it, however close together. Either alone is not
            # enough - a line with no descenders is shorter, and a line
            # full of links reads as blue.
            ca = lines[group[-1]].get("ink_colour")
            cb = lines[index].get("ink_colour")
            if ca and cb and abs(h_ - ph_) > max(h_, ph_) * 0.18 and \
                    sum(abs(a - b) for a, b in zip(ca, cb)) > 120:
                continue
            if lines[group[-1]].get("heavy") and not lines[index].get("heavy"):
                continue          # the heading above; this is its text
            if _short_item(lines[group[-1]].get("text", "")) and \
                    _short_item(lines[index].get("text", "")):
                # Two short lines one under the other are a list - a menu,
                # a column of labels - not a paragraph wrapped after three
                # words. Joined, "一休.comレストラン" and "ふるさと納税" went
                # to the engine as one phrase and came back as one.
                continue
            if _ends_cjk_sentence(lines[group[-1]].get("text", "")):
                # Chinese and Japanese lists and notices put each item on
                # its own line ending in 。 or ；, often with its number
                # read off or missing. Joined, four items went to the engine
                # as one paragraph and were shared back over the lines by
                # width - "1. …data loss during / 2. maintenance. This…".
                # Breaking at the end of a sentence costs nothing even when
                # it was a wrapped line: the sentence is whole either way.
                continue
            best = group          # keep looking; the last match is nearest
        # Every open group is considered, not just the previous line. In two
        # columns the previous line in reading order belongs to the *other*
        # column, so comparing only against it merges the columns together.
        if best is not None:
            best.append(index)
        else:
            groups.append([index])
    return _unwrap_lists(lines, groups)


# What share of a block's lines have to reach its right margin before the
# block is a sentence rather than a list.
#
# Wrapping is what makes a paragraph: every line but the last runs to the
# measure and stops. A list has no measure — each item is as long as it
# is, and the right edges scatter.
#
# This is the only thing that separates the two. A shop's navigation menu,
# a table of contents, an index, an address block, a page of verse: the
# items sit at one margin, one line apart, in one size, and every test for
# "these are one wrapped paragraph" says yes. So they were joined, and the
# engine was handed "Sports Shoes Hiking Boots Sneakers Flip-Flops Water
# Shoes All Products" as though it were a sentence. Which way any one
# block fell came down to a pixel of recogniser noise: on one menu the
# swimwear column came back as six links and the accessories column beside
# it, laid out identically, came back as one run of prose.
#
# Counted as a share rather than measured as a spread, and that is the
# part worth keeping. A spread is the distance between the furthest two
# edges, so a single short line anywhere in a block decides the whole
# question — and a heading glued to the front of a paragraph is exactly
# that, which made twenty lines of wrapped German look like a list the
# moment the page was small enough that the heading went undetected. A
# share does not care about one outlier.
#
# Measured over five pages. Every wrapped block of the contract has all
# of its lines at the margin, and the Chinese newsletter's worst is 0.83.
# A shop menu's best block is 0.67 and most sit at 0.33; a page of verse
# at 0.33 and 0.57. The gap between the two kinds is wide enough that the
# threshold did not have to be chosen carefully.
REACHES_THE_MARGIN = 0.7

# And how close to the margin a line has to end to count as reaching it —
# a share of the block's own width, because the last word of a line is as
# long as it is.
AT_THE_MARGIN = 0.15


def _unwrap_lists(lines, groups):
    """Break apart the blocks whose lines do not share a right margin.

    The last line is never counted: the last line of a paragraph is short
    because the paragraph ended, which is the one short line that means
    nothing at all. Blocks of fewer than three lines are left alone —
    two edges are not a margin.
    """
    out = []
    for group in groups:
        if len(group) < 3:
            out.append(group)
            continue
        edges = [lines[i]["box"][0] + lines[i]["box"][2] for i in group[:-1]]
        left = min(lines[i]["box"][0] for i in group)
        margin = max(edges)
        width = max(1.0, margin - left)
        reaches = [margin - e <= AT_THE_MARGIN * width for e in edges]
        # A line that stops short because the next word would not have fit
        # is wrapped all the same: German and other languages with long
        # words have ragged margins ("Hiermit kündige ich meine" /
        # "Hausratversicherung mit ..."). Judged by the width of the next
        # line's first word, estimated from that line's own width.
        for k, index in enumerate(group[:-1]):
            if reaches[k]:
                continue
            nxt = lines[group[k + 1]]
            text = str(nxt.get("text", "")).strip()
            if not text:
                continue
            first = text.split()[0] if " " in text else text[:1]
            guess = nxt["box"][2] * (len(first) + 1) / float(len(text))
            if guess > margin - edges[k]:
                reaches[k] = True
        if sum(reaches) >= REACHES_THE_MARGIN * len(edges):
            out.append(group)
            continue
        # The first line short and every line after it full is not a list.
        # It is a heading with its paragraph under it — "2. 场景体验：可变座
        # 舱设计" and then the text of point 2 — and the heading is short
        # because headings are. Counting it as one more line that missed
        # the margin broke the whole block into single lines, and the
        # paragraph's last line then went off to be translated on its own:
        # half a word ("户个性化需求" is the end of 用户) in a box as narrow
        # as that one short line, so the Korean came back stacked one word
        # to a line. The heading goes on its own and the paragraph stays
        # a paragraph.
        if not reaches[0] and len(reaches) > 1 and all(reaches[1:]):
            out.append([group[0]])
            out.append(group[1:])
            continue
        out.extend([index] for index in group)
    return out


# Below this share of letters a line is a figure rather than a sentence.
# Measured over six pages in six languages: the lines below it are meter
# numbers, dates, currency columns and the recogniser's own noise, and
# every line above it is prose. Nothing in between needed a judgement.
LETTERS_IN_LANGUAGE = 0.2


def is_language(text):
    """Is there anything here for a translation engine to do?

    A column of amounts, a meter number, a date, a reference code: sending
    these to an engine cannot improve them and can corrupt them, which is
    the same trade the app already makes for email and web addresses. A
    corrupted number is worse than an untranslated one, because it still
    looks like a number and nothing on the page says it changed.
    """
    stripped = "".join(str(text or "").split())
    if not stripped:
        return False
    letters = sum(1 for ch in stripped if ch.isalpha())
    if not letters:
        return False
    # A share, and nothing about how long the letter runs are. Asking for a
    # run of two was wrong in both directions at once: it threw away a line
    # of Chinese, where one character is a word, and it threw away a line
    # reading "a" or "I", where one letter is one.
    return letters >= len(stripped) * LETTERS_IN_LANGUAGE


def held_back(lines):
    """The lines that must not be translated and must not be drawn over.

    Three kinds, and they have to be decided in one place because two
    different places deciding it separately is what broke the page. A box
    too small to hold writing; a line that is figures rather than language,
    which an engine can only spoil; and a line carrying an email or web
    address, which is left showing in the original because a recogniser
    that turns one letter of an address into another has produced something
    that still looks like an address and goes somewhere else.

    Not judged on the line's own text being empty. A caller may hand over
    boxes with no text on them at all and supply the translations
    separately, and holding those back would leave it with nothing drawn.
    """
    stamped = stamped_addresses(lines)
    held = set()
    for index, line in enumerate(lines):
        text = str(line.get("text", "") or "").strip()
        try:
            _x, _y, w, h = line["box"]
        except Exception:
            held.add(index)
            continue
        if w < 8 or h < 6:
            held.add(index)
        elif line.get("on_a_picture"):
            # Text in a photograph, not text on a page. Covering it would
            # paint an opaque box across the picture, and what would be
            # written in the box is a translation of whatever the
            # recogniser made of a wordmark it cannot read.
            held.add(index)
        elif text and not is_language(text):
            if not _ends_a_sentence_above(lines, index):
                held.add(index)
        elif text and carries_an_address(text, ignore=stamped):
            held.add(index)
    return held


_OPEN_END = re.compile(r"[^.!?:;。！？：；)\]]\s*$")


def _ends_a_sentence_above(lines, index):
    """Whether line `index` - figures, no words - is the end of the
    sentence on the line above: "...lag bei etwa" / "2.500-3000€.". Held
    back on its own, it cut the sentence short: the paragraph went to be
    translated without its last words and came back ending in "…"."""
    if index <= 0:
        return False
    try:
        line, above = lines[index], lines[index - 1]
        text = str(line.get("text", "") or "").strip()
        before = str(above.get("text", "") or "").strip()
        if not text or not before or not is_language(before):
            return False
        if not _OPEN_END.search(before) or not text.endswith((".", "!", "?")):
            return False
        x, y, _w, h = line["box"]
        ax, ay, _aw, ah = above["box"]
        gap = y - (ay + ah)
        return -0.5 * h <= gap <= 1.2 * max(h, ah) and \
            abs(x - ax) <= 1.5 * max(h, ah)
    except Exception:
        return False


# How many lines have to be stacked before the stack is a column of
# running text rather than a cell of a table.
#
# Two is not enough: a table cell that wraps onto a second line is
# ordinary. Three in a row, each starting at the same indent, each one
# line-gap below the last, is a paragraph — a table that produced that by
# accident would have to have three consecutive rows of exactly one line
# each, aligned to the pixel, with no more space between rows than there
# is between the lines inside a paragraph.
RUNNING_TEXT = 3


# What share of the room on its row a line has to use before it is a
# sentence rather than a value in a column.
#
# A line of prose fills its column — that is what wrapping means. A cell
# holds a word, a date or an amount and uses a fifth of the space it has.
# Measured on the corpus and on the twelve-language pages: prose lines sit
# at 0.85 to 1.0 of the room up to their neighbour, cells at 0.1 to 0.3.
FILLS_ITS_ROOM = 0.6


def _fills_its_room(lines, share=FILLS_ITS_ROOM):
    """Lines that use most of the width available to them on their row.

    The room is the distance to whatever is next along the row. For the
    line at the end of the row there is nothing next, and the page edge is
    the wrong answer: the last cell of a table row fills the space up to
    its own right-hand end by definition, and so does the last column of a
    page of prose. What separates them is the *rhythm* of the row — how
    far apart the things on it start. Two columns of prose start four
    hundred pixels apart and are three hundred and seventy-five wide;
    three cells of a table start three hundred apart and are sixty wide.
    So the last one along is given the row's own spacing as its room.
    """
    boxes = [tuple(line["box"]) for line in lines]
    if not boxes:
        return set()
    edge = max(x + w for x, _y, w, _h in boxes)
    wide = set()
    for index, (x, y, w, h) in enumerate(boxes):
        band = []
        for other, (bx, by, bw, bh) in enumerate(boxes):
            if other == index:
                continue
            shared = min(y + h, by + bh) - max(y, by)
            if shared > 0.5 * max(1, min(h, bh)):
                band.append(bx)
        beyond = [bx for bx in band if bx > x]
        if beyond:
            room = min(beyond) - x
        elif band:
            starts = sorted(band + [x])
            steps = sorted(b - a for a, b in zip(starts, starts[1:]))
            room = steps[len(steps) // 2] if steps else edge - x
        else:
            # Nothing is beside it at all, so nothing about a table can be
            # decided from it either — `cells_in` only ever asks about
            # lines that share their row with something.
            room = max(1, edge - x)
            if room <= w:
                continue
        if w >= share * max(1, room):
            wide.add(index)
    return wide


def running_text(lines, least=RUNNING_TEXT, groups=None):
    """The lines that are prose rather than cells of a table.

    Two questions, and either answer will do.

    **Is it in a run?** `group_paragraphs` already knows how to tell "the
    next line of this paragraph" from "the next thing down the page": same
    indent, one line-gap below, the same size. Three of those in a row is
    a paragraph.

    **Or does it fill its row?** Three was not enough on its own, and the
    reason is worth writing down: a dense script says in two lines what
    English says in four, so a Chinese, Japanese or Arabic page is full of
    two-line paragraphs, and two-line paragraphs in two columns look
    exactly like a table of two rows. Eight of the twenty-two paragraphs
    on the test page were being cut in half by that alone.

    What a paragraph does and a table cell does not is fill the width it
    has. A line of prose runs to the edge of its column because that is
    what wrapping means; a cell holds a word or a date and uses a fifth of
    the space. The short last line of a paragraph is carried in by the
    line above it, which is wide.
    """
    if groups is None:
        groups = group_paragraphs(lines)
    wide = _fills_its_room(lines)
    keep = set()
    for group in groups:
        if any(index in wide for index in group):
            keep.update(group)
    return keep


def cells_in(lines, overlap=0.5, least=RUNNING_TEXT):
    """Which of these lines are cells of a table rather than lines of prose.

    A line of prose has the width of its column to itself. A cell of a
    table has something else beside it on the same row — that is what makes
    it a cell, and it is visible in the geometry without knowing anything
    about tables.

    It matters because everything the layout does to a line is wrong for a
    cell. A line that grows pushes the next line down, which is right for a
    paragraph and ruinous for a row: the label of a row ends up beside the
    value of the row below it. A line is gathered with the line under it
    into a paragraph, which is right for prose and turns a column of
    amounts into a sentence. A line may reach right into the space beside
    it, which is right when that space is empty and paints over the next
    cell when it is not.

    Two lines share a row when they overlap vertically by more than half
    the shorter of them, *and* do not overlap horizontally at all. The
    second half is what stops a line and its own continuation from being
    read as two cells.

    And a page in columns satisfies both of those on every single line.

    That is the fault this rule had until it was measured. The third line
    of the left column of a newsletter has the third line of the middle
    column beside it, at the same height, not touching — which is the
    definition above, word for word. On the six pages of the corpus it
    called between 55% and 90% of every line a table cell, and everything
    downstream then did the table thing to a page of prose: each line
    translated alone, so the engine saw "가능하다" with no sentence around
    it and returned "It is pos sible."; each line sized against its own
    box and never allowed to reach into the empty space beside it, so the
    text came back cramped; and each line pinned exactly where it was
    found, because a cell may not move and may not move anything else. A
    translation that is longer than its original — which is most of them —
    then had nowhere to go and was drawn over its neighbour. Fifty-eight
    pairs of blocks on top of each other across six pages, and the pages
    with the most were the ones the user could not read.

    What tells the two apart is what is *underneath* the line. A cell of a
    table has the next row under it, a row-height away. A line in a column
    of prose has the rest of its own paragraph under it, one line-gap
    away, at the same indent — three, five, ten lines of it. So a line
    caught in a run like that is not a cell, whatever is beside it.
    """
    boxes = [tuple(line["box"]) for line in lines]
    prose = running_text(lines, least)
    order = sorted(range(len(boxes)), key=lambda i: boxes[i][1])
    cells = set()
    band = []
    for index in order:
        _x, y, _w, h = boxes[index]
        if band:
            top = min(boxes[i][1] for i in band)
            bottom = max(boxes[i][1] + boxes[i][3] for i in band)
            shared = min(y + h, bottom) - max(y, top)
            if shared <= overlap * max(1, min(h, bottom - top)):
                band = []
        if not band:
            band = [index]
            continue
        band.append(index)

        for a in band:
            for b in band:
                if a >= b:
                    continue
                ax, _ay, aw, _ah = boxes[a]
                bx, _by, bw, _bh = boxes[b]
                if ax + aw <= bx or bx + bw <= ax:
                    cells.add(a)
                    cells.add(b)
    # Judged one line at a time, on its own evidence. A table whose first
    # cell wraps over four lines and whose second is a date is a real
    # thing, and the four-line cell is prose however the date is set.
    #
    # And the first line of a paragraph is not a cell because a box in the
    # next column happens to sit level with it: with the paragraph's own
    # prose starting straight underneath, at the same indent, it is that
    # paragraph's first line. Taken for a cell it was translated on its own
    # ("Hiermit kündige ich meine" without the rest of its sentence).
    def opens_paragraph(index):
        x, y, w, h = boxes[index]
        for other in prose:
            ox, oy, ow, oh = boxes[other]
            if abs(ox - x) <= 0.25 * max(1, min(w, ow)) and \
                    0 <= oy - (y + h) <= 0.8 * max(h, oh) and \
                    abs(oh - h) <= 0.35 * max(h, oh):
                return True
        return False
    # Likewise a line with another line tight underneath it - same indent,
    # same size, less than half a line between - is a wrapped line (a
    # two-line heading), however the column beside it lines up. Rows of a
    # table stand further apart than lines of text.
    def wrapped(index):
        x, y, w, h = boxes[index]
        for other, (ox, oy, ow, oh) in enumerate(boxes):
            if other == index:
                continue
            if abs(ox - x) > 0.25 * max(1, min(w, ow)) or \
                    abs(oh - h) > 0.35 * max(h, oh):
                continue
            gap = oy - (y + h) if oy >= y else y - (oy + oh)
            if 0 <= gap <= 0.5 * max(h, oh):
                return True
        return False
    return {index for index in cells
            if index not in prose and not opens_paragraph(index)
            and not wrapped(index)}


def paragraphs_for(lines):
    """`(groups, held)` — which lines belong together, decided once.

    This used to be decided twice, and the two answers were allowed to
    differ. Translation grouped the raw lines and split each translated
    paragraph back across them; the overlay then grouped them again, from
    boxes that had since been shrunk to their ink and with the held-back
    lines missing, and joined whatever pieces landed in each of *its*
    groups. When the two groupings agreed the pieces reassembled into the
    sentence they came from and nobody could tell. When they disagreed the
    page filled with half-sentences that began nowhere — and a line held
    back in the middle of a paragraph took its share of the words with it,
    so a quarter of that paragraph was simply not on the page.

    It read as a bad translation. The translation was fine; it had been
    cut up and the pieces put back in the wrong boxes.

    A held-back line also *breaks* a paragraph rather than being skipped
    over inside one. It has to: the paragraph above it and the paragraph
    below it are covered as one rectangle, and a rectangle spanning both
    paints over the address that was deliberately left showing.
    """
    held = held_back(lines)
    # Text at an angle is a label of its own: a column heading set
    # diagonally over a table, a title running up a poster. Grouped with
    # its neighbours it was translated as one sentence made of all of
    # them. See app/slant.py.
    tilted = [i for i in range(len(lines))
              if i not in held and lines[i].get("quad")]
    keep = [i for i in range(len(lines))
            if i not in held and not lines[i].get("quad")]
    # A cell is a paragraph of one. Gathering a column of table cells into
    # a paragraph sends "8,34 € 1.166,34 € 117,66 €" to the engine as a
    # sentence and lays the answer out as one block of prose.
    cells = cells_in([lines[i] for i in keep])
    prose = [j for j in range(len(keep)) if j not in cells]
    groups = [[keep[prose[j]] for j in group]
              for group in group_paragraphs([lines[keep[j]] for j in prose])]
    groups += [[keep[j]] for j in sorted(cells)]
    groups += [[i] for i in tilted]
    # Back into the order the lines appear in, so a paragraph is laid out
    # where its first line was.
    groups.sort(key=lambda g: min(g))
    return groups, held


# Codes the engine dropped altogether, most recent first, for the log and
# for anything that wants to tell the reader. Not raised: a translation
# that is right about every word and has lost a reference number is still
# worth showing, and saying nothing about it is the part that is not.
lost_identifiers = []

# And what the *last* translation lost, so the overlay can say so on the
# page rather than in a file. A running list cannot answer that: it holds
# whatever earlier pages lost too.
last_lost = []


def _note_lost(tokens):
    lost_identifiers[:] = list(tokens) + lost_identifiers[:20]


# Notes a language model sometimes writes into its answer instead of a
# translation: "[unclear - possibly referring to a specific payment method]".
_ENGINE_NOTE = re.compile(
    r"\s*[\[(](?:unclear|note|translator'?s note|untranslatable|"
    r"possibly|original|sic)\b[^\])]*[\])]", re.I)


def _misplaced(source, answer):
    """Is this answer not the translation of this block? Far too long -
    the next block's text was put into it ("PayPal Ratenzahlung" came back
    as the heading and the whole paragraph under it, drawn at heading size
    over the page) - or empty where there was text to translate."""
    source = str(source or "").strip()
    answer = str(answer or "").strip()
    if not source:
        return False
    if not answer:
        return len(source) >= 8
    # One Chinese, Japanese or Korean character is a word's worth of
    # English, so those may grow twice as much again before it is odd.
    wide = sum(1 for ch in source if ord(ch) >= 0x2E80)
    ratio = 8 if wide * 2 > len(source) else 4
    return len(answer) > max(80, ratio * len(source) + 20)


def _misplaced_again(sent, translated, translator, target, source):
    """Blocks whose answer is not theirs, translated again on their own.
    The rest stand. Engine notes are taken out of every answer."""
    out = [_ENGINE_NOTE.sub("", str(a or "")).strip() if a else a
           for a in translated]
    redo = [i for i, src in enumerate(sent[:len(out)])
            if _misplaced(src, out[i])][:6]
    if not redo:
        return out

    def ask(i):
        try:
            again = translator.translate(sent[i], target=target,
                                         source=source or "auto")
            return i, _ENGINE_NOTE.sub("", str(again or "")).strip()
        except Exception:
            return i, None
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=len(redo)) as pool:
        for i, again in pool.map(ask, redo):
            if again and not _misplaced(sent[i], again):
                out[i] = again
    return out


def _shouting(text):
    """Whether `text` is written in capitals: six letters or more, nearly
    all of them capitals, and a word of four letters or more - not a code
    or an abbreviation."""
    letters = [c for c in str(text or "") if c.isalpha()]
    if len(letters) < 6:
        return False
    upper = sum(1 for c in letters if c.isupper())
    if upper < 0.9 * len(letters):
        return False
    return any(len(w) >= 4 for w in re.findall(r"[^\W\d_]+", text))


def _sentence_case(text):
    text = str(text or "")
    out, first = [], True
    for ch in text.lower():
        if first and ch.isalpha():
            out.append(ch.upper())
            first = False
        else:
            out.append(ch)
    return "".join(out)


def translate_grouped(lines, translator, target, source="auto", groups=None,
                      progress=None):
    """Translate paragraph-by-paragraph, return one string per input line.

    `source` is the language named in the app, and it is passed on for
    the same reason the reader is told: every block of the page goes up
    as one request, so one badly-read block could skew the engine's
    detection for the whole page — and it was detecting on every snip
    even when the user had said what the language was.

    The engine sees whole paragraphs, which is what makes the wording good.
    The overlay still needs one string per box, so each translated paragraph
    is split back across its lines in proportion to their original widths —
    long lines get more of the text than short ones.

    The split is a convenience for callers that want a string per line. It
    is not how the overlay reassembles the paragraph: the whole translated
    paragraph is written onto every line of the group as `para_text`, and
    the group number onto every line as `para`, so the overlay lays out
    the sentence that came back from the engine rather than a reassembly
    of the pieces.
    """
    # `groups` lets a caller that has already grouped a larger page pass
    # its answer in. Grouping a slice of a page again from scratch loses
    # the context that told a table cell from a line of prose: a column of
    # four cells on their own looks like a paragraph, and was translated
    # and laid out as one, each row's label landing a row lower.
    if groups is None:
        groups, _held = paragraphs_for(lines)
    blocks = []
    for group in groups:
        blocks.append(" ".join(lines[i]["text"].strip() for i in group
                               if lines[i]["text"].strip()))
    # Speed, not quality, and that is the whole reason the distinction
    # exists. This is twenty short lines with somebody watching the screen
    # for them; the card path is one passage about to be read properly.
    # Choosing one engine for both gets one of them wrong every time.
    # List markers off before the engine sees them, and back on after.
    # "2、设计网" was read as "two design networks" and "1、" moved to the
    # end of its sentence. See `numbering`.
    markers, sent = numbering.split_all(blocks)
    # Text set all in capitals - a headline on a picture, a banner - is
    # sent in ordinary case and the answer put back in capitals. In
    # capitals the engine read "HANDTELLERGROSSES DESIGN" as a name and
    # handed it back, and "5 VOREINGESTELLTE" became "5 Preetermined";
    # as "Handtellergrosses design" it is "Hand-sized design".
    shouted = [_shouting(text) for text in sent]
    sent = [_sentence_case(text) if loud else text
            for text, loud in zip(sent, shouted)]
    extra = {}
    try:
        import inspect
        params = inspect.signature(translator.translate_lines).parameters
        if "blocks" in params:
            extra["blocks"] = True          # each block on its own
        if progress is not None and "progress" in params:
            # Each paragraph as it is done, finished the way the whole
            # page is finished below, for the page to be shown as it
            # fills in (see `progressive`).
            def told(gid, text):
                try:
                    fixed = _ENGINE_NOTE.sub("", str(text or "")).strip()
                    fixed, _lost = identifiers.repair(sent[gid], fixed)
                    if str(target or "").lower().startswith("ko"):
                        fixed = identifiers.korean_dates(sent[gid], fixed)
                    if shouted[gid]:
                        fixed = fixed.upper()
                    fixed = numbering.attach(markers[gid], fixed, target)
                    progress(gid, fixed)
                except Exception:
                    pass
            extra["progress"] = told
    except (TypeError, ValueError):
        pass
    translated = translator.translate_lines(
        sent, target=target, source=source or "auto",
        job=getattr(translator, "SPEED", None) or "speed", **extra)
    translated = _misplaced_again(sent, list(translated), translator,
                                  target, source)
    # Put back anything the engine retyped. A reference number, an account
    # number, an address: the reader of a document in a language they do
    # not have cannot check one of those against the sentence around it,
    # because they cannot read the sentence around it. See `identifiers`.
    translated, lost = identifiers.repair_all(sent, list(translated))
    if str(target or "").lower().startswith("ko"):
        translated = [identifiers.korean_dates(src, text)
                      for src, text in zip(sent, translated)]
    translated = [str(text or "").upper() if loud else text
                  for text, loud in zip(translated, shouted)]
    translated = numbering.attach_all(markers, translated, target)
    last_lost[:] = list(lost)
    if lost:
        _note_lost(lost)

    out = [""] * len(lines)
    for gid, (group, text) in enumerate(zip(groups, translated)):
        # The paragraph, whole, on every line of it. This is what the
        # overlay lays out; the per-line split below is for callers that
        # want one string per box.
        for index in group:
            try:
                lines[index]["para"] = gid
                lines[index]["para_text"] = text or ""
            except Exception:
                pass
        for index, part in split_over(lines, group, text or "").items():
            out[index] = part
    return out


def split_over(lines, group, text):
    """A paragraph's translation shared over its lines by their widths:
    {line index: part}. See translate_grouped."""
    if len(group) == 1:
        return {group[0]: text}
    widths = [max(1, lines[i]["box"][2]) for i in group]
    total = float(sum(widths))
    # Shared by words - or, for Chinese and Japanese, which are written
    # without spaces, by characters. By words, a Chinese translation was one
    # "word": the first line got all of it and the others none, and a line
    # with nothing of its own was taken for a line left as it was - the
    # rest of the paragraph stayed on the page in French under a Chinese
    # first line.
    raw = str(text or "")
    closed = sum(1 for c in raw if 0x3040 <= ord(c) <= 0x9FFF) > \
        0.3 * max(1, len(raw))
    words = list(raw) if closed else raw.split()
    joiner = "" if closed else " "
    parts = {}
    taken = 0
    for position, index in enumerate(group):
        if position == len(group) - 1:
            share = words[taken:]
        else:
            count = int(round(len(words) * widths[position] / total))
            count = max(1, min(count, len(words) - taken -
                               (len(group) - position - 1)))
            share = words[taken:taken + count]
            taken += count
        parts[index] = joiner.join(share)
    return parts


PAINT_EVERY = 0.35          # seconds between showing what is done so far
last_groups = []


def progressive(image, lines, translator, target, source, min_size,
                shown=None, every=PAINT_EVERY):
    """Translate and lay out a page, showing it as it fills in.

    `shown(blocks, height)` is called every `every` seconds, from a thread
    of its own, with the paragraphs finished so far laid out as they will
    be on the finished page: the rest are laid out with their own text as
    a stand-in, so a finished paragraph takes the room it will have at the
    end, and are then left out. The work is handed out top to bottom, so
    the page fills in from the top left. Returns (texts, blocks, height)
    for the finished page, exactly as translate_grouped and layout would.
    """
    import threading
    groups, _held = paragraphs_for(lines)
    # How the page was grouped, lines per paragraph, for the log: two
    # lines of one sentence translated apart come back as two half
    # sentences, and this says whether that is what happened.
    last_groups[:] = [len(g) for g in groups]
    done = {}
    lock = threading.Lock()
    finished = threading.Event()

    def told(gid, text):
        with lock:
            done[gid] = text

    pause = {"s": every}

    def paint():
        seen = 0
        # Never more than a third of the time spent laying out: on a slow
        # computer a whole-page layout takes a second or more, and laying
        # out again and again took that time from the translation itself.
        while not finished.wait(pause["s"]):
            with lock:
                ready = dict(done)
            if len(ready) == seen or not ready:
                continue
            seen = len(ready)
            try:
                copy = [dict(line) for line in lines]
                texts = [line.get("text", "") for line in copy]
                for gid, group in enumerate(groups):
                    text = ready.get(gid)
                    stand_in = " ".join(copy[i]["text"].strip()
                                        for i in group)
                    for i in group:
                        copy[i]["para"] = gid
                        copy[i]["para_text"] = text if text is not None \
                            else stand_in
                    if text is not None:
                        for i, part in split_over(copy, group,
                                                  text).items():
                            texts[i] = part
                began = time.time()
                blocks, tall = layout(image, copy, texts, target,
                                      min_size=min_size)
                pause["s"] = max(every, 2.0 * (time.time() - began))
                blocks = [b for b in blocks if b.get("para") in ready]
                if shown is not None and not finished.is_set():
                    shown(blocks, tall)
            except Exception:
                pass
    painter = None
    if shown is not None:
        painter = threading.Thread(target=paint, daemon=True,
                                   name="paint-as-done")
        painter.start()
    try:
        texts = translate_grouped(lines, translator, target, source=source,
                                  groups=groups, progress=told)
    finally:
        finished.set()
    if painter is not None:
        painter.join(timeout=2.0)
    blocks, tall = layout(image, lines, texts, target, min_size=min_size)
    return texts, blocks, tall


_WIDTHS = {}
_WIDTHS_MAX = 60000


def _width_of(draw, text, font):
    """The width of `text` in `font`, remembered: a page's layout asks for
    the same words at the same sizes thousands of times while it tries
    sizes, and asking the font each time was half the layout's time."""
    key = (getattr(font, "path", None) or id(font),
           getattr(font, "size", None), text)
    got = _WIDTHS.get(key)
    if got is not None:
        return got
    try:
        got = draw.textlength(text, font=font)
    except Exception:
        return len(text) * getattr(font, "size", 10) * 0.6
    if len(_WIDTHS) >= _WIDTHS_MAX:
        _WIDTHS.clear()
    _WIDTHS[key] = got
    return got


def _trim_to_width(draw, text, font, max_width):
    """Shorten with an ellipsis rather than letting text run off the edge."""
    if _width_of(draw, text, font) <= max_width:
        return text
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if _width_of(draw, text[:middle] + "…", font) <= max_width:
            low = middle
        else:
            high = middle - 1
    return (text[:low].rstrip() + "…") if low else text[:1]


# The smallest text worth drawing. Not a preference — a limit. Below this
# the renderer is still producing pixels and nobody is reading them, and
# every route that ends in "make it smaller" has to stop somewhere.
#
# Seven, not eleven. Eleven was a guess and the guess was wrong in a way
# that measured badly: a business letter is set in nine point, so an
# eleven point floor did not protect anything, it *inflated* every line on
# the page by a fifth. Nothing then fitted where it came from, every block
# pushed the one below it down, and a page snipped whole came back three
# times the height of the thing that was snipped. The document was already
# readable at nine point — it is a document, that is the size documents
# are — and making it bigger was never a readability improvement, only a
# layout demolition.
FLOOR = 7

# How much smaller than the original a translation may be set before the
# answer stops being "shrink it". This is what actually protects
# legibility, because it is relative to the document rather than to a
# number somebody picked: below it, the block takes more room instead.
#
# It was 0.75 — a quarter of the size — and that is what "the translation
# comes out too cramped" was. Measured over the six document pages and
# the nine language pages, at 0.75 nearly a quarter of all blocks were set
# at four fifths of the document's own size or less, and the worst of them
# at 69%. Set against a page of ordinary type that reads as damage.
#
# What buying it back costs is height, and only on the pages that were
# cramped: a dense page in a script that says in two lines what English
# says in four gets taller — the worst of the six goes from 170% of the
# original to 225% — and the other three do not move at all. That is the
# trade every tool that keeps text readable makes, Google's own page
# translation included: it does not shrink the words, the page gets
# longer. The overlay scrolls; letters at 69% cannot be made bigger by
# scrolling.
SHRINK_LIMIT = 0.90

# How much taller than the page's own text a line may claim to be before
# it is treated as a mistake rather than a headline. A heading is two or
# three times the body around it; nothing on a page of prose is five, and
# a box that says otherwise is a recogniser that swallowed the space above
# the line or ran two lines together. Since the font size is taken
# straight from the height of the box, one of those draws text five times
# too big, which then wraps over six lines and shoulders a screenful of
# the page out of the way.
TALLEST_LINE = 3.0

# Where a capture stops being a selection and starts being a page. Measured
# in logical points across, so it means the same thing on any display. An
# A4 page is 595 points wide, which is why the boundary sits below it: a
# whole page is a page, however modest its width in points.
SMALL_CAPTURE = 280
LARGE_CAPTURE = 560
# The smallest the text may be *allowed* to end up at each end. This is a
# floor and only ever a floor — it never enlarges text that was already
# bigger. A sentence grabbed on its own has room to be set comfortably; a
# page has a layout to keep and is read by zooming into it.
SMALL_TARGET = 11
LARGE_TARGET = FLOOR


def size_policy(width_points):
    """(floor, target) for an overlay covering this much of the screen.

    One setting cannot serve both ends of this. Grabbing one sentence and
    grabbing the whole screen are different requests: the first wants to be
    readable where it sits, the second wants to still look like the page it
    replaced, and the way to read *that* is to zoom, which the overlay
    already does on ctrl and the wheel.

    So the size follows the size of the capture rather than a preference.
    A selection gets comfortable text. A page gets text that fits, never
    below the floor, and a zoom to read it with.
    """
    try:
        width = float(width_points)
    except Exception:
        width = LARGE_CAPTURE
    # NaN compares false against everything, so it slips past both ends of
    # the range below and reaches round() as a number that has no integer.
    if width != width:
        width = LARGE_CAPTURE
    if width <= SMALL_CAPTURE:
        target = SMALL_TARGET
    elif width >= LARGE_CAPTURE:
        target = LARGE_TARGET
    else:
        span = float(LARGE_CAPTURE - SMALL_CAPTURE)
        share = (width - SMALL_CAPTURE) / span
        target = SMALL_TARGET - share * (SMALL_TARGET - LARGE_TARGET)
    return FLOOR, max(FLOOR, int(round(target)))


def columns(lines, page_width, min_gutter=None):
    """Group line indexes into columns, left to right.

    The renderer's most load-bearing assumption is that the space to the
    right of a line is empty and free to spill into. On one column of prose
    that is true and is what lets a longer translation take the room it
    needs. On a letter with an address block beside the body it is false,
    and the cost is not subtle: the body's covering rectangles paint over
    the column next to it, and the vertical room for each line gets measured
    against a line in the *other* column that happens to sit slightly lower.

    Columns are found as vertical gutters — bands of x that no line crosses.
    That is the same thing a reader's eye does and it needs no knowledge of
    what the document is.
    """
    if not lines:
        return []
    boxes = [line["box"] for line in lines]
    if min_gutter is None:
        # Wide enough not to trip on the space between two words, narrow
        # enough to catch a tight two-column layout. Tied to the text's own
        # size rather than the page's, so a dense page and a large-print one
        # are judged the same way.
        heights = sorted(box[3] for box in boxes)
        median_h = heights[len(heights) // 2] or 1
        min_gutter = max(int(median_h * 1.5), int(page_width * 0.02), 8)

    covered = [False] * (int(page_width) + 1)
    for x, _y, w, _h in boxes:
        left = max(0, int(x))
        right = min(int(page_width), int(x + w))
        for px in range(left, right + 1):
            covered[px] = True

    # Walk the page and cut wherever an uncovered band is wide enough.
    cuts, run_start = [], None
    for px, is_covered in enumerate(covered):
        if not is_covered:
            if run_start is None:
                run_start = px
        else:
            if run_start is not None and px - run_start >= min_gutter:
                cuts.append((run_start, px))
            run_start = None
    if run_start is not None and len(covered) - run_start >= min_gutter:
        cuts.append((run_start, len(covered)))

    # The bands at the very edges are margins, not gutters between columns.
    inner = [cut for cut in cuts if cut[0] > 0 and cut[1] < len(covered)]
    if not inner:
        return [{"left": 0, "right": int(page_width),
                 "indexes": list(range(len(lines)))}]

    edges = [0] + [(a + b) // 2 for a, b in inner] + [int(page_width)]
    out = []
    for i in range(len(edges) - 1):
        out.append({"left": edges[i], "right": edges[i + 1], "indexes": []})
    for index, (x, _y, w, _h) in enumerate(boxes):
        centre = x + w / 2.0
        placed = False
        for column in out:
            if column["left"] <= centre < column["right"]:
                column["indexes"].append(index)
                placed = True
                break
        if not placed:
            out[-1]["indexes"].append(index)
    return [column for column in out if column["indexes"]]


def column_for(index, groups):
    """The column holding this line, or None."""
    for column in groups:
        if index in column["indexes"]:
            return column
    return None


def _tiers(lines, tolerance=0.28):
    """Group line indexes by original text height.

    A page has a small number of real text sizes — a headline, a subhead,
    body. Recovering those groups is what lets every body line share one
    size while the headline stays a headline.
    """
    order = sorted(range(len(lines)), key=lambda i: _line_unit(lines[i]))
    groups, current, reference = [], [], None
    for index in order:
        height = _line_unit(lines[index])
        if reference is None or abs(height - reference) <= reference * tolerance:
            current.append(index)
            reference = height if reference is None else reference
        else:
            groups.append(current)
            current, reference = [index], height
    if current:
        groups.append(current)
    return groups


# How far a block may spill past the gap under its line before the text is
# trimmed instead. Some overlap with what is below beats an ellipsis: the
# thing underneath is about to be replaced by its own translation anyway,
# and words that are covered can still be read by moving the eye, while
# words that were never drawn are gone.
OVERFLOW = 1.75


# The mark drawn round a finished overlay: the same shape the snip frame
# uses, which is the same shape as the icon.
#
# Without it the overlay is a rectangle of translated text sitting flush
# against the page it replaced, and there is nothing to say where the
# translation stops and the original starts — it reads as the page having
# changed rather than as something drawn over it. You drag the mark, and
# what comes back is inside the same mark: one object, twice.
MARK_RADIUS = 14
MARK_GRIP = 18
MARK_THICK = 6
# Room between the mark and the translation inside it. Drawn hard against
# the edge, the frame touches whatever line happens to reach the border
# and reads as a box squeezing the text rather than one holding it.
MARK_PAD = 12


def pad_out(image, pad=None):
    """A copy with `pad` of the page's own background round the outside.

    The margin is filled from the image's own border rather than with
    white or grey: this sits over a real page, and a light band round a
    dark article would announce itself as a mistake before anybody read a
    word of the translation.

    The caller must move the window by the same amount, or the overlay
    stops lining up with the text it replaced.
    """
    pad = MARK_PAD if pad is None else pad
    if pad <= 0:
        return image
    edge = _border_colour(image)
    out = Image.new("RGB", (image.width + 2 * pad, image.height + 2 * pad),
                    edge)
    out.paste(image.convert("RGB"), (pad, pad))
    return out


def _border_colour(image):
    """The commonest colour round the edge of the picture."""
    try:
        small = image.convert("RGB")
        width, height = small.size
        edge = []
        for x in range(0, width, max(1, width // 40)):
            edge.append(small.getpixel((x, 0)))
            edge.append(small.getpixel((x, height - 1)))
        for y in range(0, height, max(1, height // 40)):
            edge.append(small.getpixel((0, y)))
            edge.append(small.getpixel((width - 1, y)))
        counts = {}
        for pixel in edge:
            counts[pixel] = counts.get(pixel, 0) + 1
        return max(counts, key=counts.get)
    except Exception:
        return (255, 255, 255)


def draw_mark(image, radius=None, grip=None, thick=None):
    """Draw Squint's corner mark round the edge of `image`, in place.

    Two-tone like the snip frame — dark underneath, light on top — rather
    than the icon's black on cream, because this lands on whatever the
    page happened to be and has to be legible over both.
    """
    radius = MARK_RADIUS if radius is None else radius
    grip = MARK_GRIP if grip is None else grip
    thick = MARK_THICK if thick is None else thick
    width, height = image.size
    radius = max(2, min(radius, width // 3, height // 3))
    draw = ImageDraw.Draw(image)

    for colour, heavy, hair in (("#000000", thick + 3, 3),
                                ("#FFFFFF", thick, 1)):
        inset = heavy // 2
        left, top = inset, inset
        right, bottom = width - 1 - inset, height - 1 - inset
        if right - left < 2 * radius or bottom - top < 2 * radius:
            continue
        box = 2 * radius
        # PIL measures from three o'clock, clockwise.
        for x, y, start, end in (
                (left, top, 180, 270),
                (right - box, top, 270, 360),
                (right - box, bottom - box, 0, 90),
                (left, bottom - box, 90, 180)):
            draw.arc([x, y, x + box, y + box], start, end,
                     fill=colour, width=heavy)
        for x0, y0, x1, y1 in (
                (left + radius, top, left + radius + grip, top),
                (right - radius - grip, top, right - radius, top),
                (left + radius, bottom, left + radius + grip, bottom),
                (right - radius - grip, bottom, right - radius, bottom),
                (left, top + radius, left, top + radius + grip),
                (left, bottom - radius - grip, left, bottom - radius),
                (right, top + radius, right, top + radius + grip),
                (right, bottom - radius - grip, right, bottom - radius)):
            draw.line([x0, y0, x1, y1], fill=colour, width=heavy)
        # The flats only. A rectangle here would put a sharp corner back
        # outside each arc, which is the thing the rounded mark is for.
        for x0, y0, x1, y1 in (
                (left + radius, top, right - radius, top),
                (left + radius, bottom, right - radius, bottom),
                (left, top + radius, left, bottom - radius),
                (right, top + radius, right, bottom - radius)):
            draw.line([x0, y0, x1, y1], fill=colour, width=hair)
    return image


def scale_lines(lines, factor):
    """The same lines against an image enlarged by `factor`.

    Zooming has to redraw rather than magnify. Enlarging the finished
    image enlarges the text as pixels — the letters get bigger and no
    clearer, which is not what somebody squinting at 11px wanted. Scaling
    the boxes and rendering again puts real type at the new size, and only
    the page behind it is interpolated.
    """
    out = []
    for line in lines:
        x, y, w, h = line["box"]
        item = dict(line)
        item["box"] = (int(x * factor), int(y * factor),
                       int(w * factor), int(h * factor))
        out.append(item)
    return out


# An email address or a web address, in text a recogniser produced.
#
# Deliberately loose about what counts, because the cost is lopsided. A
# line wrongly held back is a few words left in the original language,
# sitting next to their translation. A line wrongly drawn over is a
# working address replaced by one that looks identical and is not — and
# nothing on screen says so, because the substitute is typeset as neatly
# as everything else.
_ADDRESS = re.compile(r"""
    (?:[\w.+-]+@[\w-]+\.[\w.-]+)              # someone@example.com
  | (?:\bhttps?://\S+)                        # https://example.com/x
  | (?:\bwww\.[\w-]+\.\w{2,})                 # www.example.com
  | (?:\b[\w-]{2,}\.(?:com|org|net|de|cn|io|co|eu|uk|gov|edu)\b)
""", re.VERBOSE | re.IGNORECASE)


def addresses_in(text):
    return [a.lower() for a in _ADDRESS.findall(str(text or ""))]


def carries_an_address(text, ignore=()):
    """True if this line is something a person would click or type: an
    address, alone or with a few words ("E-Mail: info@firma.de").

    Not a sentence that mentions one. "...eines Artikels, der über
    shop.example, die App des Shops oder einen deutschen Store erworben"
    was held back whole for the domain in it: the first line of the
    paragraph stayed in German and the rest was translated without its
    beginning. The address inside a translated sentence is kept exactly
    as it was anyway (identifiers.repair)."""
    found = [a for a in addresses_in(text) if a not in (ignore or ())]
    if not found:
        return False
    rest = str(text)
    for a in found:
        rest = rest.replace(a, " ")
    words = [w for w in rest.split() if any(c.isalpha() for c in w)]
    dense = len("".join(str(text).split()))
    taken = sum(len(a) for a in found)
    return len(words) <= 4 or taken >= 0.4 * max(1, dense)


def stamped_addresses(lines, threshold=4, share=0.4):
    """Addresses that are on the page rather than in it.

    A corporate document stamped with the reader's own name and email —
    diagonally, across every paragraph — puts that address into most of
    the lines the recogniser returns. Held back on that evidence, most of
    the page then stays untranslated, which is a worse outcome than the
    one the rule was written to prevent: nothing is protected, because
    nothing was at risk. The watermark is not a link anybody is going to
    click; it is furniture.

    Two conditions together, because either alone is wrong. A contact page
    may print the same address three times in forty lines and mean every
    one of them, so a count is not enough. A two-line snip of a signature
    is entirely address and means it, so a share is not enough either.
    """
    counts = {}
    for line in lines:
        for token in set(addresses_in(line.get("text", ""))):
            counts[token] = counts.get(token, 0) + 1
    total = max(1, len(lines))
    return {token for token, seen in counts.items()
            if seen >= threshold and seen >= total * share}


def _room_below(usable, page_height, expand=2):
    """For each block, the distance to the next thing underneath it.

    Underneath, not merely further down the page: two blocks are in each
    other's way only when they overlap horizontally. A cell and the cell
    beside it are both further down the page than the row above and
    neither is under the other.

    Returns a list of distances, one per block, or 0 where nothing is
    below — which the caller reads as "the rest of the page".
    """
    # The width each block will actually be drawn at, not the width the
    # recogniser found.
    #
    # This asked `line["box"]`, which is the original line — and since a
    # block became free to reach right across the empty part of a page,
    # those are two different rectangles. A block widened to the page edge
    # now sits above things it did not sit above when it was measured, so
    # it was told it had the rest of the page beneath it, grew down, and
    # was drawn on top of them.
    #
    # `pad_r` is settled before this runs, so the honest width is available
    # here. Asking for it is the whole fix.
    boxes = []
    for item in usable:
        x, y, w, h = item["line"]["box"]
        boxes.append((x, y, w + int(item.get("pad_r", 0) or 0), h))
    out = []
    for i, (x, y, w, h) in enumerate(boxes):
        nearest = 0
        for j, (bx, by, bw, bh) in enumerate(boxes):
            if i == j or by <= y:
                continue
            if bx + bw <= x or x + w <= bx:      # side by side, not below
                continue
            gap = by - y - expand - 1
            if gap <= 0:
                continue
            if not nearest or gap < nearest:
                nearest = gap
        out.append(max(0, nearest))
    return out


def _room_beside(item, usable):
    """How far right this block may reach before it meets something.

    "Something" is any other block sharing a row with it — measured over
    the block's whole depth, not one line of it, because a paragraph three
    lines tall passes three lines of the column beside it and must clear
    all of them.

    Returns the width of the empty space, or a very large number when
    there is nothing to the right at all.
    """
    x, y, w, h = item["line"]["box"]
    top = y
    bottom = y + max(h, int(item.get("span", h)))
    nearest = None
    for other in usable:
        if other is item:
            continue
        bx, by, bw, bh = other["line"]["box"]
        if bx + bw <= x + w:
            continue                      # beside it on the left, or under
        shared = min(bottom, by + max(bh, int(other.get("span", bh)))) \
            - max(top, by)
        if shared <= 0:
            continue
        gap = bx - (x + w)
        if gap < 0:
            continue                      # already overlapping horizontally
        if nearest is None or gap < nearest:
            nearest = gap
    return 10 ** 6 if nearest is None else nearest


def _rows_of(usable, indexes, overlap=0.5):
    """The blocks of this column, gathered into the rows they sit in.

    A block of prose is a row of one. Cells that share a horizontal band
    are one row and are placed together, so a table keeps its grid when one
    of its cells needs more depth than the original gave it.

    Rows come back in the order they appear down the page, which is the
    order they have to be placed in.
    """
    order = sorted(indexes, key=lambda i: usable[i]["line"]["box"][1])
    rows, band = [], []
    for index in order:
        _x, y, _w, h = usable[index]["line"]["box"]
        if band and usable[index].get("cell"):
            top = min(usable[i]["line"]["box"][1] for i in band)
            bottom = max(usable[i]["line"]["box"][1]
                         + usable[i]["line"]["box"][3] for i in band)
            shared = min(y + h, bottom) - max(y, top)
            if (all(usable[i].get("cell") for i in band)
                    and shared > overlap * max(1, min(h, bottom - top))):
                band.append(index)
                continue
        if band:
            rows.append(band)
        band = [index]
    if band:
        rows.append(band)
    return rows


def _member_groups(members):
    """Which of these lines belong together, by index into `members`.

    The grouping the translation used when the lines carry it, and
    geometry when they do not. Order is kept — a paragraph is laid out
    where its first line was, so the groups have to come back in the order
    their lines appear.
    """
    if members and all(m.get("para") is not None for m in members):
        order, seen = [], {}
        for index, member in enumerate(members):
            key = member["para"]
            if key not in seen:
                seen[key] = len(order)
                order.append([])
            order[seen[key]].append(index)
        return order
    return group_paragraphs([m["line"] for m in members])


def _merge_paragraphs(usable, groups):
    """Fold the lines of a paragraph into one block to be placed together.

    Placing each line on its own is what produced the two faults that made
    a dense page look wrong even when every word was right. A line that
    grew nudged the next one down, and the nudges accumulated, so by the
    bottom of a column the text had drifted well away from the layout it
    was replacing — worst on the numbered items and the label-and-value
    rows, where the label ended up beside the wrong value. And each line
    was sized and coloured from its own box, so one paragraph came back in
    two or three sizes and two or three greys, which reads as damage even
    when it is perfectly legible.

    A paragraph has one rectangle, one size and one colour. The
    translation is rewrapped inside it rather than being cut to wherever
    the original happened to break, which is also the only way the wording
    survives: the engine was given a paragraph, so the paragraph is the
    thing that should be laid out.

    And it is the *same* paragraph the engine was given. Where the lines
    carry the grouping the translation used, that grouping is used here
    rather than worked out a second time from boxes that have since been
    shrunk to their ink — see `paragraphs_for` for what the second answer
    cost when it disagreed with the first.
    """
    if not usable:
        return usable, groups
    lookup = {}
    merged = []
    for column in (groups or [{"indexes": list(range(len(usable)))}]):
        members = [usable[i] for i in column["indexes"]]
        order = column["indexes"]
        for group in _member_groups(members):
            picked = [members[i] for i in group]
            if not picked:
                continue
            boxes = [p["line"]["box"] for p in picked]
            left = min(b[0] for b in boxes)
            top = min(b[1] for b in boxes)
            right = max(b[0] + b[2] for b in boxes)
            bottom = max(b[1] + b[3] for b in boxes)
            # The height carried on the box is one *line*, because that is
            # what the font size is worked out from. How far the paragraph
            # reaches down is a separate number and is kept separately.
            #
            # The median of the group, not the tallest of it. A recogniser
            # hands back the occasional box far taller than the line it
            # found — it swallows the space above, or two lines at once,
            # and it does this most on scripts without spaces. Taking the
            # tallest let one such box set the size for the whole
            # paragraph, and since the size comes straight off the height,
            # a box twice too tall is text twice too big.
            tallest = sorted(_line_unit(p["line"]) for p in picked)
            height = tallest[len(tallest) // 2]
            # The paragraph as the engine returned it, when the lines
            # carry it. Reassembling it from the per-line pieces gives the
            # same string whenever every piece is present — and silently
            # drops a quarter of the sentence when one line was held back,
            # because that line's share of the words went with it.
            whole = picked[0].get("para_text")
            if whole and all(p.get("para") == picked[0].get("para")
                             for p in picked):
                text = str(whole)
            else:
                text = " ".join(p["text"].strip() for p in picked
                                if p["text"].strip())
            entry = {
                "line": {"box": (left, top, max(1, right - left), height),
                         "unit": height,
                         "text": " ".join(p["line"].get("text", "")
                                          for p in picked)},
                "text": re.sub(r"\s+", " ", text).strip(),
                "column": picked[0].get("column"),
                "span": max(height, bottom - top),
                # One colour for the paragraph, taken from its longest
                # line. Sampling per line is what gave one paragraph two
                # or three different greys.
                "colours": max(picked,
                               key=lambda p: len(p["text"])).get("colours"),
                # How many original lines this paragraph stands for. The
                # caller decides whether enough of the page was replaced to
                # be worth showing as an overlay, and it counts lines —
                # so a page of twenty lines gathered into four paragraphs
                # must not report four, or a perfectly good translation is
                # thrown away as too sparse to be honest.
                "lines": len(picked),
                # A group of cells is still cells. This entry is a fresh
                # dictionary, so anything decided about the lines before
                # they were gathered has to be carried over deliberately —
                # and the cell rule silently stopped applying when it was
                # not, which looks exactly like the cell rule not working.
                "cell": all(p.get("cell") for p in picked),
                "pictured": all(p.get("pictured") for p in picked),
                # Which paragraph of the translation this is, so a page
                # shown as it fills in can tell finished from not.
                "para": picked[0].get("para"),
            }
            bottoms = [p["line"].get("ink_bottom") for p in picked
                       if p["line"].get("ink_bottom")]
            if bottoms:
                entry["line"]["ink_bottom"] = max(bottoms)
            lookup.setdefault(id(column), []).append(len(merged))
            merged.append(entry)
        del order
    rebuilt = []
    for column in (groups or []):
        indexes = lookup.get(id(column), [])
        if indexes:
            rebuilt.append({"left": column["left"], "right": column["right"],
                            "indexes": indexes})
    return merged, (rebuilt if groups else groups)


def layout(image, lines, translations, target_lang="en", expand=2,
           uniform=True, min_size=8, reach=True):
    """Work out where every translation goes, without drawing anything.

    Returns `(blocks, height)`. Each block is one placed translation — the
    rectangle that covers the original, the two colours sampled from it, the
    font size, and the wrapped rows with the position of the first. `height`
    is how tall the result needs to be, which can exceed the capture when a
    column had to grow to hold its own text.

    Separating this from the drawing is what lets the same placement be
    painted into a bitmap (for a translated file, which has to be a picture)
    and drawn as canvas items on screen (which stays sharp on a
    high-resolution display, where a bitmap cannot). It also makes zooming a
    re-layout rather than a magnification of something already drawn.

    Sizing is decided for a *group* of lines, not one line at a time. Fitting
    each line independently is what produced the unreadable result: English
    runs longer than Chinese, so a dense line shrank to 7px while the short
    line under it stayed at 20px, and the paragraph looked like a ransom
    note. Lines that were the same size in the original stay the same size in
    the translation.

    `min_size` is the floor. Below it the answer is to take more room, not
    to make smaller letters — see `size_policy`, which decides what it
    should be from how much of the screen was captured.
    """
    min_size = max(6, int(min_size))
    out = image.convert("RGB")
    draw = ImageDraw.Draw(out)
    kind = _font_family_for(target_lang)
    rtl = target_lang in RTL_TARGETS
    blocks = []

    # The same decision the translation used, from the same function, so
    # the two cannot drift apart. An address is left showing in the
    # original: a copy of it drawn from a recogniser that turned one letter
    # into another still looks like an address and goes somewhere else.
    held = held_back(lines)
    # And which are cells of a table rather than lines of prose. Everything
    # below treats the two differently: a cell keeps its place and takes a
    # smaller size when its translation is longer, where a line of prose
    # grows and pushes the rest of its column down. Doing the prose thing
    # to a table is what puts the label of one row beside the value of the
    # next.
    cells = set(cells_in(lines))
    # A caller laying out part of a page marks the cells it found on the
    # whole page; part of a table on its own does not look like one.
    cells |= {i for i, line in enumerate(lines) if line.get("is_cell")}

    usable = []
    standing = []            # lines drawn as they are, to be kept clear of
    turned = []              # text at an angle, drawn back at its angle
    for index, (line, translated) in enumerate(zip(lines, translations)):
        text = (translated or "").strip()
        x, y, w, h = line["box"]
        if line.get("quad"):
            if index in held or not text or \
                    text == str(line.get("text", "")).strip():
                continue
            try:
                block = turned_block(image, line, text, kind, min_size)
            except Exception:
                block = None
            if block is not None:
                block["para"] = line.get("para")
                turned.append(block)
            continue
        # Unchanged as a whole: the paragraph (or the line, when it was
        # not translated as part of one) came back exactly as it went.
        # One line's share of a translated paragraph matching its own
        # original means nothing.
        para = line.get("para")
        if para is not None and line.get("para_text") is not None:
            source = " ".join(str(l.get("text", "")).strip() for l in lines
                              if l.get("para") == para)
            same = str(line.get("para_text")).strip() == source.strip()
        else:
            same = text == str(line.get("text", "")).strip()
        # Written top to bottom (a rotated label, a vertical column of
        # Japanese): there is no way to set the translation in that
        # space - it came out one letter to a line - so it is left as it is.
        upright = h > 2.5 * max(1, w) and len(text) > 1
        # A line whose own share is empty but whose paragraph came back
        # translated is part of that translation, not a line left as it is.
        in_para = para is not None and \
            str(line.get("para_text") or "").strip() != ""
        if index in held or (not text and not in_para) or same or upright:
            # Left exactly as it is on the page - a number, a time, a code
            # kept as it was: redrawing it in another typeface over a cover
            # only makes it look different, and blurs it.
            standing.append({"line": {"box": tuple(line["box"])}})
            continue
        # Shrink the box to the writing in it before anything is measured
        # from it. Everything downstream — the size, the tiers, which lines
        # are neighbours, how far a cover may reach — is derived from these
        # numbers, so a box that includes the blank space above its line
        # is wrong in all of them at once.
        bg, _fg = sample_colours(image, line["box"])
        # On a picture there is no one background colour to tell ink from,
        # and "ink" ran on into whatever was below - a label's box grew
        # down over the figures under it, and its translation was set
        # there. The box may shrink to its ink there, never grow.
        try:
            pictured = (_busy_around(image, line["box"]) or 0) >= PATCH_BUSY
        except Exception:
            pictured = False
        tight = ink_box(image, line["box"], bg)
        if pictured and tight is not None:
            # Only a box that sits inside the reader's: on a picture the
            # "ink" found can be the label's backdrop or the figures below.
            bx, by, bw, bh = line["box"]
            tx, ty, tw, th = tight
            if tx < bx or ty < by or tx + tw > bx + bw or ty + th > by + bh \
                    or th < 0.6 * bh:
                tight = None
        if not pictured:
            try:
                tight = grow_to_ink(image, tight or line["box"], bg)
            except Exception:
                pass
        # How far the writing really goes down - descenders the box left
        # out - for the cover only: the size is still taken from the line.
        try:
            if pictured:
                raise ValueError("on a picture")
            inked = grow_to_ink(image, tight or line["box"], bg,
                                vertical=True)
            ink_bottom = inked[1] + inked[3]
        except Exception:
            ink_bottom = None
        entry = dict(line)
        if ink_bottom is not None:
            entry["ink_bottom"] = ink_bottom
        if tight is not None:
            entry["box"] = tight
            # Shrinking to the ink cures a box that swallowed the blank
            # space above its line. It cannot cure a box drawn round two
            # lines of the page at once — the ink really is that tall —
            # and that box is read as one enormous line and set at twice
            # the size of the page around it. So the lines inside it are
            # counted, and the height that decides the size is the box's
            # height divided by how many lines are in it.
            rows_in = ink_rows(image, tight, bg)
            if rows_in > 1:
                entry["unit"] = max(1, tight[3] // rows_in)
        # And when no ink is found, the box is kept as it came. Finding
        # none is not proof there is none: pale grey on white is real text
        # that a threshold can miss, and dropping a line on that evidence
        # would silently lose the quietest writing on the page — footnotes,
        # disclaimers, the small print. Trusting the recogniser that
        # something is there and only correcting the box when the pixels
        # agree is the direction that cannot lose words.
        usable.append({"line": entry, "text": text, "colours": (bg, _fg),
                       # Which paragraph the translation put this line in,
                       # and what that whole paragraph came back as. Both
                       # are absent when a caller lays out lines it did not
                       # translate through `translate_grouped`, and then the
                       # grouping falls back to geometry as it always did.
                       "para": line.get("para"),
                       "para_text": line.get("para_text"),
                       "cell": index in cells,
                       "pictured": pictured})

    # Which column each line belongs to. Everything below that asks "how
    # much space does this line have" has to ask it of the column, not of
    # the page — otherwise the body of a letter treats the address block
    # beside it as free space and paints over it.
    groups = columns([item["line"] for item in usable], out.width)
    for column in groups:
        for i in column["indexes"]:
            usable[i]["column"] = column

    # What size text is on this page, so a box that disagrees wildly can be
    # recognised as the mistake it is.
    #
    # The font size comes straight off the height of the box the recogniser
    # returned, and recognisers hand back the occasional box far taller
    # than the line inside it — swallowing the space above, or running two
    # lines together. One of those produced a heading five times the size
    # of the body around it, which then wrapped over six lines and
    # shouldered a screenful of the page out of the way. A real heading is
    # two or three times the body text. Nothing on a page of prose is five.
    #
    # Measured before the lines are gathered into paragraphs, and that
    # ordering is the point: after gathering there may be only a handful of
    # entries, and the median of a handful is not a typical anything. It
    # has to be the median of the lines the recogniser actually found.
    heights = sorted(_line_unit(item["line"]) for item in usable)
    typical = heights[len(heights) // 2] if heights else 0
    ceiling = max(1, int(typical * TALLEST_LINE)) if typical else 0

    if uniform:
        usable, groups = _merge_paragraphs(usable, groups)

    for index, item in enumerate(usable):
        box = item["line"]["box"]
        x, y, w, h = box
        column = item.get("column")
        edge = column["right"] if column else out.width
        # As far right as the page is actually empty.
        #
        # This used to stop at 35% of the block's own width, whatever was
        # there. On a left-aligned document with half the page blank — a
        # notice, a memo, most of what people snip — a short line was
        # allowed a sliver of the empty space beside it and then had to
        # shrink to fit the rest of its translation into two dense lines.
        # The limit was a guess about how far it is polite to reach, made
        # without looking at the page.
        #
        # `background_run` below is the check that matters and it is a
        # real one: it walks right through the picture and stops where the
        # background stops. It cannot paint over anything, because it can
        # only extend across pixels that are already this block's own
        # background. The column edge bounds it as well.
        # Less the margin the cover itself adds. The cover is drawn
        # `expand` pixels wider than the text on each side so no stroke of
        # the original is left showing round the edge; reaching right up
        # to the next column and then adding that margin puts the cover
        # over the first sliver of the neighbour's letters — and, on a
        # page where the two columns are the same colour, does it
        # invisibly until someone measures it.
        want = max(0, edge - (x + w) - expand)
        # And never past whatever else is on this block's own rows.
        #
        # `background_run` below walks right through the picture and stops
        # where the background stops, which sounds like enough and is not.
        # It samples three rows out of the line's height, at the line's own
        # position — so a block in the left column of a three-column page
        # whose neighbour happens to have a paragraph break at exactly that
        # height finds nothing but background, reaches across the gutter,
        # and is set at a width that runs into the middle column. That is
        # the overlapping the user reported on a three-column newsletter,
        # and no amount of sampling fixes it: the evidence really is white
        # at those rows.
        #
        # The lines are the honest answer. A block may reach as far as the
        # nearest thing that shares any of its rows, and no further,
        # whatever the pixels between them look like.
        # Lines left as they are (held back, kept as numbers, not
        # translated) are on the page too, and count as much as any block.
        want = min(want, max(0, _room_beside(item, usable + standing)
                             - expand - COVER_GAP))
        # A cell reaches right as far as the empty space beside it goes -
        # up to the next cell on its row (`_room_beside`) and never over
        # anything drawn there (`background_run`). Kept inside its own box,
        # "施設" (two characters) had to hold "Facility" and came back as
        # "Facili / ty" in tiny letters, and a row that grew pushed the
        # rest of the table down a row.
        if not reach:
            # `reach=False`: the translation stays inside the lines the
            # original was written in, as hold-to-see draws a whole page
            # and the page's own margins are part of how it looks.
            #
            # Nothing. The space to the right of a cell is the next cell,
            # and a cover filled with this cell's background painted across
            # it is the grey block that wipes out half a table.
            want = 0
        # Not the whole of it if the background stops first.
        bg, _fg = item.get("colours") or sample_colours(image, box)
        item["colours"] = (bg, _fg)
        run = background_run(image, box, bg, want, ink=_fg) if want else 0
        # `background_run` stops at the first pixel of the next thing
        # along, which is the right place for the *text* to stop and two
        # pixels too far for the cover — it is drawn `expand` wider on
        # each side so no stroke of the original is left showing. Reaching
        # right up to the neighbour and then adding that margin lays the
        # cover over the first sliver of its letters, invisibly when the
        # two are the same colour.
        item["pad_r"] = max(0, run - expand - COVER_GAP)

    # How much vertical room each block has: the distance down to the next
    # thing that is *actually underneath it*.
    #
    # "Underneath" means the two overlap horizontally. That sounds obvious
    # and was not what the code did: room was measured to whatever came
    # next by vertical position within the column, and on a page the
    # column-finder reports as one column — which is every page it has
    # been shown — the next thing by vertical position is very often the
    # cell to the *right* of this one on the same row. So a block was told
    # it had no room when the space below it was empty, or told it had the
    # whole page when the next row began ten pixels down. Both end the same
    # way: text drawn on top of other text, which is unreadable however
    # carefully each half of it was placed.
    #
    # Measured over six pages: eighty pairs of blocks were being drawn over
    # one another before this, and the pages the user could not read were
    # the ones with the most.
    room_for = _room_below(usable, out.height, expand)
    for i, item in enumerate(usable):
        x, y, w, h = item["line"]["box"]
        span = item.get("span", h)
        below = room_for[i]
        if item.get("cell"):
            # A cell takes the space its own row gives it — the distance
            # down to the next row — and shrinks if its translation still
            # will not fit.
            #
            # There used to be a second limit here: 2.2 times the cell's
            # own height, whichever was smaller. It was there because a
            # cell could not move and could not move anything, so a cell
            # that grew was a cell drawn over the row below it, and the
            # only defence was to stop it growing. That is no longer true —
            # rows are placed as rows and a row that grows pushes the rest
            # of the table down — and the limit had a cost: a row of a bill
            # set in 7pt was allowed fifteen pixels for a translation that
            # needed forty, so it came back at the floor size, which is the
            # cramping the whole page was reported for. The document's own
            # row spacing is the honest number and it is already measured.
            item["room"] = max(h, below)
            continue
        # Down to whatever is actually underneath, and no further.
        #
        # `_room_below` measures that — the distance to the next block that
        # overlaps this one horizontally. It is a real measurement of real
        # empty page, and it was then thrown away: the line under it capped
        # the result at 1.35 times the paragraph's own depth, so a block
        # with half a page of white space beneath it was told it had room
        # for a third of a line more and shrank instead.
        #
        # Chinese to Korean is where that shows worst. Chinese carries a
        # word in a character; Korean needs several, so a two-line Chinese
        # paragraph wants five or six Korean lines. It could not have them,
        # so it shrank until it fitted, and the result was correct,
        # complete, and too cramped to read.
        #
        # Nothing is invented here. Where the page below is full the answer
        # is still small, and the block still shrinks.
        room = below if below else max(span, min(int(h * 3), out.height - y))
        item["room"] = max(h, room)

    # And never further down than the page is actually empty. The lines
    # say where the next text is; they know nothing of a picture, an icon,
    # a button or text the reader did not return, and a translation that
    # grew over one of those painted it out - the rest of the page erased
    # under a cover. So the room below is also measured in the picture.
    for item in usable:
        x, y, w, h = item["line"]["box"]
        span = int(item.get("span", h))
        bg = (item.get("colours") or sample_colours(image, item["line"]["box"]))[0]
        clear = background_below(out, (x, y, w + int(item.get("pad_r", 0)),
                                         span), bg, int(item["room"]))
        item["room"] = max(h, min(item["room"], span + clear))

    # One size per tier, chosen so every line in the tier fits its own space
    # once wrapped. Lines that were the same size in the original stay the
    # same size in the translation.
    sizes = {}
    if uniform and usable:
        # Tiers exist so the lines of one paragraph come back at one size.
        #
        # Cells are tiered too — among themselves, and that is the part
        # that was missing. They used to be excluded altogether and each
        # measured against its own box, the reasoning being that a cell is
        # not in a paragraph and that one misread box should not set the
        # size for every cell near its height. The first half is true; the
        # conclusion made a table look like a ransom note. On a page put
        # through the real engine, one owner's name came back at seven
        # point and the name in the row under it at fifteen, because each
        # had asked its own box on its own. A table is the one place on a
        # page where a reader is comparing one line directly against
        # another, and a column set in three sizes is unreadable in a way
        # that has nothing to do with any of them being too small.
        #
        # Tiering them separately keeps what the exclusion was protecting:
        # the body text cannot drag the cells, and the cells cannot drag
        # the body text.
        # Tiered within each column of the page, cells and prose alike: a
        # sidebar menu is not made smaller because the article beside it
        # had to shrink, and one menu's items - some of which happen to
        # have text level with them across the page, which makes them
        # "cells" - come back at one size, not two.
        by_column = {}
        for i, item in enumerate(usable):
            by_column.setdefault(id(item.get("column")), []).append(i)
        for group_of in by_column.values():
            if not group_of:
                continue
            for tier in [[group_of[j] for j in group] for group in
                         _tiers([usable[i]["line"] for i in group_of])]:
                natural = max(int(_line_unit(usable[i]["line"]) * 0.92)
                              for i in tier)
                if ceiling:
                    natural = min(natural, ceiling)
                fitted = []
                for i in tier:
                    item = usable[i]
                    _x, _y, w, h = item["line"]["box"]
                    size, _rows = _size_that_fits_wrapped(
                        draw, item["text"], kind, w + item["pad_r"],
                        item["room"], natural, min_size=min_size)
                    fitted.append(size)
                # The floor is measured against the document, not against
                # a constant. A tier may give up a tenth of its size to
                # fit and no more; past that it takes room instead. Text
                # smaller than the absolute floor is the one case that
                # grows, because fine print nobody can read is not worth
                # preserving faithfully.
                limit = max(int(natural * SHRINK_LIMIT), min_size)
                common = max(min(fitted), limit)
                for i in tier:
                    sizes[i] = common

    for index, item in enumerate(usable):
        line, text, pad_r = item["line"], item["text"], item["pad_r"]
        x, y, w, h = line["box"]
        room = item["room"]

        natural = int(_line_unit(line) * 0.92)
        if ceiling:
            natural = min(natural, ceiling)
        size = sizes.get(index)
        if size is None:
            size, _ = _size_that_fits_wrapped(
                draw, text, kind, w + pad_r, room, natural,
                min_size=max(int(natural * SHRINK_LIMIT), min_size))
        # The size shared with its tier, unless that would cut one of its
        # words in two: then as much smaller as keeping it whole needs.
        words = str(text or "").split()
        if words and not any(0x3000 <= ord(c) <= 0xD7AF for c in text):
            longest = max(words, key=len)
            while size > min_size and _width_of(
                    draw, longest, load_font(kind, size)) > w + pad_r:
                size -= 1
        # Still too tall for the empty page under it: smaller, down to the
        # floor, rather than painted over whatever is there.
        # (One line is never made smaller for this: a line of text always
        # has the room its original took.)
        while size > min_size:
            rows_now = _wrap(draw, text, load_font(kind, size), w + pad_r)
            if len(rows_now) <= 1 or \
                    len(rows_now) * leading_for(kind, size) <= room:
                break
            size -= 1
        font = load_font(kind, size)
        item["size"] = size
        # What the block would have been set at if the space had allowed
        # it. Kept so that "the text came out too small" can be answered
        # with a number rather than a screenshot.
        item["natural"] = max(1, natural)
        # Every row of it. Nothing is trimmed here and nothing is trimmed
        # later: a translation cut off mid-sentence and given an ellipsis
        # is the one failure the reader cannot see, because a document may
        # legitimately contain an ellipsis and because the missing words
        # leave no trace. Text that does not fit its original gap pushes
        # the rest of its column down instead — see below.
        item["rows"] = _wrap(draw, text, font, w + pad_r)
        item["height"] = len(item["rows"]) * leading_for(kind, size)
        # How wide it is drawn, which can be far less than the room it
        # was given: what pushes the line below it down (see below).
        try:
            item["used_w"] = max(_width_of(draw, row, font)
                                 for row in item["rows"]) if item["rows"] \
                else w
        except Exception:
            item["used_w"] = w + pad_r

    # Place each column top to bottom, a row at a time.
    #
    # A block starts where its line was, unless something above it has
    # grown far enough down to reach it, in which case it starts underneath
    # that instead. Blocks that fit keep their position exactly; only what
    # overruns moves, only downwards, and only past what it would otherwise
    # be drawn on top of.
    #
    # "A row at a time" is the part that took three attempts. A cell used
    # to be nailed where it was found and allowed neither to move nor to
    # move anything — the reasoning being that the thing above a cell in
    # page order is usually the cell to its *left*, and that a table whose
    # rows slide about is worse than one set small. Both halves of that are
    # right and the conclusion was wrong: a cell whose translation does not
    # fit is still drawn, at the floor size, over the row beneath it. On
    # the corpus that was where the overlapping came from — a hundred and
    # seven of the hundred and nine pairs on the worst page had a cell in
    # them, and only two were prose over prose.
    #
    # A row is one thing. Its cells are placed together, keeping the
    # offsets they had from each other, and the row below starts under the
    # *tallest* of them. The grid survives: cells stay in their columns,
    # a row stays a row, and a row that needs two lines where the original
    # had one pushes the rest of the table down instead of over it.
    # One pass over the whole page rather than one pass per column.
    #
    # Placing each column separately was how blocks were kept from pushing
    # each other across a gutter, and the horizontal-overlap test below
    # already does that job properly: two things in different columns do
    # not overlap, so neither can move the other, and a block may only
    # widen as far as its own column's edge. What the per-column pass did
    # do was cut every row of a table into three, one piece per column, so
    # the cells of one row could no longer be placed together — which is
    # the whole point of placing rows as rows.
    placed = []
    units = []
    for unit in _rows_of(usable, list(range(len(usable)))):
        # A row of table cells moves as one, so the row stays a row. Lines
        # that only happen to sit at the same height - labels scattered
        # over a picture - each move only for what is above them: "Bereich"
        # being pushed under "Benutzerdefinierter" took "Motorrad", on the
        # other side of the picture, down with it, onto "25-40PSI".
        # A row of a table has three cells or more; two lines side by side
        # are as likely two labels on a picture, which each move alone.
        # Only on a picture: on an ordinary page the lines of a row move
        # together as they always did.
        if not all(usable[i].get("pictured") for i in unit) or \
                (len(unit) >= 3 and all(usable[i].get("cell") for i in unit)):
            units.append(unit)
        else:
            units.extend([i] for i in unit)
    for unit in units:
        spans = []
        for i in unit:
            x, _y, w, _h = usable[i]["line"]["box"]
            # The width it is drawn at, not all the room to its right: a
            # label on a picture was given the free space up to the next
            # label, and the label below that one was pushed down for it,
            # onto the figures under it.
            room = w + int(usable[i].get("pad_r", 0) or 0)
            used = int(usable[i].get("used_w") or 0) \
                if usable[i].get("pictured") else 0
            spans.append((x, x + max(w, min(room, used or room))))
        was = min(usable[i]["line"]["box"][1] for i in unit)
        top = was
        # Moved down by as much as what is above grew, which keeps the gap
        # there was between them - and keeps lines that overlapped on the
        # page (a two-line label read as two boxes that touch) from being
        # pushed apart and onto whatever is below.
        on_picture = all(usable[i].get("pictured") for i in unit)
        tall = min(usable[i]["line"]["box"][3] for i in unit)
        for px0, px1, pbottom, grew in placed:
            if all(px1 <= x0 or x1 <= px0 for x0, x1 in spans):
                continue
            if on_picture and was < pbottom - grew < was + 0.5 * tall:
                # The two boxes already touched on the page: two lines of
                # one label. (Two boxes nearly on top of each other are one
                # word read twice, and are kept apart as before.)
                top = max(top, was + max(0, grew))
            elif pbottom > top:
                top = pbottom
        shift = top - was
        bottom = top
        for i in unit:
            item = usable[i]
            _x, y, _w, h = item["line"]["box"]
            item["top"] = y + shift
            bottom = max(bottom, item["top"] + max(h, item["height"]) + 1)
        was_bottom = max(usable[i]["line"]["box"][1] +
                         usable[i]["line"]["box"][3] for i in unit)
        for x0, x1 in spans:
            placed.append((x0, x1, bottom, bottom - was_bottom - 1))

    needed = out.height
    for index, item in enumerate(usable):
        line, text, pad_r = item["line"], item["text"], item["pad_r"]
        x, y, w, h = line["box"]
        top, size, rows = item["top"], item["size"], item["rows"]
        bg, fg = item.get("colours") or sample_colours(image, line["box"])
        block_h = item["height"]

        # Cover the original across everything about to be drawn — and the
        # cover starts at whichever is higher, the line's own position or
        # where the translation ended up. A block that was pushed down
        # covers only its new position otherwise, and the original it was
        # supposed to replace stays on screen above it: the page then shows
        # the source language and the translation, one under the other,
        # looking like the app translated half a document.
        #
        # It also has to reach the bottom of what it replaces, which is not
        # the same as the bottom of what it draws. A paragraph of three
        # German lines can become one English line — English is shorter
        # than German more often than not — and a cover sized to the
        # translation then stops two lines above where the original ends.
        # The rest of the German stays on screen underneath its own
        # translation, which is the same fault as the one in the comment
        # above, arriving from the other direction: there it was the block
        # moving down, here it is the block being shorter.
        #
        # `span` is how far the paragraph reached before it was replaced.
        # For a single line it is that line's height and this changes
        # nothing.
        #
        # The reach to the right is the room this line has inside its own
        # column, so a wide cover can never land on the column next door.
        span = int(item.get("span", h))
        # Large, heavy type leaves its edges showing round a two-pixel
        # margin - the anti-aliased rim of a display face, a descender
        # the ink box read as background ("after 30 days_ |"). The margin
        # grows with the line: a sixteenth of its height.
        grow = max(expand, int(h * 0.06))
        cover = (max(0, x - grow), max(0, min(y, top) - grow),
                 min(out.width, x + w + grow + pad_r),
                 max(y + span, top + max(h, block_h),
                     int(line.get("ink_bottom") or 0)) + grow)
        lead = leading_for(kind, size)
        ty = (top + max(0, (h - lead) // 2)
              if len(rows) == 1 else top)
        blocks.append({"cover": cover, "bg": bg, "fg": fg, "size": size,
                       "rows": rows, "x": x, "y": ty, "kind": kind,
                       "leading": lead,
                       # Where the line ends, and whether that is the edge
                       # it should be lined up against. Arabic, Hebrew,
                       # Persian and Urdu are written right to left and a
                       # paragraph of them is set flush right; drawn from
                       # the left like English, every line of a wrapped
                       # paragraph starts in a different place and the
                       # block has a ragged left edge where the reader's
                       # eye returns to. Google sets them right; so does
                       # every page they were read off.
                       "right": x + w + pad_r,
                       "rtl": rtl,
                       "cell": bool(item.get("cell")),
                       "natural": int(item.get("natural") or size),
                       "lines": int(item.get("lines", 1)),
                       "para": item.get("para")})
        # On a photograph a flat box of one sampled colour is a grey slab
        # in the middle of the picture, and the text on it was often the
        # wrong shade for it. The cover is the picture itself, softened
        # until the original letters are gone, with edges that fade into
        # it, and the text is light or dark to stand out from it.
        try:
            busy = _busy_around(image, line["box"])
            if busy is not None and busy >= PATCH_BUSY:
                patch, ink = soft_patch(image, cover, h)
                if patch is not None:
                    blocks[-1]["patch"] = patch
                    blocks[-1]["fg"] = ink
        except Exception:
            pass
        needed = max(needed, cover[3])

    for block in turned:
        blocks.append(block)
        needed = max(needed, block["cover"][3])
    return blocks, needed


# How much of the thickness of a slanted line its letters fill, and the
# least they are made to fill before the cover is lengthened instead.
TURNED_FILL = 0.74
TURNED_LEAST = 0.5


def _level_crop(image, corners_):
    """The slanted line cut out and turned level, for its colours."""
    from . import slant
    length, thick = slant.size_of(corners_)
    w, h = max(2, int(length)), max(2, int(thick))
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = corners_
    # QUAD takes upper left, lower left, lower right, upper right.
    return image.convert("RGB").transform(
        (w, h), Image.QUAD, (x0, y0, x3, y3, x2, y2, x1, y1),
        Image.BILINEAR)


def _turned_colours(image, corners_):
    """(background, ink) of a slanted line. The background is taken from
    a band just outside the line, not from inside it: a large bold title
    is more ink than paper, and the most common colour inside its own
    rectangle is the letters."""
    from . import slant
    length, thick = slant.size_of(corners_)
    margin = max(3.0, thick * 0.25)
    (sx, sy), (ex, ey) = corners_[0], corners_[1]
    ux, uy = (ex - sx) / length, (ey - sy) / length
    nx, ny = -uy, ux

    def at(along, across):
        return (sx + ux * along + nx * across, sy + uy * along + ny * across)
    outer = [at(-margin, -margin), at(length + margin, -margin),
             at(length + margin, thick + margin),
             at(-margin, thick + margin)]
    wide = _level_crop(image, outer)
    inner = _level_crop(image, corners_)
    m = int(round(margin))
    ring = []
    for box in ((0, 0, wide.width, m), (0, wide.height - m, wide.width,
                                         wide.height)):
        if box[2] - box[0] > 1 and box[3] - box[1] > 1:
            ring.append(wide.crop(box))
    if not ring:
        return sample_colours(inner, (0, 0, inner.width, inner.height))

    def plainness(part):
        """How much of a band is one colour: the band above or below may
        run into the next line's letters, the other is plain page."""
        stepped = part.point([(c // 24) * 24 for c in range(256)] * 3)
        counts = stepped.getcolors(stepped.width * stepped.height) or []
        if not counts:
            return 0.0
        return max(n for n, _c in counts) / float(sum(n for n, _c in counts))
    band = max(ring, key=plainness)
    bg, _ = sample_colours(band, (0, 0, band.width, band.height))
    stepped = inner.point([(c // 24) * 24 for c in range(256)] * 3)
    colours = stepped.getcolors(stepped.width * stepped.height) or []
    total = float(sum(n for n, _c in colours)) or 1.0
    best, score = None, -1.0
    for count, colour in colours:
        if count < total * 0.01:
            continue
        distance = sum(abs(colour[i] - bg[i]) for i in range(3))
        value = distance * (count ** 0.35)
        if value > score:
            best, score = colour, value
    if best is None or sum(abs(best[i] - bg[i]) for i in range(3)) < 40:
        luma = (bg[0] * 299 + bg[1] * 587 + bg[2] * 114) / 1000.0
        best = (0, 0, 0) if luma > 140 else (255, 255, 255)
    return tuple(int(c) for c in bg), tuple(int(c) for c in best)


def turned_block(image, line, text, kind, min_size=8):
    """A block for one line written at an angle: its translation set on
    one row at the same angle, over a cover the shape of the original.

    The row starts where the original starts and keeps its height. A
    translation longer than the original is first set a little smaller
    and then given more length along the same slant - the way a longer
    word in a diagonal column heading would be printed.
    """
    import math
    from . import slant
    corners_ = slant.corners(line)
    length, thick = slant.size_of(corners_)
    if length < 4 or thick < 4:
        return None
    bg, fg = _turned_colours(image, corners_)
    measure = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    size = max(6, int(round(thick * TURNED_FILL)))
    font = load_font(kind, size)
    width = _width_of(measure, text, font)
    if width > length:
        least = max(6, int(round(thick * TURNED_LEAST)))
        size = max(least, int(size * length / float(width)))
        font = load_font(kind, size)
        width = _width_of(measure, text, font)
    (sx, sy), (ex, ey) = corners_[0], corners_[1]
    ux, uy = (ex - sx) / length, (ey - sy) / length
    nx, ny = -uy, ux
    # How far the row can run along its slant before it leaves what was
    # captured: a longer translation is set smaller rather than cut off
    # at the edge of the window.
    room = _room_along(image.size, (sx + nx * thick / 2.0,
                                    sy + ny * thick / 2.0), (ux, uy))
    room = max(room, length)
    if width + thick * 0.3 > room:
        floor = max(6, min(int(min_size), int(round(thick * 0.35))))
        size = max(floor, int(size * (room - thick * 0.3) / float(width)))
        font = load_font(kind, size)
        width = _width_of(measure, text, font)
    reach = max(length, width + thick * 0.3)
    grow = max(2.0, thick * 0.1)
    a = (sx - ux * grow - nx * grow, sy - uy * grow - ny * grow)
    b = (sx + ux * (reach + grow) - nx * grow,
         sy + uy * (reach + grow) - ny * grow)
    c = (b[0] + nx * (thick + 2 * grow), b[1] + ny * (thick + 2 * grow))
    d = (a[0] + nx * (thick + 2 * grow), a[1] + ny * (thick + 2 * grow))
    shape = [a, b, c, d]
    xs = [p[0] for p in shape]
    ys = [p[1] for p in shape]
    cover = (int(math.floor(min(xs))), int(math.floor(min(ys))),
             int(math.ceil(max(xs))), int(math.ceil(max(ys))))
    # Where the middle of the row goes: from the start of the line, half
    # the row along and half the thickness down.
    middle = (sx + ux * (width / 2.0 + thick * 0.08) + nx * thick / 2.0,
              sy + uy * (width / 2.0 + thick * 0.08) + ny * thick / 2.0)
    ox, oy = cover[0], cover[1]
    return {"cover": cover, "bg": bg, "fg": fg, "size": size,
            "rows": [], "x": cover[0], "y": cover[1], "kind": kind,
            "leading": size, "right": None, "rtl": False, "cell": False,
            "natural": size, "lines": 1,
            "turned": {"text": text,
                       "angle": math.degrees(math.atan2(uy, ux)),
                       # Relative to the cover's top left, so whatever
                       # moves the cover moves these with it.
                       "shape": [(px - ox, py - oy) for px, py in shape],
                       "middle": (middle[0] - ox, middle[1] - oy)}}


def _room_along(size, start, direction):
    """How far from `start` along `direction` before leaving a picture of
    `size`."""
    w, h = size
    (x, y), (ux, uy) = start, direction
    best = float("inf")
    for value, step, limit in ((x, ux, w), (y, uy, h)):
        if step > 1e-6:
            best = min(best, (limit - value) / step)
        elif step < -1e-6:
            best = min(best, (0 - value) / step)
    return max(0.0, best)


def turned_parts(block):
    """(cover polygon, middle of the row, angle for Tk, text) of a block
    from `turned_block`, in the block's own coordinates; None for any
    other block. Tk turns text anticlockwise and the screen counts down,
    hence the sign."""
    turn = block.get("turned")
    if not turn:
        return None
    ox, oy = block["cover"][0], block["cover"][1]
    shape = [(ox + x, oy + y) for x, y in turn["shape"]]
    middle = (ox + turn["middle"][0], oy + turn["middle"][1])
    return shape, middle, -float(turn["angle"]), turn["text"]


def paint(image, blocks, height=None):
    """Draw a layout onto a copy of `image` and return it.

    The bitmap half of the split. A translated *file* has to come out as a
    picture, so this stays; the screen overlay draws the same blocks as
    canvas items instead, which is what keeps them sharp.
    """
    out = image.convert("RGB")
    if height and height > out.height:
        # A column grew past the bottom of what was captured. Extending the
        # picture is the honest answer — the alternative is to cut the last
        # paragraph off, which is the thing this is here to avoid.
        tall = Image.new("RGB", (out.width, int(height)),
                         _border_colour(out))
        tall.paste(out, (0, 0))
        out = tall
    else:
        out = out.copy()
    draw = ImageDraw.Draw(out)
    for block in blocks:
        turned = turned_parts(block)
        if turned is not None:
            draw.polygon(turned[0], fill=block["bg"])
            continue
        patch = block.get("patch")
        if patch is not None:
            x0, y0 = int(block["cover"][0]), int(block["cover"][1])
            out.paste(patch, (max(0, x0), max(0, y0)), patch)
            continue
        x0, y0, x1, y1 = block["cover"]
        draw.rectangle([x0, y0, min(out.width, x1), min(out.height, y1)],
                       fill=block["bg"])
    for block in blocks:
        turned = turned_parts(block)
        if turned is not None:
            _paint_turned(out, block, turned)
            continue
        font = load_font(block["kind"], block["size"])
        ty = block["y"]
        right = block.get("rtl") and block.get("right")
        for row in block["rows"]:
            if right:
                draw.text((right, ty), row, font=font, fill=block["fg"],
                          anchor="ra")
            else:
                draw.text((block["x"], ty), row, font=font, fill=block["fg"])
            ty += block["leading"]
    return out


def _paint_turned(out, block, turned):
    """One slanted row into the picture: drawn level, turned, pasted."""
    _shape, (mx, my), angle, text = turned
    font = load_font(block["kind"], block["size"])
    measure = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    width = max(1, int(_width_of(measure, text, font)) + 4)
    tall = max(1, int(block["size"] * 1.5))
    row = Image.new("RGBA", (width, tall), (0, 0, 0, 0))
    ImageDraw.Draw(row).text((width / 2.0, tall / 2.0), text, font=font,
                             fill=tuple(block["fg"][:3]) + (255,),
                             anchor="mm")
    row = row.rotate(angle, resample=Image.BICUBIC, expand=True)
    out.paste(row, (int(round(mx - row.width / 2.0)),
                    int(round(my - row.height / 2.0))), row)


def render(image, lines, translations, target_lang="en", expand=2,
           uniform=True, min_size=8):
    """A copy of `image` with each line replaced by its translation.

    Kept as one call because a translated file wants exactly this and
    nothing else. On screen the two halves are used separately.
    """
    blocks, height = layout(image, lines, translations, target_lang,
                            expand=expand, uniform=uniform,
                            min_size=min_size)
    if not blocks:
        return image.convert("RGB").copy(), 0
    out = paint(image, blocks, height)
    # The covers are drawn first and the text after, so a block that grew
    # cannot have its own words erased by the block below it.
    #
    # The mark goes on only when something was actually replaced. Round an
    # untouched screenshot it would claim a translation that is not there.
    return draw_mark(pad_out(out)), lines_covered(blocks)


PATCH_BUSY = 0.5          # how busy round a line before it is on a picture


def soft_patch(image, cover, line_height):
    """(RGBA picture for `cover`, ink colour): the area blurred well past
    legibility, pulled half way to its own average colour, its edges
    fading out over a few pixels; the ink white on a dark patch and near
    black on a light one."""
    from PIL import ImageFilter, ImageStat
    x0, y0, x1, y1 = [int(v) for v in cover]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(image.width, x1), min(image.height, y1)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None, None
    reach = max(4, int(line_height))
    wide = image.convert("RGB").crop((max(0, x0 - reach), max(0, y0 - reach),
                                      min(image.width, x1 + reach),
                                      min(image.height, y1 + reach)))
    soft = wide.filter(ImageFilter.GaussianBlur(radius=max(3, reach * 0.8)))
    soft = soft.crop((x0 - max(0, x0 - reach), y0 - max(0, y0 - reach),
                      x0 - max(0, x0 - reach) + (x1 - x0),
                      y0 - max(0, y0 - reach) + (y1 - y0)))
    mean = tuple(int(v) for v in ImageStat.Stat(soft).mean[:3])
    flat = Image.new("RGB", soft.size, mean)
    soft = Image.blend(soft, flat, 0.5)
    feather = max(2, min(8, int(line_height * 0.25)))
    alpha = Image.new("L", soft.size, 255)
    draw = ImageDraw.Draw(alpha)
    w, h = soft.size
    for i in range(feather):
        value = int(255 * (i + 1) / float(feather + 1))
        draw.rectangle([i, i, w - 1 - i, h - 1 - i], outline=value)
    patch = soft.convert("RGBA")
    patch.putalpha(alpha)
    luma = (mean[0] * 299 + mean[1] * 587 + mean[2] * 114) / 1000.0
    ink = (255, 255, 255) if luma < 150 else (20, 20, 22)
    return patch, ink


def patch_photo(patch, scale, master):
    """A soft patch as a Tk picture at the screen's size."""
    try:
        from PIL import ImageTk
        if scale and abs(scale - 1.0) > 0.01:
            patch = patch.resize((max(1, int(round(patch.width / scale))),
                                  max(1, int(round(patch.height / scale)))),
                                 Image.LANCZOS)
        return ImageTk.PhotoImage(patch, master=master)
    except Exception:
        return None


def left_as_they_were(lines):
    """`(left, judged)`: how many lines, of those that are words rather
    than figures or addresses, came back exactly as they went - and how
    many were judged. A line of "25-40PSI" or a model name left as it is
    is not a failure; "Motorrad" or a paragraph of German is."""
    held = held_back(lines)
    left = judged = 0
    for i, line in enumerate(lines):
        text = str(line.get("text", "") or "").strip()
        if not text or i in held:
            continue
        judged += 1
        para = line.get("para")
        if para is not None:
            source = " ".join(str(l.get("text", "")).strip() for l in lines
                              if l.get("para") == para)
        else:
            source = text
        answer = str(line.get("para_text") or "").strip()
        if answer and answer != source.strip():
            continue
        if any(len(w) >= 4 for w in re.findall(r"[^\W\d_]+", text)
               if not w.isupper()):
            left += 1
    return left, judged


def lines_covered(blocks):
    """How many of the original lines these blocks stand for.

    Not len(blocks). A paragraph is one block and several lines, and the
    caller uses this to decide whether enough of the page was replaced to
    show as an overlay at all — counting blocks would throw away a good
    translation of a dense page as too sparse to be honest.
    """
    return sum(int(block.get("lines", 1)) for block in blocks)
