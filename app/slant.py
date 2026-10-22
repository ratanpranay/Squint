"""Text written at an angle: a slanted heading, a column label set
diagonally over a table, a title running up a poster.

Every line used to be a rectangle with sides parallel to the screen. For
text at an angle that rectangle is mostly empty space and overlaps its
neighbours, so the lines were joined into one paragraph, translated as
nonsense ("The duel at the Forest near Moscow"), could not be drawn over
and ended up in a card.

The readers that see such text (PaddleOCR, Apple Vision) also say where
its four corners are. Those are kept on the line as `quad`: the corners
of the text's own rectangle - start of the top edge, end of the top edge,
end of the bottom edge, start of the bottom edge - each as a share of the
line's box, so anything that moves or scales the box moves the corners
with it. A slanted line is then translated on its own, as a label, and
drawn back at its own angle over its own corners.

Lines within SLANT degrees of level carry no `quad` and go through the
page exactly as before.
"""
import math

# Degrees off level before a line is drawn at an angle. A photo or a scan
# a few degrees off is still read and laid out as an ordinary page.
SLANT = 8.0


def _cjk(text):
    text = str(text or "")
    letters = [c for c in text if not c.isspace()]
    if not letters:
        return False
    cjk = sum(1 for c in letters if 0x3040 <= ord(c) <= 0x9FFF
              or 0xAC00 <= ord(c) <= 0xD7AF)
    return cjk > 0.5 * len(letters)


def rectangle(points, ordered=False, text=""):
    """The text's own rectangle from four corners a reader gave, as
    (start-top, end-top, end-bottom, start-bottom), or None when the text
    is level (or a column of upright Chinese, Japanese or Korean, which
    is written top to bottom without being rotated).

    `ordered`: the corners are already top left, top right, bottom right,
    bottom left of the text itself (Apple Vision), so the direction of
    reading is known. Otherwise (PaddleOCR) the long side is the line and
    it is read left to right - downward when it is upright.
    """
    try:
        p = [(float(x), float(y)) for x, y in points][:4]
    except Exception:
        return None
    if len(p) != 4:
        return None
    cx = sum(x for x, _y in p) / 4.0
    cy = sum(y for _x, y in p) / 4.0
    if ordered:
        ux, uy = (p[1][0] - p[0][0] + p[2][0] - p[3][0]) / 2.0, \
            (p[1][1] - p[0][1] + p[2][1] - p[3][1]) / 2.0
        vx, vy = (p[3][0] - p[0][0] + p[2][0] - p[1][0]) / 2.0, \
            (p[3][1] - p[0][1] + p[2][1] - p[1][1]) / 2.0
    else:
        a = (p[1][0] - p[0][0], p[1][1] - p[0][1])
        b = (p[2][0] - p[1][0], p[2][1] - p[1][1])
        if math.hypot(*a) >= math.hypot(*b):
            (ux, uy), (vx, vy) = a, b
        else:
            (ux, uy), (vx, vy) = b, a
        if ux < -1e-6 or (abs(ux) <= 1e-6 and uy < 0):
            ux, uy = -ux, -uy
    length = math.hypot(ux, uy)
    thick = math.hypot(vx, vy)
    # A line is longer than it is thick. A digit or two in a square box
    # has no direction to speak of: its long side can be either.
    letters = len("".join(str(text or "").split()))
    if length < 1 or thick < 1 or length < 1.2 * thick or \
            (text and letters < 3):
        return None
    ux, uy = ux / length, uy / length
    # Down, for the text: a quarter turn from the direction of reading.
    nx, ny = -uy, ux
    angle = math.degrees(math.atan2(uy, ux))
    tilt = abs(angle) % 180.0
    tilt = min(tilt, 180.0 - tilt)
    if tilt < SLANT:
        return None
    if tilt > 75 and _cjk(text):
        return None
    sx = cx - ux * length / 2.0 - nx * thick / 2.0
    sy = cy - uy * length / 2.0 - ny * thick / 2.0
    return [(sx, sy), (sx + ux * length, sy + uy * length),
            (sx + ux * length + nx * thick, sy + uy * length + ny * thick),
            (sx + nx * thick, sy + ny * thick)]


def attach(line, points, ordered=False):
    """Put the corners on `line` (which already has its `box`) when the
    text is at an angle. Returns the line."""
    corners = rectangle(points, ordered, line.get("text", ""))
    if corners is None:
        return line
    xs = [x for x, _y in corners]
    ys = [y for _x, y in corners]
    left, top = int(math.floor(min(xs))), int(math.floor(min(ys)))
    w = max(1, int(math.ceil(max(xs))) - left)
    h = max(1, int(math.ceil(max(ys))) - top)
    line["box"] = (left, top, w, h)
    line["quad"] = [((x - left) / float(w), (y - top) / float(h))
                    for x, y in corners]
    line["angle"] = angle_of(corners)
    return line


def is_slanted(line):
    return bool(line.get("quad")) and len(line["quad"]) == 4


def corners(line):
    """The four corners in the coordinates of the line's box now."""
    x, y, w, h = line["box"]
    return [(x + fx * w, y + fy * h) for fx, fy in line["quad"]]


def angle_of(corners_):
    (x0, y0), (x1, y1) = corners_[0], corners_[1]
    return math.degrees(math.atan2(y1 - y0, x1 - x0))


def size_of(corners_):
    """(length along the line, thickness across it)."""
    (x0, y0), (x1, y1), _e, (x3, y3) = corners_
    return math.hypot(x1 - x0, y1 - y0), math.hypot(x3 - x0, y3 - y0)


def thickness(line):
    """How tall the writing is: across the line, not the box's height."""
    if is_slanted(line):
        try:
            return size_of(corners(line))[1]
        except Exception:
            pass
    return float(line["box"][3])


def start_of(line):
    """Where reading the line begins, for putting slanted labels in order."""
    if is_slanted(line):
        try:
            return corners(line)[3]
        except Exception:
            pass
    x, y, _w, h = line["box"]
    return (x, y + h)
