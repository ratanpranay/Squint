"""The front page, built to the design.

Everything here draws on a canvas rather than asking Tk for a widget,
for the same reason the rest of the kit does: Tk's own buttons and
frames are square, flat and the system's colour, and no amount of
configuring makes one into a pill with a gradient down it.

Two rules run through the whole file and are worth stating once.

**Colour comes from `theme.page`, not from `theme.resolve`.** They are
different palettes on purpose — see the note beside them. Every widget
here takes the page palette as `page` and the enclosing background as
`bg`, because a canvas has a real background and getting it wrong shows
up as a pale rectangle round a round button.

**Text comes from `theme.ui_font`, symbols come from `ui_icons`.** The
interface face has no arrow, tick, chevron, gear or heart in it, so
every mark in the design is drawn. The one deliberate exception is the
keycaps: ⌘ and ⇧ are symbols the *system* face has and the interface
face does not, and spelling them out as "Cmd" is not what a keycap looks
like on a Mac. They are set in the system face, which is what a browser
would do with the same stylesheet.
"""
import tkinter as tk
import tkinter.font as tkfont

from . import theme as theme_mod, ui_icons
from .ui_kit import (VECTOR_PLATES, plate_item, rounded,
                     rounded_image, rounded_on, set_plate)

try:
    from PIL import Image, ImageDraw, ImageTk
except Exception:                                          # pragma: no cover
    Image = ImageDraw = ImageTk = None

#: The rail, measured off the design rather than guessed: 334 pixels of
#: a 2266-pixel window, at the 1.6 the rest of these numbers came out of.
RAIL_W = 209
#: What the nav rows and the brand block are inset by, each side. The
#: rail's width minus twice this is the width of a nav pill, which is how
#: the two were measured and how they have to stay related.
RAIL_PAD = 15


#: One knob for the whole page. The design's numbers are final sizes,
#: not suggestions to be multiplied — see the note in `theme.ui_font`.
#: It is here rather than absent so that if the page turns out to read
#: small on a display nobody here has, there is one number to change
#: and everything moves together: type, spacing, icons and radii alike.
SCALE = 1.0

#: The most of the window the photograph at the top may take, in pixels,
#: set by the window when it works out its size. The band is measured
#: from its own width — it is a photograph and it has a shape — but on a
#: screen that is wide and short, a band in proportion to the width is
#: most of the height, and the page under it is what the page is for.
#: Nought means no limit. Like SCALE, it is here rather than passed in
#: because the widget that reads it is built before the window knows.
HERO_CAP = 0

#: The sample in the picture at the top, and the face that can draw it,
#: worked out once. See HeroBanner._source_text.
_sample_face = None

#: Set while the page is being rebuilt from scratch — a theme change.
#: The band is handed four or five different widths on the way to the
#: final one, each of them a full repaint of a photograph, and four of
#: them thrown away. While this is set it remembers the size and paints
#: nothing; `HeroBanner.flush()` at the end paints once, at the size
#: that turned out to be the real one.
SETTLING = False

#: The photograph, cropped and lifted, at the last couple of sizes it
#: was asked for. It does not depend on the theme — the veil over it
#: does — so a light-to-dark change repaints the band without opening,
#: resizing and sharpening a picture it already has. That change builds
#: a whole second window while somebody watches, and this is a tenth of
#: a second of it.
_plates = {}


def px(n):
    """A design measurement in this display's pixels."""
    return max(1, int(round(float(n) * SCALE)))


def pt(n):
    """A design type size, in pixels.

    Negative, because that is how Tk is told a size is in pixels rather
    than points — see `theme._exact`. Every number in the design is a
    pixel measurement, so every one of them comes through here.
    """
    return -max(6, int(round(float(n) * SCALE)))


def font_for(parent, size=15, weight=400):
    """A font tuple at the page's own scale, for the widgets that came
    from the kit and would otherwise size themselves."""
    return theme_mod.ui_font(parent, pt(size), weight, scale=False)


def text(parent, page, string, size=11, weight=400, colour="ink", bg=None,
         **kwargs):
    """A label in the interface face."""
    return tk.Label(parent, text=string, bd=0,
                    bg=bg or page["card"], fg=page[colour],
                    font=theme_mod.ui_font(parent, pt(size), weight,
                                           scale=False),
                    **kwargs)


def hand(parent, page, string, size=15, colour="dim", bg=None, **kwargs):
    """A label in the handwritten face."""
    return tk.Label(parent, text=string, bd=0,
                    bg=bg or page["card"], fg=page[colour],
                    font=theme_mod.script_font(parent, pt(size),
                                               scale=False),
                    **kwargs)


# -- pictures -------------------------------------------------------------
#
# Cached, and keyed by the interpreter as well as by the picture. A
# PhotoImage belongs to the Tk it was made in and is meaningless to any
# other: hand a second interpreter an image cached from the first and
# the canvas reports that the image does not exist, which is not a
# message anybody traces back to a cache. One interpreter is the normal
# case and two is not exotic — a theme change puts the window up again,
# and the tests build several in a row.
_gradients = {}


def _interp(owner):
    """Which Tk an image is being made for."""
    try:
        return id(owner.tk)
    except Exception:
        return 0


def gradient(width, height, top, bottom, owner=None, radius=0, angle=165):
    """A vertical wash as a PhotoImage, optionally with rounded corners.

    The design's washes are at an angle. A diagonal gradient across a
    236-pixel rail is a vertical one with a lean nobody can see, so this
    draws vertical and keeps the angle for the one place it reads: the
    brand square, which is small enough and saturated enough that the
    diagonal is the whole character of it.
    """
    if Image is None:                                      # pragma: no cover
        return None
    width, height = max(1, int(width)), max(1, int(height))
    key = (_interp(owner), width, height, top, bottom, radius, angle)
    hit = _gradients.get(key)
    if hit is not None:
        return hit
    a = Image.new("RGB", (1, height))
    pa, pb = _rgb(top), _rgb(bottom)
    draw = ImageDraw.Draw(a)
    for y in range(height):
        f = y / max(1, height - 1)
        draw.point((0, y), fill=tuple(int(round(pa[n] + (pb[n] - pa[n]) * f))
                                      for n in range(3)))
    img = a.resize((width, height), Image.BILINEAR).convert("RGBA")
    if radius:
        img.putalpha(_round_mask(width, height, radius))
    photo = ImageTk.PhotoImage(img, master=owner)
    _gradients[key] = photo
    return photo


def _rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[n:n + 2], 16) for n in (0, 2, 4))


#: Supersampling for the one mask in this file. See `_round_mask`.
MASK_SS = 4


def _round_mask(width, height, radius):
    """A rounded-rectangle mask with a smooth edge.

    The imaging library draws a rounded rectangle with no anti-aliasing
    at all: every pixel is in or out, so the corner is a staircase. That
    is fine for a shape whose colour is then blurred over it and not
    fine for a mask, which is what decides where the brand tile stops —
    so the tile has had four stepped corners on every platform since it
    was drawn, and it is the one shape in the app that never went
    through the kit's own rounded-rectangle, which has always drawn at
    four times the size and reduced for exactly this reason.
    """
    big = Image.new("L", (width * MASK_SS, height * MASK_SS), 0)
    ImageDraw.Draw(big).rounded_rectangle(
        [0, 0, width * MASK_SS - 1, height * MASK_SS - 1],
        radius=int(radius * MASK_SS), fill=255)
    return big.resize((width, height), Image.LANCZOS)


def three_stop(width, height, a, b, c, owner=None, radius=0):
    """The brand square: three stops on a diagonal."""
    if Image is None:                                      # pragma: no cover
        return None
    key = ("three", _interp(owner), width, height, a, b, c, radius)
    hit = _gradients.get(key)
    if hit is not None:
        return hit
    width, height = max(1, int(width)), max(1, int(height))
    img = Image.new("RGBA", (width, height))
    pa, pb, pc = _rgb(a), _rgb(b), _rgb(c)
    span = float(width + height)
    pixels = img.load()
    for y in range(height):
        for x in range(width):
            f = (x * 0.62 + y) / span * 1.35
            f = min(1.0, max(0.0, f))
            if f <= 0.55:
                g, lo, hi = f / 0.55, pa, pb
            else:
                g, lo, hi = (f - 0.55) / 0.45, pb, pc
            pixels[x, y] = tuple(
                int(round(lo[n] + (hi[n] - lo[n]) * g)) for n in range(3)
            ) + (255,)
    if radius:
        img.putalpha(_round_mask(width, height, radius))
    photo = ImageTk.PhotoImage(img, master=owner)
    _gradients[key] = photo
    return photo


# -- the pieces -----------------------------------------------------------
class Mark(tk.Canvas):
    """The brand square: a rounded gradient tile with the selection mark
    cut out of it in white."""

    def __init__(self, parent, page, bg, size=62):
        side = px(size)
        radius = px(size * 0.274)
        tk.Canvas.__init__(self, parent, width=side, height=side, bg=bg,
                           highlightthickness=0, bd=0, takefocus=0)
        # The gradient has to be a picture — it is a different colour at
        # every pixel and there is no canvas primitive for that. Its
        # *corners* do not: the rounding was done in the picture, so the
        # four curves were bitmap curves, and on a screen that draws two
        # device pixels to the point they are the stepped corners in
        # every screenshot of this mark.
        #
        # So the picture is a plain square now, and the corners are cut
        # out of it afterwards by the canvas, in the colour behind it.
        # The flat inside of a gradient cannot look stepped; only an edge
        # can, and every edge here is drawn rather than placed.
        self._photo = three_stop(side, side, page["mark_a"], page["mark_b"],
                                 page["mark_c"], owner=self,
                                 radius=0 if VECTOR_PLATES
                                 else radius)
        if self._photo is not None:
            self.create_image(0, 0, anchor="nw", image=self._photo)
        if VECTOR_PLATES and self._photo is not None:
            self._cut_corners(side, radius, bg)
        inset = side * 0.26
        ui_icons.draw(self, "crop", inset, inset, side - inset * 2,
                      "#FFFFFF", width=2.3)

    def _cut_corners(self, side, radius, bg):
        """Take the four corners off the square, smoothly.

        The piece removed is the square of the corner minus the quarter
        circle inside it, which is one polygon: out along the edge, round
        the arc, and back. Drawn in the colour behind the mark, so what
        is left reads as a rounded tile.
        """
        import math
        from .ui_kit import corner_steps
        steps = corner_steps(radius)
        # The piece taken out is the corner of the square minus the
        # quarter circle inside it, and it has to run a little past the
        # tile on both edges. Past, not up to: a cut that stops exactly
        # on the edge leaves the outermost pixel of the corner behind,
        # and one pixel on a curve is what a stepped corner is made of.
        #
        # The overshoot goes on the *arc's ends* as well as on the
        # corner point, which is what the first version got wrong. With
        # only the corner moved out, the polygon closed from the end of
        # the arc straight back to it — a line that cuts across the flat
        # edge of the tile and takes a notch out of it. There were two
        # of those on the left edge of the mark and one along the top.
        over = 2
        # (corner x, corner y, arc centre offset, arc start, arc end)
        corners = ((0, 0, 180.0, 270.0), (side, 0, 270.0, 360.0),
                   (side, side, 0.0, 90.0), (0, side, 90.0, 180.0))
        for cx, cy, start, end in corners:
            ox = radius if cx == 0 else -radius
            oy = radius if cy == 0 else -radius
            out_x = -over if cx == 0 else over
            out_y = -over if cy == 0 else over
            arc = []
            for step in range(steps + 1):
                angle = math.radians(start + (end - start) * step / steps)
                arc.append((cx + ox + radius * math.cos(angle),
                            cy + oy + radius * math.sin(angle)))
            first, last = arc[0], arc[-1]
            points = [cx + out_x, cy + out_y,
                      first[0] + out_x, first[1]]
            for x, y in arc:
                points.extend((x, y))
            points.extend((last[0], last[1] + out_y))
            self.create_polygon(points, fill=bg, outline=bg, width=1)


