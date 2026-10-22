"""Windows Snipping-Tool style region selector.

Each physical monitor gets its own frozen screenshot and its own fullscreen
overlay. A selection can therefore be made entirely within one display,
without squeezing a multi-monitor virtual desktop into one giant window.
"""
import tkinter as tk

from PIL import Image, ImageTk

from . import platform_util

try:
    import mss
except Exception:  # pragma: no cover
    mss = None

make_dpi_aware = platform_util.make_dpi_aware


def _log(message):
    """One line into the app's log. Never raises, never blocks a snip."""
    try:
        from . import config
        with open(config.log_path(), "a", encoding="utf-8") as fh:
            fh.write(str(message).rstrip() + "\n")
    except Exception:
        pass


def describe_displays(monitors, windows=()):
    """What the screen grabber saw, and where the overlays actually went.

    A selection that behaves as though the desk were one enormous screen
    is one of two things and they are not distinguishable by looking at
    it: either the grabber reported the displays wrongly, or it reported
    them correctly and the windows were not put where they were asked to
    go. On a machine with three displays at two different scale factors
    both are possible, and each has a different fix.

    Two numbers per display settle it — what was asked for and what
    happened — and neither can be got from a screenshot of the fault.
    """
    head = "displays   : %d reported" % len(monitors)
    try:
        awareness = platform_util.dpi_awareness()
    except Exception:
        awareness = ""
    if awareness:
        head += " | pixels reported as %s" % awareness
    out = [head]
    for index, info in enumerate(monitors):
        left = int(info.get("left", 0))
        top = int(info.get("top", 0))
        width = int(info.get("width", 0))
        height = int(info.get("height", 0))
        asked = "%dx%d at %+d%+d" % (width, height, left, top)
        got = "not placed"
        if index < len(windows) and windows[index] is not None:
            win = windows[index]
            try:
                win.update_idletasks()
                got = "%dx%d at %+d%+d" % (win.winfo_width(),
                                           win.winfo_height(),
                                           win.winfo_x(), win.winfo_y())
            except Exception:
                got = "unreadable"
        # The scale this display is drawn at. A desk where these differ is
        # the case that fails on two screens and looks perfect on the
        # third, which reads as an intermittent fault and is a settings
        # one — and it cannot be recovered from a screenshot afterwards.
        scaling = 0
        try:
            scaling = platform_util.monitor_scaling(left + width // 2,
                                                    top + height // 2)
        except Exception:
            scaling = 0
        line = "  display %d: grabbed %s | overlay %s" % (index + 1, asked,
                                                          got)
        if scaling:
            line += " | scale %d%%" % scaling
        out.append(line)
    return "\n".join(out)


def _geometry_string(width, height, left, top):
    """Tk geometry placing a window at these desktop coordinates.

    The sign is not the obvious one, and the obvious one is wrong in a way
    that only appears on somebody else's desk. In a Tk geometry string a
    leading minus does not mean a negative coordinate — it means *from the
    far edge of the screen*: "-1920" asks for the window's right edge to
    sit 1920 pixels in from the right of the display. Asking that way for
    a monitor at x = -1920, which is what any display arranged to the left
    of the main one has, measures 1920 from the wrong end of the wrong
    screen and puts that overlay on top of a different monitor. One
    display then carries two overlays and another carries none, and
    dragging behaves as though the whole desk were one screen.

    A negative coordinate is written with both signs — "+-1920" — which
    Tk parses as the number it looks like. Measured, on a 1280-wide
    screen: "-200" places the window at x=780 and "+-200" places it at
    x=-200.
    """
    x = "+%d" % int(left)
    y = "+%d" % int(top)
    return "%dx%d%s%s" % (int(width), int(height), x, y)


def grab_monitors():
    """Capture each physical monitor separately.

    mss.monitors[0] is the union of every display.  Using it for the snip
    overlay makes a multi-monitor desktop one huge bitmap; Tk then tries to
    represent that union in one window, which is where very small selections
    and bad scaling show up.  The picker should instead behave like Windows
    Snipping Tool: one frozen capture and one overlay window per physical
    monitor.
    """
    if mss is None:
        raise RuntimeError("mss is not installed")
    out = []
    with mss.mss() as sct:
        monitors = list(sct.monitors[1:])
        if not monitors:
            monitors = [sct.monitors[0]]
        for index, mon in enumerate(monitors, 1):
            raw = sct.grab(mon)
            image = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            out.append({
                "index": index,
                "left": int(mon["left"]),
                "top": int(mon["top"]),
                "width": int(mon["width"]),
                "height": int(mon["height"]),
                "image": image,
            })
    return out


def grab_virtual_screen():
    """Backward-compatible union capture used by older callers/tests."""
    if mss is None:
        raise RuntimeError("mss is not installed")
    with mss.mss() as sct:
        mon = sct.monitors[0]
        raw = sct.grab(mon)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    return img, mon["left"], mon["top"]


class SnipOverlay:
    """Modal region picker. Call .select() and get a PIL.Image or None."""

    def __init__(self, master=None):
        self.master = master
        self.result = None
        self.origin = (0, 0)      # logical-point coords of the crop
        self.scale = 1.0          # physical pixels per logical point
        self.scale_used = 1.0
        self._start = None
        self._rect = None
        self._rect_shadow = None
        self._grips = None
        self._hint = None
        self._shade = []
        self._size_label = None
        self._size_bg = None

    def select(self):
        try:
            monitors = grab_monitors()
        except Exception:
            return None
        if not monitors:
            return None

        # On Windows the process is made DPI-aware before the controller
        # creates this picker.  mss and Tk therefore use the same physical
        # coordinate space.  macOS still needs its Retina conversion.
        self._monitors = []
        probe = self.master if self.master is not None else tk.Tk()
        temporary = probe is not self.master

        # One independent overlay per physical display. Each monitor has its
        # own screenshot, canvas, scaling and selection state. This prevents
        # a 3-display desktop from being squeezed into one giant selection
        # window.
        for info in monitors:
            full = info["image"]
            if platform_util.IS_MAC:
                scale = platform_util.screen_scale(probe, full.size[0])
            else:
                scale = 1.0
            w = int(full.size[0] / scale)
            h = int(full.size[1] / scale)
            display = full if scale == 1.0 else full.resize(
                (w, h), Image.LANCZOS)

            monitor = {
                "full": full,
                "display": display,
                # The undimmed picture the bright selection patch is cut
                # out of. Splitting the overlay per monitor lost this: the
                # attribute was still read on every drag but no longer set
                # anywhere, so the first mouse-move raised AttributeError
                # inside the Tk callback. Tk swallows that and carries on,
                # which is why the selection frame simply never appeared
                # while the translation itself still worked.
                "bright": display,
                "scale": scale,
                "scale_used": scale,
                "off_x": info["left"],
                "off_y": info["top"],
                "win": None,
                "canvas": None,
                "dim_photo": None,
                "reveal_photo": None,
                "reveal_item": None,
                "reveal_box": None,
                "start": None,
                "rect": None,
                "rect_shadow": None,
                "grips": None,
                "hint": None,
                "hint_bg": None,
                "size_label": None,
                "size_bg": None,
                "cancel_items": [],
            }
            self._monitors.append(monitor)

            win = tk.Toplevel(self.master) if self.master is not None else tk.Toplevel(probe)
            monitor["win"] = win
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            try:
                win.geometry(_geometry_string(w, h, monitor["off_x"],
                                               monitor["off_y"]))
            except Exception:
                win.geometry("%dx%d" % (w, h))
            win.configure(bg="black")
            win.config(cursor="crosshair")

            canvas = tk.Canvas(win, width=w, height=h, highlightthickness=0,
                               bd=0, bg="black", cursor="crosshair")
            canvas.pack(fill="both", expand=True)
            monitor["canvas"] = canvas

            dim = Image.blend(display.convert("RGB"),
                              Image.new("RGB", display.size, (8, 8, 10)), 0.55)
            monitor["dim_photo"] = ImageTk.PhotoImage(dim, master=win)
            canvas.create_image(0, 0, anchor="nw",
                                image=monitor["dim_photo"])
            monitor["reveal_item"] = canvas.create_image(
                0, 0, anchor="nw", state="hidden")

            hint = canvas.create_text(
                w // 2, 44, anchor="n",
                text="Drag to select     Enter for the whole screen     Esc to cancel",
                fill="#f5f5f7", font=("Helvetica Neue", 13))
            monitor["hint"] = hint
            bbox = canvas.bbox(hint)
            if bbox:
                pad = 18
                monitor["hint_bg"] = canvas.create_rectangle(
                    bbox[0] - pad, bbox[1] - 10, bbox[2] + pad,
                    bbox[3] + 10, fill="#1c1c1e", outline="")
                canvas.tag_lower(monitor["hint_bg"], hint)

            cx, cy = w - 74, 30
            monitor["cancel_items"] = [
                canvas.create_oval(cx - 20, cy - 20, cx + 20, cy + 20,
                                   fill="#1c1c1e", outline="#ffffff", width=2),
                canvas.create_text(cx, cy, text="✕", fill="#ffffff",
                                   font=("Helvetica", 17, "bold")),
            ]
            for item in monitor["cancel_items"]:
                canvas.tag_bind(item, "<Button-1>",
                                lambda _e: self._on_cancel())

            canvas.bind("<ButtonPress-1>",
                        lambda e, m=monitor: self._on_press_monitor(m, e))
            canvas.bind("<B1-Motion>",
                        lambda e, m=monitor: self._on_drag_monitor(m, e))
            canvas.bind("<ButtonRelease-1>",
                        lambda e, m=monitor: self._on_release_monitor(m, e))
            canvas.bind("<Double-Button-1>",
                        lambda e, m=monitor: self._on_full_monitor(m, e))
            canvas.bind("<Button-3>",
                        lambda _e: self._on_cancel())
            win.bind("<Button-3>", self._on_cancel)
            win.bind("<Enter>",
                     lambda _e, m=monitor: self._set_active_monitor(m))
            canvas.bind("<Enter>",
                        lambda _e, m=monitor: self._set_active_monitor(m))
            win.bind("<Escape>", self._on_cancel)
            canvas.bind("<Escape>", self._on_cancel)
            win.bind("<Return>", self._on_full)
            canvas.bind("<Return>", self._on_full)

        if temporary:
            probe.withdraw()

        # Keep one process-wide binding for keyboard cancellation/whole-screen
        # selection. The pointer-over-monitor state determines which display
        # Return applies to. Unlike the previous implementation, there is no
        # bind_all installed separately for every monitor.
        self._active_monitor = self._monitors[0]
        self._set_active_monitor(self._monitors[0])
        try:
            root_for_bind = self.master if self.master is not None else probe
            root_for_bind.bind_all("<Escape>", self._on_cancel)
            root_for_bind.bind_all("<Return>", self._on_full)
        except Exception:
            pass

        # Bring the first monitor forward initially; moving the mouse onto
        # another display immediately switches the keyboard target.
        first = self._monitors[0]["win"]
        try:
            first.focus_force()
            first.lift()
        except Exception:
            pass

        # Ask macOS for the front again, now that there is something to
        # bring forward.
        #
        # The controller already asks before building these, and that is
        # the wrong moment on its own: activating an application raises the
        # windows it owns *at that instant*, and at that instant it owns no
        # overlay. Windows created afterwards are ordered against whatever
        # is in front, which — when the shortcut was pressed over another
        # app — is that other app. The overlay ends up correctly sized,
        # correctly placed, topmost within an application that is not in
        # front, and invisible.
        #
        # Twice, then: once so the app is frontmost while the windows are
        # built, once so the built windows are raised. It costs a call.
        try:
            _log("  activation: %s" % platform_util.become_foreground_app())
            for monitor in self._monitors:
                win = monitor["win"]
                win.attributes("-topmost", True)
                win.lift()
        except Exception:
            pass
        # Deliberately no grab_set(). A Tk grab routes every mouse event in
        # the application to the one window that holds it — which is right
        # for a single overlay covering everything, and wrong now that each
        # display has its own. On a three-monitor desk the grab on the first
        # window swallowed the clicks meant for the other two, so one screen
        # could be dragged on and the rest only dimmed.
        #
        # Nothing is lost by dropping it: each overlay is borderless and
        # always-on-top, so it already receives the clicks that land on it.
        # Kept so they can be cancelled. Left to run, the last of them fires
        # half a second after the overlay may already have been closed and
        # destroyed — Tk swallows the resulting error and the tests print it
        # while still passing, which is the state a thing is in just before
        # it stops being harmless.
        # Written every time the picker opens, because the fault it is for
        # only shows on somebody else's desk and only sometimes. It costs a
        # few lines of a text file and it is the difference between fixing
        # this and guessing at it again.
        try:
            _log(describe_displays(
                monitors, [m.get("win") for m in self._monitors]))
        except Exception:
            pass

        # Whether the overlay is actually on screen, not merely built.
        #
        # The line above reports its size and position, and reported them
        # correctly for an overlay nobody could see — geometry is what the
        # window was asked for, not what happened to it. `viewable` is the
        # answer to the question people actually ask, which is "did
        # anything appear".
        try:
            for index, monitor in enumerate(self._monitors, start=1):
                win = monitor["win"]
                win.update_idletasks()
                _log("  overlay %d: mapped=%s viewable=%s"
                     % (index, bool(win.winfo_ismapped()),
                        bool(win.winfo_viewable())))
        except Exception:
            pass

        self._focus_jobs = []
        for monitor in self._monitors:
            win = monitor["win"]
            for delay in (60, 200, 500):
                self._focus_jobs.append(
                    (win, win.after(delay,
                                    lambda w=win: self._retake_focus_window(w))))

        # The Tk bindings above cover every platform where a borderless
        # window can hold keyboard focus. macOS is not one of them, so
        # there Escape is also read straight from the window server.
        self._watch_job = None
        if platform_util.IS_MAC:
            self._watch_keys(first)

        if self.master is not None:
            # A hidden sentinel lets every monitor close the same modal wait
            # without waiting on just one of the Toplevels.
            self._sentinel = tk.Toplevel(self.master)
            self._sentinel.withdraw()
            self.master.wait_window(self._sentinel)
        else:
            probe.mainloop()
            try:
                probe.destroy()
            except Exception:
                pass
        return self.result

    def _set_active_monitor(self, monitor):
        # Not while a drag is running. <Enter> fires when the pointer
        # crosses onto another display, and switching then would swap the
        # start point, the canvas and the picture out from under the drag
        # in progress — the selection would jump or vanish mid-stroke.
        # A drag ends on the monitor it began on.
        if monitor is not getattr(self, "_active_monitor", None) \
                and getattr(self, "_start", None) is not None:
            return
        self._active_monitor = monitor
        self._activate_monitor(monitor)

    def _activate_monitor(self, monitor):
        """Expose one monitor's state through the legacy drawing methods."""
        self._active_monitor = monitor
        self.full = monitor["full"]
        self.display = monitor["display"]
        self._bright = monitor["bright"]
        self.scale = monitor["scale"]
        self.scale_used = monitor["scale_used"]
        self.off_x = monitor["off_x"]
        self.off_y = monitor["off_y"]
        self.win = monitor["win"]
        self.canvas = monitor["canvas"]
        self._dim_photo = monitor["dim_photo"]
        self._reveal_photo = monitor["reveal_photo"]
        self._reveal_item = monitor["reveal_item"]
        self._reveal_box = monitor["reveal_box"]
        self._start = monitor["start"]
        self._rect = monitor["rect"]
        self._rect_shadow = monitor["rect_shadow"]
        self._grips = monitor["grips"]
        self._hint = monitor["hint"]
        self._hint_bg = monitor["hint_bg"]
        self._size_label = monitor["size_label"]
        self._size_bg = monitor["size_bg"]
        self._cancel_items = monitor["cancel_items"]

    def _save_monitor(self, monitor):
        """Copy legacy drawing state back into the monitor record."""
        monitor["reveal_photo"] = self._reveal_photo
        monitor["reveal_box"] = self._reveal_box
        monitor["start"] = self._start
        monitor["rect"] = self._rect
        monitor["rect_shadow"] = self._rect_shadow
        monitor["grips"] = self._grips
        monitor["hint"] = self._hint
        monitor["hint_bg"] = self._hint_bg
        monitor["size_label"] = self._size_label
        monitor["size_bg"] = self._size_bg
        monitor["scale_used"] = self.scale_used

    def _watch_keys(self, win):
        """Poll for Escape on macOS, where the overlay never gets focus.

        60ms is under the time anybody holds a key down, and the check is a
        single call into the window server — cheap enough to run for the few
        seconds an overlay is on screen, and it stops the moment it closes.
        """
        self._watch_job = None
        try:
            if not win.winfo_exists():
                return
        except Exception:
            return
        if platform_util.key_is_down("escape"):
            self._on_cancel()
            return
        try:
            self._watch_job = win.after(60, lambda: self._watch_keys(win))
        except Exception:
            self._watch_job = None

    def _cancel_focus_jobs(self):
        """Drop the pending focus retries before their windows go away."""
        jobs, self._focus_jobs = getattr(self, "_focus_jobs", []), []
        for win, job in jobs:
            try:
                win.after_cancel(job)
            except Exception:
                pass

    def _stop_watching_keys(self):
        job, self._watch_job = getattr(self, "_watch_job", None), None
        if job is None:
            return
        for monitor in getattr(self, "_monitors", []):
            win = monitor.get("win")
            if win is None:
                continue
            try:
                win.after_cancel(job)
                return
            except Exception:
                continue

    def _retake_focus_window(self, win):
        try:
            if win.winfo_exists():
                win.lift()
                win.focus_force()
        except Exception:
            pass

    def _on_press_monitor(self, monitor, event):
        # A new press always wins, whatever a previous unfinished drag left
        # behind — otherwise the guard in _set_active_monitor could refuse
        # to switch to the monitor being clicked on.
        self._start = None
        self._set_active_monitor(monitor)
        self._on_press(event)
        self._save_monitor(monitor)

    def _on_drag_monitor(self, monitor, event):
        self._set_active_monitor(monitor)
        self._on_drag(event)
        self._save_monitor(monitor)

    def _on_release_monitor(self, monitor, event):
        self._set_active_monitor(monitor)
        self._on_release(event)
        self._save_monitor(monitor)

    def _on_full_monitor(self, monitor, event=None):
        self._set_active_monitor(monitor)
        self._on_full(event)


    # -- events -------------------------------------------------------
    def _clear_hint(self):
        for item in ("_hint", "_hint_bg"):
            obj = getattr(self, item, None)
            if obj is not None:
                try:
                    self.canvas.delete(obj)
                except Exception:
                    pass
                setattr(self, item, None)

    # -- selection frame ------------------------------------------------
    CORNER = 14          # radius of the rounded corners
    GRIP = 18            # length of the corner marks

    def _frame_items(self):
        for name in ("_rect", "_rect_shadow", "_grips"):
            item = getattr(self, name, None)
            if item is None:
                continue
            for obj in (item if isinstance(item, list) else [item]):
                try:
                    self.canvas.delete(obj)
                except Exception:
                    pass
            setattr(self, name, None)

    BRACKET = 6          # thickness of the corner marks

    def _bracket_items(self, left, top, right, bottom, colour, width,
                       edge_width):
        """The four corner marks and the hairline between them.

        This is Squint's own mark: a thin rounded rectangle with four
        thick elbows at the corners. The app is called Squint and its icon
        is the shape you make when you frame something to look at it
        closely, so the thing you drag to frame something should be that
        shape rather than a generic marquee.

        Drawn twice by the caller, dark under light. The logo is black on
        cream, which is unreadable over a dark web page — the outline has
        to be visible on top of whatever happens to be underneath it, and
        that beats matching the brand exactly.
        """
        radius = min(self.CORNER, max(2, (right - left) // 3),
                     max(2, (bottom - top) // 3))
        grip = min(self.GRIP, max(2, (right - left) // 3 - radius),
                   max(2, (bottom - top) // 3 - radius))
        items = []
        arc = self.canvas.create_arc
        line = self.canvas.create_line

        for x, y, start, dx, dy in (
                (left, top, 90, 1, 1),               # top-left
                (right - 2 * radius, top, 0, -1, 1),  # top-right
                (left, bottom - 2 * radius, 180, 1, -1),
                (right - 2 * radius, bottom - 2 * radius, 270, -1, -1)):
            items.append(arc(x, y, x + 2 * radius, y + 2 * radius,
                             start=start, extent=90, style="arc",
                             outline=colour, width=width))
            # The straight run out of each elbow, along both edges.
            cx = x if dx > 0 else x + 2 * radius
            cy = y if dy > 0 else y + 2 * radius
            # Butt caps, not round. Tk strokes an arc with flat ends, so a
            # round-capped line starting at the arc's endpoint adds a
            # semicircle half a stroke deep *backwards* over the join — and
            # since the arc is curving away underneath it, that bulge
            # escapes the curve as a little spike at each corner. It is
            # worst on the black underlay, which is the widest stroke. Flat
            # ends meet the arc's flat ends flush and tangentially, which
            # is one continuous mark with no join visible at all.
            items.append(line(cx + dx * radius, cy,
                              cx + dx * (radius + grip), cy,
                              fill=colour, width=width, capstyle="butt"))
            items.append(line(cx, cy + dy * radius,
                              cx, cy + dy * (radius + grip),
                              fill=colour, width=width, capstyle="butt"))

        # Four straight runs between the elbows, not a rectangle.
        #
        # A rectangle was the obvious way to join them and it put a sharp
        # corner back at each end — a little square poking out past the
        # arc, which is the one thing the rounded mark exists to avoid. The
        # corners belong to the arcs; the hairline only spans the flats.
        items.append(line(left + radius, top, right - radius, top,
                          fill=colour, width=edge_width))
        items.append(line(left + radius, bottom, right - radius, bottom,
                          fill=colour, width=edge_width))
        items.append(line(left, top + radius, left, bottom - radius,
                          fill=colour, width=edge_width))
        items.append(line(right, top + radius, right, bottom - radius,
                          fill=colour, width=edge_width))
        return items

    def _draw_frame(self, x0, y0, x1, y1):
        """Draw the selection frame — Squint's own corner marks.

        The bright reveal image is already underneath this, so the frame
        must be normal canvas vector items above it.
        """
        left, right = sorted((int(x0), int(x1)))
        top, bottom = sorted((int(y0), int(y1)))
        self._frame_items()

        # Dark underneath, light on top: the same two-tone trick the plain
        # rectangle used, and the only reason this is legible over both a
        # white article and a black one.
        self._rect_shadow = self._bracket_items(
            left, top, right, bottom, "#000000", self.BRACKET + 3, 3)
        self._rect = self._bracket_items(
            left, top, right, bottom, "#ffffff", self.BRACKET, 1)

        # Explicitly raised so later canvas items from the reveal path or
        # another redraw can never cover the frame.
        try:
            for item in self._rect_shadow + self._rect:
                self.canvas.tag_raise(item)
        except Exception:
            pass
        self._grips = None

    def _show_size(self, box):
        left, top, right, bottom = box
        text = "%d × %d" % (right - left, bottom - top)
        x = min(right + 12, self.display.size[0] - 60)
        y = max(top - 14, 14)
        if getattr(self, "_size_label", None) is None:
            self._size_bg = self.canvas.create_rectangle(
                0, 0, 0, 0, fill="#1c1c1e", outline="", width=0)
            self._size_label = self.canvas.create_text(
                x, y, text=text, fill="#ffffff", anchor="w",
                font=("Helvetica", 12, "bold"))
        else:
            self.canvas.itemconfig(self._size_label, text=text)
            self.canvas.coords(self._size_label, x, y)
        bbox = self.canvas.bbox(self._size_label)
        if bbox:
            self.canvas.coords(self._size_bg, bbox[0] - 8, bbox[1] - 5,
                               bbox[2] + 8, bbox[3] + 5)
            self.canvas.tag_raise(self._size_bg)
            self.canvas.tag_raise(self._size_label)

    def _on_press(self, event):
        self._clear_hint()
        self._start = (event.x, event.y)
        self._frame_items()

    def _set_shade(self, box):
        """Show `box` at full brightness. Pass None to dim the whole screen.

        The name is kept from when this moved four shading rectangles; it
        now moves the one bright patch instead.
        """
        if box is None:
            self.canvas.itemconfigure(self._reveal_item, state="hidden")
            self._reveal_box = None
            return
        if box == self._reveal_box:
            return
        left, top, right, bottom = box
        width, height = self.display.size
        left, top = max(0, int(left)), max(0, int(top))
        right, bottom = min(width, int(right)), min(height, int(bottom))
        if right - left < 1 or bottom - top < 1:
            self.canvas.itemconfigure(self._reveal_item, state="hidden")
            self._reveal_box = None
            return
        patch = self._bright.crop((left, top, right, bottom))
        # Held on the instance: Tk keeps only a weak reference to the image
        # behind a canvas item, so a photo that goes out of scope here would
        # be collected and the patch would flicker away.
        self._reveal_photo = ImageTk.PhotoImage(patch, master=self.win)
        self.canvas.itemconfigure(self._reveal_item,
                                  image=self._reveal_photo, state="normal")
        # No restacking needed: _draw_frame deletes and recreates the frame
        # on every drag event, so those items are always newer, and newer
        # canvas items sit on top.
        self.canvas.coords(self._reveal_item, left, top)
        self._reveal_box = box

    def _on_drag(self, event):
        if self._start is None:
            return
        x0, y0 = self._start
        box = self._box(x0, y0, event.x, event.y)
        if box is None:
            return
        self._set_shade(box)
        # Redrawn rather than moved: a rounded frame is a spline, so its
        # points have to be recomputed for each new size.
        self._draw_frame(x0, y0, event.x, event.y)
        self._show_size(box)

    def _on_release(self, event):
        if self._start is None:
            return
        x0, y0 = self._start
        box = self._box(x0, y0, event.x, event.y)
        if box is None:
            # A click with no drag means "I did not want this after all".
            # Leaving the dimmed screen up with nothing selected is a trap
            # when the keyboard shortcut is not reaching the window.
            if abs(event.x - x0) < 5 and abs(event.y - y0) < 5:
                self._on_cancel()
                return
            self._start = None
            return
        # Crop from the full-resolution capture, but report the origin in
        # logical points, because that is what window placement expects.
        scaled = tuple(int(round(v * self.scale)) for v in box)
        self.result = self.full.crop(scaled)
        # The screen it was cut from, for a watermark stamped across the
        # page in a grid - too little of the grid may be in the snip to
        # see it repeat (app/stamp.py).
        try:
            from . import stamp
            self.result.info["stamp_whole"] = stamp.remember_whole(self.full)
            self.result.info["stamp_box"] = scaled
        except Exception:
            pass
        self.origin = (self.off_x / self.scale + box[0],
                       self.off_y / self.scale + box[1])
        self.scale_used = self.scale
        self._close()

    def _on_full(self, _event=None):
        monitor = self._active_monitor
        self._activate_monitor(monitor)
        self.result = self.full
        self.origin = (self.off_x / self.scale, self.off_y / self.scale)
        self.scale_used = self.scale
        self._save_monitor(monitor)
        self._close()

    def _on_cancel(self, _event=None):
        self.result = None
        self._close()

    def _box(self, x0, y0, x1, y1):
        left, right = sorted((int(x0), int(x1)))
        top, bottom = sorted((int(y0), int(y1)))
        w, h = self.display.size
        left = max(0, min(left, w))
        right = max(0, min(right, w))
        top = max(0, min(top, h))
        bottom = max(0, min(bottom, h))
        if right - left < 5 or bottom - top < 5:
            return None
        return (left, top, right, bottom)

    def _retake_focus(self):
        try:
            if not self.win.winfo_exists():
                return
            self.win.lift()
            self.win.focus_force()
            self.canvas.focus_set()
        except Exception:
            pass

    def _close(self):
        """Close every monitor overlay and end the modal selection."""
        self._stop_watching_keys()
        self._cancel_focus_jobs()
        root = self.master
        try:
            if root is None and getattr(self, "_monitors", None):
                root = self._monitors[0]["win"].winfo_toplevel()
        except Exception:
            pass
        for sequence in ("<Escape>", "<Return>"):
            try:
                if root is not None:
                    root.unbind_all(sequence)
            except Exception:
                pass
        for monitor in getattr(self, "_monitors", []):
            win = monitor.get("win")
            if win is None:
                continue
            try:
                win.grab_release()
            except Exception:
                pass
            try:
                win.destroy()
            except Exception:
                pass
        sentinel = getattr(self, "_sentinel", None)
        if sentinel is not None:
            try:
                sentinel.destroy()
            except Exception:
                pass
            self._sentinel = None
