"""The ring, and the one panel beside it where every tool shows its options,
settings, progress, calendar, QR status or camera. Nothing opens a window
of its own while the ring is up.

The ring is drawn on a canvas covering the monitor under the mouse. On
Windows the canvas background is a colour the window treats as
transparent, so only the ring and the panel are visible and the rest of
the screen stays clickable.

The panel is a real Tk frame placed on the canvas. It shows one view at a
time:
  list      a tool's actions, drawn as pills that bloom out of the ring
            beside the tool (the panel itself is hidden)
  calendar  shown on hover, hidden once the mouse has left it
  pinned    anything the user is in the middle of: settings, progress, the
            QR code, the camera. Hovering does not switch away from it and
            losing focus does not close the ring; Esc or ✕ goes back.
"""
import math
import sys
import tkinter as tk
import tkinter.font as tkfont

from . import common, icons

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
KEY = "#010203"                 # the see-through colour

RING_BG = "#181B22"
ITEM_BG = "#262A33"
ITEM_LINE = "#3A404C"
HUB_BG = "#11131A"
HEART = "#F0506E"

# The ring follows the system: light glass in light mode, dark in dark.
# (The panel beside it stays dark in both.)
DARK = {"glass": "#181B22", "glass_mix": 0.72, "ring_line": "#4A505C",
        "item": "#262A33", "item_line": "#3A404C", "label": "#E6E9EF",
        "title": "#FFFFFF", "sub": "#B9C0CC", "agenda": "#F2C94C",
        "pill": "#262A33", "pill_line": "#4A505C", "pill_text": "#FFFFFF",
        "pill_key": "#8A93A3", "pill_quiet": "#1E2129",
        "quiet_text": "#B9C0CC", "card": (17, 19, 26, 235),
        "card_text": "#C9CED8", "heart": "#C8546A"}
LIGHT = {"glass": "#FFFFFF", "glass_mix": 0.62, "ring_line": "#D9DDE5",
         "item": "#FFFFFF", "item_line": "#E3E6EC", "label": "#2A2F3A",
         "title": "#1E2129", "sub": "#6B7280", "agenda": "#B7791F",
         "pill": "#FFFFFF", "pill_line": "#E1E4EA", "pill_text": "#1E2129",
         "pill_key": "#9CA3AF", "pill_quiet": "#F3F4F7",
         "quiet_text": "#4B5563", "card": (255, 255, 255, 235),
         "card_text": "#4B5563", "heart": "#E0506E"}


