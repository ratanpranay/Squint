"""The floating card that appears after a snip, and the working toast.

Both are borderless windows shaped by a drawn rounded background rather than
by the OS, so they get the same soft corners everywhere and can sit on the
frosted backdrop without a grey rectangle around them.
"""
import collections
import sys
import math
import threading
import time
import unicodedata
import tkinter as tk
import tkinter.font as tkfont

from . import config, pinch as pinch_mod, platform_util
from . import theme as theme_mod, win_effects
from .ui_kit import PillButton, plate_item, rounded, set_plate, _blend


def _at(width, height, x, y):
    """A Tk geometry string that means these coordinates.

    A leading minus in a Tk geometry is not a negative number — it is a
    distance from the far edge of the screen. Every display arranged to
    the left of or above the main one has negative coordinates, so a
    window placed with the obvious spelling lands on a different monitor
    from the one it was meant for. Both signs is how a negative
    coordinate is written: "+-1920".
    """
    return "%dx%d+%d+%d" % (int(width), int(height), int(x), int(y))


# The rungs of the zoom ladder, and how far apart they are. Six per cent
# each, twenty of them, life size up to three times it. Built here rather
# than in the class body because a comprehension there cannot see the
# names beside it.
_ZOOM_RATIO = 1.06
_ZOOM_LADDER = tuple(round(_ZOOM_RATIO ** rung, 4) for rung in range(20))


def _log_zoom_failure():
    """Write a zoom failure to the log instead of dropping it.

    Every path here caught Exception and returned quietly, so a zoom that
    could not run and a zoom that was never wired up looked identical from
    the outside — and identical in the log, which said nothing at all.
    """
    try:
        import traceback
        from .config import log_path
        with open(log_path(), "a", encoding="utf-8") as fh:
            fh.write("overlay zoom failed:\n" + traceback.format_exc() + "\n")
    except Exception:
        pass

CFG = config.CONFIG
RADIUS = 16

# How often the card asks the window server whether Escape is held. The
# same cadence the click watcher uses — about eight times a second, which
# is faster than anyone can press and release a key without meaning it.
ESCAPE_POLL = 120


