"""The ring itself: drawn on a canvas covering the monitor under the mouse.

On Windows the canvas background is a colour the window is told to treat
as transparent, so only the ring and the panel are visible and everything
else on the screen stays clickable. Clicking elsewhere takes the focus
away, and losing focus closes the menu."""
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


class RadialMenu:
    current = None

    def __init__(self, ctrl, tools, calendar_cmd, front=None):
        RadialMenu.current = self
        self.ctrl = ctrl
        self.tools = tools
        self.calendar_cmd = calendar_cmd
        self.front = front
        self.selected = 0
        self.hover_row = None
        self.closed = False

        root = ctrl.root
        px, py = root.winfo_pointerxy()
        mon = self._monitor(px, py)
        scale = 1.0
        try:
            from .. import platform_util
            scale = (platform_util.monitor_scaling(px, py) or 100) / 100.0
        except Exception:
            pass
        self.s = s = max(1.0, scale)
        self.mon = mon
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
                win.attributes("-alpha", 0.93)
            except tk.TclError:
                pass
        self.canvas = tk.Canvas(win, width=width, height=height, bg=bg,
                                highlightthickness=0, bd=0)
        self.canvas.pack()

        # The ring's centre: the mouse, moved in just enough to fit.
        margin = 215 * s
        self.cx = min(max(px - left, margin), width - margin)
        self.cy = min(max(py - top, margin), height - margin)

        families = set(tkfont.families(root))
        self.icon_font = next((f for f in ("Segoe Fluent Icons",
                                           "Segoe MDL2 Assets")
                               if f in families), None)
        self.font = common.FONT
        self._draw()

        c = self.canvas
        c.bind("<Motion>", self._motion)
        c.bind("<Button-1>", self._click)
        c.bind("<Button-3>", lambda _e: self.close())
        win.bind("<Escape>", lambda _e: self.close())
        win.bind("<Key>", self._key)
        win.bind("<FocusOut>", self._focus_out)
        win.after(10, self._take_focus)

    # -- geometry ----------------------------------------------------------

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

    def _f(self, size, bold=False):
        return (self.font, -int(round(size * self.s)),
                "bold" if bold else "normal")

    def _item_xy(self, i):
        a = math.radians(-90 + i * 40)
        r = 150 * self.s
        return self.cx + r * math.cos(a), self.cy + r * math.sin(a), a

    def _panel_box(self):
        key, _l, _full, _g, rows, note = self.tools[self.selected]
        s = self.s
        _x, _y, a = self._item_xy(self.selected)
        c, si = math.cos(a), math.sin(a)
        px, py = self.cx + 212 * s * c, self.cy + 212 * s * si
        w = 250 * s
        h = (16 + 38 + len(rows) * 42) * s + self._note_height(note, w)
        left = px - w if c < -0.3 else (px if c > 0.3 else px - w / 2)
        top = py - h if si < -0.3 else (py if si > 0.3 else py - h / 2)
        _ml, _mt, mw, mh = self.mon
        left = min(max(left, 8 * s), mw - w - 8 * s)
        top = min(max(top, 8 * s), mh - h - 8 * s)
        return left, top, w, h

    def _note_height(self, note, w):
        """Room for the footer note, wrapped to the panel's width."""
        if not note:
            return 8 * self.s
        font = tkfont.Font(root=self.win, font=self._f(11))
        width = w - 34 * self.s
        lines, line = 1, ""
        for word in note.split():
            trial = (line + " " + word).strip()
            if font.measure(trial) > width and line:
                lines, line = lines + 1, word
            else:
                line = trial
        return (26 + lines * font.metrics("linespace")) * 1.0 + 12 * self.s

    # -- drawing -------------------------------------------------------------

    def _round_rect(self, x0, y0, x1, y1, r, **kw):
        c = self.canvas
        points = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r,
                  x1, y1, x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r,
                  x0, y0 + r, x0, y0]
        return c.create_polygon(points, smooth=True, **kw)

    def _draw(self):
        c, s = self.canvas, self.s
        c.delete("all")
        cx, cy = self.cx, self.cy
        r = 200 * s
        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=RING_BG,
                      outline="#343944", width=max(1, int(s)))
        self.item_hits = []
        for i, (key, label, full, glyph, rows, _note) in enumerate(self.tools):
            x, y, _a = self._item_xy(i)
            rr = 42 * s
            on = i == self.selected
            fill = common.ACCENT if on else ITEM_BG
            fg = "#FFFFFF" if on else "#D5D9E2"
            c.create_oval(x - rr, y - rr, x + rr, y + rr, fill=fill,
                          outline=common.ACCENT if on else ITEM_LINE,
                          width=max(1, int(s)))
            if self.icon_font:
                c.create_text(x, y - 9 * s, text=glyph, fill=fg,
                              font=(self.icon_font, -int(22 * s)))
                c.create_text(x, y + 18 * s, text=label, fill=fg,
                              font=self._f(11, True))
            else:
                c.create_text(x, y - 6 * s, text=str(i + 1), fill=fg,
                              font=self._f(16, True))
                c.create_text(x, y + 14 * s, text=label, fill=fg,
                              font=self._f(11, True))
            self.item_hits.append((x, y, rr))
        hr = 64 * s
        c.create_oval(cx - hr, cy - hr, cx + hr, cy + hr, fill=HUB_BG,
                      outline=ITEM_LINE, width=max(1, int(s)))
        full = self.tools[self.selected][2]
        c.create_text(cx, cy - 10 * s, text=full, fill="#FFFFFF",
                      font=self._f(14, True), width=110 * s, justify="center")
        c.create_text(cx, cy + 20 * s, text="Ctrl + Alt + Space",
                      fill=common.MUTED, font=self._f(10))
        c.create_text(cx, cy + r + 22 * s,
                      text="1–9 picks a tool · letters pick an action · Esc closes",
                      fill="#C9CED8", font=self._f(11))
        self._draw_panel()

    def _draw_panel(self):
        c, s = self.canvas, self.s
        self.row_hits = []
        key, _l, full, _g, rows, note = self.tools[self.selected]
        if key == "cal":
            left, top, w, h = self._panel_box()
            self._round_rect(left, top, left + w, top + 92 * s, 14 * s,
                             fill=common.PANEL, outline=ITEM_LINE)
            c.create_text(left + 16 * s, top + 26 * s, anchor="w",
                          text="Calendar", fill="#FFFFFF",
                          font=self._f(13, True))
            c.create_text(left + 16 * s, top + 58 * s, anchor="w",
                          text="Click it, or press A, for the month view",
                          fill=common.MUTED, font=self._f(10), width=w - 30 * s)
            self.row_hits.append((left, top, left + w, top + 92 * s, 0))
            return
        left, top, w, h = self._panel_box()
        self._round_rect(left, top, left + w, top + h, 14 * s,
                         fill=common.PANEL, outline=ITEM_LINE)
        c.create_text(left + 18 * s, top + 26 * s, anchor="w", text=full,
                      fill="#FFFFFF", font=self._f(13, True))
        c.create_text(left + w - 16 * s, top + 26 * s, anchor="e",
                      text="key %d" % (self.selected + 1), fill=common.MUTED,
                      font=self._f(11))
        y = top + 46 * s
        for j, (label, _run, _files) in enumerate(rows):
            x0, y0, x1, y1 = left + 8 * s, y, left + w - 8 * s, y + 40 * s
            if j == self.hover_row:
                self._round_rect(x0, y0, x1, y1, 8 * s, fill=common.ROW,
                                 outline="")
            c.create_text(x0 + 12 * s, (y0 + y1) / 2, anchor="w", text=label,
                          fill=common.TEXT, font=self._f(13))
            c.create_text(x1 - 12 * s, (y0 + y1) / 2, anchor="e",
                          text=chr(65 + j), fill=common.MUTED,
                          font=self._f(11))
            self.row_hits.append((x0, y0, x1, y1, j))
            y += 42 * s
        if note:
            c.create_line(left + 12 * s, y + 6 * s, left + w - 12 * s,
                          y + 6 * s, fill=ITEM_LINE)
            c.create_text(left + 18 * s, y + 18 * s, anchor="nw", text=note,
                          fill="#B8BECA", font=self._f(11), width=w - 34 * s)

    # -- input ---------------------------------------------------------------

    def _hit_item(self, x, y):
        for i, (ix, iy, rr) in enumerate(self.item_hits):
            if (x - ix) ** 2 + (y - iy) ** 2 <= rr * rr:
                return i
        return None

    def _hit_row(self, x, y):
        for x0, y0, x1, y1, j in self.row_hits:
            if x0 <= x <= x1 and y0 <= y <= y1:
                return j
        return None

    def _motion(self, e):
        i = self._hit_item(e.x, e.y)
        if i is not None and i != self.selected:
            self.selected, self.hover_row = i, None
            self._draw()
            return
        j = self._hit_row(e.x, e.y)
        if j != self.hover_row:
            self.hover_row = j
            self._draw()

    def _click(self, e):
        i = self._hit_item(e.x, e.y)
        if i is not None:
            if i == self.selected and self.tools[i][0] == "cal":
                self.run(0)
                return
            self.selected, self.hover_row = i, None
            self._draw()
            if self.tools[i][0] == "cal":
                self.run(0)
            return
        j = self._hit_row(e.x, e.y)
        if j is not None:
            self.run(j)
            return
        cx, cy = self.cx, self.cy
        if (e.x - cx) ** 2 + (e.y - cy) ** 2 > (200 * self.s) ** 2:
            self.close()

    def _key(self, e):
        ch = (e.char or "").lower()
        if ch and ch in "123456789":
            self.selected, self.hover_row = int(ch) - 1, None
            self._draw()
            return
        if e.keysym in ("Return", "KP_Enter"):
            self.run(self.hover_row or 0)
            return
        if ch and "a" <= ch <= "z":
            j = ord(ch) - 97
            rows = self.tools[self.selected][4]
            if j < len(rows) or self.tools[self.selected][0] == "cal":
                self.run(j)
            return
        if e.keysym in ("Left", "Up"):
            self.selected = (self.selected - 1) % len(self.tools)
            self._draw()
        elif e.keysym in ("Right", "Down", "Tab"):
            self.selected = (self.selected + 1) % len(self.tools)
            self._draw()

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
        """Close once another window comes to the front: a click that
        went through the see-through part of this one, Alt+Tab, anything.
        Focus events alone miss some of these on a borderless window."""
        if self.closed:
            return
        try:
            import ctypes
            front = ctypes.windll.user32.GetForegroundWindow()
            if front and front != self.hwnd:
                self.close()
                return
        except Exception:
            return
        self.win.after(250, self._watch_front)

    def _focus_out(self, _e=None):
        def check():
            if self.closed:
                return
            try:
                if self.win.focus_get() is None:
                    self.close()
            except (KeyError, tk.TclError):
                self.close()
        self.win.after(150, check)

    # -- doing it ------------------------------------------------------------

    def run(self, j):
        key, _l, full, _g, rows, _note = self.tools[self.selected]
        ctrl = self.ctrl
        if key == "cal":
            left, top, _w, _h = self._panel_box()
            near = (int(self.mon[0] + left), int(self.mon[1] + top))
            self.close()
            ctrl.root.after(60, lambda: self.calendar_cmd(ctrl, near=near))
            return
        label, action, uses_files = rows[j]
        front = self.front
        left, top, _w, _h = self._panel_box()
        anchor = (int(self.mon[0] + left), int(self.mon[1] + top))
        self.close()

        def go():
            selection = []
            if uses_files and front:
                selection = common.explorer_selection(front)
            common.log("%s > %s (%d selected)" % (full, label, len(selection)))
            try:
                action(ctrl, selection=selection, anchor=anchor)
            except Exception as exc:      # noqa: BLE001 - shown to the user
                import traceback
                common.log(traceback.format_exc())
                common.failed(ctrl, label, exc)

        # Let the menu leave the screen before anything grabs it.
        ctrl.root.after(120, go)

    def close(self):
        if self.closed:
            return
        self.closed = True
        RadialMenu.current = None
        try:
            self.win.destroy()
        except Exception:
            pass
