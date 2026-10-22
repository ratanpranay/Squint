"""Rounded, Apple-flavoured widgets for Tk.

Tk has no rounded anything: every native widget is a rectangle with a 3D
border. So the shapes here are drawn with PIL at 4x and downsampled, which is
what makes the edges smooth rather than stair-stepped, and cached per
(size, radius, colour) so resizing stays cheap. Text is still drawn by Tk on
top, so it keeps ClearType hinting instead of PIL's softer rasteriser.
"""
import math
import sys
import tkinter as tk
import tkinter.font as tkfont

from PIL import Image, ImageDraw, ImageTk

from . import theme as theme_mod

SS = 4                      # supersampling factor for anti-aliasing
_image_cache = {}
_tile_cache = {}            # corner art, shared by every size of a shape
_CACHE_LIMIT = 400


def _interp(owner):
    """Which Tk an image belongs to.

    Part of every cache key below, because a PhotoImage is meaningless
    to an interpreter other than the one that made it: handed back to a
    second Tk, the canvas answers that the image does not exist, and
    that message names the canvas rather than the cache. A second
    interpreter is not exotic — changing the theme puts the window up
    again — so the key says which one.
    """
    try:
        return id(owner.tk)
    except Exception:
        return 0


def _remember(key, photo):
    """Bounded cache. Drops the oldest entry rather than emptying itself,
    so a busy resize cannot evict every image at once."""
    if len(_image_cache) >= _CACHE_LIMIT:
        for old in list(_image_cache)[:_CACHE_LIMIT // 4]:
            _image_cache.pop(old, None)
    _image_cache[key] = photo
    return photo


def _hex_to_rgb(value):
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def touchpad_deltas(widget, event):
    """(dx, dy) in pixels from a <TouchpadScroll> event, or (0, 0).

    Tk 9 on a Mac reports a trackpad as <TouchpadScroll>, not <MouseWheel>,
    with both directions packed into one number. The Python the Mac app
    ships with has Tk 9, and every page stopped scrolling on a trackpad:
    the wheel bindings were waiting for an event that no longer came.
    """
    try:
        values = widget.tk.splitlist(
            widget.tk.call("tk::PreciseScrollDeltas", event.delta))
        return float(values[0]), float(values[1])
    except Exception:
        return 0.0, 0.0


def bind_touchpad(widget, handler):
    """Bind <TouchpadScroll> where this Tk has it (9.0 and later)."""
    try:
        widget.bind("<TouchpadScroll>", handler, add="+")
        return True
    except Exception:
        return False


def _blend(top, bottom, alpha):
    """Flatten a translucent colour onto an opaque one."""
    t, b = _hex_to_rgb(top), _hex_to_rgb(bottom)
    return "#%02x%02x%02x" % tuple(
        int(round(t[i] * alpha + b[i] * (1 - alpha))) for i in range(3))


def _corner_tile(radius, fill, outline, outline_width):
    """The four corners of a rounded rectangle, drawn once per radius.

    A rounded rectangle 2r wide and 2r high with radius r has exactly the
    corner this shape needs, whatever the rectangle's real size — so the
    expensive supersampled drawing is done on that small square and the
    corners are cut out of it. Everything else in the shape is a straight
    edge, which needs no anti-aliasing at all.

    This is what makes the window open quickly. Supersampling the whole
    shape meant a 950x300 card was drawn at 3800x1200 and scaled back down,
    ~25ms each, dozens of times while the layout settled — nearly all of
    the second the window took to appear. The cost now depends on the
    corner radius, not on the size of the card.
    """
    key = ("corner", radius, fill, outline, outline_width)
    tile = _tile_cache.get(key)
    if tile is not None:
        return tile
    size = radius * 2
    img = Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle(
        [0, 0, size * SS - 1, size * SS - 1], radius=radius * SS,
        fill=_hex_to_rgb(fill) + (255,),
        outline=(_hex_to_rgb(outline) + (255,)) if outline else None,
        width=outline_width * SS if outline else 0)
    img = img.resize((size, size), Image.LANCZOS)
    if len(_tile_cache) > 200:
        _tile_cache.clear()
    _tile_cache[key] = img
    return img


def rounded_image(width, height, radius, fill, outline=None,
                  outline_width=1):
    """The rounded rectangle as PIL pixels, before Tk sees it."""
    rgb = _hex_to_rgb(fill) + (255,)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if radius <= 0:
        draw.rectangle([0, 0, width - 1, height - 1], fill=rgb,
                       outline=(_hex_to_rgb(outline) + (255,))
                       if outline else None,
                       width=outline_width if outline else 0)
        return img

    r = radius

    def band(x0, y0, x1, y1, colour):
        """Fill a rectangle, unless it has no area.

        A pill is the case that needs this: when the radius is half the
        height, the corners meet and the strip between them is empty. PIL
        rejects a rectangle whose end is before its start, so the strip has
        to be skipped rather than drawn backwards.
        """
        if x1 >= x0 and y1 >= y0:
            draw.rectangle([x0, y0, x1, y1], fill=colour)

    # The body: a cross of two rectangles that leaves the corners empty.
    band(r, 0, width - r - 1, height - 1, rgb)
    band(0, r, width - 1, height - r - 1, rgb)
    if outline:
        line = _hex_to_rgb(outline) + (255,)
        w = max(1, int(outline_width))
        band(r, 0, width - r - 1, w - 1, line)
        band(r, height - w, width - r - 1, height - 1, line)
        band(0, r, w - 1, height - r - 1, line)
        band(width - w, r, width - 1, height - r - 1, line)

    tile = _corner_tile(r, fill, outline, outline_width)
    img.paste(tile.crop((0, 0, r, r)), (0, 0))
    img.paste(tile.crop((r, 0, r * 2, r)), (width - r, 0))
    img.paste(tile.crop((0, r, r, r * 2)), (0, height - r))
    img.paste(tile.crop((r, r, r * 2, r * 2)), (width - r, height - r))
    return img


def rounded(width, height, radius, fill, outline=None, owner=None,
            outline_width=1):
    """An anti-aliased rounded rectangle as a PhotoImage. Cached."""
    width, height = max(1, int(width)), max(1, int(height))
    radius = max(0, min(int(radius), width // 2, height // 2))
    key = (_interp(owner), width, height, radius, fill, outline,
           outline_width)
    hit = _image_cache.get(key)
    if hit is not None:
        return hit
    img = rounded_image(width, height, radius, fill, outline, outline_width)
    return _remember(key, ImageTk.PhotoImage(img, master=owner))


#: Draw the app's rounded shapes with the canvas rather than as a
#: picture, where the canvas is the sharper of the two.
#:
#: Tk's canvas has no anti-aliasing at all on Windows and Linux, so a
#: rounded corner drawn there is a staircase and a rendered picture is
#: the only way to get a curve. On macOS the canvas goes through
#: CoreGraphics, which anti-aliases and draws at the screen's own
#: resolution, while a PhotoImage is drawn one image pixel to the point
#: whatever the screen is. So every pill, field, card and keycap in the
#: app was a bitmap on the one platform where a bitmap is the worse
#: answer.
VECTOR_PLATES = (sys.platform == "darwin")

#: The fewest and the most points a corner is drawn with.
#:
#: It was a flat eight, which is fine on a small radius and visibly
#: faceted on a large one: the end of a pill is a half-circle of radius
#: nineteen points, which on a screen drawing two device pixels to the
#: point is a sixty-pixel arc — and eight straight segments across that
#: are eight straight segments you can see. Zoomed in on a screenshot it
#: reads as exactly the thing this was supposed to remove.
#:
#: The count follows the radius instead: about one segment per point of
#: radius, which on a Retina screen is a segment every two device
#: pixels, which is finer than the anti-aliasing that draws it.
CORNER_MIN, CORNER_MAX = 10, 96

#: Segments per point of radius. Two puts a joint every 1.6 device
#: pixels on a screen drawing two to the point — finer than the
#: anti-aliasing that draws them, which is the definition of enough.
CORNER_DENSITY = 2.0


def corner_steps(radius):
    """How many straight segments to draw one corner's quarter-circle.

    Measured rather than picked: the arc is a quarter of 2*pi*r, so a
    count of `n` puts a joint every (pi * r / 2) / n points — times two
    for a Retina screen. At radius nineteen, which is the end of every
    pill in the app, eight segments is a joint every 3.7 device pixels
    and you can see each one.
    """
    try:
        wanted = int(round(float(radius) * CORNER_DENSITY))
    except Exception:
        wanted = CORNER_MIN
    return max(CORNER_MIN, min(CORNER_MAX, wanted))

#: How far inside its own widget a drawn plate keeps.
#:
#: This is the whole of why the first attempt came back with every pill
#: looking as though its rounded ends had been cut off flat. A canvas
#: clips at the widget's edge, and a shape drawn from 0 to the full
#: width has its outermost pixels exactly on that edge — where an
#: anti-aliased curve puts its softest, most important pixels. On
#: Windows and Linux there is no anti-aliasing to lose, so nothing shows;
#: on macOS the curve is cut at both extremes, which reads as a pill with
#: its ends sliced off.
#:
#: A pixel and a half, which is a whole device pixel on a screen drawing
#: two to the point plus a half for the stroke that is centred on the
#: path. Nobody can see a pill that is three pixels narrower than its
#: widget; everybody can see one with a flat end.
BLEED = 1.5


def _round_path(x, y, width, height, radius):
    """The outline of a rounded rectangle, as a flat list of points.

    A polygon rather than four arcs and two rectangles: one item, one
    fill, one outline, and no seams where the pieces meet — a seam
    between an arc and a rectangle is a hairline of background colour
    that shows on exactly the curves this exists to make smooth.
    """
    radius = max(0.0, min(float(radius), width / 2.0, height / 2.0))
    if radius <= 0.5:
        return [x, y, x + width, y, x + width, y + height, x, y + height]
    right, bottom = x + width, y + height
    corners = ((right - radius, y + radius, -90.0),      # top right
               (right - radius, bottom - radius, 0.0),   # bottom right
               (x + radius, bottom - radius, 90.0),      # bottom left
               (x + radius, y + radius, 180.0))          # top left
    steps = corner_steps(radius)
    points = []
    for cx, cy, start in corners:
        for step in range(steps + 1):
            angle = math.radians(start + 90.0 * step / steps)
            points.append(cx + radius * math.cos(angle))
            points.append(cy + radius * math.sin(angle))
    return points


def plate_item(canvas, x=0, y=0, tags=()):
    """The canvas item a rounded plate lives in, made once.

    Every widget here paints by keeping one item and reconfiguring it,
    which is what holds the stacking order: the plate is made first, so
    everything made after it is on top of it. That has to stay true
    whichever way the plate is drawn, so the vector plate is a polygon
    made in the same breath and reconfigured the same way, rather than
    a fresh item on every repaint that would land on top of the text.
    """
    if VECTOR_PLATES:
        return canvas.create_polygon(x, y, x + 1, y, x + 1, y + 1,
                                     tags=tags, joinstyle="round")
    return canvas.create_image(x, y, anchor="nw", tags=tags)


def set_plate(canvas, item, x, y, width, height, radius, fill,
              outline=None, outline_width=1):
    """Give `item` the shape and colours of a rounded rectangle.

    Returns the PhotoImage to keep alive, or None when it was drawn —
    so the caller assigns what comes back exactly as it did before.
    """
    width, height = max(1, int(width)), max(1, int(height))
    try:
        kind = canvas.type(item)
    except Exception:
        kind = None
    if kind == "polygon":
        edge = BLEED + max(0, int(outline_width)) / 2.0
        canvas.coords(item, *_round_path(x + edge, y + edge,
                                         max(1.0, width - edge * 2),
                                         max(1.0, height - edge * 2),
                                         radius - edge))
        canvas.itemconfigure(item, fill=fill, outline=outline or fill,
                             width=max(1, int(outline_width)))
        return None
    photo = rounded(width, height, radius, fill, outline, canvas,
                    outline_width)
    canvas.itemconfigure(item, image=photo)
    try:
        canvas.coords(item, x, y)
    except Exception:
        pass
    return photo


def rounded_on(canvas, x, y, width, height, radius, fill, outline=None,
               outline_width=1, tags=()):
    """Put a rounded rectangle on `canvas` at (x, y).

    Returns the PhotoImage that has to be kept alive, or None when it
    was drawn rather than placed — so a caller keeps doing exactly what
    it did before with what comes back, and holding None costs nothing.
    """
    width, height = max(1, int(width)), max(1, int(height))
    if VECTOR_PLATES:
        try:
            edge = BLEED + max(0, int(outline_width)) / 2.0
            canvas.create_polygon(
                _round_path(x + edge, y + edge,
                            max(1.0, width - edge * 2),
                            max(1.0, height - edge * 2), radius - edge),
                fill=fill, outline=outline or fill,
                width=max(1, int(outline_width)), joinstyle="round",
                tags=tags)
            return None
        except Exception:
            pass
    photo = rounded(width, height, radius, fill, outline, canvas,
                    outline_width)
    canvas.create_image(x, y, anchor="nw", image=photo, tags=tags)
    return photo


def circle(diameter, fill, owner=None, shadow=None):
    key = ("circle", _interp(owner), diameter, fill, shadow)
    hit = _image_cache.get(key)
    if hit is not None:
        return hit
    size = int(diameter) * SS
    pad = SS * 2
    img = Image.new("RGBA", (size + pad * 2, size + pad * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if shadow:
        draw.ellipse([pad, pad + SS, pad + size, pad + size + SS],
                     fill=_hex_to_rgb(shadow) + (60,))
    draw.ellipse([pad, pad, pad + size, pad + size],
                 fill=_hex_to_rgb(fill) + (255,))
    out = int(diameter) + (pad * 2) // SS
    img = img.resize((out, out), Image.LANCZOS)
    return _remember(key, ImageTk.PhotoImage(img, master=owner))


class Surface(tk.Frame):
    """A rounded panel. Children go into `.body`.

    This is a Frame with a Canvas placed behind it, not a Canvas with the
    contents embedded in it — and that distinction is the whole point.

    The card used to be a Canvas holding its contents in a canvas window
    item. On macOS those contents were repeatedly not drawn: Settings would
    open showing the card backgrounds with nothing inside them, and a
    scroll or a resize would bring the text in. Sizing the item from an
    event that had not arrived yet was one cause and was fixed; this is the
    same failure returning by another route, so the structure goes rather
    than getting patched a third time. A normally packed child is mapped by
    the geometry manager like any other widget, with no item to size and no
    event to wait for.
    """

    def __init__(self, parent, palette, radius=14, fill=None, outline=None,
                 padding=0, **kwargs):
        self.palette = palette
        self.radius = radius
        self.fill = fill or palette["surface"]
        self.outline = outline
        self._bg = kwargs.pop("bg", palette["window"])
        super().__init__(parent, bg=self._bg, **kwargs)
        # The rounded shape lives on a canvas behind everything, sized to
        # the frame. It draws nothing but the background.
        self._back = tk.Canvas(self, highlightthickness=0, bd=0,
                               bg=self._bg)
        self._back.place(x=0, y=0, relwidth=1, relheight=1)
        self._img_id = plate_item(self._back)
        self._photo = None
        self.padding = padding
        self.body = tk.Frame(self, bg=self.fill)
        self.body.pack(fill="both", expand=True, padx=padding, pady=padding)
        self.body.lift()
        self.bind("<Configure>", self._redraw)

    def set_fill(self, colour):
        self.fill = colour
        self.body.configure(bg=colour)
        self._redraw()

    def _redraw(self, _event=None):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 2 or h < 2:
            return
        self._photo = set_plate(self._back, self._img_id, 0, 0, w, h,
                                self.radius, self.fill, self.outline)


class PillButton(tk.Canvas):
    """A real pill: fully rounded, with hover and press states."""

    KINDS = ("primary", "secondary", "ghost", "danger")

    # A filled pill is already loud: bold type inside one reads as shouting,
    # and at the app's text scale it also left almost no margin between the
    # letters and the curve. Regular weight, a size below body text, and a
    # wider inset are what give the label room to breathe.
    def __init__(self, parent, text, command=None, palette=None,
                 kind="primary", height=36, min_width=0, font_size=9,
                 bg=None, radius=None, pad_x=24, weight="normal",
                 icon=None):
        self.palette = palette
        self.kind = kind
        self.command = command
        self._text = text
        self._enabled = True
        self._state = "normal"
        self._h = height
        self._radius = radius if radius is not None else height // 2
        self._bg = bg or palette["window"]
        #: A mark to the left of the label, for the one or two buttons
        #: that do something to a file rather than to the page. It is
        #: part of the width, so a label that changes still centres the
        #: pair rather than the words alone.
        self._icon = icon
        self._icon_size = int(height * 0.42) if icon else 0
        self._icon_gap = max(4, int(height * 0.16)) if icon else 0

        self._font = tkfont.Font(
            family=theme_mod.body_family(parent),
            size=theme_mod.text_size(font_size),
            weight=weight)
        self._min_w, self._pad_x = min_width, pad_x
        width = max(min_width, self._measure(text))

        super().__init__(parent, width=width, height=height,
                         highlightthickness=0, bd=0, bg=self._bg,
                         cursor="arrow")
        self._img_id = plate_item(self)
        self._text_id = self.create_text(
            width // 2, theme_mod.middle(height, self._font),
            text=text, font=self._font,
            fill=self._fg())
        self._photo = None
        self._paint()

        self.bind("<Enter>", lambda _e=None: self._set_state("hover"))
        self.bind("<Leave>", lambda _e=None: self._set_state("normal"))
        self.bind("<ButtonPress-1>", lambda _e=None: self._set_state("active"))
        self.bind("<ButtonRelease-1>", self._release)

    def _measure(self, text):
        """How wide the pill has to be for this label, mark included."""
        return (self._font.measure(text) + self._pad_x * 2
                + self._icon_size + self._icon_gap)

    # A pressed button is white with black text, whatever kind it is, and
    # hover is a light wash of white over the resting colour. Consistent
    # feedback matters more here than each kind having its own idea.
    PRESSED_FILL = "#FFFFFF"
    PRESSED_TEXT = "#111111"
    HOVER_WASH = 0.18

    # -- appearance ----------------------------------------------------
    def _colours(self):
        p = self.palette
        if not self._enabled:
            return _blend(p["separator"], p["window"], 0.6), p["text_faint"]
        if self._state == "active":
            return self.PRESSED_FILL, self.PRESSED_TEXT
        if self.kind == "primary":
            base = p["accent"]
            fill = base if self._state == "normal" else _blend(
                "#FFFFFF", base, self.HOVER_WASH)
            return fill, p["accent_text"]
        if self.kind == "danger":
            base = p["danger"]
            fill = base if self._state == "normal" else _blend(
                "#FFFFFF", base, self.HOVER_WASH)
            return fill, "#FFFFFF"
        if self.kind == "secondary":
            base = p["surface_hi"] if p["name"] == "dark" else p["surface"]
            fill = base if self._state == "normal" else _blend(
                "#FFFFFF", base, self.HOVER_WASH)
            return fill, p["text"]
        # ghost: invisible until touched
        fill = self._bg if self._state == "normal" else _blend(
            "#FFFFFF", self._bg, self.HOVER_WASH)
        return fill, p["accent"] if self.kind == "ghost" else p["text"]

    def _fg(self):
        return self._colours()[1]

    def _paint(self):
        fill, fg = self._colours()
        w = int(self["width"])
        outline = None
        if self.kind == "secondary" and self.palette["name"] == "light":
            outline = self.palette["separator"]
        self._photo = set_plate(self, self._img_id, 0, 0, w, self._h,
                                self._radius, fill, outline)
        self.itemconfig(self._text_id, fill=fg)
        self._place_label(w)
        self.tag_raise(self._text_id)

    def _place_label(self, w):
        """The mark and the words, centred as one thing."""
        self.delete("mark")
        if not self._icon:
            self.coords(self._text_id, w // 2,
                        theme_mod.middle(self._h, self._font))
            return
        block = self._font.measure(self._text) + self._icon_size + self._icon_gap
        left = (w - block) / 2.0
        self.coords(self._text_id,
                    left + self._icon_size + self._icon_gap
                    + self._font.measure(self._text) / 2.0,
                    theme_mod.middle(self._h, self._font))
        try:
            from . import ui_icons
            ui_icons.draw(self, self._icon, left,
                          (self._h - self._icon_size) / 2.0,
                          self._icon_size, self._fg(), width=1.8,
                          tags="mark")
        except Exception:
            pass

    def _set_state(self, state):
        if not self._enabled:
            return
        self._state = state
        self._paint()

    def _release(self, event):
        if not self._enabled:
            return
        inside = (0 <= event.x <= int(self["width"])
                  and 0 <= event.y <= self._h)
        self._set_state("hover" if inside else "normal")
        if inside and self.command:
            self.command()

    # -- api -----------------------------------------------------------
    def configure_text(self, text):
        self._text = text
        self.itemconfig(self._text_id, text=text)
        # Measured from the new text, not grown from the old width: a button
        # that changes from "Download" to "Update" should get narrower, and
        # taking the larger of the two left it stuck at its widest label.
        width = max(self._min_w, self._measure(text))
        self.configure(width=width)
        self._paint()

    def set_min_width(self, width):
        """Hold a floor under the width, so buttons meant to look like a set
        do. Two stacked buttons with different labels are otherwise two
        different widths, which reads as a mistake rather than a hierarchy."""
        self._min_w = int(width)
        self.configure_text(self._text)

    def set_enabled(self, enabled):
        self._enabled = bool(enabled)
        self.configure(cursor="arrow")
        self._state = "normal"
        self._paint()

    def set_palette(self, palette, bg=None):
        self.palette = palette
        if bg:
            self._bg = bg
        self.configure(bg=self._bg)
        self._paint()


class Segmented(tk.Canvas):
    """iOS-style segmented control: a track with a sliding selected pill."""

    def __init__(self, parent, options, palette, command=None, height=34,
                 font_size=10, bg=None, pad=22):
        self.palette = palette
        self.options = list(options)
        self.command = command
        self._index = 0
        self._h = height
        self._bg = bg or palette["window"]
        self._font = tkfont.Font(
            **({"font": self._given_font} if self._given_font else
               {"family": theme_mod.body_family(parent),
                "size": theme_mod.text_size(font_size)}))
        self._font_sel = tkfont.Font(family=theme_mod.body_family(parent),
                                     size=theme_mod.text_size(font_size),
                                     weight="bold")

        self._seg_w = max(self._font_sel.measure(o) for o in self.options)
        self._seg_w += pad * 2
        width = self._seg_w * len(self.options) + 6

        super().__init__(parent, width=width, height=height,
                         highlightthickness=0, bd=0, bg=self._bg,
                         cursor="arrow")
        self._track_id = plate_item(self)
        self._thumb_id = plate_item(self, 3, 3)
        self._labels = [
            self.create_text(3 + self._seg_w * i + self._seg_w // 2,
                             theme_mod.middle(height, self._font),
                             text=option, font=self._font,
                             fill=palette["text_dim"])
            for i, option in enumerate(self.options)]
        self._track_photo = None
        self._thumb_photo = None
        self._anim = None
        self._x = 3.0
        self._paint()
        self.bind("<Button-1>", self._click)

    def _paint(self):
        p = self.palette
        w = int(self["width"])
        self._track_photo = set_plate(self, self._track_id, 0, 0, w,
                                      self._h, self._h // 2, p["track"])
        thumb_fill = p["surface"] if p["name"] == "dark" else "#FFFFFF"
        self._thumb_photo = set_plate(
            self, self._thumb_id, self._x, 3, self._seg_w, self._h - 6,
            (self._h - 6) // 2, thumb_fill)
        for i, item in enumerate(self._labels):
            selected = i == self._index
            self.itemconfig(item, font=self._font_sel if selected
                            else self._font,
                            fill=p["text"] if selected else p["text_dim"])
            self.tag_raise(item)

    def _click(self, event):
        index = int((event.x - 3) // self._seg_w)
        index = max(0, min(index, len(self.options) - 1))
        self.select(index)

    def select(self, index, animate=True):
        if index == self._index:
            return
        self._index = index
        target = 3 + self._seg_w * index
        if animate:
            self._animate_to(target)
        else:
            self._x = target
        self._paint()
        if self.command:
            self.command(index, self.options[index])

    def _animate_to(self, target, step=0):
        if self._anim:
            try:
                self.after_cancel(self._anim)
            except Exception:
                pass
        frames = 10
        start = self._x

        def tick(i):
            # ease-out cubic, the curve Apple's controls use
            t = min(1.0, (i + 1) / frames)
            eased = 1 - pow(1 - t, 3)
            self._x = start + (target - start) * eased
            self.coords(self._thumb_id, self._x, 3)
            if i + 1 < frames:
                self._anim = self.after(12, tick, i + 1)
            else:
                self._anim = None

        tick(step)

    def set_palette(self, palette, bg=None):
        self.palette = palette
        if bg:
            self._bg = bg
        self.configure(bg=self._bg)
        self._paint()


class Switch(tk.Canvas):
    """iOS toggle. Wraps a BooleanVar so it drops into existing code."""

    W, H = 46, 28

    def __init__(self, parent, palette, variable=None, command=None, bg=None):
        self.palette = palette
        self.var = variable or tk.BooleanVar(value=False)
        self.command = command
        self._bg = bg or palette["window"]
        super().__init__(parent, width=self.W, height=self.H,
                         highlightthickness=0, bd=0, bg=self._bg,
                         cursor="arrow")
        self._track_id = plate_item(self)
        self._knob_id = (self.create_oval(0, 0, 1, 1, width=0)
                         if VECTOR_PLATES
                         else self.create_image(0, 0, anchor="nw"))
        self._track_photo = None
        self._knob_photo = None
        self._pos = 1.0 if self.var.get() else 0.0
        self._anim = None
        self._paint()
        self.bind("<Button-1>", lambda _e=None: self.toggle())

    def _paint(self):
        p = self.palette
        on = self.var.get()
        track = p["accent"] if on else p["track"]
        self._track_photo = set_plate(self, self._track_id, 0, 0, self.W,
                                      self.H, self.H // 2, track)
        knob = 22
        travel = self.W - knob - 6
        x = 3 + travel * self._pos
        y = (self.H - knob) // 2
        if VECTOR_PLATES:
            # No shadow under it: the picture carried one, and a canvas
            # oval cannot. At this size, on a track this colour, what the
            # shadow was doing was softening a bitmap edge — which is the
            # thing that is no longer there to soften.
            self.coords(self._knob_id, x, y, x + knob, y + knob)
            self.itemconfig(self._knob_id, fill="#FFFFFF", outline="")
        else:
            self._knob_photo = circle(knob, "#FFFFFF", owner=self,
                                      shadow=p["shadow"])
            self.coords(self._knob_id, x - 2, y - 2)
            self.itemconfig(self._knob_id, image=self._knob_photo)

    def toggle(self):
        self.var.set(not self.var.get())
        self._animate()
        if self.command:
            self.command()

    def _animate(self):
        target = 1.0 if self.var.get() else 0.0
        start = self._pos
        frames = 8
        if self._anim:
            try:
                self.after_cancel(self._anim)
            except Exception:
                pass

        def tick(i):
            t = min(1.0, (i + 1) / frames)
            self._pos = start + (target - start) * (1 - pow(1 - t, 3))
            self._paint()
            if i + 1 < frames:
                self._anim = self.after(12, tick, i + 1)
            else:
                self._anim = None

        tick(0)

    def set_palette(self, palette, bg=None):
        self.palette = palette
        if bg:
            self._bg = bg
        self.configure(bg=self._bg)
        self._paint()


class Field(tk.Frame):
    """Rounded single-line entry."""

    def __init__(self, parent, palette, textvariable=None, width=18,
                 bg=None, height=32, font_size=10, fill=None):
        self.palette = palette
        self.fill = fill or palette["field"]
        self._bg = bg or palette["window"]
        super().__init__(parent, bg=self._bg)
        self.canvas = tk.Canvas(self, height=height, highlightthickness=0,
                                bd=0, bg=self._bg)
        self.canvas.pack(fill="both", expand=True)
        self._img_id = plate_item(self.canvas)
        self._photo = None
        self.entry = tk.Entry(
            self.canvas, textvariable=textvariable, width=width, bd=0,
            highlightthickness=0, relief="flat",
            bg=self.fill, fg=palette["text"],
            insertbackground=palette["accent"],
            font=theme_mod.font(parent, font_size),
            disabledbackground=self.fill)
        self._win = self.canvas.create_window(14, height // 2, anchor="w",
                                              window=self.entry)
        self.canvas.bind("<Configure>", self._redraw)

    def _redraw(self, _event=None):
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 2 or h < 2:
            return
        outline = (self.palette["separator"]
                   if self.palette["name"] == "light" else None)
        self._photo = set_plate(self.canvas, self._img_id, 0, 0, w, h,
                                min(10, h // 2), self.fill, outline)
        self.canvas.itemconfig(self._win, width=max(10, w - 28))
        self.canvas.tag_raise(self._win)


def pinned_count(values):
    """How many choices at the top are deliberately out of order.

    A language list is alphabetical apart from its first entries — "Detect
    language", then the reader's own language — because those are the ones
    actually chosen. Found rather than declared: the pinned part is
    whatever comes before the point where the list becomes sorted, so a
    list sorted all the way through pins nothing.
    """
    values = list(values)
    for start in range(len(values)):
        tail = values[start:]
        if tail == sorted(tail, key=lambda v: v.lower()):
            return start
    return 0


def fill_grouped(menu, values, pinned, choose, heading_font, column_rows=20):
    """Pinned choices, a rule, then a heading per letter, in columns.

    Sixty languages in one column is taller than a laptop screen and
    unmarked, so finding one means reading past forty others. Broken into
    columns with a heading per letter it is four short lists side by side.

    A letter never begins halfway down a full column — it starts the next
    one. A column may run a few rows long to keep a letter whole, which is
    worth it: a reader who has to check two columns for one letter is
    worse off than one looking at a slightly uneven column.
    """
    values = list(values)
    for value in values[:pinned]:
        menu.add_command(label=value, command=lambda v=value: choose(v))
    if pinned:
        menu.add_separator()
    rows = pinned + (1 if pinned else 0)
    letter = None
    for value in values[pinned:]:
        initial = value[:1].upper()
        if initial != letter:
            letter = initial
            if rows >= column_rows:
                menu.add_command(label=letter, state="disabled",
                                 font=heading_font, columnbreak=1)
                rows = 1
            else:
                menu.add_command(label=letter, state="disabled",
                                 font=heading_font)
                rows += 1
        menu.add_command(label=value, command=lambda v=value: choose(v))
        rows += 1


class Dropdown(tk.Canvas):
    """Pill-shaped popup menu — replaces ttk.Combobox, which cannot be
    restyled far enough to stop looking like Windows 98."""

    # One height for every popup in the app. They were 32, 40 and 42 in
    # different places, which is the "inconsistent sizes" the settings page
    # was called out for.
    HEIGHT = 38

    # Where the label starts, and how much room the chevron needs after it.
    TEXT_X = 18
    CHEVRON_ROOM = 36

    def __init__(self, parent, palette, values, value=None, command=None,
                 width=None, height=HEIGHT, font_size=10, bg=None,
                 max_width=320, min_width=96, icon=None, icon_colour=None,
                 radius=None, font=None):
        # `bg` is what shows at the four corners of the pill, because a
        # canvas widget is a rectangle and a pill is not. Told, never
        # assumed: five of these in Settings were left to default to the
        # page's colour while sitting on a card, and in dark that is a
        # visible dark square behind every rounded corner. Where it is
        # not given, take the colour of whatever this is being put into
        # rather than the page's — the parent is nearly always right and
        # the page nearly always wrong.
        if bg is None:
            try:
                bg = parent.cget("bg")
            except Exception:
                bg = None
        # A ready-made font, for callers that size their own type. The
        # front page is drawn in pixels at a scale it chooses; `font_size`
        # here goes through the app-wide point scale instead, so a popup
        # left to size itself came out half again too big on a page that
        # had shrunk to fit the screen.
        self._given_font = font
        # A leading mark, for the language rows on the front page: the
        # design puts a globe at the head of each. Optional and absent
        # everywhere else, so every other popup in the app is unchanged.
        self.icon = icon
        self.icon_colour = icon_colour
        self._radius = radius
        self.palette = palette
        self.values = list(values)
        self.command = command
        self._value = value or (self.values[0] if self.values else "")
        self._bg = bg or palette["window"]
        self._h = height
        self._state = "normal"
        self._font = tkfont.Font(
            **({"font": self._given_font} if self._given_font else
               {"family": theme_mod.body_family(parent),
                "size": theme_mod.text_size(font_size)}))
        # Sized to its own contents unless told otherwise. A fixed width was
        # wrong in both directions at once: "Automatic — best available" was
        # cut off mid-word in a 250px box, while "Detect language" ran past
        # the end of its pill and over the chevron. Neither is a size that
        # can be guessed in advance — the font decides, and the font differs
        # per platform, which is why this only showed up on Windows.
        if width is None:
            widest = max([self._font.measure(v) for v in self.values] or [0])
            width = widest + self._text_x() + self.CHEVRON_ROOM
            width = max(min_width, min(int(max_width), width))
        super().__init__(parent, width=width, height=height,
                         highlightthickness=0, bd=0, bg=self._bg,
                         cursor="arrow")
        self._img_id = plate_item(self)
        self._text_id = self.create_text(self._text_x(), height // 2,
                                         anchor="w", text=self._value,
                                         font=self._font,
                                         fill=palette["text"])
        # The chevron is drawn, not typed. As a "⌄" character it sat wherever
        # the font's own metrics put it, which on macOS is well above the
        # centre of the box — it read as misaligned with the label beside it.
        # Two short lines can be placed exactly halfway down, in any font.
        self._chev_id = self.create_line(0, 0, 0, 0, 0, 0,
                                         fill=palette["text_dim"], width=2,
                                         capstyle="round", joinstyle="round")
        self._place_chevron()
        self._photo = None
        self._menu = None
        self._paint()
        self.bind("<Enter>", lambda _e=None: self._hover(True))
        self.bind("<Leave>", lambda _e=None: self._hover(False))
        self.bind("<Button-1>", lambda _e=None: self.open())

    def _fitted(self, text):
        """The label, shortened with an ellipsis if it cannot fit.

        Tk canvas text is not clipped by anything: a label longer than the
        pill simply carries on over the chevron and out past the edge, which
        is what "text bleeding out of box" was.
        """
        try:
            room = int(self["width"]) - self._text_x() - self.CHEVRON_ROOM
        except Exception:
            return text
        if room < 20 or self._font.measure(text) <= room:
            return text
        ellipsis = "…"
        cut = text
        while cut and self._font.measure(cut + ellipsis) > room:
            cut = cut[:-1]
        return (cut.rstrip() + ellipsis) if cut else ellipsis

    def _place_chevron(self):
        try:
            width = int(self["width"])
        except Exception:
            width = 210
        x, y, arm = width - 20, self._h // 2, 5
        self.coords(self._chev_id,
                    x - arm, y - 2, x, y + 3, x + arm, y - 2)

    def _hover(self, on):
        self._state = "hover" if on else "normal"
        self._paint()

    ICON_SIZE = 19
    ICON_X = 16

    def _text_x(self):
        """Where the label starts: after the mark, when there is one."""
        if self.icon:
            return self.ICON_X + self.ICON_SIZE + 12
        return self.TEXT_X

    def _paint(self):
        p = self.palette
        base = p["surface_hi"] if p["name"] == "dark" else p["surface"]
        fill = _blend(p["text"], base, 0.06) if self._state == "hover" \
            else base
        outline = p["separator"] if p["name"] == "light" else None
        radius = self._radius if self._radius is not None else self._h // 2
        self._photo = set_plate(self, self._img_id, 0, 0,
                                int(self["width"]), self._h, radius,
                                fill, outline)
        self.coords(self._text_id, self._text_x(), self._h // 2)
        self.itemconfig(self._text_id, fill=p["text"],
                        text=self._fitted(self._value))
        self.itemconfig(self._chev_id, fill=p["text_dim"])
        self._place_chevron()
        self.delete("dropdown-icon")
        if self.icon:
            try:
                from . import ui_icons
                ui_icons.draw(self, self.icon, self.ICON_X,
                              (self._h - self.ICON_SIZE) / 2.0,
                              self.ICON_SIZE,
                              p[self.icon_colour] if self.icon_colour
                              else p["accent"], width=1.8,
                              tags=("dropdown-icon",))
            except Exception:
                pass
        self.tag_raise(self._text_id)
        self.tag_raise(self._chev_id)

    def set_width(self, width):
        """Resize after the fact, so a row of popups can be made to agree."""
        self.configure(width=max(40, int(width)))
        self._check_hover()
        self._paint()

    def _check_hover(self):
        """Ask where the pointer actually is, rather than trusting the
        last event.

        Hover is normally kept by <Enter> and <Leave>, which is right
        while the pointer is what moves. It is wrong when the *widget*
        moves: laid out under a stationary pointer it gets an <Enter>,
        and when the next layout slides it out from under that pointer
        there is no <Leave> to match — so it sits there lit up, looking
        like the one control on the row that is switched on.
        """
        if self._state == "active":
            return
        try:
            x, y = self.winfo_pointerxy()
            left, top = self.winfo_rootx(), self.winfo_rooty()
            inside = (left <= x < left + self.winfo_width()
                      and top <= y < top + self.winfo_height())
        except Exception:
            return
        self._state = "hover" if inside else "normal"

    def get(self):
        return self._value

    def set(self, value):
        self._value = value
        self._paint()

    # Above this many choices, a popup is a wall rather than a list.
    #
    # Sixty languages in one column is taller than the screen: the list
    # ran from the top edge to the bottom with the letters unmarked, so
    # finding Portuguese meant reading past forty other names. Broken into
    # columns with a heading per letter it is four short lists side by
    # side, and the eye goes straight to the letter.
    GROUP_AFTER = 20

    # How many rows a column may hold before the next letter starts a new
    # one. Twenty rows is about a third of a laptop screen.
    COLUMN_ROWS = 20

    def _pinned(self):
        return pinned_count(self.values)

    def open(self):
        p = self.palette
        menu = tk.Menu(self, tearoff=0,
                       bg=p["surface"], fg=p["text"],
                       activebackground=p["accent"],
                       activeforeground=p["accent_text"],
                       disabledforeground=p["text_dim"],
                       bd=0, relief="flat",
                       font=theme_mod.font(self, 10))
        pinned = self._pinned()
        if len(self.values) - pinned < self.GROUP_AFTER:
            for value in self.values:
                menu.add_command(label=value,
                                 command=lambda v=value: self._choose(v))
        else:
            self._fill_grouped(menu, pinned)
        try:
            menu.tk_popup(self.winfo_rootx(),
                          self.winfo_rooty() + self._h + 4)
        finally:
            menu.grab_release()
        self._menu = menu

    def _fill_grouped(self, menu, pinned):
        """The pinned choices, a rule, then a heading per letter."""
        fill_grouped(menu, self.values, pinned, self._choose,
                     theme_mod.font(self, 9, weight="bold"),
                     self.COLUMN_ROWS)

    def _choose(self, value):
        self.set(value)
        if self.command:
            self.command(value)

    def set_palette(self, palette, bg=None):
        self.palette = palette
        if bg:
            self._bg = bg
        self.configure(bg=self._bg)
        self._paint()


class TextPane(tk.Frame):
    """Rounded, borderless text area with a slim overlay scrollbar."""

    PAD_X, PAD_Y, INSET = 16, 12, 3

    def __init__(self, parent, palette, height=6, font_size=11,
                 bg=None, radius=12, readonly=False, on_clear=None,
                 min_lines=4, placeholder="", inner=None, outline=None,
                 font=None, grows=False, limit=0, max_lines=0):
        # What the box says when it is empty. Written into the widget as
        # a tagged run rather than drawn over it, so it scrolls, wraps
        # and measures like the text it is standing in for — and so that
        # the box is never a blank rectangle with no clue what it wants.
        self.placeholder = placeholder
        self._showing_placeholder = False
        #: A box that grows with what is typed into it and never scrolls.
        #:
        #: A small box that scrolls is worse than it sounds. The wheel
        #: over it is claimed by the box, so scrolling the page stops
        #: dead the moment the pointer crosses it and does not start
        #: again until the pointer is moved off — which is not something
        #: anybody does deliberately, so it reads as the page having
        #: seized. Growing instead means there is nothing inside to
        #: scroll, the wheel belongs to the page throughout, and what
        #: has been written is all visible at once.
        self.grows = bool(grows)
        #: How much may be typed, in characters. Nought is no limit.
        self.limit = int(limit or 0)
        #: And how far it may grow. Nought is as far as the text goes.
        self.max_lines = int(max_lines or 0)
        # Set here rather than where the rest of the Text plumbing is
        # built: the placeholder goes in during construction, and it
        # needs this before it can.
        self._suppress_modified = False
        self.palette = palette
        self._bg = bg or palette["window"]
        # The box's own colour, told rather than assumed. Sitting on a
        # card, "surface" is the card's colour and the box disappears
        # into it — visible in light only because the two happen to
        # differ by a border, and invisible in dark, where they do not.
        self._inner = inner or palette["surface"]
        self._outline = outline
        self.radius = radius
        self.min_lines = min_lines
        self._lines = 0                 # set once the Text exists
        self._start_lines = max(min_lines, height)
        super().__init__(parent, bg=self._bg)
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0,
                                bg=self._bg)
        self.canvas.pack(fill="both", expand=True)
        self._img_id = plate_item(self.canvas)
        self._photo = None

        self.text = tk.Text(
            self.canvas, wrap="word", bd=0, highlightthickness=0,
            height=height, padx=self.PAD_X, pady=self.PAD_Y,
            bg=self._inner, fg=palette["text"],
            insertbackground=palette["accent"],
            selectbackground=palette["accent"],
            selectforeground=palette["accent_text"],
            font=font or theme_mod.font(parent, font_size),
            spacing1=1, spacing3=5, relief="flat")
        self._win = self.canvas.create_window(0, 0, anchor="nw",
                                              window=self.text)
        self.scroll = SlimScrollbar(self.canvas, palette, self.text)
        self._scroll_win = self.canvas.create_window(
            0, 0, anchor="nw", window=self.scroll, width=SlimScrollbar.W)
        self.text.configure(yscrollcommand=self.scroll.set)
        if self.grows:
            # No bar, because there is nothing to scroll: the box is
            # always as tall as its contents.
            try:
                self.canvas.itemconfigure(self._scroll_win, state="hidden")
            except Exception:
                pass
            self.text.bind("<<Modified>>", self._on_grown, add="+")
            self.text.bind("<KeyPress>", self._cap, add="+")
            self.text.bind("<Configure>", self._on_grown, add="+")
            # The wheel is the page's. Without this the toplevel handler
            # steps aside for any Text, which is right for a box that
            # scrolls and exactly wrong for one that cannot.
            self.text.pass_wheel_up = True
        self.text.tag_configure("placeholder", foreground=palette["text_faint"])
        if self.placeholder:
            self.text.bind("<Key>", self._clear_placeholder, add="+")
            self.text.bind("<<Paste>>", self._clear_placeholder, add="+")
            self._set_placeholder(True)
        self.set_lines(self._start_lines)
        if readonly:
            self.text.configure(insertwidth=0)
        self.canvas.bind("<Configure>", self._redraw)

        # The clear button lives in the top-right corner of the box itself,
        # the way Google Translate does it, rather than as another control
        # in the row above. It is a real widget rather than something drawn
        # on the canvas because an embedded window (the Text) always covers
        # canvas items, so a drawn ✕ would be hidden behind the text.
        self.clear_button = None
        self._suppress_modified = False
        if on_clear is not None:
            self.clear_button = tk.Label(
                self.canvas, text="✕", bd=0, cursor="arrow",
                bg=palette["surface"], fg=palette["text_dim"],
                font=theme_mod.font(parent, 12))
            self.clear_button.bind("<Button-1>", lambda _e=None: on_clear())
            self.clear_button.bind(
                "<Enter>", lambda _e=None: self.clear_button.configure(
                    fg=palette["text"]))
            self.clear_button.bind(
                "<Leave>", lambda _e=None: self.clear_button.configure(
                    fg=palette["text_dim"]))
            self.text.bind("<<Modified>>", self._on_modified)
            self._sync_clear()

        # Delegate the Text API so callers can treat this as a Text widget.
        # `get`, `insert` and `delete` are wrapped rather than delegated
        # when there is a placeholder, because the placeholder is real
        # text in the widget: delegated straight through, every caller
        # that asks what the user typed is told "Type or paste text
        # here…" and the app translates its own hint.
        for name in ("see", "index", "tag_add", "tag_config", "edit_reset"):
            setattr(self, name, getattr(self.text, name))
        if not self.placeholder:
            for name in ("insert", "delete", "get"):
                setattr(self, name, getattr(self.text, name))

    # -- the Text API, with the empty state accounted for ---------------
    def get(self, *args):
        if self._showing_placeholder:
            return ""
        return self.text.get(*args)

    def insert(self, *args, **kwargs):
        if self._showing_placeholder:
            self._set_placeholder(False)
            try:
                self.text.delete("1.0", "end")
            except Exception:
                pass
        state = self.text.cget("state")
        try:
            self.text.configure(state="normal")
            self.text.insert(*args, **kwargs)
        finally:
            try:
                self.text.configure(state=state)
            except Exception:
                pass
        self._sync_placeholder()

    def delete(self, *args, **kwargs):
        state = self.text.cget("state")
        try:
            self.text.configure(state="normal")
            self.text.delete(*args, **kwargs)
        finally:
            try:
                self.text.configure(state=state)
            except Exception:
                pass
        self._sync_placeholder()

    # -- height that follows the content --------------------------------
    #
    # The boxes used to be given whatever height the window had, so two
    # words of translation sat in the middle of a very large white
    # rectangle. They start at a few lines now and grow with what is in
    # them, up to whatever the window can actually show.
    def line_px(self):
        try:
            font = tkfont.Font(font=self.text["font"])
            return font.metrics("linespace") + 6      # spacing1 + spacing3
        except Exception:
            return 22

    def chrome_px(self):
        """Everything in the box that is not a line of text."""
        return self.PAD_Y * 2 + self.INSET * 2 + 2

    def wanted_lines(self):
        """How many lines the content actually occupies, wrapping included."""
        try:
            count = self.text.count("1.0", "end-1c", "displaylines")
            lines = int(count[0]) if count else 0
        except Exception:
            lines = 0
        if self._showing_placeholder:
            return self.min_lines
        if not lines:
            body = self.text.get("1.0", "end-1c")
            lines = body.count("\n") + 1 if body else 0
        return max(self.min_lines, lines)

    def set_lines(self, lines):
        """Fix the box at a number of text lines."""
        lines = max(1, int(lines))
        if lines == self._lines:
            return
        self._lines = lines
        self.canvas.configure(height=lines * self.line_px() + self.chrome_px())

    # -- growing, for a box that must never scroll ----------------------
    def _cap(self, event=None):
        """Refuse the keystroke that would go past the limit."""
        if not self.limit:
            return None
        key = getattr(event, "keysym", "")
        if key in ("BackSpace", "Delete", "Left", "Right", "Up", "Down",
                   "Home", "End", "Prior", "Next", "Tab", "Escape",
                   "Shift_L", "Shift_R", "Control_L", "Control_R",
                   "Alt_L", "Alt_R", "Meta_L", "Meta_R", "Caps_Lock"):
            return None
        if getattr(event, "state", 0) & 0x0004:      # a control chord
            return None
        if not getattr(event, "char", ""):
            return None
        try:
            if len(self.text.get("1.0", "end-1c")) >= self.limit:
                # Any selection is about to be replaced, so what is there
                # now is not what will be there after.
                if not self.text.tag_ranges("sel"):
                    return "break"
        except Exception:
            pass
        return None

    def _trim(self):
        """Cut anything past the limit. Typing is stopped at the door;
        this is for what arrives by other means — a paste, a drop."""
        if not self.limit or self._showing_placeholder:
            return
        try:
            body = self.text.get("1.0", "end-1c")
            if len(body) <= self.limit:
                return
            was = self._suppress_modified
            self._suppress_modified = True
            self.text.delete("1.0 + %dc" % self.limit, "end-1c")
            self.text.edit_modified(False)
            self._suppress_modified = was
        except Exception:
            pass

    def _on_grown(self, _event=None):
        """Follow the content, so there is never anything out of sight."""
        if not self.grows:
            return
        self._trim()
        lines = self.wanted_lines()
        if self.max_lines:
            lines = min(lines, self.max_lines)
        self.set_lines(lines)

    def _on_modified(self, _event=None):
        """Tk's change notification, used to show or hide the ✕."""
        if self._suppress_modified:
            return
        self._suppress_modified = True
        try:
            self.text.edit_modified(False)
        except Exception:
            pass
        self._suppress_modified = False
        self._sync_clear()
        self._sync_placeholder()

    # -- the empty state ------------------------------------------------
    def _sync_placeholder(self):
        """Show the grey line when the box is empty, and only then."""
        if not self.placeholder:
            return
        try:
            body = self.text.get("1.0", "end-1c")
        except Exception:
            return
        if self._showing_placeholder:
            if body and body != self.placeholder:
                self._set_placeholder(False)
            return
        if not body:
            self._set_placeholder(True)

    def _set_placeholder(self, on):
        was = self._suppress_modified
        self._suppress_modified = True
        state = None
        try:
            state = self.text.cget("state")
            self.text.configure(state="normal")
            if on:
                self.text.delete("1.0", "end")
                self.text.insert("1.0", self.placeholder, "placeholder")
                self.text.mark_set("insert", "1.0")
            else:
                self.text.tag_remove("placeholder", "1.0", "end")
            self._showing_placeholder = on
            self.text.edit_modified(False)
        except Exception:
            pass
        finally:
            if state is not None:
                try:
                    self.text.configure(state=state)
                except Exception:
                    pass
            self._suppress_modified = was

    def _clear_placeholder(self, _event=None):
        """Typing into the box is what removes it."""
        if self._showing_placeholder:
            self._set_placeholder(False)
            try:
                self.text.delete("1.0", "end")
            except Exception:
                pass

    def _sync_clear(self):
        """Only offer to clear when there is something to clear."""
        if self.clear_button is None:
            return
        try:
            has_text = bool(self.text.get("1.0", "end-1c").strip())
        except Exception:
            has_text = False
        if has_text and not self._showing_placeholder:
            self.clear_button.place(relx=1.0, rely=0.0,
                                    x=-(SlimScrollbar.W + 20), y=10,
                                    anchor="ne")
            self.clear_button.lift()
        else:
            self.clear_button.place_forget()

    def _redraw(self, _event=None):
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if w < 4 or h < 4:
            return
        outline = self._outline or (self.palette["separator"]
                                    if self.palette["name"] == "light"
                                    else None)
        self._photo = set_plate(self.canvas, self._img_id, 0, 0, w, h,
                                self.radius, self._inner, outline)
        inset = 3
        self.canvas.coords(self._win, inset, inset)
        self.canvas.itemconfig(
            self._win, width=w - inset * 2 - SlimScrollbar.W,
            height=h - inset * 2)
        self.canvas.coords(self._scroll_win, w - SlimScrollbar.W - 6, 10)
        self.canvas.itemconfig(self._scroll_win, height=max(10, h - 20))


class SlimScrollbar(tk.Canvas):
    """A 6px capsule scrollbar that hides itself when there is nothing to
    scroll — Tk's own scrollbar has no styling worth the name."""

    W = 6

    def __init__(self, parent, palette, target):
        self.palette = palette
        self.target = target
        super().__init__(parent, width=self.W, highlightthickness=0, bd=0,
                         bg=palette["surface"])
        self._thumb = plate_item(self)
        self._photo = None
        self._first, self._last = 0.0, 1.0
        self._drag_from = None
        self.bind("<Configure>", lambda _e=None: self._draw())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag)

    def set(self, first, last):
        self._first, self._last = float(first), float(last)
        self._draw()

    def _draw(self):
        h = self.winfo_height()
        if h < 4:
            return
        span = self._last - self._first
        if span >= 0.999:
            self.itemconfig(self._thumb, state="hidden")
            return
        self.itemconfig(self._thumb, state="normal")
        thumb_h = max(28, int(h * span))
        y = int((h - thumb_h) * (self._first / max(1e-6, 1 - span)))
        colour = _blend(self.palette["text"], self.palette["surface"], 0.22)
        self._photo = set_plate(self, self._thumb, 0, y, self.W, thumb_h,
                                self.W // 2, colour)

    def _press(self, event):
        self._drag_from = event.y
        self._jump(event.y)

    def _drag(self, event):
        self._jump(event.y)

    def _jump(self, y):
        h = max(1, self.winfo_height())
        span = self._last - self._first
        fraction = max(0.0, min(1.0, (y / h) - span / 2))
        try:
            self.target.yview_moveto(fraction)
        except Exception:
            pass


class ScrollArea(tk.Frame):
    """Vertically scrollable region with the same slim capsule scrollbar."""

    def __init__(self, parent, palette, bg=None, fill_height=False,
                 show_bar=True):
        # `show_bar=False` scrolls with the wheel and trackpad only. For a
        # page laid out edge to edge, where a bar arriving takes its width
        # from the content and cuts the right-hand side off.
        # `fill_height` makes the content at least as tall as the view.
        #
        # A scrolling region normally hugs its contents, which is right
        # for a settings page: the cards are as tall as they are and the
        # rest is empty. It is wrong for a page whose middle is a pair of
        # boxes, because "expand into the space left over" then has no
        # space to expand into — enlarge the window and everything stays
        # pinned to the top with a band of nothing under it, which is the
        # exact complaint an earlier release was spent fixing.
        self.fill_height = fill_height
        self.palette = palette
        self._bg = bg or palette["window"]
        super().__init__(parent, bg=self._bg)
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0,
                                bg=self._bg)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=self._bg)
        self._win = self.canvas.create_window(0, 0, anchor="nw",
                                              window=self.body)
        self.scroll = SlimScrollbar(self, palette, self.canvas)
        self.scroll.configure(bg=self._bg)
        self.show_bar = show_bar
        if show_bar:
            self.scroll.pack(side="right", fill="y", padx=(6, 0))
        self._bar_shown = show_bar
        self.canvas.configure(yscrollcommand=self._scroll_set)


        self.body.bind("<Configure>", self._on_body)
        self.canvas.bind("<Configure>", self._on_canvas)
        # Do not wait for a <Configure> event to give the content its width.
        #
        # The content is a window item on a canvas, and a canvas window item
        # is as wide as it is told to be — nothing, until _on_canvas runs.
        # On macOS that event did not arrive until the user scrolled or
        # resized, so Settings opened as an empty page with a scrollbar and
        # only appeared once the mouse wheel was touched. Measuring once the
        # geometry has settled removes the dependency on an event that may
        # never come.
        self.after_idle(self._lay_out)
        for widget in (self.canvas, self.body):
            widget.bind("<MouseWheel>", self._wheel)
            widget.bind("<Button-4>", self._wheel)
            widget.bind("<Button-5>", self._wheel)
            bind_touchpad(widget, self._touchpad)

    def _scroll_set(self, first, last):
        """Take the gutter back when there is nothing to scroll.

        The bar already hid its thumb; what it kept was its width, and
        twelve pixels of page colour down the right of a photograph that
        is supposed to reach the edge of the window is not nothing. It
        cannot oscillate: hiding it makes the view wider, and a page
        that fitted a narrower view fits a wider one.
        """
        need = (float(last) - float(first)) < 0.999 and self.show_bar
        if need != self._bar_shown:
            self._bar_shown = need
            try:
                if need:
                    self.scroll.pack(side="right", fill="y", padx=(6, 0))
                else:
                    self.scroll.pack_forget()
            except Exception:
                pass
        self.scroll.set(first, last)

    def _lay_out(self):
        """Size the content to the canvas, without waiting to be told to."""
        try:
            self.canvas.update_idletasks()
            width = self.canvas.winfo_width()
            if width > 1:
                self.canvas.itemconfig(self._win, width=width)
            self._stretch()
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except Exception:
            pass

    def _stretch(self):
        """Give the content the view's height when it asks for less."""
        if not self.fill_height:
            return
        try:
            view = self.canvas.winfo_height()
            wanted = self.body.winfo_reqheight()
            if view > 1:
                self.canvas.itemconfig(self._win, height=max(view, wanted))
        except Exception:
            pass

    def _on_body(self, _event=None):
        self._stretch()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, event):
        self.canvas.itemconfig(self._win, width=event.width)
        self._stretch()

    def _wheel(self, event):
        """Scroll by what the wheel says, now.

        This used to add the notch to a target and ease towards it on a
        ten-millisecond timer. Eased scrolling is a lovely thing when it
        keeps up and a terrible one when it does not: the page lags the
        hand, the lag is worse the faster you scroll, and letting go
        leaves it still moving. That is what "sticky" was.

        A trackpad already sends a stream of small deltas — the easing is
        in the hand, not in the app — and a wheel notch is a jump on
        purpose. So the page moves the moment it is told to and stops
        when the hand stops.
        """
        step = 0.0
        if getattr(event, "num", None) == 4:
            step = -1.0
        elif getattr(event, "num", None) == 5:
            step = 1.0
        elif getattr(event, "delta", 0):
            # Windows reports multiples of 120; macOS reports small numbers.
            divisor = 120.0 if abs(event.delta) >= 120 else 3.0
            step = -event.delta / divisor
        if step:
            self._scroll_pixels(step * 72.0)
        return "break"

    def _touchpad(self, event):
        """A trackpad under Tk 9: pixels, already in the hand's direction."""
        _dx, dy = touchpad_deltas(self.canvas, event)
        if dy:
            self._scroll_pixels(-dy)
        return "break"

    def _scroll_pixels(self, pixels):
        box = self.canvas.bbox("all")
        if not box:
            return
        total = max(1, box[3] - box[1])
        try:
            first = self.canvas.yview()[0]
            self.canvas.yview_moveto(max(0.0, min(1.0,
                                                  first + pixels / total)))
        except Exception:
            pass

    def bind_wheel_recursive(self, widget=None):
        """Tk delivers wheel events to the widget under the pointer, so every
        child has to forward them for scrolling to feel normal."""
        widget = widget or self.body
        for child in widget.winfo_children():
            for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                try:
                    child.bind(sequence, self._wheel)
                except Exception:
                    pass
            bind_touchpad(child, self._touchpad)
            self.bind_wheel_recursive(child)


class ProgressBar(tk.Canvas):
    """Capsule progress track. One drawn bar for the whole app — file
    translation progress and a language-pack install both use this
    rather than each growing its own."""

    def __init__(self, parent, palette, height=5):
        self.palette = palette
        self._h = height
        self._value = 0.0
        super().__init__(parent, height=height, highlightthickness=0, bd=0,
                         bg=palette["window"])
        self._track = plate_item(self)
        self._fill = plate_item(self)
        self._tp = self._fp = None
        self.bind("<Configure>", lambda _e=None: self._draw())

    def set(self, fraction):
        self._value = max(0.0, min(1.0, float(fraction)))
        self._draw()

    def _visible(self):
        return 0.0 < self._value < 1.0 or self._value == 1.0

    def _draw(self):
        w = self.winfo_width()
        if w < 4:
            return
        if self._value <= 0.0:
            self.itemconfig(self._track, state="hidden")
            self.itemconfig(self._fill, state="hidden")
            return
        self._tp = set_plate(self, self._track, 0, 0, w, self._h,
                             self._h // 2, self.palette["track"])
        self.itemconfig(self._track, state="normal")
        filled = int(w * self._value)
        if filled >= 4:
            self._fp = set_plate(self, self._fill, 0, 0, filled, self._h,
                                 self._h // 2, self.palette["accent"])
            self.itemconfig(self._fill, state="normal")
        else:
            self.itemconfig(self._fill, state="hidden")


def divider(parent, palette, bg=None):
    return tk.Frame(parent, bg=palette["separator"], height=1,
                    bd=0, highlightthickness=0)


def label(parent, palette, text, size=10, weight="normal", dim=False,
          bg=None, display=False, **kwargs):
    return tk.Label(
        parent, text=text, bd=0,
        bg=bg or palette["window"],
        fg=palette["text_dim"] if dim else palette["text"],
        font=theme_mod.font(parent, size, weight, display), **kwargs)