class RadialMenu:
    current = None

    def __init__(self, ctrl, tools, front=None, support_url="",
                 shortcut="Alt + Space"):
        RadialMenu.current = self
        self.ctrl = ctrl
        self.tools = tools
        self.front = front
        self.support_url = support_url
        self.shortcut = shortcut
        self.selected = None        # nothing until the mouse picks a tool
        self.closed = False
        self.pinned = False
        self.card = None
        self.view = None
        self.hub_qr = None
        self.hub_cam = False      # the camera in the middle (Selfie check)
        self._cam_photo = None
        self.heart_hover = False
        self._cleanups = []
        self._away = 0
        self._engaged = False

        root = ctrl.root
        px, py = root.winfo_pointerxy()
        self.mon = mon = self._monitor(px, py) or (
            0, 0, root.winfo_screenwidth(), root.winfo_screenheight())
        scale = 1.0
        try:
            from .. import platform_util
            scale = (platform_util.monitor_scaling(px, py) or 100) / 100.0
        except Exception:
            pass
        self.s = s = max(1.0, scale)
        left, top, width, height = mon
        self.th = LIGHT if common.system_light() else DARK
        self.bloom = []             # (x0, y0, x1, y1, j) of the action pills
        self._bloom_hover = None
        self._clock_text = None

        margin = 215 * s
        self.cx = min(max(px - left, margin), width - margin)
        # Room above the ring for the support line.
        self.cy = min(max(py - top, margin + 40 * s), height - margin)
        # Taken before the window exists, so the ring is not in it.
        self._glass_tone = None
        self._glass = self._backdrop()
        # Panels, cards, toasts: the same light or dark as the ring, and
        # the panel in the tone of the glass.
        common.apply_theme(self.th is LIGHT, self._glass_tone)

        win = self.win = tk.Toplevel(root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.geometry("%dx%d+%d+%d" % (width, height, left, top))
        bg = KEY if IS_WINDOWS else "#0B0D11"
        if IS_WINDOWS:
            win.configure(bg=bg)
            win.attributes("-transparentcolor", KEY)
        elif IS_MAC and float(tk.TkVersion) < 9.0:
            # Tk 8.6 on a Mac: only what is drawn shows. (Tk 9 paints
            # "systemTransparent" black; it gets the dimmed screen below.)
            try:
                win.attributes("-transparent", True)
                bg = "systemTransparent"
            except tk.TclError:
                pass
            win.configure(bg=bg)
        else:
            win.configure(bg=bg)
            try:
                win.attributes("-alpha", 0.95)
            except tk.TclError:
                pass
        self.canvas = tk.Canvas(win, width=width, height=height, bg=bg,
                                highlightthickness=0, bd=0)
        self.canvas.pack()


        # The panel: a frame on a rounded card drawn on the canvas. The
        # card reaches a little past the frame on every side, so its round
        # corners show and the frame's square ones are inside it.
        self.panel_outer = tk.Frame(self.canvas, bg=common.PANEL)
        self.panel = tk.Frame(self.panel_outer, bg=common.PANEL,
                              padx=int(6 * s), pady=int(4 * s))
        self.panel.pack()
        self.panel_item = self.canvas.create_window(
            0, 0, window=self.panel_outer, anchor="nw")

        self._draw_ring()
        self.idle()

        c = self.canvas
        c.bind("<Motion>", self._motion)
        c.bind("<Button-1>", self._click)
        c.bind("<Button-3>", lambda _e: self.close())
        win.bind("<Key>", self._key)
        win.bind("<Escape>", self._escape)
        win.bind("<FocusOut>", self._focus_out)
        win.after(10, self._take_focus)
        win.after(150, self._watch_pointer)
        win.after(5000, self._tick_clock)

    # -- sizes ---------------------------------------------------------------

    @staticmethod
    def _monitor(px, py):
        if IS_MAC:
            # Points, as Tk uses them on a Mac (mss gives pixels).
            try:
                from AppKit import NSScreen
                screens = NSScreen.screens()
                main_h = screens[0].frame().size.height
                for scr in screens:
                    f = scr.frame()
                    x, w, h = f.origin.x, f.size.width, f.size.height
                    y = main_h - (f.origin.y + h)
                    if x <= px < x + w and y <= py < y + h:
                        return (int(x), int(y), int(w), int(h))
            except Exception:
                pass
            return None
        try:
            from .. import platform_util
            for (x, y, w, h) in platform_util.displays():
                if x <= px < x + w and y <= py < y + h:
                    return (x, y, w, h)
        except Exception:
            pass
        return (0, 0, 1920, 1080)

    def f(self, size, bold=False):
        return (common.FONT, -int(round(size * self.s)),
                "bold" if bold else "normal")

    def panel_width(self):
        """The content width every view is laid out to."""
        wide = self.selected is not None and \
            self.tools[self.selected].get("wide")
        return int((420 if wide else 290) * self.s)

    def _item_xy(self, i):
        a = math.radians(-90 + i * 360.0 / len(self.tools))
        r = 150 * self.s
        return self.cx + r * math.cos(a), self.cy + r * math.sin(a), a

    def _backdrop(self):
        """Frosted glass: what is on screen under the ring, blurred and
        tinted, as the ring's own background. None if the screen cannot be
        read (the ring is then plain)."""
        try:
            import mss
            from PIL import Image, ImageDraw, ImageFilter
            s = self.s
            r = int(round(200 * s))
            left = int(self.mon[0] + self.cx - r)
            top = int(self.mon[1] + self.cy - r)
            with mss.mss() as grab:
                shot = grab.grab({"left": left, "top": top,
                                  "width": 2 * r, "height": 2 * r})
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            # Small, blurred, back up: smooth and quick on any screen.
            small = img.resize((max(8, r // 3), max(8, r // 3)),
                               Image.BILINEAR)
            small = small.filter(ImageFilter.GaussianBlur(3))
            img = small.resize((2 * r, 2 * r), Image.BICUBIC)
            from PIL import ImageEnhance
            img = ImageEnhance.Color(img).enhance(1.5)
            th = self.th
            img = Image.blend(img, Image.new("RGB", img.size, th["glass"]),
                              th["glass_mix"])
            mask = Image.new("L", img.size, 0)
            ImageDraw.Draw(mask).ellipse((0, 0, 2 * r - 1, 2 * r - 1),
                                         fill=255)
            tone = img.resize((1, 1), Image.BOX).getpixel((0, 0))[:3]
            # A touch more solid than the glass, for text on it.
            base = tuple(int(th["glass"][k:k + 2], 16) for k in (1, 3, 5))
            tone = tuple(int(a * 0.6 + b * 0.4) for a, b in zip(tone, base))
            self._glass_tone = "#%02X%02X%02X" % tone
            img.putalpha(mask)
            return icons.to_tk(img, self.ctrl.root)
        except Exception as exc:          # noqa: BLE001 - plain ring then
            common.log("frosted ring off: %r" % exc)
            return None

    def _glow(self, colour, radius):
        cache = self.__dict__.setdefault("_glows", {})
        key = (colour, int(radius))
        if key not in cache:
            from PIL import Image, ImageDraw, ImageFilter
            size = int(radius * 2 + 12)
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            rgb = tuple(int(colour[k:k + 2], 16) for k in (1, 3, 5))
            ImageDraw.Draw(img).ellipse((6, 6, size - 6, size - 6),
                                        fill=rgb + (80,))
            img = img.filter(ImageFilter.GaussianBlur(3))
            cache[key] = icons.to_tk(img, self.canvas)
        return cache[key]

    def _tick_clock(self):
        """The time in the middle stays current."""
        if self.closed:
            return
        import time
        if self.selected is None and self.view == "idle" and \
                not self.heart_hover and \
                time.strftime("%H:%M") != self._clock_text:
            self._draw_ring()
        self.win.after(5000, self._tick_clock)

    # -- the ring ------------------------------------------------------------

    def _draw_ring(self):
        c, s = self.canvas, self.s
        c.delete("ring")
        cx, cy = self.cx, self.cy
        r = 200 * s
        if self._glass is not None:
            # Plain fill first: if a picture ever fails to show, the ring
            # is still a ring.
            c.create_oval(cx - r, cy - r, cx + r, cy + r,
                          fill=self.th["glass"], outline="", tags="ring")
            c.create_image(cx, cy, image=self._glass, tags="ring")
            c.create_oval(cx - r, cy - r, cx + r, cy + r, fill="",
                          outline=self.th["ring_line"],
                          width=max(1, int(1.5 * s)), tags="ring")
        else:
            c.create_oval(cx - r, cy - r, cx + r, cy + r,
                          fill=self.th["glass"], outline=self.th["ring_line"],
                          width=max(1, int(s)), tags="ring")
        self.item_hits = []
        for i, tool in enumerate(self.tools):
            x, y, _a = self._item_xy(i)
            rr = 42 * s
            on = i == self.selected
            colour = tool.get("colour", common.ACCENT)
            th = self.th
            if on:
                # A soft glow in the tool's colour around it.
                glow = self._glow(colour, rr + 11 * s)
                c.create_image(x, y, image=glow, tags="ring")
            c.create_oval(x - rr + 1, y - rr + 1, x + rr - 1, y + rr - 1,
                          fill=colour if on else th["item"], outline="",
                          tags="ring")
            disc = icons.pill(2 * rr, 2 * rr, colour if on else th["item"],
                              colour if on else th["item_line"], master=self.canvas)
            c.create_image(x, y, image=disc, tags="ring")
            # Drawn, not taken from a font: the same on Windows and Mac.
            icons.draw(c, tool["key"], x, y - 8 * s, 22 * s,
                       "#FFFFFF" if on else colour, tags="ring")
            c.create_text(x, y + 17 * s, text=tool["label"],
                          fill="#FFFFFF" if on else th["label"],
                          font=self.f(11, True), tags="ring")
            self.item_hits.append((x, y, rr))
        if self.hub_qr:
            self._draw_qr()
        elif self.hub_cam:
            self._draw_cam()
        else:
            self._draw_hub()
        if self.view == "support":
            hint = "Click the code to go back · Esc closes"
            line = c.create_text(cx, cy - r - 26 * s,
                                 text="♥  Support Squint if it saves you "
                                      "time  ·  Open PayPal",
                                 fill="#141413", font=self.f(13, True),
                                 tags=("ring", "support_line"))
            # A white pill behind it, so it reads on any background.
            x0, y0, x1, y1 = c.bbox(line)
            pad_x, pad_y, rad = 14 * s, 6 * s, 14 * s
            self._pill(x0 - pad_x, y0 - pad_y, x1 + pad_x, y1 + pad_y, rad,
                       fill="#FFFFFF", tags=("ring", "support_line"))
            c.tag_raise(line)
            c.tag_bind("support_line", "<Button-1>",
                       lambda _e: self._open_support())
            c.tag_bind("support_line", "<Enter>",
                       lambda _e: c.configure(cursor="hand2"))
            c.tag_bind("support_line", "<Leave>",
                       lambda _e: c.configure(cursor=""))
        elif getattr(self, "_hint_override", None):
            hint = self._hint_override
        elif self.selected is not None and \
                self.tools[self.selected].get("note"):
            # The picked tool's note, always in this one place.
            hint = self.tools[self.selected]["note"]
        else:
            hint = "Click a tool  ·  Esc closes"
        hint_id = c.create_text(cx, cy + r + 14 * s, text=hint, anchor="n",
                                width=380 * s, justify="center",
                                fill=self.th["card_text"], font=self.f(11),
                                tags=("ring", "hint"))
        # On a dark card, so it reads on a white page as well.
        x0, y0, x1, y1 = c.bbox(hint_id)
        self._hint_image = self._card_image(x1 - x0 + 24 * s,
                                            y1 - y0 + 10 * s)
        card = self.th["card"]
        self._pill(x0 - 8 * s, y0 - 2 * s, x1 + 8 * s, y1 + 2 * s, 6 * s,
                   fill="#%02X%02X%02X" % card[:3], tags=("ring", "hint"))
        c.create_image(x0 - 12 * s, y0 - 5 * s, image=self._hint_image,
                       anchor="nw", tags=("ring", "hint"))
        c.tag_raise(hint_id)
        c.tag_raise("bloom")
        c.tag_raise(self.panel_item)
        self._fit_hint()

    def _draw_hub(self):
        c, s, cx, cy = self.canvas, self.s, self.cx, self.cy
        # No disc: the heart and the words float on the glass.
        # Support, at the top of the hub, whatever else it shows.
        hx, hy = cx, cy - 40 * s
        self.heart_hit = (hx, hy, 14 * s)
        self._heart(hx, hy, (9.5 if self.heart_hover else 8) * s,
                    HEART if self.heart_hover else self.th["heart"])
        if self.selected is None and not self.heart_hover:
            self._draw_clock()
            return
        title = "Support Squint" if self.heart_hover else \
            self.tools[self.selected]["full"]
        c.create_text(cx, cy + 2 * s, text=title, fill=self.th["title"],
                      font=self.f(14, True), width=110 * s, justify="center",
                      tags="ring")
        c.create_text(cx, cy + 30 * s, text=self.shortcut,
                      fill=self.th["sub"], font=self.f(11), tags="ring")

    def _draw_clock(self):
        """The middle when nothing is picked: time, date and week, and the
        next thing on the agenda."""
        import datetime as dt
        c, s, cx, cy = self.canvas, self.s, self.cx, self.cy
        now = dt.datetime.now()
        self._clock_text = now.strftime("%H:%M")
        c.create_text(cx, cy - 10 * s, text=self._clock_text,
                      fill=self.th["title"],
                      font=self.f(28, True), tags="ring")
        c.create_text(cx, cy + 14 * s,
                      text="%s %d %s  ·  Wk %d" % (now.strftime("%a"),
                                                   now.day,
                                                   now.strftime("%b"),
                                                   now.isocalendar()[1]),
                      fill=self.th["sub"], font=self.f(11), tags="ring")
        try:
            from . import calendar_view
            nxt = calendar_view.next_item(now)
        except Exception:
            nxt = ""
        text = nxt or "Nothing on the agenda"
        font = self.f(11)
        measure = tkfont.Font(font=font).measure
        room = 108 * s
        if measure(text) > room:
            while text and measure(text + "…") > room:
                text = text[:-1]
            text = text.rstrip() + "…"
        c.create_text(cx, cy + 33 * s, text=text,
                      fill=self.th["agenda"] if nxt else self.th["sub"],
                      font=font,
                      tags=("ring", "agenda"))

    def _pill(self, x0, y0, x1, y1, r, **kw):
        r = min(r, (y1 - y0) / 2.0)
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r,
               x1, y1, x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r,
               x0, y0 + r, x0, y0]
        return self.canvas.create_polygon(pts, smooth=True, outline="", **kw)

    def _heart(self, x, y, size, colour):
        """A heart drawn as a shape, so it looks the same on every PC."""
        points = []
        for k in range(48):
            t = 2 * math.pi * k / 48
            hx = 16 * math.sin(t) ** 3
            hy = (13 * math.cos(t) - 5 * math.cos(2 * t)
                  - 2 * math.cos(3 * t) - math.cos(4 * t))
            points += [x + hx * size / 16.0, y - hy * size / 16.0]
        self.canvas.create_polygon(points, fill=colour, outline="",
                                   smooth=True, tags="ring")

    def _draw_qr(self):
        """A round QR code (dots on a white disc) fills the middle of the
        ring, inside the tools."""
        from . import qr
        qr.draw_round(self.canvas, self.hub_qr, self.cx, self.cy,
                      104 * self.s, tags="ring")
        self.heart_hit = None

    def cam_diameter(self):
        return int(208 * self.s)

    def _draw_cam(self):
        """The round camera picture fills the middle of the ring."""
        c, s, cx, cy = self.canvas, self.s, self.cx, self.cy
        r = self.cam_diameter() / 2.0
        c.create_oval(cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2,
                      fill="#000000", outline=ITEM_LINE, tags="ring")
        if self._cam_photo is not None:
            c.create_image(cx, cy, image=self._cam_photo,
                           tags=("ring", "hubcam"))
        else:
            c.create_text(cx, cy, text="Starting the camera…",
                          fill=common.MUTED, font=self.f(11),
                          tags=("ring", "hubcam_text"))
        self.heart_hit = None

    def set_cam(self, on):
        self.hub_cam = bool(on)
        if not on:
            self._cam_photo = None
        if not self.closed:
            self._draw_ring()

    def set_cam_frame(self, photo):
        """A new picture for the middle, without redrawing the ring."""
        first = self._cam_photo is None
        self._cam_photo = photo
        if first:
            self._draw_ring()
        else:
            self.canvas.itemconfigure("hubcam", image=photo)

    def set_qr(self, url):
        self.hub_qr = url
        if not self.closed:
            self._draw_ring()

    # -- the panel -----------------------------------------------------------

    def on_clear(self, fn):
        """Run `fn` when the current view goes away (camera, server…)."""
        self._cleanups.append(fn)

    def clear_panel(self):
        for fn in self._cleanups[:]:
            try:
                fn()
            except Exception as exc:      # noqa: BLE001
                common.log("cleanup: %r" % exc)
        self._cleanups = []
        if self.hub_qr:
            self.set_qr(None)
        if self.hub_cam:
            self.set_cam(False)
        if self.card is not None and self.card._job is not None:
            # Work still running: it carries on and says when it is done.
            self.card._hidden = True
        self.card = None
        try:
            self.win.unbind("<Return>")
        except tk.TclError:
            pass
        for child in self.panel.winfo_children():
            child.destroy()
        self.canvas.delete("bloom")
        self.bloom = []
        self._bloom_hover = None

    def relayout(self):
        """Fit the panel to what is in it, beside the selected tool."""
        if self.closed:
            return
        if self.selected is None:
            self._panel_show(False)
            self.panel_box = None
            self._fit_hint()
            return
        self.panel_outer.update_idletasks()
        w = self.panel_outer.winfo_reqwidth()
        h = self.panel_outer.winfo_reqheight()
        s = self.s
        _x, _y, a = self._item_xy(self.selected)
        co, si = math.cos(a), math.sin(a)
        px, py = self.cx + 212 * s * co, self.cy + 212 * s * si
        left = px - w if co < -0.3 else (px if co > 0.3 else px - w / 2)
        top = py - h if si < -0.3 else (py if si > 0.3 else py - h / 2)
        _ml, _mt, mw, mh = self.mon
        left = min(max(left, 8 * s), mw - w - 8 * s)
        top = min(max(top, 8 * s), mh - h - 8 * s)
        m = int(8 * s)
        left = min(max(left, 8 * s + m), mw - w - 8 * s - m)
        top = min(max(top, 8 * s + m), mh - h - 8 * s - m)
        self.canvas.coords(self.panel_item, left, top)
        self._draw_panel_card(left - m, top - m, w + 2 * m, h + 2 * m)
        self._panel_show(True)
        self.panel_box = (left - m, top - m, w + 2 * m, h + 2 * m)
        self._fit_hint()

    def _draw_panel_card(self, x, y, w, h):
        from PIL import Image, ImageDraw
        c, s = self.canvas, self.s
        c.delete("panelcard")
        w, h = int(round(w)), int(round(h))
        k = 3
        rgb = lambda col: tuple(int(col[i:i + 2], 16)  # noqa: E731
                                for i in (1, 3, 5))
        img = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        rad = int(16 * s * k)
        d.rounded_rectangle((0, 0, w * k - 1, h * k - 1), rad,
                            fill=rgb(common.LINE) + (255,))
        d.rounded_rectangle((k, k, w * k - 1 - k, h * k - 1 - k), rad - k,
                            fill=rgb(common.PANEL) + (255,))
        self._panel_card = icons.to_tk(img.resize((w, h), Image.LANCZOS),
                                       c)
        # A plain shape under it, in case pictures do not show.
        self._pill(x + 5 * s, y + 5 * s, x + w - 5 * s, y + h - 5 * s,
                   10 * s, fill=common.PANEL, tags=("panelcard",))
        c.create_image(x, y, image=self._panel_card, anchor="nw",
                       tags=("panelcard",))
        c.tag_raise(self.panel_item)

    def _panel_show(self, on):
        state = "normal" if on else "hidden"
        self.canvas.itemconfigure(self.panel_item, state=state)
        self.canvas.itemconfigure("panelcard", state=state)

    def _fit_hint(self):
        """The key hint under the ring hides while the panel covers any
        of it, so no half-sentence pokes out from under the panel."""
        c = self.canvas
        box = c.bbox("hint")
        if not box:
            return
        covered = False
        x0, y0, x1, y1 = box
        for bx0, by0, bx1, by1, _j in self.bloom:
            if not (x1 < bx0 or x0 > bx1 or y1 < by0 or y0 > by1):
                covered = True
        pb = getattr(self, "panel_box", None)
        if pb and c.itemcget(self.panel_item, "state") != "hidden":
            left, top, w, h = pb
            x0, y0, x1, y1 = box
            covered = not (x1 < left or x0 > left + w or
                           y1 < top or y0 > top + h)
        c.itemconfigure("hint", state="hidden" if covered else "normal")

    def header(self, parent, title, right=None, close=False):
        row = tk.Frame(parent, bg=common.PANEL)
        row.pack(fill="x")
        tk.Label(row, text=title, bg=common.PANEL, fg=common.TITLE,
                 font=self.f(13, True), anchor="w").pack(side="left")
        if close:
            x = tk.Label(row, text="✕", bg=common.PANEL, fg=common.MUTED,
                         font=self.f(12), cursor="hand2")
            x.pack(side="right")
            x.bind("<Button-1>", lambda _e: self.back())
        elif right:
            tk.Label(row, text=right, bg=common.PANEL, fg=common.MUTED,
                     font=self.f(11)).pack(side="right")
        tk.Frame(parent, bg=common.PANEL, width=self.panel_width(),
                 height=int(8 * self.s)).pack()
        return row

    def note(self, parent, text):
        tk.Frame(parent, bg=common.LINE, height=1).pack(
            fill="x", pady=(int(6 * self.s), int(8 * self.s)))
        tk.Label(parent, text=text, bg=common.PANEL, fg=common.MUTED,
                 font=self.f(11), anchor="w", justify="left",
                 wraplength=self.panel_width()).pack(fill="x")

    def row(self, parent, label, command, hint=""):
        """One choice in a panel: a pill across the panel, lit in the
        tool's colour under the mouse."""
        s = self.s
        colour = common.ACCENT
        if self.selected is not None:
            colour = self.tools[self.selected].get("colour", colour)
        b = common.PillButton(parent, text=label, command=command,
                              bg=common.ROW, fg=common.TEXT,
                              activebackground=colour,
                              activeforeground="#FFFFFF", font=self.f(13),
                              padx=int(16 * s), pady=int(8 * s), anchor="w",
                              width=self.panel_width())
        b.pack(fill="x", pady=(0, int(6 * s)))
        return b

    def button(self, parent, text, command, primary=False):
        b = common._button(parent, text, command, primary)
        b.configure(font=self.f(12), padx=int(14 * self.s),
                    pady=int(6 * self.s))
        return b

    def show_list(self):
        """The tool's actions bloom out of the ring beside it, as pills;
        the panel is only for settings, progress and views."""
        self.clear_panel()
        self.pinned = False
        self.view = "list"
        self._panel_show(False)
        self.panel_box = None
        self._draw_bloom()
        self._fit_hint()

    def _draw_bloom(self, items=None):
        c, s = self.canvas, self.s
        tool = self.tools[self.selected]
        if items is None:
            items = [("", label, j)
                     for j, (label, _f, _u, _k) in enumerate(tool["rows"])]
            if tool.get("top_label"):
                items.append(("", tool["top_label"](), "top"))
        h = int(round(32 * s))
        step = h + 8 * s
        # The words first, so each pill is as wide as what is in it.
        texts = []
        for key, label, j in items:
            tag = "bloom_%s" % j
            special = j in ("top", "back")
            kid = c.create_text(0, 0, text=key, anchor="w",
                                fill=self.th["pill_key"],
                                font=self.f(11, True),
                                tags=("bloom", tag, tag + "_key")) \
                if key else None
            lid = c.create_text(0, 0, text=label, anchor="w",
                                fill=self.th["quiet_text"] if special
                                else self.th["pill_text"],
                                font=self.f(12) if special else self.f(13),
                                tags=("bloom", tag, tag + "_text"))
            lx0, _y0, lx1, _y1 = c.bbox(lid)
            pad = 14 * s
            inner = (16 * s if key else 0) + (lx1 - lx0)
            texts.append((kid, lid, int(round(inner + 2 * pad))))
        _ix, iy, a = self._item_xy(self.selected)
        co, si = math.cos(a), math.sin(a)
        _ml, _mt, mw, mh = self.mon
        rb = 214 * s
        n = len(items)
        boxes = []
        if abs(co) >= 0.3 or si > 0:
            # Beside the ring: a column that hugs the ring's edge, ending
            # above the note under the ring. (A tool at the bottom puts
            # its column at the side too, to keep that space free.)
            side = 1 if co >= 0 else -1
            y0 = iy - (n - 1) / 2.0 * step
            lowest = self.cy + 200 * s + 4 * s - h / 2.0
            y0 = min(y0, lowest - (n - 1) * step)
            y0 = max(y0, 8 * s + h / 2.0)
            for k, (_kid, _lid, w) in enumerate(texts):
                y = y0 + k * step
                dy = y - self.cy
                edge = math.sqrt(max(rb * rb - dy * dy, 0))
                x = self.cx + side * edge
                x0 = x if side > 0 else x - w
                x0 = min(max(x0, 8 * s), mw - w - 8 * s)
                boxes.append((x0, y - h / 2.0, x0 + w, y + h / 2.0))
        else:
            # Above the ring: a column going upwards.
            for k, (_kid, _lid, w) in enumerate(texts):
                y = self.cy - rb - h / 2.0 - (n - 1 - k) * step
                x0 = min(max(self.cx - w / 2.0, 8 * s), mw - w - 8 * s)
                boxes.append((x0, y - h / 2.0, x0 + w, y + h / 2.0))
        self.bloom = []
        self._bloom_images = {}
        for (key, label, j), (kid, lid, w), (x0, y0, x1, y1) in zip(
                items, texts, boxes):
            tag = "bloom_%s" % j
            special = j in ("top", "back")
            th = self.th
            normal = icons.pill(w, h, th["pill_quiet"] if special
                                else th["pill"], th["pill_line"], master=self.canvas)
            colour = tool.get("colour", common.ACCENT)
            lit = icons.pill(w, h, colour, colour, master=self.canvas)
            self._bloom_images[j] = (normal, lit)
            fb = th["pill_quiet"] if special else th["pill"]
            fbt = ("bloom", tag, tag + "_fb")
            # Plain shape under the picture: two circles and a bar, so it
            # never shows past the smooth edge.
            c.create_oval(x0 + 1, y0 + 1, x0 + h - 1, y1 - 1, fill=fb,
                          outline="", tags=fbt)
            c.create_oval(x1 - h + 1, y0 + 1, x1 - 1, y1 - 1, fill=fb,
                          outline="", tags=fbt)
            c.create_rectangle(x0 + h / 2.0, y0 + 1, x1 - h / 2.0, y1 - 1,
                               fill=fb, outline="", tags=fbt)
            c.create_image(x0, y0, image=normal, anchor="nw",
                           tags=("bloom", tag, tag + "_bg"))
            c.tag_lower(tag + "_bg", lid)
            tx = x0 + 14 * s
            ym = (y0 + y1) / 2.0
            if kid:
                c.coords(kid, tx, ym)
                c.tag_lower(tag + "_bg", kid)
                tx += 16 * s
            c.tag_lower(tag + "_fb", tag + "_bg")
            c.coords(lid, tx, ym)
            self.bloom.append((x0, y0, x1, y1, j))
        for _x0, _y0, _x1, _y1, j in self.bloom:
            tag = "bloom_%s" % j
            c.tag_bind(tag, "<Enter>",
                       lambda _e: c.configure(cursor="hand2"))
            c.tag_bind(tag, "<Leave>", lambda _e: c.configure(cursor=""))
        c.tag_raise("bloom")
        c.tag_raise(self.panel_item)
        # The first action is lit: Enter runs it.
        if self.bloom:
            self._paint_bloom(self.bloom[0][4])

    def _card_image(self, w, h):
        from PIL import Image, ImageDraw
        k = 4
        w, h = int(round(w)), int(round(h))
        img = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
        ImageDraw.Draw(img).rounded_rectangle(
            (0, 0, w * k - 1, h * k - 1), int(10 * self.s * k),
            fill=self.th["card"])
        return icons.to_tk(img.resize((w, h), Image.LANCZOS), self.canvas)

    def _hit_bloom(self, x, y):
        for x0, y0, x1, y1, j in self.bloom:
            if x0 <= x <= x1 and y0 <= y <= y1:
                return j
        return None

    def _paint_bloom(self, j):
        if j == self._bloom_hover or j is None:
            # Off the pills, the last one lit stays lit (Enter runs it).
            return
        c = self.canvas
        images = getattr(self, "_bloom_images", {})
        for old, on in ((self._bloom_hover, False), (j, True)):
            if old is None or old not in images:
                continue
            tag = "bloom_%s" % old
            special = old in ("top", "back")
            c.itemconfigure(tag + "_bg", image=images[old][1 if on else 0])
            colour = self.tools[self.selected].get("colour", common.ACCENT)
            c.itemconfigure(tag + "_fb", fill=colour if on else (
                self.th["pill_quiet"] if special else self.th["pill"]))
            c.itemconfigure(tag + "_key", fill="#FFFFFF" if on
                            else self.th["pill_key"])
            c.itemconfigure(tag + "_text", fill="#FFFFFF" if on else (
                self.th["quiet_text"] if special else self.th["pill_text"]))
        self._bloom_hover = j

    def show_choices(self, choices, note=None):
        """A second set of actions (Phone via QR: which way), bloomed out
        of the ring like the first, with Back to return to them."""
        self.clear_panel()
        self.pinned = False
        self.view = "sub"
        self._panel_show(False)
        self.panel_box = None
        self._sub = [fn for _label, fn in choices]
        self._hint_override = note
        self._draw_ring()
        items = [("", label, "sub%d" % k)
                 for k, (label, _fn) in enumerate(choices)]
        items.append(("", "‹  Back", "back"))
        self._draw_bloom(items)
        self._fit_hint()

    def _bloom_pick(self, j):
        if j == "back":
            self.back()
            return
        if isinstance(j, str) and j.startswith("sub"):
            fn = self._sub[int(j[3:])]
            self.pinned = True
            fn()
            return
        if j == "top":
            tool = self.tools[self.selected]

            def build(frame):
                self.header(frame, tool.get("top_title", "Settings"),
                            close=True)
                tool["top"](self, frame)
                if tool.get("top_note"):
                    self.note(frame, tool["top_note"])

            self.show_view(build, pinned=True, name="top")
            return
        self.run_action(j)

    def show_view(self, builder, pinned=True, name="custom"):
        """Replace the panel's content with `builder(frame)`."""
        self.clear_panel()
        self.pinned = pinned
        self.view = name
        builder(self.panel)
        self.relayout()

    def attach(self, card):
        """A Card asks for the panel (see card.py)."""
        self.clear_panel()
        self.pinned = True
        self.view = "card"
        self.card = card
        return self.panel

    def release(self, card):
        if self.card is card:
            self.card = None
            if not self.closed:
                self.show_list()

    def back(self):
        """Esc / ✕: leave what is open and show the tool's actions."""
        if self.card is not None:
            self.card.cancel()
            return
        if self.selected is None:
            self.idle()
        else:
            self.select(self.selected)

    def idle(self):
        """Just the ring: no tool picked, no panel."""
        self.clear_panel()
        self.selected = None
        self.pinned = False
        self.view = "idle"
        self._panel_show(False)
        self._draw_ring()

    def select(self, i):
        self.selected = i
        self._hint_override = None
        self.heart_hover = False
        self._engaged = False
        self._away = 0
        self._draw_ring()
        tool = self.tools[i]
        if tool.get("view"):
            self.show_view(lambda f: tool["view"](self, f), pinned=False,
                           name="hover")
        else:
            self.show_list()

    # -- input ---------------------------------------------------------------

    def _hit_item(self, x, y):
        for i, (ix, iy, rr) in enumerate(self.item_hits):
            if (x - ix) ** 2 + (y - iy) ** 2 <= rr * rr:
                return i
        return None

    def _on_heart(self, x, y):
        h = getattr(self, "heart_hit", None)
        return bool(h) and (x - h[0]) ** 2 + (y - h[1]) ** 2 <= h[2] ** 2

    def _motion(self, e):
        heart = self._on_heart(e.x, e.y)
        if heart != self.heart_hover and not self.hub_qr \
                and not self.hub_cam:
            self.heart_hover = heart
            self._draw_ring()
            self.canvas.configure(cursor="hand2" if heart else "")
        if self.bloom:
            j = self._hit_bloom(e.x, e.y)
            self._paint_bloom(j)
        if self.pinned or self.view == "support":
            return
        i = self._hit_item(e.x, e.y)
        if i is not None and (i != self.selected or self.view == "hidden"):
            self.select(i)

    def _click(self, e):
        if self.view == "support":
            if (e.x - self.cx) ** 2 + (e.y - self.cy) ** 2 <= \
                    (104 * self.s) ** 2:
                self.idle()
                return
        if self._on_heart(e.x, e.y):
            self.support()
            return
        j = self._hit_bloom(e.x, e.y) if self.bloom else None
        if j is not None:
            self._bloom_pick(j)
            return
        i = self._hit_item(e.x, e.y)
        if i is not None:
            self.select(i)
            return
        r = 200 * self.s
        if (e.x - self.cx) ** 2 + (e.y - self.cy) ** 2 > r * r \
                and not self.pinned:
            self.close()

    def _typing(self):
        try:
            return isinstance(self.win.focus_get(), tk.Entry)
        except (KeyError, tk.TclError):
            return False

    def _key(self, e):
        """Tools and actions are picked with the mouse only; Esc (bound on
        its own) goes back or closes."""
        return

    def _escape(self, _e=None):
        if self.view == "sub":
            self.back()
        elif self.view in ("list", "hover", "hidden", "idle", "support"):
            self.close()
        else:
            self.back()

    def _take_focus(self):
        if IS_MAC:
            # No focus_force here: on a Mac it activates Squint, and that
            # brings Squint's own window up with the ring.
            self._mac_front()
            try:
                self.win.lift()
            except tk.TclError:
                pass
            return
        try:
            self.win.lift()
            self.win.focus_force()
            self.canvas.focus_set()
            if IS_WINDOWS:
                import ctypes
                self.hwnd = int(self.win.wm_frame(), 16)
                ctypes.windll.user32.SetForegroundWindow(self.hwnd)
                self.win.after(600, self._watch_front)
        except Exception:
            pass

    def _mac_front(self):
        """On a Mac the ring is shown without making Squint the active app:
        activating it would bring Squint's own window forward too. So the
        mouse is followed here rather than through events (a borderless
        window of an inactive app gets none), and Escape is read straight
        from the keyboard."""
        try:
            from AppKit import NSWorkspace
            import os
            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            pid = int(app.processIdentifier()) if app is not None else 0
            self._mac_start_front = None if pid == os.getpid() else pid
        except Exception:
            self._mac_start_front = None
        self._hover_widget = None
        self._last_pointer = None
        self.win.after(200, self._mac_watch)

    def _mac_watch(self):
        if self.closed:
            return
        try:
            px, py = self.win.winfo_pointerxy()
            if (px, py) != self._last_pointer:
                self._last_pointer = (px, py)
                self._mac_hover(px, py)
            from .. import platform_util
            if platform_util.key_is_down("escape") and not self._typing():
                if not getattr(self, "_esc_down", False):
                    self._esc_down = True
                    self._escape()
                    if self.closed:
                        return
            else:
                self._esc_down = False
            # Another app coming to the front (a click outside the ring)
            # closes it, as on Windows.
            from AppKit import NSWorkspace
            import os
            front = NSWorkspace.sharedWorkspace().frontmostApplication()
            pid = int(front.processIdentifier()) if front is not None else 0
            if pid and pid != os.getpid() and \
                    pid != self._mac_start_front and not self.pinned:
                self.close()
                return
        except Exception as exc:          # noqa: BLE001 - keep watching
            common.log("mac watch: %r" % exc)
        self.win.after(50, self._mac_watch)

    def _pointer_on_ring(self):
        px, py = self._last_pointer or self.win.winfo_pointerxy()
        x, y = px - self.mon[0], py - self.mon[1]
        r = 200 * self.s
        if (x - self.cx) ** 2 + (y - self.cy) ** 2 <= r * r:
            return True
        if self.bloom and self._hit_bloom(x, y) is not None:
            return True
        if self.canvas.itemcget(self.panel_item, "state") != "hidden":
            left, top, w, h = getattr(self, "panel_box", None) or (0, 0, 0, 0)
            return left <= x <= left + w and top <= y <= top + h
        return False

    def _mac_hover(self, px, py):
        """What <Motion>, <Enter> and <Leave> would have done."""
        x, y = px - self.mon[0], py - self.mon[1]

        class Event:
            pass

        e = Event()
        e.x, e.y = x, y
        self._motion(e)
        try:
            widget = self.win.winfo_containing(px, py)
        except (KeyError, tk.TclError):
            widget = None
        if widget is not self._hover_widget:
            old, self._hover_widget = self._hover_widget, widget
            for w, seq in ((old, "<Leave>"), (widget, "<Enter>")):
                if w is not None and w is not self.canvas:
                    try:
                        w.event_generate(seq)
                    except tk.TclError:
                        pass

    def _mac_hand_back(self):
        """If a click made Squint the active app, give the front back to
        the app that was there, so Squint's window does not stay on top."""
        try:
            from AppKit import NSRunningApplication
            if NSRunningApplication.currentApplication().isActive() and \
                    getattr(self, "_mac_start_front", None):
                from .. import platform_util
                platform_util.bring_back(self._mac_start_front)
        except Exception:
            pass

    def _watch_front(self):
        """Close once another window comes to the front, unless the user is
        in the middle of something in the panel (a file dialog, the QR
        code, the camera…)."""
        if self.closed:
            return
        try:
            import ctypes
            front = ctypes.windll.user32.GetForegroundWindow()
            if front and front != self.hwnd and not self.pinned:
                self.close()
                return
        except Exception:
            return
        self.win.after(250, self._watch_front)

    def _focus_out(self, _e=None):
        def check():
            if self.closed or self.pinned:
                return
            try:
                if self.win.focus_get() is None:
                    self.close()
            except (KeyError, tk.TclError):
                self.close()
        self.win.after(200, check)

    def _watch_pointer(self):
        """A hover view (the calendar) stays while the mouse is on its tool
        or in the panel, and goes once it has been away for a moment."""
        if self.closed:
            return
        if self.view in ("hover", "hidden") and not self._typing():
            px, py = self.win.winfo_pointerxy()
            x, y = px - self.mon[0], py - self.mon[1]
            inside = False
            if self.view == "hover":
                left, top, w, h = getattr(self, "panel_box", None) or (0, 0, 0, 0)
                inside = left <= x <= left + w and top <= y <= top + h
            ix, iy, rr = self.item_hits[self.selected]
            on_tool = (x - ix) ** 2 + (y - iy) ** 2 <= rr * rr
            if inside or on_tool:
                self._away = 0
                self._engaged = True
                if self.view == "hidden":
                    self._panel_show(True)
                    self.view = "hover"
            else:
                self._away += 1
                if self._away >= 3 and self.view == "hover" \
                        and self._engaged:
                    self._panel_show(False)
                    self.view = "hidden"
        self.win.after(150, self._watch_pointer)

    # -- doing it ------------------------------------------------------------

    def support(self):
        """♥: the PayPal code in the middle of the ring and one line above
        it. Clicking the code brings the heart back."""
        self.clear_panel()
        self.selected = None
        # Not pinned: clicking anywhere outside the ring closes it, as
        # usual. Hover over a tool does not switch away (see _motion).
        self.pinned = False
        self.view = "support"
        self._panel_show(False)
        self.set_qr(self.support_url)

    def _open_support(self):
        import webbrowser
        url = self.support_url
        self.close()
        if url:
            webbrowser.open(url)

    def run_action(self, j):
        tool = self.tools[self.selected]
        label, action, uses_files, kind = tool["rows"][j]
        ctrl = self.ctrl
        common.log("%s > %s" % (tool["full"], label))
        if kind == "screen":
            self.close()
            ctrl.root.after(150, lambda: self._call(action, label, []))
            return
        # The panel stays up for this one, through any file dialog.
        self.pinned = True
        selection = []
        if uses_files and self.front:
            selection = common.explorer_selection(self.front)
        before = self.view
        self._call(action, label, selection)
        if not self.closed and self.view == before and self.card is None:
            self.show_list()             # nothing came of it (cancelled)

    def _call(self, action, label, selection):
        try:
            action(self.ctrl, selection=selection, menu=self)
        except Exception as exc:          # noqa: BLE001 - shown to the user
            import traceback
            common.log(traceback.format_exc())
            common.failed(self.ctrl, label, exc)

    def close_then(self, fn, delay=150):
        """Close the ring (it must not be in a screenshot), then `fn()`."""
        self.close()
        self.ctrl.root.after(delay, fn)

    def close(self):
        if self.closed:
            return
        self.clear_panel()
        self.closed = True
        if IS_MAC:
            self._mac_hand_back()
        RadialMenu.current = None
        try:
            self.win.destroy()
        except Exception:
            pass
