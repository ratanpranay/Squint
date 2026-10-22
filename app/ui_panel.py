"""The small panel that opens from the menu-bar icon (macOS) or the tray
icon (Windows).

The icon used to open a plain menu: two actions, a language list three
levels deep, Open, Quit. The panel puts the everyday things one click
away instead - Snip and Text as two big buttons with their shortcuts on
them, the language translations go into, and whether offline translation
is ready - and Settings behind the gear. The old menu is still there on a
right click.

Drawn on one canvas, so the buttons are the same shape on both systems:
rounded and under the icon on a Mac, square-cornered with a thin border
above the taskbar on Windows (Windows 11 rounds the window itself).
Clicking anywhere else, or Esc, closes it; clicking the icon again does
too.
"""
import sys
import time
import tkinter as tk

from . import theme as theme_mod
from .ui_kit import VECTOR_PLATES, _blend, plate_item, set_plate

IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"

WIDTH = 300
PAD = 14
GAP = 10
TILE_H = 76
ROW_H = 28
RADIUS = 14 if IS_MAC else 0
TILE_RADIUS = 12 if IS_MAC else 6
PICK_RADIUS = 8 if IS_MAC else 4
# How often the status line is read again while the panel is open: the
# offline model's download moves while somebody watches it.
STATUS_EVERY = 1000
# A click on the icon while the panel is open closes it on the way down
# (the click watcher) and would open it again on the way up (the icon's
# own action). Inside this many seconds of a close, the icon only closes.
REOPEN_GUARD = 0.4
# Nothing closes the panel for this long after it opens: the click that
# opened it is still on its way up.
ARM_AFTER = 250


# -- icons -------------------------------------------------------------
#
# Each icon is one drawing, in points inside its own box, drawn two ways:
# as canvas shapes on a Mac, where the canvas goes through CoreGraphics
# (smoothed, and at the screen's own resolution, so sharp on Retina), and
# as a picture drawn four times larger and scaled down everywhere else,
# where Tk's canvas does not smooth anything and a diagonal or a curve is
# a staircase. The same choice ui_kit makes for its rounded shapes.
#
# Shapes: ("line", points, width, round_ends), ("poly", points),
# ("dot", cx, cy, r) and ("hole", cx, cy, r) - a hole is cut out of what
# is drawn before it.

SS = 4


def _dashes(x0, y0, x1, y1, dash=3.2, gap=2.2):
    """The sides of a box as dashes, a whole dash on every corner."""
    out = []
    for ax, ay, bx, by in ((x0, y0, x1, y0), (x1, y0, x1, y1),
                           (x1, y1, x0, y1), (x0, y1, x0, y0)):
        length = abs(bx - ax) + abs(by - ay)
        n = max(2, int(round((length + gap) / (dash + gap))))
        d = (length - (n - 1) * gap) / float(n)
        for i in range(n):
            t0 = i * (d + gap) / length
            t1 = (i * (d + gap) + d) / length
            out.append(("line", (ax + (bx - ax) * t0, ay + (by - ay) * t0,
                                 ax + (bx - ax) * t1, ay + (by - ay) * t1),
                        2.0, False))
    return out


def _gear(cx, cy, outer=8.0, inner=6.0, teeth=8, hole=2.6):
    import math
    points = []
    step = 2 * math.pi / teeth
    for i in range(teeth):
        a = i * step - math.pi / 2
        # A tooth: flat top, sloped sides.
        for da, r in ((-0.30, inner), (-0.17, outer), (0.17, outer),
                      (0.30, inner)):
            points += [cx + r * math.cos(a + da * step * 1.6),
                       cy + r * math.sin(a + da * step * 1.6)]
    return [("poly", tuple(points)), ("hole", cx, cy, hole)]


ICONS = {
    # A selection being drawn: a dashed box.
    "snip": ((24, 18), _dashes(1.0, 1.0, 23.0, 17.0)),
    # A paragraph: three lines, the last one short.
    "text": ((24, 16), [("line", (1.0, y, x, y), 2.2, True)
                        for y, x in ((2.0, 23.0), (8.0, 23.0),
                                     (14.0, 14.0))]),
    "arrow": ((16, 10), [("line", (1.0, 5.0, 11.0, 5.0), 1.5, True),
                         ("poly", (9.0, 1.2, 15.0, 5.0, 9.0, 8.8))]),
    "chevron": ((10, 6), [("line", (1.0, 1.0, 5.0, 5.0, 9.0, 1.0), 1.6,
                           True)]),
    "gear": ((18, 18), _gear(9.0, 9.0)),
    "dot": ((8, 8), [("dot", 4.0, 4.0, 4.0)]),
}