class NavButton(tk.Canvas):
    """A row in the rail: an icon, a word, and a soft pill behind it when
    it is the one you are looking at."""

    def __init__(self, parent, page, label_text, icon, command, bg):
        self.page = page
        self.command = command
        self.icon = icon
        self._bg = bg
        self._selected = False
        self._hover = False
        self._dot = False
        self._font = tkfont.Font(**_font_kw(parent, 13, 500))
        self._font_on = tkfont.Font(**_font_kw(parent, 13, 600))
        self._text = label_text
        height = px(44)
        width = px(RAIL_W - RAIL_PAD * 2)
        tk.Canvas.__init__(self, parent, width=width, height=height, bg=bg,
                           highlightthickness=0, bd=0, cursor="arrow")
        self._height, self._width = height, width
        self._paint()
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Button-1>", self._click)

    def _enter(self, _event=None):
        self._hover = True
        self._paint()

    def _leave(self, _event=None):
        self._hover = False
        self._paint()

    def _click(self, _event=None):
        if self.command:
            try:
                self.command()
            except Exception:
                pass

    def select(self, on):
        if on == self._selected:
            return
        self._selected = on
        self._paint()

    def set_dot(self, on):
        """A red dot on the icon: something here wants attention."""
        on = bool(on)
        if on == self._dot:
            return
        self._dot = on
        self._paint()

    def _paint(self):
        self.delete("all")
        p = self.page
        if self._selected:
            fill, ink = p["accent_soft"], p["accent"]
        elif self._hover:
            fill, ink = p["field"], p["ink_2"]
        else:
            fill, ink = None, p["ink_2"]
        if fill:
            self._photo = rounded_on(self, 0, 0, self._width, self._height,
                                     px(13), fill)
        size = px(20)
        left = px(14)
        ui_icons.draw(self, self.icon, left, (self._height - size) / 2.0, size,
                      ink, width=1.9)
        self.create_text(left + size + px(13),
                         theme_mod.middle(self._height, self._font),
                         anchor="w", text=self._text, fill=ink,
                         font=self._font_on if self._selected else self._font)
        if self._dot:
            # Drawn smooth, like the pill behind it: a plain Tk oval this
            # small comes out as a square.
            d = px(10)
            x0 = int(left + size - d * 0.3)
            y0 = int((self._height - size) / 2.0 - d * 0.35)
            self._dot_photo = rounded_on(self, x0, y0, d, d, d / 2.0,
                                         "#F04438")


def _font_kw(parent, size, weight):
    family, tk_weight = theme_mod.ui_family(weight, parent)
    return {"family": family, "size": pt(size), "weight": tk_weight}


def _font_px(parent, pixels, weight):
    """A face at an exact pixel size, for type that has worked out its
    own size — the band at the top of the page shrinks its block until
    it fits, and what it arrives at is a number of pixels, not a design
    size waiting to be scaled."""
    family, tk_weight = theme_mod.ui_family(weight, parent)
    return {"family": family, "size": -max(6, int(round(pixels))),
            "weight": tk_weight}


def _system_font_kw(parent, size, weight="normal"):
    """The system face, for the handful of symbols the interface face
    has no glyph for — the modifier keys on a keycap, and nothing else."""
    return {"family": theme_mod.body_family(parent), "size": pt(size),
            "weight": weight}


class Rail(tk.Frame):
    """The sidebar: who this is, where you can go, and what build it is."""

    ITEMS = (("Home", "home", "Translate"),
             ("Settings", "gear", "Settings"),
             ("Updates", "download", "Updates"),
             ("Support", "heart", "Support"))

    def __init__(self, parent, page, go, version):
        self.page = page
        tk.Frame.__init__(self, parent, bg=page["rail"], width=px(RAIL_W))
        self.pack_propagate(False)
        bg = page["rail"]

        # Centred, not left-aligned: in the design the mark, the wordmark
        # and the line under it all sit on the rail's centre line, and
        # the nav pills below them are full width. Left-aligning the
        # three of them is the single change that made the rail look
        # like a different design from the one it was drawn from.
        brand = tk.Frame(self, bg=bg)
        brand.pack(fill="x", padx=px(RAIL_PAD), pady=(px(26), 0))
        Mark(brand, page, bg, size=65).pack()
        text(brand, page, "Squint", size=25, weight=700, bg=bg).pack(
            pady=(px(10), 0))
        text(brand, page, "Snap. Translate.\nUnderstand.", size=13,
             weight=400, colour="dim", bg=bg, justify="center").pack(
                 pady=(px(2), 0))

        nav = tk.Frame(self, bg=bg)
        nav.pack(fill="x", padx=px(RAIL_PAD), pady=(px(36), 0))
        self.buttons = {}
        for label_text, icon, pane in self.ITEMS:
            button = NavButton(nav, page, label_text, icon,
                               (lambda name=pane: go(name)), bg)
            button.pack(anchor="w", pady=px(2))
            self.buttons[pane] = button

        foot = tk.Frame(self, bg=bg)
        foot.pack(side="bottom", fill="x", padx=px(26), pady=(0, px(20)))
        text(foot, page, version, size=12, colour="faint", bg=bg).pack(
            anchor="w")
        text(foot, page, "© Pranay ’26", size=12, colour="faint",
             bg=bg).pack(anchor="w")

    def select(self, pane):
        for name, button in self.buttons.items():
            button.select(name == pane)


