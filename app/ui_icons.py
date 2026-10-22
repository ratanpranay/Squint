"""The interface's icons, drawn rather than typed.

Nothing here is a font glyph and nothing here is a picture file, and
both of those were tried first.

A glyph was the obvious answer and it does not survive contact with the
type. The face the interface is set in is a text face: it has no close
mark, no tick, no arrow, no chevron, no heart, no gear, no sun or moon,
and none of the modifier keys. Falling back to whatever face on the
machine *does* have them means an emoji, and an emoji is full colour on
macOS and a flat outline on Windows — two platforms that were supposed
to look like one design, diverging on the most visible marks in it.

A picture file survives the type and not the theme. Every icon here
takes its colour from the palette and several change colour on hover or
when selected; as files that is the same icon exported once per colour
per state per scale, and a palette change means exporting them all
again. Two of them also have to be drawn at whatever size the display
says, which is a third axis.

So they are drawn, at the size asked for, in the colour given. The
shapes are written in the same 24-unit square the design's own drawings
use, which is what makes it possible to check one against the other by
reading the numbers rather than by squinting at a screenshot.

Curves are the one compromise. Tk's canvas has no path primitive and no
bezier — `smooth=True` on a line is a cardinal spline, which is close
enough for a heart or a bulb and wrong for a circle, so circles are
ovals and arcs are arcs and only the genuinely freehand shapes are
splines.
"""
import math
import sys

#: The square every shape below is written in, the same one the design's
#: drawings use. Nothing here is in pixels.
BOX = 24.0

# Each icon is a list of shapes:
#   ("line", [(x, y), ...], {"smooth": bool, "width": float})
# `width` on a shape overrides the icon's stroke for that shape only —
# a gear's teeth are blocks where its rings are lines.
#   ("oval", cx, cy, r, {"width": float})     the options are optional
#   ("disc", cx, cy, r)                       filled, no outline
#   ("arc",  cx, cy, r, start, extent)
#   ("ellipse", cx, cy, rx, ry)
#   ("poly", [(x, y), ...])                   filled, no outline
#   ("rect", x0, y0, x1, y1, radius)
_ICONS = {}


def _icon(name, *shapes):
    _ICONS[name] = shapes


def names():
    return sorted(_ICONS)


# -- the mark ------------------------------------------------------------
# Four corner brackets: a selection being drawn, which is the whole app
# in one shape. The bar through the middle is the difference between the
# app's own mark and the plain "expand" icon.
_CORNERS = (
    ("line", [(4, 9), (4, 5.5), (5.5, 4), (9, 4)], {}),
    ("line", [(15, 4), (18.5, 4), (20, 5.5), (20, 9)], {}),
    ("line", [(20, 15), (20, 18.5), (18.5, 20), (15, 20)], {}),
    ("line", [(9, 20), (5.5, 20), (4, 18.5), (4, 15)], {}),
)
_icon("crop", *_CORNERS, ("line", [(8.5, 12), (15.5, 12)], {}))
_icon("expand", *_CORNERS)

# -- navigation ----------------------------------------------------------
# Solid, not outlined. In the design this is the one filled mark in the
# rail — it is the place you are, and a filled shape says that where an
# outline of the same drawing says "another option".
_icon("home",
      ("poly", [(12, 3.2), (21.4, 10.6), (21.4, 20.0), (19.6, 21.6),
                (15.2, 21.6), (15.2, 14.2), (8.8, 14.2), (8.8, 21.6),
                (4.4, 21.6), (2.6, 20.0), (2.6, 10.6)]))

