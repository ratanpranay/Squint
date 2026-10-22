"""The ring, and the one panel beside it where every tool shows its options,
settings, progress, calendar, QR status or camera. Nothing opens a window
of its own while the ring is up.

The ring is drawn on a canvas covering the monitor under the mouse. On
Windows the canvas background is a colour the window treats as
transparent, so only the ring and the panel are visible and the rest of
the screen stays clickable.

The panel is a real Tk frame placed on the canvas. It shows one view at a
time:
  list      a tool's actions (hovering another tool switches)
  calendar  shown on hover, hidden once the mouse has left it
  pinned    anything the user is in the middle of: settings, progress, the
            QR code, the camera. Hovering does not switch away from it and
            losing focus does not close the ring; Esc or ✕ goes back.
"""
import math
import sys
import tkinter as tk
import tkinter.font as tkfont

from . import common

IS_WINDOWS = sys.platform == "win32"
KEY = "#010203"                 # the see-through colour

RING_BG = "#181B22"
ITEM_BG = "#262A33"
ITEM_LINE = "#3A404C"
HUB_BG = "#11131A"
HEART = "#F0506E"


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
        self.heart_hover = False
        self._cleanups = []
        self._away = 0
        self._engaged = False

        root = ctrl.root
        px, py = root.winfo_pointerxy()
        self.mon = mon = self._monitor(px, py)
        scale = 1.0
        try:
            from .. import platform_util
            scale = (platform_util.monitor_scaling(px, py) or 100) / 100.0
        except Exception:
            pass
        self.s = s = max(1.0, scale)
        left, top, width, height = mon

        win = self.win = tk.Toplevel(root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.geometry("%dx%d+%d+%d" % (width, height, left, top))
        bg = KEY if IS_WINDOWS else "#0B0D11"
        win.configure(bg=bg)
        if IS_WINDOWS:
            win.attributes("-transparentcolor", KEY)
        else:
            try:
                win.attributes("-alpha", 0.95)
            except tk.TclError:
                pass
        self.canvas = tk.Canvas(win, width=width, height=height, bg=bg,
                                highlightthickness=0, bd=0)
        self.canvas.pack()

        margin = 215 * s
        self.cx = min(max(px - left, margin), width - margin)
        # Room above the ring for the support line.
        self.cy = min(max(py - top, margin + 40 * s), height - margin)

        families = set(tkfont.families(root))
        self.icon_font = next((f for f in ("Segoe Fluent Icons",
                                           "Segoe MDL2 Assets")
                               if f in families), None)

        # The panel: a border frame holding a padded content frame.
        self.panel_outer = tk.Frame(self.canvas, bg=ITEM_LINE)
        self.panel = tk.Frame(self.panel_outer, bg=common.PANEL,
                              padx=int(14 * s), pady=int(12 * s))
        self.panel.pack(padx=1, pady=1)
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

    # -- sizes ---------------------------------------------------------------

    @staticmethod
    def _monitor(px, py):
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
        a = math.radians(-90 + i * 40)
        r = 150 * self.s
        return self.cx + r * math.cos(a), self.cy + r * math.sin(a), a

    # -- the ring ------------------------------------------------------------

    def _draw_ring(self):
        c, s = self.canvas, self.s
        c.delete("ring")
        cx, cy = self.cx, self.cy
        r = 200 * s
        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=RING_BG,
                      outline="#343944", width=max(1, int(s)), tags="ring")
        self.item_hits = []
        for i, tool in enumerate(self.tools):
            x, y, _a = self._item_xy(i)
            rr = 42 * s
            on = i == self.selected
            fg = "#FFFFFF" if on else "#D5D9E2"
            c.create_oval(x - rr, y - rr, x + rr, y + rr,
                          fill=common.ACCENT if on else ITEM_BG,
                          outline=common.ACCENT if on else ITEM_LINE,
                          width=max(1, int(s)), tags="ring")
            if self.icon_font:
                c.create_text(x, y - 9 * s, text=tool["glyph"], fill=fg,
                              font=(self.icon_font, -int(22 * s)), tags="ring")
            else:
                c.create_text(x, y - 6 * s, text=str(i + 1), fill=fg,
                              font=self.f(16, True), tags="ring")
            c.create_text(x, y + 16 * s, text=tool["label"], fill=fg,
                          font=self.f(11, True), tags="ring")
            self.item_hits.append((x, y, rr))
        if self.hub_qr:
            self._draw_qr()
        else:
            self._draw_hub()
        if self.view == "support":
            hint = "Click the code to go back · Esc closes"
            c.create_text(cx, cy - r - 24 * s,
                          text="♥  Support Squint if it saves you time  ·  "
                               "Open PayPal",
                          fill="#FFFFFF", font=self.f(13, True),
                          tags=("ring", "support_line"))
            c.tag_bind("support_line", "<Button-1>",
                       lambda _e: self._open_support())
            c.tag_bind("support_line", "<Enter>",
                       lambda _e: c.configure(cursor="hand2"))
            c.tag_bind("support_line", "<Leave>",
                       lambda _e: c.configure(cursor=""))
        else:
            hint = "1–9 picks a tool · letters pick an action · Esc goes back"
        c.create_text(cx, cy + r + 22 * s, text=hint,
                      fill="#C9CED8", font=self.f(11), tags="ring")
        c.tag_raise(self.panel_item)

    def _draw_hub(self):
        c, s, cx, cy = self.canvas, self.s, self.cx, self.cy
        hr = 64 * s
        c.create_oval(cx - hr, cy - hr, cx + hr, cy + hr, fill=HUB_BG,
                      outline=ITEM_LINE, width=max(1, int(s)), tags="ring")
        # Support, at the top of the hub.
        hx, hy = cx, cy - 36 * s
        self.heart_hit = (hx, hy, 14 * s)
        self._heart(hx, hy, (9.5 if self.heart_hover else 8) * s,
                    HEART if self.heart_hover else "#C8546A")
        if self.heart_hover:
            title = "Support Squint"
        elif self.selected is None:
            title = "Squint"
        else:
            title = self.tools[self.selected]["full"]
        c.create_text(cx, cy + 2 * s, text=title, fill="#FFFFFF",
                      font=self.f(14, True), width=110 * s, justify="center",
                      tags="ring")
        c.create_text(cx, cy + 30 * s, text=self.shortcut,
                      fill=common.MUTED, font=self.f(10), tags="ring")

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
        """The QR code fills the middle of the ring."""
        from . import qr
        c, s, cx, cy = self.canvas, self.s, self.cx, self.cy
        side = 148 * s
        x0, y0 = cx - side / 2, cy - side / 2
        c.create_rectangle(x0 - 6 * s, y0 - 6 * s, x0 + side + 6 * s,
                           y0 + side + 6 * s, fill="#FFFFFF", outline="",
                           tags="ring")
        rows = qr.encode(self.hub_qr)
        n = len(rows) + 2
        cell = side / float(n)
        for ry, row in enumerate(rows):
            for rx, on in enumerate(row):
                if on:
                    x = x0 + (rx + 1) * cell
                    y = y0 + (ry + 1) * cell
                    c.create_rectangle(x, y, x + cell + 0.4, y + cell + 0.4,
                                       fill="#000000", width=0, tags="ring")
        self.heart_hit = None

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

    def relayout(self):
        """Fit the panel to what is in it, beside the selected tool."""
        if self.closed:
            return
        if self.selected is None:
            self.canvas.itemconfigure(self.panel_item, state="hidden")
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
        self.canvas.coords(self.panel_item, left, top)
        self.canvas.itemconfigure(self.panel_item, state="normal")
        self.panel_box = (left, top, w, h)

    def header(self, parent, title, right=None, close=False):
        row = tk.Frame(parent, bg=common.PANEL)
        row.pack(fill="x")
        tk.Label(row, text=title, bg=common.PANEL, fg="#FFFFFF",
                 font=self.f(13, True), anchor="w").pack(side="left")
        if close:
            x = tk.Label(row, text="✕", bg=common.PANEL, fg=common.MUTED,
                         font=self.f(12), cursor="hand2")
            x.pack(side="right")
            x.bind("<Button-1>", lambda _e: self.back())
        elif right:
            tk.Label(row, text=right, bg=common.PANEL, fg=common.MUTED,
                     font=self.f(10)).pack(side="right")
        tk.Frame(parent, bg=common.PANEL, width=self.panel_width(),
                 height=int(8 * self.s)).pack()
        return row

    def note(self, parent, text):
        tk.Frame(parent, bg=ITEM_LINE, height=1).pack(
            fill="x", pady=(int(6 * self.s), int(8 * self.s)))
        tk.Label(parent, text=text, bg=common.PANEL, fg="#B8BECA",
                 font=self.f(10), anchor="w", justify="left",
                 wraplength=self.panel_width()).pack(fill="x")

    def row(self, parent, label, command, hint=""):
        """One clickable line, highlighted under the mouse."""
        s = self.s
        frame = tk.Frame(parent, bg=common.PANEL, cursor="hand2")
        frame.pack(fill="x", pady=(0, int(2 * s)))
        text = tk.Label(frame, text=label, bg=common.PANEL, fg=common.TEXT,
                        font=self.f(13), anchor="w", padx=int(10 * s),
                        pady=int(8 * s))
        text.pack(side="left", fill="x", expand=True)
        key = tk.Label(frame, text=hint, bg=common.PANEL, fg=common.MUTED,
                       font=self.f(11), padx=int(10 * s))
        key.pack(side="right")
        parts = (frame, text, key)

        def paint(on):
            for p in parts:
                p.configure(bg=common.ROW if on else common.PANEL)

        for p in parts:
            p.bind("<Enter>", lambda _e: paint(True))
            p.bind("<Leave>", lambda _e: paint(False))
            p.bind("<Button-1>", lambda _e: command())
        return frame

    def button(self, parent, text, command, primary=False):
        b = common._button(parent, text, command, primary)
        b.configure(font=self.f(11), padx=int(14 * self.s),
                    pady=int(6 * self.s))
        return b

    def show_list(self):
        self.clear_panel()
        self.pinned = False
        self.view = "list"
        tool = self.tools[self.selected]
        self.header(self.panel, tool["full"], "key %d" % (self.selected + 1))
        if tool.get("top"):
            tool["top"](self, self.panel)
        for j, (label, _fn, _files, _kind) in enumerate(tool["rows"]):
            self.row(self.panel, label, lambda j=j: self.run_action(j),
                     chr(65 + j))
        if tool.get("note"):
            self.note(self.panel, tool["note"])
        self.relayout()

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
        self.canvas.itemconfigure(self.panel_item, state="hidden")
        self._draw_ring()

    def select(self, i):
        self.selected = i
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
        if heart != self.heart_hover and not self.hub_qr:
            self.heart_hover = heart
            self._draw_ring()
            self.canvas.configure(cursor="hand2" if heart else "")
        if self.pinned:
            return
        i = self._hit_item(e.x, e.y)
        if i is not None and (i != self.selected or self.view == "hidden"):
            self.select(i)

    def _click(self, e):
        if self.view == "support":
            half = 80 * self.s
            if abs(e.x - self.cx) <= half and abs(e.y - self.cy) <= half:
                self.idle()
                return
        if self._on_heart(e.x, e.y):
            self.support()
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
        if self._typing() or self.pinned:
            return
        ch = (e.char or "").lower()
        if ch and ch in "123456789":
            self.select(int(ch) - 1)
            return
        if self.selected is None:
            if e.keysym in ("Left", "Up", "Right", "Down", "Tab"):
                self.select(0)
            return
        rows = self.tools[self.selected]["rows"]
        if e.keysym in ("Return", "KP_Enter") and rows:  # noqa
            self.run_action(0)
            return
        if ch and "a" <= ch <= "z" and ord(ch) - 97 < len(rows):
            self.run_action(ord(ch) - 97)
            return
        if e.keysym in ("Left", "Up"):
            self.select((self.selected - 1) % len(self.tools))
        elif e.keysym in ("Right", "Down", "Tab"):
            self.select((self.selected + 1) % len(self.tools))

    def _escape(self, _e=None):
        if self.view in ("list", "hover", "hidden", "idle", "support"):
            self.close()
        else:
            self.back()

    def _take_focus(self):
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
                left, top, w, h = getattr(self, "panel_box", (0, 0, 0, 0))
                inside = left <= x <= left + w and top <= y <= top + h
            ix, iy, rr = self.item_hits[self.selected]
            on_tool = (x - ix) ** 2 + (y - iy) ** 2 <= rr * rr
            if inside or on_tool:
                self._away = 0
                self._engaged = True
                if self.view == "hidden":
                    self.canvas.itemconfigure(self.panel_item, state="normal")
                    self.view = "hover"
            else:
                self._away += 1
                if self._away >= 3 and self.view == "hover" \
                        and self._engaged:
                    self.canvas.itemconfigure(self.panel_item, state="hidden")
                    self.view = "hidden"
        self.win.after(150, self._watch_pointer)

    # -- doing it ------------------------------------------------------------

    def support(self):
        """♥: the PayPal code in the middle of the ring and one line above
        it. Clicking the code brings the heart back."""
        self.clear_panel()
        self.selected = None
        self.pinned = True
        self.view = "support"
        self.canvas.itemconfigure(self.panel_item, state="hidden")
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
        RadialMenu.current = None
        try:
            self.win.destroy()
        except Exception:
            pass