class ThemeToggle(tk.Canvas):
    """One button, both marks: click it and the page changes scheme.

    It was two halves of a pill, one per scheme, and you had to hit the
    right half — a thirty-point target for a thing with exactly two
    states and no ambiguity about which one you want next. The whole
    pill is the button now; the marks stay, because what they say is
    which scheme you are in and which one is on the other side of the
    click.

    `glow` is what makes the change gradual on the button as well as in
    the window: the highlight and the two marks are redrawn at any point
    between the two states, and the window's own dimming walks it from
    one end to the other.
    """

    def __init__(self, parent, page, command, bg, current="light"):
        self.page = page
        self.command = command
        self._choice = current
        self._glow = 0.0 if current == "light" else 1.0
        self._hover = False
        # The same height as the pill beside it. They sit in a row in
        # the corner and they are the same kind of thing; two pills of
        # different heights next to each other is the sort of mismatch
        # you see before you can say what it is.
        pad, cell_w, cell_h = px(4), px(34), px(36)
        width = pad * 2 + cell_w * 2
        height = pad * 2 + cell_h
        tk.Canvas.__init__(self, parent, width=width, height=height, bg=bg,
                           highlightthickness=0, bd=0, cursor="arrow")
        self._width, self._height = width, height
        self._pad, self._cw, self._ch = pad, cell_w, cell_h
        self._paint()
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", lambda _e=None: self._set_hover(True))
        self.bind("<Leave>", lambda _e=None: self._set_hover(False))

    def _set_hover(self, on):
        self._hover = on
        self._paint()

    def _click(self, _event=None):
        choice = "dark" if self._choice == "light" else "light"
        self.set(choice)
        if self.command:
            try:
                self.command(choice)
            except Exception:
                pass

    def set(self, choice):
        self._choice = choice
        self._glow = 0.0 if choice == "light" else 1.0
        self._paint()

    def glow(self, value):
        """Part way between the two states, for the length of a fade."""
        self._glow = max(0.0, min(1.0, float(value)))
        self._paint()

    def backdrop(self, photo):
        """The band's own pixels, to stand on instead of a flat colour.

        A canvas widget has a background, and one colour behind a
        rounded pill on a photograph leaves the pill sitting in a little
        square of the wrong blue. Averaging the pixels underneath got
        the colour right and the square stayed: a gradient sky is not
        one colour, and the eye finds the join. So the widget is given
        the picture it covers and draws it under itself.
        """
        self._under = photo
        self._paint()

    def _paint(self):
        self.delete("all")
        p = self.page
        under = getattr(self, "_under", None)
        if under is not None:
            self.create_image(0, 0, anchor="nw", image=under)
        self._shell = rounded_on(self, 0, 0, self._width, self._height,
                                 self._height // 2,
                                 p["field"] if self._hover else p["card"],
                                 outline=p["line"])
        # The highlight slides rather than jumping between two cells:
        # halfway through the fade it is halfway across.
        x = self._pad + self._glow * self._cw
        self._cell = rounded_on(self, x, self._pad, self._cw, self._ch,
                                self._ch // 2, p["accent_soft"])
        size = px(17)
        for index, icon in enumerate(("sun", "moon")):
            near = 1.0 - abs(self._glow - index)
            ui_icons.draw(self, icon,
                          self._pad + index * self._cw + (self._cw - size) / 2.0,
                          self._pad + (self._ch - size) / 2.0, size,
                          _mix(p["faint"], p["accent"], near), width=1.9)


def _mix(a, b, amount):
    """Between two colours. The theme button's marks are drawn part way
    from one to the other while the window is fading."""
    amount = max(0.0, min(1.0, float(amount)))
    return "#%02x%02x%02x" % tuple(
        int(round(x + (y - x) * amount)) for x, y in zip(_rgb(a), _rgb(b)))


class IconTextPill(tk.Canvas):
    """A bordered pill with an icon and a word — the top-bar Settings
    button, and the file button inside the drop target."""

    def __init__(self, parent, page, label_text, icon, command, bg,
                 height=44, size=15, weight=500, icon_colour="ink_2",
                 fill="card"):
        self.page = page
        self.command = command
        self.icon = icon
        self._fill_key = fill
        self._icon_colour = icon_colour
        self._hover = False
        self._font = tkfont.Font(**_font_kw(parent, size, weight))
        self._text = label_text
        h = px(height)
        icon_size = px(18)
        width = (px(16) + icon_size + px(9) +
                 self._font.measure(label_text) + px(20))
        tk.Canvas.__init__(self, parent, width=width, height=h, bg=bg,
                           highlightthickness=0, bd=0, cursor="arrow")
        self._width, self._height, self._icon_size = width, h, icon_size
        self._paint()
        self.bind("<Enter>", lambda _e=None: self._set_hover(True))
        self.bind("<Leave>", lambda _e=None: self._set_hover(False))
        self.bind("<Button-1>", self._click)

    def _set_hover(self, on):
        self._hover = on
        self._paint()

    def _click(self, _event=None):
        if self.command:
            try:
                self.command()
            except Exception:
                pass

    def backdrop(self, photo):
        """The band's own pixels under the pill. See ThemeToggle."""
        self._under = photo
        self._paint()

    def _paint(self):
        self.delete("all")
        p = self.page
        under = getattr(self, "_under", None)
        if under is not None:
            self.create_image(0, 0, anchor="nw", image=under)
        fill = p["field"] if self._hover else p[self._fill_key]
        self._photo = rounded_on(self, 0, 0, self._width, self._height,
                                 self._height // 2, fill,
                                 outline=p["line"])
        ui_icons.draw(self, self.icon, px(16),
                      (self._height - self._icon_size) / 2.0, self._icon_size,
                      p[self._icon_colour], width=1.9)
        self.create_text(px(16) + self._icon_size + px(9),
                         theme_mod.middle(self._height, self._font),
                         anchor="w", text=self._text, fill=p["ink"],
                         font=self._font)


class SnipButton(tk.Canvas):
    """The one button the whole page is built around.

    A gradient, the selection mark, the words, and the shortcut set in
    keycaps — the last of those in the system face, because ⌘ and ⇧ are
    not in the interface one and "Cmd" is not what is printed on the key.
    """

    def __init__(self, parent, page, label_text, keys, command, bg,
                 height=54):
        self.page = page
        self.command = command
        self._state = "normal"
        self._font = tkfont.Font(**_font_kw(parent, 17, 500))
        self._key_font = tkfont.Font(**_system_font_kw(parent, 13))
        self._text = label_text
        self._keys = [k for k in (keys or []) if k]
        h = px(height)
        icon = px(21)
        cap_w = [max(px(20), self._key_font.measure(k) + px(6))
                 for k in self._keys]
        width = (px(24) + icon + px(16) + self._font.measure(label_text) +
                 (px(18) + sum(cap_w) + px(8) * max(0, len(self._keys) - 1)
                  + px(12) if self._keys else 0) + px(24))
        tk.Canvas.__init__(self, parent, width=width, height=h, bg=bg,
                           highlightthickness=0, bd=0, cursor="arrow")
        self._width, self._height = width, h
        self._icon, self._cap_w = icon, cap_w
        self._paint()
        self.bind("<Enter>", lambda _e=None: self._set("hover"))
        self.bind("<Leave>", lambda _e=None: self._set("normal"))
        self.bind("<ButtonPress-1>", lambda _e=None: self._set("active"))
        self.bind("<ButtonRelease-1>", self._release)

    def _set(self, state):
        if state != self._state:
            self._state = state
            self._paint()

    def set_keys(self, keys):
        """A new shortcut, printed on the button. Changing one in
        Settings has to show here, because here is where people read
        it."""
        keys = [k for k in (keys or []) if k]
        if keys == self._keys:
            return
        self._keys = keys
        self._cap_w = [max(px(20), self._key_font.measure(k) + px(6))
                       for k in keys]
        self._paint()

    def _release(self, _event=None):
        self._set("hover")
        if self.command:
            try:
                self.command()
            except Exception:
                pass

    def _paint(self):
        self.delete("all")
        p = self.page
        top, bottom = p["accent_hi"], p["accent"]
        if self._state == "hover":
            top, bottom = _lighten(top, 0.10), _lighten(bottom, 0.10)
        elif self._state == "active":
            top, bottom = bottom, bottom
        # A pill, not a rounded box: in the design the radius is half the
        # height and the ends are semicircles.
        self._photo = gradient(self._width, self._height, top, bottom,
                               owner=self, radius=self._height // 2)
        if self._photo is not None:
            self.create_image(0, 0, anchor="nw", image=self._photo)
        x = px(24)
        ui_icons.draw(self, "crop", x, (self._height - self._icon) / 2.0,
                      self._icon, p["on_accent"], width=2.0)
        x += self._icon + px(16)
        self.create_text(x, theme_mod.middle(self._height, self._font),
                         anchor="w",
                         text=self._text, fill=p["on_accent"],
                         font=self._font)
        x += self._font.measure(self._text)
        if not self._keys:
            return
        # One block holding all three, the way a key combination is
        # written on a Mac — not three separate caps with gaps, which
        # reads as three things to press rather than one chord.
        x += px(18)
        cap_h = px(32)
        block_w = sum(self._cap_w) + px(8) * max(0, len(self._keys) - 1) + px(12)
        self._cap_block = rounded_on(self, x, (self._height - cap_h) / 2.0,
                                     block_w, cap_h, cap_h // 2,
                                     _lighten(bottom, 0.28))
        at = x + px(6)
        for key, width in zip(self._keys, self._cap_w):
            self.create_text(at + width / 2.0,
                             theme_mod.middle(self._height, self._key_font),
                             text=key, fill=p["on_accent"],
                             font=self._key_font)
            at += width + px(8)


def _lighten(colour, amount):
    r, g, b = _rgb(colour)
    return "#%02X%02X%02X" % tuple(
        min(255, int(round(n + (255 - n) * amount))) for n in (r, g, b))


class KeyCaps(tk.Canvas):
    """The shortcut, on its own, for the tip bar."""

    def __init__(self, parent, page, keys, bg):
        self.page = page
        self._font = tkfont.Font(**_system_font_kw(parent, 13))
        self._keys = []
        self._h = px(28)
        tk.Canvas.__init__(self, parent, width=1, height=self._h, bg=bg,
                           highlightthickness=0, bd=0, takefocus=0)
        self.set_keys(keys)

    def set_keys(self, keys):
        keys = [k for k in (keys or []) if k]
        if keys == self._keys:
            return
        self._keys = keys
        self.delete("all")
        page, h = self.page, self._h
        widths = [max(px(28), self._font.measure(k) + px(14)) for k in keys]
        width = sum(widths) + px(4) * max(0, len(keys) - 1)
        self.configure(width=max(1, width))
        x = 0
        self._photos = []
        for key, w in zip(keys, widths):
            self._photos.append(
                rounded_on(self, x, 0, w, h, px(8), page["key"],
                           outline=page["key_line"]))
            self.create_text(x + w / 2.0, theme_mod.middle(h, self._font), text=key,
                             fill=page["ink_2"], font=self._font)
            x += w + px(4)


class SectionRule(tk.Frame):
    """The heading that divides the page in two.

    No rule, despite the name it kept. The drawing has the words and
    nothing else — the hairline running off to the right was mine, from
    an earlier preview, and it is the kind of addition that looks like a
    detail until you put the two side by side and the page reads as a
    form rather than as a page.
    """

    def __init__(self, parent, page, string, bg, rule=False):
        tk.Frame.__init__(self, parent, bg=bg)
        text(self, page, string, size=17, weight=700, bg=bg).pack(side="left")
        if rule:
            tk.Frame(self, bg=page["line"], height=1).pack(
                side="left", fill="x", expand=True, padx=(px(16), 0))


class Card(tk.Frame):
    """A rounded panel in the page's own colours. Children go in `.body`.

    A Frame with a Canvas behind it rather than a Canvas with widgets
    inside it — the same choice the rest of the kit makes, and for the
    same reason: children of a canvas do not take part in geometry
    management, so a card built the other way cannot grow with its
    contents.
    """

    def __init__(self, parent, page, bg, radius=18, padding=14, fill="card",
                 outline="line", least=0):
        # `least` is a floor, not a height: the frame still grows with
        # whatever space it is given. It exists so that two cards meant
        # to be read as a pair cannot end up different heights because
        # one of them happens to hold more.
        tk.Frame.__init__(self, parent, bg=bg)
        if least:
            self.configure(height=px(least))
            self.pack_propagate(False)
        self.page = page
        self._radius = px(radius)
        self._fill = page[fill]
        self._outline = page[outline]
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg=bg)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._image = plate_item(self.canvas)
        self._photo = None
        self.body = tk.Frame(self, bg=self._fill)
        self.body.pack(fill="both", expand=True, padx=px(padding),
                       pady=px(padding))
        self.bind("<Configure>", self._redraw)

    def _redraw(self, _event=None):
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        try:
            self._photo = set_plate(self.canvas, self._image, 0, 0,
                                    width, height, self._radius,
                                    self._fill, outline=self._outline)
        except Exception:
            pass


class IconButton(tk.Canvas):
    """A small square button with one drawn mark in it."""

    def __init__(self, parent, page, icon, command, bg, size=40,
                 icon_size=18):
        self.page = page
        self.command = command
        self.icon = icon
        self._hover = False
        side = px(size)
        tk.Canvas.__init__(self, parent, width=side, height=side, bg=bg,
                           highlightthickness=0, bd=0, cursor="arrow")
        self._side, self._icon_size = side, px(icon_size)
        self._paint()
        self.bind("<Enter>", lambda _e=None: self._set(True))
        self.bind("<Leave>", lambda _e=None: self._set(False))
        self.bind("<Button-1>", self._click)

    def _set(self, on):
        self._hover = on
        self._paint()

    def _click(self, _event=None):
        if self.command:
            try:
                self.command()
            except Exception:
                pass

    def _paint(self):
        self.delete("all")
        p = self.page
        ink = p["accent"] if self._hover else p["dim"]
        line = p["accent"] if self._hover else p["field_line"]
        self._photo = rounded_on(self, 0, 0, self._side, self._side,
                                 px(12), p["card"], outline=line)
        inset = (self._side - self._icon_size) / 2.0
        ui_icons.draw(self, self.icon, inset, inset, self._icon_size, ink,
                      width=1.8)


class SwapButton(tk.Canvas):
    """The circle that sits across the seam between the two cards.

    Two things make this awkward and one trick solves both. Tk has no
    transparent widget, so a canvas placed over the seam brings its own
    rectangle of background with it — and the background under it is not
    one colour but three: card, the gutter, card. The design also wants a
    ring of *card* colour round the circle, which is what makes it read
    as sitting on top of the two panels rather than as a hole punched
    through them, and a ring is only visible if what is behind it is not
    the same colour.

    So the widget paints the background it is standing on: two bands of
    card with the gutter between them, at the exact widths it covers.
    The button sits at half height, where a card's edge is straight, so
    three rectangles are not an approximation of what is behind it —
    they are what is behind it.
    """

    def __init__(self, parent, page, command, bg, size=64, ring=5, gutter=22,
                 flank="field"):
        self.page = page
        self.command = command
        self._hover = False
        side = px(size)
        tk.Canvas.__init__(self, parent, width=side, height=side, bg=bg,
                           highlightthickness=0, bd=0, cursor="arrow")
        self._side, self._ring, self._gutter = side, px(ring), px(gutter)
        # What is actually behind the button on each side. It sits at the
        # vertical middle of the pair, which is level with the two text
        # boxes rather than with the plain part of the cards — so the
        # colour to paint is the boxes', not the cards'.
        self._flank = flank
        self._paint()
        self.bind("<Enter>", lambda _e=None: self._set(True))
        self.bind("<Leave>", lambda _e=None: self._set(False))
        self.bind("<Button-1>", self._click)

    def _set(self, on):
        self._hover = on
        self._paint()

    def _click(self, _event=None):
        if self.command:
            try:
                self.command()
            except Exception:
                pass

    def _paint(self):
        self.delete("all")
        p = self.page
        side = self._side
        flank = max(0, (side - self._gutter) / 2.0)
        if flank:
            behind = p[self._flank]
            self.create_rectangle(0, 0, flank, side, fill=behind, outline="")
            self.create_rectangle(side - flank, 0, side, side, fill=behind,
                                  outline="")
        fill = p["accent"] if self._hover else p["accent_soft"]
        ink = p["on_accent"] if self._hover else p["accent"]
        self.create_oval(0, 0, side - 1, side - 1, fill=p["card"], outline="")
        r = self._ring
        self.create_oval(r, r, side - r - 1, side - r - 1, fill=fill,
                         outline="")
        size = px(26)
        inset = (side - size) / 2.0
        ui_icons.draw(self, "swap", inset, inset, size, ink, width=2.0)


class TipBar(tk.Frame):
    """The line along the bottom that says the thing worth knowing."""

    def __init__(self, parent, page, bg, keys, before, after, learn=None,
                 learn_text="Learn more"):
        card = Card(parent, page, bg, radius=15, padding=0)
        tk.Frame.__init__(self, card.body, bg=page["card"])
        self.card = card
        row = tk.Frame(card.body, bg=page["card"])
        row.pack(fill="x", padx=px(22), pady=px(16))
        bulb = tk.Canvas(row, width=px(20), height=px(20), bg=page["card"],
                         highlightthickness=0, bd=0, takefocus=0)
        bulb.pack(side="left")
        ui_icons.draw(bulb, "bulb", 0, 0, px(20), page["accent"], width=1.8)
        # The link claims its side before the sentence does. `pack` hands
        # out space in the order it is asked, so packed after a sentence
        # long enough to fill the row it is simply cut off the end — and
        # the thing cut off is the only control in the bar.
        if learn:
            LearnMore(row, page, learn_text, learn,
                      page["card"]).pack(side="right")
        self.before = text(row, page, before, size=16, colour="ink_2",
                           bg=page["card"])
        self.before.pack(side="left", padx=(px(13), 0))
        self.keys = KeyCaps(row, page, keys, page["card"])
        self.keys.pack(side="left", padx=(px(6), px(6)))
        self.after = text(row, page, after, size=16, colour="ink_2",
                          bg=page["card"])
        self.after.pack(side="left")
        # A Tk label does not shorten itself, and this row ends with the
        # only control in it. Packed left, a sentence longer than the
        # room left runs under the link and out of the card — which is
        # what a narrow window did to it. The tail of the sentence goes
        # when there is no room for it; the keys never do, because the
        # keys are the tip.
        self._row = row
        self._shown = None
        row.bind("<Configure>", self._fit)

    def _fit(self, _event=None):
        row = self._row
        width = row.winfo_width()
        if width <= 1:
            return
        spare = width
        for widget in row.winfo_children():
            if widget not in (self.before, self.after):
                spare -= widget.winfo_reqwidth() + px(12)
        keep = 2
        if self.before.winfo_reqwidth() + self.after.winfo_reqwidth() > spare:
            keep = 1
        if self.before.winfo_reqwidth() > spare:
            keep = 0
        if keep == self._shown:
            return
        self._shown = keep
        self.after.pack_forget()
        self.before.pack_forget()
        if keep >= 1:
            self.before.pack(side="left", padx=(px(13), 0), before=self.keys)
        if keep >= 2:
            self.after.pack(side="left")

    def set_keys(self, keys):
        self.keys.set_keys(keys)

    def pack(self, **kwargs):                      # the card is the widget
        self.card.pack(**kwargs)

    def pack_forget(self):
        self.card.pack_forget()


class LearnMore(tk.Canvas):
    """A word and an arrow, in the accent, with no box round it."""

    def __init__(self, parent, page, label_text, command, bg):
        self.page = page
        self.command = command
        self._font = tkfont.Font(**_font_kw(parent, 15, 600))
        arrow = px(17)
        width = self._font.measure(label_text) + px(7) + arrow
        height = px(24)
        tk.Canvas.__init__(self, parent, width=width, height=height, bg=bg,
                           highlightthickness=0, bd=0, cursor="arrow")
        self.create_text(0, theme_mod.middle(height, self._font),
                         anchor="w", text=label_text,
                         fill=page["accent"], font=self._font)
        ui_icons.draw(self, "arrow_right",
                      self._font.measure(label_text) + px(7),
                      (height - arrow) / 2.0, arrow, page["accent"],
                      width=2.0)
        self.bind("<Button-1>", lambda _e=None: command and command())


class HeroBanner(tk.Canvas):
    """The top of the page: the photograph, with the promise written on it.

    It was a picture *beside* a headline, in a column of its own, and the
    two halves of it were two different pages — words on the left, a
    photograph on the right, a seam down the middle. One band, with the
    photograph running the whole width of it and the words standing on
    it, is the design. The picture stops being an illustration of the
    app and becomes the screen the app is used on, which is the whole
    argument the page is making.

    Everything in here is a canvas item on one canvas, and it has to be.
    A label has an opaque background: a word set in a widget over a
    photograph is a word in a grey box. So the type is drawn, the marks
    are drawn, and the only real widgets are the two controls in the top
    corner, which are hosted (see `host`) and tinted to the pixels they
    stand on.

    The backdrop — the photograph, the wash that lifts the left of it
    far enough for black type to sit on it, and the line of Japanese
    being read — is composed once per size into a single image.
    Everything that moves is an item on top of it: the dashed rectangle,
    its handles, the pointer, and the card with the answer in it. That
    is why it can run at twenty-five frames a second without building a
    single bitmap per frame: nothing is redrawn, things are moved.
    """

    SOURCES = (("より良い明日をつくる",
                "Japanese"),
               ("Лучшее завтра", "Russian"),
               ("Ein besseres Morgen", "German"))
    ENGLISH = "Building a brighter tomorrow"

    #: The sky, top to bottom, straight off the design. Only used when
    #: the photograph is missing — see `PHOTO`.
    SKY = ((0.00, (239, 243, 253)), (0.34, (228, 229, 246)),
           (0.56, (233, 220, 236)), (0.72, (201, 189, 207)),
           (0.86, (169, 172, 198)), (1.00, (138, 152, 184)))

    #: The band's shape: width to height, measured off the design.
    RATIO = 0.322

    # Where everything sits, as a share of the band. Fractions rather
    # than pixels because the band is the one thing on the page whose
    # size is the window's, not the design's — the photograph inside it
    # moves with it, and type that stayed put would drift across the
    # mountain as the window changed.
    LEFT = 0.045                # the margin the words start at
    COLUMN = 0.560              # and the share of the width they get
    EYEBROW_Y = 0.255
    HEAD_Y = 0.315
    CHIP_Y = 0.885
    SOURCE_X, SOURCE_Y = 0.628, 0.515
    NOTE_X, NOTE_Y = 0.985, 0.315

    # The loop, in milliseconds: how long each part of a snip takes.
    WAIT = 900          # nothing happening
    DRAG = 820          # the rectangle being pulled out
    SETTLE = 260        # handles appear
    THINK = 420         # the pause before the answer
    HOLD = 2200         # the answer, up long enough to read
    CLEAR = 320         # and away
    TICK = 40           # 25 frames a second

    def __init__(self, parent, page, bg, eyebrow="", headline=(), blurb="",
                 chips=(), note="", ratio=None, animate=True, margin=None):
        self.page = page
        self._ratio = float(ratio or self.RATIO)
        self._bg = bg
        self._eyebrow = eyebrow
        self._headline = headline            # ((text, colour key), ...)
        self._blurb = blurb
        self._chips = chips                  # ((icon, text, colour key), ...)
        self._note = note
        #: What the words are inset by. In pixels, and the page's own
        #: margin: a fraction of the band's width is a different number
        #: from the margin everything under the band keeps, and two
        #: left edges a few pixels apart is the kind of wrong that is
        #: hard to name and impossible to unsee.
        self._margin = margin
        self._photo = None
        self._flat = None                    # the composed image, for tinting
        self._drawn = (0, 0)
        self._animate = animate
        self._job = None
        self._t = 0
        self._items = {}
        self._hosted = []
        self._pill_box = None
        self._want = None
        self._pending = None
        self._language = self.SOURCES[0][1]
        tk.Canvas.__init__(self, parent, bg=bg, highlightthickness=0, bd=0,
                           takefocus=0, height=px(300))
        self.bind("<Configure>", self._resized)
        self.bind("<Destroy>", lambda _e=None: self.stop())

    # -- size -----------------------------------------------------------
    def _wanted(self, width):
        """How tall the band should be at this width."""
        height = int(round(width * self._ratio))
        if HERO_CAP:
            height = min(height, max(px(120), HERO_CAP))
        return height

    def _resized(self, event):
        """Remember the size asked for; lay out once, when the asking
        stops.

        A rebuild of the page hands this widget four or five different
        widths on its way to the final one, and each of them was a full
        repaint: the photograph resized, the veil mixed, the Japanese
        card drawn at twice size and put down. Sixty milliseconds each,
        four of them thrown away, and all of it inside the pause in the
        middle of a theme change — which is the pause somebody watching
        sees.

        An idle callback is the right debounce here rather than a timer.
        Tk runs idle work once the events in hand are dealt with, so a
        burst of Configures collapses into one layout; and anything that
        calls `update_idletasks` — every measurement in the app, and
        every test — still gets a laid-out band immediately rather than
        having to wait out a clock.
        """
        self._want = (event.width, self._wanted(event.width))
        if SETTLING or self._pending is not None:
            return
        try:
            self._pending = self.after_idle(self.flush)
        except Exception:
            self._pending = None
            self._relayout(*self._want)

    def flush(self, force=False):
        """Lay out now, if a size is waiting to be laid out.

        `force` ignores the hold, and is how the rebuild settles up.
        """
        if SETTLING and not force:
            return
        self._pending = None
        want, self._want = self._want, None
        if want:
            self._relayout(*want)

    def recap(self):
        """Re-measure against a cap that has changed.

        The cap is a share of the window's height, and the window's
        height changes without the band's width changing at all — drag
        the bottom edge down and the band should grow with the room it
        has. Nothing else notices, because nothing else asks.
        """
        self._relayout(self._drawn[0], self._wanted(self._drawn[0]))

    def _relayout(self, width, height):
        if (width, height) == self._drawn or width < 40:
            return
        self._drawn = (width, height)
        self.configure(height=height)
        self._repaint(width, height)
        self._lay_type(width, height)
        self._build_items(width, height)
        self._place_hosted(width, height)
        if self._animate:
            self.start()

    def stop(self):
        if self._job:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def start(self):
        self.stop()
        self._t = 0
        self._job = self.after(self.TICK, self._step)

    # -- the widgets that sit on it -------------------------------------
    def host(self, widget, relx, rely, anchor="ne", dx=0, dy=0, sample=None):
        """Put a real widget on the band and keep it there.

        For the controls in the corners, which have to be clickable and
        so cannot be drawn. What they cost is a background: a canvas
        widget has one, and over a photograph a pill's four corners
        would sit in little squares of the wrong colour. So each one is
        given the average of the pixels it covers, which at the corner
        of a rounded pill is the difference between invisible and a
        smudge nobody can name but everybody sees.

        `dx`/`dy` shift it by a measured number of pixels — one control
        sitting a fixed gap from the edge of another is not a fraction
        of anything. `sample` is a box, in the same fractions, to take
        the colour from instead of from what the widget covers: for a
        label whose width is whatever it has been given to say, the
        thing it covers is the wrong question.
        """
        self._hosted.append([widget, relx, rely, anchor, None, dx, dy,
                             sample])
        if self._drawn[0]:
            self._place_hosted(*self._drawn)
        return widget

    def _place_hosted(self, w, h):
        for entry in self._hosted:
            widget, relx, rely, anchor, item, dx, dy, sample = entry
            try:
                x, y = int(w * relx) + dx, int(h * rely) + dy
                if item is None:
                    entry[4] = self.create_window(x, y, window=widget,
                                                  anchor=anchor, tags="host")
                else:
                    self.coords(item, x, y)
                self._tint(widget, x, y, anchor, sample)
            except Exception:
                continue

    def _tint(self, widget, x, y, anchor, sample=None):
        """The average colour of the band under a widget."""
        if self._flat is None:
            return
        try:
            if sample:
                w, h = self._drawn
                box = (int(w * sample[0]), int(h * sample[1]),
                       max(1, int(w * sample[2])), max(1, int(h * sample[3])))
            else:
                ww = widget.winfo_reqwidth()
                wh = widget.winfo_reqheight()
                left = x - ww if "e" in anchor else x
                top = y - wh if "s" in anchor else y
                if "w" not in anchor and "e" not in anchor:
                    left = x - ww // 2
                if "n" not in anchor and "s" not in anchor:
                    top = y - wh // 2
                box = (max(0, left), max(0, top),
                       max(1, left + ww), max(1, top + wh))
            patch = self._flat.crop(box).convert("RGB")
            how = getattr(Image, "BOX", Image.BILINEAR)
            r, g, b = patch.resize((1, 1), how).getpixel((0, 0))
            widget.configure(bg="#%02x%02x%02x" % (r, g, b))
            # And, where the widget can take it, the pixels themselves
            # rather than their average. One flat colour behind a
            # rounded pill on a gradient sky is a square you can see —
            # right in the corner the eye goes to first.
            if hasattr(widget, "backdrop"):
                ww = widget.winfo_reqwidth()
                wh = widget.winfo_reqheight()
                left = x - ww if "e" in anchor else x
                top = y - wh if "s" in anchor else y
                if "w" not in anchor and "e" not in anchor:
                    left = x - ww // 2
                if "n" not in anchor and "s" not in anchor:
                    top = y - wh // 2
                under = Image.new("RGB", (max(1, ww), max(1, wh)),
                                  (r, g, b))
                bw, bh = self._flat.size
                cx0, cy0 = max(0, left), max(0, top)
                cx1, cy1 = min(bw, left + ww), min(bh, top + wh)
                if cx1 > cx0 and cy1 > cy0:
                    under.paste(self._flat.crop((cx0, cy0, cx1, cy1)),
                                (cx0 - left, cy0 - top))
                widget._under_photo = ImageTk.PhotoImage(under, master=self)
                widget.backdrop(widget._under_photo)
        except Exception:
            pass

    # -- the type -------------------------------------------------------
    #: What the words may take of the band, top to bottom. The rest is
    #: air above and below them, and it is not decoration: this is a
    #: photograph, and type that runs to the edge of a photograph reads
    #: as type that did not fit.
    TEXT_SHARE = 0.74

    def _lay_type(self, w, h):
        """The words, drawn onto the band and measured, not placed.

        Every line here used to sit at a fraction of the band's height —
        the eyebrow at a quarter down, the claims at nine tenths — which
        is exactly right at one size and wrong at every other. The band
        is as tall as the window is wide; the type is the size the page
        is drawn at. Drag the window narrower and the band loses height
        while the words keep theirs, and the sentence ends up printed
        through the row of claims underneath it.

        So the block is built from its own measurements, from nothing,
        and if it comes out taller than the band has room for it is
        rebuilt smaller until it fits. Nothing can overlap, because
        nothing is placed anywhere it was not measured into.
        """
        self.delete("words")
        self.delete("note")
        x = self._margin if self._margin else int(w * self.LEFT)
        column = max(px(120), int(w * self.COLUMN) - x)
        room = max(px(60), int(h * self.TEXT_SHARE))

        fit = 1.0
        for _ in range(5):
            tall = self._draw_words(x, column, w, h, fit)
            if tall <= room or fit <= 0.5:
                break
            self.delete("words")
            # Two thirds of the way to what would fit, never less than a
            # tenth at a time: stepping straight to the answer overshoots
            # (a smaller face wraps the sentence in fewer lines, so the
            # block that fits is taller than the one asked for) and a
            # fixed step takes five passes to get anywhere.
            fit *= max(0.72, min(0.94, room / float(tall)))
        box = self.bbox("words")
        if box:
            # Settled a little below the middle: the claims want more air
            # under them than the eyebrow wants above it.
            self.move("words", 0, int((h - (box[3] - box[1])) * 0.54) - box[1])
        self._draw_note(w, h, fit)

    def _draw_words(self, x, column, w, h, fit):
        """The left block, from y=0 down. Returns how tall it came out."""
        p = self.page
        y = 0

        def size(design):
            return max(7, int(round(design * fit * SCALE)))

        if self._eyebrow:
            font = tkfont.Font(**_font_px(self, size(15), 700))
            self.create_text(x, y, anchor="nw", text=self._eyebrow,
                             fill=p["dim"], font=font, tags="words")
            y += font.metrics("linespace") + size(14)

        # One line, in two colours. Two create_text items side by side
        # rather than one: a Tk text item is one colour, and the line is
        # the app's name for what it does in the first half and what you
        # get in the second. Set as two lines it was a poster; the design
        # is a sentence.
        head, font = self._headline_size(column, fit)
        at = x
        space = font.measure(" ")
        for string, colour in self._headline:
            self.create_text(at, y, anchor="nw", text=string, fill=p[colour],
                             font=font, tags="words")
            at += font.measure(string) + space
        y = int(y + font.metrics("linespace") + size(10))

        if self._blurb:
            font = tkfont.Font(**_font_px(self, size(18), 400))
            item = self.create_text(x, y, anchor="nw", text=self._blurb,
                                    fill=p["ink_2"], width=column,
                                    justify="left", font=font, tags="words")
            box = self.bbox(item)
            y = box[3] + size(18)

        # The three claims, in a row, laid out left to right from their
        # own measured widths — a table of thirds puts a gap of nothing
        # after a short one and crowds the long one. They have the width
        # of the band to run into rather than the width of the column:
        # they are a single line low down, where there is nothing to
        # run into but photograph.
        if self._chips:
            font, gap = self._chip_size(w, x, fit)
            mark = size(19)
            at = x
            for icon, string, colour in self._chips:
                ui_icons.draw(self, icon, at, y, mark, p[colour], width=2.0,
                              tags="words")
                at += mark + size(9)
                self.create_text(at, y + mark / 2.0, anchor="w", text=string,
                                 fill=p["ink_2"], font=font, tags="words")
                at += font.measure(string) + gap
            y += mark
        return y

    def _draw_note(self, w, h, fit):
        """The handwritten aside. The arrow to it is drawn later, with
        the marquee, because it points at the marquee and the marquee is
        as wide as whatever line of Japanese this machine can draw."""
        self._note_box = None
        if not self._note:
            return
        p = self.page
        # Two lines in a tall band, one in a short one. The note sits
        # between the controls in the corner and the top of the snip,
        # and in a window this shape that gap is a line and a half.
        words = self._note if h >= px(210) else self._note.replace("\n", " ")
        for step in range(0, 6):
            size = max(8, int(round((19 - step * 1.5) * fit * SCALE)))
            item = self.create_text(
                int(w * self.NOTE_X), int(h * self.NOTE_Y), anchor="ne",
                text=words, fill=p["ink_2"], justify="right", tags="note",
                font=theme_mod.script_font(self, size, scale=False))
            box = self.bbox(item)
            if box[0] > w * 0.52 or size <= 8:
                break
            self.delete(item)
        self._note_box = self.bbox("note")

    def _headline_size(self, column, fit=1.0):
        """The largest size at which the whole line still fits."""
        biggest = max(14, int(round(40 * fit * SCALE)))
        for size in range(biggest, 13, -1):
            font = tkfont.Font(**_font_px(self, size, 800))
            run = sum(font.measure(string) for string, _c in self._headline)
            run += font.measure(" ") * max(0, len(self._headline) - 1)
            if run <= column:
                return size, font
        return 14, tkfont.Font(**_font_px(self, 14, 800))

    def _chip_size(self, w, x, fit):
        """A face and a gap at which the three claims fit on one line."""
        budget = max(px(100), int(w * 0.62) - x)
        for step in range(0, 8):
            size = max(7, int(round((15 - step * 0.8) * fit * SCALE)))
            font = tkfont.Font(**_font_px(self, size, 500))
            gap = max(px(8), int(round(34 * fit * SCALE)) - step * 2)
            mark = max(7, int(round(19 * fit * SCALE)))
            run = sum(font.measure(s) + mark + max(4, int(9 * fit * SCALE))
                      + gap for _i, s, _c in self._chips) - gap
            if run <= budget:
                return font, gap
        return font, gap

    # -- the moving parts -----------------------------------------------
    def _build_items(self, w, h):
        """Every item the loop moves, created once and then only moved."""
        self.delete("live")
        p = self.page
        blue = "#2F74FF"
        # The rectangle is drawn round the line of Japanese, wherever
        # that ended up: the pill is as wide as its own text, and a
        # marquee measured in fractions of the band cut through it in
        # every language but the one it was measured in.
        if self._pill_box:
            x0, y0, x1, y1 = self._pill_box
            x0 -= int(w * 0.014)
            y0 -= int(h * 0.030)
            x1 += int(w * 0.014)
            y1 += int(h * 0.030)
        else:                                          # pragma: no cover
            x0, y0 = int(w * 0.613), int(h * 0.541)
            x1, y1 = int(w * 0.809), int(h * 0.688)
        self._box = (x0, y0, x1, y1)
        # The arrow from the note to the corner of the marquee. Here
        # rather than with the note, because this is where the corner is
        # known: the marquee is drawn round the line of Japanese and the
        # line of Japanese is as wide as it is.
        self.delete("arrow")
        box = getattr(self, "_note_box", None)
        if box and box[3] < y0 - px(6):
            self.create_line(box[0] + (box[2] - box[0]) * 0.18, box[3] + px(3),
                             (box[0] + x1) / 2.0, (box[3] + y0) / 2.0,
                             x1 + px(4), y0 - px(5),
                             fill=self.page["ink_2"], width=max(2, px(2)),
                             smooth=True, arrow="last",
                             arrowshape=(px(9), px(11), px(4)), tags="arrow")
        self._items["rect"] = self.create_rectangle(
            x0, y0, x0, y0, outline=blue, width=max(1, int(h * 0.006)),
            dash=(5, 4), tags="live")
        self._items["handles"] = [
            self.create_oval(0, 0, 0, 0, fill="#FFFFFF", outline=blue,
                             width=max(1, int(h * 0.006)), state="hidden",
                             tags="live")
            for _ in range(5)]

        # The answer: a card, the way the app's own result looks — and
        # measured from what is in it rather than cut to a share of the
        # band. Set at the page's scale it was a card with a sentence
        # hanging out of both sides of it the moment the band was
        # shorter than the design's, which is every window but one.
        label = "%s → %s" % (self._language, "English")
        for step in range(0, 10):
            size = max(7, int(round(h * (0.088 - step * 0.007))))
            small = tkfont.Font(**_font_px(self, size * 0.72, 500))
            big = tkfont.Font(**_font_px(self, size, 500))
            pad = max(px(6), int(h * 0.045))
            card_w = max(small.measure(label) + int(h * 0.22),
                         big.measure(self.ENGLISH)) + pad * 2
            card_h = (small.metrics("linespace") + big.metrics("linespace")
                      + pad * 2)
            if card_w <= w * 0.30 and card_h <= h * 0.26:
                break
        self._card_at = (x0, y1 + int(h * 0.055))
        self._items["card"] = self.create_image(0, 0, anchor="nw",
                                                state="hidden", tags="live")
        self._card_photo = self._card_plate(card_w, card_h)
        self.itemconfigure(self._items["card"], image=self._card_photo)
        self._items["from"] = self.create_text(
            0, 0, anchor="w", text=label,
            fill=p["dim"], state="hidden", tags="live", font=small)
        self._items["answer"] = self.create_text(
            0, 0, anchor="w", text=self.ENGLISH, fill=p["ink"],
            state="hidden", tags="live", font=big)
        self._card_pad = pad
        self._card_lines = (small.metrics("linespace"),
                            big.metrics("linespace"))
        self._items["cursor"] = self.create_polygon(
            0, 0, 0, 0, 0, 0, 0, 0, fill="#10172A", outline="#FFFFFF",
            width=max(1, int(h * 0.005)), tags="live")
        self._cursor_size = h * 0.105
        self._card_size = (card_w, card_h)

    def _card_plate(self, w, h):
        """The card the answer arrives in, with its copy mark drawn in.

        One image rather than a rounded rectangle and a pair of canvas
        items: it appears and disappears as a unit, and hiding one thing
        is harder to get wrong than hiding three.
        """
        if Image is None:                                  # pragma: no cover
            return rounded(w, h, px(12), self.page["card"], owner=self)
        scale = 2
        img = Image.new("RGBA", (w * scale, h * scale), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([0, 0, w * scale - 1, h * scale - 1],
                               radius=px(12) * scale,
                               fill=_rgb(self.page["card"]) + (255,))
        # The copy mark: two rounded squares, one behind the other.
        mark = _rgb(self.page["faint"]) + (255,)
        size = int(h * scale * 0.20)
        right = w * scale - int(h * scale * 0.26)
        top = int(h * scale * 0.22)
        wide = max(1, int(scale * 1.4))
        draw.rounded_rectangle([right - size, top, right, top + size],
                               radius=size // 5, outline=mark, width=wide)
        draw.line([(right - size - size // 3, top + size // 4),
                   (right - size - size // 3, top + size - size // 5)],
                  fill=mark, width=wide)
        draw.line([(right - size - size // 3, top - size // 5 + size // 4),
                   (right - size // 3, top - size // 5 + size // 4)],
                  fill=mark, width=wide)
        return ImageTk.PhotoImage(
            img.resize((max(1, w), max(1, h)), Image.LANCZOS), master=self)

    def _place_cursor(self, x, y):
        s = self._cursor_size
        self.coords(self._items["cursor"],
                    x, y, x + s * 0.58, y + s * 0.40,
                    x + s * 0.32, y + s * 0.46, x + s * 0.19, y + s * 0.73)

    def _step(self):
        if not self.winfo_exists():
            return
        span = (self.WAIT + self.DRAG + self.SETTLE + self.THINK +
                self.HOLD + self.CLEAR)
        box = getattr(self, "_box", None)
        if box is None:
            # The animation can tick before the band has been laid out
            # for the first time; there is nothing to animate round yet.
            self._job = self.after(self.TICK, self._step)
            return
        self._t = (self._t + self.TICK) % span
        t = self._t
        x0, y0, x1, y1 = box
        w, h = self._drawn
        rect, handles = self._items["rect"], self._items["handles"]
        card = (self._items["card"], self._items["from"],
                self._items["answer"])
        if t < self.WAIT:                                   # nothing yet
            self.coords(rect, x0, y0, x0, y0)
            for item in handles:
                self.itemconfigure(item, state="hidden")
            for item in card:
                self.itemconfigure(item, state="hidden")
            self._place_cursor(x0 - w * 0.04, y0 - h * 0.10)
        elif t < self.WAIT + self.DRAG:                     # the drag
            f = (t - self.WAIT) / float(self.DRAG)
            f = f * f * (3 - 2 * f)                         # ease, both ends
            cx, cy = x0 + (x1 - x0) * f, y0 + (y1 - y0) * f
            self.coords(rect, x0, y0, cx, cy)
            self._place_cursor(cx, cy)
        else:
            self.coords(rect, x0, y0, x1, y1)
            self._place_cursor(x1, y1)
            r = max(2, int(h * 0.018))
            for item, (hx, hy) in zip(handles, ((x0, y0), ((x0 + x1) // 2, y0),
                                                (x1, y0), (x0, y1), (x1, y1))):
                self.coords(item, hx - r, hy - r, hx + r, hy + r)
                self.itemconfigure(item, state="normal")
            after = t - self.WAIT - self.DRAG - self.SETTLE
            if after > self.THINK:
                cx, cy = self._card_at
                pad = self._card_pad
                first, second = self._card_lines
                self.coords(self._items["card"], cx, cy)
                self.coords(self._items["from"], cx + pad,
                            cy + pad + first / 2.0)
                self.coords(self._items["answer"], cx + pad,
                            cy + pad + first + second / 2.0)
                for item in card:
                    self.itemconfigure(item, state="normal")
        self._job = self.after(self.TICK, self._step)

    # -- the backdrop ---------------------------------------------------
    #: Where a face with kana and kanji in it lives, machine by machine.
    #: These are asked before the app's own font finder, and the reason
    #: is a mountain: the picture is of Fuji, the line in it should be
    #: Japanese, and it was coming out in Russian — the second sample —
    #: on a Mac that has four Japanese faces installed. The finder has
    #: to answer for every script the app can translate into and settles
    #: for a file that exists; here there is one script and it is worth
    #: naming the files. On macOS they are named in Japanese, which is
    #: why no list of ASCII file names was ever going to find them.
    JAPANESE_FILES = (
        "/System/Library/Fonts/\u30d2\u30e9\u30ae\u30ce\u89d2\u30b4"
        "\u30b7\u30c3\u30af W3.ttc",
        "/System/Library/Fonts/\u30d2\u30e9\u30ae\u30ce\u89d2\u30b4"
        "\u30b7\u30c3\u30af W4.ttc",
        "/System/Library/Fonts/\u30d2\u30e9\u30ae\u30ce\u89d2\u30b4"
        "\u30b7\u30c3\u30af W6.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "C:\\Windows\\Fonts\\YuGothM.ttc",
        "C:\\Windows\\Fonts\\YuGothR.ttc",
        "C:\\Windows\\Fonts\\meiryo.ttc",
        "C:\\Windows\\Fonts\\msgothic.ttc",
        "C:\\Windows\\Fonts\\msmincho.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    )

    def _source_text(self):
        """The first sample this machine can actually draw.

        Asked of the face itself, not of the font finder, which will
        hand back a file for Japanese with no Japanese in it. A face
        with no glyph does not fail; it draws a box, and a row of boxes
        is the one thing this picture must never show.

        Collections are asked face by face as well. A .ttc holds several
        weights, PIL opens the first of them, and on more than one
        machine the first is not the one with the kanji — so a file that
        would have done was rejected for the contents of one of its
        faces. Cached for the process: this is four or five files opened
        and a dozen glyphs drawn, and the answer cannot change while the
        app is running.
        """
        global _sample_face
        if _sample_face is not None:
            return _sample_face
        if Image is None:                                  # pragma: no cover
            return self.SOURCES[-1][0], None, 0, self.SOURCES[-1][1]
        for string, language in self.SOURCES:
            for path in self._font_files(language):
                for index in range(0, 4):
                    if _can_draw(path, string, index):
                        _sample_face = (string, path, index, language)
                        return _sample_face
        _sample_face = (self.SOURCES[-1][0], None, 0, self.SOURCES[-1][1])
        return _sample_face

    def _font_files(self, language):
        """Files to try for this sample, the named ones first."""
        paths = []
        if language == "Japanese":
            paths.extend(self.JAPANESE_FILES)
        try:
            from . import overlay
            found = overlay._find_font_file(
                overlay._font_family_for(language))
            if found:
                paths.append(found)
        except Exception:                                  # pragma: no cover
            pass
        import os
        return [path for path in paths if os.path.isfile(path)]

    @staticmethod
    def _face(path, size, index=0):
        from PIL import ImageFont
        if path:
            try:
                return ImageFont.truetype(path, size, index=index)
            except Exception:
                pass
        try:
            import os
            from . import config as _config
            here = os.path.join(_config.app_dir(), "assets", "fonts",
                                "plus-jakarta-sans-600.ttf")
            return ImageFont.truetype(here, size)
        except Exception:
            return ImageFont.load_default()

    #: The photograph behind it all, if one shipped. A drawing of a
    #: mountain is a drawing of a mountain however carefully it is
    #: shaded; this is the one part of the picture that wants to be real.
    #: Absent, everything below still draws and the page still works —
    #: which is why the drawn version is kept rather than deleted.
    PHOTO = "hero.jpg"
    #: Nothing comes off the right any more. The shipped photograph is
    #: cropped to the band's own shape, with the peak already sitting
    #: where the design has it — a little right of centre, clear of the
    #: headline. Composing the picture in the file rather than in the
    #: code means the code only ever reduces it, which is the one
    #: resampling that costs nothing.
    OFF_RIGHT = 0.0

    def _photo_plate(self, w, h):
        """The photograph, cropped to fill and never stretched."""
        import os
        key = (self.PHOTO, w, h, self.OFF_RIGHT)
        if key in _plates:
            return _plates[key].copy()
        try:
            from . import config as _config
            for base in (_config.resource_dir(), _config.app_dir()):
                path = os.path.join(base, "assets", self.PHOTO)
                if os.path.isfile(path):
                    break
            else:
                return None
            plate = Image.open(path).convert("RGB")
        except Exception:
            return None
        if self.OFF_RIGHT:
            plate = plate.crop((0, 0,
                                int(plate.width * (1.0 - self.OFF_RIGHT)),
                                plate.height))
        # Cover, not fit: match the wider ratio and take the part of the
        # other axis the picture is actually of — the sky above the peak
        # and the water under it, not a band across the middle.
        want = w / float(h)
        have = plate.width / float(plate.height)
        if have > want:
            keep = int(round(plate.height * want))
            left = (plate.width - keep) // 2
            plate = plate.crop((left, 0, left + keep, plate.height))
        else:
            keep = int(round(plate.width / want))
            top = int((plate.height - keep) * 0.5)
            plate = plate.crop((0, top, plate.width, top + keep))
        plate = plate.resize((w, h), Image.LANCZOS)
        # The photograph is a dusk shot and the band is a light surface
        # with black type on it. Veiling a dark picture until type will
        # sit on it turns the mountain grey; lifting the picture first
        # and veiling it less leaves a mountain. The numbers are small
        # on purpose — this is exposure, not a filter.
        #
        # And no sharpening. It had some, at both ends: the shipped file
        # was sharpened when it was made and the band was sharpened again
        # when it was drawn. A photograph enlarged past its own
        # resolution and then sharpened twice does not come out sharp,
        # it comes out crunchy — hard stair-steps along every ridge,
        # which is exactly what "pixellated" looks like. Soft is what an
        # enlargement honestly is, and soft behind a veil reads as
        # distance. The file ships lossless now for the same reason:
        # there are no compression blocks to magnify.
        # No lift either. The picture that shipped before this was a dusk
        # shot, nearly black, and had to be opened up before type would
        # sit on it; this one is a morning and needs nothing.
        try:
            from PIL import ImageEnhance
            plate = ImageEnhance.Color(plate).enhance(1.03)
        except Exception:                                  # pragma: no cover
            pass
        if len(_plates) > 3:
            _plates.clear()
        _plates[key] = plate
        return plate.copy()

    def _repaint(self, width, height):
        """Compose the band, once per size.

        At its own size, not at twice it. Drawing everything twice as
        big and shrinking it once is the usual way to get smooth edges,
        and for a photograph it is the wrong trade: the picture is
        already smaller than the band, so that route enlarges it by more
        than two, then halves it again, and what comes back has been
        resampled twice for the sake of the corners of one rounded
        rectangle. The photograph is resized exactly once now, straight
        to the size it will be drawn at, and the one thing that wanted
        the extra resolution — the card with the Japanese in it — is
        drawn big in a patch of its own and put down small.
        """
        if Image is None:                                  # pragma: no cover
            return
        self.delete("back")
        w, h = width, height
        plate = self._photo_plate(w, h)
        self.on_photo = plate is not None
        if plate is not None:
            img = plate
            draw = ImageDraw.Draw(img, "RGBA")
        else:
            img = Image.new("RGB", (w, h))
            draw = ImageDraw.Draw(img, "RGBA")
            self._sky(img, w, h)
            self._mountain(img, w, h)
            self._haze(draw, w, h)
        self._wash(img, w, h)
        string, path, index, language = self._source_text()
        self._language = language
        self._pill_box = self._source(img, draw, w, h, string, path, index)
        self._flat = img.convert("RGB")
        self._photo = ImageTk.PhotoImage(self._flat, master=self)
        self.create_image(0, 0, anchor="nw", image=self._photo, tags="back")
        self.tag_lower("back")

    #: The veil, as three numbers: how much of it there is over the
    #: words, how much is left by the time it reaches the mountain, and
    #: how much more of it there is at the top, where the note and the
    #: two controls are. The last two differ by scheme, and not by a
    #: little: the same veil that leaves a bright photograph bright on a
    #: white page leaves it glowing on a dark one.
    HEAVY = 234
    LIGHT_BY_SCHEME = {"light": 58, "dark": 132}
    LIFT_BY_SCHEME = {"light": 30, "dark": 76}

    def _wash(self, img, w, h):
        """What makes a photograph something you can write on.

        A single flat veil over the whole picture is how this reads as a
        stock header with the contrast turned down. The point is that
        the left of the band is a surface and the right of it is a
        photograph, with nothing in between that the eye can find as an
        edge — so the veil is the page's own background colour, heavy
        where the words are, thin by the time it reaches the mountain,
        and thicker again towards the top whatever the column.

        Built as a small mask and enlarged rather than drawn a column at
        a time: the same picture, and it is not two million calls into
        PIL every time the window is resized.
        """
        small = 256
        light = self.LIGHT_BY_SCHEME.get(self.page["name"], 58)
        lift = self.LIFT_BY_SCHEME.get(self.page["name"], 30)
        mask = Image.new("L", (small, small))
        pixels = mask.load()
        start, end = 0.28, 0.72
        columns = []
        for i in range(small):
            f = i / float(small - 1)
            if f <= start:
                base = self.HEAVY
            elif f >= end:
                base = light
            else:
                g = (f - start) / (end - start)
                g = g * g * (3 - 2 * g)
                base = self.HEAVY + (light - self.HEAVY) * g
            columns.append(base)
        for j in range(small):
            f = j / float(small - 1)
            top = lift * max(0.0, 1.0 - f / 0.55) ** 1.3
            for i in range(small):
                pixels[i, j] = int(min(255, columns[i] + top))
        veil = Image.new("RGB", (w, h), _rgb(self.page["bg_a"]))
        img.paste(veil, (0, 0), mask.resize((w, h), Image.BILINEAR))

    def _sky(self, img, w, h):
        strip = Image.new("RGB", (1, 256))
        pixels = strip.load()
        stops = self.SKY
        for y in range(256):
            f = y / 255.0
            for n in range(len(stops) - 1):
                a, b = stops[n], stops[n + 1]
                if a[0] <= f <= b[0]:
                    g = (f - a[0]) / max(1e-6, b[0] - a[0])
                    pixels[0, y] = tuple(
                        int(round(a[1][i] + (b[1][i] - a[1][i]) * g))
                        for i in range(3))
                    break
        img.paste(strip.resize((w, h), Image.BILINEAR), (0, 0))

    def _mountain(self, img, w, h):
        """One peak, shaded by a wash rather than by two flat halves.

        Two polygons meeting at the ridge is how this was drawn first,
        and the join is a dead straight line down the middle of the
        mountain — which is the single thing that made the whole picture
        read as clip art. A mountain has no hard edge down its face. So
        the silhouette is one shape, and the light across it is a
        gradient painted through that shape as a mask.
        """
        apex_x = int(w * 0.60)
        top = int(h * 0.22)
        base = int(h * 0.88)
        span = int(w * 0.62)
        left, right = apex_x - span // 2, apex_x + span // 2

        def flank(x_end):
            points = []
            steps = 22
            for n in range(steps + 1):
                f = n / float(steps)
                # The skirt flares as it falls: a volcano, not a wedge.
                points.append((apex_x + (x_end - apex_x) * (f ** 1.42),
                               top + (base - top) * f))
            return points

        shape = flank(left)[::-1] + flank(right)
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).polygon(shape, fill=255)

        # The wash: darker on the shaded left, lighter where the sun is,
        # and paler again at the foot where the haze sits.
        wash = Image.new("RGB", (w, h))
        pixels = wash.load()
        for x in range(w):
            f = min(1.0, max(0.0, (x - left) / float(max(1, right - left))))
            base_rgb = tuple(int(round(a + (b - a) * (f ** 0.85)))
                             for a, b in zip((96, 108, 144), (150, 160, 190)))
            for y in range(top, h):
                g = (y - top) / float(max(1, h - top))
                pixels[x, y] = tuple(
                    int(round(c + (196 - c) * (g ** 2.2) * 0.55))
                    for c in base_rgb)
        img.paste(wash, (0, 0), mask)

        # Snow, following the gullies rather than sitting on top.
        cap = (base - top) * 0.22
        snow = ImageDraw.Draw(img, "RGBA")
        snow.polygon([(apex_x, top + cap * 0.04),
                      (apex_x + span * 0.052, top + cap * 0.72),
                      (apex_x + span * 0.030, top + cap * 0.54),
                      (apex_x + span * 0.014, top + cap * 0.92),
                      (apex_x - span * 0.002, top + cap * 0.62),
                      (apex_x - span * 0.020, top + cap * 0.98),
                      (apex_x - span * 0.036, top + cap * 0.58),
                      (apex_x - span * 0.056, top + cap * 0.76)],
                     fill=(248, 240, 236, 245))

    @staticmethod
    def _haze(draw, w, h):
        """The band of light the peak stands in. Drawn as many lines of
        falling alpha — one rectangle has an edge, and an edge across the
        foot of a mountain reads as a mistake."""
        band = max(2, int(h * 0.34))
        for n in range(band):
            f = n / float(band)
            draw.line([(0, h - band + n), (w, h - band + n)],
                      fill=(206, 206, 226, int(130 * (1.0 - f) ** 1.5)))

    def _source(self, img, draw, w, h, string, path, index):
        """The line being read, in a card on the picture.

        Drawn into a patch of its own at four times the area and put
        down at size, because the imaging library draws a rounded corner
        with no smoothing at all and a card with stepped corners is the
        first thing the eye finds on a photograph.

        Returns where it ended up, in the band's own coordinates, so the
        marquee drawn round it can be drawn round *it* rather than round
        where a line of Japanese was once measured to be.
        """
        x0, y0 = int(w * self.SOURCE_X), int(h * self.SOURCE_Y)
        size = max(9, int(h * 0.115))
        pad_x, pad_y = int(w * 0.013), int(h * 0.030)

        def measure(face):
            try:
                box = draw.textbbox((0, 0), string, font=face)
                return box[2] - box[0], box[3] - box[1]
            except Exception:                              # pragma: no cover
                return size * len(string), size

        face = self._face(path, size, index)
        text_w, text_h = measure(face)
        # A line of Japanese, a line of Russian and a line of German are
        # three different lengths, and the card is as wide as whichever
        # one this machine can draw. Sized to the design's width instead
        # of to the design's type: the card is what the picture is of,
        # and a card running off the edge of the band is not a card.
        want = int(w * 0.215)
        if text_w > want:
            size = max(9, int(size * want / float(text_w)))
            face = self._face(path, size, index)
            text_w, text_h = measure(face)
        card_w = text_w + pad_x * 2
        card_h = text_h + pad_y * 2
        # A card that would run off the edge is one the band is too
        # narrow for, not one the design got wrong: pull it back in.
        if x0 + card_w > w - int(w * 0.03):
            x0 = w - int(w * 0.03) - card_w

        over = 2
        patch = Image.new("RGBA", (card_w * over, card_h * over), (0, 0, 0, 0))
        pen = ImageDraw.Draw(patch)
        pen.rounded_rectangle([0, 0, card_w * over - 1, card_h * over - 1],
                              radius=int(h * 0.030) * over,
                              fill=_rgb(self.page["card"]) + (255,))
        big = self._face(path, size * over, index)
        try:
            box = pen.textbbox((0, 0), string, font=big)
            pen.text((pad_x * over - box[0], pad_y * over - box[1]), string,
                     font=big, fill=_rgb(self.page["ink"]))
        except Exception:                                  # pragma: no cover
            pen.text((pad_x * over, pad_y * over), string, font=big,
                     fill=_rgb(self.page["ink"]))
        patch = patch.resize((card_w, card_h), Image.LANCZOS)
        img.paste(patch, (x0, y0), patch)
        return (x0, y0, x0 + card_w, y0 + card_h)


def _dashed(draw, x0, y0, x1, y1, colour, width, dash=9, gap=6):
    """A dashed rectangle. PIL draws solid lines and nothing else."""
    def run(ax, ay, bx, by):
        span = max(abs(bx - ax), abs(by - ay))
        if not span:
            return
        step = dash + gap
        n = 0
        while n < span:
            f0, f1 = n / span, min(1.0, (n + dash) / span)
            draw.line([(ax + (bx - ax) * f0, ay + (by - ay) * f0),
                       (ax + (bx - ax) * f1, ay + (by - ay) * f1)],
                      fill=colour, width=width)
            n += step
    run(x0, y0, x1, y0)
    run(x1, y0, x1, y1)
    run(x1, y1, x0, y1)
    run(x0, y1, x0, y0)


class DonateButton(tk.Canvas):
    """The one button on the page that asks for something.

    Blue with a white heart, because that is what was asked for, and
    because the previous one — a ghost pill the weight of the copyright
    line beside it — was so quiet that nobody ever found out the app had
    a tip jar. It is still the only thing of its kind in the window.
    """

    def __init__(self, parent, page, label_text, command, bg, height=46):
        self.page = page
        self.command = command
        self._state = "normal"
        self._font = tkfont.Font(**_font_kw(parent, 15, 600))
        self._text = label_text
        h = px(height)
        icon = px(19)
        width = px(20) + icon + px(10) + self._font.measure(label_text) + px(22)
        tk.Canvas.__init__(self, parent, width=width, height=h, bg=bg,
                           highlightthickness=0, bd=0, cursor="arrow")
        self._width, self._height, self._icon = width, h, icon
        self._paint()
        self.bind("<Enter>", lambda _e=None: self._set("hover"))
        self.bind("<Leave>", lambda _e=None: self._set("normal"))
        self.bind("<ButtonPress-1>", lambda _e=None: self._set("active"))
        self.bind("<ButtonRelease-1>", self._release)

    def _set(self, state):
        if state != self._state:
            self._state = state
            self._paint()

    def _release(self, _event=None):
        self._set("hover")
        if self.command:
            try:
                self.command()
            except Exception:
                pass

    def _paint(self):
        self.delete("all")
        p = self.page
        fill = p["accent"]
        if self._state == "hover":
            fill = p["accent_hi"]
        elif self._state == "active":
            fill = _lighten(p["accent"], -0.0)
        self._photo = rounded_on(self, 0, 0, self._width, self._height,
                                 self._height // 2, fill)
        ui_icons.draw(self, "heart", px(20),
                      (self._height - self._icon) / 2.0, self._icon,
                      p["on_accent"], width=2.0)
        self.create_text(px(20) + self._icon + px(10),
                         theme_mod.middle(self._height, self._font),
                         anchor="w", text=self._text,
                         fill=p["on_accent"], font=self._font)


def _can_draw(path, string, index=0):
    """Whether this font file has a glyph for every character.

    Compared against what the same face draws for a noncharacter, which
    no font anywhere has: if a letter comes out identical to that, it is
    the missing-glyph box and not the letter.

    `index` picks a face out of a collection. A .ttc is several fonts in
    one file and they do not all have the same coverage.
    """
    if Image is None:                                      # pragma: no cover
        return False
    try:
        from PIL import ImageFont
        face = ImageFont.truetype(path, 28, index=index)
    except Exception:
        return False

    def drawn(ch):
        sheet = Image.new("L", (44, 44), 0)
        ImageDraw.Draw(sheet).text((4, 4), ch, font=face, fill=255)
        return sheet.tobytes()

    try:
        missing = drawn("\uFFFF")
        return all(drawn(ch) != missing
                   for ch in string if not ch.isspace())
    except Exception:
        return False


class CloseButton(tk.Canvas):
    """A small round cross. Takes back whatever has just been put in.

    Quiet until pointed at, because it sits beside the thing you normally
    want and is the thing you normally do not — but always present, never
    only on hover: an affordance that appears only once the pointer finds
    it is one you have to already know about.
    """

    SIDE = 30

    def __init__(self, parent, page, command, bg, side=None):
        self.page = page
        self.command = command
        self._hover = False
        self._side = px(side or self.SIDE)
        tk.Canvas.__init__(self, parent, width=self._side, height=self._side,
                           bg=bg, highlightthickness=0, bd=0, takefocus=0,
                           cursor="hand2")
        self._plate = None
        self._paint()
        self.bind("<Enter>", lambda _e=None: self._set(True))
        self.bind("<Leave>", lambda _e=None: self._set(False))
        self.bind("<Button-1>", self._click)

    def _set(self, on):
        if on != self._hover:
            self._hover = on
            self._paint()

    def _click(self, _event=None):
        if self.command:
            self.command()

    def _paint(self):
        self.delete("face")
        side = self._side
        if self._hover:
            self._plate = rounded_on(self, 0, 0, side, side, side // 2,
                                     self.page["field_line"], tags=("face",))
        else:
            self._plate = None
        mark = int(side * 0.58)
        ui_icons.draw(self, "close", (side - mark) / 2.0, (side - mark) / 2.0,
                      mark, self.page["ink" if self._hover else "faint"],
                      width=2.0, tags=("face",))


class ProgressPill(tk.Canvas):
    """A pill that fills as the work is done and is the button at the end.

    Progress used to be a hairline above the fold with the sentence under
    it and, when it finished, a button at the far end of a different row.
    Three places for one thing, and the one you had to act on was the
    easiest of the three to miss — a file could finish translating and sit
    there unsaved because nothing where you were looking had changed.

    So it is one object in one place: the place the file went in. It fills
    left to right while there is work, and when the work is done the same
    shape says what to do with the result and does it when clicked. There
    is nothing to notice, because the thing you were already watching is
    the thing that becomes the button.

    While it is filling it carries no words. That is not an omission: a
    label inside a bar that is half filled is half on the blue and half
    on the pale, and there is no one colour that reads on both. Dark
    disappears into the blue, light disappears into the pale, and
    switching at the halfway mark puts the change exactly where the words
    are. The canvas cannot clip text, so it cannot be two colours at
    once. So while there is progress to show, the bar shows progress and
    the words sit under it on the card, where they are legible from the
    first per cent to the last. Once it is finished the fill is the whole
    pill, there is only one ground left, and the label goes back inside
    it — which is also the moment the label is worth reading, because it
    is now the thing to click.
    """

    #: How tall, before the display's scale is applied.
    HEIGHT = 46

    #: How far up the bar is drawn before it is reduced. The bar is small
    #: — a few hundred pixels by forty — so supersampling the whole of it
    #: costs a few milliseconds and buys a curve that is a curve.
    OVER = 4

    #: Fill widths are rounded to this many pixels, so that a bar filling
    #: across six hundred pixels draws a picture a hundred and fifty
    #: times rather than six hundred.
    STEP = 4

    def __init__(self, parent, page, bg, height=None):
        self.page = page
        self._bg = bg
        self._height = px(height or self.HEIGHT)
        # A width of its own. A canvas with none defaults to 378 pixels,
        # which is what it falls back to the moment anything stops it
        # being stretched to fit — and a bar suddenly 378 wide in a box
        # narrower than that hangs out of the box.
        tk.Canvas.__init__(self, parent, width=px(120), height=self._height,
                           bg=bg, highlightthickness=0, bd=0, takefocus=0)
        # One item, one picture: the track and the fill are drawn together
        # rather than stacked as two plates.
        #
        # They were two, through the shared plate machinery every other
        # rounded shape in the app uses, and the bar came back with
        # corners cut off at an angle instead of rounded — on one machine,
        # not reproducible here, and not explicable from that code, whose
        # output measured as a true half-circle every time it was asked
        # for one. A shape this small and this specific does not need to
        # share machinery with the cards and the keycaps. It draws itself,
        # and a test measures what it drew against a real circle, so
        # "it is a pill" is a number rather than an opinion.
        self._bar = self.create_image(0, 0, anchor="nw")
        self._photo = None
        self._drawn = None
        self._value = 0.0
        self._label = ""
        self._icon = None
        self._state = "busy"          # busy | done | failed
        self._command = None
        self._hover = False
        self._font = tkfont.Font(**_font_kw(parent, 14, 600))
        self.bind("<Configure>", lambda _e=None: self._paint())
        self._paint()

    # -- what it is doing ------------------------------------------------
    def working(self, fraction):
        self._state = "busy"
        self._command = None
        self._icon = None
        self._label = ""
        self._value = max(0.0, min(1.0, float(fraction)))
        self._cursor("arrow")
        self._paint()

    def done(self):
        """Full, and still a bar. What to do next is a button of its own
        under the box — see MainWindow's download row."""
        self._state = "done"
        self._value = 1.0
        self._label = ""
        self._icon = None
        self._command = None
        self._cursor("arrow")
        self._paint()

    def failed(self, label):
        self._state = "failed"
        self._value = 0.0
        self._label = label
        self._icon = None
        self._command = None
        self._cursor("arrow")
        self._paint()

    def value(self):
        return self._value

    def set_height(self, height):
        """Make the bar shorter, when the box it is in is short.

        Clipped it looks broken: a pill with its top and bottom sliced
        off is not a shorter pill, it is a rectangle with two stubs. A
        bar that is genuinely shorter is just a thinner bar.
        """
        # A floor. Below about this a bar stops reading as a bar at
        # all, and a box too short for one is better with a little of it
        # cut off than with a blue hairline in it.
        height = max(px(22), int(height))
        if height == self._height:
            return
        self._height = height
        self._drawn = None
        try:
            self.configure(height=height)
        except Exception:
            pass
        self._paint()

    def _round_to(self, pixels):
        return int(round(pixels / float(self.STEP))) * self.STEP

    def _fill_width(self):
        """How wide the fill is drawn, in pixels. Nought when hidden.

        Never shorter than the bar is tall. A fill a few pixels across and
        the full height of the bar is a slab whatever radius it is given,
        so the shortest it is allowed to be is a circle.
        """
        width = max(1, self.winfo_width())
        filled = int(round(width * self._value))
        if filled <= 0:
            return 0
        return max(self._height, min(width, self._round_to(filled)))

    # -- behaviour -------------------------------------------------------
    def _cursor(self, shape):
        try:
            self.configure(cursor=shape)
        except Exception:
            pass

    def _click(self, _event=None):
        """Nothing. The bar reports; it is not a control."""

    def _colours(self):
        """Track, fill and the two label colours, by state."""
        p = self.page
        if self._state == "failed":
            return p["field_line"], None, p["dim"], p["dim"]
        return p["accent_soft"], p["accent"], p["dim"], p["on_accent"]

    # -- drawing ---------------------------------------------------------
    @staticmethod
    def bar_image(width, height, filled, track, fill, over=4):
        """The whole bar as one picture: a pill, and a pill inside it.

        Drawn `over` times up and reduced, which is what makes the ends
        semicircles rather than a polygon's idea of one. Both shapes use
        the same radius — half the height — so the fill is the same shape
        as the thing it is filling, at every width it passes through.
        """
        from PIL import Image, ImageDraw
        width = max(1, int(width))
        height = max(1, int(height))
        big = (width * over, height * over)
        img = Image.new("RGBA", big, (0, 0, 0, 0))
        pen = ImageDraw.Draw(img)
        radius = height * over / 2.0
        pen.rounded_rectangle([0, 0, big[0] - 1, big[1] - 1],
                              radius=radius,
                              fill=ui_icons._rgba(track))
        filled = int(filled)
        if fill and filled > 0:
            # Never narrower than it is tall: below that a rounded
            # rectangle is a slab with its corners nibbled, whatever
            # radius it is asked for.
            filled = max(height, min(width, filled)) * over
            pen.rounded_rectangle([0, 0, filled - 1, big[1] - 1],
                                  radius=radius, fill=ui_icons._rgba(fill))
        return img.resize((width, height), Image.LANCZOS)

    def _paint(self):
        width = max(1, self.winfo_width())
        height = self._height
        if width < 8:
            return
        track, fill, off_ink, on_ink = self._colours()
        filled = self._fill_width()

        want = (width, height, filled, track, fill)
        if want != self._drawn:
            try:
                from PIL import ImageTk
                picture = self.bar_image(width, height, filled, track, fill,
                                         self.OVER)
                # Held, not just handed to the canvas. A PhotoImage with
                # nothing referring to it is collected while it is still
                # on screen, and what is left is an item pointing at an
                # image that no longer exists.
                self._photo = ImageTk.PhotoImage(picture, master=self)
                self.itemconfigure(self._bar, image=self._photo)
                self._drawn = want
            except Exception:
                return

        self.delete("pill_face")
        ink = on_ink if self._value >= 0.5 else off_ink
        label = self._label or ""
        if not label:
            return
        gap = px(10)
        mark = px(20) if self._icon else 0
        span = self._font.measure(label) + (mark + gap if mark else 0)
        left = (width - span) / 2.0
        if mark:
            ui_icons.draw(self, self._icon, left, (height - mark) / 2.0,
                          mark, ink, width=1.8, tags=("pill_face",))
            left += mark + gap
        self.create_text(left, height / 2.0, text=label, fill=ink,
                         font=self._font, anchor="w", tags=("pill_face",))


class DropZone(tk.Frame):
    """Where a file goes, inside the box you would otherwise type in.

    Typing and dropping a file are the same intent — "translate this" —
    so they are the same box. A separate Open file button beside it made
    you classify what you were about to do before you did it, and put a
    control in the page's furniture for something that belongs in the
    thing itself.

    It steps aside the moment there is text: an empty box offers both
    ways in, a box with something in it is a box with something in it.
    """

    #: It has to be tall enough to hold what is in it. Packed to expand
    #: it gets whatever is left after the caret, and on a short window
    #: that is a dashed line with nothing visible inside it.
    def __init__(self, parent, page, on_open, bg, kinds="", on_cancel=None):
        tk.Frame.__init__(self, parent, bg=bg)
        self.page = page
        self._bg = bg
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg=bg)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.body = tk.Frame(self, bg=bg)
        self.body.pack(fill="both", expand=True, padx=px(14), pady=px(12))
        inner = tk.Frame(self.body, bg=bg)
        inner.place(relx=0.5, rely=0.5, anchor="center")

        mark = tk.Canvas(inner, width=px(26), height=px(26), bg=bg,
                         highlightthickness=0, bd=0, takefocus=0)
        ui_icons.draw(mark, "upload", 0, 0, px(26), page["dim"], width=1.7)
        label = text(inner, page, "Drag & drop an image, or click to upload",
                     size=14, colour="dim", bg=bg)
        self.invite_label = label
        button = GhostButton(inner, page, "Open file…", on_open, bg)
        extra = None
        if kinds:
            extra = text(inner, page, kinds, size=12, colour="faint", bg=bg)

        # In order, and each with the gap that goes above it. The box is
        # given whatever is left of the field, which on a small window is
        # less than all of this; rather than centre it and let the ends
        # fall outside, the least important row is dropped until what is
        # left fits. A button half cut off is worse than no icon.
        self._inner = inner
        self._rows = [(mark, 0), (label, px(11)), (button, px(11))]
        if extra is not None:
            self._rows.append((extra, px(10)))
        #: Which row goes first when there is not room for all of them,
        #: then the next. The sentence is never dropped: the whole box
        #: is a button, and the sentence is the only thing that says so.
        #: The pill goes before it for the same reason — a lone pill in
        #: a dashed box is the separate Open file button this replaced.
        self._order = [0, 3, 2] if extra is not None else [0, 2]
        self._shown = None
        #: Small, rather than gone, once there is text in the box above.
        #: It used to be unpacked entirely — and since the whole box is
        #: the only way to open a file, typing a word removed every way
        #: of opening one. Out of the way is not the same as taken away.
        self._compact = False
        self._can_drop = True
        self._fit()

        self._over = False
        self._invite = [self, self.canvas, self.body, inner, mark, label,
                        extra]
        for widget in self._invite:
            if widget is None:
                continue
            # Not while there is a file in it. The whole box is a click
            # target, and a chooser opening over a translation in progress
            # is the one click nobody means to make.
            widget.bind("<Button-1>",
                        lambda _e=None: (on_open and not self._working
                                         and on_open()))
        self.bind("<Configure>", self._redraw)

        # -- what it becomes once there is a file in it -----------------
        #
        # Not a second panel somewhere else on the page. The file was put
        # here, so this is where it is reported on and this is where the
        # result is collected; see ProgressPill for why that matters.
        self._busy = tk.Frame(self.body, bg=bg)
        self.name_label = text(self._busy, page, "", size=13, colour="dim",
                               bg=bg)
        # The bar and the way out share a row, so that the way out cannot
        # be dropped while the bar is still there. Put beside the file's
        # name it would go with the name on a short box — and a file put
        # in by accident on a short box is exactly when you want it back.
        self._bar_row = tk.Frame(self._busy, bg=bg)
        self.pill = ProgressPill(self._bar_row, page, bg)
        self.pill.pack(side="left", fill="x", expand=True)
        self.close_button = CloseButton(self._bar_row, page,
                                        on_cancel or self.reset, bg)
        self.close_button.pack(side="left", padx=(px(8), 0))
        self.note_label = text(self._busy, page, "", size=13, colour="dim",
                               bg=bg)
        # Same rule as the invitation above: on a short window say less
        # rather than saying it half off the edge. The bar's row is never
        # dropped — it is the only row that can be acted on.
        self._busy_rows = [(self.name_label, 0), (self._bar_row, px(10)),
                           (self.note_label, px(9))]
        self._busy_order = [0, 2]
        self._busy_shown = None
        self._working = False

    # -- the file that is in it ------------------------------------------
    def begin(self, name, label="Reading…"):
        """A file has arrived. Stop inviting and start reporting."""
        self._working = True
        self._inner.place_forget()
        self._busy.place(relx=0.5, rely=0.5, anchor="center",
                         relwidth=0.92)
        self._busy_shown = None
        self._fit_busy()
        self.name_label.configure(text=name)
        self.note_label.configure(text=label)
        self.pill.working(0.0)
        self._redraw()

    def _ensure_busy(self):
        """Report even if nobody said a file had arrived.

        `begin` is how this normally starts, and every one of these could
        simply do nothing without it — which is exactly what went wrong
        once: a translation finished, the box had not been told a file was
        coming, and the result was dropped on the floor with no button to
        collect it and nothing on screen to say so. Reporting a result is
        never the wrong thing to do.
        """
        if not self._working:
            self.begin("", label="")

    def step(self, fraction, label="", note=""):
        self._ensure_busy()
        self.pill.working(fraction)
        words = note or label
        if words:
            self.note_label.configure(text=words)

    def finished(self, note=""):
        """The work is done. The bar says so; the button below says what
        to do about it."""
        self._ensure_busy()
        self.pill.done()
        self.note_label.configure(text=note)

    def failed(self, message):
        self._ensure_busy()
        self.pill.failed(message)
        self.note_label.configure(text="")

    def reset(self):
        """Back to an empty box asking for a file."""
        self._working = False
        self._busy.place_forget()
        self._inner.place(relx=0.5, rely=0.5, anchor="center")
        self._redraw()

    def is_working(self):
        return self._working

    def _fit_busy(self):
        """As much of the report as there is room for."""
        room = max(0, self.winfo_height() - 2 * px(12))
        chosen = set()
        for count in range(len(self._busy_order) + 1):
            chosen = set(self._busy_order[:count])
            total, first = 0, True
            for index, (widget, gap) in enumerate(self._busy_rows):
                if index in chosen:
                    continue
                total += widget.winfo_reqheight() + (0 if first else gap)
                first = False
            if not room or total <= room:
                break
        # The bar takes whatever height is left after the rows that are
        # staying, rather than keeping its own and being cut off by the
        # top and bottom of the box.
        spare = room
        for index, (widget, gap) in enumerate(self._busy_rows):
            if index in chosen or widget is self._bar_row:
                continue
            spare -= widget.winfo_reqheight() + gap
        self.pill.set_height(min(px(ProgressPill.HEIGHT), spare - px(4)))
        if chosen == self._busy_shown:
            return
        self._busy_shown = chosen
        first = True
        for index, (widget, gap) in enumerate(self._busy_rows):
            widget.pack_forget()
            if index in chosen:
                continue
            widget.pack(fill="x" if widget is self._bar_row else "none",
                        pady=(0 if first else gap, 0))
            first = False

    def droppable(self):
        """Every widget a file could be let go over.

        The canvas and the label sit *on top of* the frame, so registering
        only the frame leaves the middle of the box — the part anyone
        aims at — not a drop target at all.
        """
        return [w for w in self._invite if w is not None]

    def compact(self, on):
        """Shrink to one line, or go back to the full invitation."""
        on = bool(on)
        if on == self._compact:
            return
        self._compact = on
        self._shown = None
        try:
            if on:
                # An explicit height, because everything inside is placed
                # rather than packed and a frame asked how tall it wants
                # to be answers "one pixel".
                self.pack_propagate(False)
                self.configure(height=px(46))
            else:
                self.pack_propagate(True)
                self.configure(height=1)
        except Exception:
            pass
        self._fit()
        self._redraw()

    def is_compact(self):
        return self._compact

    def promise_drops(self, can_drop):
        """Say what the box can actually do.

        Tk gets drag and drop from an extension, and on a machine without
        it a file dropped here goes nowhere. The words underneath said
        "Drag & drop an image" regardless, so on those machines the box
        described something that was never going to happen and the only
        way in went unmentioned. It says what it can do.
        """
        self._can_drop = bool(can_drop)
        self.invite_label.configure(
            text=("Drag & drop an image, or click to upload" if can_drop
                  else "Click to upload an image or PDF"))
        self._redraw()

    def highlight(self, on):
        """Shown while a file is being dragged over the window."""
        if on != self._over:
            self._over = on
            self._redraw()

    def _needed(self, dropped):
        total, first = 0, True
        for index, (widget, gap) in enumerate(self._rows):
            if index in dropped:
                continue
            total += widget.winfo_reqheight() + (0 if first else gap)
            first = False
        return total

    def _fit(self, _event=None):
        """Show as much of the invitation as there is room for.

        The rows are dropped in a fixed order — decoration first, words
        after, the button never — so the box says less on a small screen
        rather than saying it half off the edge.
        """
        if self._compact:
            # One line and nothing else: the sentence, which is the only
            # row that says the whole box is a button.
            chosen = set(self._order)
        else:
            room = max(0, self.winfo_height() - 2 * px(12))
            chosen = set()
            for count in range(len(self._order) + 1):
                chosen = set(self._order[:count])
                if not room or self._needed(chosen) <= room:
                    break
        if chosen == self._shown:
            return
        self._shown = chosen
        first = True
        for index, (widget, gap) in enumerate(self._rows):
            widget.pack_forget()
            if index in chosen:
                continue
            widget.pack(pady=(0 if first else gap, 0))
            first = False

    def _redraw(self, _event=None):
        if self._working:
            self._fit_busy()
        else:
            self._fit()
        self.canvas.delete("all")
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        p = self.page
        colour = p["accent"] if self._over else p["field_line"]
        if self._over:
            self._wash = rounded_on(self.canvas, 0, 0, width, height,
                                    px(13), p["accent_soft"])
        # Dashes mean "put something here". Once something is here they
        # are describing a state the box is no longer in, so the edge
        # goes quiet and solid and lets the pill do the talking.
        _dashed_box(self.canvas, 1, 1, width - 2, height - 2, px(13), colour,
                    max(1, px(2)), dashed=not self._working)


def _dashed_box(canvas, x0, y0, x1, y1, radius, colour, width, dashed=True):
    """A dashed rounded rectangle. Tk draws dashes on lines and arcs, and
    has no rounded rectangle at all, so it is four of each."""
    r = max(0, min(radius, (x1 - x0) // 2, (y1 - y0) // 2))
    kw = {"dash": (5, 4)} if dashed else {}
    for points in (((x0 + r, y0), (x1 - r, y0)), ((x1, y0 + r), (x1, y1 - r)),
                   ((x1 - r, y1), (x0 + r, y1)), ((x0, y1 - r), (x0, y0 + r))):
        flat = [n for point in points for n in point]
        canvas.create_line(*flat, fill=colour, width=width, **kw)
    for box, start in (((x1 - 2 * r, y0, x1, y0 + 2 * r), 0),
                       ((x1 - 2 * r, y1 - 2 * r, x1, y1), 270),
                       ((x0, y1 - 2 * r, x0 + 2 * r, y1), 180),
                       ((x0, y0, x0 + 2 * r, y0 + 2 * r), 90)):
        canvas.create_arc(*box, start=start, extent=90, style="arc",
                          outline=colour, width=width, **kw)


class GhostButton(tk.Canvas):
    """A quiet pill: a border, a word, and nothing else until you point
    at it."""

    def __init__(self, parent, page, label_text, command, bg, height=40,
                 size=14):
        self.page = page
        self.command = command
        self._hover = False
        self._font = tkfont.Font(**_font_kw(parent, size, 600))
        self._text = label_text
        h = px(height)
        width = self._font.measure(label_text) + px(44)
        tk.Canvas.__init__(self, parent, width=width, height=h, bg=bg,
                           highlightthickness=0, bd=0, cursor="arrow")
        self._width, self._height = width, h
        self._paint()
        self.bind("<Enter>", lambda _e=None: self._set(True))
        self.bind("<Leave>", lambda _e=None: self._set(False))
        self.bind("<Button-1>", self._click)

    def _set(self, on):
        self._hover = on
        self._paint()

    def _click(self, _event=None):
        if self.command:
            try:
                self.command()
            except Exception:
                pass
        return "break"

    def _paint(self):
        self.delete("all")
        p = self.page
        line = p["accent"] if self._hover else p["field_line"]
        ink = p["accent"] if self._hover else p["ink"]
        self._photo = rounded_on(self, 0, 0, self._width, self._height,
                                 self._height // 2, p["card"],
                                 outline=line)
        self.create_text(self._width / 2.0,
                         theme_mod.middle(self._height, self._font),
                         text=self._text, fill=ink, font=self._font)