# A gear as a ring of teeth rather than a traced outline.
#
# The teeth are the reason this icon is laid out the way it is. A tooth
# is a short stroke pointing away from the centre, and a short stroke at
# an angle is the hardest thing there is to draw cleanly at seventeen
# pixels: it lands across the pixel grid rather than along it, so its
# edges step. The first version had eight of them at 22.5°, which put
# *every* tooth on a diagonal, and the icon read as a ring of lint.
#
# So: the teeth start at 0°, which puts four of the eight exactly on the
# vertical and horizontal — those four are drawn along the grid and come
# out crisp, and they are the four the eye checks. The remaining four are
# on the true diagonal, which is the one angle that steps evenly rather
# than in a limp. And they are short rather than long, because a stubby
# stroke is mostly its two round caps, and a round cap is a circle, which
# the renderer draws well at any size.
#
# The ring is drawn heavier than everything else on purpose. Made all
# one weight, eight teeth on a thin ring is a starburst, and there is
# already a starburst in this set — the sun, four inches away in the same
# window. A gear is a solid body with small bumps on it, so the body gets
# the weight and the teeth are nubs.
_GEAR = [("oval", 12, 12, 3.1), ("oval", 12, 12, 6.8, {"width": 2.6})]
for _n in range(8):
    _a = math.radians(_n * 45.0)
    _GEAR.append(("line", [(12 + 7.2 * math.cos(_a), 12 + 7.2 * math.sin(_a)),
                           (12 + 9.1 * math.cos(_a), 12 + 9.1 * math.sin(_a))],
                  {"width": 2.2}))
_icon("gear", *_GEAR)

_icon("heart",
      ("line", [(12, 21), (4.4, 13.4), (3.2, 10.6), (3.6, 7.6), (5.6, 5.4),
                (8.6, 4.6), (11, 5.8), (12, 7.2), (13, 5.8), (15.4, 4.6),
                (18.4, 5.4), (20.4, 7.6), (20.8, 10.6), (19.6, 13.4),
                (12, 21)], {"smooth": True}))

# -- appearance ----------------------------------------------------------
# A bigger disc and shorter rays than the obvious drawing of a sun, and
# for the same reason as the gear's teeth: a ray is a stroke at an angle,
# and the longer and thinner it is the more of it is spent stepping
# across the pixel grid. The first version's rays were 2.8 long on a 4.2
# disc, which at seventeen pixels is four ragged hairs and four clean
# ones. These are 2.0 on a 5.0 disc: the disc carries the shape and the
# rays are ticks around it.
_SUN = [("oval", 12, 12, 5.0)]
for _n in range(8):
    _a = math.radians(_n * 45.0)
    _SUN.append(("line", [(12 + 7.9 * math.cos(_a), 12 + 7.9 * math.sin(_a)),
                          (12 + 9.9 * math.cos(_a), 12 + 9.9 * math.sin(_a))],
                 {}))
_icon("sun", *_SUN)


def _crescent(outer_r=8.8, inner_r=7.9, shift=3.7, steps=64):
    """The two arcs of a crescent, as one closed outline.

    Drawn as a single arc it reads as the letter C — which is exactly
    what the first version of this looked like on screen. A crescent is
    the gap between two circles, so both edges have to be traced.

    Where the two arcs *stop* is the whole difficulty. Guessed angles
    leave the two curves ending near each other but not on each other,
    and the stroke that closes the gap is a stub across the tip: on
    screen the horns of the moon come out blunt, or forked, or with a
    little hook. So the angles are not guessed. The two circles cross at
    exactly two points and those points are solved for here, so each horn
    is one place where both curves genuinely end and the outline turns
    through it rather than being patched across it.

    `steps` is per arc and is deliberately generous. A crescent is two
    long sweeps with no straight anywhere; at twenty-two steps the joints
    are three degrees apart near the horns and half a pixel of facet
    shows, which is exactly the kind of unevenness this icon was accused
    of.
    """
    # Where the two circles cross. Outer is centred on (12, 12), inner is
    # the same distance right; along that line the crossing sits at `mid`
    # from the outer centre, `rise` above and below it.
    mid = (shift * shift + outer_r * outer_r - inner_r * inner_r) / (2.0 * shift)
    rise = math.sqrt(max(0.0, outer_r * outer_r - mid * mid))
    top = math.degrees(math.atan2(rise, mid))                # on the outer
    inner_top = math.degrees(math.atan2(rise, mid - shift))  # on the inner

    points = []
    sweep = 360.0 - 2.0 * top
    for n in range(steps + 1):
        a = math.radians(top + sweep * n / float(steps))
        points.append((12 + outer_r * math.cos(a), 12 - outer_r * math.sin(a)))
    sweep = 360.0 - 2.0 * inner_top
    for n in range(steps + 1):
        a = math.radians(360.0 - inner_top - sweep * n / float(steps))
        points.append((12 + shift + inner_r * math.cos(a),
                       12 - inner_r * math.sin(a)))
    points.append(points[0])
    return ("line", points, {})