class _Floating(tk.Toplevel):
    """Shared plumbing: shaped background, drag-to-move, glass."""

    def __init__(self, master, palette, radius=RADIUS):
        super().__init__(master)
        self.palette = palette
        self.radius = radius
        self._drag = None
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        # Matching the card colour means the corners left over after the
        # region clip never flash a different shade.
        self.configure(bg=palette["surface"])

        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0,
                                bg=palette["surface"])
        self.canvas.pack(fill="both", expand=True)
        self._bg_id = plate_item(self.canvas)
        self._bg_photo = None
        self.body = tk.Frame(self.canvas, bg=palette["surface"])
        self._body_id = self.canvas.create_window(0, 0, anchor="nw",
                                                  window=self.body)
        self.canvas.bind("<Configure>", self._paint)

    def finalize(self):
        """Size the window to its content.

        A Canvas does not grow to fit the items drawn on it, and the body
        frame lives inside a canvas *item*, so neither the canvas nor the
        toplevel learns how big the content is. Measuring the body and
        setting the geometry explicitly is what makes the card appear at all.
        """
        self.body.update_idletasks()
        w = max(120, self.body.winfo_reqwidth() + 2)
        h = max(60, self.body.winfo_reqheight() + 2)
        self.canvas.configure(width=w, height=h)
        self.geometry("%dx%d" % (w, h))
        self.update_idletasks()
        self._paint()
        if CFG.get("window_effects", False):
            win_effects.round_region(self, self.radius)
        return w, h

    def _paint(self, _event=None):
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if w < 4 or h < 4:
            return
        p = self.palette
        outline = _blend(p["text"], p["surface"], 0.14)
        self._bg_photo = set_plate(self.canvas, self._bg_id, 0, 0, w, h,
                                   self.radius, p["surface"], outline)
        self.canvas.coords(self._body_id, 1, 1)
        self.canvas.itemconfig(self._body_id, width=w - 2, height=h - 2)

    def enable_drag(self, *widgets):
        for widget in widgets:
            widget.bind("<ButtonPress-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)

    def _drag_start(self, event):
        self._drag = (event.x_root - self.winfo_x(),
                      event.y_root - self.winfo_y())

    def _drag_move(self, event):
        if not self._drag:
            return
        dx, dy = self._drag
        self.geometry("+%d+%d" % (event.x_root - dx, event.y_root - dy))

    def place_near_cursor(self, offset=(18, 18)):
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        try:
            x = self.winfo_pointerx() + offset[0]
            y = self.winfo_pointery() + offset[1]
        except Exception:
            x = y = 120
        try:
            vx, vy = self.winfo_vrootx(), self.winfo_vrooty()
            vw, vh = self.winfo_vrootwidth(), self.winfo_vrootheight()
        except Exception:
            vx = vy = 0
            vw, vh = self.winfo_screenwidth(), self.winfo_screenheight()
        if x + w > vx + vw:
            x = x - w - 36
        if y + h > vy + vh:
            y = y - h - 36
        x = max(vx, min(int(x), vx + vw - w))
        y = max(vy, min(int(y), vy + vh - h))
        self.geometry("+%d+%d" % (x, y))

    def apply_glass(self, alpha=None):
        # Off unless explicitly enabled — see the note in ui_main.
        if not CFG.get("window_effects", False):
            return
        win_effects.set_opacity(self, alpha or self.palette["alpha"])


class ResultPopup(_Floating):
    """The translation card. Esc closes; drag the header to move it."""

    _open = []

    def __init__(self, master, translated, original="", meta="",
                 show_original=True, font_size=12, palette=None,
                 kind="result", engine=""):
        palette = palette or theme_mod.resolve(CFG.get("theme", "auto"))
        super().__init__(master, palette)
        p = self.palette
        self.kind = kind
        accent = p["danger"] if kind == "error" else p["accent"]

        pad = tk.Frame(self.body, bg=p["surface"])
        pad.pack(fill="both", expand=True, padx=18, pady=14)

        # header
        header = tk.Frame(pad, bg=p["surface"])
        header.pack(fill="x")
        dot = tk.Canvas(header, width=8, height=8, highlightthickness=0,
                        bd=0, bg=p["surface"])
        dot.create_oval(0, 0, 7, 7, fill=accent, outline="")
        dot.pack(side="left", pady=(0, 1))
        self.meta_label = tk.Label(
            header, text=meta or "Translation", bg=p["surface"],
            fg=p["text_dim"], font=theme_mod.font(self, 9))
        self.meta_label.pack(side="left", padx=8)
        close = tk.Label(header, text="✕", bg=p["surface"], fg=p["text_faint"],
                         font=theme_mod.font(self, 10), cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda _e: self.close())
        close.bind("<Enter>", lambda _e: close.configure(fg=p["danger"]))
        close.bind("<Leave>", lambda _e: close.configure(fg=p["text_faint"]))
        self.enable_drag(header, self.meta_label)

        # translation
        self.font = tkfont.Font(family=theme_mod.body_family(self),
                                size=font_size)
        self.text = tk.Text(
            pad, wrap="word", bd=0, highlightthickness=0, relief="flat",
            bg=p["surface"], fg=p["text"], font=self.font,
            insertbackground=p["accent"], selectbackground=p["accent"],
            selectforeground=p["accent_text"], padx=0, pady=0,
            spacing3=4, height=1, cursor="xterm")
        self.text.insert("1.0", translated or "(nothing to translate)")
        self.text.pack(fill="both", expand=True, pady=(10, 0))

        # detected original
        self.original = original or ""
        self.orig_text = None
        if self.original and show_original:
            tk.Frame(pad, bg=p["separator"], height=1).pack(
                fill="x", pady=(12, 10))
            tk.Label(pad, text="DETECTED", bg=p["surface"], fg=p["text_faint"],
                     font=theme_mod.font(self, 8, "bold")).pack(anchor="w")
            self.orig_text = tk.Text(
                pad, wrap="word", bd=0, highlightthickness=0, relief="flat",
                bg=p["surface"], fg=p["text_dim"],
                font=theme_mod.font(self, max(8, font_size - 2)),
                padx=0, pady=0, height=1)
            self.orig_text.insert("1.0", self.original)
            self.orig_text.pack(fill="x", pady=(4, 0))

        # Which engine produced this. The engines available here differ
        # visibly in quality — Google, an LLM, or a model running on this
        # machine — so the answer to "why does this read oddly?" should not
        # require opening a log.
        if engine and kind != "error":
            tk.Label(pad, text=engine, bg=p["surface"], fg=p["text_faint"],
                     font=theme_mod.font(self, 8)).pack(anchor="w",
                                                        pady=(8, 0))

        # actions
        actions = tk.Frame(pad, bg=p["surface"])
        actions.pack(fill="x", pady=(14, 0))
        self.status = tk.Label(actions, text="", bg=p["surface"],
                               fg=p["success"], font=theme_mod.font(self, 9))
        self.status.pack(side="left")
        if kind == "error":
            PillButton(actions, "Close", command=self.close, palette=p,
                       kind="secondary", height=32, font_size=9, pad_x=20,
                       bg=p["surface"]).pack(side="right")
        else:
            PillButton(actions, "Copy", command=self.copy, palette=p,
                       kind="primary", height=32, font_size=9, pad_x=20,
                       bg=p["surface"]).pack(side="right")
            PillButton(actions, "Close", command=self.close, palette=p,
                       kind="ghost", height=32, font_size=9, pad_x=18,
                       bg=p["surface"]).pack(side="right", padx=(0, 6))

        self.bind("<Escape>", lambda _e: self.close())
        # No app-wide Escape binding here. bind_all replaces whatever else
        # owns the sequence, and the snip overlay's Escape — the one that
        # rescues you from a dimmed screen — is app-wide by necessity.
        # Taking it over to close a card that can be clicked away was a
        # straight regression.
        self.bind("<FocusOut>", self._maybe_close)
        self.bind_all("<Button-1>", self._click_elsewhere, add="+")
        # bind_all is this *application* wide, not screen wide: a click on
        # Outlook or a browser is delivered to that program and Tk never
        # hears it, so the card sat over the page it had just translated.
        # This asks the OS about the button instead.
        from . import click_watch
        self._watch = click_watch.Watcher(self, self._clicked_anywhere)
        self._autosize(font_size)
        self.finalize()
        self.place_near_cursor()
        self.apply_glass()
        ResultPopup._open.append(self)
        self.after(40, self._focus)
        # Nothing may dismiss the card for its first half-second. Whatever
        # focus and click events the window server generates while a window
        # is appearing, none of them are the user deciding they are done
        # reading.
        self._armed = False
        self.after(500, self._arm)
        # It comes up above everything so it cannot appear behind the thing
        # it is translating — but it does not stay there. A card that
        # floats over every other window until dismissed is a card you have
        # to deal with before you can get on with your work.
        self.after(1500, self._release_topmost)

    def _arm(self):
        self._armed = True
        try:
            self._watch.start()
        except Exception:
            pass

    def _release_topmost(self):
        try:
            if self.winfo_exists():
                self.attributes("-topmost", False)
        except Exception:
            pass

    def _clicked_anywhere(self):
        """A click somewhere on the screen, from the OS rather than Tk."""
        if not getattr(self, "_armed", False):
            return
        try:
            if not self.winfo_exists():
                return
            x, y = self.winfo_pointerx(), self.winfo_pointery()
            left, top = self.winfo_rootx(), self.winfo_rooty()
            if (left <= x <= left + self.winfo_width()
                    and top <= y <= top + self.winfo_height()):
                return
        except Exception:
            return
        if CFG.get("close_on_click_away", True):
            self.close()

    def _autosize(self, font_size):
        """The card fits the translation: a short phrase a small card, a
        paragraph a larger one, never cut off.

        It used to guess the number of lines from the number of characters,
        which counts a Korean or Chinese character as one letter when it is
        drawn about twice as wide - so a paragraph of Korean was given three
        lines and its end was cut off. Now the width is chosen from the
        text (wide characters counted as two), and the height is what the
        text actually takes when laid out at that width, up to two thirds
        of the screen; past that it scrolls."""
        content = self.text.get("1.0", "end-1c")

        def units(line):
            return sum(2 if unicodedata.east_asian_width(c) in ("W", "F")
                       else 1 for c in line)
        longest = max((units(line) for line in content.splitlines()),
                      default=20)
        chars = max(24, min(60, longest + 2))
        try:
            screen_h = self.winfo_screenheight()
            line_h = max(1, self.font.metrics("linespace") + 4)
            max_lines = max(4, int(screen_h * 0.66 / line_h) - 6)
        except Exception:
            max_lines = 18

        def fit(widget, text, cap):
            widget.configure(width=chars, height=1)
            lines = None
            try:
                widget.update_idletasks()
                got = widget.count("1.0", "end", "displaylines")
                lines = got[0] if isinstance(got, tuple) else got
            except Exception:
                lines = None
            if not lines:
                per = max(1, chars)
                lines = sum(max(1, -(-units(para) // per))
                            for para in (text or " ").split("\n"))
            widget.configure(height=max(1, min(int(lines), cap)))

        fit(self.text, content, max_lines)
        if self.orig_text is not None:
            fit(self.orig_text, self.original, 5)
        self.update_idletasks()

    def _focus(self):
        """Take the keyboard — except on macOS, where taking it takes far
        more than the keyboard.

        `focus_force` does not focus a window on macOS so much as activate
        the *application* that owns it, and activating an application
        raises every window it has. So pressing the shortcut over a
        sentence in a browser brought the whole of Squint forward — the
        settings window the user had left open two hours ago included —
        and then drew the card on top of it. What they asked for was a
        translation of one sentence; what they got was their work covered
        by an app they were not using.

        The card does not need the keyboard. It has a Copy button and a
        Close button, it is dismissed by clicking anywhere else — which is
        watched through the OS, not through focus — and the one thing that
        would be lost, Escape, is read from the window server instead. That
        is the same route the snip overlay already takes for the same
        reason: a borderless window on macOS never becomes the key window,
        so a key press is never delivered to it however hard Tk is asked.
        """
        if platform_util.IS_MAC:
            self._watch_escape()
            return
        try:
            self.focus_force()
            self.text.focus_set()
        except Exception:
            pass

    def _watch_escape(self):
        """Escape, asked of the window server rather than waited for.

        Not `bind_all`: that is application-wide and would take the
        sequence away from the snip overlay, whose Escape is the one that
        rescues you from a dimmed screen.
        """
        self._escape_job = None
        try:
            if not self.winfo_exists():
                return
            if platform_util.key_is_down("escape"):
                self.close()
                return
            self._escape_job = self.after(ESCAPE_POLL, self._watch_escape)
        except Exception:
            pass

    def _stop_watching_escape(self):
        job, self._escape_job = getattr(self, "_escape_job", None), None
        if job is None:
            return
        try:
            self.after_cancel(job)
        except Exception:
            pass

    def _maybe_close(self, _event=None):
        """Losing focus is not the same as being dismissed.

        This used to close the card. On macOS a borderless window belonging
        to a process that is not a foreground app is handed focus and then
        has it taken straight back by the window server — so the card was
        told it had lost focus a moment after appearing and closed itself.
        The translation flashed up and vanished, and the only way to read it
        was to hold the shortcut down.

        A real dismissal is a click somewhere else, which is detected
        directly in _click_elsewhere. Focus is not evidence of anything
        here, so nothing happens on it.
        """
        return

    def _click_elsewhere(self, event):
        """Close when a click lands outside this card.

        Checked against the card's own rectangle rather than trusting the
        event's widget: the click may be delivered to a child, or to the
        overlay behind, and either way what matters is where it landed.
        """
        if not getattr(self, "_armed", False):
            return
        try:
            # An app-wide binding outlives the window that made it, so the
            # first thing to check is whether this card still exists.
            if not self.winfo_exists():
                return
            x, y = event.x_root, event.y_root
            left, top = self.winfo_rootx(), self.winfo_rooty()
            if (left <= x <= left + self.winfo_width()
                    and top <= y <= top + self.winfo_height()):
                return
        except Exception:
            return
        if CFG.get("close_on_click_away", True):
            self.close()

    def copy(self):
        content = self.text.get("1.0", "end-1c")
        try:
            self.clipboard_clear()
            self.clipboard_append(content)
            self.update()
            self.status.configure(text="Copied")
            self.after(1600, lambda: self.status.configure(text=""))
        except Exception:
            self.status.configure(text="Could not access clipboard")

    def close(self):
        # Stop the polls first: a timer that outlives its window keeps
        # firing into nothing.
        try:
            self._watch.stop()
        except Exception:
            pass
        self._stop_watching_escape()
        try:
            ResultPopup._open.remove(self)
        except ValueError:
            pass
        try:
            self.destroy()
        except Exception:
            pass

    @classmethod
    def close_all(cls):
        for popup in list(cls._open):
            popup.close()


class StatusToast(_Floating):
    """Small 'working…' pill so the shortcut never feels dead."""

    def __init__(self, master, message="Working…", palette=None):
        palette = palette or theme_mod.resolve(CFG.get("theme", "auto"))
        super().__init__(master, palette, radius=18)
        p = self.palette
        row = tk.Frame(self.body, bg=p["surface"])
        row.pack(fill="both", expand=True, padx=18, pady=12)
        self.spinner = Spinner(row, p)
        self.spinner.pack(side="left", padx=(0, 10))
        self.label = tk.Label(row, text=message, bg=p["surface"], fg=p["text"],
                              font=theme_mod.font(self, 10))
        self.label.pack(side="left")
        self.finalize()
        self.place_near_cursor()
        self.apply_glass()
        self.spinner.start()

    def set(self, message):
        if getattr(self, "_on_cancel", None) is not None:
            message = message + "   \u00d7"
        try:
            self.label.configure(text=message)
            self.finalize()
        except Exception:
            pass

    def on_click(self, callback):
        """A click on the pill cancels what it is waiting for."""
        self._on_cancel = callback
        try:
            self.bind("<Button-1>", lambda _e: callback())
            self.configure(cursor="hand2")
            current = self.label.cget("text")
            self.set(current)
        except Exception:
            pass

    def close(self):
        try:
            self.spinner.stop()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass


class Spinner(tk.Canvas):
    """Twelve fading ticks — the iOS activity indicator."""

    def __init__(self, parent, palette, size=16):
        super().__init__(parent, width=size, height=size,
                         highlightthickness=0, bd=0, bg=palette["surface"])
        self.palette = palette
        self.size = size
        self._phase = 0
        self._job = None
        self._ticks = []
        centre = size / 2.0
        import math
        for i in range(12):
            angle = math.pi * 2 * i / 12
            x1 = centre + math.cos(angle) * (size * 0.22)
            y1 = centre + math.sin(angle) * (size * 0.22)
            x2 = centre + math.cos(angle) * (size * 0.46)
            y2 = centre + math.sin(angle) * (size * 0.46)
            self._ticks.append(
                self.create_line(x1, y1, x2, y2, width=2, capstyle="round",
                                 fill=palette["text_faint"]))

    def start(self):
        self._tick()

    def _tick(self):
        for i, item in enumerate(self._ticks):
            distance = (i - self._phase) % 12
            alpha = 0.18 + 0.82 * (1.0 - distance / 12.0)
            self.itemconfig(item, fill=_blend(self.palette["text"],
                                              self.palette["surface"], alpha))
        self._phase = (self._phase + 1) % 12
        self._job = self.after(70, self._tick)

    def stop(self):
        if self._job:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None


__all__ = ["ResultPopup", "StatusToast", "OverlayWindow"]


class _Scrim(tk.Toplevel):
    """An almost-invisible full-screen window that catches the click away.

    The overlay used to listen for <FocusOut>, which never fires on macOS: a
    borderless window (overrideredirect) is not given keyboard focus, so it
    can never lose it. The translation then stayed on screen with no way to
    dismiss it — and <Escape> was dead for the same reason.

    A window that covers everything and sits directly under the overlay gets
    the click instead, wherever on screen it lands.
    """

    LIFETIME_MS = 120000        # never outlive its overlay by more than this

    def __init__(self, master, on_dismiss):
        super().__init__(master)
        self._on_dismiss = on_dismiss
        self.overrideredirect(True)
        try:
            self.attributes("-topmost", True)
            # Not fully transparent: a window with alpha 0 is click-through
            # on some systems, which would defeat the point.
            self.attributes("-alpha", 0.01)
        except Exception:
            pass
        self.configure(bg="#000000")
        width = self.winfo_screenwidth()
        height = self.winfo_screenheight()
        # Oversized and offset so extra monitors are covered too.
        self.geometry(_at(width * 3, height * 3, -width, -height))
        for sequence in ("<Button-1>", "<Button-2>", "<Button-3>",
                         "<Escape>", "<Key>"):
            self.bind(sequence, self._dismiss)
        # A stuck scrim would swallow every click on the machine, so it is
        # never allowed to be permanent.
        self._timer = self.after(self.LIFETIME_MS, self._dismiss)

    def _dismiss(self, _event=None):
        try:
            self.after_cancel(self._timer)
        except Exception:
            pass
        try:
            self._on_dismiss()
        except Exception:
            pass
        self.close()

    def close(self):
        try:
            self.destroy()
        except Exception:
            pass


class OverlayWindow(tk.Toplevel):
    """Shows the translated image exactly over the region it came from.

    Sits at the snip's screen coordinates with no chrome at all, so the
    translation reads as part of the page rather than a panel about it.
    Clicking anywhere on it, pressing Esc, or clicking away all dismiss it.
    """

    _open = []

    # Small steps. The first version went 1.0 to 1.4, which is a 40% jump
    # on one notch of the wheel — the overlay leapt rather than grew, and
    # landing on the size you wanted was luck. Then twelve per cent a
    # notch, which is what a browser does and is right for a wheel that
    # clicks. It is still too coarse for a trackpad, where the gesture is
    # continuous and each step of it is tiny, so the rungs are half that
    # again and a wheel notch is worth two of them — the same twelve per
    # cent to the hand holding a mouse, and something a pinch can slide
    # along.
    ZOOM_RATIO = _ZOOM_RATIO
    ZOOMS = _ZOOM_LADDER

    # What one click of a wheel is worth, in rungs.
    RUNGS_PER_NOTCH = 2.0
    # And the most a gesture may cover in a second, however many events
    # the trackpad fires. A wheel sends one event per notch; a trackpad
    # sends dozens a second, and one rung apiece would send the overlay
    # from life size to three times it in the blink of an eye. This is
    # the difference between a zoom that glides and one that leaps.
    # Eleven rungs is a little under doubling, so a second of gesture is
    # a doubling and no more. Four in hand at the start, because three
    # quick clicks of a wheel are one movement of one finger and should
    # not be rationed.
    RUNGS_PER_SECOND = 11.0
    RUNG_BURST = 4.0
    # Longer than this between events and the gesture is over: whatever
    # was left over from it is dropped rather than added to the next one.
    GESTURE_GAP = 0.3
    # And the least time between two redraws while a gesture is running.
    # Laying a page out again is not free, and doing it on every event of
    # a pinch is how a zoom comes to feel like a hang. There is always a
    # last redraw after the fingers stop.
    ZOOM_SETTLE = 90
    # How often the pinches heard by AppKit are read off. Twenty-five
    # times a second: fast enough that a gesture feels answered, and it
    # costs nothing when nobody is pinching.
    PINCH_POLL = 40

    # The strip along the bottom that carries the language and any
    # warning. Drawn below the page rather than over it: the overlay is a
    # picture of a document and a badge in its corner lands on whatever
    # happens to be in that corner.
    BAR_H = 26

    def __init__(self, master, image, x, y, on_copy=None, rerender=None,
                 shrink=1.0, blocks=None, height=None, notice="",
                 engine=""):
        # The scrim is created first so it sits *below* this window.
        self.scrim = None
        if CFG.get("close_on_click_away", True):
            try:
                self.scrim = _Scrim(master, self.close)
            except Exception:
                self.scrim = None

        super().__init__(master)
        self.on_copy = on_copy
        # Redrawing at a larger size, for when the translation came out
        # small. English runs about twice as long as Chinese and has to go
        # back into the space the Chinese occupied, so on a dense page it
        # ends up at the floor. This is the way out of that, and it draws
        # again rather than magnifying: enlarging the finished picture
        # would make the letters bigger and no easier to read.
        self._rerender = rerender
        # Codes the engine dropped. Written to the log before this existed,
        # which is the one place nobody looks: the reader sees a fluent
        # sentence with a reference number missing from it and no reason to
        # doubt it.
        self._notice = str(notice or "")
        # Which engine translated this, as the result card already says.
        # "Is this Groq or the offline model?" had no answer on a snip.
        self._engine = str(engine or "")
        self._shrink = shrink or 1.0
        self._zoom = 0
        # Where the gesture has asked to be, which runs ahead of where the
        # page has been drawn: see _roll and _settle.
        self._want_zoom = 0
        self._zoom_job = None
        self._drawn_at = 0.0
        self._debt = 0.0                # part-rungs not yet spent
        self._tokens = self.RUNG_BURST  # rungs the gesture may still spend
        self._token_at = time.monotonic()
        self._rolled_at = 0.0
        # Pinches land in here from AppKit's run loop and are read off it
        # by a timer on the Tk side. A deque because appending to one is
        # the largest thing that handler is allowed to do — see app/pinch.
        self._pinches = collections.deque()
        self._pinch = None
        self._pinch_job = None
        self._origin = (int(x), int(y))
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="#000000")

        self._blocks = blocks
        if blocks is not None:
            width, tall = self._build_canvas(image, blocks, height)
            self.label = self.canvas
        else:
            from PIL import ImageTk
            self._photo = ImageTk.PhotoImage(image, master=self)
            self.canvas = None
            self.label = tk.Label(self, image=self._photo, bd=0,
                                  highlightthickness=0, cursor="hand2")
            self.label.pack()
            width, tall = image.width, image.height
        # Anchored where the snip was, then pulled back on screen. A block
        # that grew makes the overlay taller than the region it covers, and
        # a translation whose last paragraph is below the bottom of the
        # display is the problem this was opened to solve.
        try:
            x, y = platform_util.clamp_to_display(
                x, y, width, tall, scale=self._shrink,
                fallback=(self.winfo_screenwidth(),
                          self.winfo_screenheight()))
        except Exception:
            pass
        self.geometry(_at(width, tall, x, y))

        # Ctrl and the wheel zooms, which is what every other application
        # this sits on top of uses for the same thing; Windows and macOS
        # send one event, X11 sends two different ones. The plain wheel
        # scrolls, when there is anything to scroll to — Tk prefers the
        # more specific pattern, so holding ctrl still zooms rather than
        # doing both.
        self._bind_pointer()
        for key, step in (("<Down>", 48), ("<Up>", -48),
                          ("<Next>", 240), ("<Prior>", -240)):
            self.bind(key, lambda _e, s=step: self._scroll(step=s))
        for key, step in (("<Right>", 48), ("<Left>", -48)):
            self.bind(key, lambda _e, s=step: self._scroll_x(step=s))
        self.bind("<Escape>", lambda _e: self.close())
        self.bind("<Control-c>", self._copy)
        self.bind("<FocusOut>", self._maybe_close)
        # A keypress is one whole notch, the same as a click of the wheel.
        step = int(self.RUNGS_PER_NOTCH)
        for key in ("<plus>", "<KP_Add>", "<equal>"):
            self.bind(key, lambda _e, s=step: self.zoom(s))
        for key in ("<minus>", "<KP_Subtract>"):
            self.bind(key, lambda _e, s=step: self.zoom(-s))
        self.bind("<0>", lambda _e: self.zoom(None))

        # Above the scrim, and bound app-wide so Escape works even though a
        # borderless window on macOS never holds keyboard focus.
        self.lift()
        try:
            self.bind_all("<Escape>", lambda _e: OverlayWindow.close_all())
        except Exception:
            pass

        # And a pinch, on the machines where Tk cannot hear one. Only
        # while this overlay is up: the monitor is taken away in close().
        if self._rerender is not None and CFG.get("pinch_zoom", True):
            try:
                self._pinch = pinch_mod.watch(self._pinches.append)
            except Exception:
                self._pinch = None
            if self._pinch is not None:
                self._pinch_job = self.after(self.PINCH_POLL,
                                             self._read_pinches)

        OverlayWindow._open.append(self)
        self.after(30, self._focus)

    @staticmethod
    def _hex(rgb):
        try:
            r, g, b = (max(0, min(255, int(v))) for v in rgb[:3])
            return "#%02x%02x%02x" % (r, g, b)
        except Exception:
            return "#000000"

    def _build_canvas(self, page, blocks, height):
        """Draw the layout as canvas items rather than a finished picture.

        This is the whole reason the renderer was split in two. A bitmap
        handed to Tk is one image pixel to one point, so on a display that
        draws two device pixels per point the picture is scaled down to fit
        the window and scaled back up to reach the screen — every glyph
        makes the trip twice and arrives soft. Canvas items are drawn by
        the system at the real resolution, which is why the selection frame
        is crisp and this was not.

        Only the page behind stays a bitmap, and it is a photograph of
        something already on screen — nobody is reading it, it is there so
        the translation sits on its own background.
        """
        from PIL import Image as _Image, ImageTk
        from . import overlay as overlay_mod

        scale = self._shrink or 1.0
        pad = overlay_mod.MARK_PAD
        tall_px = int(height or page.height)
        width = max(1, int(round(page.width / scale))) + 2 * pad
        content = max(1, int(round(tall_px / scale))) + 2 * pad

        # How big the window may actually be. A column that overran makes
        # the content taller than what was snipped, and zooming makes it
        # wider — and beyond a point both are bigger than the display, at
        # which point growing the window stops helping, because the words
        # that did not fit the page now do not fit the screen either. Past
        # that the window stops growing and the content scrolls inside it.
        #
        # The width matters as much as the height and used to be left out.
        # Only the window's *position* was pulled back on screen, never its
        # size, so zooming a full-screen capture produced a window wider
        # than the display, pinned at the left edge, with everything past
        # the right edge unreachable — there was no sideways scrolling
        # either. Zoom appeared to do nothing useful, which is exactly what
        # it was doing.
        try:
            span = None
            try:
                span = platform_util.room_on_display(
                    self._origin[0], self._origin[1], scale=self._shrink,
                    fallback=(self.winfo_screenwidth(),
                              self.winfo_screenheight()))
            except Exception:
                span = None
            span = span or (self.winfo_screenwidth(),
                            self.winfo_screenheight())
            room_h = int(span[1] * 0.92)
            room_w = int(span[0] * 0.96)
        except Exception:
            room_h, room_w = content, width
        view_w = min(width, max(160, room_w))
        tall = min(content, max(120, room_h))
        self._content_width = width
        self._content_height = content
        self._view_width = view_w
        self._view_height = tall
        self._offset = 0
        self._offset_x = 0

        bar = self._bar_height()
        border = overlay_mod._border_colour(page.convert("RGB"))
        self.canvas = tk.Canvas(self, width=view_w, height=tall + bar,
                                highlightthickness=0, bd=0,
                                bg=self._hex(border), cursor="hand2",
                                scrollregion=(0, 0, width, content + bar))
        self.canvas.pack()

        shown = page.convert("RGB")
        if scale > 1.01:
            shown = shown.resize(
                (max(1, int(round(shown.width / scale))),
                 max(1, int(round(shown.height / scale)))), _Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(shown, master=self)
        self.canvas.create_image(pad, pad, anchor="nw", image=self._photo)

        self._paint_blocks(blocks)

        self._draw_mark(view_w, tall)
        self._tall = tall
        self._draw_engine(view_w, tall)
        self._draw_scroll_hint(view_w, tall)
        self._mark_at = 0
        self._mark_at_x = 0
        if bar:
            self._draw_bar(view_w, tall, bar)
        return view_w, tall + bar

    def _paint_blocks(self, blocks):
        """The translation's covers and rows as canvas items, tagged "tx"
        so they can be drawn again as a page fills in."""
        from . import overlay as overlay_mod
        scale = self._shrink or 1.0
        pad = overlay_mod.MARK_PAD
        self._patches = []

        def at(value):
            return int(round(value / scale)) + pad

        # Covers first, all of them, then every row of text. Interleaving
        # them lets a block that grew downward have its own words painted
        # over by the cover of the block beneath it.
        for block in blocks:
            turned = overlay_mod.turned_parts(block)
            if turned is not None:
                # Text at an angle: a cover the shape of the line.
                self.canvas.create_polygon(
                    *[at(v) for point in turned[0] for v in point],
                    fill=self._hex(block["bg"]), outline="", tags=("tx",))
                continue
            x0, y0, x1, y1 = block["cover"]
            patch = block.get("patch")
            if patch is not None:
                photo = overlay_mod.patch_photo(patch, scale, self)
                if photo is not None:
                    self._patches.append(photo)
                    self.canvas.create_image(at(max(0, x0)), at(max(0, y0)),
                                             anchor="nw", image=photo,
                                             tags=("tx",))
                    continue
            self.canvas.create_rectangle(
                at(x0), at(y0), at(x1), at(y1),
                fill=self._hex(block["bg"]), outline="", tags=("tx",))

        family = overlay_mod.tk_family(
            blocks[0].get("kind", "default") if blocks else "default", self)
        for block in blocks:
            size = max(1, int(round(block["size"] / scale)))
            turned = overlay_mod.turned_parts(block)
            if turned is not None:
                # ...and its translation at the same angle.
                font = (family, -size) if family else ("", -size)
                try:
                    self.canvas.create_text(
                        at(turned[1][0]), at(turned[1][1]), text=turned[3],
                        angle=turned[2], anchor="center", font=font,
                        fill=self._hex(block["fg"]), tags=("tx",))
                except Exception:
                    pass
                continue
            # Negative asks Tk for pixels. Positive is points, which it
            # then scales by the display's own idea of resolution — so the
            # size the layout measured with and the size drawn would be
            # two different numbers.
            font = (family, -size) if family else ("", -size)
            # Never wider than its cover: the layout measured the rows in a
            # font file, Tk draws them in its own copy of a font, and where
            # the two differ a long row ran past the edge of the page.
            try:
                room = (block["cover"][2] - block["x"]) / scale
                if block.get("rtl") and block.get("right"):
                    room = (block["right"] - block["cover"][0]) / scale
                widest = max((tkfont.Font(font=font).measure(row)
                              for row in block["rows"]), default=0)
                if widest > room > 0:
                    size = max(1, int(size * room / widest))
                    font = (family, -size) if family else ("", -size)
            except Exception:
                pass
            colour = self._hex(block["fg"])
            ty = block["y"]
            # Right to left is set flush right — see the note in
            # overlay.layout, and keep the two drawing paths agreeing.
            right = block.get("rtl") and block.get("right")
            for row in block["rows"]:
                self.canvas.create_text(
                    at(right if right else block["x"]), at(ty), text=row,
                    anchor="ne" if right else "nw", fill=colour, font=font,
                    tags=("tx",))
                ty += block["leading"]

    def show_blocks(self, blocks):
        """Draw the translation again with these blocks - more of the page,
        as it fills in."""
        if self.canvas is None:
            return
        try:
            self.canvas.delete("tx")
            self._paint_blocks(blocks)
            self.canvas.tag_raise("pinned")
            self._blocks = blocks
        except Exception:
            pass

    def set_engine(self, engine):
        """Name the engine that translated the page. The window that shows
        a page filling in is made before any engine has answered, and it
        kept saying so - "(none yet)" - on the finished page."""
        engine = str(engine or "")
        if engine == self._engine or self.canvas is None:
            return
        self._engine = engine
        try:
            self.canvas.delete("engine")
            width = getattr(self, "_view_width", None) or \
                int(self.canvas.cget("width") or 0)
            tall = getattr(self, "_tall", None)
            if tall:
                self._draw_engine(width, tall)
        except Exception:
            pass

    def finish(self, blocks, on_copy=None, rerender=None, engine=None):
        """The finished page, into a window shown while it filled in."""
        self.show_blocks(blocks)
        if engine is not None:
            self.set_engine(engine)
        self.on_copy = on_copy
        self._rerender = rerender
        if self._rerender is not None and self._pinch is None and \
                CFG.get("pinch_zoom", True):
            try:
                self._pinch = pinch_mod.watch(self._pinches.append)
            except Exception:
                self._pinch = None
            if self._pinch is not None:
                self._pinch_job = self.after(self.PINCH_POLL,
                                             self._read_pinches)

    def _draw_engine(self, width, tall):
        """A small tag in the bottom corner naming the engine. Pinned, so
        it stays put while the page scrolls under it."""
        if not self._engine or width < 160 or tall < 40:
            return
        from . import overlay as overlay_mod
        font = (theme_mod.body_family(self), -theme_mod.scaled(10))
        inset = overlay_mod.MARK_RADIUS + overlay_mod.MARK_GRIP + 8
        right, bottom = width - inset, tall - 6
        text = self.canvas.create_text(right - 7, bottom - 3, anchor="se",
                                       text=self._engine, fill="#ffffff",
                                       font=font, tags=("pinned", "engine"))
        box = self.canvas.bbox(text)
        if box:
            back = self.canvas.create_rectangle(
                box[0] - 7, box[1] - 3, box[2] + 7, box[3] + 3,
                fill="#1d1f24", outline="", tags=("pinned", "engine"))
            self.canvas.tag_lower(back, text)

    # -- the strip along the bottom -------------------------------------
    def _bar_height(self):
        """How tall the strip is, or nothing when there is nothing on it."""
        if not self._notice:
            return 0
        return theme_mod.scaled(self.BAR_H)

    def _draw_bar(self, width, top, height):
        """Anything that went wrong, said on the page rather than the log.

        Pinned like the mark and the scroll thumb, because it belongs to
        the window rather than to the page: scrolling the page must not
        take the warning off the bottom of it.
        """
        # Its own colours rather than the theme's: the strip sits under a
        # photograph of somebody else's document, and a light bar under a
        # light page has no edge at all.
        base = "#1d1f24"
        dim = "#a9adb6"
        warn = "#ffb4a2"
        self.canvas.create_rectangle(0, top, width, top + height,
                                     fill=base, outline="",
                                     tags=("pinned", "bar"))
        middle = top + height // 2
        font = (theme_mod.body_family(self), -theme_mod.scaled(11))
        self.canvas.create_text(10, middle, anchor="w",
                                text=self._notice, fill=warn, font=font,
                                tags=("pinned", "bar"))
        self.canvas.create_text(width - 10, middle, anchor="e",
                                text="Esc closes  \u00b7  Ctrl+C copies",
                                fill=dim, font=font,
                                tags=("pinned", "bar"))

    # -- scrolling -----------------------------------------------------
    def _scrollable(self):
        return (getattr(self, "_content_height", 0)
                > getattr(self, "_view_height", 0) + 1)

    def _draw_scroll_hint(self, width, tall):
        """A thumb on the right edge, only when there is more to see.

        Without it the extra text is not hidden so much as secret: the
        overlay looks like a complete translation that simply stops, and
        there is nothing on screen to suggest the rest is a scroll away.
        """
        if not self._scrollable():
            return
        share = float(self._view_height) / float(self._content_height)
        thumb = max(28, int(tall * share))
        x = width - 7
        self.canvas.create_line(x, 6, x, tall - 6, fill="#000000",
                                width=5, capstyle="round",
                                tags=("pinned", "scroll_track"))
        self.canvas.create_line(x, 6, x, 6 + thumb, fill="#ffffff",
                                width=3, capstyle="round",
                                tags=("pinned", "scroll_thumb"))
        self._thumb_span = (6, tall - 6, thumb)
        # Remembered rather than measured later: winfo_width() is 1 until
        # the window is mapped, and a thumb placed from that lands off the
        # left edge of the overlay.
        self._thumb_x = x

    def _move_thumb(self):
        try:
            top, bottom, thumb = self._thumb_span
        except Exception:
            return
        travel = max(0, (bottom - top) - thumb)
        limit = max(1, self._content_height - self._view_height)
        y = top + int(travel * (self._offset / float(limit)))
        base = self.canvas.canvasy(0)
        x = getattr(self, "_thumb_x", 0)
        self.canvas.coords("scroll_thumb", x, base + y, x, base + y + thumb)

    def _scrollable_x(self):
        return (getattr(self, "_content_width", 0)
                > getattr(self, "_view_width", 0) + 1)

    def _scroll_x(self, event=None, step=None):
        """Sideways, for when zooming has made the page wider than the
        screen. Shift and the wheel, which is what everything else uses."""
        if not self._scrollable_x():
            return "break"
        if step is None:
            delta = getattr(event, "delta", 0) or 0
            step = -delta if abs(delta) < 30 else -int(delta / 120.0) * 3
            step *= 16
        self._move_to(x=self._offset_x + int(step))
        return "break"

    def _move_to(self, x=None, y=None):
        """Put the content at these offsets, clamped, frame left where it is.

        Both scrolling and dragging end up here, because the awkward part —
        clamping to the ends and moving the frame and the thumb back by the
        same amount so they stay pinned — is identical either way and is
        exactly the sort of thing that goes subtly wrong in the second copy.
        """
        limit_x = max(0, getattr(self, "_content_width", 0)
                      - getattr(self, "_view_width", 0))
        limit_y = max(0, getattr(self, "_content_height", 0)
                      - getattr(self, "_view_height", 0))
        if x is not None:
            x = max(0, min(limit_x, int(x)))
        if y is not None:
            y = max(0, min(limit_y, int(y)))
        if (x is None or x == self._offset_x) \
                and (y is None or y == self._offset):
            return False
        try:
            if x is not None and x != self._offset_x:
                self._offset_x = x
                self.canvas.xview_moveto(x / float(self._content_width))
                base = self.canvas.canvasx(0)
                self.canvas.move("pinned", base - self._mark_at_x, 0)
                self._mark_at_x = base
            if y is not None and y != self._offset:
                self._offset = y
                self.canvas.yview_moveto(y / float(self._content_height))
                base = self.canvas.canvasy(0)
                self.canvas.move("pinned", 0, base - self._mark_at)
                self._mark_at = base
                self._move_thumb()
        except Exception:
            pass
        return True

    # -- dragging ------------------------------------------------------
    # How far the pointer may wander before a click becomes a drag. A
    # click closes the overlay and a drag moves it, so the two have to be
    # told apart on release — and nobody's hand is perfectly still on a
    # button, which is what this few pixels of slack is for.
    DRAG_SLOP = 5

    def _pan_press(self, event):
        # getattr, because the bitmap overlay has no offsets at all — it
        # binds the same handlers so that a click still closes it.
        self._drag_from = (event.x_root, event.y_root)
        self._drag_origin = (getattr(self, "_offset_x", 0),
                             getattr(self, "_offset", 0))
        self._dragged = False
        return "break"

    def _pan_move(self, event):
        """Drag to read the parts that are off the edge.

        Sideways scrolling needs a wheel that tilts or a trackpad, and
        plenty of mice have neither — so the page that zooming pushed past
        the right edge would be unreachable for anybody with an ordinary
        two-button mouse. Dragging needs nothing but the button.
        """
        if getattr(self, "_drag_from", None) is None:
            return "break"
        if not (self._scrollable() or self._scrollable_x()):
            return "break"
        dx = event.x_root - self._drag_from[0]
        dy = event.y_root - self._drag_from[1]
        if not self._dragged and abs(dx) + abs(dy) < self.DRAG_SLOP:
            return "break"
        if not self._dragged:
            self._dragged = True
            try:
                self.canvas.configure(cursor="fleur")
            except Exception:
                pass
        # The page follows the hand: drag left and the content goes left,
        # which means looking further right.
        self._move_to(x=self._drag_origin[0] - dx,
                      y=self._drag_origin[1] - dy)
        return "break"

    def _pan_release(self, _event=None):
        """A click inside a page you can move through is not a dismissal.

        Clicking away closes — that is the scrim's job and it covers the
        whole screen. Inside the overlay, once there is more page than
        window, the button belongs to reading it: press, drag, let go. A
        click that closed the thing you were about to drag would make the
        dragging unusable, since every drag begins with a press.

        When the whole translation is on screen there is nothing to drag
        and clicking it to dismiss it is the quickest way out, so that
        stays. Escape and right-click close either way.
        """
        dragged = getattr(self, "_dragged", False)
        self._drag_from = None
        self._dragged = False
        try:
            self.canvas.configure(cursor="hand2")
        except Exception:
            pass
        if not dragged and not (self._scrollable() or self._scrollable_x()):
            self.close()
        return "break"

    def _scroll(self, event=None, step=None):
        """Move the content, keeping the frame and the thumb where they are.

        Everything on a canvas scrolls together, and the corner mark is not
        content — it frames the window. So the mark and the scroll thumb
        carry a tag and are moved back by the same amount, which pins them.
        """
        if not self._scrollable():
            return "break"
        if step is None:
            delta = getattr(event, "delta", 0) or 0
            # Windows sends multiples of 120 per notch; macOS sends small
            # numbers per tick and a stream of them from a trackpad, which
            # is what makes the scrolling feel continuous rather than
            # stepped. Both want the same pixels-per-unit here.
            step = -delta if abs(delta) < 30 else -int(delta / 120.0) * 3
            step *= 16
        self._move_to(y=self._offset + int(step))
        return "break"

    def _draw_mark(self, width, tall):
        """The corner mark, as vectors — same shape as the snip frame."""
        from . import overlay as overlay_mod
        radius = overlay_mod.MARK_RADIUS
        grip = overlay_mod.MARK_GRIP
        for colour, thick, hair in (("#000000", overlay_mod.MARK_THICK + 3, 3),
                                    ("#ffffff", overlay_mod.MARK_THICK, 1)):
            inset = thick // 2
            left, top = inset, inset
            right, bottom = width - 1 - inset, tall - 1 - inset
            if right - left < 2 * radius or bottom - top < 2 * radius:
                continue
            for x, y, start in ((left, top, 90),
                                (right - 2 * radius, top, 0),
                                (left, bottom - 2 * radius, 180),
                                (right - 2 * radius, bottom - 2 * radius, 270)):
                self.canvas.create_arc(x, y, x + 2 * radius, y + 2 * radius,
                                       start=start, extent=90, style="arc",
                                       outline=colour, width=thick,
                                       tags=("pinned",))
            # Butt caps, for the reason written out in snip.py: a round cap
            # on a line meeting an arc's flat end bulges back over the join
            # and escapes the curve as a spike.
            for x0, y0, x1, y1 in (
                    (left + radius, top, left + radius + grip, top),
                    (right - radius - grip, top, right - radius, top),
                    (left + radius, bottom, left + radius + grip, bottom),
                    (right - radius - grip, bottom, right - radius, bottom),
                    (left, top + radius, left, top + radius + grip),
                    (left, bottom - radius - grip, left, bottom - radius),
                    (right, top + radius, right, top + radius + grip),
                    (right, bottom - radius - grip, right, bottom - radius)):
                self.canvas.create_line(x0, y0, x1, y1, fill=colour,
                                        width=thick, capstyle="butt",
                                        tags=("pinned",))
            for x0, y0, x1, y1 in (
                    (left + radius, top, right - radius, top),
                    (left + radius, bottom, right - radius, bottom),
                    (left, top + radius, left, bottom - radius),
                    (right, top + radius, right, bottom - radius)):
                self.canvas.create_line(x0, y0, x1, y1, fill=colour,
                                        width=hair, tags=("pinned",))

    def _focus(self):
        try:
            self.focus_force()
        except Exception:
            pass

    def _maybe_close(self, _event=None):
        """Ignored, for the reason given on ResultPopup._maybe_close.

        This one closed on any focus loss with no delay and no guard at
        all, so the translation drawn over the page disappeared as soon as
        macOS took focus back — which it does immediately for a borderless
        window. Clicking the overlay still closes it; that binding is right
        above.
        """
        return

    @staticmethod
    def _notches(event):
        """One click of a wheel, whatever the platform calls it.

        Windows counts in 120ths and sends 120 for a notch; a precision
        touchpad there sends fractions of one, which is a pinch already
        arriving as something this can use. macOS counts in ones. Which
        of the two it is can be told apart by size — nothing sends 20 of
        anything for a single small movement — and a trackpad's stream of
        small ones then comes out as a stream of fractions rather than a
        stream of whole notches, which is the jumpiness this removes.
        """
        delta = float(getattr(event, "delta", 0) or 0)
        if not delta:
            return 0.0
        if abs(delta) >= 20:
            delta /= 120.0
        # No single event moves more than one notch. A trackpad that
        # reports a large delta for a fast flick would otherwise cross
        # the whole ladder in one go.
        return max(-1.0, min(1.0, delta))

    @staticmethod
    def _stamp(event):
        """When the gesture actually made this, not when we got to it.

        Laying a page out again takes long enough that a burst of forty
        trackpad events arrives faster than they can be answered, and the
        rest of them sit in the queue. Paced by the clock on the wall,
        those leftovers would go on zooming for seconds after the fingers
        had stopped — a third of a second of gesture spread over three
        seconds of overlay. Each event carries the moment it happened, so
        that is what the pacing counts.
        """
        when = getattr(event, "time", 0)
        try:
            when = float(when) / 1000.0
        except Exception:
            return None
        return when or None

    def _wheel(self, event):
        self._roll(self._notches(event) * self.RUNGS_PER_NOTCH,
                   when=self._stamp(event))
        return "break"

    def _read_pinches(self):
        """Take whatever the trackpad has said since last time.

        The handler that hears a pinch cannot call Tk — doing so crashes
        the application outright, for the reason set out at the top of
        app/pinch — so it leaves the numbers in a deque and this reads
        them off, twenty-five times a second, from the Tk side.

        Everything waiting is one movement, so it is added up and asked
        for once. Magnification multiplies, which is why the fractions
        compound rather than sum, and why the answer converts to rungs by
        asking how many of them multiply up to it.
        """
        self._pinch_job = None
        grown, when = 1.0, None
        while self._pinches:
            try:
                fraction, moment = self._pinches.popleft()
            except IndexError:
                break
            grown *= 1.0 + max(-0.9, float(fraction))
            when = moment
        if grown != 1.0:
            try:
                self._roll(math.log(grown) / math.log(self.ZOOM_RATIO),
                           when=when)
            except Exception:
                _log_zoom_failure()
        try:
            self._pinch_job = self.after(self.PINCH_POLL, self._read_pinches)
        except Exception:
            self._pinch_job = None

    def _roll(self, rungs, when=None):
        """Turn part of a gesture into ladder steps, at a pace to follow.

        Wheel notches and pinches both land here. Fractions are kept
        between events, so ten small ones move the same distance as one
        big one; a pause longer than a gesture throws the remainder away
        rather than letting it fall into the next gesture.
        """
        if not rungs:
            return
        now = time.monotonic() if when is None else float(when)
        # A pinch and a wheel count from different starting points, so a
        # gesture of one kind after a gesture of the other looks like a
        # jump in either direction. Both mean "a new gesture".
        since = now - self._rolled_at
        if since < 0 or since > self.GESTURE_GAP:
            self._debt = 0.0
            self._tokens = self.RUNG_BURST
            self._token_at = now
        self._rolled_at = now

        self._tokens = min(self.RUNG_BURST,
                           self._tokens
                           + max(0.0, now - self._token_at)
                           * self.RUNGS_PER_SECOND)
        self._token_at = now

        self._debt += rungs
        steps = int(self._debt)                 # toward zero, either sign
        if not steps:
            return
        # Nothing is drawn until the gesture rests (_settle), so there is
        # no need to ration it: every notch counts.
        spend = abs(steps)
        steps = spend if steps > 0 else -spend
        self._debt -= steps
        self._tokens -= spend

        self._want_zoom = max(
            0, min(len(self.ZOOMS) - 1, self._want_zoom + steps))
        self._settle()

    # How long the wheel or the fingers must rest before the page is laid
    # out again at the size they arrived at.
    #
    # It used to be laid out at every rung on the way, at most every 90 ms.
    # Laying out a dense page takes longer than that, and it ran on the
    # thread that hears the wheel: each redraw held the window still while
    # the next notches piled up, and the page then jumped through sizes
    # nobody had stopped at - "very laggy and jumpy". Now the gesture only
    # moves the target; the page is laid out once, for where it ends, away
    # from the window's thread, and swapped in when it is ready.
    ZOOM_IDLE = 160
    ZOOM_POLL = 30

    def _settle(self):
        """Lay the page out again once the gesture has rested."""
        if self._zoom_job is not None:
            try:
                self.after_cancel(self._zoom_job)
            except Exception:
                pass
            self._zoom_job = None
        if self._want_zoom == self._zoom:
            return
        try:
            self._zoom_job = self.after(self.ZOOM_IDLE, self._apply_zoom)
        except Exception:
            self._apply_zoom()

    def _apply_zoom(self):
        self._zoom_job = None
        want = self._want_zoom
        if want == self._zoom:
            return
        if self._rerender is None or self._blocks is None:
            self.zoom(want - self._zoom)
            return
        if getattr(self, "_zoom_busy", False):
            return                    # picked up when the current one lands
        self._zoom_busy = True
        box = {}

        def work():
            try:
                box["produced"] = self._rerender(self.ZOOMS[want])
            except Exception:
                box["error"] = True
        threading.Thread(target=work, daemon=True,
                         name="zoom-layout").start()
        self._zoom_wait(want, box)

    def _zoom_wait(self, want, box):
        if "produced" not in box and "error" not in box:
            try:
                self.after(self.ZOOM_POLL, self._zoom_wait, want, box)
            except Exception:
                self._zoom_busy = False
            return
        self._zoom_busy = False
        self._drawn_at = time.monotonic()
        if "error" in box:
            _log_zoom_failure()
            self._want_zoom = self._zoom
            return
        if self._replace(box["produced"]):
            self._zoom = want
        if self._want_zoom != self._zoom:
            self._settle()            # the gesture went on meanwhile

    def _bind_pointer(self):
        for widget in (self, self.label):
            widget.bind("<ButtonPress-1>", self._pan_press)
            widget.bind("<B1-Motion>", self._pan_move)
            widget.bind("<ButtonRelease-1>", self._pan_release)
            widget.bind("<Button-3>", lambda _e: self.close())
            widget.bind("<Control-MouseWheel>", self._wheel)
            # Cmd and the wheel is the Mac spelling of the same thing, and
            # is what a Mac trackpad's own pinch is mapped to by the
            # applications this sits on top of.
            widget.bind("<Command-MouseWheel>", self._wheel)
            widget.bind("<Control-Button-4>",
                        lambda _e: self._roll(self.RUNGS_PER_NOTCH))
            widget.bind("<Control-Button-5>",
                        lambda _e: self._roll(-self.RUNGS_PER_NOTCH))
            widget.bind("<MouseWheel>", self._scroll)
            from .ui_kit import bind_touchpad, touchpad_deltas
            bind_touchpad(widget, lambda e, w=widget: self._scroll(
                step=-touchpad_deltas(w, e)[1]))
            widget.bind("<Button-4>", lambda _e: self._scroll(step=-48))
            widget.bind("<Button-5>", lambda _e: self._scroll(step=48))
            widget.bind("<Shift-MouseWheel>", self._scroll_x)

    def _replace(self, produced):
        """Put a new layout on screen, or leave the old one alone.

        The canvas currently up is the only copy of what the user is
        reading. Destroying it first and failing second leaves an empty
        window with no way back — so the replacement is built while the old
        one is still there, and the old one goes only once there is
        something to put in its place.
        """
        page, blocks, height = produced
        old = self.canvas
        try:
            self.canvas = None
            width, tall = self._build_canvas(page, blocks, height)
        except Exception:
            _log_zoom_failure()
            self.canvas = old
            return False
        try:
            old.destroy()
        except Exception:
            pass
        self._blocks = blocks
        self.label = self.canvas
        self._bind_pointer()
        x, y = self._origin
        try:
            x, y = platform_util.clamp_to_display(
                x, y, width, tall, scale=self._shrink,
                fallback=(self.winfo_screenwidth(),
                          self.winfo_screenheight()))
        except Exception:
            pass
        self.geometry(_at(width, tall, x, y))
        return True

    def zoom(self, step):
        """One notch bigger or smaller; None goes back to where it started.

        Redrawn each time from the original image and the translated
        lines, so the type is real type at the new size. Only the page
        behind it is interpolated, and that is the half nobody is trying
        to read.
        """
        if self._rerender is None:
            return "break"
        want = 0 if step is None else max(
            0, min(len(self.ZOOMS) - 1, self._zoom + step))
        # Whatever asked for this is now where the gesture is too,
        # otherwise a keypress and a pinch would fight over the ladder.
        self._want_zoom = want
        if want == self._zoom:
            return "break"
        try:
            produced = self._rerender(self.ZOOMS[want])
        except Exception:
            # Logged rather than swallowed. A zoom that quietly does
            # nothing is indistinguishable from a zoom that is not wired
            # up, and the difference is the whole of the diagnosis.
            _log_zoom_failure()
            return "break"          # keep what is on screen
        self._zoom = want

        if self._blocks is not None and isinstance(produced, tuple):
            # Re-laid out, not magnified: the type is real type at the new
            # size rather than the old size enlarged.
            if not self._replace(produced):
                self._zoom = want - step if step else self._zoom
                self._want_zoom = self._zoom
            return "break"

        image = produced
        try:
            if self._shrink > 1.01:
                from PIL import Image as _Image
                image = image.resize(
                    (max(1, int(image.width / self._shrink)),
                     max(1, int(image.height / self._shrink))),
                    _Image.LANCZOS)
            from PIL import ImageTk
            self._photo = ImageTk.PhotoImage(image, master=self)
            self.label.configure(image=self._photo)
            # Anchored where the snip was, then pulled back on screen: a
            # zoomed overlay whose right edge is past the display is a
            # translation you cannot read, which is the problem it was
            # opened to solve.
            x, y = self._origin
            try:
                x, y = platform_util.clamp_to_display(
                    x, y, image.width, image.height, scale=self._shrink,
                    fallback=(self.winfo_screenwidth(),
                              self.winfo_screenheight()))
            except Exception:
                pass
            self.geometry(_at(image.width, image.height, x, y))
        except Exception:
            pass
        return "break"

    def _copy(self, _event=None):
        if self.on_copy:
            try:
                self.clipboard_clear()
                self.clipboard_append(self.on_copy)
                self.update()
            except Exception:
                pass

    def close(self):
        try:
            OverlayWindow._open.remove(self)
        except ValueError:
            pass
        # Told once, for a window shown while its page was still being
        # translated: closing it then is cancelling that snip.
        hook, self.on_close = getattr(self, "on_close", None), None
        if hook is not None:
            try:
                hook()
            except Exception:
                pass
        # The pinch monitor is system-wide and outlives this window unless
        # it is taken away, so it goes before anything that can fail.
        stop, self._pinch = self._pinch, None
        if stop is not None:
            try:
                stop()
            except Exception:
                pass
        for name in ("_zoom_job", "_pinch_job"):
            job = getattr(self, name, None)
            setattr(self, name, None)
            if job is not None:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        # The scrim covers the whole screen, so it must go even if tearing
        # down this window fails.
        scrim, self.scrim = self.scrim, None
        if scrim is not None:
            scrim.close()
        try:
            self.unbind_all("<Escape>")
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass

    @classmethod
    def close_all(cls):
        for window in list(cls._open):
            window.close()


def _no_see_through():
    """True where a window cannot be partly see-through: a Mac with Tk 9.

    Tk 9 on a Mac paints "systemTransparent" as black, so the snip's frame
    — a see-through window with only its outline drawn — came out as a
    black box over the text being read. There the outline is made from
    four thin solid windows, and labels are solid shapes.
    """
    return sys.platform == "darwin" and float(tk.TkVersion) >= 9.0


class ScanToast:
    """The area you snipped, tinted, with a soft light sweeping across it.

    The small "Translating…" pill it replaces sat near the cursor and was
    easy to miss — on a large screen, a snip that took a few seconds looked
    like a snip that had done nothing. This stays exactly where the eye
    already is: on the text being translated, where the translation will
    appear. A label on its top edge says which stage it is at.

    Built from several small windows rather than one, because a window can
    be see-through as a whole, smoothly, but not in parts: the first
    version was one window with a transparent colour and dithered fills,
    and the tint and the sweep came out as a visible checkerboard. Here the
    tint is one faint window over the area, the sweep is three narrow ones
    moving across it (brighter in the middle, softer at the edges), and the
    outline and the label sit on top with only their own pixels showing.
    """

    BLUE = "#2F6BFF"
    KEY = "#FF00FE"            # the colour Windows is told to leave out
    TICK = 30
    STEP = 14
    # (offset from the band's left edge, width, opacity)
    BAND = ((0, 18, 0.14), (18, 26, 0.26), (44, 18, 0.14))
    TAG_H = 26

    def __init__(self, master, x, y, width, height, message="Reading text…"):
        self.master = master
        self._windows = []
        self._job = None
        self.x, self.y = int(x), int(y)
        self.width, self.height = max(40, int(width)), max(24, int(height))
        self._pos = -self._band_width()
        try:
            self._tint = self._pane(self.x, self.y, self.width, self.height,
                                    0.10)
            self._bands = [self._pane(self.x, self.y, w, self.height, alpha)
                           for _off, w, alpha in self.BAND]
            self._outline = self._frame()
            self._pill, self._label = self._tag(message)
        except Exception:
            self.close()
            raise
        self._tick()

    # -- the pieces ----------------------------------------------------
    def _top(self, alpha=None):
        win = tk.Toplevel(self.master)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        if alpha is not None:
            win.attributes("-alpha", alpha)
        self._windows.append(win)
        return win

    def _see_through(self, win):
        """Only what is drawn shows; everything else is the page below."""
        if sys.platform == "win32":
            win.configure(bg=self.KEY)
            win.attributes("-transparentcolor", self.KEY)
            return self.KEY
        win.configure(bg="systemTransparent")
        win.attributes("-transparent", True)
        return "systemTransparent"

    def _pane(self, x, y, w, h, alpha):
        win = self._top(alpha)
        win.configure(bg=self.BLUE)
        win.geometry("%dx%d+%d+%d" % (w, h, x, y))
        return win

    def _frame(self):
        if _no_see_through():
            return self._frame_strips()
        win = self._top()
        base = self._see_through(win)
        canvas = tk.Canvas(win, width=self.width, height=self.height,
                           highlightthickness=0, bd=0, bg=base)
        canvas.pack()
        canvas.create_rectangle(1, 1, self.width - 1, self.height - 1,
                                outline=self.BLUE, width=2)
        win.geometry("%dx%d+%d+%d" % (self.width, self.height, self.x,
                                      self.y))
        return win

    def _frame_strips(self):
        """The outline as four solid windows, one per edge."""
        t = 2
        edges = ((self.x, self.y, self.width, t),
                 (self.x, self.y + self.height - t, self.width, t),
                 (self.x, self.y, t, self.height),
                 (self.x + self.width - t, self.y, t, self.height))
        wins = []
        for x, y, w, h in edges:
            win = self._top()
            win.configure(bg=self.BLUE)
            win.geometry("%dx%d+%d+%d" % (w, h, x, y))
            wins.append(win)
        self._strips = wins
        return wins[0]

    def _tag(self, message):
        win = self._top()
        base = self.BLUE if _no_see_through() else self._see_through(win)
        canvas = tk.Canvas(win, height=self.TAG_H, width=200,
                           highlightthickness=0, bd=0, bg=base)
        canvas.pack()
        label = canvas.create_text(14, self.TAG_H // 2, anchor="w",
                                   text=message, fill="white",
                                   font=theme_mod.font(win, 10, "bold"))
        self._tag_canvas = canvas
        self._fit_tag(win, canvas, label)
        return win, label

    def _fit_tag(self, win, canvas, label):
        x0, _y0, x1, _y1 = canvas.bbox(label)
        w, h = x1 + 14, self.TAG_H
        r = h // 2
        canvas.delete("pill")
        canvas.configure(width=w)
        canvas.create_oval(0, 0, h, h, fill=self.BLUE, outline=self.BLUE,
                           tags="pill")
        canvas.create_oval(w - h, 0, w, h, fill=self.BLUE, outline=self.BLUE,
                           tags="pill")
        canvas.create_rectangle(r, 0, w - r, h, fill=self.BLUE,
                                outline=self.BLUE, tags="pill")
        canvas.tag_raise(label)
        win.geometry("%dx%d+%d+%d" % (w, h, self.x,
                                      self.y - h - 4))

    def _band_width(self):
        return sum(w for _off, w, _a in self.BAND)

    # -- motion ----------------------------------------------------------
    def _tick(self):
        try:
            self._pos += self.STEP
            if self._pos > self.width:
                self._pos = -self._band_width()
            for (off, w, _alpha), win in zip(self.BAND, self._bands):
                left = max(0, self._pos + off)
                right = min(self.width, self._pos + off + w)
                if right - left < 1:
                    win.withdraw()
                    continue
                win.deiconify()
                win.geometry("%dx%d+%d+%d" % (right - left, self.height,
                                              self.x + left, self.y))
            for strip in getattr(self, "_strips", None) or [self._outline]:
                strip.lift()
            self._pill.lift()
            self._job = self._outline.after(self.TICK, self._tick)
        except Exception:
            self._job = None

    # -- the same calls as StatusToast ----------------------------------
    CANCEL_MARK = "   \u00d7"

    def set(self, message):
        self._message = message
        if getattr(self, "_on_cancel", None) is not None:
            message = message + self.CANCEL_MARK
        try:
            self._tag_canvas.itemconfigure(self._label, text=message)
            self._fit_tag(self._pill, self._tag_canvas, self._label)
        except Exception:
            pass

    def on_click(self, callback):
        """A click on the label cancels. Only the label: the tint over the
        area is left alone, so a click on the page is never taken for one."""
        self._on_cancel = callback
        try:
            self._pill.bind("<Button-1>", lambda _e: callback())
            self._tag_canvas.configure(cursor="hand2")
        except Exception:
            pass
        try:
            current = self._tag_canvas.itemcget(self._label, "text")
        except Exception:
            current = "Reading text…"
        self.set(getattr(self, "_message", None) or current)

    def close(self):
        if self._job and self._windows:
            try:
                self._windows[0].after_cancel(self._job)
            except Exception:
                pass
        self._job = None
        windows, self._windows = self._windows, []
        # Hidden and see-through first, destroyed a moment later. Destroyed
        # straight away, a thin band of the sweep could stay painted on a
        # Mac until the next click there: the window was gone, the pixels
        # macOS had composited for it were not.
        for win in windows:
            try:
                win.attributes("-alpha", 0.0)
            except Exception:
                pass
            try:
                win.withdraw()
            except Exception:
                pass

        def finish():
            for win in windows:
                try:
                    win.destroy()
                except Exception:
                    pass
        try:
            windows[0].update_idletasks()
            windows[0].after(80, finish)
        except Exception:
            finish()


def working_indicator(master, x, y, width, height, message="Reading text…",
                      palette=None):
    """The scan over the snipped area where the system allows it, else the
    small pill. Never raises: an indicator is not worth a failed snip."""
    if sys.platform in ("win32", "darwin") and width >= 40 and height >= 16:
        try:
            return ScanToast(master, x, y, width, height, message)
        except Exception:
            pass
    return StatusToast(master, message, palette=palette)


class ClipScanToast:
    """Copied text being translated: the snip's pill, and under it a strip
    with the start of the copied text and the snip's blue band sweeping
    across it. Appears by the pointer, since where copied text sits on
    screen is not something Squint can know.

    One window, drawn on a canvas. The strip is opaque, so the band is
    painted in solid colours mixed toward the blue rather than as
    see-through windows — the only see-through part is the window's own
    background around the rounded shapes.
    """

    BLUE = ScanToast.BLUE
    KEY = ScanToast.KEY
    TICK = 30
    STEP = 9
    BAND = ((0, 16, 0.16), (16, 22, 0.32), (38, 16, 0.16))
    TAG_H = 26
    STRIP_H = 36
    GAP = 6
    MAX_W = 380
    PAD = 14

    def __init__(self, master, text, message="Translating…", palette=None):
        self.master = master
        self.palette = palette or theme_mod.resolve(CFG.get("theme", "auto"))
        self._job = None
        self._dots = 0
        self._message = message.rstrip("…. ")
        win = tk.Toplevel(master)
        self.win = win
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        base = self._see_through(win)
        self.font = theme_mod.font(win, 10)
        self.bold = theme_mod.font(win, 10, "bold")
        measure = tkfont.Font(win, font=self.font)
        preview = " ".join(str(text or "").split())
        self.text = self._shorten(preview, measure, self.MAX_W - 2 * self.PAD)
        text_w = measure.measure(self.text) if self.text else 120
        self.width = max(220, min(self.MAX_W, text_w + 2 * self.PAD))
        self.height = self.TAG_H + self.GAP + self.STRIP_H + 4
        self.canvas = tk.Canvas(win, width=self.width, height=self.height,
                                highlightthickness=0, bd=0, bg=base)
        self.canvas.pack()
        self._pos = -self._band_width()
        self._draw_static()
        self._place()
        self._tick()

    # -- drawing -------------------------------------------------------
    def _see_through(self, win):
        if sys.platform == "win32":
            win.configure(bg=self.KEY)
            win.attributes("-transparentcolor", self.KEY)
            return self.KEY
        if _no_see_through():
            # Solid: the page's own card colour round the pill and strip.
            win.configure(bg=self.palette["surface"])
            return self.palette["surface"]
        if sys.platform == "darwin":
            win.configure(bg="systemTransparent")
            win.attributes("-transparent", True)
            return "systemTransparent"
        return self.palette["surface"]

    @staticmethod
    def _shorten(text, measure, room):
        if measure.measure(text) <= room:
            return text
        while text and measure.measure(text + "…") > room:
            text = text[:-1]
        return text.rstrip() + "…"

    def _round(self, x0, y0, x1, y1, r, fill, outline=None, tags=()):
        c = self.canvas
        outline = outline or fill
        items = [
            c.create_oval(x0, y0, x0 + 2 * r, y0 + 2 * r, fill=fill,
                          outline=outline, tags=tags),
            c.create_oval(x1 - 2 * r, y0, x1, y0 + 2 * r, fill=fill,
                          outline=outline, tags=tags),
            c.create_oval(x0, y1 - 2 * r, x0 + 2 * r, y1, fill=fill,
                          outline=outline, tags=tags),
            c.create_oval(x1 - 2 * r, y1 - 2 * r, x1, y1, fill=fill,
                          outline=outline, tags=tags),
            c.create_rectangle(x0 + r, y0, x1 - r, y1, fill=fill,
                               outline=fill, tags=tags),
            c.create_rectangle(x0, y0 + r, x1, y1 - r, fill=fill,
                               outline=fill, tags=tags),
        ]
        return items

    def _draw_static(self):
        c = self.canvas
        p = self.palette
        # The pill, the same as the snip's.
        self._pill_text = c.create_text(14, self.TAG_H // 2, anchor="w",
                                        text=self._message + "…",
                                        fill="white", font=self.bold)
        self._fit_pill()
        # The strip: a blue edge, the page's own surface inside it.
        top = self.TAG_H + self.GAP
        self.strip = (2, top, self.width - 2, top + self.STRIP_H)
        x0, y0, x1, y1 = self.strip
        self._round(x0, y0, x1, y1, 9, self.BLUE)
        self._round(x0 + 2, y0 + 2, x1 - 2, y1 - 2, 7, p["surface"])
        self._bands = [c.create_rectangle(0, y0 + 2, 0, y1 - 2, width=0,
                                          fill=_blend(self.BLUE,
                                                      p["surface"], a))
                       for _off, _w, a in self.BAND]
        c.create_text(x0 + self.PAD, (y0 + y1) // 2, anchor="w",
                      text=self.text, fill=p["text"], font=self.font,
                      tags="words")

    def _fit_pill(self):
        c = self.canvas
        x0, _y0, x1, _y1 = c.bbox(self._pill_text)
        c.delete("pill")
        self._round(0, 0, x1 + 14, self.TAG_H, self.TAG_H // 2, self.BLUE,
                    tags=("pill",))
        c.tag_raise(self._pill_text)

    def _band_width(self):
        return sum(w for _off, w, _a in self.BAND)

    def _place(self, offset=(18, 18)):
        win = self.win
        win.update_idletasks()
        w, h = self.width, self.height
        try:
            x = win.winfo_pointerx() + offset[0]
            y = win.winfo_pointery() + offset[1]
        except Exception:
            x = y = 120
        try:
            vx, vy = win.winfo_vrootx(), win.winfo_vrooty()
            vw, vh = win.winfo_vrootwidth(), win.winfo_vrootheight()
        except Exception:
            vx = vy = 0
            vw, vh = win.winfo_screenwidth(), win.winfo_screenheight()
        if x + w > vx + vw:
            x = x - w - 36
        if y + h > vy + vh:
            y = y - h - 36
        x = max(vx, min(int(x), vx + vw - w))
        y = max(vy, min(int(y), vy + vh - h))
        win.geometry(_at(w, h, x, y))

    # -- motion --------------------------------------------------------
    def _tick(self):
        try:
            x0, y0, x1, y1 = self.strip
            inner0, inner1 = x0 + 4, x1 - 4
            span = inner1 - inner0
            self._pos += self.STEP
            if self._pos > span:
                self._pos = -self._band_width()
            for (off, w, _a), item in zip(self.BAND, self._bands):
                left = max(0, self._pos + off)
                right = min(span, self._pos + off + w)
                if right - left < 1:
                    self.canvas.coords(item, 0, 0, 0, 0)
                    continue
                self.canvas.coords(item, inner0 + left, y0 + 2,
                                   inner0 + right, y1 - 2)
            self.canvas.tag_raise("words")
            # The dots, as the snip's label would have them if it moved.
            self._dots = (self._dots + 1) % 48
            dots = "." * (1 + self._dots // 12 % 3)
            self.canvas.itemconfigure(self._pill_text,
                                      text=self._message + dots)
            self._job = self.win.after(self.TICK, self._tick)
        except Exception:
            self._job = None

    # -- the same two calls as StatusToast -------------------------------
    def set(self, message):
        self._message = str(message).rstrip("…. ")
        try:
            self.canvas.itemconfigure(self._pill_text,
                                      text=self._message + "…")
            self._fit_pill()
        except Exception:
            pass

    def close(self):
        if self._job:
            try:
                self.win.after_cancel(self._job)
            except Exception:
                pass
        self._job = None
        win = self.win
        try:
            win.attributes("-alpha", 0.0)
            win.withdraw()
        except Exception:
            pass
        try:
            win.after(80, win.destroy)
        except Exception:
            try:
                win.destroy()
            except Exception:
                pass


def clip_indicator(master, text, message="Translating…", palette=None):
    """The scan pill for copied text; the plain pill if it cannot be made."""
    try:
        return ClipScanToast(master, text, message, palette=palette)
    except Exception:
        return StatusToast(master, message, palette=palette)
