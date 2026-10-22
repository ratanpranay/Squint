"""Main window: Translate and Settings, on a plain light surface."""
import os
import queue
import sys
import threading
import weakref
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox

from . import (config, docs, file_translate, hotkey, platform_util,
               selection, theme as theme_mod, translator, ui_guide)
from .i18n import t
from .langs import target_choices, name_for, code_for_name
from . import ui_home
from .ui_kit import (Dropdown, Field, PillButton, ProgressBar, ScrollArea,
                     Surface, Switch, TextPane, divider, label)

CFG = config.CONFIG
# The Text pane was merged into Files: one place to translate text,
# not two doing the same thing to different boxes. "Translate" is the
# pane the rail calls Home — see the note in _build.
PANES = ("Translate", "Settings", "Updates", "Support")
# One height for every pill and popup on the Translate row.
ROW_H = 40
# The gutter down each side of the page, and the gap between the two
# cards. Design measurements, in design pixels — not yet scaled. They
# cannot be scaled here: the scale is chosen when the window learns how
# big the screen is, which happens long after this module is imported.
# Every use below goes through ui_home.px.
PAGE_PAD = 48
CARD_GAP = 30
# The floor under both text boxes. It is the left one's content that
# sets it — a caret area and a place to drop a file — and the right one
# is given the same so the two can never come out different heights.
FIELD_LEAST = 120


def _short_name(path, limit=34):
    """A file name that fits on a row shared with a button.

    Real documents arrive with names like the subject line of the email
    they came in, and two of them side by side with an arrow between is
    wider than the window. Cut from the middle: the start says what the
    document is and the end keeps the extension, which is the half that
    says whether this is the original or the translation.
    """
    import os as _os
    name = _os.path.basename(str(path or ""))
    if len(name) <= limit:
        return name
    root, ext = _os.path.splitext(name)
    keep = max(6, limit - len(ext) - 1)
    head = keep // 2
    tail = keep - head
    return "%s…%s%s" % (root[:head], root[-tail:] if tail else "", ext)
# Inside every settings card, and between the rows within one.
CARD_PAD = 24
ROW_GAP = 8
LABEL_GAP = 28
# `Squint.exe --safe` forces a plain opaque window, so a display
# problem can always be undone from outside the app.
SAFE_MODE = "--safe" in sys.argv


class _Abandoned(Exception):
    """The file being translated was taken back out of the box."""


def in_background(window, work, then):
    """Run `work()` off the Tk thread and give what it returns to
    `window.<then>(*result)` on the Tk thread — without the thread ever
    holding the window.

    That last part is the point. A thread whose function closes over the
    window keeps the window alive for as long as the thread runs, and when
    the thread ends the window's last reference can go with it — on the
    thread. Tk will not be torn down anywhere but the thread that made it,
    and says so by stopping the whole program: "Tcl_AsyncDelete: async
    handler deleted by the wrong thread". A package install runs for a
    minute, and a theme change rebuilds the window in less than that.

    So the thread gets the window's queue, which is a plain Python object,
    and a weak reference, which does not keep anything alive. If the
    window is gone by the time the work is done, the result is dropped.
    """
    ref = weakref.ref(window)
    box = window._ui_queue

    def run():
        try:
            result = work()
        except Exception:
            return
        if result is not None:
            box.put((_deliver, (ref, then, result)))

    threading.Thread(target=run, daemon=True).start()


def _deliver(ref, name, result):
    """On the Tk thread: hand a background result to its window, if the
    window is still there."""
    window = ref()
    if window is None:
        return
    try:
        getattr(window, name)(*result)
    except Exception:
        pass


def _blend(a, b, share):
    """Colour `a` moved `share` of the way to `b` (both #rrggbb)."""
    try:
        a, b = a.lstrip("#"), b.lstrip("#")
        mix = [round(int(a[i:i + 2], 16) * (1 - share)
                     + int(b[i:i + 2], 16) * share) for i in (0, 2, 4)]
        return "#%02x%02x%02x" % tuple(mix)
    except Exception:
        return b


class DisclosureRow(tk.Frame):
    """A folded section that looks like something to press: a tinted,
    outlined row with an icon, a title, a line under it and "Show" on the
    right. The plain text link it replaces read as a caption and was
    missed."""

    def __init__(self, parent, palette, title, note, icon, command):
        p = palette
        tint = _blend(p["surface"], p["accent"], 0.07)
        edge = _blend(p["surface"], p["accent"], 0.28)
        super().__init__(parent, bg=tint, highlightthickness=1,
                         highlightbackground=edge, highlightcolor=edge,
                         bd=0)
        self._command = command
        inner = tk.Frame(self, bg=tint)
        inner.pack(fill="x", padx=ui_home.px(14), pady=ui_home.px(10))
        badge = tk.Label(inner, text=icon, bg=p["accent"],
                         fg=p["accent_text"], width=2,
                         font=theme_mod.font(inner, 11, "bold"))
        badge.pack(side="left", padx=(0, ui_home.px(12)), ipady=2)
        words = tk.Frame(inner, bg=tint)
        words.pack(side="left", fill="x", expand=True)
        self.title = label(words, p, title, size=10, weight="bold", bg=tint)
        self.title.pack(anchor="w")
        self.note = label(words, p, note, size=9, dim=True, bg=tint,
                          justify="left", wraplength=420)
        self.note.pack(anchor="w")
        self.action = tk.Label(inner, text="Show  ▾", bg=tint,
                               fg=p["accent"],
                               font=theme_mod.font(inner, 10, "bold"))
        self.action.pack(side="right", padx=(ui_home.px(12), 0))
        # No hand cursor: under the Mac app's Tk 9 it stuck after the
        # pointer left, and stayed as a hand over the whole window.
        for widget in (self, inner, badge, words, self.title, self.note,
                       self.action):
            widget.bind("<Button-1>", self._press)

    def _press(self, _event=None):
        try:
            self._command()
        except Exception:
            pass
        return "break"

    def set_open(self, opened):
        self.action.configure(text="Hide  ▴" if opened else "Show  ▾")