def icon_image(kind, colour, scale=1.0, cache={}):
    """The icon as an RGBA picture at `scale` pixels to the point, smoothed:
    drawn SS times larger as a mask and scaled down."""
    key = (kind, colour, round(scale, 3))
    hit = cache.get(key)
    if hit is not None:
        return hit
    from PIL import Image, ImageDraw
    (w, h), shapes = ICONS[kind]
    out_w = max(1, int(round(w * scale)))
    out_h = max(1, int(round(h * scale)))
    k = scale * SS
    mask = Image.new("L", (out_w * SS, out_h * SS), 0)
    draw = ImageDraw.Draw(mask)
    for shape in shapes:
        kind_ = shape[0]
        if kind_ == "line":
            pts, width, round_ends = shape[1], shape[2], shape[3]
            xy = [v * k for v in pts]
            draw.line(xy, fill=255, width=max(1, int(round(width * k))),
                      joint="curve")
            if round_ends:
                r = width * k / 2.0
                for x, y in ((xy[0], xy[1]), (xy[-2], xy[-1])):
                    draw.ellipse([x - r, y - r, x + r, y + r], fill=255)
        elif kind_ == "poly":
            draw.polygon([v * k for v in shape[1]], fill=255)
        elif kind_ in ("dot", "hole"):
            cx, cy, r = shape[1] * k, shape[2] * k, shape[3] * k
            draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                         fill=255 if kind_ == "dot" else 0)
    mask = mask.resize((out_w, out_h), Image.LANCZOS)
    rgb = tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))
    img = Image.new("RGBA", (out_w, out_h), rgb + (0,))
    img.putalpha(mask)
    if len(cache) > 120:
        cache.clear()
    cache[key] = img
    return img


def _work_area(widget):
    """The screen minus the taskbar, (x0, y0, x1, y1), on Windows; None
    elsewhere."""
    if not IS_WINDOWS:
        return None
    try:
        import ctypes
        from ctypes import wintypes
        rect = wintypes.RECT()
        # SPI_GETWORKAREA
        if ctypes.windll.user32.SystemParametersInfoW(
                0x0030, 0, ctypes.byref(rect), 0):
            return rect.left, rect.top, rect.right, rect.bottom
    except Exception:
        pass
    return None


def _windows_monitor(point):
    """((x0, y0, x1, y1) of the whole monitor, (x0, y0, x1, y1) of its work
    area) for the monitor under `point` - or the pointer when `point` is
    None - in the screen's own pixels; (None, None) elsewhere."""
    if not IS_WINDOWS:
        return None, None
    try:
        import ctypes
        from ctypes import wintypes

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD),
                        ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT),
                        ("dwFlags", wintypes.DWORD)]
        user32 = ctypes.windll.user32
        if point is None:
            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
        else:
            pt = wintypes.POINT(int(point[0]), int(point[1]))
        user32.MonitorFromPoint.restype = wintypes.HMONITOR
        monitor = user32.MonitorFromPoint(pt, 2)     # MONITOR_DEFAULTTONEAREST
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None, None
        m, w = info.rcMonitor, info.rcWork
        return ((m.left, m.top, m.right, m.bottom),
                (w.left, w.top, w.right, w.bottom))
    except Exception:
        return None, None


def _windows_cursor():
    try:
        import ctypes
        from ctypes import wintypes
        pt = wintypes.POINT()
        if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
            return pt.x, pt.y
    except Exception:
        pass
    return None