_icon("moon", _crescent())

# -- the translate pair --------------------------------------------------
_icon("globe",
      ("oval", 12, 12, 9),
      ("line", [(3.2, 12), (20.8, 12)], {}),
      ("ellipse", 12, 12, 4.6, 9))

_icon("chevron_down", ("line", [(6, 9), (12, 15), (18, 9)], {}))

# Two strokes on the true diagonal, which is the one angle other than the
# axes that steps evenly rather than in a limp — and they cross at the
# middle of the square, so the two halves of each stroke are mirror
# images and any unevenness would be in both and read as weight rather
# than as wobble.
_icon("close",
      ("line", [(7, 7), (17, 17)], {}),
      ("line", [(17, 7), (7, 17)], {}))

_icon("swap",
      ("line", [(4, 8), (19, 8)], {}),
      ("line", [(15, 4), (19, 8), (15, 12)], {}),
      ("line", [(20, 16), (5, 16)], {}),
      ("line", [(9, 12), (5, 16), (9, 20)], {}))

_icon("arrow_right",
      ("line", [(5, 12), (19, 12)], {}),
      ("line", [(13, 6), (19, 12), (13, 18)], {}))

_icon("copy",
      ("rect", 9, 9, 20, 20, 2),
      ("line", [(5, 15), (4, 15), (3, 14), (3, 4), (4, 3), (14, 3), (15, 4),
                (15, 5)], {}))

_icon("upload",
      ("line", [(12, 15), (12, 4)], {}),
      ("line", [(7.5, 8.5), (12, 4), (16.5, 8.5)], {}),
      ("line", [(4, 15), (4, 18), (6, 20), (18, 20), (20, 18), (20, 15)], {}))

_icon("download",
      ("line", [(12, 4), (12, 15)], {}),
      ("line", [(7.5, 10.5), (12, 15), (16.5, 10.5)], {}),
      ("line", [(4, 15), (4, 18), (6, 20), (18, 20), (20, 18), (20, 15)], {}))

_icon("speaker",
      ("line", [(11, 5), (6.5, 9), (3, 9), (3, 15), (6.5, 15), (11, 19),
                (11, 5)], {}),
      ("arc", 11, 12, 6, -40, 80),
      ("arc", 11, 12, 9.4, -40, 80))

_icon("bulb",
      ("line", [(9, 18), (15, 18)], {}),
      ("line", [(10, 21), (14, 21)], {}),
      ("line", [(9.6, 15.4), (9.4, 14.2), (8.4, 13.2), (6.4, 10.6),
                (6.6, 7.4), (9, 4.6), (12, 3.9), (15, 4.6), (17.4, 7.4),
                (17.6, 10.6), (15.6, 13.2), (14.6, 14.2), (14.4, 15.4),
                (9.6, 15.4)], {"smooth": True}))

# The pointer in the hero picture, and the only solid one.
_icon("cursor", ("poly", [(5, 2.5), (19, 12), (12.8, 13.4), (9.6, 20)]))

# The three claims under the headline. Solid rather than outlined: they
# are read at about sixteen pixels, where a stroked shape is a grey
# smudge and a filled one still has a silhouette.
_icon("bolt", ("poly", [(13.6, 2), (5, 13.6), (10.8, 13.6), (10.4, 22),
                        (19, 10.4), (13.2, 10.4)]))

_icon("lock",
      ("poly", [(5.4, 11.4), (18.6, 11.4), (18.6, 20.4), (5.4, 20.4)]),
      ("arc", 12, 11.6, 4.0, 0, 180, {"width": 2.2}))

# The hand-drawn arrow beside the annotation. Freehand on purpose: it is
# set in the handwritten face and a ruled arrow beside it looks wrong.
_icon("curve",
      ("line", [(5, 4), (3.6, 9.4), (5.4, 14.4), (10.5, 18.6), (16, 21),
                (22, 22)], {"smooth": True}),
      ("line", [(18, 18.6), (22.5, 22), (18, 25.4)], {}))


