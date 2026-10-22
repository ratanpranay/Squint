"""The picture guides to getting a key, shown inside the app.

There is a written guide next door in `ui_help_keys`, and a checklist next
to that which tests a key you already have. Neither answers the question
people are actually stuck on, which is not "what is a key" but "which of
these forty buttons". Google redesigns its console every few months and no
sentence survives that; a picture of the button does.

Bundled rather than linked, for the reasons the written guide gives: the
person reading this is reading it because they are stuck, a link that
opens a browser on a locked-down machine is one more thing that can fail,
and a page on the internet drifts out of step with the app.

The first version of this window fitted the picture to the screen and left
it there, which is the one thing a guide made of screenshots must not do.
Fitted to a laptop display, a step is a thumbnail — you can see there is a
button and not read what it says. So the picture opens at the size that
fits and then zooms and pans like a map: a floating window, the wheel to
zoom, drag to move, and the keyboard for both.

Everything here is defensive on purpose. It is help, opened by somebody
already having a bad time, and there is no failure in it worth taking the
app down for. Anything that cannot be done is not done, and the window
either opens usefully or says where the words are instead.
"""
import os
import tkinter as tk

from . import config, platform_util, theme as theme_mod
from .ui_kit import PillButton, label


# Which picture answers which field. The names are the asset filenames.
GUIDES = {
    "gemini": ("guide-gemini.webp", "Getting a free Gemini key"),
    "google": ("guide-google.webp", "Getting a Google Cloud API key"),
    "groq": ("guide-groq.webp", "Getting a free Groq key"),
}

# How much of the display the window may take when it opens.
FILL = 0.9

# What the wheel and the buttons step through. Not a continuous zoom: a
# guide is read at a handful of useful sizes — the whole thing, a row of
# steps, one step, the writing inside a screenshot — and stepping lands on
# them where dragging a slider hunts around them.
ZOOMS = (0.35, 0.5, 0.7, 0.85, 1.0, 1.25, 1.5, 2.0, 3.0)

# Drawing a 2200-pixel picture at 3x on every wheel notch is slow enough to
# feel broken, so a redraw waits for the notches to stop arriving.
REDRAW_AFTER = 90


def asset(name):
    """Where the picture is, or None. Same search as the app icon."""
    try:
        for base in (config.resource_dir(), config.app_dir()):
            for candidate in (os.path.join(base, "assets", name),
                              os.path.join(base, name)):
                if os.path.exists(candidate):
                    return candidate
    except Exception:
        return None
    return None


def available(which):
    """Whether this guide can actually be shown.

    Asked before a button offering it is drawn. A question mark that opens
    an apology is worse than no question mark: whoever clicked it is
    already stuck, and being told the help is missing helps with nothing.
    """
    try:
        entry = GUIDES.get(which)
        if entry is None or asset(entry[0]) is None:
            return False
        from PIL import Image, ImageTk          # noqa: F401
        return True
    except Exception:
        return False