def _windows_rect(window):
    """(hwnd, (x0, y0, x1, y1)) of the window as Windows has it."""
    try:
        import ctypes
        from ctypes import wintypes
        from . import win_effects
        hwnd = win_effects.hwnd_for(window)
        rect = wintypes.RECT()
        if hwnd and ctypes.windll.user32.GetWindowRect(hwnd,
                                                       ctypes.byref(rect)):
            return hwnd, (rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        pass
    return None, None


def _windows_move(hwnd, x, y):
    try:
        import ctypes
        # SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
        ctypes.windll.user32.SetWindowPos(hwnd, 0, int(x), int(y), 0, 0,
                                          0x0001 | 0x0004 | 0x0010)
        return True
    except Exception:
        return False


def place(width, height, pointer, screen, anchor=None, work=None):
    """Where the panel goes: (x, y).

    `anchor` is the icon's box (x0, y0, x1, y1) when it is known - on a
    Mac, under the icon. Otherwise near the pointer, which has just
    clicked the icon: above it when the icon is in the bottom half of the
    screen (a taskbar at the bottom), below it otherwise. Always kept on
    the screen (`screen` is (x0, y0, x1, y1)), and off the taskbar
    (`work`, the same shape) when that is known.
    """
    sx0, sy0, sx1, sy1 = screen
    margin = 8
    if anchor is not None:
        ax0, _ay0, ax1, ay1 = anchor
        x = (ax0 + ax1) / 2.0 - width / 2.0
        y = ay1 + 6
    else:
        px, py = pointer
        x = px - width / 2.0
        if py > (sy0 + sy1) / 2.0:
            y = py - height - 18
            if work is not None and py >= work[3]:
                y = work[3] - height - 12
        else:
            y = py + 18
            if work is not None and py <= work[1]:
                y = work[1] + 12
    x = max(sx0 + margin, min(x, sx1 - width - margin))
    y = max(sy0 + margin, min(y, sy1 - height - margin))
    return int(round(x)), int(round(y))


class MiniPanel(tk.Toplevel):
    """The panel. One at a time: see `toggle`.

    Everything it does is handed in, so it knows nothing of the app:
    `on_snip()`, `on_text()`, `on_language(code)`, `on_settings()`;
    `language` is the current target's code, `keys` the two shortcuts as
    they are shown (snip, text), and `status()` returns (text, colour
    name in the palette) for the line at the bottom.
    """

    _current = None
    _closed_at = 0.0

    def __init__(self, master, palette, on_snip, on_text, on_language,
                 on_settings, language="en", keys=("", ""), status=None,
                 anchor=None, languages=None):
        super().__init__(master)
        self.palette = palette
        self.on_snip, self.on_text = on_snip, on_text
        self.on_language, self.on_settings = on_language, on_settings
        self.language = language
        self.keys = keys
        self.status = status or (lambda: ("", "text_dim"))
        self.languages = languages
        self._menu_open = False
        self._closed = False
        self._armed = False
        self._job = None
        self._hover = None
        self._photos = {}
        self.scale = 1.0
        if IS_WINDOWS:
            try:
                self.scale = max(1.0, float(self.winfo_fpixels("1i")) / 96.0)
            except Exception:
                self.scale = 1.0

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self._bg = palette["window"]
        corner = self._see_through()
        self.configure(bg=corner)
        width, height = self.px(WIDTH), self.px(self._height())
        self.canvas = tk.Canvas(self, width=width, height=height,
                                highlightthickness=0, bd=0, bg=corner)
        self.canvas.pack(fill="both", expand=True)
        self.width, self.height = width, height
        self._draw()
        self.update_idletasks()
        self._place(anchor)
        if IS_WINDOWS:
            # Windows 11 rounds the window and draws its own thin border
            # round it; the panel's own border is then left off, so there
            # are not two. Windows 10 keeps square corners and this one.
            try:
                from . import win_effects
                if win_effects.round_corners(self, "round"):
                    self._system_border = True
                    self._draw()
            except Exception:
                pass

        self.bind("<Escape>", lambda _e: self.close())
        self.canvas.bind("<Escape>", lambda _e: self.close())
        from . import click_watch
        self._watch = click_watch.Watcher(self, self._clicked_anywhere)
        self.after(ARM_AFTER, self._arm)
        self.after(30, self._focus)
        self._job = self.after(STATUS_EVERY, self._tick)
        MiniPanel._current = self

    # -- sizes ---------------------------------------------------------
    def px(self, value):
        return int(round(value * self.scale))

    @staticmethod
    def _height():
        return PAD + TILE_H + 12 + ROW_H + 8 + ROW_H + 10

    def font(self, size, weight=400):
        family, tk_weight = theme_mod.ui_family(weight, self)
        return (family, -max(6, self.px(size)), tk_weight)

    def _see_through(self):
        """The colour round the panel's rounded corners: the screen behind
        on a Mac where Tk can do that, the panel's own colour elsewhere."""
        if IS_MAC and float(tk.TkVersion) < 9.0:
            try:
                self.attributes("-transparent", True)
                return "systemTransparent"
            except Exception:
                pass
        return self._bg

    # -- drawing -------------------------------------------------------
    def _draw(self):
        c, p, px = self.canvas, self.palette, self.px
        c.delete("all")
        self._photos = {}
        w, h = self.width, self.height
        border = p["window"] if getattr(self, "_system_border", False) \
            else _blend(p["text"], p["window"], 0.16)
        plate = plate_item(c)
        self._photos["plate"] = set_plate(c, plate, 0, 0, w, h,
                                          px(RADIUS) or 1, p["window"],
                                          border)
        tile_w = (WIDTH - 2 * PAD - GAP) / 2.0
        top = PAD
        tiles = (("snip", "Snip", self.keys[0]),
                 ("text", "Text", self.keys[1]))
        for i, (name, label, key) in enumerate(tiles):
            x0 = PAD + i * (tile_w + GAP)
            self._tile(name, x0, top, tile_w, TILE_H, label, key)

        y = top + TILE_H + 12
        # Drawn rather than typed: an arrow, a chevron and a gear are not
        # in every system font, and a missing one prints as a box.
        mid = px(y + ROW_H / 2.0)
        label = c.create_text(px(PAD + 2), mid, anchor="w", text="Auto",
                              fill=p["text_dim"], font=self.font(13))
        ax = c.bbox(label)[2] + px(8)
        self._icon("arrow", ax + px(8), mid, p["text_dim"])
        self._pick(y)

        y += ROW_H + 8
        self._status_row(y)
        for tag in ("snip", "text", "pick", "gear"):
            c.tag_bind(tag, "<Enter>", lambda _e, t=tag: self._hover_on(t))
            c.tag_bind(tag, "<Leave>", lambda _e, t=tag: self._hover_on(None))
        c.tag_bind("snip", "<ButtonRelease-1>", lambda _e: self._do("snip"))
        c.tag_bind("text", "<ButtonRelease-1>", lambda _e: self._do("text"))
        c.tag_bind("pick", "<ButtonRelease-1>", lambda _e: self._pick_menu())
        c.tag_bind("gear", "<ButtonRelease-1>",
                   lambda _e: self._do("settings"))

    def _tile(self, name, x0, y0, w, h, label, key):
        c, p, px = self.canvas, self.palette, self.px
        fill = p["surface"]
        outline = None if IS_MAC else _blend(p["text"], p["surface"], 0.12)
        item = plate_item(c, tags=(name, name + "_bg"))
        self._photos[name] = set_plate(c, item, px(x0), px(y0), px(w),
                                       px(h), px(TILE_RADIUS), fill,
                                       outline or fill)
        cx = x0 + w / 2.0
        accent = p["accent"]
        self._icon(name, px(cx), px(y0 + 21), accent, tags=(name,),
                   hole_fill=fill)
        c.create_text(px(cx), px(y0 + 44), text=label, fill=p["text"],
                      font=self.font(15, 600), tags=(name,))
        c.create_text(px(cx), px(y0 + 62), text=key, fill=p["text_dim"],
                      font=self.font(12), tags=(name, name + "_key"))

    def _language_name(self):
        from .langs import name_for
        return name_for(self.language)

    def _pick(self, y):
        c, p, px = self.canvas, self.palette, self.px
        text = self._language_name()
        font = self.font(13)
        try:
            import tkinter.font as tkfont
            text_w = tkfont.Font(root=self, font=font).measure(text)
        except Exception:
            text_w = px(8 * len(text))
        box_w = text_w + px(36)
        x1 = px(WIDTH - PAD)
        x0 = x1 - box_w
        y0, y1 = px(y + 1), px(y + ROW_H - 1)
        fill = p["surface"]
        outline = _blend(p["text"], p["surface"], 0.18)
        item = plate_item(c, tags=("pick", "pick_bg"))
        self._photos["pick"] = set_plate(c, item, x0, y0, box_w, y1 - y0,
                                         px(PICK_RADIUS), fill, outline)
        cy = (y0 + y1) / 2.0
        c.create_text(x0 + px(10), cy, anchor="w", text=text,
                      fill=p["text"], font=font, tags=("pick", "pick_text"))
        self._icon("chevron", x1 - px(15), cy, p["text_dim"],
                   tags=("pick",))
        self._pick_box = (x0, y0, x1, y1)

    def _status_row(self, y):
        c, p, px = self.canvas, self.palette, self.px
        text, colour = self._status()
        mid = px(y + ROW_H / 2.0)
        r = px(4)
        x = px(PAD + 2)
        self._dot_colour = p.get(colour, p["text_dim"])
        self._icon("dot", x + r, mid, self._dot_colour)
        c.create_text(x + 2 * r + px(7), mid, anchor="w", text=text,
                      fill=p["text_dim"], font=self.font(13),
                      tags=("status_text",))
        gx = px(WIDTH - PAD - 12)
        # A hit area larger than the glyph, so the gear is easy to click.
        c.create_rectangle(gx - px(14), mid - px(13), gx + px(14),
                           mid + px(13), fill=p["window"], outline="",
                           tags=("gear", "gear_bg"))
        self._icon("gear", gx, mid, p["text_dim"], tags=("gear",))

    def _icon(self, kind, cx, cy, colour, tags=(), hole_fill=None):
        """Put icon `kind` centred on (cx, cy), canvas pixels. Its items
        all carry the tag "icon_<kind>" so its colour can be changed."""
        c = self.canvas
        tags = tuple(tags) + ("icon_" + kind,)
        (w, h), shapes = ICONS[kind]
        if not VECTOR_PLATES:
            photo = __import__("PIL.ImageTk", fromlist=["ImageTk"]) \
                .PhotoImage(icon_image(kind, colour, self.scale),
                            master=self)
            self._photos["icon_" + kind] = photo
            c.create_image(int(round(cx)), int(round(cy)), image=photo,
                           anchor="center", tags=tags)
            return
        s = self.scale
        ox, oy = cx - w * s / 2.0, cy - h * s / 2.0

        def at(pts):
            return [ox + v * s if i % 2 == 0 else oy + v * s
                    for i, v in enumerate(pts)]
        for shape in shapes:
            if shape[0] == "line":
                c.create_line(*at(shape[1]), fill=colour,
                              width=shape[2] * s,
                              capstyle="round" if shape[3] else "butt",
                              joinstyle="round", tags=tags + ("ink",))
            elif shape[0] == "poly":
                c.create_polygon(*at(shape[1]), fill=colour, outline="",
                                 tags=tags + ("ink",))
            else:
                x, y = at((shape[1], shape[2]))
                r = shape[3] * s
                fill = colour if shape[0] == "dot" else \
                    (hole_fill or self.palette["window"])
                c.create_oval(x - r, y - r, x + r, y + r, fill=fill,
                              outline="", tags=tags + (
                                  "ink" if shape[0] == "dot" else "hole",))

    def _recolour(self, kind, colour):
        """Icon `kind` in a new colour (the gear on hover, the dot when the
        status changes)."""
        c = self.canvas
        items = c.find_withtag("icon_" + kind)
        if not items:
            return
        if not VECTOR_PLATES:
            from PIL import ImageTk
            photo = ImageTk.PhotoImage(icon_image(kind, colour, self.scale),
                                       master=self)
            self._photos["icon_" + kind] = photo
            for item in items:
                c.itemconfigure(item, image=photo)
            return
        for item in items:
            if "ink" in c.gettags(item):
                c.itemconfigure(item, fill=colour)

    def _status(self):
        try:
            text, colour = self.status()
            return str(text or ""), colour or "text_dim"
        except Exception:
            return "", "text_dim"

    def _hover_on(self, tag):
        if tag == self._hover:
            return
        p = self.palette
        for name in ("snip", "text", "pick"):
            fill = p["surface_hi"] if name == tag else p["surface"]
            self._refill(name, fill)
        self._recolour("gear",
                       p["text"] if tag == "gear" else p["text_dim"])
        self._hover = tag
        try:
            self.canvas.configure(cursor="hand2" if tag else "")
        except Exception:
            pass

    def _refill(self, name, fill):
        """A new fill for a tile or the picker, keeping its shape."""
        c, px = self.canvas, self.px
        item = c.find_withtag(name + "_bg")
        if not item:
            return
        item = item[0]
        if c.type(item) == "polygon":
            c.itemconfigure(item, fill=fill)
            if IS_MAC and name != "pick":
                c.itemconfigure(item, outline=fill)
            return
        x0, y0, x1, y1 = c.bbox(item)
        p = self.palette
        if name == "pick":
            outline = _blend(p["text"], p["surface"], 0.18)
            radius = px(PICK_RADIUS)
        else:
            outline = None if IS_MAC else _blend(p["text"], p["surface"],
                                                 0.12)
            radius = px(TILE_RADIUS)
        self._photos[name] = set_plate(c, item, x0, y0, x1 - x0, y1 - y0,
                                       radius, fill, outline or fill)

    # -- life ----------------------------------------------------------
    def _place(self, anchor):
        try:
            pointer = (self.winfo_pointerx(), self.winfo_pointery())
        except Exception:
            pointer = (0, 0)
        try:
            vx, vy = self.winfo_vrootx(), self.winfo_vrooty()
            vw, vh = self.winfo_vrootwidth(), self.winfo_vrootheight()
        except Exception:
            vx = vy = 0
            vw, vh = self.winfo_screenwidth(), self.winfo_screenheight()
        x, y = place(self.width, self.height, pointer,
                     (vx, vy, vx + vw, vy + vh), anchor, _work_area(self))
        self.geometry("%dx%d+%d+%d" % (self.width, self.height, x, y))
        if IS_WINDOWS:
            # Tk's pointer and screen sizes are not always the screen's own
            # pixels (scaling, a second monitor, a taskbar on another
            # side), and the panel came out partly below the bottom of
            # the screen. Placed again from what Windows itself reports:
            # the pointer, the monitor it is on, that monitor's work area,
            # and the window's real size - and once more after it is shown.
            self._place_windows(anchor)
            self.after(60, lambda: self._place_windows(anchor))

    def _place_windows(self, anchor=None):
        if self._closed:
            return
        try:
            self.update_idletasks()
        except Exception:
            return
        hwnd, rect = _windows_rect(self)
        if not hwnd:
            return
        width, height = rect[2] - rect[0], rect[3] - rect[1]
        if width <= 1 or height <= 1:
            return
        if not hasattr(self, "_win_pointer"):
            self._win_pointer = _windows_cursor()
        pointer = self._win_pointer
        if pointer is None:
            return
        screen, work = _windows_monitor(pointer)
        if screen is None:
            return
        x, y = place(width, height, pointer, screen, None, work)
        # Kept inside the work area: never under the taskbar.
        x = max(work[0] + 8, min(x, work[2] - width - 8))
        y = max(work[1] + 8, min(y, work[3] - height - 8))
        if (x, y) != (rect[0], rect[1]):
            _windows_move(hwnd, x, y)

    def _focus(self):
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _arm(self):
        if self._closed:
            return
        self._armed = True
        try:
            self._watch.start()
        except Exception:
            pass

    def _tick(self):
        """The status line, read again."""
        self._job = None
        if self._closed:
            return
        try:
            text, colour = self._status()
            p = self.palette
            self.canvas.itemconfigure("status_text", text=text)
            dot = p.get(colour, p["text_dim"])
            if dot != getattr(self, "_dot_colour", None):
                self._dot_colour = dot
                self._recolour("dot", dot)
        except Exception:
            return
        self._job = self.after(STATUS_EVERY, self._tick)

    def _clicked_anywhere(self):
        if not self._armed or self._menu_open or self._closed:
            return
        try:
            x, y = self.winfo_pointerx(), self.winfo_pointery()
            left, top = self.winfo_rootx(), self.winfo_rooty()
            if (left <= x <= left + self.winfo_width()
                    and top <= y <= top + self.winfo_height()):
                return
        except Exception:
            return
        self.close()

    def _do(self, what):
        """A button: the panel goes first, so nothing of it is on the
        screen a snip reads or in front of the text being copied."""
        action = {"snip": self.on_snip, "text": self.on_text,
                  "settings": self.on_settings}.get(what)
        master = self.master
        self.close()
        if action is None:
            return
        try:
            master.after(120 if what != "settings" else 0, action)
        except Exception:
            pass

    def _pick_menu(self):
        """The languages: the usual ones, then all of them."""
        from .langs import TARGET_LANGUAGES, name_for, target_choices
        from .tray import QUICK_LANGS
        p = self.palette
        menu = tk.Menu(self, tearoff=0)
        if not IS_MAC:
            menu.configure(bg=p["surface"], fg=p["text"],
                           activebackground=p["accent"],
                           activeforeground=p["accent_text"])
        self._lang_var = tk.StringVar(self, value=self.language)
        quick = [c for c in (self.languages or QUICK_LANGS)
                 if c in TARGET_LANGUAGES]
        if self.language not in quick and self.language in TARGET_LANGUAGES:
            quick = [self.language] + quick
        for code in quick:
            menu.add_radiobutton(label=name_for(code), value=code,
                                 variable=self._lang_var,
                                 command=lambda c=code: self.choose(c))
        more = tk.Menu(menu, tearoff=0)
        for code, name in target_choices():
            more.add_radiobutton(label=name, value=code,
                                 variable=self._lang_var,
                                 command=lambda c=code: self.choose(c))
        menu.add_separator()
        menu.add_cascade(label="More languages", menu=more)
        self._menu = menu
        x0, _y0, _x1, y1 = self._pick_box
        self._menu_open = True
        try:
            menu.tk_popup(self.winfo_rootx() + int(x0),
                          self.winfo_rooty() + int(y1) + 2)
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass
            # Mac and Windows return from tk_popup when the menu has
            # closed; the click that closed it is let go before the
            # panel listens for clicks again.
            self.after(300, self._menu_closed)

    def _menu_closed(self):
        self._menu_open = False

    def choose(self, code):
        """A language was picked: it is the target now, and the panel
        says so."""
        self._menu_open = False
        if not code or code == self.language:
            return
        self.language = code
        try:
            self.on_language(code)
        except Exception:
            pass
        if not self._closed:
            self._draw()
            self._hover = None

    def close(self):
        if self._closed:
            return
        self._closed = True
        MiniPanel._closed_at = time.monotonic()
        if MiniPanel._current is self:
            MiniPanel._current = None
        try:
            self._watch.stop()
        except Exception:
            pass
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
        try:
            self.destroy()
        except Exception:
            pass

    # -- the icon ------------------------------------------------------
    @classmethod
    def is_open(cls):
        panel = cls._current
        try:
            return bool(panel is not None and panel.winfo_exists())
        except Exception:
            return False

    @classmethod
    def toggle(cls, master, palette, **kwargs):
        """What a click on the icon does: open the panel, or close it if
        it is open. Returns the panel, or None when it closed."""
        if cls.is_open():
            cls._current.close()
            return None
        if time.monotonic() - cls._closed_at < REOPEN_GUARD:
            # This click on the icon has just closed it.
            return None
        return cls(master, palette, **kwargs)


def status_line(config=None):
    """The panel's bottom line: (text, palette colour name)."""
    from . import offline_model
    from .config import CONFIG
    cfg = config or CONFIG
    try:
        state = offline_model.download_state()
    except Exception:
        state = {}
    kind = state.get("state")
    if kind in ("downloading", "updating"):
        total = float(state.get("total") or 0)
        done = float(state.get("done") or 0)
        if total > 1:
            return ("Getting offline model… %d%%"
                    % int(100 * min(1.0, done / total)), "warning")
        return "Getting offline model…", "warning"
    try:
        if offline_model.ready():
            return "Offline ready", "success"
    except Exception:
        pass
    if kind == "paused" and cfg.get("offline_enabled", False):
        return "Offline model paused", "warning"
    if kind == "failed" and cfg.get("offline_enabled", False):
        return "Offline model did not download", "danger"
    return "Online translation", "accent"