def _shape_points(shape, x, y, scale):
    kind = shape[0]
    if kind in ("line", "poly"):
        points = shape[1]
        return [(x + px * scale, y + py * scale) for px, py in points]
    return None


def draw(canvas, name, x, y, size, colour, width=1.9, tags=()):
    """Draw `name` into `canvas`, `size` px square, top-left at (x, y).

    `width` is a stroke weight in the 24-unit square, scaled with
    everything else, so an icon drawn at 40px is not a 19px icon with a
    hairline round it.

    Drawn as a picture rather than as canvas lines and arcs, and that is
    not an implementation detail. Tk's canvas draws its own primitives
    with no anti-aliasing at all on Windows and Linux: a gear at
    seventeen pixels comes out as a handful of stepped black dots, and
    the smaller the icon the worse it looks — which is every icon in the
    rail, every chevron, and the marks on both controls in the corner.
    The same shapes rendered four times up and reduced are smooth
    everywhere, and cost one cached image per icon, size and colour.

    On macOS it is the other way round, and for the same reason stated
    backwards. Tk's canvas there draws through CoreGraphics, which
    anti-aliases and — this is the part that matters — draws at the
    display's own resolution. A Retina screen has two device pixels to
    the point, and text on it is drawn with all four; a picture is not.
    Tk has no way to say "this image is two pixels to the point", so a
    PhotoImage is always drawn one image pixel to the point and stretched
    to fill, which on a Retina Mac is every icon in the app at half
    resolution. Measured on a screenshot of the Settings pane: the word
    beside the gear has 165 distinct grey levels along its edges and the
    gear has eight.

    So the picture is for the platforms whose canvas cannot draw smoothly,
    and the canvas is for the platform whose canvas draws better than a
    picture can.

    An unknown name draws nothing rather than raising: an icon that does
    not appear is a blemish, and a window that does not open is not.
    """
    shapes = _ICONS.get(name)
    if not shapes:
        return []
    if not DRAWN_BY_HAND:
        photo = _picture(name, size, colour, width, canvas)
        if photo is not None:
            return [canvas.create_image(x, y, anchor="nw", image=photo,
                                        tags=tags)]
    return _draw_vector(canvas, shapes, x, y, size, colour, width, tags)


#: Icons already rendered, by name, size, colour, weight and which Tk
#: they were made for. A PhotoImage belongs to one interpreter and is
#: meaningless to another — see the same note in ui_home.
_pictures = {}
#: How far up an icon is drawn before it is reduced, when nothing better
#: is worked out. See `_oversample`, which usually picks a better one.
OVER = 8
#: The range `_oversample` is allowed to choose from. Eight is already
#: past the point where the sampling itself shows; the rest of the range
#: is there so the stroke can come out the weight it was asked for.
OVER_MIN, OVER_MAX = 8, 24


def _weights(name, width):
    """Every stroke weight this icon uses, in the 24-unit square."""
    used = {round(float(width), 3)}
    for shape in _ICONS.get(name, ()):
        options = shape[len(shape) - 1]
        if isinstance(options, dict) and options.get("width"):
            used.add(round(float(options["width"]), 3))
    return sorted(used)


def _oversample(name, size, width):
    """How far up to draw this icon, at this size, to get the weight right.

    The imaging library takes a stroke width in whole pixels. The icon
    asks for 1.9 of the 24 units it is drawn in, which at seventeen
    pixels and four times up is 5.38 pixels — and 5 is what gets drawn.
    That is a stroke seven per cent thin, and seven per cent of a stroke
    that is only a pixel and a quarter wide is the difference between a
    line and a smudge. Worse, the error changes with the size, so the
    same icon is a different weight in the rail than it is on a card, and
    that is the sort of thing that is seen long before it is named.

    So the multiple is not fixed. Every weight the icon uses is asked
    what it would come out as at each multiple in the range, and the one
    that gets them all closest to what was asked for wins. Measured
    against a forty-eight-times reference, this takes the average error
    of a finished pixel from about nine grey levels to under two.
    """
    wanted = _weights(name, width)
    best, best_miss = OVER, None
    for over in range(OVER_MIN, OVER_MAX + 1):
        scale = size * over / BOX
        miss = 0.0
        for w in wanted:
            drawn = max(1, int(round(w * scale))) / scale
            miss += abs(drawn - w) / w
        if best_miss is None or miss < best_miss - 1e-9:
            best, best_miss = over, miss
    return best