class MainWindow(tk.Toplevel):
    def __init__(self, controller, hidden=False):
        super().__init__(controller.root)
        # A Toplevel is on screen the moment it exists, so a window is
        # normally built in front of you: an empty frame, then a rail,
        # then a page, then whichever pane is being restored. Built
        # hidden it arrives finished, which is what a theme change needs
        # — see Controller.request_restart_for_theme.
        if hidden:
            try:
                self.withdraw()
            except Exception:
                pass
        self.controller = controller
        self.current_pane = "Translate"
        # Two views of one scheme. `page` is the design's own palette and
        # is what the front page is drawn in; `palette` is the same
        # colours under the names every dropdown, text pane and switch in
        # the kit already asks for. See theme.bridge.
        self.page = theme_mod.page(CFG.get("theme", "auto"))
        self.palette = theme_mod.bridge(self.page)
        self.pages = []
        self.current_file = None
        self._auto_job = None
        self._box_job = None
        self._last_translated = None
        self._translating = False
        # Tk is not thread-safe, and calling .after() from a worker thread
        # only appears to work. Workers post results here instead, and the
        # main thread drains the queue.
        self._ui_queue = queue.Queue()

        self.title("Squint")
        self._fit_to_screen()
        self.configure(bg=self.page["bg_a"])
        if controller.icon_path and os.path.isfile(controller.icon_path):
            try:
                self.iconbitmap(controller.icon_path)
            except Exception:
                pass

        # Deliberately plain. Every Windows compositing trick tried here —
        # acrylic blur, system backdrop, layered-window alpha — either broke
        # rendering outright or could not be verified, and a window that
        # renders beats a window that looks clever. Opt in via config if you
        # want to experiment; the default is a normal opaque window.
        # No compositing. Every attempt at it here produced a blank or
        # transparent window on some machine or other.
        self.effects = {}

        # Before _build(): building the tabs schedules timers that land here.
        self._timers = []
        #: Measurements that can only be taken once the thing being
        #: measured is on screen. A pane is built while it is hidden —
        #: that is the point of building it on demand — and a label asked
        #: how wide its row is while the row is one pixel wide gets one
        #: pixel for an answer. They are collected here and run when the
        #: pane is shown.
        self._fits = []
        #: Every grey line under a row, so they can all be given
        #: the same width once the pane is on screen. See `_even_wraps`.
        self._wrap_lines = []
        self._closing = False
        self._pump_id = None

        self._build()
        # One wheel handler for the whole window.
        #
        # Tk sends a wheel event to the widget under the pointer, and
        # nothing bubbles — so a scrolling page has to bind every widget
        # inside it, and anything built later, or rebuilt, or packed in
        # response to a setting, is a patch of page the wheel does not
        # work over. That is what "scrolling sticks" was: not slowness,
        # but a few dozen widgets that had never been told.
        #
        # A toplevel's own name is in the bindtags of every widget
        # inside it, so one binding here is every widget, for good,
        # including the ones that do not exist yet.
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind(sequence, self._wheel_anywhere)
        # A Mac trackpad under Tk 9 — what the Mac app ships with — is a
        # different event altogether.
        from .ui_kit import bind_touchpad
        bind_touchpad(self, self._touchpad_anywhere)
        self.protocol("WM_DELETE_WINDOW", self.hide)
        self._pump_id = self.after(50, self._pump_ui)

    # -- cross-thread plumbing -----------------------------------------
    def _post(self, func, *args):
        """Call `func(*args)` on the Tk thread. Safe from any thread."""
        self._ui_queue.put((func, args))

    def _pump_ui_once(self):
        """Drain pending results without rescheduling (used by tests)."""
        try:
            while True:
                func, args = self._ui_queue.get_nowait()
                try:
                    func(*args)
                except Exception:
                    pass
        except queue.Empty:
            pass

    def _pump_ui(self):
        try:
            while True:
                func, args = self._ui_queue.get_nowait()
                try:
                    func(*args)
                except Exception:
                    pass
        except queue.Empty:
            pass
        except Exception:
            pass
        if self._closing:
            return
        try:
            self._pump_id = self.after(50, self._pump_ui)
        except Exception:
            pass

    def destroy(self):
        """Stop the repeating timers before the widgets go away.

        A pending after() callback outlives the window it belongs to. When it
        finally fires there is nothing left to call, and Tk prints
        `invalid command name ..._pump_ui` — harmless, but it appears in the
        self-test output as if something had gone wrong.
        """
        self._closing = True
        for timer in [getattr(self, "_pump_id", None)] + \
                list(getattr(self, "_timers", [])):
            if timer:
                try:
                    self.after_cancel(timer)
                except Exception:
                    pass
        self._timers = []
        try:
            super().destroy()
        except Exception:
            pass

    # -- structure -----------------------------------------------------
    def _build(self, show=True):
        """The frame the design asks for: a rail, a top bar, and a pane.

        `show=False` builds it without putting it on screen, which is
        what a scheme change needs: the replacement is made while the
        old one is still there to look at, and the swap is one step with
        no empty window in between.

        The pane keys are the old ones. "Translate" is what the rail
        calls Home \u2014 it is the pane you translate in, it is the pane the
        gear returns to, and renaming the key would rename it in every
        place that has ever referred to it for the sake of a word the
        user never sees.
        """
        p = self.palette
        page = self.page
        shell = tk.Frame(self, bg=page["bg_a"])
        if show:
            shell.pack(fill="both", expand=True)
        self.root_frame = shell

        self.rail = ui_home.Rail(shell, page, self._go,
                                 "v%s" % config.build_id())
        self.rail.pack(side="left", fill="y")
        tk.Frame(shell, bg=page["line"], width=1).pack(side="left", fill="y")

        main = tk.Frame(shell, bg=page["bg_a"])
        main.pack(side="left", fill="both", expand=True)
        # No padding here, and no top bar above the panes. The front
        # page opens with a photograph that runs to the edge of the
        # window and up to the top of it, with the two controls standing
        # on the picture — so the margin belongs to what each pane puts
        # inside itself, not to a frame they all sit in. See `_pad`.
        body = tk.Frame(main, bg=page["bg_a"])
        body.pack(fill="both", expand=True)

        self.pane_host = tk.Frame(body, bg=page["bg_a"])
        self.pane_host.pack(fill="both", expand=True)

        self.panes = {}
        for name in PANES:
            self.panes[name] = tk.Frame(self.pane_host, bg=page["bg_a"])
        self._build_files(self.panes["Translate"])
        self._settings_built = False
        self._support_built = False
        self._updates_built = False
        self._show_pane("Translate")
        self.refresh_update_dot()
        self._say_permissions()

    #: The window the front page is drawn for. Everything in the design
    #: is measured against this; a smaller screen gets the same design,
    #: smaller, rather than the same sizes in less room.
    DESIGN_W, DESIGN_H = 1416, 880
    #: What the whole page needs vertically at full size — the scrolling
    #: part and the chrome around it both — measured off the built window
    #: rather than guessed. The window's height is divided by this, so it
    #: has to be the total: getting it wrong by the height of the top bar
    #: leaves exactly the top bar's worth of overflow, which is what a
    #: first guess of this number produced.
    DESIGN_CONTENT_H = 1050
    #: The window's shape, and the display it was drawn against. The
    #: window does not resize — the whole page is laid out for one shape
    #: — but one shape is not one *size*: a window 960 units wide is
    #: half a 4K screen's width on Windows and a quarter of it, because
    #: on a Mac those units are points and the display draws two pixels
    #: for each of them. Same number, two very different windows.
    #:
    #: So the size is a share of the screen it opens on, in whatever
    #: units that screen reports, and the page is drawn at a scale that
    #: moves with it. The design was measured on a display that reports
    #: 1512 by 982; everything is in proportion to that.
    OPEN_W, OPEN_H = 960, 540
    REFERENCE_W, REFERENCE_H = 1512, 982
    #: How far that proportion may be taken. Below the first the page
    #: stops being readable; the second is where a 4K display lands, and
    #: it is a ceiling rather than a share because past it a window
    #: stops being a window and starts being a wall — a screen twice as
    #: wide is not a reason for a window twice as wide, it is a reason
    #: for more desk around it.
    #: The floor is where the body text is eleven pixels, which is the
    #: smallest this page is worth reading at. Below it the window would
    #: fit more screens and be worth less on all of them.
    SMALLEST, BIGGEST = 0.95, 1.50
    #: What the type is drawn at on the reference display. See
    #: ui_home.SCALE — everything on the page is this times the design.
    LEAST_SCALE = 0.78
    #: How much of the window the photograph has.
    HERO_SHARE = 0.32

    def _fit_to_screen(self):
        """One shape, in proportion to the display it opens on.

        It used to open at a share of whatever screen it found, which is
        how a window ends up a different size on every machine. Then it
        opened at a fixed number of units, which is how a window ends up
        a different *physical* size on every machine — the same 960 is a
        comfortable window on a Retina Mac and a postage stamp on a 4K
        display, because one of them counts in points and the other in
        pixels.

        A share of the screen is the only measure that means the same
        thing on both. The window and the type are scaled together by
        one number, so the page is the same page everywhere and only its
        size changes.
        """
        try:
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
        except Exception:
            screen_w, screen_h = self.REFERENCE_W, self.REFERENCE_H
        factor = min(screen_w / float(self.REFERENCE_W),
                     screen_h / float(self.REFERENCE_H))
        factor = max(self.SMALLEST, min(self.BIGGEST, factor))
        width = int(round(self.OPEN_W * factor))
        height = int(round(self.OPEN_H * factor))
        # Whatever that came out as, it has to be a window this screen
        # can actually show.
        room_w, room_h = max(480, screen_w - 60), max(320, screen_h - 90)
        if width > room_w or height > room_h:
            shrink = min(room_w / float(width), room_h / float(height))
            width, height = int(width * shrink), int(height * shrink)
        ui_home.SCALE = max(0.5, self.LEAST_SCALE *
                            (width / float(self.OPEN_W)))
        # And everything the kit draws — Settings, Support — with it.
        theme_mod.PAGE_SCALE = ui_home.SCALE
        ui_home.HERO_CAP = int(height * self.HERO_SHARE)
        self.geometry("%dx%d" % (width, height))
        self.minsize(width, height)
        self.maxsize(width, height)
        try:
            self.resizable(False, False)
        except Exception:
            pass

    def _pad(self, parent, top=0, bottom=20):
        """A frame inset by the page's margin.

        The margin used to be on one frame every pane sat in. It moved
        in here when the front page's photograph was given the whole
        width of the window: a band that has to reach the edge cannot
        live inside the thing that holds everything away from it.
        """
        page = self.page
        inner = tk.Frame(parent, bg=page["bg_a"])
        inner.pack(fill="both", expand=True, padx=ui_home.px(PAGE_PAD),
                   pady=(ui_home.px(top), ui_home.px(bottom)))
        return inner

    def _banner_controls(self, banner):
        """Appearance and Settings, standing on the picture.

        The gear is here as well as in the rail on purpose: the rail is
        where you go when you are looking for a place, and this is where
        your hand already is when you have just been refused by a
        shortcut and want to know why.
        """
        page = self.page
        self.gear_button = ui_home.IconTextPill(
            banner, page, t("Settings"), "gear", self._toggle_settings,
            page["bg_a"])
        banner.host(self.gear_button, 0.975, 0.058, anchor="ne")
        self.theme_toggle = ui_home.ThemeToggle(
            banner, page, self._on_theme_choice, page["bg_a"],
            current=page["name"])
        banner.host(self.theme_toggle, 0.975, 0.058, anchor="ne",
                    dx=-(self.gear_button.winfo_reqwidth() + ui_home.px(14)))
        # What the window has to say for itself: a shortcut that would
        # not register, an update waiting. Top left, where a
        # left-to-right reader meets it first, and empty the rest of the
        # time.
        #
        # Their colour is sampled from a fixed patch rather than from
        # what they cover, because what they cover changes every time
        # they are given something to say — and a label that re-tints
        # itself on a timer is a label that flickers.
        patch = (0.045, 0.055, 0.30, 0.13)
        self.header_status = ui_home.text(banner, page, "", size=13,
                                          colour="dim", bg=page["bg_a"])
        banner.host(self.header_status, 0.045, 0.062, anchor="nw",
                    sample=patch)
        self.update_banner = ui_home.text(banner, page, "", size=13,
                                          colour="accent", bg=page["bg_a"])
        banner.host(self.update_banner, 0.045, 0.125, anchor="nw",
                    sample=patch)

    def _go(self, pane):
        """The rail's answer to being clicked."""
        if pane == "Settings":
            if self.current_pane != "Settings":
                self._toggle_settings()
            return
        if pane == "Support":
            self._show_support()
            return
        if pane == "Updates":
            self._show_updates()
            return
        self._show_pane("Translate")

    def _on_theme_choice(self, choice):
        """Light or dark, chosen here rather than buried in Settings.

        Tk cannot restyle a built window: every widget was handed its
        colours when it was made, and there are several hundred of them.
        The controller knows how to put the window back up in the other
        scheme, which is what it has always done for the setting in
        Settings \u2014 this is the same road, with a shorter walk to it.
        """
        CFG.set("theme", choice)
        try:
            self.controller.request_restart_for_theme()
        except Exception:
            pass

    def show_recent(self, items, reopen):
        """The last few finished translations, as buttons that reopen them.

        A snip closes and is gone; getting it back means finding the
        document again and drawing the same rectangle, which is never
        quite the same rectangle. These put it back where it was.
        """
        p = self.palette
        for child in self.recent_holder.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        if not items:
            self.recent_row.pack_forget()
            return
        for text, index in items:
            PillButton(self.recent_holder, text,
                       command=lambda i=index: reopen(i),
                       palette=p, kind="ghost", height=26,
                       font_size=8).pack(side="left", padx=(0, 8))
        self.recent_row.pack(fill="x", pady=(12, 0))

    def wake(self):
        """Called when the window comes back. Restarts what `hide` stopped."""
        try:
            if self.current_pane == "Translate":
                self.hero_picture.start()
        except Exception:
            pass

    def _show_pane(self, name):
        # Which pane the window is on is a fact about the window, not
        # about whether it happens to be on screen. Asking the frame
        # whether it is mapped answered "none of them" for a window
        # built out of sight, which is exactly when the answer matters —
        # a theme change rebuilds the window hidden and then has to put
        # you back where you were.
        self.current_pane = name
        # The hero only runs while it is the pane you are looking at.
        try:
            if name == "Translate":
                self.hero_picture.start()
            else:
                self.hero_picture.stop()
        except Exception:
            pass
        for key, frame in self.panes.items():
            if key == name:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()
        try:
            self.rail.select(name)
        except Exception:
            pass

    def _toggle_settings(self):
        if not self._settings_built:
            self._build_settings(self.panes["Settings"])
            self._wrap_to_fit(self.panes["Settings"])
            self._settings_built = True
        showing = self.current_pane == "Settings"
        self._show_pane("Translate" if showing else "Settings")
        if not showing:
            try:
                self.sync_permission()
            except Exception:
                pass
        if not showing:
            # The pane was built while hidden, so it had no width to lay out
            # against. Now that it is on screen, measure again.
            try:
                self.settings_scroll._lay_out()
                self.settle()
                self.settings_scroll._lay_out()
            except Exception:
                pass

    def _show_updates(self):
        """Updates, built the first time it is opened, like Support."""
        if not self._updates_built:
            self._build_updates(self.panes["Updates"])
            self._wrap_to_fit(self.panes["Updates"])
            self._updates_built = True
        self._show_pane("Updates")
        try:
            self.updates_scroll._lay_out()
            self.settle()
            self.updates_scroll._lay_out()
        except Exception:
            pass

    def _build_updates(self, parent):
        """The app, and the offline model: what is here, what is newer."""
        p = self.palette
        area = ScrollArea(self._pad(parent, top=20), p)
        area.pack(fill="both", expand=True)
        wrap = area.body
        self.updates_scroll = area
        label(wrap, p, t("Updates"), size=11, weight="bold",
              bg=p["window"]).pack(anchor="w", pady=(0, 10))

        body = self._panel(wrap, t("App"), first=True)
        holder = self._setting(
            body, "This build",
            "An update replaces the app's code and restarts it. Your "
            "settings, your keys and anything downloaded stay where they "
            "are.")
        self.build_label = label(holder, p, config.build_id(), size=10,
                                 dim=True, bg=p["surface"])
        self.build_label.pack(side="left", padx=(0, 12))
        # The new number, beside the old one, when there is one. It was
        # only in the grey text below, where "Build 1.48.7 is available"
        # read as one more line of notes.
        self.new_build_label = label(holder, p, "", size=10, weight="bold",
                                     bg=p["surface"])
        self.new_build_label.configure(fg=p["accent"])
        self.update_button = PillButton(
            holder, t("Check for updates"), command=self._check_update,
            palette=p, kind="secondary", height=Dropdown.HEIGHT,
            bg=p["surface"])
        self.update_button.pack(side="left")
        self.install_button = PillButton(
            holder, t("Install and restart"), command=self._install_update,
            palette=p, kind="primary", height=Dropdown.HEIGHT,
            bg=p["surface"])
        self.var_autocheck = tk.BooleanVar(
            value=CFG.get("check_for_updates", True))
        holder = self._setting(
            body, "Look for updates automatically",
            "Once a day, in the background. It fetches one small file and "
            "shows a red dot on Updates if there is a new build — it never "
            "downloads or installs anything on its own.", last=True)
        Switch(holder, p, variable=self.var_autocheck,
               command=lambda: CFG.set("check_for_updates",
                                       self.var_autocheck.get()),
               bg=p["surface"]).pack(side="right")
        # In a strip of its own and on the pane's wrap width, like the
        # other lines along the bottom of a card. With a fixed wrap it was
        # wider than the card whenever release notes arrived, and was cut
        # off at both edges.
        strip = tk.Frame(body, bg=p["surface"])
        strip.pack(fill="x", padx=ui_home.px(self.ROW_PAD), pady=(0, 10))
        self.update_status = label(strip, p, "", size=9, dim=True,
                                   wraplength=600, justify="left",
                                   anchor="w", bg=p["surface"])
        self.update_status.pack(anchor="w", fill="x")
        self._wrap_lines.append((self.update_status, None))
        if getattr(self, "_pending_update", None) is None:
            self._pending_update = None


        self._build_offline_updates(wrap)
        self._fits.append(self._even_wraps)
        # A newer build found by a check in an earlier session: ask again,
        # so the Install button has something to install.
        try:
            from . import updater
            if updater.pending_build() and self._pending_update is None:
                self.after(300, self._check_update)
        except Exception:
            pass

    def _build_offline_updates(self, wrap):
        from . import offline_model as om
        p = self.palette
        body = self._panel(wrap, t("Offline translation"))
        holder = self._setting(
            body, "Hy-MT2",
            "The offline model. When Tencent publishes a new version, the "
            "old one keeps working while the new one downloads, then "
            "replaces it.")
        self.offline_update_label = label(holder, p, "", size=10, dim=True,
                                          bg=p["surface"])
        self.offline_update_label.pack(side="left", padx=(0, 12))
        self.offline_check_button = PillButton(
            holder, t("Check now"), command=self._check_offline_update,
            palette=p, kind="secondary", height=Dropdown.HEIGHT,
            bg=p["surface"])
        self.offline_check_button.pack(side="left")
        self.offline_update_button = PillButton(
            holder, t("Update (1.1 GB)"), command=self._start_offline_update,
            palette=p, kind="primary", height=Dropdown.HEIGHT,
            bg=p["surface"])
        self.var_offline_autocheck = tk.BooleanVar(
            value=CFG.get("check_offline_updates", True))
        holder = self._setting(
            body, "Look for model updates automatically",
            "Once a week. Nothing is downloaded until you press Update.",
            last=True)
        Switch(holder, p, variable=self.var_offline_autocheck,
               command=lambda: CFG.set("check_offline_updates",
                                       self.var_offline_autocheck.get()),
               bg=p["surface"]).pack(side="right")
        strip = tk.Frame(body, bg=p["surface"])
        strip.pack(fill="x", padx=ui_home.px(self.ROW_PAD), pady=(0, 10))
        self.offline_update_bar = ProgressBar(strip, p, height=8)
        self.offline_update_status = label(
            strip, p, "", size=9, dim=True, wraplength=600, justify="left",
            anchor="w", bg=p["surface"])
        self.offline_update_status.pack(anchor="w", fill="x")
        self._wrap_lines.append((self.offline_update_status, None))
        self._offline_update_refresh()

    def _offline_update_refresh(self, message=None, colour=None):
        from . import offline_model as om
        p = self.palette
        try:
            have = om.installed(om.chosen())
            state = om.download_state()
            updating = state.get("state") == "updating"
            if not have:
                text = "Not downloaded"
                if message is None:
                    message = ("Press Set up to download it in Settings › "
                               "Offline translation.")
            elif updating:
                text = "Updating…"
            elif om.update_available():
                text = "New version"
            else:
                text = "Up to date"
            self.offline_update_label.configure(text=text)
            if have and om.update_available() and not updating:
                self.offline_update_button.pack(side="left", padx=(8, 0))
            else:
                self.offline_update_button.pack_forget()
            # Not downloaded: the button leads to where it is downloaded,
            # rather than sitting greyed out with nothing to check.
            try:
                self.offline_check_button.configure_text(
                    t("Check now") if have else t("Set up"))
            except Exception:
                pass
            self.offline_check_button.set_enabled(not updating)
            if updating:
                total = state.get("total") or 1
                self.offline_update_bar.pack(fill="x", pady=(0, 6),
                                             before=self.offline_update_status)
                self.offline_update_bar.set(state.get("done", 0) / total)
                message = "%d MB of %d MB" % (state.get("done", 0) >> 20,
                                              total >> 20)
            else:
                self.offline_update_bar.pack_forget()
            if message is None:
                checked = float(CFG.get("offline_update_checked", 0) or 0)
                message = ("Last checked %s." % time.strftime(
                    "%d %b %Y", time.localtime(checked))) if checked else ""
            self.offline_update_status.configure(
                text=message, fg=colour or p["text_dim"])
        except Exception:
            pass
        self.refresh_update_dot()

    def _check_offline_update(self):
        from . import offline_model as om
        if not om.installed(om.chosen()):
            self._go_to_offline_settings()
            return
        self.offline_check_button.set_enabled(False)
        self._offline_update_refresh("Checking…")

        def work():
            try:
                found = om.check_for_update()
                self._post(self._offline_update_refresh,
                           "A new version is available." if found
                           else "You have the newest version.",
                           None if found else self.palette["success"])
            except Exception as exc:
                self._post(self._offline_update_refresh,
                           "Could not check: %s" % str(exc)[:120],
                           self.palette["danger"])

        threading.Thread(target=work, daemon=True).start()

    def _go_to_offline_settings(self):
        """Settings, scrolled to Offline translation."""
        try:
            if self.current_pane != "Settings":
                self._toggle_settings()
            self.update_idletasks()
            panel = getattr(self, "offline_panel", None)
            area = self.settings_scroll
            if panel is not None:
                y = panel.winfo_rooty() - area.body.winfo_rooty()
                total = max(1, area.body.winfo_height())
                area.canvas.yview_moveto(max(0.0, (y - 60) / float(total)))
        except Exception:
            pass

    def _start_offline_update(self):
        from . import offline_model as om
        if not om.start_update():
            return
        self._offline_update_poll()

    def _offline_update_poll(self):
        from . import offline_model as om
        state = om.download_state().get("state")
        if state == "updating":
            self._offline_update_refresh()
            self.after(700, self._offline_update_poll)
            return
        if state == "ready":
            self._offline_update_refresh("Updated. The new model is in use.",
                                         self.palette["success"])
        else:
            self._offline_update_refresh(
                "The update stopped: %s. The old model is still in use."
                % (om.download_state().get("error") or state),
                self.palette["danger"])

    def refresh_update_dot(self):
        """The red dot on Updates: a newer app build, or a newer model."""
        on = False
        try:
            from . import updater, offline_model
            on = bool(getattr(self, "_pending_update", None) is not None
                      or updater.pending_build()
                      or offline_model.update_available())
        except Exception:
            pass
        try:
            self.rail.buttons["Updates"].set_dot(on)
        except Exception:
            pass

    def _show_support(self):
        """Support, built the first time somebody asks for it.

        Same bargain as Settings: a pane nobody opens in most sessions
        should not cost anything to open the window.
        """
        if not self._support_built:
            self._build_support(self.panes["Support"])
            self._wrap_to_fit(self.panes["Support"])
            self._support_built = True
        self._show_pane("Support")
        try:
            self.support_scroll._lay_out()
            self.settle()
            self.support_scroll._lay_out()
        except Exception:
            pass

    def _build_support(self, parent):
        """Two things and a fact sheet: a way to say thank you, a way to
        say something is wrong, and what this copy of the app is."""
        page = self.page
        p = self.palette
        area = ScrollArea(self._pad(parent, top=24), p, bg=page["bg_a"])
        area.pack(fill="both", expand=True)
        wrap = area.body
        self.support_scroll = area
        pad = ui_home.px(24)

        # -- the tip jar -------------------------------------------------
        card = ui_home.Card(wrap, page, page["bg_a"], padding=24)
        card.pack(fill="x")
        ui_home.text(card.body, page, t("Buy me a coffee"), size=19,
                     weight=700, bg=page["card"]).pack(anchor="w")
        ui_home.text(card.body, page,
                     t("Squint is free and stays free. If it has saved you "
                       "an afternoon, this is the tip jar."),
                     size=15, colour="ink_2", bg=page["card"],
                     wraplength=ui_home.px(560), justify="left",
                     anchor="w").pack(anchor="w", pady=(ui_home.px(6),
                                                        ui_home.px(18)))
        ui_home.DonateButton(card.body, page, t("Donate"), self._open_donate,
                             page["card"]).pack(anchor="w")
        ui_home.text(card.body, page, t("Opens PayPal in your browser."),
                     size=12, colour="faint", bg=page["card"]).pack(
                         anchor="w", pady=(ui_home.px(8), 0))

        # -- a problem ---------------------------------------------------
        report = ui_home.Card(wrap, page, page["bg_a"], padding=24)
        report.pack(fill="x", pady=(pad, 0))
        body = report.body
        ui_home.text(body, page, t("Report a problem"), size=19, weight=700,
                     bg=page["card"]).pack(anchor="w")
        ui_home.text(body, page,
                     t("A translation that came out wrong, something that "
                       "will not open, a shortcut that does nothing."),
                     size=15, colour="ink_2", bg=page["card"],
                     wraplength=ui_home.px(560), justify="left",
                     anchor="w").pack(anchor="w", pady=(ui_home.px(6),
                                                        ui_home.px(16)))

        ui_home.text(body, page, t("What went wrong"), size=14, weight=600,
                     bg=page["card"]).pack(anchor="w")
        # It grows with what is written in it and never scrolls: a small
        # box that scrolls swallows the wheel, so scrolling the page
        # stops the moment the pointer crosses it. Five hundred
        # characters is enough to say what went wrong and short enough
        # that the whole of it stays on screen.
        self.report_text = TextPane(
            body, p, height=4, min_lines=4, bg=page["card"],
            inner=page["field"], outline=page["field_line"],
            radius=ui_home.px(13), grows=True, limit=500)
        self.report_text.pack(fill="x", pady=(ui_home.px(6), ui_home.px(16)))

        ui_home.text(body, page, t("Your email"), size=14, weight=600,
                     bg=page["card"]).pack(anchor="w")
        self.report_from = tk.StringVar(value=CFG.get("report_from", ""))
        Field(body, p, textvariable=self.report_from, width=34,
              bg=page["card"], fill=page["field"],
              height=ui_home.px(40)).pack(anchor="w",
                                          pady=(ui_home.px(6), 0))
        ui_home.text(body, page,
                     t("So I can write back — and so you can send a "
                       "screenshot, which is usually the fastest way to "
                       "show me what happened."),
                     size=12, colour="faint", bg=page["card"],
                     wraplength=ui_home.px(520), justify="left",
                     anchor="w").pack(anchor="w", pady=(ui_home.px(6), 0))

        # Said before it is sent, not after. Somebody describing a
        # problem with a document they are translating has a right to
        # know what leaves their machine, and the answer is: what they
        # typed, and two lines about the build.
        ui_home.text(body, page,
                     t("Your version and platform go with it — %s, %s. "
                       "Nothing else, and nothing you have translated.")
                     % (config.build_id(), platform_util.describe()),
                     size=12, colour="faint", bg=page["card"],
                     wraplength=ui_home.px(560), justify="left",
                     anchor="w").pack(anchor="w", pady=(ui_home.px(14), 0))

        send_row = tk.Frame(body, bg=page["card"])
        send_row.pack(fill="x", pady=(ui_home.px(16), 0))
        self.report_button = PillButton(
            send_row, t("Send"), command=self._send_report, palette=p,
            kind="primary", height=ui_home.px(40), bg=page["card"])
        self.report_button.pack(side="left")
        self.report_status = ui_home.text(send_row, page, "", size=13,
                                          colour="dim", bg=page["card"],
                                          wraplength=ui_home.px(420),
                                          justify="left", anchor="w")
        self.report_status.pack(side="left", padx=(ui_home.px(14), 0))

        # -- what this is ------------------------------------------------
        facts = ui_home.Card(wrap, page, page["bg_a"], padding=24)
        facts.pack(fill="x", pady=(pad, pad))
        ui_home.text(facts.body, page, t("This build"), size=19, weight=700,
                     bg=page["card"]).pack(anchor="w")
        for name, value in ((t("Version"), config.build_id()),
                            (t("Platform"), platform_util.describe()),
                            (t("Log"), config.log_path())):
            row = tk.Frame(facts.body, bg=page["card"])
            row.pack(fill="x", pady=(ui_home.px(10), 0))
            ui_home.text(row, page, name, size=14, colour="dim",
                         bg=page["card"], width=11,
                         anchor="w").pack(side="left")
            ui_home.text(row, page, str(value), size=14, bg=page["card"],
                         anchor="w", justify="left",
                         wraplength=ui_home.px(460)).pack(side="left")
        buttons = tk.Frame(facts.body, bg=page["card"])
        buttons.pack(fill="x", pady=(ui_home.px(18), 0))
        PillButton(buttons, t("Open the log"), command=self._open_log,
                   palette=p, kind="secondary", height=ui_home.px(40),
                   bg=page["card"]).pack(side="left")
        PillButton(buttons, t("Copy these details"),
                   command=self._copy_build_details, palette=p,
                   kind="secondary", height=ui_home.px(40),
                   bg=page["card"]).pack(side="left",
                                         padx=(ui_home.px(10), 0))
        # Three test pages through the whole snip on this computer
        # (app/selfcheck.py): read, translated, drawn, in time.
        PillButton(buttons, t("Run check"),
                   command=lambda: self.controller.run_check(), palette=p,
                   kind="secondary", height=ui_home.px(40),
                   bg=page["card"]).pack(side="left",
                                         padx=(ui_home.px(10), 0))

    # -- the report ------------------------------------------------------
    #: Where a report goes. Overridable from the settings file, the same
    #: way the donate address is, so it can be changed without a build —
    #: which matters more here than it looks, because this address ends
    #: up in the To: field of everyone who ever reports anything.
    #:
    #: Emptied, it is not a failure: `_send_report` puts the whole report
    #: on the clipboard and says where to send it, rather than being a
    #: button that quietly does nothing.
    REPORT_TO = "pranayratan@gmail.com"

    def report_to(self):
        return str(CFG.get("report_email", "") or "").strip() or self.REPORT_TO

    def _report_body(self):
        """What gets sent, assembled in one place so the sentence above
        the button and the thing itself cannot drift apart."""
        said = ""
        try:
            said = self.report_text.get("1.0", "end-1c").strip()
        except Exception:
            pass
        return "\n".join((said, "", "-- ",
                           "Squint %s" % config.build_id(),
                           platform_util.describe()))

    def _send_report(self):
        """Hand it to the mail program, with everything already in it.

        Not posted anywhere. There is no server between the two of us,
        and adding one to carry a paragraph of text would mean somebody
        else's machine holding what people write about their documents.
        A mail client already knows how to send mail, and the reply
        comes back to a real address rather than to a form.
        """
        said = ""
        try:
            said = self.report_text.get("1.0", "end-1c").strip()
        except Exception:
            pass
        if not said:
            self._say_report(t("Say what went wrong first."), warn=True)
            return
        CFG.set("report_from", self.report_from.get().strip())
        body = self._report_body()
        where = self.report_to()
        if not where:
            try:
                self.clipboard_clear()
                self.clipboard_append(body)
                self.update()
            except Exception:
                pass
            self._say_report(
                t("Copied. There is no address built into this version yet "
                  "— paste it into an email and it will reach me."))
            return
        import urllib.parse
        query = urllib.parse.urlencode(
            {"subject": "Squint %s — a problem" % config.build_id(),
             "body": body}, quote_via=urllib.parse.quote)
        opened = False
        try:
            opened = bool(webbrowser.open("mailto:%s?%s" % (where, query)))
        except Exception:
            opened = False
        if opened:
            self._say_report(t("Your mail program should be opening."))
        else:
            try:
                self.clipboard_clear()
                self.clipboard_append(body)
                self.update()
            except Exception:
                pass
            self._say_report(
                t("No mail program opened, so it is on the clipboard "
                  "instead. Send it to %s.") % where)

    def _say_report(self, text, warn=False):
        try:
            self.report_status.configure(
                text=text,
                fg=self.palette["danger"] if warn else self.palette["text_dim"])
            self._timers.append(
                self.after(9000, lambda: self.report_status.configure(text="")))
        except Exception:
            pass

    def _open_log(self):
        try:
            platform_util.reveal(config.log_path())
        except Exception:
            try:
                webbrowser.open("file://%s" % config.log_path())
            except Exception:
                pass

    def _copy_build_details(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(
                "Squint %s\n%s\n%s" % (config.build_id(),
                                        platform_util.describe(),
                                        config.log_path()))
            self.update()
            self._say_report(t("Copied."))
        except Exception:
            pass

    def _on_lang_change(self, display_name):
        CFG.set("target_lang", code_for_name(display_name))
        self.controller.refresh_tray()
        try:
            self.dst_heading.configure(text=display_name.upper())
        except Exception:
            pass
        self._offer_pack_if_missing()
        # Whatever is on screen is now in the wrong language; redo it.
        self._last_translated = None
        if self.text_src.get("1.0", "end-1c").strip():
            self._schedule_auto()
        if self.current_file:
            self.load_file(self.current_file)

    def sync_language(self):
        self.lang_dropdown.set(name_for(CFG["target_lang"]))

    def set_hotkey_status(self, problems):
        """Say plainly whether the shortcut is live.

        A shortcut Windows refused to register looks identical to a broken
        app from the outside, so it should not be reported only in a tray
        balloon that disappears.
        """
        if not problems:
            self.header_status.configure(text="",
                                         fg=self.palette["text_dim"])
            return
        self.header_status.configure(
            text="Shortcut unavailable — %s. Pick another in Settings."
                 % problems[0],
            fg=self.palette["danger"])
        self._set_hk_status(problems[0], self.palette["danger"])

    # -- files pane ----------------------------------------------------
    def _build_files(self, parent):
        """Home: the hero, and under it the other ways to translate.

        The snip is the app and it is the top half of the page. Typing,
        pasting and opening a file are the other ways, and they are one
        pair of boxes rather than three tabs — typing and dropping a file
        are the same intent, so they are the same box, and a tab strip
        asked you to classify what you were about to do before you had
        done it.

        Every widget the rest of this file already talks to survives the
        move: `file_src`, `file_dst`, `src_lang`, `lang_dropdown`,
        `text_status`. They are in new places and in new colours; they
        are the same objects.
        """
        p = self.palette
        page = self.page
        area = ScrollArea(parent, p, bg=page["bg_a"], fill_height=True,
                          show_bar=False)
        area.pack(fill="both", expand=True)
        wrap = area.body
        self.home_scroll = area

        # -- the hero ---------------------------------------------------
        #
        # One band, edge to edge, with the words on the photograph
        # rather than beside it. Everything in it is drawn on the one
        # canvas; the two controls in the corner are the exception and
        # are hosted on it \u2014 see HeroBanner.
        self.hero_picture = ui_home.HeroBanner(
            wrap, page, page["bg_a"],
            eyebrow=t("Fast. Anywhere.").upper(),
            headline=((t("Snip it,"), "ink"),
                      (t("Understand it."), "accent")),
            blurb=t("Capture any text on your screen and get instant "
                    "translations \u2014 in any app, website, or document."),
            chips=(("bolt", t("Works anywhere"), "gold"),
                   ("globe", t("100+ languages"), "accent"),
                   ("lock", t("Private & secure"), "ink")),
            note=t("Drag to select\nany text on your screen"),
            margin=ui_home.px(PAGE_PAD))
        self.hero_picture.pack(fill="x")
        self._banner_controls(self.hero_picture)

        # Everything under the band keeps the page's margin.
        wrap = self._pad(wrap, top=18, bottom=14)

        # The last few translations, when there are any. Packed only
        # then: an empty "Recent" caption above an empty row is a promise
        # the window has not kept yet.
        self.recent_row = tk.Frame(wrap, bg=page["bg_a"])
        self.recent_label = ui_home.text(self.recent_row, page, t("Recent"),
                                         size=13, colour="dim",
                                         bg=page["bg_a"])
        self.recent_label.pack(side="left", padx=(0, ui_home.px(10)))
        self.recent_holder = tk.Frame(self.recent_row, bg=page["bg_a"])
        self.recent_holder.pack(side="left", fill="x", expand=True)

        # One row: the heading on the left, the button on the right.
        #
        # The button had a row of its own under the picture, and to the
        # right of it was a band of empty page as wide as the window.
        # Putting it here costs nothing — it is still the first thing
        # under the photograph and still the largest thing on the page —
        # and it gives the row back to the boxes, which is the part of
        # the page anybody actually works in.
        ways = tk.Frame(wrap, bg=page["bg_a"])
        ways.pack(fill="x", pady=(0, ui_home.px(10)))
        self.snip_button = ui_home.SnipButton(
            ways, page, t("Snip & Translate"), self._shortcut_keys(),
            self.controller.trigger_snip, page["bg_a"])
        self.snip_button.pack(side="right")
        # Nothing about a file lives on this row any more. The Open file
        # button went into the box first, because that is where the thing
        # it opens ends up; the name of the file and the button that
        # saves the result have now followed it there for the same
        # reason. A file that was put into the box is reported on in the
        # box — see DropZone and ProgressPill. What is left here is the
        # heading and the one action that is not about a file at all.
        self.section_rule = ui_home.SectionRule(
            ways, page, t("Other ways to translate"), page["bg_a"])
        self.section_rule.pack(side="left", fill="x", expand=True)

        # -- the pair ---------------------------------------------------
        #
        # Created here and packed last, at the bottom of this method.
        # `pack` hands out space in the order it is asked, and this is
        # the one thing on the page that expands: packed first it takes
        # the whole of the leftover height and the tip bar under it ends
        # up below the fold in a window the design fits comfortably.
        panes = tk.Frame(wrap, bg=page["bg_a"])
        self.panes_frame = panes

        # Gridded rather than packed, and that is not a preference.
        # The two are read as a pair: one a few pixels taller than the
        # other looks like a fault even when both are the right size.
        # Packed side by side their heights are the *result* of what
        # each happens to contain; in one grid row with one weight they
        # are the same height by construction, which is a thing that
        # cannot come apart later.
        panes.columnconfigure(0, weight=1, uniform="pair")
        panes.columnconfigure(1, weight=1, uniform="pair")
        panes.rowconfigure(0, weight=1)
        src_card = ui_home.Card(panes, page, page["bg_a"])
        # The gap is split between the two cells, not hung off the left
        # one. Put it all on the left card and the space between them
        # sits inside column 0, so the seam is not at the halfway line —
        # and the swap button, placed at the halfway line, comes out half
        # a gutter to the right of where it belongs.
        half = ui_home.px(CARD_GAP) // 2
        src_card.grid(row=0, column=0, sticky="nsew", padx=(0, half))
        dst_card = ui_home.Card(panes, page, page["bg_a"])
        dst_card.grid(row=0, column=1, sticky="nsew", padx=(half, 0))

        src_top = tk.Frame(src_card.body, bg=page["card"])
        src_top.pack(fill="x")
        # Full width of the card, a globe at the head and the chevron
        # hard right — the design's language row, not a pill floating in
        # the corner of one.
        self.src_lang = Dropdown(
            src_top, p, [self.AUTO] + [n for _c, n in target_choices()],
            value=CFG.get("source_lang_name", self.AUTO),
            command=self._on_source_lang, height=ui_home.px(46),
            bg=page["card"], icon="globe", radius=ui_home.px(13),
            max_width=4000, font=ui_home.font_for(src_top, 15, 500))
        self.src_lang.pack(fill="x")

        dst_top = tk.Frame(dst_card.body, bg=page["card"])
        dst_top.pack(fill="x")
        self.lang_dropdown = Dropdown(
            dst_top, p, [n for _c, n in target_choices()],
            value=name_for(CFG["target_lang"]), command=self._on_lang_change,
            height=ui_home.px(46), bg=page["card"], icon="globe",
            radius=ui_home.px(13), max_width=4000,
            font=ui_home.font_for(dst_top, 15, 500))
        self.lang_dropdown.pack(fill="x")

        # One field per card, and inside the left one both ways in: the
        # caret at the top, and under it the place to drop a file. They
        # are the same box because they are the same intent — and
        # because the two cards then hold the same things in the same
        # order, which is what keeps the pair the same height.
        self.src_field = src_field = ui_home.Card(
            src_card.body, page, page["card"], radius=15, padding=0,
            fill="field", outline="field_line", least=FIELD_LEAST)
        src_field.pack(fill="both", expand=True, pady=(ui_home.px(14), 0))
        # Two lines, not three: what sits under the caret here is the
        # place a file goes, and on a small screen the two together are
        # more than the box has.
        self.file_src = TextPane(src_field.body, p, height=1, min_lines=1,
                                 on_clear=self.clear_text,
                                 placeholder=t("Type or paste text here…"),
                                 bg=page["field"], inner=page["field"],
                                 outline=page["field"], radius=0,
                                 font=ui_home.font_for(src_field, 16))
        self.file_src.pack(fill="x")
        self.drop_zone = ui_home.DropZone(
            src_field.body, page, self.pick_file, page["field"],
            on_cancel=self.cancel_file)
        self.drop_zone.pack(fill="both", expand=True,
                            padx=ui_home.px(16), pady=(0, ui_home.px(14)))

        self.dst_field = dst_field = ui_home.Card(
            dst_card.body, page, page["card"], radius=15, padding=0,
            fill="field", outline="field_line", least=FIELD_LEAST)
        dst_field.pack(fill="both", expand=True, pady=(ui_home.px(14), 0))
        self.file_dst = TextPane(
            dst_field.body, p, height=3, min_lines=3,
            placeholder=t("Translation will appear here…"),
            bg=page["field"], inner=page["field"],
            outline=page["field"], radius=0,
            font=ui_home.font_for(dst_field, 16))
        self.file_dst.pack(fill="both", expand=True)

        # The swap sits on the seam rather than in a gutter of its own,
        # which is the one measurement in this file that depends on
        # another: the gap between the cards is what it has to cover.
        self.swap_button = ui_home.SwapButton(
            panes, page, self.swap_languages, page["bg_a"], gutter=CARD_GAP,
            flank="field")
        self.swap_button.place(relx=0.5, rely=0.5, anchor="center")
        # Vertically it belongs to the boxes, not to the cards. The cards
        # carry a language row above and a row of buttons below, so their
        # middle is not the middle of the two things the swap sits
        # between — it came out low by half the difference.
        self.src_field.bind("<Configure>", self._place_swap, add="+")
        panes.bind("<Configure>", self._place_swap, add="+")

        self.text_src = self.file_src
        self.text_dst = self.file_dst
        self.file_src.text.bind("<KeyRelease>", self._schedule_auto)
        self.file_src.text.bind("<KeyRelease>", self._count_characters,
                                add="+")
        self.file_src.text.bind("<<Paste>>", self._schedule_auto)
        self._make_read_only(self.file_dst.text)
        self._wire_drops()

        # -- the line along the bottom ----------------------------------
        actions = tk.Frame(wrap, bg=page["bg_a"])
        self.actions_row = actions
        # Wide and wrapping: when a translation fails the reason is a
        # sentence from the service, and a status line that can only show
        # a few words reads as "nothing happened".
        self.text_status = ui_home.text(actions, page, "", size=13,
                                        colour="dim", bg=page["bg_a"],
                                        wraplength=ui_home.px(620),
                                        justify="left", anchor="w")
        self.text_status.pack(side="left")

        # In a slot of its own, because it comes and goes: a window
        # short enough to need the room gets the page without it, and
        # `pack` hands out the bottom of the cavity in the order it is
        # asked — so a bar that unpacked itself and came back later came
        # back above the row of buttons it belongs under. The slot keeps
        # the order; what changes is whether there is anything in it.
        self.tip_slot = tk.Frame(wrap, bg=page["bg_a"])
        self.tip_bar = ui_home.TipBar(
            self.tip_slot, page, page["bg_a"], self._shortcut_keys(),
            t("Tip: Use the shortcut"),
            # Shorter than the drawing's line, because the drawing is of a
            # wider window: at this one the full sentence and the link
            # together are longer than the bar, and a Tk label does not
            # ellipsise — it is simply cut off mid-word.
            t("to snip and translate from any app or document."),
            learn=self._toggle_settings,
            learn_text=t("Change it"))
        # Bottom-up, then the pair into what is left. `pack` hands out
        # space in the order it is asked, and the pair is the one thing
        # on this page that expands: packed before these it takes the
        # whole of the leftover height and the tip bar ends up below the
        # fold in a window the design fits comfortably.
        self.tip_slot.pack(side="bottom", fill="x")
        self.tip_bar.pack(fill="x", pady=(ui_home.px(12), 0))
        actions.pack(side="bottom", fill="x", pady=(ui_home.px(8), 0))
        panes.pack(fill="both", expand=True)

        # The pair of icon rows along the bottom of each box: copy on the
        # left card, copy and full-screen on the right, with the counter
        # opposite them. Inside the card rather than under it, which is
        # where the design puts them.
        # The way to keep the result, under the box the file went into
        # rather than inside it. The bar in the box says how the work is
        # going and finishes full; this says what to do with what came
        # out. Two different things, so two different objects — a bar that
        # turned into a button meant the box held, at different moments,
        # a report and an instruction, and they read as the same thing.
        #
        # Packed before the counter row so that it appears between the box
        # and the counter rather than under everything.
        self.download_row = tk.Frame(src_card.body, bg=page["card"])
        self.download_button = PillButton(
            self.download_row, t("Download translated file"),
            command=self.save_translated, palette=p, kind="primary",
            height=ui_home.px(46), bg=page["card"], icon="download")
        self.download_button.pack(fill="x")

        src_foot = tk.Frame(src_card.body, bg=page["card"])
        self.src_foot = src_foot
        src_foot.pack(fill="x", pady=(ui_home.px(10), 0))
        self.char_count = ui_home.text(src_foot, page, "0 / 10,000", size=13,
                                       colour="faint", bg=page["card"])
        self.char_count.pack(side="left")
        ui_home.IconButton(src_foot, page, "copy",
                           lambda: self._copy(self.file_src),
                           page["card"]).pack(side="right")

        dst_foot = tk.Frame(dst_card.body, bg=page["card"])
        dst_foot.pack(fill="x", pady=(ui_home.px(10), 0))
        # The design has a full-screen button and a read-aloud button
        # here as well. Neither exists yet, and a button that does
        # nothing is worse than a button that is not there, so this row
        # carries the one that works and the other two are queued.
        ui_home.IconButton(dst_foot, page, "copy",
                           lambda: self._copy(self.file_dst),
                           page["card"]).pack(side="right")

        self._timers.append(self.after(80, self._sync_box_height))
        self._timers.append(self.after(120, self._fit_language_rows))
        # Check that the packages this build needs are actually here. (The
        # warm-up that used to sit beside this belongs to the process, not
        # the window, and starts in `main`.)
        self._timers.append(self.after(2500, self._repair_packages))
        self.bind("<Configure>", self._on_resize)

    def _place_swap(self, _event=None):
        """Centre the swap on the two boxes it sits between."""
        try:
            field = self.src_field
            panes = self.panes_frame
            middle = (field.winfo_rooty() - panes.winfo_rooty()
                      + field.winfo_height() / 2.0)
            if panes.winfo_height() > 1:
                self.swap_button.place_configure(
                    relx=0.5, y=int(middle), rely=0, anchor="center")
        except Exception:
            pass

    def _fit_language_rows(self):
        """Stretch the two language rows to their cards.

        A popup sizes itself to its widest choice, which is how every
        other one in the app should behave. These two are a row rather
        than a control: they span the card, and the card's width is not
        known until it has been laid out.
        """
        try:
            for picker in (self.src_lang, self.lang_dropdown):
                room = picker.master.winfo_width()
                if room > 40:
                    picker.set_width(room)
        except Exception:
            pass

    def _count_characters(self, _event=None):
        """How much is in the source box, as the design shows it."""
        try:
            body = self.file_src.get("1.0", "end-1c")
            self.char_count.configure(text="{:,} / 10,000".format(len(body)))
        except Exception:
            body = ""
        self._sync_drop_zone(bool(body.strip()))

    def _sync_drop_zone(self, has_text):
        """Out of the way once there is something to translate — but not
        taken away.

        It used to be unpacked the moment anything was typed. The whole
        box is the only way to open a file, so typing one word removed
        every way of opening one, and nothing brought it back: the text
        being cleared did not return it, because the only thing that
        called this was a key being released and clearing is not typing.
        A box with text in it had no file button for the rest of the
        session.

        So it shrinks rather than leaving. An empty box offers the full
        invitation; a box with text in it keeps one line of it, which is
        enough to say a file can still go here.
        """
        zone = getattr(self, "drop_zone", None)
        if zone is None or zone.is_working():
            return
        try:
            zone.compact(has_text)
            if has_text:
                self.file_src.pack_configure(fill="both", expand=True)
            else:
                self.file_src.pack_configure(fill="x", expand=False)
            if not zone.winfo_ismapped():
                zone.pack(fill="x", padx=ui_home.px(16),
                          pady=(0, ui_home.px(14)))
            zone.pack_configure(fill="both" if not has_text else "x",
                                expand=not has_text)
        except Exception:
            pass

    def _shortcut_keys(self):
        """The snip shortcut as the separate keys a keycap needs.

        `pretty` produces one string because that is what a line of prose
        wants. A row of keycaps wants them apart, and the modifiers on
        macOS are single symbols with nothing between them, so the split
        is by character there and by the plus sign everywhere else.
        """
        from .shortcut_field import pretty
        shown = pretty(CFG["hotkey"]) or ""
        if "+" in shown:
            return [part.strip() for part in shown.split("+") if part.strip()]
        return [ch for ch in shown if not ch.isspace()]

    def _touchpad_anywhere(self, event):
        widget = getattr(event, "widget", None)
        if isinstance(widget, tk.Text) and not getattr(widget,
                                                       "pass_wheel_up", False):
            return
        area = {"Translate": getattr(self, "home_scroll", None),
                "Settings": getattr(self, "settings_scroll", None),
                "Updates": getattr(self, "updates_scroll", None),
                "Support": getattr(self, "support_scroll", None)}.get(
                    self.current_pane)
        if area is None:
            return
        try:
            area._touchpad(event)
        except Exception:
            pass

    def _wheel_anywhere(self, event):
        """Send the wheel to whichever pane is on screen."""
        widget = getattr(event, "widget", None)
        if isinstance(widget, tk.Text) and not getattr(widget,
                                                       "pass_wheel_up", False):
            # A text box scrolls itself, and it has its own bar. Unless
            # it is one that grows with its contents and so has nothing
            # inside to scroll — for those the wheel belongs to the page,
            # and stepping aside for them is what made the page stop dead
            # the moment the pointer crossed the box.
            return
        area = {"Translate": getattr(self, "home_scroll", None),
                "Settings": getattr(self, "settings_scroll", None),
                "Updates": getattr(self, "updates_scroll", None),
                "Support": getattr(self, "support_scroll", None)}.get(
                    self.current_pane)
        if area is None:
            return
        try:
            area._wheel(event)
        except Exception:
            pass

    def _on_resize(self, event=None):
        if getattr(event, "widget", None) is not self:
            return
        if self._box_job:
            try:
                self.after_cancel(self._box_job)
            except Exception:
                pass
        self._box_job = self.after(60, self._sync_box_height)
        try:
            self._fit_language_rows()
            self._place_swap()
        except Exception:
            pass

    def _max_box_lines(self):
        """A ceiling on how far the boxes may grow.

        This used to be arithmetic on the window: how many lines fit
        before the button under the boxes falls off the bottom. The page
        scrolls now, so nothing falls off any more and that sum no longer
        has an answer — measured against a scrolling body it came out
        negative, the floor of four caught it, and the boxes stopped
        growing at all.

        What is left is worth keeping for a different reason. A box that
        grows without limit pushes everything under it out of view, so a
        long translation costs you the controls that act on it. Half the
        visible pane, whatever the window's size, leaves the other half
        for what comes next.
        """
        try:
            view = self.home_scroll.canvas.winfo_height()
            per_line = self.file_src.line_px()
            usable = view * 0.55 - self.file_src.chrome_px()
            # A few lines, not the page: past this the box scrolls.
            return max(4, min(self.MAX_BOX_LINES,
                              int(usable // max(1, per_line))))
        except Exception:
            return 12

    #: How tall the text boxes may grow while typing before they scroll.
    MAX_BOX_LINES = 8

    def _sync_box_height(self):
        """One height for both boxes: whatever the fuller of the two needs.

        The boxes used to be given the whole window, so a two-word
        translation sat in the middle of a very large empty rectangle. They
        now start small and grow with the text, which is what keeps the
        window compact when there is little in it.
        """
        self._box_job = None
        try:
            # The band's share of a window whose height has just
            # changed. Here rather than in the resize handler itself
            # because it repaints a photograph, and a photograph
            # repainted on every pixel of a drag is a window that does
            # not keep up with the hand.
            ui_home.HERO_CAP = int(self.winfo_height() * self.HERO_SHARE)
            self.hero_picture.recap()
        except Exception:
            pass
        try:
            self.update_idletasks()
            ceiling = self._max_box_lines()
            wanted = max(self.file_src.wanted_lines(),
                         self.file_dst.wanted_lines())
            lines = max(self.file_src.min_lines, min(ceiling, wanted))
            self.file_dst.set_lines(lines)
            # The caret area on the left is not the box on the right.
            # One height for both was right when both were a box and
            # nothing else; the left one now has the place a file goes
            # underneath it, and giving it the height of a three-line
            # translation left the dashed area with nothing — not
            # smaller, gone: pack cannot fit what there is no room for,
            # so it was not mapped at all and the whole way of opening a
            # file by dropping one disappeared from the page.
            #
            # So it takes what its own text needs, and what is left in
            # the field belongs to the drop area.
            own = max(self.file_src.min_lines,
                      min(ceiling, self.file_src.wanted_lines()))
            self.file_src.set_lines(own)
        except Exception:
            pass
        self._fit_fields()

    def _fit_fields(self):
        """Let the two fields grow with their text, both the same height.

        A field was held at its floor (FIELD_LEAST) whatever it held, so
        the box asked for eleven lines and was given four, and the place
        a file goes and the character count were pushed out of sight.
        Each field now takes what its contents ask for — never less than
        the floor, and with the text boxes capped at a few lines by
        `_max_box_lines`, never the whole page. Clearing brings them back
        to the floor, because the contents ask for less again.
        """
        try:
            self.update_idletasks()
            fields = (self.src_field, self.dst_field)
            pad = ui_home.px(2)
            def holds_text(pane):
                return bool(pane.text.get("1.0", "end-1c").strip()) and \
                    not getattr(pane, "_showing_placeholder", False)
            empty = not (holds_text(self.file_src)
                         or holds_text(self.file_dst))
            wanted = max(field.body.winfo_reqheight() for field in fields)
            # Empty, the fields are exactly as they open: the floor.
            height = ui_home.px(FIELD_LEAST) if empty else max(
                ui_home.px(FIELD_LEAST), wanted + pad)
            changed = False
            for field in fields:
                if int(field.cget("height")) != height:
                    field.configure(height=height)
                    changed = True
            if changed:
                # The page is laid out to the view's height; it has to be
                # told the content is taller (or shorter) now — and told
                # again once the rest of the page has settled, because a
                # page held at its old height never sees itself shrink.
                for _ in range(2):
                    self.update_idletasks()
                    self.home_scroll._lay_out()
                self.after(80, self.home_scroll._lay_out)
                self.after(250, self.home_scroll._lay_out)
        except Exception:
            pass

    AUTO = t("Detect language")

    @staticmethod
    def _make_read_only(text_widget):
        """Output, not input — but still selectable and copyable.

        Setting state="disabled" would do it, except the app has to keep
        writing results into the widget, and disabled text greys out and
        cannot be selected. Swallowing keystrokes keeps it looking and
        selecting like normal text while refusing edits.
        """
        allowed = {"c", "a"}          # copy and select-all

        def on_key(event):
            control = bool(event.state & 0x0004)     # Ctrl
            command = bool(event.state & 0x0008)     # Cmd on macOS
            if (control or command) and event.keysym.lower() in allowed:
                return None
            if event.keysym in ("Left", "Right", "Up", "Down", "Home", "End",
                                "Prior", "Next", "Shift_L", "Shift_R",
                                "Control_L", "Control_R", "Meta_L", "Meta_R"):
                return None
            return "break"

        text_widget.bind("<Key>", on_key)
        for sequence in ("<<Paste>>", "<<Cut>>", "<<Clear>>"):
            text_widget.bind(sequence, lambda _e: "break")

    def _on_source_lang(self, display_name):
        CFG.set("source_lang_name", display_name)
        self._last_translated = None
        if self.file_src.get("1.0", "end-1c").strip():
            self._schedule_auto()

    def source_code(self):
        """'auto' unless a specific source language was chosen."""
        name = CFG.get("source_lang_name", self.AUTO)
        if not name or name == self.AUTO:
            return "auto"
        return code_for_name(name) or "auto"

    def clear_text(self):
        """Empty both boxes and forget the pending translation."""
        if self._auto_job:
            try:
                self.after_cancel(self._auto_job)
            except Exception:
                pass
            self._auto_job = None
        self._last_translated = None
        # Nothing already in flight may land in a box that has just been
        # emptied. A translation started before this takes as long as it
        # takes, and arriving afterwards it used to fill the cleared box
        # back in — so clearing appeared to half work, and only sometimes,
        # which is the worst way for it to fail.
        self._text_token += 1
        self._fill(self.file_src, "")
        self._fill(self.file_dst, "")
        self.text_status.configure(text="")
        self.current_file = None
        self._translated_file = None
        # The box goes back to asking for a file. Left showing a finished
        # Download button it would offer a translation of a file that has
        # just been cleared away.
        self._release_drop_zone()
        # The counter and the box's own state are worked out from what is
        # in it, and both used to be worked out only when a key was
        # released — so after clearing, the count still read "12 / 10,000"
        # and the way to open a file stayed gone.
        self._count_characters()
        try:
            self.file_src.text.focus_set()
        except Exception:
            pass

    def swap_languages(self):
        """Send the translation back the other way.

        The obvious use is writing English and wanting Chinese, which the
        old one-way layout could not express at all.
        """
        target_name = self.lang_dropdown.get()
        source_name = self.src_lang.get()
        if source_name == self.AUTO:
            # Nothing to swap into the target box until the source is known;
            # use whatever was detected for the text on screen.
            detected = translator.guess_source(
                self.file_src.get("1.0", "end-1c"))
            source_name = name_for(detected) if detected else None
            if not source_name:
                self.text_status.configure(
                    text="Pick a language on the left first")
                return
        self.src_lang.set(target_name)
        self.lang_dropdown.set(source_name)
        self._on_source_lang(target_name)
        self._on_lang_change(source_name)

        left = self.file_src.get("1.0", "end-1c")
        right = self.file_dst.get("1.0", "end-1c")
        if right.strip():
            self._fill(self.file_src, right)
            self._fill(self.file_dst, left)
            self._schedule_auto()

    def _enable_drop(self, widget):
        """Accept files dropped onto the window, if tkdnd is present.

        Tk has no drag-and-drop of its own. tkinterdnd2 ships the tkdnd
        extension and can be loaded into an existing root, so this is a
        genuine drop target when the package is installed and simply does
        nothing when it is not — the Open file button still works either way.
        """
        try:
            from tkinterdnd2 import TkinterDnD, DND_FILES
        except Exception:
            return False
        try:
            TkinterDnD._require(self.controller.root)
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop)
            # And say so while the file is still in the air. Without
            # these the box gives no sign it will take the file, so a
            # drop that is about to work looks exactly like one that is
            # not — which is most of why it was thought broken even
            # where the extension was installed.
            widget.dnd_bind("<<DropEnter>>", self._drag_over)
            widget.dnd_bind("<<DropLeave>>", self._drag_away)
            return True
        except Exception:
            return False

    def _wire_drops(self):
        """Make every part of the box a drop target, and say whether it
        worked."""
        self._enable_drop(self.file_src.text)
        self._enable_drop(self)
        can_drop = False
        for target in self.drop_zone.droppable():
            can_drop = self._enable_drop(target) or can_drop
        # And say so either way. Drag and drop comes from an extension
        # that may not be on the machine, and the box said "drag a file
        # here" regardless — describing, on those machines, something
        # that was never going to happen, and leaving the one way in that
        # did work unmentioned.
        self.drop_zone.promise_drops(can_drop)
        # In the log too, so "drag and drop does not work" can be
        # answered from a log file rather than from a screenshot.
        try:
            from .main import log
            log("drag and drop: %s"
                % ("available" if can_drop
                   else "NOT available - tkinterdnd2 is not installed"))
        except Exception:
            pass
        return can_drop

    def _repair_packages(self):
        """Install anything this build needs and does not have.

        Not "has requirements.txt changed", which is what used to be
        asked and is a different question: a build that adds a package
        and fails to install it leaves a machine where the file has
        stopped changing and the package is still missing, and every
        check of the file after that says there is nothing to do. This
        asks whether the packages are importable, which is the thing that
        actually matters, and it asks on every start rather than only
        during an update — so a machine in that state repairs itself the
        next time the app opens instead of staying broken forever.

        Quiet when there is nothing to do, which is almost always.
        """
        from . import updater
        try:
            if not updater.own_environment():
                return
            missing = updater.missing_packages()
        except Exception:
            return
        if not missing:
            return

        def work():
            try:
                from .main import log
                log("missing packages: %s" % ", ".join(missing))
            except Exception:
                pass
            ok, said = updater.install_requirements()
            return ok, said, missing

        in_background(self, work, "_packages_repaired")

    def _packages_repaired(self, ok, said, missing):
        try:
            from .main import log
            log("package repair: %s (%s)" % ("ok" if ok else "failed", said))
        except Exception:
            pass
        if not ok:
            return
        # Wire the box up again rather than asking for a restart. The
        # extension loads into a running interpreter perfectly well, and
        # "restart to finish" is how a fix ends up not applied.
        try:
            if self._wire_drops():
                self.header_status.configure(
                    text=t("Drag and drop is ready to use"))
                self.after(6000,
                           lambda: self.header_status.configure(text=""))
        except Exception:
            pass

    def _drag_over(self, event=None):
        try:
            self.drop_zone.highlight(True)
        except Exception:
            pass
        return getattr(event, "action", None)

    def _drag_away(self, event=None):
        try:
            self.drop_zone.highlight(False)
        except Exception:
            pass
        return getattr(event, "action", None)

    def _on_drop(self, event):
        try:
            self.drop_zone.highlight(False)
        except Exception:
            pass
        raw = str(getattr(event, "data", "")).strip()
        # Tk hands over a brace-quoted list when paths contain spaces.
        if raw.startswith("{") and raw.endswith("}"):
            raw = raw[1:-1]
        path = raw.split("} {")[0].strip()
        if path:
            self.load_file(path)

    def pick_file(self):
        # One at a time. The whole drop zone is a click target, and a
        # click that lands while the chooser is already up puts a second
        # modal dialog behind the first one — the window looks frozen
        # until both have been dismissed, and only one of them is on
        # screen to dismiss.
        if getattr(self, "_choosing", False):
            return
        self._choosing = True
        try:
            self._pick_file()
        finally:
            self._choosing = False

    def _pick_file(self):
        path = filedialog.askopenfilename(
            title="Choose an image or PDF",
            filetypes=[("Images and PDF",
                        "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.pdf"),
                       ("PDF", "*.pdf"),
                       ("Images", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff "
                                  "*.webp"),
                       ("All files", "*.*")])
        if path:
            self.load_file(path)

    #: Which file the box is currently about. Every report a translation
    #: makes carries the number it started with, and one that no longer
    #: matches is thrown away — that is what taking a file back out of the
    #: box means, and it is the only thing that can mean it: the work
    #: happens on a thread, and a thread cannot be stopped from outside.
    _file_token = 0

    def cancel_file(self):
        """Take the file back out of the box.

        Whatever it was doing stops as far as anything can see: the next
        page it finishes finds its number stale and abandons the rest,
        and nothing it has already queued up to say gets said.
        """
        self._file_token += 1
        self.current_file = None
        self._translated_file = None
        self._release_drop_zone()
        try:
            self.file_src.text.focus_set()
        except Exception:
            pass

    def load_file(self, path):
        if not docs.is_supported(path):
            messagebox.showwarning(
                "Unsupported file",
                "Choose a JPG, PNG, TIFF, BMP, WEBP or PDF file.",
                parent=self)
            return
        if self.drop_zone.is_working():
            # One at a time. Two translations writing to the same box
            # would report over each other and the second would win the
            # Download button whatever order they finished in.
            return
        self._file_token += 1
        self.current_file = path
        self.file_src.delete("1.0", "end")
        self.file_dst.delete("1.0", "end")
        # Everything about this file is reported inside the box the file
        # went into. The band above the panes, the sentence under it and
        # the button at the end of another row were three places for one
        # thing, and the one you had to act on was the easiest of the
        # three to miss — see ProgressPill.
        self._show_download(False)
        self.drop_zone.begin(_short_name(path))
        threading.Thread(target=self._run_file,
                         args=(path, self._file_token), daemon=True).start()

    def _run_file(self, path, token=None):
        """Translate the file into a new file of the same kind.

        Emptying a PDF into a text box throws away the document — the
        layout, the tables, the picture the text sat beside. The translation
        is drawn back onto the page instead, and what comes out is a PDF.

        `token` is which file the box was about when this started. A
        thread cannot be stopped from outside, so taking the file back out
        is done by changing that number: the next thing this reports finds
        it stale and gives up where it stands, part-done, with nothing
        written and nothing said.
        """
        target = CFG["target_lang"]

        def alive():
            return token is None or token == self._file_token

        def guard():
            if not alive():
                raise _Abandoned()

        try:
            guard()
            self._post(self._say_file, token, 0.02, t("Reading\u2026"))

            def note(message):
                guard()
                self._post(self._say_file, token, None, message)

            def step(done, total):
                # A share of the whole, kept short of the end: the last
                # page still has to be written out, and a bar that sits
                # full while the file is still being saved says the work
                # is over when it is not.
                guard()
                if not total:
                    return
                self._post(self._say_file, token,
                           0.04 + 0.90 * (done / float(total)),
                           t("Translating page %d of %d")
                           % (min(done + 1, total), total))

            dest, pages, drawn, plain = file_translate.translate_file(
                path, target, progress=note, steps=step)
            guard()
            if not drawn:
                self._post(self._no_text_in_file, token)
                return
            self._translated_file = dest
            self._post(self._show_translated_file, token, dest, pages, target)
        except _Abandoned:
            return
        except Exception as exc:
            if not alive():
                return
            message = str(exc)
            self._post(self._file_failed, token, message)
            self._post(messagebox.showerror, "Squint", message)

    def _stale(self, token):
        """A report about a file that is no longer the one in the box."""
        return token is not None and token != self._file_token

    def _say_file(self, token=None, fraction=None, words=None):
        """Move the bar, and say what it is doing under it."""
        if self._stale(token):
            return
        try:
            zone = self.drop_zone
            if fraction is None:
                fraction = zone.pill.value()
            zone.step(fraction, note=words or "")
        except Exception:
            pass

    def _no_text_in_file(self, token=None):
        if self._stale(token):
            return
        try:
            self.drop_zone.failed("No readable text in this file")
            self.drop_zone.note_label.configure(
                text="Click to choose a different one.")
            self.drop_zone.after(
                2600, lambda n=self._file_token: self._release_drop_zone(n))
        except Exception:
            pass

    def _file_failed(self, token=None, message=""):
        if self._stale(token):
            return
        try:
            self.drop_zone.failed("Could not translate this file")
            self.drop_zone.note_label.configure(text=message[:90])
            self.drop_zone.after(
                3200, lambda n=self._file_token: self._release_drop_zone(n))
        except Exception:
            pass

    def _show_download(self, showing):
        """The button under the box, which is there only when there is
        something to download."""
        try:
            if showing:
                self.download_row.pack(fill="x", pady=(ui_home.px(12), 0),
                                       before=self.src_foot)
            else:
                self.download_row.pack_forget()
        except Exception:
            pass

    def _release_drop_zone(self, token=None):
        """Back to an empty box, so another file can be dropped."""
        if self._stale(token):
            return
        self._show_download(False)
        try:
            self.drop_zone.reset()
        except Exception:
            pass

    def _show_translated_file(self, token, dest, pages, target):
        """The bar finishes full, and the button under the box appears."""
        if self._stale(token):
            return
        self.drop_zone.finished(
            note="%d page%s translated into %s"
                 % (pages, "" if pages == 1 else "s", name_for(target)))
        self._show_download(True)

    def save_translated(self):
        """Copy the translated file wherever the user wants it."""
        source = getattr(self, "_translated_file", None)
        if not source or not os.path.isfile(source):
            return
        extension = os.path.splitext(source)[1]
        dest = filedialog.asksaveasfilename(
            title="Save translated file",
            initialfile=os.path.basename(source),
            defaultextension=extension,
            filetypes=[("Same format as the original", "*" + extension),
                       ("All files", "*.*")])
        if not dest:
            return
        try:
            import shutil
            if os.path.abspath(dest) != os.path.abspath(source):
                shutil.copyfile(source, dest)
            # Said where the file went in, not in a band elsewhere.
            self.drop_zone.note_label.configure(text="Saved to %s"
                                                % _short_name(dest))
        except Exception as exc:
            messagebox.showerror("Squint", str(exc), parent=self)

    def _fill(self, pane, content):
        pane.delete("1.0", "end")
        pane.insert("1.0", content)
        self._sync_box_height()

    def _copy(self, pane):
        content = pane.get("1.0", "end-1c")
        if not content.strip():
            return
        self.clipboard_clear()
        self.clipboard_append(content)
        self.update()
        self.header_status.configure(text="Copied to clipboard")
        self.after(1800, lambda: self.header_status.configure(text=""))

    def _schedule_auto(self, _event=None):
        """Debounce: translate once typing pauses, not on every keystroke."""
        if self._auto_job:
            try:
                self.after_cancel(self._auto_job)
            except Exception:
                pass
        self._auto_job = self.after(650, self._auto_translate)
        # Grow the box while typing, not only once a translation lands.
        if self._box_job is None:
            self._box_job = self.after(120, self._sync_box_height)

    def _auto_translate(self):
        self._auto_job = None
        content = self.text_src.get("1.0", "end-1c").strip()
        if not content or content == self._last_translated:
            return
        self.translate_text()

    def paste_clipboard(self):
        # Same reason as the clipboard shortcut: Tk's own read asks Windows
        # for the ANSI clipboard, which has no Chinese in it.
        from . import clipboard as clipboard_mod
        content = clipboard_mod.get_text(self)
        if content:
            self._fill(self.text_src, content)
            self._schedule_auto()

    #: Which text the boxes are currently about. Same idea as the file
    #: token: a translation cannot be stopped once it is running, so a
    #: result that comes back for text the boxes no longer hold is thrown
    #: away rather than written into them.
    _text_token = 0

    def translate_text(self):
        content = self.text_src.get("1.0", "end-1c").strip()
        if not content or self._translating:
            return
        self._translating = True
        token = self._text_token
        self.text_status.configure(text="Translating…",
                                   fg=self.palette["text_dim"])
        target = CFG["target_lang"]

        def work():
            try:
                out = translator.translate_best(content, target=target,
                                                source=self.source_code())
                self._post(self._text_done, token, content, out,
                           target, None)
            except Exception as exc:
                self._post(self._text_done, token, content, None, target,
                           str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _text_done(self, token, source, out, target, error):
        self._translating = False
        if token != self._text_token:
            # The box was cleared, or something else was put in it, while
            # this was on its way back.
            return
        if error:
            # In red and in the service's own words. A grey "Error: ..."
            # clipped to a few characters is why a failed translation read
            # as the app doing nothing at all.
            self.text_status.configure(text=error,
                                       fg=self.palette["danger"])
            return
        self._last_translated = source
        self._fill(self.text_dst, out)
        self.text_status.configure(
            text="Translated into %s  ·  %s"
                 % (name_for(target), translator.engine_label()),
            fg=self.palette["text_dim"])
        self._refresh_usage()
        # If more was typed while this was in flight, catch up.
        if self.text_src.get("1.0", "end-1c").strip() != source:
            self._schedule_auto()

    # -- settings pane -------------------------------------------------
    #
    # Every card is a list of settings, and every setting is one row: what
    # it is called and one line saying what it does on the left, the
    # control that changes it on the right, a hairline between rows. That
    # is the whole design.
    #
    # It was paragraphs before — a heading, three or four sentences of
    # explanation, then the controls underneath in a row of their own —
    # which reads as a manual with switches in it. The explanations have
    # not gone; they are one line each, beside the thing they explain,
    # which is the only place anybody reads them.
    #: The rhythm of a settings card, in the design's own pixels — so it
    #: keeps its proportions at every window size, which raw numbers do
    #: not. The rows were tight and the type was large, which is the
    #: wrong way round: a settings page is read one line at a time and
    #: wants air between the lines, not weight in them.
    ROW_PAD = 28

    #: What the right-hand column of a settings row is worth, in the
    #: design's own pixels. Every grey line on the left wraps to whatever
    #: is left of the card after this, so all of them end on one edge —
    #: and the number is a decision rather than a measurement, which is
    #: what makes it the same on a Mac and on a PC and the same twice in
    #: a row on either.
    CONTROL_W = 380
    ROW_GAP_Y = 22
    PANEL_GAP = 28

    def _panel(self, wrap, title, first=False, ruled=False):
        """A card with a name at the top. Rows go in what it returns.

        `ruled` puts a hairline under the name. For a card whose rows are
        a list of things rather than a set of settings: the name is a
        column heading there, and a heading floating over the first row
        with nothing between them reads as part of it.
        """
        p = self.palette
        card = Surface(wrap, p, radius=16, padding=0, bg=p["window"])
        card.pack(fill="x", padx=(0, 4),
                  pady=(0 if first else ui_home.px(self.PANEL_GAP), 0))
        head = tk.Frame(card.body, bg=p["surface"])
        head.pack(fill="x", padx=ui_home.px(self.ROW_PAD),
                  pady=(ui_home.px(22), ui_home.px(16)))
        label(head, p, title, size=10, weight="bold",
              bg=p["surface"]).pack(anchor="w")
        if ruled:
            divider(card.body, p).pack(fill="x",
                                       padx=ui_home.px(self.ROW_PAD))
        body = tk.Frame(card.body, bg=p["surface"])
        body.pack(fill="x", pady=(0, ui_home.px(8)))
        return body

    def _setting(self, body, title, note="", last=False):
        """One row of a card. Returns the frame the control goes in."""
        p = self.palette
        row = tk.Frame(body, bg=p["surface"])
        row.pack(fill="x", padx=ui_home.px(self.ROW_PAD),
                 pady=ui_home.px(self.ROW_GAP_Y))
        # The control claims its side first. `pack` hands out space in
        # the order it is asked, so a column of words packed before it
        # takes what it wants and the control on the right is clipped —
        # which is how a Save & test button ends up outside the card.
        holder = tk.Frame(row, bg=p["surface"])
        holder.pack(side="right")
        words = tk.Frame(row, bg=p["surface"])
        words.pack(side="left", fill="x", expand=True)
        if title:
            label(words, p, title, size=10, bg=p["surface"]).pack(anchor="w")
        line = None
        if note:
            line = label(words, p, note, size=9, dim=True, bg=p["surface"],
                         justify="left", anchor="w", wraplength=400)
            line.pack(anchor="w", fill="x")
        if line is not None:
            # Measured against the row, never against the column the
            # label is in: a label wrapped to its own parent's width sets
            # that width, which sets the wrap, which sets the width — and
            # the column walks itself down to nothing.
            # Collected rather than measured here. Every one of these
            # gets the *same* width, worked out once for the whole pane
            # — see `_even_wraps`. Measuring each row against its own
            # control gave every grey line a different right-hand edge,
            # because every row has a different control beside it: a
            # switch, a dropdown, a button with a longer word on it. Six
            # rows, six ragged edges, down a card whose whole point is
            # that its rows line up.
            self._wrap_lines.append((line, holder))
        if not last:
            divider(body, p).pack(fill="x", padx=ui_home.px(self.ROW_PAD))
        return holder

    def _panel_note(self, body, words):
        """The line along the bottom of a card, for what belongs to the
        whole of it rather than to any one row."""
        p = self.palette
        strip = tk.Frame(body, bg=p["surface"])
        strip.pack(fill="x", padx=ui_home.px(self.ROW_PAD),
                   pady=(ui_home.px(8), ui_home.px(14)))
        line = label(strip, p, words, size=9, dim=True, bg=p["surface"],
                     justify="left", anchor="w", wraplength=600)
        line.pack(anchor="w", fill="x")
        self._wrap_lines.append((line, None))
        return strip

    # The glossary card in Settings. Off for now; the glossary still applies.
    SHOW_GLOSSARY = False

    def _build_settings(self, parent):
        p = self.palette
        area = ScrollArea(self._pad(parent, top=20), p)
        area.pack(fill="both", expand=True)
        wrap = area.body
        self.settings_scroll = area
        from .shortcut_field import ShortcutField
        from . import ocr as ocr_mod
        from . import profile as profile_mod
        from . import i18n
        self.profile_mod = profile_mod

        label(wrap, p, t("Settings"), size=11, weight="bold",
              bg=p["window"]).pack(anchor="w", pady=(0, 10))

        # -- shortcuts --------------------------------------------------
        body = self._panel(wrap, t("Shortcuts"), first=True)
        holder = self._setting(
            body, t("Snip & translate"),
            "Tap to snip. Hold to see the whole screen translated; press "
            "the letter twice while holding to keep it up.")
        self.hk_snip = ShortcutField(
            holder, p, value=CFG["hotkey"],
            on_change=lambda spec: self._on_hotkey_captured(spec, "hotkey"),
            bg=p["surface"])
        self.hk_snip.pack(side="right")
        holder = self._setting(body, t("Translate clipboard"),
                               "Translates whatever you last copied.")
        self.hk_clip = ShortcutField(
            holder, p, value=CFG["hotkey_clipboard"],
            on_change=lambda spec: self._on_hotkey_captured(
                spec, "hotkey_clipboard"),
            bg=p["surface"])
        self.hk_clip.pack(side="right")
        # A way back that does not require knowing what the defaults were.
        # Somebody who has just bound something unfortunate is, by
        # definition, in the worst position to type the right answer in.
        holder = self._setting(body, t("Reset to defaults"),
                               "Puts both shortcuts back.", last=True)
        PillButton(holder, t("Reset"), command=self._reset_hotkeys,
                   palette=p, kind="secondary", height=Dropdown.HEIGHT,
                   bg=p["surface"]).pack(side="right")
        # Said only when there is something to say — an empty status line
        # is still a line. It hangs off a holder that is always packed,
        # because every direct child of a card must stay mapped.
        strip = tk.Frame(body, bg=p["surface"])
        strip.pack(fill="x", padx=ui_home.px(self.ROW_PAD))
        self.hk_footer = tk.Frame(strip, bg=p["surface"])
        self.hk_status = label(self.hk_footer, p, "", size=9, dim=True,
                               bg=p["surface"], wraplength=600,
                               justify="left")
        self.hk_status.pack(side="left")
        # Whether macOS is letting the clipboard shortcut copy for the
        # user. Shown before it fails, not only after: the failure is
        # silent by design on Apple's side.
        self._permission_row(body, p)

        # -- engines ----------------------------------------------------
        body = self._panel(wrap, t("Engines"))
        holder = self._setting(
            body, t("Translating"),
            "Automatic walks the list until one answers.")
        self.engine_choice = Dropdown(
            holder, p, self._profile_names(), value=self._profile_display(),
            command=self._on_profile_change, max_width=300,
            bg=p["surface"])
        self.engine_choice.pack(side="right")
        # The escape hatch. "The local reading looks wrong" is a guess and
        # has to be — Windows OCR pointed at a language it has no pack for
        # returns plausible Latin junk rather than failing.
        self.var_cloud_read = tk.BooleanVar(
            value=bool(CFG.get(profile_mod.CLOUD_READ_KEY, False)))
        holder = self._setting(
            body, t("Reading text"),
            "This computer reads first. Turn this on to always read with "
            "the cloud engine instead.")
        Switch(holder, p, variable=self.var_cloud_read,
               command=self._on_cloud_read, bg=p["surface"]).pack(
                   side="right")
        # A verdict per key, beside the key it is about. There was one
        # line under all of them once, in one colour, so an exhausted
        # Gemini allowance painted a working Google key red.
        self.key_marks = {}
        self.var_aikey = tk.StringVar(value=CFG.get("gemini_api_key", ""))
        self.var_gkey = tk.StringVar(value=CFG.get("google_api_key", ""))
        self.var_dkey = tk.StringVar(value=CFG.get("deepl_api_key", ""))
        self.var_qkey = tk.StringVar(value=CFG.get("groq_api_key", ""))
        # Two free keys with no card, in front. Google and DeepL need an
        # account with a card on it, so they wait behind "Advanced
        # translation" for whoever wants them — shown already open for
        # somebody who has one of their keys saved, so a key is never
        # hidden from the person who put it there.
        self.key_fields = []
        self.key_doors = []
        self.key_hows = []
        primary = (
            ("Gemini", self.var_aikey,
             "Free, no card. Understands context and reads screenshots."),
            ("Groq", self.var_qkey, "Free, no card. Very fast."))
        for name, var, note in primary:
            self._key_row(body, name, var, note)
        # The switch, and under it the two that need a card. The frame
        # that holds them is always packed — every direct child of a card
        # must stay mapped — and only what is inside it comes and goes.
        advanced = tk.Frame(body, bg=p["surface"])
        advanced.pack(fill="x")
        toggle_row = tk.Frame(advanced, bg=p["surface"])
        toggle_row.pack(fill="x", padx=ui_home.px(self.ROW_PAD),
                        pady=(ui_home.px(8), ui_home.px(8)))
        self.advanced_button = DisclosureRow(
            toggle_row, p, "Advanced translation",
            "Google and DeepL · need a card", "+",
            self._toggle_advanced_keys)
        self.advanced_button.pack(fill="x")
        self.advanced_rows = tk.Frame(advanced, bg=p["surface"])
        divider(self.advanced_rows, p).pack(
            fill="x", padx=ui_home.px(self.ROW_PAD))
        for name, var, note, last in (
                ("DeepL", self.var_dkey,
                 "Strongest on European languages.", False),
                ("Google", self.var_gkey,
                 "Google Translate and Cloud Vision.", True)):
            self._key_row(self.advanced_rows, name, var, note, last=last)
        self._show_advanced_keys(self._advanced_wanted())
        # Measured once the three exist, and applied to all three: the
        # widest label decides, so no row is narrower than its own words
        # and no two rows differ.
        try:
            translator.load_key_checks()
            self.after(50, self._mark_keys)
        except Exception:
            pass
        self._fits.append(self._square_up_keys)
        self._fits.append(self._even_wraps)
        strip = self._panel_note(
            body,
            "Keys are free to get and sidestep the rate limits on the open "
            "services. The free Gemini allowance is per day and is not "
            "large: reading a screenshot spends one request and translating "
            "spends another.")
        # The how-to for each key now sits on its own row, as "How?".
        links = tk.Frame(body, bg=p["surface"])
        links.pack(fill="x", padx=ui_home.px(self.ROW_PAD), pady=(0, 12))
        PillButton(links, "Test connection", command=self._test_connection,
                   palette=p, kind="ghost", height=Dropdown.HEIGHT,
                   bg=p["surface"]).pack(side="left", padx=(0, 6))
        self.key_status = label(body, p, "", size=9, dim=True,
                                bg=p["surface"], wraplength=600,
                                justify="left")
        self.key_status.pack(anchor="w", padx=ui_home.px(self.ROW_PAD), pady=(0, 4))
        # How much of Google's free allowance is gone this month. Without
        # this the first sign of overrunning it would be a bill.
        self.usage_label = label(body, p, "", size=9, dim=True,
                                 bg=p["surface"])
        self.usage_label.pack(anchor="w", padx=ui_home.px(self.ROW_PAD), pady=(0, 10))
        self._refresh_usage()

        # What the one control resolved to, what the reader can read, and
        # whether a language pack is missing — the three things the pair
        # of choices above cannot say for themselves.
        notes = tk.Frame(body, bg=p["surface"])
        notes.pack(fill="x", padx=ui_home.px(self.ROW_PAD), pady=(0, 10))
        self.profile_note = label(notes, p, "", size=9, dim=True,
                                  wraplength=600, justify="left",
                                  bg=p["surface"])
        self.profile_note.pack(anchor="w")
        self.ocr_note = label(notes, p, "", size=9, dim=True,
                              wraplength=600, justify="left",
                              bg=p["surface"])
        self.ocr_note.pack(anchor="w", pady=(6, 0))
        self._update_ocr_note()
        warning = self._ocr_warning(ocr_mod)
        self.ocr_warning_label = label(
            notes, p, warning, size=9, wraplength=600, justify="left",
            bg=p["surface"])
        self.ocr_warning_label.configure(fg=p["warning"])
        self.ocr_warning_label.pack(anchor="w", pady=(6, 0))
        if not warning:
            self.ocr_warning_label.pack_forget()
        self._langpack_row(notes, p)
        self.engine_note = label(notes, p, "", size=9, dim=True,
                                 wraplength=600, justify="left",
                                 bg=p["surface"])
        self.engine_note.pack(anchor="w", pady=(6, 0))
        self._update_engine_note()
        self._say_profile(self._profile_text(profile_mod))

        # -- offline, beside the engines it stands in for ----------------------------------------------------
        # A list of what is on the machine, one language a row, rather
        # than a single picker that had to say what it would do to
        # whatever was selected. What somebody wants from this card is
        # "what have I got, what does it cost me, and how do I add
        # another" — three questions a list answers by being a list.
        self.offline_panel = self._panel(wrap, t("Offline translation"),
                                         ruled=True)
        self._build_offline_rows()

        # -- behaviour --------------------------------------------------
        body = self._panel(wrap, t("Behaviour"))
        self.var_copy = tk.BooleanVar(value=CFG["auto_copy"])
        self.var_orig = tk.BooleanVar(value=CFG["show_original"])
        self.var_startup = tk.BooleanVar(
            value=CFG["run_at_startup"] or platform_util.run_at_login_is_set())
        self.var_overlay = tk.BooleanVar(value=CFG.get("overlay_mode", True))
        self.var_clickaway = tk.BooleanVar(
            value=CFG.get("close_on_click_away", True))
        self.var_readahead = tk.BooleanVar(
            value=CFG.get("read_ahead", False))
        self.var_selecticon = tk.BooleanVar(
            value=CFG.get("select_icon", True))
        switches = (
            ("Squint icon on selected text",
             "Select text in any app and a small Squint icon appears "
             "beside it. Click it to translate.", self.var_selecticon,
             lambda: self.controller.set_select_icon(
                 self.var_selecticon.get())),
            ("Replace the text in place",
             "Draw the translation over the original, keeping its position "
             "and colour.", self.var_overlay,
             lambda: CFG.set("overlay_mode", self.var_overlay.get())),
            ("Close when you click away",
             "Dismiss the translation as soon as you click elsewhere.",
             self.var_clickaway,
             lambda: CFG.set("close_on_click_away",
                             self.var_clickaway.get())),
            ("Copy translations to the clipboard",
             "Every result is ready to paste straight away.", self.var_copy,
             lambda: CFG.set("auto_copy", self.var_copy.get())),
            ("Show the detected text",
             "The popup also shows what was read off the screen.",
             self.var_orig,
             lambda: CFG.set("show_original", self.var_orig.get())),
            ("Start with Windows", "Runs quietly in the tray.",
             self.var_startup, self._toggle_startup))
        for index, (title, note, var, command) in enumerate(switches):
            holder = self._setting(body, title, note,
                                   last=index == len(switches) - 1)
            Switch(holder, p, variable=var, command=command,
                   bg=p["surface"]).pack(side="right")

        # -- appearance -------------------------------------------------
        body = self._panel(wrap, t("Appearance"))
        # "Overlay text size" was a lie: it set the font on the result
        # card and the drawn overlay ignored it completely. It is one
        # number for both now, and the name says so.
        holder = self._setting(
            body, t("Text size"),
            "The result card, and the smallest the translation drawn over "
            "a page is allowed to get.")
        self.font_size = Dropdown(
            holder, p, [str(n) for n in range(9, 25)], bg=p["surface"],
            value=str(CFG.get("popup_font_size", 12)),
            command=self._on_font_size, min_width=90)
        self.font_size.pack(side="right")
        holder = self._setting(body, t("App language"),
                               "What Squint's own words are in.", last=True)
        self.app_language = Dropdown(
            holder, p, i18n.language_names(), value=i18n.current_name(),
            bg=p["surface"],
            command=self._on_app_language, max_width=220)
        self.app_language.pack(side="right")
        self.app_language_soon = None
        if len(i18n.LANGUAGES) < 2:
            # Said here rather than as a greyed-out entry in the list: a
            # language that cannot be chosen has no business being in a
            # list of languages you choose from.
            self.app_language_soon = label(
                body, p, "More languages coming soon.", size=9, dim=True,
                bg=p["surface"])
            self.app_language_soon.pack(anchor="w", padx=ui_home.px(self.ROW_PAD),
                                        pady=(0, 8))
        self.font_preview = label(
            body, p, "The quick brown fox jumps over the lazy dog.",
            size=int(CFG.get("popup_font_size", 12)), bg=p["surface"])
        self.font_preview.pack(anchor="w", padx=ui_home.px(self.ROW_PAD), pady=(0, 10))
        self.app_language_note = label(body, p, "", size=9, dim=True,
                                       bg=p["surface"])

        # -- glossary ---------------------------------------------------
        # Hidden for now. The glossary itself still works: the file is
        # read on every translation whether this card is shown or not.
        if self.SHOW_GLOSSARY:
            body = self._panel(wrap, t("Your glossary"))
            holder = self._setting(
                body, "Words to leave alone",
                "Product names, model codes, the way your company writes "
                "things. One rule a line; an update never touches this file.",
                last=True)
            PillButton(holder, t("Open"), command=self._open_glossary, palette=p,
                       kind="secondary", height=Dropdown.HEIGHT,
                       bg=p["surface"]).pack(side="left")
            PillButton(holder, t("Show folder"), command=self._open_data_dir,
                       palette=p, kind="ghost", height=Dropdown.HEIGHT,
                       bg=p["surface"]).pack(side="left", padx=(6, 0))
            self.glossary_path = label(body, p, self._glossary_where(), size=9,
                                       dim=True, wraplength=600, justify="left",
                                       bg=p["surface"])
            self.glossary_path.pack(anchor="w", padx=ui_home.px(self.ROW_PAD), pady=(0, 10))


    # Which service does the translating. "Automatic" is the fallback chain
    # the app has always used; the rest pin it to one.
    ENGINE_CHOICES = (
        ("auto", "Automatic — best available"),
        ("gemini", "Gemini (free key, understands context)"),
        ("offline", "Offline, on this computer"),
        ("gtx", "Google (free, rate-limited)"),
        ("google-api-key", "Google, with API key"),
        ("deepl-api-key", "DeepL, with API key"),
        ("groq", "Groq (free key)"),
        ("mymemory", "MyMemory (free)"),
    )

    ENGINE_NOTES = {
        "auto": "Tries the fastest thing that works and remembers it.",
        "gemini": "A language model, so it knows brand names from words. "
                  "Needs the free Gemini key below.",
        "offline": "On-device · no internet · nothing sent anywhere · "
                   "needs the language downloaded above.",
        "gtx": "Good quality and free, but shared per network — your office "
               "connection is rate-limited (HTTP 429).",
        "google-api-key": "Best quality. Needs a key below; 500,000 "
                          "characters a month are free.",
        "deepl-api-key": "Needs a DeepL key below.",
        "groq": "A fast language model on a free key with no card. "
                "Needs the Groq key below.",
        "mymemory": "Free, no key, works anywhere — but the plainest wording.",
    }

    # Languages whose scripts a Latin recogniser cannot produce by accident
    # — the ones where a missing pack shows up as nonsense rather than as
    # slightly worse reading.
    NON_LATIN_HEADS = ("zh", "ja", "ko", "ru", "uk", "el", "ar", "he", "th",
                       "hi", "bg", "sr", "fa")

    # Which engine reads the screen. The first is what everyone should
    # leave it on; the other two exist because one sends the selection to
    # Google and the other refuses to.
    OCR_CHOICES = (
        ("auto", "Automatic — this computer first"),
        ("local", "This computer only"),
        ("gemini", "Gemini (free key, no card)"),
        ("cloud", "Google Cloud Vision"),
    )

    # -- the key rows -------------------------------------------------
    KEY_DOORS = {
        "Gemini": ("Get free key", "_get_gemini_key"),
        "Groq": ("Get free key", "_open_groq_keys"),
        "DeepL": ("Get a key", "_open_deepl_signup"),
        "Google": ("Set up", "_open_google_setup"),
    }

    def _key_row(self, body, name, var, note, last=False):
        """Name and note; the verdict dot, the key, the way to get one,
        and How? for the picture guide to getting it."""
        p = self.palette
        holder = self._setting(body, name, note, last=last)
        mark = label(holder, p, "", size=10, bg=p["surface"])
        mark.pack(side="left", padx=(0, 10))
        self.key_marks[name] = mark
        field = Field(holder, p, textvariable=var, width=10, height=34,
                      bg=p["surface"], fill=p["field_on_card"])
        field.pack(side="left")
        self.key_fields.append(field)
        # Saved on the way out of the box. A key typed and never saved is
        # the worst of both — the app looks configured and is not.
        for event in ("<FocusOut>", "<Return>"):
            field.entry.bind(event,
                             lambda _e=None: self._save_keys(quiet=True),
                             add="+")
        words, method = self.KEY_DOORS[name]
        door = PillButton(holder, t(words), command=getattr(self, method),
                          palette=p, kind="secondary",
                          height=Dropdown.HEIGHT, bg=p["surface"])
        door.pack(side="left", padx=(10, 0))
        self.key_doors.append(door)
        how = PillButton(holder, "How?", command=self._how_to(name),
                         palette=p, kind="ghost", height=Dropdown.HEIGHT,
                         bg=p["surface"])
        how.pack(side="left", padx=(4, 0))
        self.key_hows.append(how)

    def _how_to(self, name):
        """The picture guide for this key where there is one, else the
        written guide."""
        which = {"Gemini": "gemini", "Groq": "groq",
                 "Google": "google"}.get(name)
        if which:
            return self._help_for(which)
        return self._open_key_help

    def _advanced_wanted(self):
        remembered = CFG.get("show_advanced_keys", None)
        if remembered is not None:
            return bool(remembered)
        return bool(CFG.get("google_api_key", "")
                    or CFG.get("deepl_api_key", ""))

    def _show_advanced_keys(self, show):
        self._advanced_open = bool(show)
        try:
            if show:
                self.advanced_rows.pack(fill="x")
            else:
                self.advanced_rows.pack_forget()
            self.advanced_button.set_open(show)
        except Exception:
            pass
        try:
            self.engine_choice.values = self._profile_names()
        except Exception:
            pass

    def _toggle_advanced_keys(self):
        show = not getattr(self, "_advanced_open", False)
        CFG.set("show_advanced_keys", show)
        self._show_advanced_keys(show)

    @staticmethod
    def _profiles_shown():
        """The Translating list: Google and DeepL only once Advanced is
        open, or when one of them is in use or has a key."""
        from . import profile as profile_mod
        opened = CFG.get("show_advanced_keys", None)
        if opened is None:
            opened = bool(CFG.get("google_api_key", "")
                          or CFG.get("deepl_api_key", ""))
        current = profile_mod.current()
        needs = {profile_mod.GOOGLE: "google_api_key",
                 profile_mod.DEEPL: "deepl_api_key"}
        shown = []
        for key, text in profile_mod.PROFILES:
            if key in needs and not (opened or key == current
                                     or CFG.get(needs[key], "")):
                continue
            shown.append((key, text))
        return shown

    @staticmethod
    def _profile_names():
        """The list, with the ones that cannot work saying why.

        Greyed rather than hidden, and never selectable-then-silently-
        ignored: offering a choice that cannot act and quietly doing
        something else is exactly what the language pack list did for
        three releases.
        """
        from . import profile as profile_mod
        names = []
        for key, text in MainWindow._profiles_shown():
            reason = profile_mod.why_not(key)
            names.append("%s  (%s)" % (text, reason) if reason else text)
        return names

    @staticmethod
    def _profile_display():
        from . import profile as profile_mod
        current = profile_mod.current()
        for (key, text), shown in zip(MainWindow._profiles_shown(),
                                      MainWindow._profile_names()):
            if key == current:
                return shown
        return MainWindow._profile_names()[0]

    @staticmethod
    def _profile_key(display_name):
        from . import profile as profile_mod
        for (key, _text), shown in zip(MainWindow._profiles_shown(),
                                       MainWindow._profile_names()):
            if shown == display_name:
                return key
        return profile_mod.AUTO

    def _on_profile_change(self, display_name):
        from . import profile as profile_mod
        key = self._profile_key(display_name)
        # A keyed engine with no key is refused, because choosing it would
        # silently do something else. "On this computer" with no engine
        # installed is allowed, because it is a policy about where the
        # text may go rather than a request for a particular service —
        # and its failure mode is a plain refusal on screen rather than an
        # invisible substitution.
        if key != profile_mod.LOCAL and profile_mod.why_not(key):
            # Put the control back rather than accept a choice that
            # cannot be honoured.
            try:
                self.engine_choice.set(self._profile_display())
            except Exception:
                pass
            self._say_profile(
                "That one %s. Add it under Translation quality below."
                % profile_mod.why_not(key), warn=True)
            return
        profile_mod.set_profile(key)
        translator._preferred = None
        translator._cache.clear()
        self._refresh_profile()

    def _on_cloud_read(self):
        from . import profile as profile_mod
        CFG.set(profile_mod.CLOUD_READ_KEY, bool(self.var_cloud_read.get()))
        self._refresh_profile()

    def _refresh_profile(self):
        from . import profile as profile_mod
        try:
            self._say_profile(self._profile_text(profile_mod))
        except Exception:
            pass
        self._update_ocr_note()
        self._update_engine_note()
        self._refresh_ocr_warning()

    @staticmethod
    def _profile_text(profile_mod):
        """What this choice is for, then what it resolved to right now.

        The second half is the part that makes collapsing two dropdowns
        into one safe. The old Translating control showed which engine was
        going to answer; that information did not stop being useful when
        the control went away, and it is also the answer to the question
        that started all this — "I chose this computer, why is Google
        answering".
        """
        about = profile_mod.ABOUT.get(profile_mod.current(), "")
        try:
            resolved = profile_mod.summary()
        except Exception:
            resolved = ""
        return ("%s\n%s" % (about, resolved)).strip()

    def _say_profile(self, text, warn=False):
        widget = getattr(self, "profile_note", None)
        if widget is None:
            return
        widget.configure(
            text=text,
            fg=self.palette["warning" if warn else "text_dim"])

    def _langpack_row(self, parent, p):
        """Choose a Windows text-recognition pack and install it.

        The first version of this took the language from the source
        dropdown, which is the wrong input: somebody whose source is set to
        English pressed it and was told Windows does not offer a pack for
        en-US — true, useless, and nothing to do with the Chinese they were
        trying to read. What is wanted is not "the language I am reading
        right now" but "which pack should this computer have", and those
        are different questions.

        So it lists what Windows actually offers on this edition and lets
        the user pick. Asking Windows takes a second or two, so it happens
        off the main thread and the row fills itself in when the answer
        arrives.
        """
        from . import win_langpack
        if not win_langpack.supported():
            return
        # Folded away: PaddleOCR already reads Chinese, Japanese, Korean
        # and English, so these packs are for the other scripts.
        self._langpack_outer = outer = tk.Frame(parent, bg=p["surface"])
        outer.pack(fill="x", pady=(0, 10))
        self.langpack_toggle = DisclosureRow(
            outer, p, "More reading languages",
            "Arabic, Russian, Thai, Hindi… · free Windows packs", "A",
            self._toggle_langpacks)
        self.langpack_toggle.pack(fill="x")
        self._langpack_frame = frame = tk.Frame(outer, bg=p["surface"])
        self._langpacks_open = False
        self.langpack_status = label(
            frame, p, "Asking Windows which text-recognition packs it "
                      "offers…", size=9, dim=True, wraplength=620,
            justify="left", bg=p["surface"])
        self.langpack_status.pack(anchor="w")
        self._langpack_packs = {}
        threading.Thread(target=self._load_langpacks, daemon=True).start()

    def _toggle_langpacks(self):
        self._show_langpack_list(not getattr(self, "_langpacks_open", False))

    def _show_langpack_list(self, show):
        self._langpacks_open = bool(show)
        try:
            if show:
                self._langpack_frame.pack(fill="x", pady=(10, 0))
            else:
                self._langpack_frame.pack_forget()
            self.langpack_toggle.set_open(show)
        except Exception:
            pass

    def _load_langpacks(self, status=None):
        from . import win_langpack
        try:
            packs = win_langpack.available_packs()
            note = win_langpack.last_note
        except Exception as exc:
            packs, note = [], str(exc)
        self._post(self._show_langpacks, packs, note, status)

    # Windows names its packs with a script subtag; the app's language
    # list uses regions. Neither is wrong, and they do not meet without
    # this.
    PACK_NAMES = {"zh-hans": "zh-CN", "zh-hant": "zh-TW",
                  "pt-pt": "pt", "pt-br": "pt", "nb": "no", "iw": "he"}

    # Windows offers several packs per language and the app's table has
    # one name for each. Without these, three Chinese packs and two
    # Serbian ones come out with the same word in front of them and the
    # list stops being a list of choices.
    PACK_LABELS = {
        "zh-cn": "Chinese (Simplified)",
        "zh-tw": "Chinese (Traditional)",
        "zh-hk": "Chinese (Hong Kong)",
        "sr-cyrl-rs": "Serbian (Cyrillic)",
        "sr-latn-rs": "Serbian (Latin)",
        "bs-latn-ba": "Bosnian",
        "pt-br": "Portuguese (Brazil)",
        "pt-pt": "Portuguese (Portugal)",
        "es-es": "Spanish (Spain)",
        "es-mx": "Spanish (Mexico)",
        "fr-fr": "French",
        "fr-ca": "French (Canada)",
        "en-gb": "English (UK)",
        "en-us": "English (US)",
    }

    @staticmethod
    def _pack_name(tag):
        """"Chinese (Simplified)", or "" when the app has no name for it.

        Kept apart from the label because a sentence about the pack wants
        the language, not the tag and not the mark in front of it.
        """
        low = str(tag).lower()
        name = MainWindow.PACK_LABELS.get(low, "")
        if name:
            return name
        # Longest first: zh-Hans before zh, or every Chinese pack gets the
        # same name and the list becomes unusable.
        for attempt in (low, "-".join(low.split("-")[:2]),
                        low.split("-")[0]):
            mapped = MainWindow.PACK_NAMES.get(attempt, attempt)
            found = name_for(mapped) or ""
            if found and found.lower() != mapped.lower():
                return found
        return ""

    @staticmethod
    def _pack_label(tag, installed):
        """"● Chinese (Simplified) — zh-CN", or the tag on its own.

        The tag stays visible because three Chinese packs and two
        Portuguese ones differ only by it, and a list with the same word
        three times in it is worse than one with codes in it.

        The filled and hollow marks are the ones the offline translation
        list already uses. Two lists in one panel, both saying "you have
        this one and not that one", had two different ways of saying it —
        a dot in one and the word "(installed)" trailing the other — which
        makes them look like unrelated controls rather than the same idea
        twice.
        """
        name = MainWindow._pack_name(tag)
        shown = ("%s — %s" % (name, tag)) if name else str(tag)
        return "%s  %s" % ("●" if installed else "○", shown)

    def _show_langpacks(self, packs, note="", status=None):
        """Draw the row. `status` is (text, kind) to put back afterwards.

        The list is redrawn after an install, and redrawing destroys the
        line that said the install worked. Carrying it through is the
        difference between "Installed" and a row that silently resets
        itself the moment it succeeds.

        There are two lines under the dropdown, and separating them is the
        other half of the same fix. One describes the pack you have
        highlighted and changes whenever you open the list; the other says
        what happened last time you pressed Install. They used to be the
        same label, so opening the dropdown to look at something erased
        the answer — which is how an install that had failed for minutes
        came to look as though nothing had been pressed at all.
        """
        p = self.palette
        self._langpack_note = note
        frame = getattr(self, "_langpack_frame", None)
        if frame is None:
            return
        for child in frame.winfo_children():
            child.destroy()
        if not packs:
            self.langpack_status = label(
                frame, p, "This edition of Windows offers no text-"
                          "recognition packs to add. A Gemini or Google key "
                          "above still lets Squint read anything.",
                size=9, dim=True, wraplength=620, justify="left",
                bg=p["surface"])
            self.langpack_status.pack(anchor="w")
            return

        # Alphabetical by the name on screen, not by the tag behind it.
        #
        # Sorting on the tag is alphabetical and looks wrong, which is the
        # only test that matters: zh-CN puts Chinese after Turkish, and
        # sr-CYRL-RS puts Serbian after Slovenian. Nobody scans a list of
        # languages by their BCP-47 codes. They read the words.
        packs = sorted(packs, key=lambda item: (
            self._pack_name(item[0]) or str(item[0]), str(item[0]).lower()))
        self._langpack_packs = {}
        names = []
        for tag, capability, installed in packs:
            shown = self._pack_label(tag, installed)
            names.append(shown)
            self._langpack_packs[shown] = (capability, installed)

        row = tk.Frame(frame, bg=p["surface"])
        row.pack(fill="x")
        self.langpack_choice = Dropdown(row, p, names, value=names[0],
                                        command=self._on_langpack_choice,
                                        max_width=340, bg=p["surface"])
        self.langpack_choice.pack(side="left")
        self.langpack_button = PillButton(
            row, "Install", command=self._install_langpack, palette=p,
            kind="primary", height=Dropdown.HEIGHT, bg=p["surface"])
        self.langpack_button.pack(side="left", padx=(12, 0))
        self.langpack_status = label(
            frame, p, "", size=9, dim=True, wraplength=620,
            justify="left", bg=p["surface"])
        self.langpack_status.pack(anchor="w", pady=(8, 0))
        # The line the dropdown cannot touch: what the last install did,
        # and what it is doing now while it does it.
        self.langpack_result = label(
            frame, p, "", size=9, dim=True, wraplength=620,
            justify="left", bg=p["surface"])
        self._on_langpack_choice(names[0])
        if status:
            text, kind = status
            self.langpack_result.configure(text=text, fg=p[kind])
            self.langpack_result.pack(anchor="w", pady=(6, 0))
            if getattr(self, "_langpack_restart_needed", False):
                PillButton(frame, "Restart Squint",
                           command=self._restart_for_langpack, palette=p,
                           kind="primary", height=Dropdown.HEIGHT,
                           bg=p["surface"]).pack(anchor="w", pady=(8, 0))
        if note:
            label(frame, p, note, size=9, dim=True, wraplength=620,
                  justify="left", bg=p["surface"]).pack(anchor="w",
                                                        pady=(6, 0))

    def _on_langpack_choice(self, shown):
        capability, installed = self._langpack_packs.get(shown, (None, False))
        del capability
        try:
            self.langpack_button.set_enabled(not installed)
        except Exception:
            pass
        self.langpack_status.configure(
            text=("Windows already has this one."
                  if installed else
                  # The size is worth saying because the line below this
                  # one mentions a 2 GB download for a different thing
                  # entirely, and the two got read as one.
                  "Free, and nothing to sign up for. Windows will ask "
                  "permission. The pack is a few megabytes, but Windows "
                  "takes several minutes to put it in place."),
            fg=self.palette["text_dim"])

    def _install_langpack(self):
        from . import win_langpack
        shown = self.langpack_choice.get() if hasattr(
            self.langpack_choice, "get") else self.langpack_choice._value
        capability, installed = self._langpack_packs.get(shown, (None, False))
        if capability is None or installed:
            return
        self.langpack_button.set_enabled(False)
        found = win_langpack.CAPABILITY.match(str(capability))
        self._langpack_naming = self._pack_name(
            found.group(2)) if found else ""
        self._langpack_started = time.time()
        self._langpack_running = True
        self._langpack_tick()

        def work():
            ok, message = win_langpack.install(capability)
            self._post(self._langpack_done, ok, message, capability)

        threading.Thread(target=work, daemon=True).start()

    BAR_WIDTH = 24

    @staticmethod
    def _bar(percent, width=None):
        """A bar made of characters, because it cannot break the layout.

        A drawn widget would look better and would be another thing that
        can size itself wrongly inside a card that has had trouble with
        exactly that. This is a label, like the line it replaces.
        """
        width = MainWindow.BAR_WIDTH if width is None else width
        filled = int(round(width * max(0, min(100, percent)) / 100.0))
        return "%s%s  %d%%" % ("█" * filled, "░" * (width - filled),
                               int(percent))

    def _langpack_tick(self):
        """What Windows is doing, said once a second.

        A percentage when there is one and a clock when there is not, and
        that order matters. The first version had only the clock, because
        I had decided there was no progress to be had — the cmdlet reports
        through PowerShell's progress stream, which is the one stream that
        cannot be redirected out of a hidden shell. That was true and the
        conclusion drawn from it was wrong: DISM prints a percentage, and
        the person waiting had watched it do so in his own console while
        being told by this panel that nothing could be known.

        DISM still says nothing for the first stretch while it works out
        what it is doing, and an install can pass five minutes, so the
        clock stays for the time before the first percentage and for any
        machine where the reading does not arrive at all.
        """
        if not getattr(self, "_langpack_running", False):
            return
        widget = getattr(self, "langpack_result", None)
        if widget is None:
            return
        seconds = int(time.time() - getattr(self, "_langpack_started",
                                            time.time()))
        name = getattr(self, "_langpack_naming", "") or "the pack"
        percent = None
        try:
            from . import win_langpack
            percent = win_langpack.progress()
        except Exception:
            percent = None
        clock = "%d:%02d" % (seconds // 60, seconds % 60)
        if percent is None:
            text = ("Installing %s — %s elapsed. Windows is working on it; "
                    "several minutes is normal. You can leave this open."
                    % (name, clock))
        else:
            text = ("Installing %s\n%s   %s elapsed"
                    % (name, self._bar(percent), clock))
        try:
            widget.configure(text=text, fg=self.palette["text_dim"])
            if not widget.winfo_ismapped():
                widget.pack(anchor="w", pady=(6, 0))
            self.after(1000, self._langpack_tick)
        except Exception:
            self._langpack_running = False

    def _langpack_done(self, ok, message, capability=None):
        """Say what actually happened, and stop the rest of the panel lying.

        The install succeeded and three other things on screen still said
        it had not: the amber line above ("This PC can only read de, en"),
        the reading note, and the dropdown, which went on offering the
        pack that had just been installed. All three are built once, when
        the panel is built, and none of them was told.
        """
        self._langpack_running = False
        try:
            self.langpack_button.set_enabled(True)
        except Exception:
            pass
        self._langpack_restart_needed = False
        if ok:
            message = self._langpack_ready(capability, message)
        widget = getattr(self, "langpack_result", None) or self.langpack_status
        widget.configure(
            text=message, fg=self.palette["success" if ok else "danger"])
        try:
            if not widget.winfo_ismapped():
                widget.pack(anchor="w", pady=(6, 0))
        except Exception:
            pass
        self._update_ocr_note()
        self._refresh_ocr_warning()
        if ok:
            # Asking Windows again is the only way to know, and it is slow
            # enough to belong on a thread.
            threading.Thread(
                target=self._load_langpacks,
                args=((message, "success"),), daemon=True).start()

    def _langpack_ready(self, capability, message):
        """Whether Squint can use the pack now, or has to be restarted.

        Nothing on the Python side caches the language list — it is asked
        of the OCR engine every time. Whether the engine itself caches it
        for the life of the process is not documented either way, and
        Windows can also still be finishing the download after the
        elevated command has returned. So rather than hedging in both
        directions every time, this looks.
        """
        from . import win_langpack
        self._langpack_restart_needed = False
        found = win_langpack.CAPABILITY.match(str(capability or ""))
        tag = found.group(2) if found else ""
        visible = False
        if tag:
            try:
                from . import ocr_windows
                visible = bool(ocr_windows.resolve_tag(tag))
            except Exception:
                visible = False
        name = self._pack_name(tag) if tag else ""
        if visible:
            return ("Installed. Squint can read %s now." % name) if name \
                else "Installed."
        self._langpack_restart_needed = True
        return ("Installed. Squint has to start again before it can use "
                "it — Windows may still be finishing the download.")

    def _restart_for_langpack(self):
        from . import updater
        widget = getattr(self, "langpack_result", None) or self.langpack_status
        widget.configure(text="Restarting…", fg=self.palette["success"])
        self.update_idletasks()
        try:
            self.after(300, updater.restart)
        except Exception:
            widget.configure(
                text="Close Squint and start it again to finish.",
                fg=self.palette["text_dim"])

    def _refresh_ocr_warning(self):
        """Redraw the amber line, which a new pack may have made untrue."""
        widget = getattr(self, "ocr_warning_label", None)
        if widget is None:
            return
        from . import ocr as ocr_mod
        try:
            text = self._ocr_warning(ocr_mod)
        except Exception:
            return
        if not text:
            widget.pack_forget()
            return
        widget.configure(text=text, fg=self.palette["warning"])
        if not widget.winfo_ismapped():
            frame = getattr(self, "_langpack_outer", None) or getattr(
                self, "_langpack_frame", None)
            try:
                if frame is not None and frame.winfo_exists():
                    widget.pack(anchor="w", pady=(0, 10), before=frame)
                else:
                    widget.pack(anchor="w", pady=(0, 10))
            except Exception:
                widget.pack(anchor="w", pady=(0, 10))

    def _update_ocr_note(self):
        from . import ocr as ocr_mod
        widget = getattr(self, "ocr_note", None)
        if widget is None:
            return
        choice = ocr_mod.ocr_choice()
        local = ocr_mod.local_engine_name()
        try:
            tags = ocr_mod.readable_languages()
        except Exception:
            tags = []
        reads = (" — reads %s" % ", ".join(tags[:6])) if tags else ""
        has_key = bool(CFG.get("google_api_key", ""))
        has_gemini = bool(CFG.get("gemini_api_key", ""))

        if choice == "local":
            note = ("%s%s. Nothing leaves this computer. Anything it has no "
                    "pack for will come back unreadable." % (local, reads))
        elif choice == "gemini":
            note = ("Every screenshot is read by Gemini. Reads Chinese, "
                    "Japanese, Korean, Russian and Arabic properly, and the "
                    "key is free with no card. On the free tier Google may "
                    "use what it reads to improve its products, so use Cloud "
                    "Vision for anything confidential.")
            if not has_gemini:
                note = ("Needs the free Gemini key below — a Google account, "
                        "no card, about a minute. Until then this falls back "
                        "to %s." % local)
        elif choice == "cloud":
            note = ("Every screenshot is read by Google Cloud Vision. "
                    "Reads Chinese, Japanese, Korean, Russian and Arabic "
                    "properly; 1,000 a month are free, then $1.50 per "
                    "1,000.")
            if not has_key:
                note = ("Needs the Google Translate key below, and Cloud "
                        "Vision enabled for that key. Until then this "
                        "falls back to %s." % local)
        else:
            behind = "Google Cloud Vision"
            if has_gemini and not has_key:
                behind = "Gemini"
            elif has_gemini and has_key:
                behind = "Google Cloud Vision, then Gemini"
            note = ("%s%s, with %s behind it for anything it cannot read. "
                    "Google is only asked when the reading fails or comes "
                    "back as nonsense." % (local, reads, behind))
            if not has_key and not has_gemini:
                note = ("%s%s. Add the free Gemini key below — a Google "
                        "account, no card — and anything this computer "
                        "cannot read is handled by Google instead of "
                        "failing." % (local, reads))
        widget.configure(text=note, fg=self.palette["text_dim"])

    @staticmethod
    def _ocr_summary(ocr_mod):
        """"Windows OCR — reads en-US, de-DE  ·  Google Cloud Vision when
        it cannot"."""
        name = ocr_mod.engine_name()
        try:
            tags = ocr_mod.readable_languages()
        except Exception:
            tags = []
        if tags:
            shown = ", ".join(tags[:6])
            if len(tags) > 6:
                shown += ", …"
            name = "%s — reads %s" % (name, shown)
        try:
            backup = ocr_mod.use_cloud_vision() and ocr_mod.engine_name() \
                != "Google Cloud Vision"
        except Exception:
            backup = False
        if backup:
            name += "  ·  Google Cloud Vision when it cannot"
        return name

    def _ocr_warning(self, ocr_mod):
        """Say when the PC cannot read the language the user is aiming at.

        Windows recognises exactly the languages it has packs for. Pointed
        at anything else it does not fail — it returns plausible-looking
        rubbish, which the app then translates and draws over the page.
        Nothing in the app can fix that; the pack is a Windows download.
        """
        try:
            tags = ocr_mod.readable_languages()
        except Exception:
            return ""
        if not tags:
            return ""
        heads = {str(tag).split("-")[0].lower() for tag in tags}
        if heads & set(self.NON_LATIN_HEADS):
            return ""
        try:
            covered = ocr_mod.use_cloud_vision()
        except Exception:
            covered = False
        try:
            paddle = ocr_mod.use_paddle()
        except Exception:
            paddle = False
        if paddle:
            # PaddleOCR, installed with Squint, reads Chinese, Japanese
            # and Korean on this computer. Russian and Arabic are what is
            # left, and only somebody reading those needs to hear it.
            if covered:
                return ""
            return ("This PC reads %s itself, and Chinese, Japanese and "
                    "Korean with PaddleOCR. For Russian or Arabic, add the "
                    "free Gemini key above."
                    % ", ".join(sorted(heads)))
        if covered:
            # Handled — the reading note says which engine does what, and
            # an amber warning about a solved problem is just noise.
            return ""
        # The order of the two answers is the whole point of this text.
        #
        # It used to say "add one below" and mention the key afterwards,
        # so that is what people did — and the pack is the harder path by
        # a long way. It needs administrator rights, Windows downloads it
        # and takes minutes, and on a managed work laptop the answer may
        # simply be no. The key takes about a minute, needs nothing from
        # the machine, and covers every language at once.
        #
        # The pack still has a reason to exist, and it is named rather
        # than implied: it is the answer for somebody who does not want
        # the screen leaving the computer, and it keeps working with no
        # network at all. That is a real reason to take the harder path.
        # Being the first thing suggested to everybody was not.
        return ("This PC can only read %s. Chinese, Japanese, Korean, "
                "Russian and Arabic will come back as nonsense. The "
                "quickest fix is the free Gemini key above — a Google "
                "account, no card, about a minute, and it reads every "
                "language. If you would rather nothing left this "
                "computer, add a Windows pack below instead: it needs "
                "administrator rights and takes a few minutes."
                % ", ".join(sorted(heads)))


    def _update_engine_note(self):
        from . import profile as profile_mod
        key = {profile_mod.LOCAL: "offline", profile_mod.GEMINI: "gemini",
               profile_mod.GOOGLE: "google-api-key",
               profile_mod.DEEPL: "deepl-api-key",
               profile_mod.GROQ: "groq"}.get(
                   profile_mod.current(), "auto")
        note = self.ENGINE_NOTES.get(key, "")
        if key == "auto":
            note += "  Currently using: %s." % translator.active_backend()
        colour = self.palette["text_dim"]
        # Choosing an engine that cannot run is not refused — every engine
        # falls back, which is what keeps the app working when one service
        # is down. But falling back silently makes the dropdown a lie: it
        # said "Offline, on this computer" while every translation went to
        # Google, and the only clue was a line in the result card.
        unavailable = self._engine_unavailable(key)
        if unavailable:
            note = unavailable
            colour = self.palette["warning"]
        self.engine_note.configure(text=note, fg=colour)

    def _engine_unavailable(self, key):
        """Why the chosen engine cannot answer, or "".

        Only for the two that can be chosen and then not exist: offline
        needs a downloaded model, and the keyed services need a key.
        """
        if key == "offline":
            from . import local_engine, offline_model
            if offline_model.ready():
                return ""
            if not local_engine.available():
                # Without the import error on the end. "No module named
                # 'argostranslate'" is true, is the reason, and is not
                # something to put in front of somebody who wanted to
                # translate a bicycle advertisement.
                # No longer "so translations are going online instead" —
                # they are not. On this computer means it, and refusing is
                # the point rather than a shortcoming.
                return ("The offline engine is not installed on this "
                        "computer, so nothing here can translate and "
                        "Squint will not send your text to a web service "
                        "after you have said not to. Install it under "
                        "Offline translation above, or choose another "
                        "engine.")
            source = code_for_name(CFG.get("source_lang_name", "")) or ""
            target = CFG.get("target_lang", "en")
            if source and source != "auto" and not local_engine.has_pair(
                    source, target):
                return ("No offline model for %s → %s is downloaded, so "
                        "those translations are going to the free online "
                        "service instead. Download one under Offline "
                        "translation below."
                        % (name_for(source) or source,
                           name_for(target) or target))
            if not local_engine.installed_pairs():
                return ("No offline models are downloaded yet, so "
                        "translations are going to the free online service "
                        "instead. Download one under Offline translation "
                        "below.")
            return ""
        needs_key = {"gemini": "gemini_api_key",
                     "google-api-key": "google_api_key",
                     "deepl-api-key": "deepl_api_key",
                     "groq": "groq_api_key"}
        name = needs_key.get(key)
        if name and not CFG.get(name, ""):
            return ("No %s key is saved, so translations are going to the "
                    "free online service instead. Add one above."
                    % {"gemini": "Gemini",
                       "google-api-key": "Google Translate",
                       "deepl-api-key": "DeepL",
                       "groq": "Groq"}[key])
        return ""


    def _on_font_size(self, value):
        try:
            size = int(value)
        except ValueError:
            return
        CFG.set("popup_font_size", size)
        self.font_preview.configure(
            font=theme_mod.font(self, size))

    def _on_app_language(self, display_name):
        """Change the language, and offer to restart rather than instruct.

        Every label is built when the window is built, so nothing already
        on screen changes until the app starts again. Saying "restart
        Squint to see the change" and leaving it there makes the setting
        look as though it did nothing — and the user then presses it again.
        A button that does the restarting is one action instead of three.
        """
        from . import i18n
        i18n.set_language_by_name(display_name)
        self.app_language_note.configure(
            text="Squint has to start again to change the labels that are "
                 "already on screen.",
            fg=self.palette["text_dim"])
        self.app_language_note.pack(anchor="w", pady=(10, 0))
        button = getattr(self, "app_language_restart", None)
        if button is None:
            self.app_language_restart = button = PillButton(
                self.app_language_note.master, t("Restart now"),
                command=self._restart_for_language, palette=self.palette,
                kind="primary", height=Dropdown.HEIGHT,
                bg=self.palette["surface"])
        button.pack(anchor="w", pady=(10, 0))

    def _restart_for_language(self):
        from . import updater
        self.app_language_note.configure(
            text="Restarting…", fg=self.palette["success"])
        self.update_idletasks()
        try:
            self.after(300, updater.restart)
        except Exception:
            self.app_language_note.configure(
                text="Close Squint and start it again to finish.",
                fg=self.palette["text_dim"])

    def _offer_pack_if_missing(self):
        """Say when the chosen language has no offline model yet.

        Picking a target language and silently falling back to a web service
        is the sort of thing that only shows up later as 'why is it slow' or
        'why did it fail' — so it is said here, next to the choice.
        """
        # Retired with the per-language engine. Hy-MT2 covers every
        # language, and this line on the front page read as a fault — "No
        # offline model for English yet" on a Mac that was translating
        # perfectly well online. Anything left of it is cleared.
        try:
            if "offline model for" in str(self.header_status.cget("text")):
                self.header_status.configure(text="")
        except Exception:
            pass

    # -- offline language packs -----------------------------------------
    # The languages worth offering first. Anything else can still be typed
    # into the box; these are the ones people actually snip.
    OFFLINE_LANGS = [("zh", "Chinese"), ("ja", "Japanese"), ("ko", "Korean"),
                     ("de", "German"), ("fr", "French"), ("es", "Spanish"),
                     ("it", "Italian"), ("pt", "Portuguese"),
                     ("ru", "Russian"), ("ar", "Arabic"), ("hi", "Hindi"),
                     ("nl", "Dutch"), ("pl", "Polish"), ("tr", "Turkish"),
                     ("sv", "Swedish")]

    def _offline_choices(self):
        """Just the language name, with a dot when it is already here.

        "Chinese → English" repeated down a list is noise: the target is
        whatever you picked at the top, and it is the same on every row.
        """
        from . import local_engine
        try:
            # Any installed model that mentions a language means that
            # language is here. Downloading one fetches both directions, so
            # tying the dot to the current target only confused things.
            pairs = local_engine.installed_pairs()
            have = {a for a, _b in pairs} | {b for _a, b in pairs}
        except Exception:
            have = set()
        # Only what is not here yet. The ones that are have a row of
        # their own above; offering them again in the list of things to
        # add was the picker having to explain itself with a dot.
        other = CFG["target_lang"].split("-")[0]
        return [name for code, name in self.OFFLINE_LANGS
                if code not in have and code != other]

    # A language sits in the list once it is on the machine; what it
    # costs is measured off the disk, because the packages report where
    # they live and not how big they are.
    # -- Hy-MT2 on this computer ---------------------------------------
    def _build_hymt(self, body):
        from . import offline_model as om
        p = self.palette
        self.var_offline = tk.BooleanVar(
            value=bool(CFG.get("offline_enabled", False)))
        holder = self._setting(
            body, "Translate on this computer",
            "When there is no internet, or Gemini and Groq are busy or out "
            "for the day. Free, private, no key — nothing leaves the "
            "computer.")
        Switch(holder, p, variable=self.var_offline,
               command=self._on_offline_switch,
               bg=p["surface"]).pack(side="right")

        holder = self._setting(
            body, "Model",
            "Hy-MT2 by Tencent. One download covers all 33 languages. It "
            "downloads in the "
            "background and carries on where it stopped if interrupted.")
        om.retire_old()
        try:
            om.upgrade_engine()
        except Exception:
            pass
        label(holder, p, om.MODELS["standard"]["label"], size=10,
              bg=p["surface"]).pack(side="right")

        row = tk.Frame(body, bg=p["surface"])
        row.pack(fill="x", padx=ui_home.px(self.ROW_PAD),
                 pady=(ui_home.px(4), ui_home.px(12)))
        self.hymt_bar = ProgressBar(row, p, height=8)
        self.hymt_status = label(row, p, "", size=9, dim=True,
                                 bg=p["surface"], wraplength=520,
                                 justify="left")
        self.hymt_status.pack(side="left", anchor="w")
        self.hymt_remove = PillButton(row, t("Remove"),
                                      command=self._hymt_remove, palette=p,
                                      kind="ghost", height=Dropdown.HEIGHT,
                                      bg=p["surface"])
        self.hymt_pause = PillButton(row, t("Pause"),
                                     command=self._hymt_pause, palette=p,
                                     kind="secondary",
                                     height=Dropdown.HEIGHT, bg=p["surface"])
        self._hymt_refresh()
        # Downloaded before the self-test existed, or never tested: test it
        # now, once, so the line above says whether it actually runs.
        try:
            if CFG.get("offline_enabled") and om.installed(om.chosen()) \
                    and om.engine_path() and om.tested() is None:
                self.after(1500, self._hymt_test)
        except Exception:
            pass

    def _on_offline_switch(self, *_):
        from . import offline_model as om
        on = bool(self.var_offline.get())
        CFG.set("offline_enabled", on)
        # Switched off by hand: not fetched or switched on again by itself.
        CFG.set("offline_declined", not on)
        if on and not om.installed(om.chosen()):
            self._hymt_start()
        if not on:
            om.stop()
        self._hymt_refresh()

    def _hymt_start(self):
        from . import offline_model as om
        CFG.set("offline_declined", False)
        CFG.set("offline_paused", False)
        om.start_download(om.chosen())
        self._hymt_poll()

    def _hymt_pause(self):
        from . import offline_model as om
        state = om.download_state()["state"]
        if state == "downloading":
            om.pause_download()
            CFG.set("offline_paused", True)   # not resumed by itself
        elif om.installed(om.chosen()) and om.engine_path():
            self._hymt_test()
            return
        else:
            self._hymt_start()
        self.after(300, self._hymt_refresh)

    def _hymt_remove(self):
        from . import offline_model as om
        om.pause_download()
        om.remove(om.chosen())
        CFG.set("offline_declined", True)
        self._hymt_refresh()

    def _hymt_poll(self):
        from . import offline_model as om
        self._hymt_refresh()
        try:
            state = om.download_state()["state"]
            if state == "downloading" and self.winfo_exists():
                self.after(700, self._hymt_poll)
            elif state == "ready":
                self._hymt_test()
        except Exception:
            pass

    def _hymt_test(self):
        """Load the model and translate a line, in the background. A
        finished download says nothing about whether it runs here."""
        from . import offline_model as om
        if getattr(self, "_hymt_testing", False):
            return
        if not (om.installed(om.chosen()) and om.engine_path()):
            return
        self._hymt_testing = True
        try:
            self.hymt_status.configure(
                text="Testing %s on this computer…" % om.MODELS[
                    om.chosen()]["label"].split(" ·")[0])
        except Exception:
            pass
        in_background(self, om.self_test, "_hymt_tested")

    def _hymt_tested(self, ok, message):
        self._hymt_testing = False
        self._hymt_refresh()

    def _hymt_refresh(self):
        """Say where it stands, and show only the buttons that apply."""
        from . import offline_model as om
        try:
            state = om.download_state()
            which = om.chosen()
            info = om.MODELS.get(which, om.MODELS["standard"])
            size_gb = info["size"] / 1e9
            for widget in (self.hymt_bar, self.hymt_pause,
                           self.hymt_remove):
                widget.pack_forget()
            if state["state"] == "downloading" and state["which"] == which:
                done, total = state["done"], max(1, state["total"])
                self.hymt_bar.pack(side="top", fill="x", pady=(0, 6),
                                   before=self.hymt_status)
                self.hymt_bar.set(done / float(total))
                text = "Downloading %s… %d MB of %d MB" % (
                    info["label"].split(" ·")[0], done // 1_000_000,
                    total // 1_000_000)
                self.hymt_pause.configure_text(t("Pause"))
                self.hymt_pause.pack(side="right")
            elif om.installed(which) and om.engine_path():
                name = info["label"].split(" ·")[0]
                verdict = om.tested(which)
                if verdict is None:
                    text = "Downloaded: %s. Not tested yet." % name
                elif verdict[0]:
                    text = "Ready: %s %s." % (name, verdict[1])
                else:
                    text = ("%s is downloaded but does not run here: %s"
                            % (name, verdict[1]))
                if not CFG.get("offline_enabled"):
                    text += " Switched off above."
                self.hymt_remove.pack(side="right")
                self.hymt_pause.configure_text(t("Test"))
                self.hymt_pause.pack(side="right", padx=(0, 6))
            elif state["state"] == "paused" and state["which"] == which:
                text = "Paused at %d MB of %d MB." % (
                    state["done"] // 1_000_000, state["total"] // 1_000_000)
                self.hymt_pause.configure_text(t("Resume"))
                self.hymt_pause.pack(side="right")
                self.hymt_remove.pack(side="right", padx=(0, 6))
            elif state["state"] == "failed" and state["which"] == which:
                text = "Download stopped: %s" % state["error"]
                self.hymt_pause.configure_text(t("Try again"))
                self.hymt_pause.pack(side="right")
            elif CFG.get("offline_enabled"):
                text = "Not downloaded yet (%.1f GB)." % size_gb
                self.hymt_pause.configure_text(t("Download"))
                self.hymt_pause.pack(side="right")
            else:
                text = ("Off. Switch it on to download %s (%.1f GB)."
                        % (info["label"].split(" ·")[0], size_gb))
            self.hymt_status.configure(text=text)
        except Exception:
            pass
        # "On this computer only (needs the offline engine)" was worked out
        # when Settings opened and stayed so after the download finished.
        try:
            self.engine_choice.values = self._profile_names()
            self.engine_choice.set(self._profile_display())
        except Exception:
            pass

    def _build_offline_rows(self):
        """Draw the card: one row a language, then the row that adds one.

        Rebuilt outright whenever the set changes. A list of what is
        installed is not a thing that can be patched in place — a
        language leaving takes its row, its size and its button with it.
        """
        body = getattr(self, "offline_panel", None)
        if body is None:
            return
        from . import local_engine
        p = self.palette
        for child in body.winfo_children():
            child.destroy()
        self.remove_buttons = {}

        # Hy-MT2 first: it is what most people will use here. The older
        # per-language engine only shows where it is already installed.
        self._build_hymt(body)
        if not local_engine.available():
            self.offline_choice = None
            self.pack_button = None
            self.remove_button = None
            self.offline_status = None
            return

        # The per-language engine came before Hy-MT2, which covers every
        # language in one download. Its rows are folded under one line,
        # closed while Hy-MT2 is set up: laid out in full they were most
        # of the card, and read as the thing to download.
        from . import offline_model as om
        outer = tk.Frame(body, bg=p["surface"])
        outer.pack(fill="x", padx=ui_home.px(self.ROW_PAD),
                   pady=(ui_home.px(8), ui_home.px(8)))
        self.older_toggle = DisclosureRow(
            outer, p, "Older offline languages", "", "A",
            self._toggle_older_langs)
        self.older_toggle.pack(fill="x")
        self._older_rows = section = tk.Frame(outer, bg=p["surface"])

        names = dict(self.OFFLINE_LANGS)
        other = CFG["target_lang"].split("-")[0]
        try:
            pairs = local_engine.installed_pairs()
        except Exception:
            pairs = []
        here = {a for a, _b in pairs} | {b for _a, b in pairs}
        installed = sorted((code for code, _name in self.OFFLINE_LANGS
                            if code in here and code != other),
                           key=lambda c: names[c])

        total = 0
        for code in installed:
            holder = self._setting(section, names[code], "")
            size = 0
            try:
                size = local_engine.language_size(code, other)
            except Exception:
                size = 0
            total += size or 0
            if size:
                label(holder, p, self._megabytes(size), size=9, dim=True,
                      bg=p["surface"]).pack(side="left",
                                            padx=(0, ui_home.px(16)))
            # No padding of its own. Every other pill in the app takes
            # the default, which is a plain number; this one was handed a
            # scaled one, so on a display that scales below 1.0 it was
            # the only pill in the window whose label lost its breathing
            # space while every pill beside it kept theirs.
            button = PillButton(
                holder, t("Remove"),
                command=lambda c=code: self._remove_pack(c), palette=p,
                kind="secondary", height=Dropdown.HEIGHT, bg=p["surface"])
            button.pack(side="left")
            self.remove_buttons[code] = button
        # The one the older tests and the rest of this file reach for.
        self.remove_button = (self.remove_buttons[installed[-1]]
                              if installed else None)

        # Nothing new to add once Hy-MT2 is here: it covers every one of
        # these. What is installed stays usable, and removable.
        if om.installed(om.chosen()):
            self.offline_choice = None
            self.pack_button = None
            if installed:
                self._setting(section, "",
                              "Not needed with Hy-MT2. They are used only "
                              "if Hy-MT2 cannot answer; remove them to "
                              "free the space.", last=True)
            self.offline_status = label(body, p, "", size=9, dim=True,
                                        wraplength=600, justify="left",
                                        bg=p["surface"])
            self.older_toggle.note.configure(
                text=("%d installed · %s · not needed with Hy-MT2"
                      % (len(installed), self._megabytes(total)))
                if installed else "Replaced by Hy-MT2")
            self._show_older_langs(bool(getattr(self, "_older_open", False)))
            if not installed:
                outer.pack_forget()
            self._offline_foot = None
            return

        choices = self._offline_choices()
        holder = self._setting(
            section, t("Add a language"),
            "Downloaded once, then it works with no internet at all.",
            last=True)
        self.offline_pick = holder
        self.offline_choice = Dropdown(
            holder, p, choices or [t("Nothing left to add")],
            value=(choices or [t("Nothing left to add")])[0],
            width=ui_home.px(150), bg=p["surface"],
            command=lambda _v: self._sync_pack_buttons())
        self.offline_choice.pack(side="left")
        self.pack_button = PillButton(
            holder, t("Download"), command=self._download_pack, palette=p,
            kind="primary", height=Dropdown.HEIGHT, bg=p["surface"],
            icon="download")
        self.pack_button.pack(side="left", padx=(ui_home.px(14), 0))

        # Where a download says how it is getting on. Empty and unpacked
        # until there is something to say: an always-there status line is
        # a blank row of card for the ninety-nine per cent of the time
        # nothing is downloading.
        note = ("%d installed · %s · Hy-MT2 above covers all of these"
                % (len(installed), self._megabytes(total))
                if installed else "One language at a time, before Hy-MT2")
        self.older_toggle.note.configure(text=note)
        wanted = getattr(self, "_older_open", None)
        if wanted is None:
            wanted = not om.installed(om.chosen())
        self._show_older_langs(wanted)
        self.offline_status = label(body, p, "", size=9, dim=True,
                                    wraplength=600, justify="left",
                                    bg=p["surface"])
        self._offline_foot = self._panel_note(
            body,
            "Slower than the online engines and a little blunter, but "
            "nothing leaves the machine.")
        self._sync_pack_buttons()

    def _toggle_older_langs(self):
        self._show_older_langs(not getattr(self, "_older_open", False))

    def _show_older_langs(self, show):
        self._older_open = bool(show)
        try:
            if show:
                self._older_rows.pack(fill="x", pady=(ui_home.px(6), 0))
            else:
                self._older_rows.pack_forget()
            self.older_toggle.set_open(show)
        except Exception:
            pass

    @staticmethod
    def _megabytes(size):
        """A model's size, in the unit people think of models in."""
        return "%d MB" % max(1, int(round(size / (1024.0 * 1024.0))))

    def _say_offline(self, text, colour=None):
        """Put a line under the Add row, or take it away again."""
        widget = getattr(self, "offline_status", None)
        if widget is None:
            return
        try:
            widget.configure(text=text,
                             fg=colour or self.palette["text_dim"])
            if text:
                # Above the card's own footnote, not under it: packing
                # it plainly sends it to the end of the card, which is
                # below the line explaining what offline translation is.
                foot = getattr(self, "_offline_foot", None)
                where = {"before": foot} if foot is not None else {}
                widget.pack(anchor="w", padx=ui_home.px(self.ROW_PAD),
                            pady=(0, ui_home.px(10)), **where)
            else:
                widget.pack_forget()
        except Exception:
            pass

    def _refresh_offline_status(self):
        """The set changed, so the card is drawn again."""
        self._build_offline_rows()
        # The card changed height, so the pane has to measure itself
        # again — and the wrap widths inside the new rows have never
        # been measured at all.
        try:
            self.settings_scroll._lay_out()
            self.settle()
            self.settings_scroll._lay_out()
        except Exception:
            pass

    def _selected_pack(self):
        """(code, name) for the language chosen in the Add row."""
        chooser = getattr(self, "offline_choice", None)
        chosen = chooser.get() if chooser is not None else ""
        for code, name in self.OFFLINE_LANGS:
            if chosen.endswith(name):
                return code, name
        return None, chosen

    def _sync_pack_buttons(self):
        """Nothing to add means nothing to press."""
        button = getattr(self, "pack_button", None)
        if button is None:
            return
        code, _name = self._selected_pack()
        try:
            button.set_enabled(bool(code))
        except Exception:
            pass

    def _run_pack_job(self, verb, job, code=None, name=None):
        """Shared plumbing for downloading and removing."""
        if code is None:
            code, name = self._selected_pack()
        if not code:
            return
        self._say_offline("%s %s\u2026" % (verb, name))

        def work():
            def progress(message):
                self._post(self._say_offline, "%s  %s" % (name, message))
            ok, message = job(code, progress)
            self._post(self._download_done, ok, name, message)

        threading.Thread(target=work, daemon=True).start()

    def _download_pack(self):
        from . import local_engine
        code, name = self._selected_pack()
        other = CFG["target_lang"].split("-")[0]
        if not code:
            return
        self._run_pack_job(
            "Downloading",
            lambda c, progress: local_engine.install_language(
                c, other, progress=progress, force=False),
            code, name)

    def _remove_pack(self, code=None):
        from . import local_engine
        other = CFG["target_lang"].split("-")[0]
        name = dict(self.OFFLINE_LANGS).get(code, "")
        if code is None:
            code, name = self._selected_pack()
        self._run_pack_job(
            "Removing",
            lambda c, progress: local_engine.remove_language(
                c, other, progress=progress),
            code, name)

    def _download_done(self, ok, label_text, message):
        if ok:
            translator._preferred = None
            translator._cache.clear()
            self._refresh_offline_status()
        else:
            self._say_offline(
                "%s could not be downloaded: %s" % (label_text, message),
                self.palette["danger"])

    def _refresh_usage(self):
        """Show characters spent against Google's free 500,000 a month."""
        widget = getattr(self, "usage_label", None)
        if widget is None:
            return
        try:
            used, allowance = translator.google_usage()
        except Exception:
            return
        lines = []
        if CFG.get("gemini_api_key", ""):
            # A tally with no denominator, and that is the honest shape of
            # it: Google does not report what is left and has stopped
            # publishing the free-tier figures, so a fraction here would
            # be a number this app invented. What it can say is what it
            # spent — which is the question somebody asks when the
            # allowance runs out sooner than they expected, and the answer
            # that would have found the twenty-requests-per-snip bug in a
            # second.
            try:
                calls, _day = translator.gemini_usage()
                lines.append(
                    "Gemini: %s requests today from this computer "
                    "(the free allowance is per Google account, so "
                    "anything else using the key spends it too)"
                    % "{:,}".format(calls))
            except Exception:
                pass
        if not CFG.get("google_api_key", ""):
            widget.configure(
                text="\n".join(lines), justify="left",
                fg=self.palette["text_dim"])
            return
        # "on this computer", not "on the account". The count is kept
        # locally, but the allowance belongs to the key — so when a key is
        # shared, every copy of Squint shows only its own share of a pot
        # they are all drinking from. Someone reading "12 / 500,000" and
        # concluding there is plenty left would be wrong, and the way they
        # find out is a bill.
        text = ("Google: %s of %s characters, counted on this computer"
                % ("{:,}".format(used), "{:,}".format(allowance)))
        if lines:
            text = "\n".join(lines) + "\n" + text
        over = used >= allowance
        # The reading allowance is counted separately and charged
        # separately — it is images, not characters — so it is said
        # separately rather than folded into one number.
        try:
            from . import ocr_google
            shots, cap = ocr_google.usage()
            if shots:
                text += ("\nCloud Vision: %s of %s screenshots, counted on "
                         "this computer"
                         % ("{:,}".format(shots), "{:,}".format(cap)))
                over = over or shots >= cap
        except Exception:
            pass
        widget.configure(
            text=text, justify="left",
            fg=(self.palette["danger"] if over
                else self.palette["text_dim"]))

    def _test_connection(self):
        """Which layer is refusing: DNS, the firewall, TLS, or Google.

        The one that matters on a company network is TLS. A proxy that
        opens encrypted traffic to inspect it presents its own certificate;
        Windows has been told to trust it, so browsers are happy, and
        Python has not, so the app fails — which is exactly the shape of
        "the page opens in Brave but Squint times out".
        """
        # Whatever is in the key boxes is what gets tested. Focus leaving
        # a box saves it, and pressing this button does move focus — but
        # not on every platform and not from every widget, and a test
        # that quietly used the previous key would be worse than no test.
        try:
            self._save_keys(quiet=True)
        except Exception:
            pass
        self.key_status.configure(text="testing the connection…",
                                  fg=self.palette["text_dim"])

        self._blank_marks()

        def work():
            from . import netcheck
            try:
                ok, report = netcheck.summary()
            except Exception as exc:
                ok, report = False, "could not run the check: %s" % exc
            # And every key on its own service. A working connection to
            # Google says nothing about a Groq key, and one green line for
            # four keys was read as four green lights.
            keys = ""
            try:
                if any(_key for _key in (CFG.get(v, "") for v in
                                         translator.KEY_SETTINGS.values())):
                    translator.check_keys()
                    keys = self._key_lines()
            except Exception as exc:
                keys = str(exc)[:160]
            self._post(self._show_connection_result, ok, report, keys)

        threading.Thread(target=work, daemon=True).start()

    def _key_lines(self):
        """"Gemini ● working · Groq ● rejected: …" — one per key tested."""
        parts = []
        for name in translator.KEY_SETTINGS:
            verdict = translator.KEY_RESULTS.get(name)
            if verdict is None:
                continue
            good, why = verdict
            word = {True: "working", False: "not working",
                    None: "valid, but"}.get(good, "")
            detail = "" if good is True else ": %s" % why
            parts.append("%s %s%s" % (name, word, detail))
        return "   ·   ".join(parts)

    def _blank_marks(self):
        for mark in getattr(self, "key_marks", {}).values():
            try:
                mark.configure(text="…", fg=self.palette["text_dim"])
            except Exception:
                pass

    def _show_connection_result(self, ok, report, keys=""):
        # Written to the log as well as shown. The panel has room for a few
        # lines; a report worth sending to somebody is worth keeping.
        try:
            from .main import log
            log("connection check:\n%s" % report)
        except Exception:
            pass
        lines = [line.strip() for line in report.splitlines()]
        if ok:
            shown = ("Everything between this computer and Google is "
                     "working. If translating still fails, the fault is at "
                     "Google's end or with the key itself.")
        else:
            failed = [line for line in lines if line.startswith(("FAIL",))
                      or " FAIL " in line]
            shown = failed[0] if failed else lines[-1]
        if keys:
            shown = "%s\n%s" % (keys, shown)
            ok = ok and all(good is not False for good, _why
                            in translator.KEY_RESULTS.values())
        self._mark_keys()
        self.key_status.configure(
            text=shown, fg=self.palette["success" if ok else "danger"])

    def _get_gemini_key(self):
        """Open the key page, then fill the box when the key is copied.

        The page is the easy half. The hard half is what happens after
        pressing the copy icon: the key is on the clipboard, the browser is
        in front, and Google will not show that key again. People come back
        to an empty field with no way to tell whether they copied it.

        So Squint watches its own clipboard while that tab is open and
        types the key in itself. It stops at the first key, or after a few
        minutes — see key_catch, which explains why this is deliberately
        narrow.
        """
        from . import key_catch
        webbrowser.open("https://aistudio.google.com/apikey")
        watcher = getattr(self, "_key_watcher", None)
        if watcher is not None:
            watcher.stop()
        self.key_status.configure(
            text="Press Create API key, then copy it — Squint will fill it "
                 "in here.", fg=self.palette["text_dim"])
        self._key_watcher = key_catch.Watcher(
            self, self._gemini_key_arrived,
            ignore=self.var_aikey.get()).start()

    def _gemini_key_arrived(self, key):
        self.var_aikey.set(key)
        self.key_status.configure(
            text="Key filled in. Press Test connection to check it.",
            fg=self.palette["text_dim"])

    def _save_keys(self, quiet=False):
        """Save the keys, and unless asked not to, prove they work.

        Saving a key that turns out to be rejected is worse than not having
        one: the app looks configured and quietly keeps using the free
        services. So the key is tested here and the result said plainly.

        `quiet` saves without testing, which is what leaving a key box
        does. Testing every time the pointer moves off a field would
        spend somebody's allowance on a keystroke.
        """
        # A key copied out of a browser can arrive with a line break or a
        # stray space in it, which the service then rejects as invalid — an
        # error that looks exactly like a bad key. No API key contains
        # whitespace, so take it all out.
        def clean(var):
            value = "".join(var.get().split())
            var.set(value)
            return value

        CFG.set("gemini_api_key", clean(self.var_aikey))
        # A new key may belong to a different project, so the remembered
        # model name is no longer necessarily valid.
        CFG.set("gemini_model", "")
        CFG.set("google_api_key", clean(self.var_gkey))
        CFG.set("deepl_api_key", clean(self.var_dkey))
        groq_key = clean(self.var_qkey)
        if groq_key != CFG.get("groq_api_key", ""):
            # A new key may see a different list of models.
            CFG.set("groq_model", "")
        CFG.set("groq_api_key", groq_key)
        translator._preferred = None
        translator._cache.clear()
        try:
            translator.load_key_checks()
            self._mark_keys()
        except Exception:
            pass
        if quiet:
            return
        self.key_status.configure(text="testing…",
                                  fg=self.palette["text_dim"])

        def work():
            try:
                ok, message = translator.check_keys()
            except Exception as exc:
                ok, message = False, str(exc)[:110]
            # The same key has to be allowed to do two different things,
            # and the second one fails on its own: a new project has Cloud
            # Vision switched off, and a restricted key does not include
            # it. Testing only translation would call that key good and
            # leave screen reading quietly broken.
            if CFG.get("google_api_key", "") and CFG.get(
                    "use_cloud_vision", True):
                try:
                    from . import ocr_google
                    vok, vmsg = ocr_google.check_key()
                except Exception as exc:
                    vok, vmsg = False, str(exc)[:160]
                message = "%s   ·   %s" % (message, vmsg)
                ok = ok and vok
            # And the same for Gemini, for the same reason: a key that
            # translates does not necessarily read pictures, and finding
            # that out mid-snip is finding it out too late.
            if CFG.get("gemini_api_key", "") and CFG.get(
                    "use_gemini_ocr", True):
                try:
                    from . import ocr_gemini
                    gok, gmsg = ocr_gemini.check_key()
                except Exception as exc:
                    gok, gmsg = False, str(exc)[:160]
                # "Google is busy" is not a verdict on the key. Reporting
                # it in red alongside a rejected-key message teaches people
                # to distrust a key that is perfectly good.
                if not gok and "busy at the moment" in gmsg:
                    gok = True
                message = "%s   ·   %s" % (message, gmsg)
                ok = ok and gok
            self._post(self._show_key_result, ok, message)
            self._post(self._refresh_usage)

        threading.Thread(target=work, daemon=True).start()

    def show_update_available(self, release):
        """A line under the title, not a dialog.

        An update is never urgent enough to interrupt what someone is in
        the middle of, and a box that appears over the document they were
        reading is what teaches people to dismiss update prompts unread.
        This waits in the window until they happen to look.
        """
        self._pending_update = release
        try:
            self.update_banner.configure(
                text="Build %s is available  ·  Updates" % release.build)
        except Exception:
            pass
        # If Updates is already open, fill the card in too.
        try:
            if self._updates_built:
                self._update_checked(release, None)
        except Exception:
            pass
        self.refresh_update_dot()

    # -- updates -------------------------------------------------------
    def _set_update_status(self, text, colour=None):
        try:
            self.update_status.configure(
                text=text, fg=colour or self.palette["text_dim"])
        except Exception:
            pass

    def _check_update(self):
        from . import updater
        self.update_button.set_enabled(False)
        self._set_update_status("Checking…")

        def work():
            try:
                release = updater.check()
                self._post(self._update_checked, release, None)
            except Exception as exc:
                self._post(self._update_checked, None, str(exc)[:200])

        threading.Thread(target=work, daemon=True).start()

    def _update_checked(self, release, error):
        try:
            if not error:
                from . import updater
                updater.remember_available(release)
        except Exception:
            pass
        self._after_update_check(release, error)
        self.refresh_update_dot()

    def _after_update_check(self, release, error):
        self.update_button.set_enabled(True)
        if error:
            self._set_update_status(error, self.palette["danger"])
            return
        if release is None:
            self._pending_update = None
            self.install_button.pack_forget()
            self._show_new_build(None)
            self._set_update_status("You have the newest build.",
                                    self.palette["success"])
            return
        self._pending_update = release
        self.install_button.pack(side="right")
        self._show_new_build(release.build)
        notes = ("\n\n" + release.notes) if release.notes else ""
        self._set_update_status("Squint %s is ready to install.%s"
                                % (release.build, notes))

    def _show_new_build(self, build):
        """"1.48.6  →  1.48.7" beside the button, or just the old number."""
        try:
            # The install button takes the check button's place while
            # there is something to install, so the row is no wider than
            # it was and the grey line beside it is not cut short.
            if build:
                self.new_build_label.configure(text="→  %s" % build)
                self.new_build_label.pack(side="left", padx=(0, 12),
                                          after=self.build_label)
                self.update_button.pack_forget()
            else:
                self.new_build_label.pack_forget()
                if not self.update_button.winfo_ismapped():
                    self.update_button.pack(side="left",
                                            after=self.build_label)
        except Exception:
            pass

    def _install_update(self):
        from . import updater
        release = self._pending_update
        if release is None:
            return
        self.install_button.set_enabled(False)
        self.update_button.set_enabled(False)
        self._set_update_status("Downloading…")

        def work():
            try:
                def progress(fraction):
                    self._post(self._set_update_status,
                               "Downloading… %d%%" % int(fraction * 100))
                path = updater.download(release, progress=progress)
                self._post(self._set_update_status, "Installing…")
                backup = updater.install(path)
                if updater.requirements_changed(backup):
                    # The one case where an update is not just a code
                    # swap. It used to say so and restart immediately,
                    # which put the sentence on screen for less time than
                    # it takes to read and left the packages uninstalled;
                    # the build that needed it shipped a feature that
                    # quietly did nothing for everyone who updated from
                    # in here. It installs them.
                    self._post(self._set_update_status,
                               "Installing packages — this one takes a "
                               "minute\u2026")
                    # With the installer from the build just unpacked, not
                    # the one this process started with: a fix to how
                    # packages are installed should apply to the update
                    # that brings it.
                    fresh = updater
                    try:
                        import importlib
                        fresh = importlib.reload(updater)
                    except Exception:
                        pass
                    ok, said = fresh.install_requirements()
                    if not ok:
                        self._post(
                            self._set_update_status,
                            "Updated, but some new packages did not "
                            "install (%s). Quit Squint and open it again: "
                            "it finishes them in the background." % said,
                            self.palette["warning"])
                        # Not restarted. A restart here would replace the
                        # only sentence that says what still has to be
                        # done with a window that looks perfectly fine.
                        self._post(self._update_failed_softly)
                        return
                self._post(self._restart_for_update)
            except Exception as exc:
                self._post(self._update_failed, str(exc)[:220])

        threading.Thread(target=work, daemon=True).start()

    def _update_failed_softly(self):
        """The code updated and something after it did not.

        The buttons go back on without the status line being overwritten:
        what it says is the only record of what is left to do.
        """
        try:
            self.install_button.set_enabled(True)
            self.update_button.set_enabled(True)
        except Exception:
            pass

    def _update_failed(self, message):
        self.install_button.set_enabled(True)
        self.update_button.set_enabled(True)
        self._set_update_status(message, self.palette["danger"])

    def _restart_for_update(self):
        from . import updater
        self._set_update_status("Restarting…", self.palette["success"])
        self.update_idletasks()
        try:
            self.after(400, updater.restart)
        except Exception:
            self._set_update_status(
                "Installed. Close Squint and start it again to finish.",
                self.palette["success"])

    # Where the coffee button goes. One line, overridable from the settings
    # file, because the link that actually works has to be confirmed by the
    # person whose account it is — a payment link is not something to guess
    # at and ship to other people.
    #
    # A PayPal.Me handle is the better address if you have one: it is short,
    # it is testable in a browser in five seconds, and it does not put an
    # email address into a file that anyone can download.
    DONATE_URL = ("https://www.paypal.com/donate/?business="
                  "pranayratan%40gmail.com&no_recurring=0"
                  "&item_name=Squint&currency_code=EUR")

    def donate_url(self):
        return str(CFG.get("donate_url", "") or "").strip() or self.DONATE_URL

    def _open_donate(self):
        try:
            webbrowser.open(self.donate_url())
        except Exception:
            pass

    def _open_key_help(self):
        from .ui_help_keys import KeyHelp
        try:
            window = KeyHelp(self, palette=self.palette)
            window.lift()
            platform_util.raise_to_front(window)
        except Exception as exc:
            self.key_status.configure(text=str(exc)[:160],
                                      fg=self.palette["danger"])

    def _guide_opener(self, which):
        """A command for the question mark on one key's row."""
        def go():
            try:
                ui_guide.show(self, which, palette=self.palette)
            except Exception:
                # A guide that will not open must not take the settings
                # window down with it. The written guide is still two
                # buttons away.
                pass
        return go

    def _even_wraps(self):
        """One width for every grey line in the pane.

        The narrowest row decides and everything follows it, so the text
        down the whole of Settings ends on one straight edge instead of
        on a different one per row. Run from `settle`, once the pane has
        been laid out — a widget asked how wide it is before it is on
        screen answers one pixel.
        """
        lines = getattr(self, "_wrap_lines", ())
        if not lines:
            return
        # Two kinds, and only one of them has a control beside it.
        #
        # A row's grey line shares its row with a switch or a dropdown,
        # so what it may take is the row less that control — and every
        # row takes the same, which is the point. The line along the
        # bottom of a card shares its row with nothing and may have the
        # whole card; giving it the rows' width would wrap a full-width
        # footnote into a narrow column with half the card empty beside
        # it.
        # Worked out from the card's width and a fixed column for the
        # controls, not from measuring what each row's control happens
        # to be. Measuring was unstable: the same pane opened twice gave
        # two different answers, because a row measured before it had
        # been laid out reports a width of one pixel and the narrowest
        # row decides for all of them. One bad measurement, and every
        # line in Settings wrapped into a column a third of the width it
        # should have had — which is exactly what two screenshots of the
        # same page, taken minutes apart, showed.
        #
        # The card's width is stable: it follows the window, and the
        # window does not resize. CONTROL_W is what the widest control
        # in the pane is allowed, in the design's own pixels, so the
        # answer is the same on both platforms and the same every time.
        card = None
        for line, holder in lines:
            try:
                width = line.master.master.winfo_width()
            except Exception:
                continue
            if width > 200:
                card = width if card is None else max(card, width)
        if not card:
            return
        room = card - ui_home.px(self.CONTROL_W) - ui_home.px(self.ROW_PAD) * 2
        for line, holder in lines:
            try:
                if holder is None:
                    strip = line.master
                    want = strip.winfo_width() - ui_home.px(10)
                else:
                    want = room
                if want and want > 120 and abs(
                        int(line.cget("wraplength")) - want) > 2:
                    line.configure(wraplength=want)
            except Exception:
                continue

    def _square_up_keys(self):
        """One width for the three key boxes, one for the three buttons.

        Run from `settle`, once the card has been laid out: a widget
        asked how wide it is before it is on screen answers one pixel,
        and three rows agreeing on one pixel is not the same as three
        rows agreeing.
        """
        doors = getattr(self, "key_doors", ())
        fields = getattr(self, "key_fields", ())
        if not doors or not fields:
            return
        try:
            widest = max(button.winfo_reqwidth() for button in doors)
            for button in doors:
                button.set_min_width(widest)
            # And the boxes take what is left of the narrowest row, so
            # all three end at the same place.
            # Sized to the same column every other row's control gets,
            # so the key rows do not stick out past the rest of the pane
            # — and so the grey text beside them wraps where all the
            # other grey text does. A key is long and the box scrolls;
            # the sentences do not.
            hows = getattr(self, "key_hows", ())
            how = max([b.winfo_reqwidth() for b in hows] or [0])
            box = max(ui_home.px(150),
                      ui_home.px(self.CONTROL_W) - widest - how
                      - ui_home.px(28 if how else 24))
            for field in fields:
                field.configure(width=box)
                field.canvas.configure(width=box)
        except Exception:
            pass

    def _help_for(self, which):
        """The written guide for one engine, or the general one.

        The picture guides are built from screenshots that ship with the
        app and there is not one for every engine. Falling back to the
        written help is better than a button that is sometimes there and
        sometimes not — a row of links that changes shape depending on
        what is installed is a row nobody learns.
        """
        def go():
            if ui_guide.available(which):
                self._guide_opener(which)()
                return
            self._open_key_help()
        return go

    def _open_google_console(self):
        """Straight to the console, where the key actually comes from.

        The guided checklist is still here — it is "How to set up Google
        API" under the rows. This button is for somebody who knows what
        they are doing and wants the page.
        """
        webbrowser.open("https://console.cloud.google.com/apis/credentials")

    def _open_groq_keys(self):
        """Groq's key page. Signing in there is an email or a Google
        account, no card; then Create API Key, copy, paste."""
        webbrowser.open("https://console.groq.com/keys")

    def _open_deepl_signup(self):
        """DeepL's API plans. The free tier needs an account and a card
        on file, which is worth knowing before starting — it is on that
        page, said plainly, which is why this opens the page rather than
        trying to explain it in a settings row."""
        webbrowser.open("https://www.deepl.com/pro-api")

    def _open_google_setup(self):
        from .ui_setup import GoogleSetup
        try:
            window = GoogleSetup(self, palette=self.palette,
                                 on_saved=self._google_setup_done)
            window.lift()
            platform_util.raise_to_front(window)
        except Exception as exc:
            self.key_status.configure(text=str(exc)[:160],
                                      fg=self.palette["danger"])

    def _google_setup_done(self):
        """Pick up a key the checklist saved, without a restart."""
        try:
            self.var_gkey.set(CFG.get("google_api_key", ""))
            translator._preferred = None
            translator._cache.clear()
            self._refresh_usage()
            self._update_ocr_note()
        except Exception:
            pass

    # ● worked, ● failed, ● could not be judged — busy, or out of
    # allowance, neither of which is a verdict on the key.
    KEY_MARK = {True: "●", False: "●", None: "●"}

    def _show_key_result(self, ok, message):
        self._mark_keys()
        # The joined line stays, because it carries the service's own
        # words and those are the part somebody can act on. What it no
        # longer does is pass one colour over four answers.
        self.key_status.configure(
            text=message,
            fg=self.palette["text_dim"] if self._marks_disagree()
            else (self.palette["success"] if ok
                  else self.palette["danger"]))

    def _mark_keys(self):
        colours = {True: self.palette["success"],
                   False: self.palette["danger"],
                   None: self.palette["warning"]}
        for name, mark in getattr(self, "key_marks", {}).items():
            verdict = translator.KEY_RESULTS.get(name)
            try:
                if verdict is None:
                    mark.configure(text="")
                    continue
                good, _why = verdict
                mark.configure(text=self.KEY_MARK.get(good, "●"),
                               fg=colours.get(good,
                                              self.palette["text_dim"]))
            except Exception:
                pass

    def _marks_disagree(self):
        """True when the keys did not all say the same thing.

        The line under them is then a summary of several answers, and a
        summary of several answers should not be painted as though it were
        one — which is how a working Google key came to be shown in red
        because Gemini had run out for the day.
        """
        seen = {good for good, _why in translator.KEY_RESULTS.values()}
        return len(seen) > 1

    def _set_hk_status(self, text, colour=None):
        """Show the shortcut result, and take the line away again when
        there is nothing to report."""
        try:
            self.hk_status.configure(
                text=text, fg=colour or self.palette["text_dim"])
            if text:
                self.hk_footer.pack(fill="x", pady=(16, 0))
            else:
                self.hk_footer.pack_forget()
        except Exception:
            pass

    def _permission_row(self, parent, p):
        """macOS only: the two permissions, as a two-step checklist.

        ① Accessibility, for the clipboard shortcut, then ② Screen
        Recording, for snips. One button starts it; Squint opens each
        list in System Settings, notices the first switch by itself and
        moves on to the second, and ends with the one restart macOS needs.
        Nothing here on Windows, where the question does not arise.
        """
        if sys.platform != "darwin":
            return
        holder = tk.Frame(parent, bg=p["surface"])
        holder.pack(fill="x", padx=ui_home.px(self.ROW_PAD),
                    pady=(ui_home.px(14), ui_home.px(12)))
        label(holder, p, "macOS permissions", size=10, weight="bold",
              bg=p["surface"]).pack(anchor="w", pady=(0, ui_home.px(8)))
        self._perm_rows = {}
        for key, number, title, what in (
                ("accessibility", "1", "Copy selected text",
                 "Accessibility — lets the clipboard shortcut press ⌘C for "
                 "you."),
                ("screen", "2", "Snip the screen",
                 "Screen & System Audio Recording — lets a snip see what is "
                 "on screen.")):
            row = tk.Frame(holder, bg=p["surface"])
            row.pack(fill="x", pady=(0, 8))
            mark = label(row, p, number, size=10, weight="bold",
                         bg=p["surface"], width=2)
            mark.pack(side="left", padx=(0, 8))
            words = tk.Frame(row, bg=p["surface"])
            words.pack(side="left", fill="x", expand=True)
            label(words, p, title, size=10, bg=p["surface"]).pack(anchor="w")
            label(words, p, what, size=9, dim=True, bg=p["surface"],
                  wraplength=520, justify="left").pack(anchor="w")
            state = label(row, p, "", size=10, dim=True, bg=p["surface"])
            button = PillButton(
                row, "Enable", command=lambda k=key: self._enable_permission(k),
                palette=p, kind="primary", height=Dropdown.HEIGHT,
                bg=p["surface"])
            self._perm_rows[key] = (mark, state, button)
        foot = tk.Frame(holder, bg=p["surface"])
        foot.pack(fill="x")
        self.permission_note = label(
            foot, p, "", size=9, dim=True, wraplength=720, justify="left",
            bg=p["surface"])
        self.permission_restart = PillButton(
            foot, "Restart Squint", command=self._restart_for_permission,
            palette=p, kind="primary", height=Dropdown.HEIGHT,
            bg=p["surface"])
        self.permission_state = self._perm_rows["accessibility"][1]
        self.permission_button = self._perm_rows["accessibility"][2]
        self._perm_asked_screen = False
        self._perm_poll_job = None
        self.sync_permission()

    def sync_permission(self):
        rows = getattr(self, "_perm_rows", None)
        if not rows:
            return
        from . import mac_permissions as mp
        p = self.palette
        done = {"accessibility": mp.accessibility_ok(),
                "screen": mp.screen_ok()}
        for key, (mark, state, button) in rows.items():
            if done[key]:
                mark.configure(text="✓", fg=p["success"])
                state.pack_forget()
                try:
                    button.configure_text("Enabled")
                    button.set_enabled(False)
                except Exception:
                    pass
                button.pack(side="right")
            elif key == "screen" and self._perm_asked_screen:
                mark.configure(text="2", fg=p["text"])
                try:
                    button.configure_text("Open again")
                    button.set_enabled(True)
                except Exception:
                    pass
                state.configure(text="Switch it on, then restart",
                                fg=p["text_dim"])
                state.pack(side="right", padx=(0, 10))
                button.pack(side="right")
            else:
                mark.configure(text="1" if key == "accessibility" else "2",
                               fg=p["text"])
                state.pack_forget()
                try:
                    button.configure_text("Enable")
                    button.set_enabled(True)
                except Exception:
                    pass
                button.pack(side="right")
        note = self.permission_note
        if all(done.values()):
            note.pack_forget()
            self.permission_restart.pack_forget()
        elif self._perm_asked_screen and done["accessibility"]:
            note.configure(text="Switch Squint on in the list System Settings "
                                "is showing. macOS then offers Quit & "
                                "Reopen — or press Restart Squint here.")
            note.pack(anchor="w", pady=(4, 6))
            self.permission_restart.pack(anchor="w")
        else:
            note.configure(text="macOS lets only you switch these on. Press "
                                "Enable: Squint opens the right list in "
                                "System Settings — flip the switch next to "
                                "Squint and it carries on from there.")
            note.pack(anchor="w", pady=(4, 0))
            self.permission_restart.pack_forget()

    def _ask_permission(self):
        """Kept for the callers that still use the old name."""
        self._enable_permission("accessibility")

    def _enable_permission(self, which):
        from . import mac_permissions as mp
        if which == "accessibility":
            mp.ask_accessibility()
            self._poll_accessibility(0)
        else:
            self._perm_asked_screen = True
            mp.ask_screen()
        self.sync_permission()

    # How long to keep watching for the Accessibility switch: a second at a
    # time, for five minutes, then it stops rather than polling for ever.
    PERMISSION_POLL_MS = 1000
    PERMISSION_POLL_LIMIT = 300

    def _poll_accessibility(self, count):
        from . import mac_permissions as mp
        if mp.accessibility_ok():
            self.sync_permission()
            # Step two follows by itself, unless it is already done.
            if not mp.screen_ok():
                self.after(600, lambda: self._enable_permission("screen"))
            return
        if count >= self.PERMISSION_POLL_LIMIT:
            return
        self._perm_poll_job = self.after(
            self.PERMISSION_POLL_MS,
            lambda: self._poll_accessibility(count + 1))

    def say_toolkit_ready(self):
        """The Mac stability fix is in place; it takes effect on restart."""
        try:
            status = self.header_status
            status.configure(text="Stability fix installed  ·  Restart "
                                  "Squint →", fg=self.palette["accent"],
                             cursor="hand2")
            status.bind("<Button-1>", self._restart_for_toolkit, add="+")
        except Exception:
            pass

    def _restart_for_toolkit(self, _event=None):
        if "Stability fix" not in str(self.header_status.cget("text")):
            return
        from . import updater
        try:
            self.after(200, updater.restart)
        except Exception:
            pass

    def _say_permissions(self):
        """On a Mac missing a permission, one line on the front page that
        leads to the checklist. Nothing once both are on."""
        if sys.platform != "darwin":
            return
        try:
            from . import mac_permissions as mp
            if mp.all_ok():
                if "permission" in str(self.header_status.cget("text")):
                    self.header_status.configure(text="", cursor="")
                return
            status = self.header_status
            status.configure(text="Two permissions to switch on  ·  Set up "
                                  "→", fg=self.palette["accent"],
                             cursor="hand2")
            status.bind("<Button-1>", self._open_permissions, add="+")
        except Exception:
            pass

    def _open_permissions(self, _event=None):
        try:
            from . import mac_permissions as mp
            if "permission" not in str(self.header_status.cget("text")):
                return
            if mp.all_ok():
                self.header_status.configure(text="")
                return
            if self.current_pane != "Settings":
                self._toggle_settings()
            self.after(150, lambda: self._enable_permission(
                "accessibility" if not mp.accessibility_ok() else "screen"))
        except Exception:
            pass

    def _restart_for_permission(self):
        from . import updater
        try:
            self.after(200, updater.restart)
        except Exception:
            pass

    def _hotkey_row(self, parent, text, value, row, cfg_key):
        """A field you click and then press the keys into.

        Typing "ctrl+cmd+t" and pressing Apply gave no sign whether the app
        understood it, whether it was legal, or whether another app already
        owned it — which is most of why the shortcuts took so long to get
        right. Pressing the keys answers all three immediately.
        """
        from .shortcut_field import ShortcutField
        p = self.palette
        label(parent, p, text, size=10, bg=p["surface"]).grid(
            row=row, column=0, sticky="w", pady=ROW_GAP)
        field = ShortcutField(
            parent, p, value=value,
            on_change=lambda spec, k=cfg_key: self._on_hotkey_captured(
                spec, k),
            bg=p["surface"])
        field.grid(row=row, column=1, sticky="w", padx=(LABEL_GAP, 0),
                   pady=ROW_GAP)
        return field

    def _on_hotkey_captured(self, spec, cfg_key):
        """A pause before a risky shortcut actually takes over the system.

        The field used to apply the instant a combination was pressed —
        no gap between pressing a key and it becoming a global shortcut.
        That is how a clipboard shortcut ended up bound to Cmd+C: nothing
        stood between one keypress and every Copy on the machine going to
        Squint instead. hotkey.risky() already knew which combinations are
        contested; the field just never asked before acting on the
        answer. It still does not refuse anything — a knowing yes is
        respected — it only stops assuming the keypress was the yes.
        """
        fields = {"hotkey": (self.hk_snip, "Snip & translate"),
                  "hotkey_clipboard": (self.hk_clip, "Translate clipboard")}
        field = fields[cfg_key][0]
        if spec:
            for other_key, (other_field, other_name) in fields.items():
                if other_key == cfg_key:
                    continue
                other_spec = other_field.get().strip() or CFG[other_key]
                if other_spec and hotkey.normalise(spec) == \
                        hotkey.normalise(other_spec):
                    # Not "risky" — flatly impossible. Two fields firing
                    # the same combination means only one of them would.
                    messagebox.showerror(
                        "Squint",
                        "That's already the shortcut for %s." % other_name,
                        parent=self)
                    field.set(CFG[cfg_key])
                    return
            warning = hotkey.risky(spec)
            if warning and not messagebox.askyesno(
                    "Squint", warning + "\n\nUse it anyway?", parent=self):
                field.set(CFG[cfg_key])
                return
        self.apply_hotkeys()

    def _reset_hotkeys(self):
        """Both shortcuts back to what they were on a fresh install.

        No confirmation. The person pressing this has a shortcut they want
        rid of; asking them to confirm getting rid of it is a dialog with
        one sensible answer, and the thing it would guard is one keypress
        away from being undone anyway.
        """
        snip_spec, clip_spec = platform_util.default_hotkeys()
        self.hk_snip.set(snip_spec)
        self.hk_clip.set(clip_spec)
        self.apply_hotkeys()

    def _wrap_to_fit(self, root):
        """Make every wrapped paragraph wrap to the width it has.

        The cards were written with the wrap widths typed in — 720, 680,
        560 — which were right for the window those cards were laid out
        in and are wrong in any other. A label wider than its parent is
        not clipped at the right; it is centred, so the sentence loses
        its first words off one side and its last off the other. The
        window has a size of its own now, and these follow it.
        """
        # The grey line under a settings row is not one of these. Those
        # are given one width for the whole pane by `_even_wraps`, so
        # that they end on a single straight edge; measuring each one
        # against its own holder — which is what this does, correctly,
        # for everything else — is exactly what made them ragged.
        owned = {id(line) for line, _holder in getattr(self, "_wrap_lines", ())}
        for widget in self._every(root):
            if not isinstance(widget, tk.Label) or id(widget) in owned:
                continue
            try:
                if int(widget.cget("wraplength")) <= 0:
                    continue
            except Exception:
                continue
            holder = widget.master

            def fit(_event=None, label=widget, holder=holder):
                try:
                    room = holder.winfo_width() - ui_home.px(20)
                    if room > 80 and abs(int(label.cget("wraplength"))
                                         - room) > 2:
                        label.configure(wraplength=room)
                except Exception:
                    pass

            self._fits.append(fit)

    @staticmethod
    def _every(widget, found=None):
        found = [] if found is None else found
        for child in widget.winfo_children():
            found.append(child)
            MainWindow._every(child, found)
        return found

    def _switch_row(self, parent, title, note, variable, command,
                    last=False, pady=(0, 0)):
        p = self.palette
        row = tk.Frame(parent, bg=p["surface"])
        row.pack(fill="x", pady=pady)
        text_col = tk.Frame(row, bg=p["surface"])
        text_col.pack(side="left", fill="x", expand=True)
        label(text_col, p, title, size=10, bg=p["surface"]).pack(anchor="w")
        # Wrapped to whatever room the row actually has. Left to run on
        # one line it is wider than the card, and a label wider than its
        # parent is centred — so the sentence lost its first word off one
        # side and its last off the other.
        note_label = label(text_col, p, note, size=9, dim=True,
                           bg=p["surface"], justify="left", anchor="w")
        note_label.pack(anchor="w", fill="x")
        self._fits.append(
            lambda lb=note_label, col=text_col: lb.configure(
                wraplength=max(160, col.winfo_width() - 8)))
        Switch(row, p, variable=variable, command=command,
               bg=p["surface"]).pack(side="right")
        if not last:
            line = divider(row.master, p)
            line.pack(fill="x", pady=9)

    def apply_hotkeys(self):
        ok, msg = self.controller.apply_hotkeys(self.hk_snip.get().strip(),
                                                self.hk_clip.get().strip())
        self._set_hk_status(
            msg, self.palette["success"] if ok else self.palette["danger"])
        # The shortcut is printed in two places on the front page now —
        # on the button itself and in the tip along the bottom — and
        # both have to be told. This used to set a subtitle that no
        # longer exists, which meant changing a shortcut raised rather
        # than applied.
        keys = self._shortcut_keys()
        for widget in (getattr(self, "snip_button", None),
                       getattr(self, "tip_bar", None)):
            try:
                widget.set_keys(keys)
            except Exception:
                pass
        self.hk_snip.set(CFG["hotkey"])
        self.hk_clip.set(CFG["hotkey_clipboard"])

    def _toggle_startup(self):
        enabled = self.var_startup.get()
        ok, msg = self.controller.set_run_at_startup(enabled)
        if not ok:
            self.var_startup.set(not enabled)
            messagebox.showerror("Squint", msg, parent=self)
        else:
            CFG.set("run_at_startup", enabled)

    def _open_path(self, path):
        if not platform_util.open_path(path):
            webbrowser.open("file:///" + path.replace("\\", "/"))

    def _open_data_dir(self):
        self._open_path(config.data_dir())

    @staticmethod
    def _glossary_where():
        try:
            from . import glossary
            return glossary.user_path()
        except Exception:
            return ""

    def _open_glossary(self):
        """Open the user's own glossary, making it first if need be.

        Opening a path that does not exist yet does nothing at all on
        Windows and shows an error on macOS, and "nothing happened" is the
        worst possible answer to a button that says Open.
        """
        try:
            from . import glossary
            glossary.ensure_file()
        except Exception:
            pass
        where = self._glossary_where()
        if where:
            self._open_path(where)

    def restyle(self):
        """Change scheme without changing window.

        The whole scheme is baked into several hundred widgets when they
        are built, so something has to be thrown away and made again.
        What used to be thrown away was the window — and a window is the
        one thing that must not blink, because a new one is a new one to
        the system as well: it appears, it takes focus, it has no history
        of where the old one was. Every attempt to cover that up with
        fades was covering up the wrong thing.

        So the window stays and its contents are rebuilt inside it. It
        happens at once, with nothing dimmed and nothing faded: click,
        and the page is in the other scheme.

        There was a fade, through four releases, and it was answering a
        question nobody asked. Fading the window's opacity dims the
        whole thing to almost nothing and brings it back, which is not a
        colour transition however smoothly it is done — it is the window
        blinking out and returning, with the change hidden inside the
        blink. Making the blink smoother made it slower and no better.
        Doing it instantly is both the faster answer and the honest one:
        there is no transition, so nothing pretends there is.

        What survives is what always survived, and the window's position
        above all: this rebuilds the contents of a window that is never
        replaced, so there is nothing to put back. Also carried over:
        which pane you were on, and what is in the two boxes.
        """
        pane = self.current_pane
        try:
            source = self.file_src.get("1.0", "end-1c")
            answer = self.file_dst.get("1.0", "end-1c")
        except Exception:
            source = answer = ""
        try:
            self.hero_picture.stop()
        except Exception:
            pass
        for timer in list(getattr(self, "_timers", [])) + \
                [getattr(self, "_box_job", None),
                 getattr(self, "_auto_job", None)]:
            if timer:
                try:
                    self.after_cancel(timer)
                except Exception:
                    pass
        self._timers, self._box_job, self._auto_job = [], None, None
        # Built first, shown second, and the old one thrown away in
        # between — with no redraw in the gap, so the window never shows
        # an empty interior. That grey rectangle halfway through the
        # change was the whole of what still looked wrong: the fade was
        # fading, but what it was fading was nothing.
        going = getattr(self, "root_frame", None)
        ui_home.SETTLING = True
        try:
            self.page = theme_mod.page(CFG.get("theme", "auto"))
            self.palette = theme_mod.bridge(self.page)
            self._build(show=False)
        except Exception:
            # A hold that is never let go leaves the band permanently
            # unable to draw itself, which is a far worse outcome than
            # whatever went wrong here.
            ui_home.SETTLING = False
            raise
        coming = self.root_frame
        if going is not None:
            try:
                going.destroy()
            except Exception:
                pass
        self.configure(bg=self.page["bg_a"])
        coming.pack(fill="both", expand=True)
        self.open_pane(pane)
        try:
            if source:
                self.file_src.insert("1.0", source)
            if answer:
                self.file_dst.insert("1.0", answer)
            self._sync_box_height()
        except Exception:
            pass
        # The band's layout is deferred to idle so that a rebuild paints
        # it once instead of five times. This is where that debt is
        # settled — before anything is shown, so the window is drawn in
        # the new scheme complete rather than in two goes.
        ui_home.SETTLING = False
        try:
            self.hero_picture.flush(force=True)
        except Exception:
            pass
        try:
            self.update_idletasks()
        except Exception:
            pass
        try:
            self.controller._palette = self.palette
        except Exception:
            pass

    def settle(self):
        """Take the measurements that needed the pane to be on screen."""
        try:
            self.update_idletasks()
        except Exception:
            pass
        for fit in list(getattr(self, "_fits", ())):
            try:
                fit()
            except Exception:
                pass

    def open_pane(self, name):
        """Put the window on a named pane, building it if it has never
        been opened. Safe to call before the window is on screen."""
        try:
            if name == "Settings":
                if self.current_pane != "Settings":
                    self._toggle_settings()
            elif name == "Support":
                self._show_support()
            elif name == "Updates":
                self._show_updates()
            else:
                self._show_pane("Translate")
        except Exception:
            pass

    # -- fading ---------------------------------------------------------
    #
    # There is none, and that is deliberate. The scheme change was the
    # only thing that ever used it, and a fade of the window's opacity
    # was the wrong instrument for it: it dims the whole window to
    # almost nothing and brings it back, which reads as a blink with the
    # change hidden inside it rather than as a colour transition. Four
    # releases went into making that blink smoother. The change is
    # instant now, and the machinery is gone rather than left lying
    # around for somebody to reach for again.

    def show(self):
        self.deiconify()
        self.lift()
        try:
            self.focus_force()
        except Exception:
            pass
        # On macOS a window from a non-bundled process can open behind
        # everything else; this pulls it forward.
        platform_util.raise_to_front(self)
        self.sync_language()
        # Permissions may have been switched on while the window was away.
        self._say_permissions()
        try:
            self.sync_permission()
        except Exception:
            pass
        # A pane built while the window was hidden had no width to wrap
        # against. Now it has one.
        if self.current_pane == "Settings":
            try:
                self.settings_scroll._lay_out()
            except Exception:
                pass
        self.wake()

    def hide(self):
        # A shortcut field left listening has released the app's shortcuts.
        # Closing the window on top of that would leave Squint with none of
        # them and nothing on screen to say so.
        try:
            from .shortcut_field import ShortcutField
            ShortcutField.disarm_any()
        except Exception:
            pass
        # Squint lives in the tray. A picture animating twenty-five times
        # a second behind a window nobody can see is a background app
        # spending somebody's battery on nothing.
        try:
            self.hero_picture.stop()
        except Exception:
            pass
        self.withdraw()
