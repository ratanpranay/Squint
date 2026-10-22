"""Throw away the watermark before it gets translated and drawn.

A confidential document from a Chinese office is tiled with the reader's own
name and address, in pale grey, at an angle, a dozen times across the page.
An OCR engine reads it — correctly, which is the problem. The app then
translated the reader's name and employer a dozen times and drew
each one across the sentence it was sitting on, and because a diagonal line
has a very tall bounding box, the type was set enormous. The page came out
unreadable in a way the original never was.

Nothing here is certain on its own — a repeated line might be a table
heading, pale text might be a caption, and a rotated box might be a bad
crop. So a line has to look wrong in two different ways before it is
dropped, the same bar the jumble test uses. Getting this wrong deletes real
sentences, which is worse than leaving a watermark on screen.
"""
import re

# A watermark is laid down repeatedly; a heading is not.
REPEATS = 3
# Degrees off horizontal. Body text is never more than a degree or two out
# even on a skewed scan; a watermark is usually 20-45.
TILT = 6.0
# Difference between the ink and the paper, 0-255. Black on white is well
# over 150; the grey used for watermarks is under 70.
FAINT = 70
# How many times the page's own text a line has to be before its size is a
# mark against it. A heading is larger than the body; a watermark is set to
# be seen across the whole page and is enormous. Measured against the page
# rather than in pixels, so it means the same on any capture at any scale.
#
# This is the signal that was missing. The three above catch a watermark
# tiled diagonally a dozen times, which is the one that prompted them. The
# next one seen was horizontal, in the corner, and repeated twice — pale
# and nothing else, so one mark, so kept, so translated and drawn several
# times the size of the mail it was sitting on. Being far bigger than
# everything around it is the thing a reader notices first about a
# watermark, and it was the thing not being looked at.
OVERSIZED = 2.2
# Below this many lines there is no reliable idea of what size the page is
# set in, and a median of three lines is not a median of anything.
ENOUGH_LINES = 5
# What share of a box counts as "the ink" and "the paper" when measuring
# how far apart they are. Small, because ink is a minority of the pixels in
# its own box and shrinks further the taller the box is.
EXTREME = 0.02


def _key(text):
    """Watermarks repeat as the same words, but OCR varies the punctuation
    and spacing between copies, so those are ignored when matching."""
    return re.sub(r"[\W_]+", "", str(text or "")).lower()


def _tilt(line):
    """How far off horizontal, in degrees, if the reader said."""
    angle = line.get("angle")
    if angle is None:
        return 0.0
    angle = abs(float(angle)) % 180.0
    return min(angle, 180.0 - angle)


def _height(line):
    """How tall the writing is. For text at an angle that is across the
    line, not the height of its box, which a diagonal label makes many
    times the size of the page's type."""
    try:
        from . import slant
        return slant.thickness(line)
    except Exception:
        return float(line["box"][3])


def contrast(image, box):
    """How strongly this line stands out from the paper behind it.

    Measured as the gap between the darkest and lightest few per cent of
    the pixels: ink against paper. It does not care which is which, so
    white text on a dark page scores the same as black on white.

    A *few* per cent, not a tenth. Ink is a small minority of the pixels in
    its own box, and the taller the box the smaller that minority gets — so
    on a heading, whose box is mostly the space around the letters, a tenth
    reached well past the glyphs into the paper and averaged the two
    together. A black heading came back at contrast 51, which is the range
    watermarks live in, and it was dropped as one. Reading further into the
    extremes measures the ink rather than the ink diluted by its margins.
    """
    try:
        x, y, w, h = [int(v) for v in box]
        if w < 2 or h < 2:
            return 255
        crop = image.convert("L").crop((max(0, x), max(0, y),
                                        max(1, x + w), max(1, y + h)))
        try:
            data = crop.get_flattened_data()       # Pillow 12+
        except AttributeError:
            data = crop.getdata()
        pixels = sorted(data)
        if len(pixels) < 10:
            return 255
        edge = max(1, int(len(pixels) * EXTREME))
        dark = sum(pixels[:edge]) / float(edge)
        light = sum(pixels[-edge:]) / float(edge)
        return light - dark
    except Exception:
        return 255           # never drop a line because measuring failed


def typical_height(lines):
    """The height of an ordinary line on this page, or 0 if unknowable."""
    heights = sorted(int(_height(line)) for line in lines
                     if line.get("box") and int(_height(line)) > 0)
    if len(heights) < ENOUGH_LINES:
        return 0
    return heights[len(heights) // 2]


def score(lines, image=None):
    """(line, reasons) for each line, reasons being the marks against it."""
    counts = {}
    for line in lines:
        key = _key(line.get("text"))
        if key:
            counts[key] = counts.get(key, 0) + 1
    ordinary = typical_height(lines)

    out = []
    for line in lines:
        reasons = []
        key = _key(line.get("text"))
        if key and counts.get(key, 0) >= REPEATS:
            reasons.append("repeated %d times" % counts[key])
        if _tilt(line) >= TILT:
            reasons.append("tilted %.0f degrees" % _tilt(line))
        if image is not None and line.get("box"):
            level = contrast(image, line["box"])
            if level < FAINT:
                reasons.append("faint (contrast %d)" % level)
        if ordinary and line.get("box"):
            height = int(_height(line))
            if height >= ordinary * OVERSIZED:
                reasons.append("%.1fx the size of the page" %
                               (height / float(ordinary)))
        out.append((line, reasons))
    return out


def looks_like_watermark(reasons):
    """Two independent marks against a line, not one.

    Except large and at an angle, and nothing else: that is a poster's
    title or a heading set on a slant, printed in full colour. A
    watermark is also pale or repeated."""
    if len(reasons) < 2:
        return False
    kinds = {str(r).split()[0] if str(r).split()[0] in
             ("faint", "repeated", "tilted") else "size" for r in reasons}
    return kinds != {"tilted", "size"}


def strip(lines, image=None):
    """(kept lines, dropped lines). Never drops everything.

    The guard matters: a scan of a rotated page, or a photo of a screen,
    could tick every box on every line. Removing the entire page would look
    exactly like the app failing to read it, which is the one outcome worth
    ruling out.
    """
    scored = score(lines, image)
    keep = [line for line, reasons in scored
            if not looks_like_watermark(reasons)]
    dropped = [line for line, reasons in scored
               if looks_like_watermark(reasons)]
    if not keep:
        return list(lines), []
    return keep, dropped