#: Which way round to draw, per platform. See `draw`.
#:
#: Tk's canvas has no anti-aliasing at all on Windows and Linux, so
#: there a rendered picture is the only way to get a smooth edge. On
#: macOS the canvas goes through CoreGraphics, which anti-aliases *and*
#: draws at the screen's real resolution — so there the canvas is the
#: only way to get a sharp one, because a PhotoImage is drawn one image
#: pixel to the point and a Retina point is two pixels wide.
DRAWN_BY_HAND = (sys.platform == "darwin")


def _interp(owner):
    try:
        return id(owner.tk)
    except Exception:                                      # pragma: no cover
        return 0


def _picture(name, size, colour, width, owner):
    """The icon as an anti-aliased picture, or None if it cannot be."""
    size = max(4, int(round(float(size))))
    key = (name, size, colour, round(float(width), 2), _interp(owner))
    hit = _pictures.get(key)
    if hit is not None:
        return hit
    try:
        from PIL import Image, ImageDraw, ImageTk
    except Exception:                                      # pragma: no cover
        return None
    try:
        box = size * _oversample(name, size, width)
        # Drawn as coverage, not as colour. The obvious way is to draw
        # the icon in its own colour on a transparent square and reduce
        # that, and it is subtly wrong: a transparent pixel is stored as
        # transparent *black*, the reduction averages those blacks into
        # the colour of every edge pixel, and the result is a dark rim
        # around a pale icon. Drawing the coverage on its own and putting
        # the colour in flat afterwards cannot do that — every pixel is
        # the same colour and only its opacity varies. Measured against
        # an eight-times reference, it also halves the error of the
        # reduction itself.
        mask = Image.new("L", (box, box), 0)
        pen = ImageDraw.Draw(mask)
        scale = box / BOX
        stroke = max(1, int(round(float(width) * scale)))
        for shape in _ICONS[name]:
            _paint(pen, shape, scale, 255, stroke)
        # A whole number of source pixels to each finished one, so this
        # is a plain average of the square — the exact answer, and with
        # none of the ringing a sharpening filter leaves along an edge.
        mask = mask.resize((size, size), Image.BOX)
        img = Image.new("RGBA", (size, size), _rgba(colour))
        img.putalpha(mask)
        photo = ImageTk.PhotoImage(img, master=owner)
    except Exception:                                      # pragma: no cover
        return None
    if len(_pictures) > 400:
        _pictures.clear()
    _pictures[key] = photo
    return photo


def _rgba(colour):
    value = str(colour).lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    try:
        return (int(value[0:2], 16), int(value[2:4], 16),
                int(value[4:6], 16), 255)
    except Exception:                                      # pragma: no cover
        return (0, 0, 0, 255)