class GuideWindow(tk.Toplevel):
    """One guide, floating, zoomable and pannable."""

    _open = {}

    def __init__(self, master, which, palette=None):
        super().__init__(master)
        self.which = which
        self.palette = palette or theme_mod.resolve(
            config.CONFIG.get("theme", "auto"))
        p = self.palette
        name, title = GUIDES.get(which, (None, "Guide"))
        self.title(title)
        self.configure(bg=p["window"])
        self._source = None
        self._photo = None
        self._zoom = 0
        self._redraw_job = None
        self._drag = None

        self._source = self._read(name)
        if self._source is None:
            self._explain()
            return

        self._build(title)
        self._fit()
        self._place()
        GuideWindow._open[self.which] = self

    # -- what is on screen ---------------------------------------------
    def _read(self, name):
        path = asset(name) if name else None
        if path is None:
            return None
        try:
            from PIL import Image
            picture = Image.open(path)
            picture.load()
            return picture.convert("RGB")
        except Exception:
            return None

    def _build(self, title):
        p = self.palette
        bar = tk.Frame(self, bg=p["window"])
        bar.pack(fill="x", padx=16, pady=(12, 8))
        label(bar, p, title, size=11, weight="bold").pack(side="left")
        self.zoom_label = label(bar, p, "", size=9, dim=True)
        self.zoom_label.pack(side="left", padx=(12, 0))
        PillButton(bar, "Close", command=self.close, palette=p,
                   kind="secondary", height=32, font_size=9,
                   pad_x=18).pack(side="right")
        PillButton(bar, "+", command=lambda: self.zoom(1), palette=p,
                   kind="ghost", height=32, font_size=10,
                   pad_x=14).pack(side="right", padx=(6, 8))
        PillButton(bar, "−", command=lambda: self.zoom(-1), palette=p,
                   kind="ghost", height=32, font_size=10,
                   pad_x=14).pack(side="right")
        PillButton(bar, "Fit", command=self._fit_again, palette=p,
                   kind="ghost", height=32, font_size=9,
                   pad_x=14).pack(side="right", padx=(0, 6))

        holder = tk.Frame(self, bg=p["window"])
        holder.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        self.canvas = tk.Canvas(holder, bg=p["window"], highlightthickness=0,
                                bd=0, cursor="fleur")
        self.down = tk.Scrollbar(holder, orient="vertical",
                                 command=self.canvas.yview)
        self.across = tk.Scrollbar(self, orient="horizontal",
                                   command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.down.set,
                              xscrollcommand=self.across.set)
        self.down.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.across.pack(fill="x", padx=16, pady=(0, 6))
        self._item = self.canvas.create_image(0, 0, anchor="nw")

        hint = ("Scroll to move · %s and the wheel to zoom · drag to pan"
                % ("⌘" if platform_util.IS_MAC else "Ctrl"))
        label(self, p, hint, size=8, dim=True).pack(pady=(0, 10))

        self.canvas.bind("<ButtonPress-1>", self._grab)
        self.canvas.bind("<B1-Motion>", self._drag_to)
        self.canvas.bind("<ButtonRelease-1>", self._let_go)
        for widget in (self, self.canvas):
            widget.bind("<Control-MouseWheel>", self._wheel_zoom)
            widget.bind("<Command-MouseWheel>", self._wheel_zoom)
            widget.bind("<Control-Button-4>", lambda _e: self.zoom(1))
            widget.bind("<Control-Button-5>", lambda _e: self.zoom(-1))
            widget.bind("<MouseWheel>", self._wheel_scroll)
            widget.bind("<Shift-MouseWheel>", self._wheel_scroll_x)
            from .ui_kit import bind_touchpad
            bind_touchpad(widget, self._touch_scroll)
            widget.bind("<Button-4>", lambda _e: self._scroll(-3))
            widget.bind("<Button-5>", lambda _e: self._scroll(3))
        for key, step in (("<Down>", 3), ("<Up>", -3),
                          ("<Next>", 12), ("<Prior>", -12)):
            self.bind(key, lambda _e, s=step: self._scroll(s))
        for key, step in (("<Right>", 3), ("<Left>", -3)):
            self.bind(key, lambda _e, s=step: self._scroll_x(s))
        for key in ("<plus>", "<KP_Add>", "<equal>"):
            self.bind(key, lambda _e: self.zoom(1))
        for key in ("<minus>", "<KP_Subtract>"):
            self.bind(key, lambda _e: self.zoom(-1))
        self.bind("<0>", lambda _e: self._fit_again())
        self.bind("<Escape>", lambda _e: self.close())
        self.protocol("WM_DELETE_WINDOW", self.close)

    def _explain(self):
        """No picture. Say where the same steps are in words."""
        label(self, self.palette,
              "That guide could not be opened.\n\nSettings ▸ How to add "
              "API keys has the same steps written out.",
              size=10, wraplength=360, justify="left").pack(padx=28,
                                                            pady=(28, 12))
        PillButton(self, "Close", command=self.close, palette=self.palette,
                   kind="secondary", height=36).pack(pady=(0, 20))
        GuideWindow._open[self.which] = self

    # -- size ----------------------------------------------------------
    def _room(self):
        try:
            span = platform_util.room_on_display(
                self.winfo_pointerx(), self.winfo_pointery(),
                fallback=(self.winfo_screenwidth(),
                          self.winfo_screenheight()))
        except Exception:
            span = None
        span = span or (self.winfo_screenwidth(), self.winfo_screenheight())
        return int(span[0] * FILL), int(span[1] * FILL)

    def _fit(self):
        """Open at the step nearest to filling the window's width.

        Nearest rather than largest-that-fits: a guide one notch too big
        that you scroll sideways a little is far more use than one two
        notches too small, which is a picture of a button you cannot read.
        """
        room_w, room_h = self._room()
        wanted = (room_w - 60) / float(max(1, self._source.width))
        self._zoom = min(range(len(ZOOMS)),
                         key=lambda i: abs(ZOOMS[i] - wanted))
        self._paint()
        view_w = min(self._photo.width() + 40, room_w)
        view_h = min(self._photo.height() + 40, room_h - 150)
        try:
            self.canvas.configure(width=max(320, view_w),
                                  height=max(240, view_h))
        except Exception:
            pass

    def _fit_again(self):
        self._fit()
        try:
            self.canvas.xview_moveto(0)
            self.canvas.yview_moveto(0)
        except Exception:
            pass
        return "break"

    def _paint(self):
        """Redraw at the current step. Never raises."""
        try:
            from PIL import Image, ImageTk
            scale = ZOOMS[self._zoom]
            width = max(1, int(self._source.width * scale))
            height = max(1, int(self._source.height * scale))
            shown = self._source if scale == 1.0 else self._source.resize(
                (width, height),
                Image.LANCZOS if scale < 1.0 else Image.BICUBIC)
            self._photo = ImageTk.PhotoImage(shown, master=self)
            self.canvas.itemconfigure(self._item, image=self._photo)
            self.canvas.configure(scrollregion=(0, 0, width, height))
            self.zoom_label.configure(text="%d%%" % round(scale * 100))
        except Exception:
            # A size the machine cannot allocate, or a canvas already gone.
            # Whatever is on screen stays on screen.
            pass

    def zoom(self, step):
        want = max(0, min(len(ZOOMS) - 1, self._zoom + step))
        if want == self._zoom:
            return "break"
        self._zoom = want
        # Coalesced: the wheel sends notches faster than a 2200-pixel
        # picture can be resized, and redrawing on every one of them is
        # how a zoom comes to feel like a hang.
        if self._redraw_job is not None:
            try:
                self.after_cancel(self._redraw_job)
            except Exception:
                pass
        self._redraw_job = self.after(REDRAW_AFTER, self._redraw)
        return "break"

    def _redraw(self):
        self._redraw_job = None
        self._paint()

    # -- moving around --------------------------------------------------
    def _grab(self, event):
        self._drag = (event.x, event.y)
        try:
            self.canvas.scan_mark(event.x, event.y)
        except Exception:
            pass
        return "break"

    def _drag_to(self, event):
        if self._drag is None:
            return "break"
        try:
            self.canvas.scan_dragto(event.x, event.y, gain=1)
        except Exception:
            pass
        return "break"

    def _let_go(self, _event=None):
        self._drag = None
        return "break"

    def _scroll(self, step):
        try:
            self.canvas.yview_scroll(int(step), "units")
        except Exception:
            pass
        return "break"

    def _scroll_x(self, step):
        try:
            self.canvas.xview_scroll(int(step), "units")
        except Exception:
            pass
        return "break"

    def _wheel_scroll(self, event):
        return self._scroll(-3 if getattr(event, "delta", 0) > 0 else 3)

    def _touch_scroll(self, event):
        from .ui_kit import touchpad_deltas
        dx, dy = touchpad_deltas(self.canvas, event)
        try:
            if dy:
                self.canvas.yview_scroll(int(-dy), "pixels")
            if dx:
                self.canvas.xview_scroll(int(-dx), "pixels")
        except Exception:
            pass
        return "break"

    def _wheel_scroll_x(self, event):
        return self._scroll_x(-3 if getattr(event, "delta", 0) > 0 else 3)

    def _wheel_zoom(self, event):
        return self.zoom(1 if getattr(event, "delta", 0) > 0 else -1)

    # -- opening and closing --------------------------------------------
    def _place(self):
        try:
            self.update_idletasks()
            width = self.winfo_reqwidth()
            height = self.winfo_reqheight()
            x = max(0, (self.winfo_screenwidth() - width) // 2)
            y = max(0, (self.winfo_screenheight() - height) // 2 - 30)
            self.geometry("+%d+%d" % (x, y))
        except Exception:
            pass
        # Floating rather than modal, and not `transient`: a transient
        # window is withdrawn whenever its master is, so a guide parented
        # to the settings window vanished the moment somebody closed the
        # settings window to go and follow it.
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def close(self):
        GuideWindow._open.pop(self.which, None)
        if self._redraw_job is not None:
            try:
                self.after_cancel(self._redraw_job)
            except Exception:
                pass
            self._redraw_job = None
        self._photo = None
        try:
            if self._source is not None:
                self._source.close()
        except Exception:
            pass
        self._source = None
        try:
            self.destroy()
        except Exception:
            pass


def show(master, which, palette=None):
    """Open the guide, or bring the one already open forward.

    Pressing the same question mark twice should not stack two identical
    windows on top of each other.
    """
    existing = GuideWindow._open.get(which)
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.lift()
                existing.focus_force()
                return existing
        except Exception:
            pass
        GuideWindow._open.pop(which, None)
    return GuideWindow(master, which, palette=palette)