def _smooth(points, steps=12):
    """A Catmull-Rom curve through the points.

    Tk's `smooth` is a spline through the control points, and several of
    these shapes are drawn as one — a heart, a bulb, the crescent of the
    moon. Sampling the same curve keeps them the shapes they were.
    """
    if len(points) < 3:
        return list(points)
    pad = [points[0]] + list(points) + [points[-1]]
    out = []
    for n in range(len(pad) - 3):
        p0, p1, p2, p3 = pad[n], pad[n + 1], pad[n + 2], pad[n + 3]
        for step in range(steps):
            t = step / float(steps)
            t2, t3 = t * t, t * t * t
            out.append((
                0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t +
                       (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
                       (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
                0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t +
                       (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
                       (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)))
    out.append(points[-1])
    return out


#: The thinnest line worth drawing on a canvas. Below about this the
#: renderer has nothing to shade and the stroke starts disappearing in
#: places, which looks like a broken icon rather than a faint one.
MIN_STROKE = 0.75


def _weight(width, scale):
    """A stroke in the 24-unit square, as a distance on the canvas.

    Not rounded. See the note in `_draw_vector` — the rounding was the
    fault, not the cure for one.
    """
    return max(MIN_STROKE, float(width) * scale)


def _paint(pen, shape, scale, ink, stroke):
    """One shape, into the supersampled picture."""
    kind = shape[0]
    if kind == "line":
        options = shape[2] if len(shape) > 2 else {}
        own = options.get("width")
        weight = (max(1, int(round(float(own) * scale))) if own else stroke)
        points = [(x * scale, y * scale) for x, y in shape[1]]
        if options.get("smooth"):
            points = _smooth(points)
        pen.line(points, fill=ink, width=weight, joint="curve")
        # Round caps. The imaging library draws square ends, and a gear
        # tooth with square ends is a brick.
        radius = weight / 2.0
        for x, y in (points[0], points[-1]):
            pen.ellipse([x - radius, y - radius, x + radius, y + radius],
                        fill=ink)
    elif kind == "poly":
        pen.polygon([(x * scale, y * scale) for x, y in shape[1]], fill=ink)
    elif kind == "ellipse":
        _k, cx, cy, rx, ry = shape
        pen.ellipse([(cx - rx) * scale, (cy - ry) * scale,
                     (cx + rx) * scale, (cy + ry) * scale],
                    outline=ink, width=stroke)
    elif kind in ("oval", "disc"):
        _k, cx, cy, r = shape[:4]
        options = shape[4] if len(shape) > 4 else {}
        own = options.get("width")
        weight = (max(1, int(round(float(own) * scale))) if own else stroke)
        box = [(cx - r) * scale, (cy - r) * scale,
               (cx + r) * scale, (cy + r) * scale]
        if kind == "disc":
            pen.ellipse(box, fill=ink)
        else:
            pen.ellipse(box, outline=ink, width=weight)
    elif kind == "arc":
        _k, cx, cy, r, start, extent = shape[:6]
        options = shape[6] if len(shape) > 6 else {}
        own = options.get("width")
        weight = (max(1, int(round(float(own) * scale))) if own else stroke)
        box = [(cx - r) * scale, (cy - r) * scale,
               (cx + r) * scale, (cy + r) * scale]
        # Tk measures angles anticlockwise from three o'clock; the
        # imaging library measures them clockwise, on a y-down canvas.
        # Same circle, mirrored — so the sweep is negated and reversed.
        pen.arc(box, -(start + extent), -start, fill=ink, width=weight)
    elif kind == "rect":
        _k, x0, y0, x1, y1, radius = shape
        pen.rounded_rectangle([x0 * scale, y0 * scale,
                               x1 * scale, y1 * scale],
                              radius=radius * scale, outline=ink,
                              width=stroke)


def _draw_vector(canvas, shapes, x, y, size, colour, width, tags):
    """Tk's own canvas primitives. The path macOS takes, and the fallback
    for a machine with no imaging library.

    The stroke is a fraction and is passed as one. It was rounded to a
    whole pixel for years, which was the single worst thing in the
    drawing and was invisible to every test because it looks correct in
    isolation: 1.9 units of a 24-unit square is 1.35 pixels on a
    seventeen-pixel icon, and a whole number of pixels is 1 — twenty-six
    per cent thin. Three pixels larger, at twenty, the same rounding
    gives 2 — twenty-six per cent heavy. So two icons a few pixels apart
    in size, side by side in the same window, differed in weight by more
    than half, and the thin one looked ragged while the fat one looked
    soft. Tk takes a screen distance here, not a pixel count, and has
    always accepted a fraction; nothing was gained by rounding it.

    The floor is there so that an icon drawn very small still has a line
    rather than nothing at all.
    """
    scale = float(size) / BOX
    stroke = _weight(width, scale)
    made = []
    for shape in shapes:
        kind = shape[0]
        try:
            if kind == "line":
                points = _shape_points(shape, x, y, scale)
                options = shape[2] if len(shape) > 2 else {}
                own = options.get("width")
                weight = _weight(own, scale) if own else stroke
                flat = [n for point in points for n in point]
                made.append(canvas.create_line(
                    *flat, fill=colour, width=weight, capstyle="round",
                    joinstyle="round", smooth=bool(options.get("smooth")),
                    splinesteps=48, tags=tags))
            elif kind == "poly":
                points = _shape_points(shape, x, y, scale)
                flat = [n for point in points for n in point]
                made.append(canvas.create_polygon(
                    *flat, fill=colour, outline="", tags=tags))
            elif kind == "ellipse":
                _k, cx, cy, rx, ry = shape
                made.append(canvas.create_oval(
                    x + (cx - rx) * scale, y + (cy - ry) * scale,
                    x + (cx + rx) * scale, y + (cy + ry) * scale,
                    outline=colour, width=stroke, fill="", tags=tags))
            elif kind in ("oval", "disc"):
                _k, cx, cy, r = shape[:4]
                options = shape[4] if len(shape) > 4 else {}
                own = options.get("width")
                weight = _weight(own, scale) if own else stroke
                box = (x + (cx - r) * scale, y + (cy - r) * scale,
                       x + (cx + r) * scale, y + (cy + r) * scale)
                if kind == "disc":
                    made.append(canvas.create_oval(*box, fill=colour,
                                                   outline="", tags=tags))
                else:
                    made.append(canvas.create_oval(
                        *box, outline=colour, width=weight, fill="",
                        tags=tags))
            elif kind == "arc":
                _k, cx, cy, r, start, extent = shape[:6]
                options = shape[6] if len(shape) > 6 else {}
                own = options.get("width")
                weight = _weight(own, scale) if own else stroke
                box = (x + (cx - r) * scale, y + (cy - r) * scale,
                       x + (cx + r) * scale, y + (cy + r) * scale)
                made.append(canvas.create_arc(
                    *box, start=start, extent=extent, style="arc",
                    outline=colour, width=weight, tags=tags))
            elif kind == "rect":
                _k, x0, y0, x1, y1, radius = shape
                made.extend(_rounded_rect(
                    canvas, x + x0 * scale, y + y0 * scale,
                    x + x1 * scale, y + y1 * scale, radius * scale,
                    colour, stroke, tags))
        except Exception:
            continue
    return made


def _rounded_rect(canvas, x0, y0, x1, y1, radius, colour, width, tags):
    """A rounded outline, as four sides and four arcs.

    Tk has no rounded rectangle. A polygon with `smooth` rounds every
    corner by an amount nobody chose; this rounds them by the radius
    asked for.
    """
    r = max(0.0, min(radius, (x1 - x0) / 2.0, (y1 - y0) / 2.0))
    made = []
    for points in (((x0 + r, y0), (x1 - r, y0)), ((x1, y0 + r), (x1, y1 - r)),
                   ((x1 - r, y1), (x0 + r, y1)), ((x0, y1 - r), (x0, y0 + r))):
        flat = [n for point in points for n in point]
        made.append(canvas.create_line(*flat, fill=colour, width=width,
                                       capstyle="round", tags=tags))
    if r > 0:
        for box, start in (((x1 - 2 * r, y0, x1, y0 + 2 * r), 0),
                           ((x1 - 2 * r, y1 - 2 * r, x1, y1), 270),
                           ((x0, y1 - 2 * r, x0 + 2 * r, y1), 180),
                           ((x0, y0, x0 + 2 * r, y0 + 2 * r), 90)):
            made.append(canvas.create_arc(*box, start=start, extent=90,
                                          style="arc", outline=colour,
                                          width=width, tags=tags))
    return made


class Icon(__import__("tkinter").Canvas):
    """One icon on its own, in a canvas sized to it.

    Used where an icon stands alone — a nav row, a round button. Where
    an icon shares a canvas with text or a background, call `draw`
    directly instead of nesting a widget.
    """

    def __init__(self, parent, name, size, colour, bg, width=1.9, pad=0):
        import tkinter as tk
        side = int(size) + 2 * int(pad)
        tk.Canvas.__init__(self, parent, width=side, height=side, bg=bg,
                           highlightthickness=0, bd=0, takefocus=0)
        self.name = name
        self.size = int(size)
        self.pad = int(pad)
        self.stroke = width
        self._colour = colour
        self._paint()

    def _paint(self):
        self.delete("all")
        draw(self, self.name, self.pad, self.pad, self.size, self._colour,
             self.stroke)

    def set_colour(self, colour):
        if colour == self._colour:
            return
        self._colour = colour
        self._paint()

    def set_icon(self, name):
        if name == self.name:
            return
        self.name = name
        self._paint()

    def set_bg(self, colour):
        try:
            self.configure(bg=colour)
        except Exception:
            pass
